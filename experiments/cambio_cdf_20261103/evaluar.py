"""Contraste temporal sin retocar los ajustes ni la partición del experimento anterior."""
import argparse, collections, hashlib, json, sys, tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import scipy
from experiments.distribuciones_ruido_20261022.evaluar import dump,sha
from experiments.ruido_concentrado_20261022.metodo import MercadoL1
from experiments.cambio_cdf_20261103.metodo import coordenadas,cambio,conjunto

FOLDER=Path(__file__).resolve().parent
OLD=ROOT/'experiments/ruido_concentrado_20261022/resultados'
CASES=('principal','referencias','estricto','uniforme')
HOURS=('09:45','10:00')
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def lf(p): return hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()


def snapshot(origin,day,hour,rep):
    tag=day+'_'+hour.replace(':','')
    df=pd.read_parquet(origin/(tag+'_evaluacion.parquet'))
    if (not df.raiz.eq('SPXW').all() or not df.subyacente.eq('SPX').all()
            or not df.ejercicio.eq('europeo').all() or not df.liquidacion.eq('PM').all()
            or not df.captura.eq(day+'T'+hour.replace(':','')).all()
            or not (df.entrenamiento==~df.holdout).all() or df.id_contrato.duplicated().any()):
        raise ValueError('Captura o universo incompatible: '+tag)
    zs=read(origin/(tag+'_modelos.json'))['modelos_fijos'][0]['rebanadas']
    result={}
    for z in zs:
        mask=np.isclose(df.dias,z['T']*365,rtol=0,atol=1e-10)&(df.k.abs()<=.1)
        g=df[mask&df.entrenamiento];h=df[mask&df.holdout&df.tipo.eq('C')]
        if g.empty or h.empty or g.vencimiento.nunique()!=1: raise ValueError('Vencimiento ambiguo')
        venc=str(g.vencimiento.iloc[0])
        if venc in result: raise ValueError('Vencimiento duplicado')
        r=rep[day,hour,venc];F=z['F']
        if len(g)!=r['filas'] or abs(z['T']*365-r['dias'])>1e-10: raise ValueError('Ajuste no corresponde')
        extras=[float(h.iloc[np.argmin(abs(h.strike/F-k))].strike/F) for k in (.97,1.,1.03)]
        result[venc]=(g,z,r,extras)
    return result


