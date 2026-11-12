"""Precios independientes, restricciones exactas y huellas del ensayo ML."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
from scipy.special import ndtr


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--privado',type=Path,required=True);a=ap.parse_args()
    folder=Path(__file__).parent/'resultados';r=json.loads((folder/'resumen.json').read_text(encoding='utf-8'))
    for file,h in r['codigo_sha256_lf'].items():
        assert hashlib.sha256((RAIZ/file).read_text(encoding='utf-8').encode()).hexdigest()==h,file
    for file,h in r['privados_sha256'].items():
        p=(a.privado/file).resolve();assert p.is_relative_to(a.privado.resolve()) and sha(p)==h,file
    ids=set();maxerr=0.;n=0;masserr=meanerr=0.;calmin=0.
    for c in r['cortes']:
        tag=c['fecha']+'_'+c['hora'].replace(':','')
        e=pd.read_parquet(a.privado/(tag+'_evaluacion.parquet'));p=json.loads((a.privado/(tag+'_modelos.json')).read_text(encoding='utf-8'))
        ids.update(e.id_contrato);assert np.array_equal(e.entrenamiento,~e.holdout)
        assert e.groupby(['dias','strike']).holdout.nunique().eq(1).all()
        base=p['origen_parametros']['ajustes']['estimado'];weights=np.array(p['red_pesos']);x=np.array(p['convexo_soporte']);masses=np.array(p['convexo_masas'])
        masserr=max(masserr,float(abs(masses.sum(axis=1)-1).max()));meanerr=max(meanerr,float(abs(masses@x-1).max()))
        assert masses.min()>=-1e-10
        prices_knots=np.maximum(x[None,:]-x[:,None],0)@masses.T
        calmin=min(calmin,float(np.diff(prices_knots,axis=1).min()))
        predictions={model:np.zeros(len(e)) for model in ('ssvi','red','convexo')}
        for j,(dias,g) in enumerate(e.groupby('dias',sort=True)):
            t=float(dias)/365;f=p['origen_parametros']['forwards'][str(t)];F,D=f['estimado'],f['D']
            K=g.strike.to_numpy();k=np.log(K/F);theta=np.interp(t,base['tiempos'],base['thetas']);rho=base['rho']
            phi=base['eta']/(theta**base['gamma']*(1+theta)**(1-base['gamma']))
            wb=theta/2*(1+rho*phi*k+np.sqrt((phi*k+rho)**2+1-rho*rho))
            delta=.25*np.tanh(np.tanh(k[:,None]/.03*weights[:4]+weights[4:8])@weights[8:12]+weights[12])
            for model,w in [('ssvi',wb),('red',wb*np.exp(delta))]:
                sq=np.sqrt(w);d1=(-k+w/2)/sq;d2=d1-sq
                pp=np.where(g.tipo.eq('C'),D*(F*ndtr(d1)-K*ndtr(d2)),D*(K*ndtr(-d2)-F*ndtr(-d1)))
                predictions[model][g.index]=pp
                col='estimado_ssvi' if model=='ssvi' else model
                maxerr=max(maxerr,float(abs(pp-g[col]).max()));n+=len(g)
            pay=np.where(g.tipo.eq('C').to_numpy()[:,None],np.maximum(x-K[:,None]/F,0),np.maximum(K[:,None]/F-x,0))
            pp=D*F*(pay@masses[j]);predictions['convexo'][g.index]=pp
            maxerr=max(maxerr,float(abs(pp-g.convexo).max()));n+=len(g)
        for model,price in predictions.items():
            for group,mask in [('train',e.entrenamiento.to_numpy()),('holdout',e.holdout.to_numpy())]:
                inside=int(((price[mask]>=e.bid.to_numpy()[mask])&(price[mask]<=e.ask.to_numpy()[mask])).sum())
                assert inside==c['medidas'][model][group]['dentro']
    assert maxerr<1e-8 and max(masserr,meanerr)<1e-8 and calmin>=-1e-8
    def scan(v):
        if isinstance(v,dict):
            assert not(set(v)&{'bid','ask','strike','id_contrato','spot','red_pesos','convexo_masas','convexo_soporte','rho','eta','gamma','thetas'})
            for vv in v.values():scan(vv)
        elif isinstance(v,list):
            for vv in v:scan(vv)
    txt=(folder/'resumen.json').read_text(encoding='utf-8');assert not any(id in txt for id in ids);scan(json.loads(txt))
    out=dict(precios_reproducidos=n,max_error_precio=maxerr,error_masa_max=masserr,error_media_max=meanerr,
        calendario_min=calmin,split_y_huellas_correctos=True,datos_individuales_fuera_de_git=True,
        resumen_sha256=sha(folder/'resumen.json'),codigo_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest())
    (folder/'verificacion.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(json.dumps(out,indent=2))


if __name__=='__main__':main()
