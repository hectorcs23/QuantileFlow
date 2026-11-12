"""Contraste L1+cap con cohortes separadas; no usa holdout para ajustar tolerancias."""
import argparse,hashlib,json,math,sys,tomllib
from pathlib import Path
RAIZ=Path(__file__).resolve().parents[2];sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
import scipy
from experiments.ruido_concentrado_20261022.metodo import MercadoL1,conflictos_paridad
from experiments.distribuciones_ruido_20261022.evaluar import dump,sha


def evaluar_rebanada(g,held,z,meta,proto):
    F,D,T=z['F'],z['D'],z['T']
    chosen=pd.concat([held.iloc[[np.argmin(abs(held.strike/F-r))]] for r in (.97,1.,1.03)]).drop_duplicates('id_contrato')
    kw=dict(soporte=proto['soporte_maximo'],epsilon=proto['epsilon_cdf'],puntos=proto['ratios_cdf'],extras=(chosen.strike/F).tolist())
    evidence=[]; rows=[]
    def save(m,case):
        evidence.append(dict(**meta,caso=case,ids=g.id_contrato.tolist(),holdout_ids=chosen.id_contrato.tolist(),**m.evidencia()))
    m=MercadoL1(g,F,D,**kw);rho=m.reparar();cap=rho+.5
    minimum=m.reparar_l1(cap)
    w=m.testigos[-1];err=m.desviaciones(np.array(w['p']),w['d'])
    top=max(1,math.ceil(.1*len(g)));total=float(sum(err))
    rep=dict(**meta,filas=len(g),rho=rho,cap=cap,media_min=minimum,
        fraccion_modificada=float(np.mean(err>1e-6)),
        participacion_top10=float(np.sort(err)[-top:].sum()/total) if total>1e-8 else 0.,
        paridad=conflictos_paridad(g,F,D,cap))
    if rep['paridad']['media_error_min']>minimum+1e-6: raise ValueError('Cota de paridad excede optimo')
    save(m,'reparaciones')
    budget=minimum+proto['margen_principal']
    cases=[dict(nombre='uniforme',uniforme=True)]
    cases.extend(dict(nombre=f'l1_margen_{v:g}',presupuesto=minimum+v) for v in proto['margenes_media'])
    cases.extend([
        dict(nombre='referencias',presupuesto=budget,fb=(1-proto['forward_banda_relativa'],1+proto['forward_banda_relativa']),
             db=(np.exp(-proto['shock_tasa_anual']*T),np.exp(proto['shock_tasa_anual']*T))),
        dict(nombre='soporte_4F',presupuesto=budget,soporte=4.),
        dict(nombre='rampa_mitad',presupuesto=budget,epsilon=proto['epsilon_cdf']/2)])
    for case in cases:
        opts=dict(kw);opts.update({k:case[k] for k in ('soporte','epsilon') if k in case})
        m=MercadoL1(g,F,D,**opts);uniform=case.get('uniforme',False)
        refs=dict(fb=case.get('fb',(1.,1.)),db=case.get('db',(1.,1.)))
        intervals=[]
        for k in proto['ratios_cdf']:
            outer=(m.cdf(k,cap,**refs) if uniform else m.cdf_l1(k,cap,case['presupuesto'],**refs))
            inner=(m.cdf(k,cap,**refs,discreta=True) if uniform else m.cdf_l1(k,cap,case['presupuesto'],**refs,discreta=True))
            if inner['inferior']<outer['inferior']-1e-7 or inner['superior']>outer['superior']+1e-7:
                raise ValueError('Cotas interior/exterior incompatibles')
            intervals.append(dict(ratio=k,**outer,alcanzable_inferior=inner['inferior'],
                                  alcanzable_superior=inner['superior'],ancho_alcanzado=inner['ancho']))
        hits=0;widths=[]
        for h in chosen.itertuples():
            v=(m.precio_call(h.strike/F,cap,**refs) if uniform else m.precio_call_l1(h.strike/F,cap,case['presupuesto'],**refs))
            lo,hi=v['inferior']*F*D,v['superior']*F*D
            hits+=int(lo<=h.ask+1e-7 and hi>=h.bid-1e-7)
            widths.append((hi-lo)/(h.ask-h.bid))
        rows.append(dict(**meta,caso=case['nombre'],filas=len(g),cap=cap,
            presupuesto=None if uniform else case['presupuesto'],cdf=intervals,
            holdout_n=len(chosen),holdout_solapan=hits,holdout_ancho_spreads_medio=float(np.mean(widths))))
        save(m,case['nombre'])
    return rep,rows,evidence


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('origen','nuevos','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();private=a.privado.resolve()
    if private.is_relative_to(RAIZ) or any(private==p.resolve() or private.is_relative_to(p.resolve()) for p in (a.origen,a.nuevos)):
        raise ValueError('Salida privada fuera de Git y de las entradas')
    private.mkdir(parents=True,exist_ok=True)
    folder=Path(__file__).parent;out=folder/'resultados';out.mkdir(exist_ok=True)
    proto=tomllib.loads((folder/'protocolo.toml').read_text(encoding='utf-8'))
    hist=RAIZ/'experiments/forward_fijo_20261014/resultados/resumen.json';new=out/'entradas_nuevas.json'
    cohorts=[('conocidas',a.origen,hist),('nuevas',a.nuevos,new)]
    rows=[];rep=[];certs=[];files=[];sources={}
    for cohort,origin,source in cohorts:
        src=json.loads(source.read_text(encoding='utf-8'))
        sources[cohort]=dict(resumen_sha256_lf=hashlib.sha256(source.read_text(encoding='utf-8').encode()).hexdigest(),
                            privados_sha256=src['privados_sha256'])
        for name,h in src['privados_sha256'].items():
            if sha(origin/name)!=h: raise ValueError('Entrada alterada: '+name)
        for cut in src['cortes']:
            tag=cut['fecha']+'_'+cut['hora'].replace(':','')
            e=pd.read_parquet(origin/(tag+'_evaluacion.parquet'))
            models=json.loads((origin/(tag+'_modelos.json')).read_text(encoding='utf-8'))
            if not e.raiz.eq('SPXW').all() or not (e.entrenamiento==~e.holdout).all():
                raise ValueError('Universo/particion incorrecto')
            evidence=[]
            for z in models['modelos_fijos'][0]['rebanadas']:
                mask=np.isclose(e.dias,z['T']*365,rtol=0,atol=1e-10)&(e.k.abs()<=.1)
                g=e[mask&e.entrenamiento];h=e[mask&e.holdout&e.tipo.eq('C')]
                if g.empty or h.empty: raise ValueError('Training/holdout vacio')
                meta=dict(cohorte=cohort,fecha=cut['fecha'],hora=cut['hora'],dias=z['T']*365,vencimiento=str(g.vencimiento.iloc[0]))
                rr,rs,ev=evaluar_rebanada(g,h,z,meta,proto)
                rep.append(rr);rows.extend(rs);evidence.extend(ev)
                for model in ev:certs.extend(t['certificado'] for t in model['testigos'])
            path=private/(cohort+'_'+tag+'_medidas.json');dump(path,evidence);files.append(path)
            print(cohort,tag,'LP acumulados',len(certs),flush=True)
    agregado=[]
    for cohort in ('conocidas','nuevas'):
        for case in sorted({r['caso'] for r in rows}):
            rr=[r for r in rows if (r['cohorte'],r['caso'])==(cohort,case)]
            cc=[]
            for j,k in enumerate(proto['ratios_cdf']):
                cc.append(dict(ratio=k,mediana_ancho=float(np.median([r['cdf'][j]['ancho'] for r in rr])),
                    mediana_alcanzado=float(np.median([r['cdf'][j]['ancho_alcanzado'] for r in rr])),
                    max_ancho=max(r['cdf'][j]['ancho'] for r in rr)))
            agregado.append(dict(cohorte=cohort,caso=case,rebanadas=len(rr),cdf=cc,
                holdout_n=sum(r['holdout_n'] for r in rr),holdout_solapan=sum(r['holdout_solapan'] for r in rr),
                mediana_ancho_holdout=float(np.median([r['holdout_ancho_spreads_medio'] for r in rr]))))
    repairs=[]
    for co in ('conocidas','nuevas'):
        rr=[r for r in rep if r['cohorte']==co]
        repairs.append(dict(cohorte=co,sesiones=len({r['fecha'] for r in rr}),rebanadas=len(rr),filas=sum(r['filas'] for r in rr),
            medianas={k:float(np.median([r[k] for r in rr])) for k in ('rho','cap','media_min','fraccion_modificada','participacion_top10')},
            paridad={k:sum(r['paridad'][k] for r in rr) for k in ('pares','incompatibles','filas_modificadas_min')}))
    code=[Path(__file__),folder/'metodo.py',folder/'protocolo.toml',RAIZ/'experiments/distribuciones_ruido_20261022/metodo.py']
    dump(out/'por_rebanada.json',rows);dump(out/'reparaciones.json',rep)
    dump(out/'resumen.json',dict(protocolo=proto,scipy=scipy.__version__,total_lp=len(certs),agregado=agregado,reparaciones=repairs,
        diagnosticos={k:max(c[k] for c in certs) for k in ('primal','dual','gap')},origenes=sources,
        codigo_sha256_lf={p.relative_to(RAIZ).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in code},
        privados_sha256={p.name:sha(p) for p in files}))
    print(json.dumps(repairs,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