def evaluate(pair,ratios,eps,tol):
    F0=pair[0][1]['F'];Ks=ratios*F0
    caps=[side[2]['cap'] for side in pair]
    bases=[side[2]['media_min'] for side in pair]
    physical_support=[bool(all(s[0].strike.min()<=k<=s[0].strike.max() for s in pair)) for k in Ks]
    pub={}; evidence={}; certs=[]
    for case in CASES:
        ms=[]; bands=[]; models=[]
        for (g,z,r,extras),cap,base in zip(pair,caps,bases):
            points,epsilon=coordenadas(ratios,F0,z['F'],eps)
            m=MercadoL1(g,z['F'],z['D'],puntos=points,epsilon=epsilon,extras=extras)
            ms.append(m)
            kw=({'fb':(.9975,1.0025),'db':(np.exp(-.01*z['T']),np.exp(.01*z['T']))} if case=='referencias' else {})
            bs=[]
            for k in points:
                if case=='uniforme':
                    o=m.cdf(k,cap);i=m.cdf(k,cap,discreta=True)
                else:
                    budget=base+(.05 if case=='estricto' else .1)
                    o=m.cdf_l1(k,cap,budget,**kw);i=m.cdf_l1(k,cap,budget,**kw,discreta=True)
                bs.append([o['inferior'],i['inferior'],i['superior'],o['superior']])
            bands.append(bs);models.append(dict(puntos=points.tolist(),**m.evidencia()))
            certs.extend(w['certificado'] for w in m.testigos)
        pub[case]=[dict(ratio=float(r),apoyo_ambos=ok,temprana=a,tardia=b,**cambio(a,b,tol))
                   for r,ok,a,b in zip(ratios,physical_support,*bands,strict=True)]
        evidence[case]=models
        if case=='principal':
            j=conjunto(ms,caps,[b+.1 for b in bases]); certs.append(j['certificado'])
            evidence['conjunto']=j
            joint={k:j[k] for k in ('gamma','diferencia_max')}
            joint['igualdad_testificada']=bool(j['diferencia_max']<=tol)
    return pub,joint,evidence,certs


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('conocidas','segunda','privado'):ap.add_argument('--'+n,type=Path,required=True)
    args=ap.parse_args()
    origins={'conocidas':args.conocidas.resolve(),'nuevas':args.segunda.resolve()}
    private=args.privado.resolve()
    if (private.is_relative_to(ROOT) or ROOT.is_relative_to(private)
            or any(private.is_relative_to(x) or x.is_relative_to(private) for x in origins.values())):
        raise ValueError('Separar entradas, datos privados y repositorio')
    private.mkdir(parents=True,exist_ok=True)
    out=FOLDER/'resultados';out.mkdir(exist_ok=True)
    proto=tomllib.loads((FOLDER/'protocolo.toml').read_text('utf-8'))
    assert tuple(proto['horas'])==HOURS
    old=read(OLD/'resumen.json');check=read(OLD/'verificacion.json')
    for name,h in check['entradas_publicas_sha256'].items():
        if sha(OLD/name)!=h: raise ValueError('Fuente pública alterada: '+name)
    for co,orig in origins.items():
        for n,h in old['origenes'][co]['privados_sha256'].items():
            if sha(orig/n)!=h:raise ValueError('Snapshot privado alterado: '+n)
    for name,h in old['codigo_sha256_lf'].items():
        if lf(ROOT/name)!=h:raise ValueError('Método previo modificado: '+name)
    repairs=read(OLD/'reparaciones.json')
    rep={(r['fecha'],r['hora'],r['vencimiento']):r for r in repairs}
    if len(rep)!=len(repairs):raise ValueError('Claves de origen duplicadas')
    rows=[];missing=[];files=[];certs=[]
    for day in proto['fechas']:
        cs={r['cohorte'] for r in repairs if r['fecha']==day}
        if len(cs)!=1:raise ValueError('Cohorte ambigua')
        co,=cs;snaps=[snapshot(origins[co],day,h,rep) for h in HOURS]
        s0,s1=map(set,snaps)
        missing.extend(dict(fecha=day,vencimiento=v,hora_faltante=HOURS[int(v in s0)]) for v in sorted(s0^s1))
        evidence=[]
        for v in sorted(s0&s1):
            pair=[s[v] for s in snaps]
            if abs(365*(pair[0][1]['T']-pair[1][1]['T'])-15/1440)>1e-8:raise ValueError('Separación distinta de 15 minutos')
            meta=dict(cohorte=co,fecha=day,vencimiento=v,dte_0945=pair[0][1]['T']*365)
            pub,joint,ev,cert=evaluate(pair,np.array(proto['ratios']),proto['epsilon'],proto['tolerancia'])
            rows.append(dict(**meta,casos=pub,conjunto=joint));evidence.append(dict(**meta,medidas=ev));certs.extend(cert)
        p=private/(day+'_testigos.json');dump(p,evidence);files.append(p)
        print(day,'pares',len(s0&s1),'LP acumulados',len(certs),flush=True)
    dump(out/'por_vencimiento.json',rows)
    stats=[]
    for co in (*origins,'total'):
        rr=[r for r in rows if co=='total' or r['cohorte']==co]
        group=dict(cohorte=co,sesiones=len({r['fecha'] for r in rr}),pares=len(rr),
                   iguales_conjuntos=sum(r['conjunto']['igualdad_testificada'] for r in rr),casos={})
        for case in CASES:
            vals=[v for r in rr for v in r['casos'][case]]
            at=[v for v in vals if v['ratio']==1.]
            group['casos'][case]=dict(puntos=len(vals),dentro_apoyo=sum(v['apoyo_ambos'] for v in vals),
                estados=dict(collections.Counter(v['estado'] for v in vals)),
                ancho_mediano_en_F_pp=float(100*np.median([v['superior']-v['inferior'] for v in at])))
        stats.append(group)
    code=[FOLDER/n for n in ('metodo.py','evaluar.py','protocolo.toml')]
    dump(out/'resumen.json',dict(estadisticas=stats,sin_pareja=missing,protocolo=proto,
        fecha_primera=proto['fechas'][0],fecha_ultima=proto['fechas'][-1],scipy=scipy.__version__,
        total_lp=len(certs),certificados_max={k:max(c[k] for c in certs) for k in ('primal','dual','gap')},
        fuente_verificada_sha256=sha(OLD/'verificacion.json'),codigo_sha256_lf={p.name:lf(p) for p in code},
        testigos_privados_sha256={p.name:sha(p) for p in files}))
    print(json.dumps(stats[-1],ensure_ascii=False),flush=True)


if __name__=='__main__':main()
