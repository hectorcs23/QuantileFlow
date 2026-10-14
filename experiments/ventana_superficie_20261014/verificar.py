"""Reconstruye precios/CDF independientemente y comprueba las reservas históricas."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
from scipy.special import ndtr


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def formulas(p, t, k):
    th = np.interp(t, p['tiempos'], p['thetas'])
    rho = p['rho']; phi = p['eta']/(th**p['gamma']*(1+th)**(1-p['gamma']))
    root = np.sqrt((phi*k+rho)**2+1-rho*rho)
    w = th/2*(1+rho*phi*k+root)
    w1 = th/2*phi*(rho+(phi*k+rho)/root)
    dm = -k/np.sqrt(w)-np.sqrt(w)/2
    cdf = ndtr(-dm)+np.exp(-dm*dm/2)/np.sqrt(2*np.pi)*w1/(2*np.sqrt(w))
    return w,cdf


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for n in ('privado','forward'): ap.add_argument('--'+n,type=Path,required=True)
    a = ap.parse_args(); out = Path(__file__).parent/'resultados'
    summary = json.loads((out/'resumen.json').read_text(encoding='utf-8'))
    for name,h in summary['codigo_sha256_lf'].items():
        assert hashlib.sha256((RAIZ/name).read_text(encoding='utf-8').encode()).hexdigest()==h
    for name,h in summary['privados_sha256'].items(): assert sha(a.privado/name)==h
    prices=roots=0; err=0.; qe=0.; ids=set()
    totals=[dict(centro=[0,0],alas_3_6=[0,0],alas_6_10=[0,0],coverage=np.zeros(5,int)) for _ in range(3)]
    sensitivity=[dict(ancho=w,max_cdf_centro_pp=0.,max_mediana_bp=0.,max_forward_bp=0.)
                 for w in summary['protocolo']['anchos_log_moneyness']]
    for c in summary['cortes']:
        tag=c['fecha']+'_'+c['hora'].replace(':','')
        e=pd.read_parquet(a.privado/(tag+'_evaluacion.parquet'))
        old=pd.read_parquet(a.forward/(tag+'_evaluacion.parquet'))
        ids.update(e.id_contrato); assert (~e.holdout).equals(e.entrenamiento)
        check=e.set_index('id_contrato').loc[old.id_contrato]
        for field in ('bid','ask','strike','dias','entrenamiento','holdout'):
            assert np.array_equal(check[field],old[field])
        assert set(e[e.k.abs()<=.03].id_contrato)==set(old.id_contrato)
        assert e.groupby(['vencimiento','strike']).holdout.nunique().max()==1
        stored=json.loads((a.privado/(tag+'_modelos.json')).read_text(encoding='utf-8'))
        for j,(model,pub) in enumerate(zip(stored['modelos'],c['variantes'])):
            p=model['parametros']; width=model['ancho']; col='precio_'+str(width)
            assert pub['ancho']==width
            assert np.all(np.diff(p['thetas'])>=0) and 0<p['gamma']<=.5
            assert p['eta']*(1+abs(p['rho']))<=2+1e-10
            cover=np.zeros(5,int)
            for z in model['rebanadas']:
                t,F,D=z['T'],z['F'],z['D']; mask=np.isclose(e.dias,t*365,rtol=0,atol=1e-10)
                g=e[mask]; K=g.strike.to_numpy(); k=np.log(K/F)
                w,_=formulas(p,t,k); sq=np.sqrt(w); d1=(np.log(F/K)+w/2)/sq; d2=d1-sq
                price=np.where(g.tipo.eq('C'),D*(F*ndtr(d1)-K*ndtr(d2)),D*(K*ndtr(-d2)-F*ndtr(-d1)))
                err=max(err,float(abs(price-g[col]).max()));prices+=len(g)
                q=np.array(z['cuantiles_modelo']); _,cdf=formulas(p,t,np.log(q))
                qe=max(qe,float(abs(cdf-summary['protocolo']['cuantiles']).max()));roots+=len(q)
                tr=g[g.entrenamiento & (g.k.abs()<=width)]
                lo,hi=tr.strike.min()/F,tr.strike.max()/F
                assert np.allclose([lo,hi],z['rango_training'],rtol=0,atol=1e-12)
                cover+=(q>=lo)&(q<=hi)
                base=stored['modelos'][0]
                zb=next(v for v in base['rebanadas'] if v['T']==t)
                original_training=g[g.entrenamiento & g.historico]
                axis=np.linspace(original_training.strike.min()/zb['F'],original_training.strike.max()/zb['F'],401)
                _,cb=formulas(base['parametros'],t,np.log(axis))
                _,cw=formulas(p,t,np.log(axis*zb['F']/F))
                delta=100*float(abs(cb-cw).max())
                median=10000*abs(q[2]*F/zb['F']-zb['cuantiles_modelo'][2])
                sensitivity[j]['max_cdf_centro_pp']=max(sensitivity[j]['max_cdf_centro_pp'],delta)
                sensitivity[j]['max_mediana_bp']=max(sensitivity[j]['max_mediana_bp'],median)
                sensitivity[j]['max_forward_bp']=max(sensitivity[j]['max_forward_bp'],10000*abs(F/zb['F']-1))
            assert cover.tolist()==pub['cuantiles_dentro_training'];totals[j]['coverage']+=cover
            for ring in ('centro','alas_3_6','alas_6_10'):
                h=e[e.holdout & e.anillo.eq(ring)]
                count=int(((h[col]>=h.bid)&(h[col]<=h.ask)).sum())
                m=pub['holdout_por_anillo'][ring]
                assert (len(h),count)==(m['filas'],m['dentro'])
                totals[j][ring][0]+=len(h);totals[j][ring][1]+=count
    for t,pub in zip(totals,summary['total']):
        assert t['coverage'].tolist()==pub['cuantiles_dentro_training']
        for ring in ('centro','alas_3_6','alas_6_10'):
            m=pub['holdout_por_anillo'][ring];assert t[ring]==[m['filas'],m['dentro']]
    assert err<1e-8 and qe<1e-9
    assert not any(i in (out/'resumen.json').read_text(encoding='utf-8') for i in ids)
    result=dict(precios_reproducidos=prices,cuantiles_verificados=roots,max_error_precio=err,
        max_error_cdf_cuantil=qe,reservas_historicas_intactas=True,pares_sin_fuga=True,
        conteos_y_cobertura_reproducidos=True,huellas_correctas=True,resumen_sha256=sha(out/'resumen.json'),
        sensibilidad_vs_ventana_central=sensitivity,
        fuentes_verificacion_sha256_lf={f.name:hashlib.sha256(f.read_text(encoding='utf-8').encode()).hexdigest()
            for f in (Path(__file__),Path(__file__).with_name('graficas.py'))})
    (out/'verificacion.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
