"""Verificador independiente: reconstruye precios y presupuestos sin llamar al solver."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
import pandas as pd
RAIZ=Path(__file__).resolve().parents[2]


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def leer(p): return json.loads(p.read_text(encoding='utf-8'))
def key(m): return (m['cohorte'],m['fecha'],m['hora'],m['dias'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('origen','nuevos','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();folder=Path(__file__).parent;out=folder/'resultados'
    summary=leer(out/'resumen.json');new=leer(out/'entradas_nuevas.json')
    for name,h in (summary['codigo_sha256_lf']|new['codigo_sha256_lf']).items():
        assert hashlib.sha256((RAIZ/name).read_text(encoding='utf-8').encode()).hexdigest()==h,name
    for co,origin,src in [('conocidas',a.origen,RAIZ/'experiments/forward_fijo_20261014/resultados/resumen.json'),
                          ('nuevas',a.nuevos,out/'entradas_nuevas.json')]:
        assert hashlib.sha256(src.read_text(encoding='utf-8').encode()).hexdigest()==summary['origenes'][co]['resumen_sha256_lf']
        for name,h in summary['origenes'][co]['privados_sha256'].items(): assert sha(origin/name)==h,name
    rows={(*key(r),r['caso']):r for r in leer(out/'por_rebanada.json')}
    reps={key(r):r for r in leer(out/'reparaciones.json')}
    mx=dict(masa=0.,negatividad=0.,referencia=0.,cap_spreads=0.,media_spreads=0.,objetivo=0.)
    total=0;checked=set()
    for name,h in summary['privados_sha256'].items():
        assert sha(a.privado/name)==h,name
        co,tag=name.split('_',1);tag=tag.replace('_medidas.json','')
        origin=a.origen if co=='conocidas' else a.nuevos
        df=pd.read_parquet(origin/(tag+'_evaluacion.parquet'))
        anchors=leer(origin/(tag+'_modelos.json'))['modelos_fijos'][0]['rebanadas']
        for model in leer(a.privado/name):
            F,D=model['F'],model['D']; x=np.asarray(model['x']);eps=model['epsilon']
            assert np.isfinite(x).all() and x[0]==0 and x[-1]==model['soporte'] and np.all(np.diff(x)>0)
            z=next(z for z in anchors if abs(z['T']*365-model['dias'])<1e-10)
            assert F==z['F'] and D==z['D']
            mask=np.isclose(df.dias,model['dias'],rtol=0,atol=1e-10)&(df.k.abs()<=.1)
            train=df[mask&df.entrenamiento];reserved=df[mask&df.holdout&df.tipo.eq('C')]
            held=pd.concat([reserved.iloc[[np.argmin(abs(reserved.strike/F-r))]] for r in (.97,1.,1.03)]).drop_duplicates('id_contrato')
            assert train.id_contrato.tolist()==model['ids'] and held.id_contrato.tolist()==model['holdout_ids']
            assert not set(train.id_contrato)&set(held.id_contrato)
            K=train.strike.to_numpy();bid=train.bid.to_numpy();ask=train.ask.to_numpy();s=ask-bid
            pay=np.maximum(np.where(train.tipo.to_numpy()[:,None]=='C',F*x-K[:,None],K[:,None]-F*x),0)
            calls={}; public=rows.get((*key(model),model['caso']))
            for t in model['testigos']:
                total+=1;p=np.asarray(t['p']);d=t['d'];cap=t.get('cap',t.get('rho'))
                assert np.isfinite(p).all() and len(p)==len(x) and d>0 and cap>=0
                mx['masa']=max(mx['masa'],abs(sum(p)-1));mx['negatividad']=max(mx['negatividad'],-float(min(p)))
                mx['referencia']=max(mx['referencia'],t['fb'][0]-x@p,x@p-t['fb'][1],t['db'][0]-d,d-t['db'][1])
                price=D*d*(pay@p)
                e=np.maximum.reduce([bid-price,price-ask,np.zeros(len(train))])/s
                mx['cap_spreads']=max(mx['cap_spreads'],max(e)-cap)
                if t.get('presupuesto') is not None:
                    mx['media_spreads']=max(mx['media_spreads'],float(np.mean(e))-t['presupuesto'])
                    assert abs(t['presupuesto']-public['presupuesto'])<1e-9
                typ=t['tipo']
                if typ=='reparacion':
                    value=max(e);assert abs(reps[key(model)]['rho']-t['rho'])<1e-8
                elif typ=='reparacion_l1':
                    value=float(np.mean(e));r=reps[key(model)]
                    assert abs(r['media_min']-value)<1e-7
                    assert abs(r['fraccion_modificada']-np.mean(e>1e-6))<1e-8
                    top=max(1,math.ceil(.1*len(e)))
                    share=float(np.sort(e)[-top:].sum()/sum(e)) if sum(e)>1e-8 else 0.
                    assert abs(r['participacion_top10']-share)<1e-7
                    # Paridad: cota inferior por pares disjuntos, reconstruida por separado.
                    pairs=train.pivot(index='strike',columns='tipo',values=['bid','ask']).dropna()
                    gap=np.maximum.reduce([(D*(F-pairs.index)-(pairs['ask']['C']-pairs['bid']['P'])).to_numpy(),
                         ((pairs['bid']['C']-pairs['ask']['P'])-D*(F-pairs.index)).to_numpy(),np.zeros(len(pairs))])
                    spreads=np.stack([(pairs['ask'][v]-pairs['bid'][v]).to_numpy() for v in ('C','P')])
                    high=np.max(spreads,axis=0);low=np.min(spreads,axis=0)
                    first=np.minimum(cap,gap/high);rem=np.maximum(gap-first*high,0)
                    lower=dict(pares=len(pairs),incompatibles=int(sum(gap>1e-7)),
                        filas_modificadas_min=int(sum(gap>1e-7)+sum((gap>1e-7)&(rem>1e-7))),
                        media_error_min=float(np.sum(np.where(gap>1e-7,first+rem/low,0)))/len(train))
                    for k,v in lower.items():assert abs(r['paridad'][k]-v)<1e-7
                    checked.add(key(model))
                elif typ.startswith('cdf'):
                    k=t['umbral']
                    if 'discreta' in typ: f=(x<=k).astype(float)
                    elif t['lado']=='inferior': f=np.where(x<=k-eps,1.,np.where(x>=k,0.,(k-x)/eps))
                    else:f=np.where(x<=k,1.,np.where(x>=k+eps,0.,(k+eps-x)/eps))
                    value=float(p@f);true=float(sum(p[x<=k]))
                    assert value<=true+1e-7 if t['lado']=='inferior' else value>=true-1e-7
                    c=next(c for c in public['cdf'] if c['ratio']==k)
                    field=('alcanzable_' if 'discreta' in typ else '')+t['lado']
                    assert abs(c[field]-value)<1e-7
                elif typ.startswith('call'):
                    value=float(d*(p@np.maximum(x-t['strike_ratio'],0)))
                    calls.setdefault(t['strike_ratio'],{})[t['lado']]=value*F*D
                else: raise ValueError('Testigo desconocido')
                mx['objetivo']=max(mx['objetivo'],abs(value-t['valor']))
            if public:
                hits=0;widths=[]
                for q in held.itertuples():
                    v=calls[q.strike/F];lo,hi=v['inferior'],v['superior']
                    hits+=int(lo<=q.ask+1e-7 and hi>=q.bid-1e-7);widths.append((hi-lo)/(q.ask-q.bid))
                assert hits==public['holdout_solapan'] and len(held)==public['holdout_n']
                assert abs(float(np.mean(widths))-public['holdout_ancho_spreads_medio'])<1e-7
        print(name,'verificados',total,flush=True)
    assert total==summary['total_lp'] and len(checked)==len(reps)
    assert max(mx.values())<1e-6,mx
    comparisons=0;controls={co:{} for co in ('conocidas','nuevas')}
    def contains(outer,inner):
        for a,b in zip(outer['cdf'],inner['cdf']):
            assert a['inferior']<=b['inferior']+1e-7 and a['superior']>=b['superior']-1e-7
    previous=leer(RAIZ/'experiments/distribuciones_ruido_20261022/resultados/por_rebanada.json')
    previous={(r['fecha'],r['hora'],r['dias']):r for r in previous if r['caso']=='todos_margen_0.5'}
    for k in reps:
        group={case:rows[(*k,case)] for case in ('uniforme','l1_margen_0.05','l1_margen_0.1','l1_margen_0.5','referencias','soporte_4F','rampa_mitad')}
        base=group['l1_margen_0.1']
        contains(group['uniforme'],group['l1_margen_0.5']);contains(group['l1_margen_0.5'],base)
        contains(base,group['l1_margen_0.05']);contains(group['referencias'],base)
        contains(group['soporte_4F'],base);contains(base,group['rampa_mitad']);comparisons+=6
        for case in ('referencias','soporte_4F','rampa_mitad'):
            delta=max(abs(a[field]-b[field]) for a,b in zip(group[case]['cdf'],base['cdf']) for field in ('inferior','superior'))
            controls[k[0]][case]=max(controls[k[0]].get(case,0),delta)
        if k[0]=='conocidas':
            old=previous[k[1:]];now=group['uniforme']
            for a,b in zip(old['cdf'],now['cdf']):
                for field in ('inferior','superior','alcanzable_inferior','alcanzable_superior'):
                    assert abs(a[field]-b[field])<1e-7
            assert old['holdout_solapan']==now['holdout_solapan']
    report=dict(testigos=total,errores_maximos=mx,reparaciones_reconstruidas=len(checked),
        comparaciones_anidadas=comparisons,controles_max_cambio_extremo=controls,
        historial_reproduce_B=True,verificador_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        entradas_publicas_sha256={p.name:sha(p) for p in [out/'resumen.json',out/'reparaciones.json',out/'por_rebanada.json',out/'entradas_nuevas.json']})
    (out/'verificacion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
