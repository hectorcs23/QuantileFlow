"""Recalcula CDF/cuantiles y conteos de precios sin usar el valorador del ajuste."""
import argparse,hashlib,json,sys
from pathlib import Path
RAIZ=Path(__file__).resolve().parents[2];sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
from scipy.special import ndtr


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def formulas(p,T,x,factor):
    th=np.interp(T,p['tiempos'],p['thetas']);rho=p['rho']
    phi=p['eta']/(th**p['gamma']*(1+th)**(1-p['gamma']))
    k=np.log(np.asarray(x)/factor);root=np.sqrt((phi*k+rho)**2+1-rho*rho)
    w=th/2*(1+rho*phi*k+root)
    w1=th/2*phi*(rho+(phi*k+rho)/root)
    dm=-k/np.sqrt(w)-np.sqrt(w)/2
    cdf=ndtr(-dm)+np.exp(-dm*dm/2)/np.sqrt(2*np.pi)*w1/(2*np.sqrt(w))
    return w,cdf


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('privado','forward','ml'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();folder=Path(__file__).parent/'resultados';r=json.loads((folder/'resumen.json').read_text(encoding='utf-8'))
    for name,h in r['codigo_sha256_lf'].items():assert hashlib.sha256((RAIZ/name).read_text(encoding='utf-8').encode()).hexdigest()==h
    for name,h in r['privados_sha256'].items():assert sha(a.privado/name)==h
    roots=0;prices=0;maxcdferr=maxdifferr=0.;ids=set()
    for c in r['cortes']:
        tag=c['fecha']+'_'+c['hora'].replace(':','');e=pd.read_parquet(a.forward/(tag+'_evaluacion.parquet'));ids.update(e.id_contrato)
        origin=json.loads((a.forward/(tag+'_parametros.json')).read_text(encoding='utf-8'));orig=origin['ajustes']['estimado']
        pp=json.loads((a.privado/(tag+'_sensibilidad.json')).read_text(encoding='utf-8'))
        for case,pub in zip(pp['casos'],c['variantes']):
            count=0;observed=[];qd=[]
            for z in case['rebanadas']:
                t=z['T'];F,F0=z['F'],z['F_nominal'];q=np.array(z['cuantiles_modelo_diagnostico'])
                _,cdf=formulas(case['parametros'],t,q,F/F0)
                maxcdferr=max(maxcdferr,float(abs(cdf-r['protocolo']['cuantiles']).max()));roots+=len(q)
                q0=np.array(next(y['cuantiles_modelo_ssvi'] for y in pp['contraste_modelos'] if y['T']==t))
                qd.append(abs((q-q0)*10000));g=e[np.isclose(e.dias,t*365,atol=1e-10,rtol=0)]
                tr=g[g.entrenamiento];x=np.linspace(tr.strike.min()/F0,tr.strike.max()/F0,401)
                obs=100*np.max(abs(formulas(case['parametros'],t,x,F/F0)[1]-formulas(orig,t,x,1)[1]));observed.append(obs)
                maxdifferr=max(maxdifferr,abs(obs-z['cdf_observada_max_pp']))
                h=g[g.holdout];K=h.strike.to_numpy();D=origin['forwards'][str(t)]['D']
                w,_=formulas(case['parametros'],t,K/F0,F/F0);sq=np.sqrt(w);d1=(np.log(F/K)+w/2)/sq;d2=d1-sq
                price=np.where(h.tipo.eq('C'),D*(F*ndtr(d1)-K*ndtr(d2)),D*(K*ndtr(-d2)-F*ndtr(-d1)))
                count+=int(((price>=h.bid)&(price<=h.ask)).sum());prices+=len(h)
            assert count==pub['holdout']['dentro']
            assert np.allclose(np.max(qd,axis=0),pub['cuantiles_mov_max_bp'],atol=1e-8,rtol=0)
            assert abs(max(observed)-pub['cdf_observada_max_pp'])<1e-10
        mp=json.loads((a.ml/(tag+'_modelos.json')).read_text(encoding='utf-8'))
        nodes=np.array(mp['convexo_soporte']);ks=[]
        for j,z in enumerate(pp['contraste_modelos']):
            t=z['T'];F0=origin['forwards'][str(t)]['estimado'];g=e[np.isclose(e.dias,t*365,atol=1e-10,rtol=0)&e.entrenamiento]
            lo,hi=g.strike.min()/F0,g.strike.max()/F0
            points=np.unique(np.r_[lo,hi,nodes[(nodes>=lo)&(nodes<=hi)]])
            probs=np.array(mp['convexo_masas'])[j]
            target=formulas(orig,t,points,1)[1]
            left=(points[:,None]>nodes)@probs;right=(points[:,None]>=nodes)@probs
            left=np.where(points>lo,left,right)
            value=100*max(np.max(abs(left-target)),np.max(abs(right-target)))
            assert abs(value-z['cdf_observada_max_pp'])<1e-10
            ks.append(value)
        assert abs(max(ks)-c['contraste_modelos']['cdf_observada_max_pp'])<1e-10
    assert maxcdferr<1e-9 and maxdifferr<1e-10
    txt=(folder/'resumen.json').read_text(encoding='utf-8');assert not any(i in txt for i in ids)
    out=dict(cuantiles_verificados=roots,precios_holdout_reproducidos=prices,
        max_error_cdf_en_cuantil=maxcdferr,max_error_movimiento_cdf_pp=maxdifferr,
        conteos_precio_reproducidos=True,distancia_cdf_entre_modelos_reproducida=True,huellas_correctas=True,
        resumen_sha256=sha(folder/'resumen.json'),codigo_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest())
    (folder/'verificacion.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(json.dumps(out,indent=2))


if __name__=='__main__':main()
