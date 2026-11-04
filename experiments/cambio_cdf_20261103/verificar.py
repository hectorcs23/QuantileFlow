"""Verificación independiente con precios y masas guardadas; no llama al optimizador."""
import argparse,collections,hashlib,json,tomllib
from pathlib import Path
import numpy as np
import pandas as pd
FOLDER=Path(__file__).resolve().parent
ROOT=FOLDER.parents[1]
OLD=ROOT/'experiments/ruido_concentrado_20261022/resultados'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lf(p):return hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()


def main():
    if not __debug__:raise RuntimeError('Ejecutar sin -O')
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('conocidas','segunda','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();origins={'conocidas':a.conocidas,'nuevas':a.segunda};out=FOLDER/'resultados'
    s=read(out/'resumen.json');rs=read(out/'por_vencimiento.json');old=read(OLD/'resumen.json')
    proto=tomllib.loads((FOLDER/'protocolo.toml').read_text(encoding='utf-8'));tol=proto['tolerancia']
    assert proto==s['protocolo'] and sha(OLD/'verificacion.json')==s['fuente_verificada_sha256']
    for n,h in s['codigo_sha256_lf'].items():assert lf(FOLDER/n)==h,n
    for co,origin in origins.items():
        for n,h in old['origenes'][co]['privados_sha256'].items():assert sha(origin/n)==h,n
    repair={(r['fecha'],r['hora'],r['vencimiento']):r for r in read(OLD/'reparaciones.json')}
    prev={(r['fecha'],r['vencimiento'],r['caso']):r for r in read(OLD/'por_rebanada.json') if r['hora']=='09:45'}
    cases={'principal':'l1_margen_0.1','referencias':'referencias','estricto':'l1_margen_0.05','uniforme':'uniforme'}
    pub={(r['fecha'],r['vencimiento']):r for r in rs};seen=set();miss=[]
    assert len(pub)==len(rs)
    mx=dict(masa=0.,negatividad=0.,F_D=0.,cap_spreads=0.,media_spreads=0.,objetivo=0.,mezcla_cero=0.)
    nm=nj=mixes=0
    assert set(s['testigos_privados_sha256'])=={d+'_testigos.json' for d in proto['fechas']}
    for filename,h in s['testigos_privados_sha256'].items():
        path=a.privado/filename;assert sha(path)==h,filename
        day=filename[:10];co,={r['cohorte'] for r in repair.values() if r['fecha']==day}
        sets=[{v for d,h,v in repair if d==day and h==hr} for hr in proto['horas']]
        miss.extend((day,v,proto['horas'][int(v in sets[0])]) for v in sorted(sets[0]^sets[1]))
        expect={(day,v) for v in sets[0]&sets[1]}
        evid=read(path)
        assert {(row['fecha'],row['vencimiento']) for row in evid}==expect
        snaps=[];anchors=[]
        for hr in proto['horas']:
            tag=day+'_'+hr.replace(':','');origin=origins[co]
            snaps.append(pd.read_parquet(origin/(tag+'_evaluacion.parquet')))
            anchors.append(read(origin/(tag+'_modelos.json'))['modelos_fijos'][0]['rebanadas'])
        for row in evid:
            v=row['vencimiento'];r=pub[day,v];assert (day,v) not in seen;seen.add((day,v))
            assert r['cohorte']==co;ev=row['medidas'];pair=[]
            for hr,df,zs in zip(proto['horas'],snaps,anchors):
                g=df[df.entrenamiento & (df.k.abs()<=.1) & (df.vencimiento.astype(str)==v)]
                rr=repair[day,hr,v]; assert len(g)==rr['filas'] and not g.holdout.any() and g.dias.nunique()==1
                z,=[z for z in zs if abs(z['T']*365-g.dias.iloc[0])<1e-10]
                pair.append((g,rr,z))
            assert abs(pair[0][2]['T']-pair[1][2]['T']-15/(365*1440))<1e-11
            F0=pair[0][2]['F'];K=np.array(proto['ratios'])*F0
            for case,oldcase in cases.items():
                allw=[];feas=[]
                for j,(m,(g,rr,z)) in enumerate(zip(ev[case],pair,strict=True)):
                    F,D=z['F'],z['D'];x=np.array(m['x']);points=K/F;epsilon=proto['epsilon']*F0/F
                    assert m['F']==F and m['D']==D and x[0]==0 and x[-1]==2. and np.all(np.diff(x)>0)
                    assert np.allclose(m['puntos'],points,atol=1e-14,rtol=0) and abs(m['epsilon']-epsilon)<1e-14
                    strikes=g.strike.to_numpy();bid=g.bid.to_numpy();ask=g.ask.to_numpy()
                    A=np.maximum(0.,np.where(g.tipo.to_numpy()[:,None]=='C',F*x-strikes[:,None],strikes[:,None]-F*x))*D
                    cap=rr['cap'];budget=None if case=='uniforme' else rr['media_min']+(.05 if case=='estricto' else .1)
                    fb=(.9975,1.0025) if case=='referencias' else (1.,1.)
                    db=(np.exp(-.01*z['T']),np.exp(.01*z['T'])) if case=='referencias' else (1.,1.)
                    def feasible(p,d,x=x,A=A,bid=bid,ask=ask,cap=cap,budget=budget,fb=fb,db=db):
                        assert np.isfinite(p).all() and np.isfinite(d) and d>0
                        mx['masa']=max(mx['masa'],abs(sum(p)-1))
                        mx['negatividad']=max(mx['negatividad'],-min(p))
                        mx['F_D']=max(mx['F_D'],fb[0]-p@x,p@x-fb[1],db[0]-d,d-db[1])
                        price=d*(A@p)
                        e=np.maximum.reduce([bid-price,price-ask,np.zeros_like(bid)])/(ask-bid)
                        mx['cap_spreads']=max(mx['cap_spreads'],max(e)-cap)
                        if budget is not None:mx['media_spreads']=max(mx['media_spreads'],sum(e)/len(e)-budget)
                    feas.append(feasible);by={}
                    for w in m['testigos']:
                        nm+=1;p=np.asarray(w['p']);d=w['d'];feasible(p,d)
                        k=w['umbral'];side=w['lado'];ii,=np.flatnonzero(points==k)
                        is_discrete='discreta' in w['tipo']
                        actual=float(sum(p[x<=k]))
                        if is_discrete: value=actual
                        else:
                            start=k-epsilon if side=='inferior' else k
                            end=k if side=='inferior' else k+epsilon
                            ramp=np.where(x<=start,1.,np.where(x>=end,0.,(end-x)/epsilon))
                            value=float(p@ramp)
                            assert value<=actual+tol if side=='inferior' else value>=actual-tol
                        mx['objetivo']=max(mx['objetivo'],abs(value-w['valor']))
                        pos={(False,'inferior'):0,(True,'inferior'):1,(True,'superior'):2,(False,'superior'):3}[is_discrete,side]
                        assert abs(r['casos'][case][ii][('temprana','tardia')[j]][pos]-value)<tol
                        assert (ii,pos) not in by;by[ii,pos]=(value,p,d)
                    assert len(by)==4*len(points);allw.append(by)
                for i,cell in enumerate(r['casos'][case]):
                    assert cell['ratio']==proto['ratios'][i]
                    assert cell['apoyo_ambos']==all(g.strike.min()<=K[i]<=g.strike.max() for g,_,_ in pair)
                    p0=prev[day,v,oldcase]['cdf'][i]
                    assert np.allclose(cell['temprana'],[p0[k] for k in ('inferior','alcanzable_inferior','alcanzable_superior','superior')],rtol=0,atol=tol)
                    left,right=allw
                    dif=[right[i,j][0]-left[i,3-j][0] for j in range(4)]
                    assert np.allclose(dif,[cell[k] for k in ('inferior','interior_inferior','interior_superior','superior')],rtol=0,atol=tol)
                    if cell['estado']=='aumento':assert dif[0]>tol
                    elif cell['estado']=='descenso':assert dif[3]<-tol
                    elif cell['estado']=='cero_alcanzable':
                        l=max(w[i,1][0] for w in allw);u=min(w[i,2][0] for w in allw);assert l<=u+1e-12
                        target=(l+u)/2;achieved=[]
                        for j,w in enumerate(allw):
                            low,p0,d0=w[i,1];high,p1,d1=w[i,2]
                            frac=np.clip((target-low)/(high-low),0,1) if high>low else 0.
                            p=(1-frac)*p0+frac*p1;d=1/((1-frac)/d0+frac/d1)
                            feas[j](p,d);m=ev[case][j]
                            achieved.append(sum(p[np.asarray(m['x'])<=m['puntos'][i]]))
                        mx['mezcla_cero']=max(mx['mezcla_cero'],abs(achieved[1]-achieved[0]));mixes+=1
                    else:assert cell['estado']=='indeterminado' and dif[0]<=tol and dif[3]>=-tol and (dif[1]>-tol or dif[2]<tol)
                if case=='principal':
                    nj+=1;joint=ev['conjunto'];cdfs=[]
                    for j,m in enumerate(ev[case]):
                        p=np.asarray(joint['masas'][j]);feas[j](p,1.)
                        vals=np.array([sum(p[np.asarray(m['x'])<=k]) for k in m['puntos']])
                        assert np.max(abs(vals-joint['cdf'][j]))<tol;cdfs.append(vals)
                    gap=float(np.max(abs(cdfs[1]-cdfs[0])))
                    assert abs(gap-r['conjunto']['diferencia_max'])<tol and abs(gap-joint['gamma'])<tol
                    assert r['conjunto']['igualdad_testificada']==(gap<=tol)
        print(day,'reconstruido',flush=True)
    assert set(pub)==seen and sorted(miss)==sorted((r['fecha'],r['vencimiento'],r['hora_faltante']) for r in s['sin_pareja'])
    assert nm+nj==s['total_lp'] and max(mx.values())<1e-6,mx
    for group in s['estadisticas']:
        rr=[r for r in rs if group['cohorte'] in ('total',r['cohorte'])]
        assert group['pares']==len(rr) and group['iguales_conjuntos']==sum(r['conjunto']['igualdad_testificada'] for r in rr)
        for case,stats in group['casos'].items():
            vs=[v for r in rr for v in r['casos'][case]]
            assert stats['estados']==dict(collections.Counter(v['estado'] for v in vs)) and stats['puntos']==len(vs)
            assert abs(stats['ancho_mediano_en_F_pp']-100*np.median([v['superior']-v['inferior'] for v in vs if v['ratio']==1.]))<1e-7
    report=dict(lp_marginales=nm,lp_conjuntos=nj,mezclas_puntuales_de_cambio_cero=mixes,pares=len(seen),
        errores_max=mx,fuentes_publicas={n:sha(out/n) for n in ('resumen.json','por_vencimiento.json')},verificador_sha256_lf=lf(Path(__file__)))
    (out/'verificacion.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
