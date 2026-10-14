"""Control independiente de precios, forward congelado y límites de paridad."""
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


def price(p,t,F,D,g):
    th=np.interp(t,p['tiempos'],p['thetas']);rho=p['rho']
    phi=p['eta']/(th**p['gamma']*(1+th)**(1-p['gamma']))
    K=g.strike.to_numpy();k=np.log(K/F)
    w=th/2*(1+rho*phi*k+np.sqrt((phi*k+rho)**2+1-rho*rho))
    sq=np.sqrt(w);d1=(-k+w/2)/sq;d2=d1-sq
    return np.where(g.tipo.eq('C'),D*(F*ndtr(d1)-K*ndtr(d2)),D*(K*ndtr(-d2)-F*ndtr(-d1)))


def parity(g,D,F,col):
    lows=[];highs=[];bad=0;forced=0
    for K,pair in g.groupby('strike',sort=True):
        if len(pair)!=2:continue
        c=pair[pair.tipo.eq('C')].iloc[0];p=pair[pair.tipo.eq('P')].iloc[0]
        lo=K+(c.bid-p.ask)/D;hi=K+(c.ask-p.bid)/D
        lows.append(lo);highs.append(hi)
        incompatible=F<lo-1e-9 or F>hi+1e-9
        bad+=int(incompatible)
        if incompatible:
            outside=not (c.bid<=c[col]<=c.ask and p.bid<=p[col]<=p.ask)
            assert outside;forced+=1
    assert not lows or min(lows)>0
    # Independent sweep of closed interval endpoints. Starts processed before ends.
    events=sorted([(l,1) for l in lows]+[(u,-1) for u in highs],key=lambda z:(z[0],-z[1]))
    alive=peak=0
    for _,d in events:alive+=d;peak=max(peak,alive)
    return dict(pares=len(lows),incompatibles=bad,minimo_incompatibles_F_libre=len(lows)-peak),forced


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('privado','ventana'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();folder=Path(__file__).parent/'resultados'
    r=json.loads((folder/'resumen.json').read_text(encoding='utf-8'))
    for n,h in r['codigo_sha256_lf'].items():assert hashlib.sha256((RAIZ/n).read_text(encoding='utf-8').encode()).hexdigest()==h
    for n,h in r['privados_sha256'].items():assert sha(a.privado/n)==h
    nprices=anchors=forced=0;err=0.;ids=set();aggregate={};agparity={}
    for cut in r['cortes']:
        tag=cut['fecha']+'_'+cut['hora'].replace(':','')
        e=pd.read_parquet(a.privado/(tag+'_evaluacion.parquet'))
        old=pd.read_parquet(a.ventana/(tag+'_evaluacion.parquet'));ids.update(e.id_contrato)
        assert e[old.columns].equals(old)
        assert (~e.holdout).equals(e.entrenamiento)
        assert e.groupby(['vencimiento','strike']).holdout.nunique().max()==1
        p=json.loads((a.privado/(tag+'_modelos.json')).read_text(encoding='utf-8'))
        original=json.loads((a.ventana/(tag+'_modelos.json')).read_text(encoding='utf-8'))
        assert p['modelos_origen']==original['modelos']
        base={z['T']:z for z in original['modelos'][0]['rebanadas']}
        for j,fixed in enumerate(p['modelos_fijos']):
            width=fixed['ancho']
            for z in fixed['rebanadas']:
                assert z=={key:base[z['T']][key] for key in ('T','F','D')};anchors+=1
            for name,model,col in [('fijo',fixed,'fijo_'+str(width)),('reestimado',p['modelos_origen'][j],'precio_'+str(width))]:
                assert np.all(np.diff(model['parametros']['thetas'])>=0)
                assert 0<model['parametros']['gamma']<=.5
                assert model['parametros']['eta']*(1+abs(model['parametros']['rho']))<=2+1e-10
                zs={z['T']:z for z in model['rebanadas']}
                for t,z in zs.items():
                    g=e[np.isclose(e.dias,t*365,rtol=0,atol=1e-10)]
                    pp=price(model['parametros'],t,z['F'],z['D'],g)
                    err=max(err,float(abs(pp-g[col]).max()));nprices+=len(g)
                for region in ('centro','alas_3_6','alas_6_10','conjunto'):
                    mask=e.anillo.eq(region) if region!='conjunto' else pd.Series(True,index=e.index)
                    h=e[e.holdout & mask];inside=int(((h[col]>=h.bid)&(h[col]<=h.ask)).sum())
                    v=next(v for v in cut['variantes'] if v['ancho']==width and v['forward']==name)
                    assert v['holdout'][region]['filas']==len(h) and v['holdout'][region]['dentro']==inside
                    key=(width,name,region);agg=aggregate.setdefault(key,[0,0]);agg[0]+=len(h);agg[1]+=inside
                    for group,partition in [('training',e.entrenamiento),('holdout',e.holdout)]:
                        q=e[partition & mask];counts=dict(pares=0,incompatibles=0,minimo_incompatibles_F_libre=0)
                        for t,z in zs.items():
                            gg=q[np.isclose(q.dias,t*365,rtol=0,atol=1e-10)]
                            d,f=parity(gg,z['D'],z['F'],col);forced+=f
                            for k in counts:counts[k]+=d[k]
                        pub=next(d for d in cut['paridad'] if (d['ancho'],d['forward'],d['grupo'],d['region'])==(width,name,group,region))
                        assert all(pub[k]==counts[k] for k in counts)
                        keyp=(width,name,group,region);aggp=agparity.setdefault(keyp,dict(pares=0,incompatibles=0,minimo_incompatibles_F_libre=0))
                        for k in counts:aggp[k]+=counts[k]
    for v in r['total']:
        for region,m in v['holdout'].items():assert aggregate[(v['ancho'],v['forward'],region)]==[m['filas'],m['dentro']]
    for p in r['paridad']:
        d=agparity[(p['ancho'],p['forward'],p['grupo'],p['region'])];assert all(p[k]==d[k] for k in d)
    assert err<1e-8
    assert not any(i in (folder/'resumen.json').read_text(encoding='utf-8') for i in ids)
    out=dict(precios_reproducidos=nprices,max_error_precio=err,anclas_congeladas_verificadas=anchors,
        origen_y_split_intactos=True,paridad_y_minimo_F_libre_reproducidos=True,
        comprobaciones_pares_incompatibles_con_precio_fuera=forced,
        nota_conteo='Los pares se revisan repetidamente entre ventanas, anclas y regiones; no son observaciones independientes',
        huellas_correctas=True,resumen_sha256=sha(folder/'resumen.json'),
        fuentes_sha256_lf={f.name:hashlib.sha256(f.read_text(encoding='utf-8').encode()).hexdigest()
            for f in (Path(__file__),Path(__file__).with_name('graficas.py'))})
    (folder/'verificacion.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(json.dumps(out,indent=2))


if __name__=='__main__':main()
