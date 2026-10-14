"""Reproducción independiente de 2x2, forward convexo y conteos privados."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import ndtr


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--privado',type=Path,required=True)
    a=ap.parse_args()
    carpeta=Path(__file__).parent/'resultados'
    r=json.loads((carpeta/'resumen.json').read_text(encoding='utf-8'))
    for name,h in (r['fuentes_sha256_lf']|r['fuentes_historicas_sha256_lf']).items():
        assert hashlib.sha256((RAIZ/name).read_text(encoding='utf-8').encode()).hexdigest()==h,name
    assert sha(RAIZ/'configs/piloto.toml')==r['config_sha256']
    for name,h in r['privado_sha256'].items():
        ruta=(a.privado/name).resolve()
        assert ruta.is_relative_to(a.privado.resolve()) and sha(ruta)==h,name
    maxerr,precios,forwardchecks=0.,0,0
    allids=set()
    for c in r['cortes']:
        tag=c['fecha']+'_'+c['hora'].replace(':','')
        e=pd.read_parquet(a.privado/(tag+'_evaluacion.parquet'))
        p=json.loads((a.privado/(tag+'_parametros.json')).read_text(encoding='utf-8'))
        assert np.array_equal(e.entrenamiento,~e.holdout)
        assert e.groupby(['dias','strike']).holdout.nunique().eq(1).all()
        allids.update(e.id_contrato)
        for j,(dias,g) in enumerate(e.groupby('dias',sort=True)):
            t=float(dias)/365;D=np.exp(-p['tasa']*t)
            fs=p['forwards'][str(t)]
            tr=g[g.entrenamiento]
            intervals=[]
            for K,gg in tr.groupby('strike'):
                cc=gg[gg.tipo=='C'];pp=gg[gg.tipo=='P']
                assert len(cc)==1 and len(pp)==1
                intervals.append((K+(cc.bid.iloc[0]-pp.ask.iloc[0])/D,K+(cc.ask.iloc[0]-pp.bid.iloc[0])/D))
            ints=np.array(intervals);h=(ints[:,1]-ints[:,0])/2
            def loss(F):
                d=np.maximum(ints[:,0]-F,0)+np.maximum(F-ints[:,1],0)
                return np.sum((d/h)**2+r['protocolo']['peso_mid']*((F-ints.mean(axis=1))/h)**2)
            independent=minimize_scalar(loss,bounds=(ints.min(),ints.max()),method='bounded',options={'xatol':1e-9})
            assert loss(fs['estimado'])<=loss(independent.x)+1e-6
            forwardchecks+=1
            K=g.strike.to_numpy();mask=g.tipo.eq('C').to_numpy()
            for anchor in ('declarado','estimado'):
                F=fs[anchor];params=p['ajustes'][anchor]
                theta=np.interp(t,params['tiempos'],params['thetas'])
                phi=params['eta']/(theta**params['gamma']*(1+theta)**(1-params['gamma']))
                k=np.log(K/F);rho=params['rho']
                ww=theta/2*(1+rho*phi*k+np.sqrt((phi*k+rho)**2+1-rho*rho))
                for model,w in [('plano',params['planas'][str(t)]**2*t),('ssvi',ww)]:
                    sq=np.sqrt(w);d1=(-k+w/2)/sq;d2=d1-sq
                    price=np.where(mask,D*(F*ndtr(d1)-K*ndtr(d2)),D*(K*ndtr(-d2)-F*ndtr(-d1)))
                    maxerr=max(maxerr,float(abs(price-g[anchor+'_'+model].to_numpy()).max()))
                    hd=g.holdout.to_numpy()
                    n=int(((price[hd]>=g.bid.to_numpy()[hd])&(price[hd]<=g.ask.to_numpy()[hd])).sum())
                    assert n==c['por_vencimiento'][j]['metricas'][anchor][model]['dentro']
                    precios+=len(price)
    assert maxerr<1e-8
    for anchor in ('declarado','estimado'):
        for model in ('plano','ssvi'):
            assert r['total'][anchor][model]['dentro']==sum(v['metricas'][anchor][model]['dentro'] for c in r['cortes'] for v in c['por_vencimiento'])
    def scan(v):
        if isinstance(v,dict):
            assert not(set(v)&{'bid','ask','strike','id_contrato','spot','theta','thetas','rho','eta','gamma','forwards'})
            for vv in v.values(): scan(vv)
        elif isinstance(v,list):
            for vv in v: scan(vv)
    text=(carpeta/'resumen.json').read_text(encoding='utf-8')
    assert not any(id in text for id in allids)
    scan(json.loads(text))
    out=dict(cortes=len(r['cortes']),precios_reproducidos=precios,max_error_precio=maxerr,
        forwards_convexos_verificados=forwardchecks,huellas_y_split_correctos=True,
        sin_datos_individuales_en_json_publico=True,resumen_sha256=sha(carpeta/'resumen.json'),
        verificador_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest())
    (carpeta/'verificacion.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
