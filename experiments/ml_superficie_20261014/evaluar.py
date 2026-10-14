"""Entrena red pequeña y convexo con training; guarda mercado fuera de Git."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import tomllib
RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
import scipy
import clarabel
from quantileflow.superficies import Rebanada
from experiments.forward_superficies_20261014.evaluar import restaurar
from experiments.skew_bandas_20261010.evaluar import metricas
from experiments.ml_superficie_20261014.modelos import ajustar_red, ajustar_convexo


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--origen',type=Path,required=True)
    ap.add_argument('--privado',type=Path,required=True)
    ap.add_argument('--publico',type=Path,default=Path(__file__).parent/'resultados')
    a=ap.parse_args()
    out=a.privado.resolve();pub=a.publico.resolve()
    if out.is_relative_to(RAIZ) or out.is_relative_to(pub) or pub.is_relative_to(out):raise ValueError('privados separados y fuera de Git')
    oldpath=RAIZ/'experiments/forward_superficies_20261014/resultados/resumen.json'
    old=json.loads(oldpath.read_text(encoding='utf-8'))
    for name,h in old['privado_sha256'].items():
        p=(a.origen/name).resolve()
        if not p.is_relative_to(a.origen.resolve()) or sha(p)!=h:raise ValueError('datos históricos alterados')
    for name,h in (old['fuentes_sha256_lf']|old['fuentes_historicas_sha256_lf']).items():
        if hashlib.sha256((RAIZ/name).read_text(encoding='utf-8').encode()).hexdigest()!=h:raise ValueError('código base alterado')
    proto_path=Path(__file__).with_name('protocolo.toml');proto=tomllib.loads(proto_path.read_text(encoding='utf-8'))
    out.mkdir(parents=True,exist_ok=True);pub.mkdir(parents=True,exist_ok=True)
    cortes=[]
    for c in old['cortes']:
        tag=c['fecha']+'_'+c['hora'].replace(':','')
        e=pd.read_parquet(a.origen/(tag+'_evaluacion.parquet'))
        params=json.loads((a.origen/(tag+'_parametros.json')).read_text(encoding='utf-8'))
        if not np.array_equal(e.entrenamiento,~e.holdout) or not e.groupby(['dias','strike']).holdout.nunique().eq(1).all():raise ValueError('split inválido')
        fit=restaurar(params['ajustes']['estimado'])
        def rebs(df):
            rr=[]
            for dias,g in df.groupby('dias',sort=True):
                t=float(dias)/365;f=params['forwards'][str(t)]
                rr.append((g.index,Rebanada(t,f['estimado'],f['D'],g.strike.to_numpy(float),g.bid.to_numpy(float),g.ask.to_numpy(float),g.tipo.eq('C').to_numpy())))
            return rr
        rs=[r for _,r in rebs(e[e.entrenamiento])]
        start=time.perf_counter();red,redinfo=ajustar_red(rs,fit.superficie,proto);tred=time.perf_counter()-start
        start=time.perf_counter();conv,convinfo=ajustar_convexo(rs,proto);tconv=time.perf_counter()-start
        for model in ('red','convexo'):e[model]=np.nan
        for ids,r in rebs(e):
            e.loc[ids,'red']=red.precios(r)
            e.loc[ids,'convexo']=conv.precios(r)
        measures={}
        for model,col in [('ssvi','estimado_ssvi'),('red','red'),('convexo','convexo')]:
            measures[model]={grupo:metricas(e[mask],col) for grupo,mask in [('train',e.entrenamiento),('holdout',e.holdout)]}
            # distance to band: unlike distance to mid, zero for every inside-band price
            h=e[e.holdout];p=h[col].to_numpy();dist=abs(p-np.clip(p,h.bid,h.ask))/((h.ask-h.bid)/2)
            measures[model]['holdout']['media_distancia_fuera_semispreads']=float(np.mean(dist))
        e.to_parquet(out/(tag+'_evaluacion.parquet'),index=False)
        dump(out/(tag+'_modelos.json'),dict(origen_parametros=params,red_pesos=red.pesos.tolist(),
            convexo_tiempos=conv.tiempos.tolist(),convexo_soporte=conv.soporte.tolist(),convexo_masas=conv.masas.tolist()))
        cortes.append(dict(fecha=c['fecha'],hora=c['hora'],apto_puntual=c['apto_puntual'],bloqueos=c['bloqueos'],
            medidas=measures,red=redinfo,convexo=convinfo,tiempos_seg=dict(red=tred,convexo=tconv)))
        print(tag,{m:measures[m]['holdout']['dentro'] for m in measures},'red convergente/coherente',redinfo['elegido']['convergencia'],redinfo['elegido']['pasa_malla_y_alas'],'convexo',convinfo['convergencia'],convinfo['pasa_restricciones'],flush=True)
    total={}
    for m in ('ssvi','red','convexo'):
        total[m]=dict(filas=sum(c['medidas'][m]['holdout']['filas'] for c in cortes),dentro=sum(c['medidas'][m]['holdout']['dentro'] for c in cortes),
            train_filas=sum(c['medidas'][m]['train']['filas'] for c in cortes),train_dentro=sum(c['medidas'][m]['train']['dentro'] for c in cortes),
            medianas_error_por_corte=[c['medidas'][m]['holdout']['mediana_error_semispreads'] for c in cortes])
    if total['ssvi']['dentro']!=744:raise ValueError('base SSVI no reproduce 744')
    total['red']['cortes_convergentes']=sum(c['red']['elegido']['convergencia'] for c in cortes)
    total['red']['cortes_pasan_malla']=sum(c['red']['elegido']['pasa_malla_y_alas'] for c in cortes)
    total['convexo']['cortes_convergentes']=sum(c['convexo']['convergencia'] for c in cortes)
    total['convexo']['cortes_pasan_restricciones']=sum(c['convexo']['pasa_restricciones'] for c in cortes)
    sources=[Path(__file__),Path(__file__).with_name('modelos.py'),proto_path,
        Path(__file__).with_name('graficas.py'),Path(__file__).with_name('verificar.py'),Path(__file__).with_name('requirements.txt'),
        RAIZ/'quantileflow/superficies.py',RAIZ/'quantileflow/opciones.py']
    dump(pub/'resumen.json',dict(naturaleza=proto['alcance'],protocolo=proto,cortes=cortes,total=total,
        origen_resumen_sha256=sha(oldpath),integridad_origen=old['integridad'],
        entorno=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,pandas=pd.__version__,clarabel=clarabel.__version__),
        codigo_sha256_lf={x.relative_to(RAIZ).as_posix():hashlib.sha256(x.read_text(encoding='utf-8').encode()).hexdigest() for x in sources},
        privados_sha256={x.name:sha(x) for x in sorted(out.iterdir()) if x.suffix in ('.parquet','.json')}))
    print(json.dumps(total,indent=2),flush=True)


if __name__=='__main__':main()
