"""Contraste exploratorio 2x2, universo y holdout congelados del 10 de octubre.

Guarda parámetros/cotizaciones solo fuera del repo. No cambia captura ni rankings.
"""
import argparse
from dataclasses import replace
import hashlib
import json
import math
import platform
from pathlib import Path
import sys
import tomllib

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import numpy as np
import pandas as pd
import scipy
from experiments.cadena_comparador_20261010.evaluar_cadena import integridad, sha
from experiments.skew_bandas_20261010.evaluar import rebanadas, metricas
from experiments.skew_bandas_20261010.control_forward import maximo_solapamiento
from experiments.forward_superficies_20261014.metodo import estimar_forward, intervalos_forward, cambiar_forward
from quantileflow.ajuste_bandas import AjusteBandas, ajustar_bandas, precios_ajuste, incompatibilidades_paridad
from quantileflow.adaptador_comparador import preparar_comparador
from quantileflow.superficies import SuperficieSSVI, funcion_g
from quantileflow.piloto import cargar_config


def dump(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')


def serializar(ajuste):
    s = ajuste.superficie
    return dict(planas={str(t):v for t,v in ajuste.planas.items()}, tiempos=s.tiempos.tolist(),
                thetas=s.thetas.tolist(),rho=s.rho,eta=s.eta,gamma=s.gamma,diagnostico=ajuste.diagnostico)


def restaurar(p):
    s = SuperficieSSVI(np.array(p['tiempos']),np.array(p['thetas']),p['rho'],p['eta'],p['gamma'])
    if not all(s.condiciones().values()):
        raise ValueError('superficie de origen no cumple condiciones')
    return AjusteBandas({float(t):v for t,v in p['planas'].items()},s,{})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for n in ('tablas','crudo','origen-privado','salida-privada'):
        ap.add_argument('--'+n,type=Path,required=True)
    ap.add_argument('--salida-publica',type=Path,default=Path(__file__).parent/'resultados')
    a = ap.parse_args()
    privado, publico = a.salida_privada.resolve(),a.salida_publica.resolve()
    if privado.is_relative_to(RAIZ) or privado.is_relative_to(publico) or publico.is_relative_to(privado):
        raise ValueError('privados fuera de Git y separados de salida pública')
    old = json.loads((RAIZ/'experiments/skew_bandas_20261010/resultados/resumen.json').read_text(encoding='utf-8'))
    for file,h in old['fuentes_sha256_lf'].items():
        if hashlib.sha256((RAIZ/file).read_text(encoding='utf-8').encode()).hexdigest()!=h:
            raise ValueError('código histórico alterado: '+file)
    for file,h in old['salidas_privadas_sha256'].items():
        if sha(a.origen_privado/file)!=h: raise ValueError('salida histórica alterada')
    evidencia = integridad(a.tablas,a.crudo)
    if evidencia!=old['integridad']: raise ValueError('snapshot no coincide')
    cfg = cargar_config(RAIZ/'configs/piloto.toml')
    if sha(RAIZ/'configs/piloto.toml')!=old['config_sha256']: raise ValueError('config cambió')
    protocolo_path = Path(__file__).with_name('protocolo.toml')
    protocolo = tomllib.loads(protocolo_path.read_text(encoding='utf-8'))
    if [(c['fecha'],c['hora']) for c in old['cortes']]!=[(f,h) for f in protocolo['fechas'] for h in protocolo['horas']]:
        raise ValueError('fotos históricas no coinciden con protocolo')
    qs = pd.read_parquet(a.tablas/'cotizaciones.parquet')
    refs = pd.read_parquet(a.tablas/'subyacente.parquet')
    privado.mkdir(parents=True,exist_ok=True)
    publico.mkdir(parents=True,exist_ok=True)
    cortes, stresses = [], []
    desplazamientos = []
    for previo in old['cortes']:
        fecha,hora = previo['fecha'],previo['hora']
        tag = fecha+'_'+hora.replace(':','')
        e = pd.read_parquet(a.origen_privado/(tag+'_evaluacion.parquet'))
        op = old['protocolo']
        prep = preparar_comparador(qs,refs,fecha,hora,cfg.reglas,modo_descriptivo=True,
            tasa=cfg.tasa,q=cfg.rendimiento_dividendo,ancho_atm=op['ancho_evaluacion'],
            **{k:op[k] for k in ('ancho_evaluacion','minimo_dias','maximo_dias','minimo_entrenamiento','objetivos_moneyness')})
        if not e[['id_contrato','entrenamiento','holdout']].reset_index(drop=True).equals(
            prep.evaluacion[['id_contrato','entrenamiento','holdout']].reset_index(drop=True)):
            raise ValueError('universo/split no coincide')
        if e.groupby(['dias','strike']).entrenamiento.nunique().max()!=1:
            raise ValueError('call y put repartidos entre grupos')
        train = rebanadas(e[e.entrenamiento],prep.spot,cfg.tasa,cfg.rendimiento_dividendo)
        f = {r.T:estimar_forward(r,protocolo['peso_mid']) for r in train}
        desplazamientos.extend(100*(f[r.T]/r.F-1) for r in train)
        training_estimado = [cambiar_forward(r,f[r.T]) for r in train]
        oldp = json.loads((a.origen_privado/(tag+'_ajustes.json')).read_text(encoding='utf-8'))
        ajustes = {'declarado':restaurar(oldp['parametros']['0.5']),
                   'estimado':ajustar_bandas(training_estimado,protocolo['preferencia'],protocolo['peso_mid'])}
        medidas, por_vencimiento = {}, []
        for anchor,fit in ajustes.items():
            gmin = min(float(funcion_g(*fit.superficie.derivadas(np.linspace(-2,2,4001),t),np.linspace(-2,2,4001)).min()) for t in fit.superficie.tiempos)
            if not all(fit.superficie.condiciones().values()) or gmin < -1e-10:
                raise ValueError('arbitraje de superficie')
            medidas[anchor] = {'g_min_malla':gmin,'condiciones':fit.superficie.condiciones()}
            for model in ('plano','ssvi'):
                col=anchor+'_'+model
                e[col]=np.nan
                for dias,g in e.groupby('dias',sort=True):
                    r=rebanadas(g,prep.spot,cfg.tasa,cfg.rendimiento_dividendo)[0]
                    if anchor=='estimado': r=cambiar_forward(r,f[r.T])
                    e.loc[g.index,col]=precios_ajuste(fit,r,model)
                medidas[anchor][model]={grupo:metricas(e[mask],col) for grupo,mask in
                    (('train',e.entrenamiento),('holdout',e.holdout))}
        for j,original in enumerate(train):
            g=e[e.dias==original.T*365]
            # Group floating times by a close equality only after unique times verified.
            if g.empty: g=e[np.isclose(e.dias,original.T*365,rtol=0,atol=1e-10)]
            row={'indice_vencimiento':j+1,'dias':float(original.T*365),'metricas':{},'paridad':{}}
            for anchor in ('declarado','estimado'):
                r=original if anchor=='declarado' else cambiar_forward(original,f[original.T])
                row['paridad'][anchor]=incompatibilidades_paridad(r)
                rh=rebanadas(g[g.holdout],prep.spot,cfg.tasa,cfg.rendimiento_dividendo)[0]
                if anchor=='estimado': rh=cambiar_forward(rh,f[rh.T])
                row['paridad'][anchor+'_holdout']=incompatibilidades_paridad(rh)
                row['metricas'][anchor]={m:metricas(g[g.holdout],anchor+'_'+m) for m in ('plano','ssvi')}
            aa=intervalos_forward(original)
            row['paridad']['minimo_incompatibles']=len(aa)-maximo_solapamiento(aa)
            por_vencimiento.append(row)
        # Carry shocks are parity diagnostics only. Frozen rows and split, no recalibration.
        for tasa,q in [(r,cfg.rendimiento_dividendo) for r in protocolo['estres_tasa']]+[(cfg.tasa,q) for q in protocolo['estres_dividendo'] if q!=cfg.rendimiento_dividendo]:
            pares=decl=est=lim=0
            for r in rebanadas(e[e.entrenamiento],prep.spot,tasa,q):
                F=estimar_forward(r,protocolo['peso_mid'])
                p0=incompatibilidades_paridad(r);p1=incompatibilidades_paridad(cambiar_forward(r,F))
                pares+=p0['pares'];decl+=p0['incompatibles'];est+=p1['incompatibles']
                aa=intervalos_forward(r);lim+=len(aa)-maximo_solapamiento(aa)
            stresses.append(dict(fecha=fecha,hora=hora,tasa=tasa,q=q,pares=pares,declarado=decl,estimado=est,minimo=lim))
        e.to_parquet(privado/(tag+'_evaluacion.parquet'),index=False)
        dump(privado/(tag+'_parametros.json'),dict(spot=prep.spot,tasa=cfg.tasa,q=cfg.rendimiento_dividendo,
            forwards={str(r.T):dict(declarado=r.F,estimado=f[r.T],D=r.D) for r in train},
            ajustes={anchor:serializar(fit) for anchor,fit in ajustes.items()}))
        cortes.append(dict(fecha=fecha,hora=hora,apto_puntual=prep.apto_puntual,bloqueos=list(prep.bloqueos),
            medidas=medidas,por_vencimiento=por_vencimiento))
        print(tag, {anchor:{m:medidas[anchor][m]['holdout']['dentro'] for m in ('plano','ssvi')} for anchor in ajustes},flush=True)
    totales={}
    for anchor in ('declarado','estimado'):
        totales[anchor]={m:dict(filas=sum(c['medidas'][anchor][m]['holdout']['filas'] for c in cortes),
            dentro=sum(c['medidas'][anchor][m]['holdout']['dentro'] for c in cortes),
            medianas_por_corte=[c['medidas'][anchor][m]['holdout']['mediana_error_semispreads'] for c in cortes]) for m in ('plano','ssvi')}
        totales[anchor]['paridad']={grupo:dict(pares=sum(v['paridad'][grupo]['pares'] for c in cortes for v in c['por_vencimiento']),
            incompatibles=sum(v['paridad'][grupo]['incompatibles'] for c in cortes for v in c['por_vencimiento'])) for grupo in (anchor,anchor+'_holdout')}
    if totales['declarado']['plano']['dentro']!=107 or totales['declarado']['ssvi']['dentro']!=357:
        raise ValueError('control histórico no reproduce 107/357')
    fuentes=[Path(__file__),Path(__file__).with_name('metodo.py'),protocolo_path,
        Path(__file__).with_name('graficas.py'),Path(__file__).with_name('verificar.py'),
        Path(__file__).with_name('control_pdf.py'),
        RAIZ/'quantileflow/ajuste_bandas.py',RAIZ/'quantileflow/superficies.py',RAIZ/'quantileflow/opciones.py']
    out=dict(naturaleza=protocolo['alcance'],presupuesto_datos=0,protocolo=protocolo,integridad=evidencia,
        config_sha256=sha(RAIZ/'configs/piloto.toml'),
        entorno=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,pandas=pd.__version__),
        fuentes_historicas_sha256_lf=old['fuentes_sha256_lf'],
        origen_resumen_sha256=sha(RAIZ/'experiments/skew_bandas_20261010/resultados/resumen.json'),
        fuentes_sha256_lf={x.relative_to(RAIZ).as_posix():hashlib.sha256(x.read_text(encoding='utf-8').encode()).hexdigest() for x in fuentes},
        privado_sha256={x.name:sha(x) for x in sorted(privado.glob('*')) if x.suffix in ('.parquet','.json')},
        cortes=cortes,total=totales,carry=stresses,
        desplazamiento_forward_pct=dict(mediana=float(np.median(desplazamientos)),minimo=float(min(desplazamientos)),maximo=float(max(desplazamientos))))
    dump(publico/'resumen.json',out)
    print(json.dumps(totales,indent=2),flush=True)


if __name__=='__main__': main()
