"""Control exploratorio posterior: solo pares sin testigo conjunto en el protocolo."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.linalg import block_diag
from experiments.cambio_cdf_20261103.evaluar import FOLDER,OLD,CASES,HOURS,snapshot,read,sha,dump,lf
from experiments.cambio_cdf_20261103.metodo import coordenadas
from experiments.distribuciones_ruido_20261022.metodo import resolver
from experiments.ruido_concentrado_20261022.metodo import MercadoL1


def resolver_conjunto(ms,caps,budgets,refs,rampas):
    # p, z=e/d y t=1/d por marginal, a partir del mismo conjunto L1 verificado.
    parts=[m._sistema(cap,b,fb,db,cdf=True) for m,cap,b,(fb,db) in zip(ms,caps,budgets,refs,strict=True)]
    G=block_diag(*[s[0] for s in parts]); E=block_diag(*[s[2] for s in parts])
    fs=[]
    for m in ms:
        k=m.puntos[:,None];x=m.x[None,:]
        if rampas:
            lo=np.clip((k-x)/m.eps,0,1);hi=np.clip((k+m.eps-x)/m.eps,0,1)
        else:lo=hi=(x<=k).astype(float)
        tail=np.zeros((len(k),len(m.lo)+1));fs.append((np.c_[lo,tail],np.c_[hi,tail]))
    # Para toda CDF real valen L1-U0 <= Q1-Q0 y L0-U1 <= Q0-Q1.
    A=np.vstack([np.c_[-fs[0][1],fs[1][0]],np.c_[fs[0][0],-fs[1][1]]])
    M=np.vstack([np.c_[G,np.zeros(len(G))],np.c_[A,-np.ones(len(A))]])
    bounds=parts[0][4]+parts[1][4]+[(0,1)]
    v,cert=resolver(np.r_[np.zeros(G.shape[1]),1.],M,np.r_[parts[0][1],parts[1][1],np.zeros(len(A))],
        np.c_[E,np.zeros(len(E))],np.r_[parts[0][3],parts[1][3]],bounds)
    n=parts[0][0].shape[1];w=[v[:n],v[n:-1]]
    return dict(gamma=float(v[-1]),certificado=cert,masas=[a[:len(m.x)].tolist() for a,m in zip(w,ms)],
                descuentos=[float(1/a[-1]) for a in w])


def main():
    if not __debug__:raise RuntimeError('Ejecutar sin -O')
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('conocidas','segunda','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();out=FOLDER/'resultados';summary=read(out/'resumen.json');prior=read(OLD/'resumen.json')
    checks=read(out/'verificacion.json');proto=summary['protocolo'];private=a.privado.resolve()
    origins={'conocidas':a.conocidas.resolve(),'nuevas':a.segunda.resolve()}
    if private.is_relative_to(ROOT) or ROOT.is_relative_to(private) or any(private.is_relative_to(p) or p.is_relative_to(private) for p in origins.values()):
        raise ValueError('Carpeta privada fuera de Git y de las entradas')
    for name,h in checks['fuentes_publicas'].items():assert sha(out/name)==h
    for co,p in origins.items():
        for name,h in prior['origenes'][co]['privados_sha256'].items():assert sha(p/name)==h
    rep={(s['fecha'],s['hora'],s['vencimiento']):s for s in read(OLD/'reparaciones.json')}
    target=[r for r in read(out/'por_vencimiento.json') if not r['conjunto']['igualdad_testificada']]
    rows=[];private_rows=[];tol=proto['tolerancia']
    for r in target:
        co,day,v=r['cohorte'],r['fecha'],r['vencimiento'];pair=[snapshot(origins[co],day,hr,rep)[v] for hr in HOURS]
        F0=pair[0][1]['F'];ms=[];caps=[];bases=[]
        for g,z,rr,extras in pair:
            k,eps=coordenadas(proto['ratios'],F0,z['F'],proto['epsilon'])
            original=MercadoL1(g,z['F'],z['D'],puntos=k,epsilon=eps,extras=extras)
            # Conservar cada nodo anterior y añadir quiebres a ±0.001% de F_0945.
            m=MercadoL1(g,z['F'],z['D'],puntos=k,epsilon=1e-5*F0/z['F'],extras=original.x[1:-1])
            ms.append(m);caps.append(rr['cap']);bases.append(rr['media_min'])
        for case in CASES:
            bs=[c if case=='uniforme' else b+(.05 if case=='estricto' else .1) for c,b in zip(caps,bases)]
            refs=[((.9975,1.0025),(np.exp(-.01*z['T']),np.exp(.01*z['T']))) if case=='referencias'
                  else ((1.,1.),(1.,1.)) for _,z,_,_ in pair]
            runs=[resolver_conjunto(ms,caps,bs,refs,rampas) for rampas in (True,False)]
            observed=[]
            for index,sol in enumerate(runs):
                low=[];high=[];actual=[]
                for j,(m,(g,z,_,_)) in enumerate(zip(ms,pair)):
                    p=np.array(sol['masas'][j]);d=sol['descuentos'][j];xx=m.x;kk=m.puntos
                    bid=g.bid.to_numpy();ask=g.ask.to_numpy();K=g.strike.to_numpy()
                    pay=np.maximum(0.,np.where(g.tipo.to_numpy()[:,None]=='C',xx*m.F-K[:,None],K[:,None]-xx*m.F))
                    price=m.D*d*(pay@p);e=np.maximum.reduce([bid-price,price-ask,np.zeros_like(bid)])/(ask-bid)
                    fb,db=refs[j]
                    assert abs(sum(p)-1)<tol and min(p)>=-tol and max(e)<=caps[j]+tol and np.mean(e)<=bs[j]+tol
                    assert fb[0]-tol<=p@xx<=fb[1]+tol and db[0]-tol<=d<=db[1]+tol
                    kk=kk[:,None];actual.append((xx<=kk)@p)
                    low.append(np.where(xx<=kk-m.eps,1.,np.where(xx>=kk,0.,(kk-xx)/m.eps))@p)
                    high.append(np.where(xx<=kk,1.,np.where(xx>=kk+m.eps,0.,(kk+m.eps-xx)/m.eps))@p)
                witness=float(max(abs(actual[1]-actual[0])))
                value=(max(0.,max(low[1]-high[0]),max(low[0]-high[1])) if index==0 else witness)
                assert abs(sol['gamma']-value)<tol
                observed.append(witness)
            assert runs[0]['gamma']<=observed[1]+tol
            meta=dict(cohorte=co,fecha=day,vencimiento=v,caso=case)
            rows.append(dict(**meta,inferior_relajacion=runs[0]['gamma'],superior_testigo=observed[1],
                             igualdad_testificada=bool(observed[1]<=tol)))
            private_rows.append(dict(**meta,estados=[m.x.tolist() for m in ms],puntos=[m.puntos.tolist() for m in ms],
                soluciones=runs))
    ev=private/'control_malla.json';dump(ev,private_rows)
    dump(out/'control_malla.json',dict(alcance='Exploratorio solo para los pares sin testigo conjunto inicial. Misma tolerancia, precios y presupuestos.',
        epsilon_relativo_al_F0945=1e-5,pares=len(target),lp=2*len(rows),resultados=rows,
        codigo_sha256_lf=lf(Path(__file__)),testigos_privados_sha256=sha(ev),verificacion_base_sha256=sha(out/'verificacion.json')))
    print(rows,flush=True)


if __name__=='__main__':main()
