"""Ventanas con F congelado y diagnóstico posterior de paridad por región."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tomllib
RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
from quantileflow.superficies import Rebanada,funcion_g,SuperficieSSVI
from quantileflow.opciones import precio_black
from experiments.cadena_comparador_20261010.evaluar_cadena import sha
from experiments.estabilidad_superficie_20261014.evaluar import ajustar,verificar_origen
from experiments.skew_bandas_20261010.evaluar import metricas
from experiments.ventana_superficie_20261014.evaluar import dump,params
from experiments.forward_fijo_20261014.metodo import diagnostico

RINGS=('centro','alas_3_6','alas_6_10','conjunto')


def restaurar(p):
    return SuperficieSSVI(np.array(p['tiempos']),np.array(p['thetas']),p['rho'],p['eta'],p['gamma'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('ventana','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();private=a.privado.resolve()
    if private.is_relative_to(RAIZ) or private==a.ventana.resolve():raise ValueError('privados separados fuera de Git')
    private.mkdir(parents=True,exist_ok=True)
    folder=Path(__file__).parent;out=folder/'resultados';out.mkdir(exist_ok=True)
    proto=tomllib.loads((folder/'protocolo.toml').read_text(encoding='utf-8'))
    source_file=RAIZ/'experiments/ventana_superficie_20261014/resultados/resumen.json'
    source=json.loads(source_file.read_text(encoding='utf-8'));verificar_origen(source['privados_sha256'],a.ventana)
    for name,h in source['codigo_sha256_lf'].items():
        if hashlib.sha256((RAIZ/name).read_text(encoding='utf-8').encode()).hexdigest()!=h:raise ValueError('código de origen cambió')
    cuts=[]
    for c in source['cortes']:
        tag=c['fecha']+'_'+c['hora'].replace(':','')
        e=pd.read_parquet(a.ventana/(tag+'_evaluacion.parquet'))
        old=json.loads((a.ventana/(tag+'_modelos.json')).read_text(encoding='utf-8'))
        base=old['modelos'][0];anchor={z['T']:z for z in base['rebanadas']}
        variants=[];models=[];diagnostics=[]
        for j,width in enumerate(proto['anchos']):
            original=old['modelos'][j];rs=[]
            for t,z in anchor.items():
                g=e[e.entrenamiento & (e.k.abs()<=width) & np.isclose(e.dias,t*365,rtol=0,atol=1e-10)]
                rs.append(Rebanada(t,z['F'],z['D'],g.strike.to_numpy(),g.bid.to_numpy(),g.ask.to_numpy(),g.tipo.eq('C').to_numpy(),((g.bid+g.ask)/2).to_numpy()))
            s=restaurar(base['parametros']) if width==.03 else ajustar(rs,proto['peso_mid'])
            col='fijo_'+str(width);e[col]=np.nan
            for t,z in anchor.items():
                mask=np.isclose(e.dias,t*365,rtol=0,atol=1e-10);g=e[mask];K=g.strike.to_numpy()
                e.loc[mask,col]=precio_black(z['F'],K,s.w(np.log(K/z['F']),t),z['D'],g.tipo.eq('C').to_numpy())
            k=np.linspace(-.3,.3,601);times=np.linspace(s.tiempos[0],s.tiempos[-1],25)
            gm=min(float(funcion_g(*s.derivadas(k,t),k).min()) for t in times)
            cal=float(np.diff(s.w(k[None,:],times[:,None]),axis=0).min())
            if gm<-1e-10 or cal<-1e-10 or not all(s.condiciones().values()):raise ValueError('superficie inválida')
            for name,column in (('reestimado','precio_'+str(width)),('fijo',col)):
                measures={ring:metricas(e[e.holdout & (e.anillo.eq(ring) if ring!='conjunto' else True)],column) for ring in RINGS}
                variants.append(dict(ancho=width,forward=name,holdout=measures))
            # Store only anchors, not the nominal quantiles/ranges of a different fit.
            models.append(dict(ancho=width,parametros=params(s),
                rebanadas=[{key:z[key] for key in ('T','F','D')} for z in anchor.values()],
                condiciones=s.condiciones(),g_min_malla=gm,incremento_w_min_malla=cal))
            anchors={z['T']:z for z in original['rebanadas']}
            for group,mask in (('training',e.entrenamiento),('holdout',e.holdout)):
                for ring in RINGS:
                    g=e[mask & (e.anillo.eq(ring) if ring!='conjunto' else True)]
                    for name in ('fijo','reestimado'):
                        total=dict(pares=0,incompatibles=0,minimo_incompatibles_F_libre=0)
                        for t,z in anchor.items():
                            gg=g[np.isclose(g.dias,t*365,rtol=0,atol=1e-10)]
                            F=z['F'] if name=='fijo' else anchors[t]['F']
                            d=diagnostico(gg,z['D'],F)
                            for key in total:total[key]+=d[key]
                        diagnostics.append(dict(ancho=width,forward=name,grupo=group,region=ring,**total))
        if not np.allclose(e['fijo_0.03'],e['precio_0.03'],rtol=0,atol=1e-10):raise ValueError('control nominal cambió')
        e.to_parquet(private/(tag+'_evaluacion.parquet'),index=False)
        dump(private/(tag+'_modelos.json'),dict(modelos_fijos=models,modelos_origen=old['modelos']))
        cuts.append(dict(fecha=c['fecha'],hora=c['hora'],apto_puntual=c['apto_puntual'],bloqueos=c['bloqueos'],variantes=variants,paridad=diagnostics))
        print(tag,[(v['ancho'],v['forward'],v['holdout']['centro']['dentro']) for v in variants],flush=True)
    totals=[];parity=[]
    for width in proto['anchos']:
        for name in ('reestimado','fijo'):
            vv=[v for c in cuts for v in c['variantes'] if v['ancho']==width and v['forward']==name]
            totals.append(dict(ancho=width,forward=name,holdout={ring:dict(filas=sum(v['holdout'][ring]['filas'] for v in vv),dentro=sum(v['holdout'][ring]['dentro'] for v in vv)) for ring in RINGS}))
            for group in ('training','holdout'):
                for ring in RINGS:
                    dd=[d for c in cuts for d in c['paridad'] if (d['ancho'],d['forward'],d['grupo'],d['region'])==(width,name,group,ring)]
                    parity.append(dict(ancho=width,forward=name,grupo=group,region=ring,
                        **{key:sum(d[key] for d in dd) for key in ('pares','incompatibles','minimo_incompatibles_F_libre')}))
    if len(cuts)!=12 or totals[0]['holdout']['centro']['dentro']!=744:raise ValueError('control 744 falló')
    files=[Path(__file__),folder/'metodo.py',folder/'protocolo.toml',
        RAIZ/'experiments/estabilidad_superficie_20261014/evaluar.py',
        RAIZ/'experiments/skew_bandas_20261010/control_forward.py',RAIZ/'quantileflow/superficies.py',RAIZ/'quantileflow/opciones.py']
    dump(out/'resumen.json',dict(protocolo=proto,cortes=cuts,total=totals,paridad=parity,origen_sha256=sha(source_file),
        codigo_sha256_lf={f.relative_to(RAIZ).as_posix():hashlib.sha256(f.read_text(encoding='utf-8').encode()).hexdigest() for f in files},
        privados_sha256={f.name:sha(f) for f in sorted(private.glob('*')) if f.suffix in ('.parquet','.json')}))


if __name__=='__main__':main()
