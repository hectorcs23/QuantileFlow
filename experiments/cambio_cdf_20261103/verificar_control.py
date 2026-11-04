"""Releer los testigos del control exploratorio y repriciarlos sin ejecutar un LP."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
F=Path(__file__).resolve().parent;OLD=F.parent/'ruido_concentrado_20261022/resultados'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if not __debug__:raise RuntimeError('Ejecutar sin -O')
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('conocidas','segunda','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();out=F/'resultados';ctrl=read(out/'control_malla.json')
    assert sha(out/'verificacion.json')==ctrl['verificacion_base_sha256']
    assert sha(a.privado/'control_malla.json')==ctrl['testigos_privados_sha256']
    assert hashlib.sha256((F/'control_malla.py').read_text('utf-8').encode()).hexdigest()==ctrl['codigo_sha256_lf']
    old=read(OLD/'resumen.json');sources={'conocidas':a.conocidas,'nuevas':a.segunda}
    pri=read(a.privado/'control_malla.json');base=read(out/'resumen.json');tol=base['protocolo']['tolerancia']
    reps={(r['fecha'],r['hora'],r['vencimiento']):r for r in read(OLD/'reparaciones.json')}
    key=lambda r:(r['fecha'],r['vencimiento'],r['caso'])
    published={key(r):r for r in ctrl['resultados']};assert len(pri)==len(published)==len(ctrl['resultados'])
    expected={(r['fecha'],r['vencimiento'],case) for r in read(out/'por_vencimiento.json') if not r['conjunto']['igualdad_testificada'] for case in r['casos']}
    assert set(published)=={key(r) for r in pri}==expected
    worst=0.;count=0
    for r in pri:
        day,v,case=key(r);co=r['cohorte'];root=sources[co];phys=None
        sol=r['soluciones'][1];values=[]
        for j,hour in enumerate(base['protocolo']['horas']):
            tag=day+'_'+hour.replace(':','');ep=root/(tag+'_evaluacion.parquet');mp=root/(tag+'_modelos.json')
            for path in (ep,mp):assert sha(path)==old['origenes'][co]['privados_sha256'][path.name]
            df=pd.read_parquet(ep);g=df[df.entrenamiento & (df.k.abs()<=.1) & (df.vencimiento.astype(str)==v)]
            z,=[z for z in read(mp)['modelos_fijos'][0]['rebanadas'] if abs(z['T']*365-g.dias.iloc[0])<1e-10]
            if j==0:phys=np.array(base['protocolo']['ratios'])*z['F']
            x=np.array(r['estados'][j]);p=np.array(sol['masas'][j]);d=sol['descuentos'][j]
            assert x[0]==0 and x[-1]==2 and np.all(np.diff(x)>0) and len(x)==len(p) and np.isfinite(p).all()
            assert abs(p.sum()-1)<tol and p.min()>=-tol and np.allclose(phys/z['F'],r['puntos'][j],atol=1e-14,rtol=0)
            fx=.0025 if case=='referencias' else 0.;rate=.01 if case=='referencias' else 0.
            assert abs(p@x-1)<=fx+tol and np.exp(-rate*z['T'])-tol<=d<=np.exp(rate*z['T'])+tol
            k=g.strike.to_numpy()[:,None];S=z['F']*x
            prices=z['D']*d*(np.maximum(np.where(g.tipo.to_numpy()[:,None]=='C',S-k,k-S),0)@p)
            errs=np.maximum(0,np.maximum((g.bid-prices).to_numpy(),(prices-g.ask).to_numpy()))/(g.ask-g.bid).to_numpy()
            rep=reps[day,hour,v];assert np.max(errs)<=rep['cap']+tol
            if case!='uniforme':assert np.mean(errs)<=rep['media_min']+(.05 if case=='estricto' else .1)+tol
            values.append(np.array([np.sum(p[x<=k]) for k in phys/z['F']]))
        gap=float(max(abs(values[1]-values[0])));assert abs(gap-published[key(r)]['superior_testigo'])<tol
        assert (gap<=tol)==published[key(r)]['igualdad_testificada']
        worst=max(worst,gap);count+=1
    cerrados={(k[0],k[1]) for k,row in published.items() if k[2]=='principal' and row['igualdad_testificada']}
    base_rows=read(out/'por_vencimiento.json')
    n_pares=sum(r['conjunto']['igualdad_testificada'] or (r['fecha'],r['vencimiento']) in cerrados for r in base_rows)
    n_puntos=sum(c['estado']=='cero_alcanzable' or (r['fecha'],r['vencimiento']) in cerrados for r in base_rows for c in r['casos']['principal'])
    report=dict(pares_principales_con_igualdad_simultanea_final=n_pares,puntos_principales_con_cero_final=n_puntos,
        pares_de_medidas_reconstruidos=count,max_diferencia_cdf=worst,control_sha256=sha(out/'control_malla.json'),
        codigo_sha256_lf=hashlib.sha256(Path(__file__).read_text('utf-8').encode()).hexdigest())
    (out/'verificacion_control.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(report)


if __name__=='__main__':main()
