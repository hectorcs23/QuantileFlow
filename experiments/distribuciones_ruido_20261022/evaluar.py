"""Experimento B: ruido acotado, filtros y envolventes de distribuciones."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tomllib

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
import scipy
from experiments.distribuciones_ruido_20261022.metodo import Mercado


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p,obj):
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
                 encoding="utf-8",newline="\n")


def seleccionar_filtros(g,F,segundos):
    edad=(g.recibido_utc-g.sello_evento_utc).dt.total_seconds()
    fresca=(edad>=0)&(edad<=segundos)&(g.disponible_utc<=g.recibido_utc)
    otm=((g.tipo=="C")&(g.strike>=F))|((g.tipo=="P")&(g.strike<F))
    return {"todos":g,"frescas_5s":g[fresca],"otm":g[otm],
            "otm_frescas_5s":g[otm&fresca]}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origen",type=Path,required=True)
    ap.add_argument("--privado",type=Path,required=True)
    a=ap.parse_args()
    origen,privado=a.origen.resolve(),a.privado.resolve()
    if privado.is_relative_to(RAIZ) or privado==origen or privado.is_relative_to(origen):
        raise ValueError("Salida privada fuera del repositorio y del origen requerida")
    privado.mkdir(parents=True,exist_ok=True)
    folder=Path(__file__).parent; out=folder/"resultados"; out.mkdir(exist_ok=True)
    proto=tomllib.loads((folder/"protocolo.toml").read_text(encoding="utf-8"))
    fuente=RAIZ/"experiments/forward_fijo_20261014/resultados/resumen.json"
    previo=json.loads(fuente.read_text(encoding="utf-8"))
    for name,h in previo["privados_sha256"].items():
        if sha(origen/name)!=h:
            raise ValueError("Snapshot modificado: "+name)
    resultados, reparaciones, certificados=[],[],[]
    archivo_privados=[]
    perfil=None
    for corte in previo["cortes"]:
        tag=corte["fecha"]+"_"+corte["hora"].replace(":","")
        e=pd.read_parquet(origen/(tag+"_evaluacion.parquet"))
        modelos=json.loads((origen/(tag+"_modelos.json")).read_text(encoding="utf-8"))
        if (not e.raiz.eq("SPXW").all() or (e.entrenamiento&e.holdout).any()
                or not (e.entrenamiento|e.holdout).all()):
            raise ValueError("Universo o partición inválidos")
        evidencia=[]
        for z in modelos["modelos_fijos"][0]["rebanadas"]:
            F,D,T=z["F"],z["D"],z["T"]
            fecha_mask=np.isclose(e.dias,T*365,rtol=0,atol=1e-10)
            g=e[e.entrenamiento&fecha_mask&(e.k.abs()<=.10)]
            h=e[e.holdout&fecha_mask&(e.k.abs()<=.10)&e.tipo.eq("C")]
            if g.empty or h.empty:
                raise ValueError("Training o holdout vacío")
            selected=pd.concat([h.iloc[[np.argmin(abs(h.strike/F-r))]] for r in (.97,1.,1.03)])
            selected=selected.drop_duplicates("id_contrato")
            extras=(selected.strike/F).tolist()
            filtros=seleccionar_filtros(g,F,proto["edad_maxima_segundos"])
            meta=dict(fecha=corte["fecha"],hora=corte["hora"],dias=T*365,
                      vencimiento=str(g.vencimiento.iloc[0]))
            kw=dict(soporte=proto["soporte_maximo"],epsilon=proto["epsilon_cdf"],
                    puntos=proto["ratios_cdf"],extras=extras)
            rhos={}
            def guardar(m,filtro,caso):
                for t in m.testigos:
                    certificados.append(t["certificado"])
                evidencia.append(dict(**meta,filtro=filtro,caso=caso,
                    ids=filtros[filtro].id_contrato.tolist(),
                    holdout_ids=selected.id_contrato.tolist(),**m.evidencia()))
            for filtro,df in filtros.items():
                if df.empty:
                    reparaciones.append(dict(**meta,filtro=filtro,filas=0,rho=None))
                    continue
                m=Mercado(df,F,D,**kw); rhos[filtro]=m.reparar()
                reparaciones.append(dict(**meta,filtro=filtro,filas=len(df),rho=rhos[filtro]))
                guardar(m,filtro,"reparacion_"+filtro)
            fb=(1-proto["forward_banda_relativa"],1+proto["forward_banda_relativa"])
            db=(np.exp(-proto["shock_tasa_anual"]*T),np.exp(proto["shock_tasa_anual"]*T))
            m=Mercado(g,F,D,**kw); rho_economico=m.reparar(fb,db)
            reparaciones.append(dict(**meta,filtro="todos_referencias_en_banda",filas=len(g),rho=rho_economico))
            guardar(m,"todos","reparacion_referencias")
            rho_base=rhos["todos"]+.5
            casos=[]
            for margen in proto["margenes_spreads"]:
                casos.append(dict(nombre=f"todos_margen_{margen:g}",filtro="todos",rho=rhos["todos"]+margen))
            casos.extend([
                dict(nombre="referencias_en_banda",filtro="todos",rho=rho_base,fb=fb,db=db),
                dict(nombre="soporte_4F",filtro="todos",rho=rho_base,soporte=proto["control_soporte_maximo"]),
                dict(nombre="rampa_mitad",filtro="todos",rho=rho_base,epsilon=proto["control_epsilon_cdf"]),
            ])
            for filtro in proto["filtros"][1:]:
                if filtro not in rhos:
                    resultados.append(dict(**meta,caso=filtro+"_sin_datos",estado="sin_datos",filas=0))
                    continue
                casos.extend([
                    dict(nombre=filtro+"_rho_propio",filtro=filtro,rho=rhos[filtro]+.5),
                    dict(nombre=filtro+"_rho_comun",filtro=filtro,rho=rho_base),
                ])
            for caso in casos:
                args=dict(kw)
                for clave in ("soporte","epsilon"):
                    if clave in caso: args[clave]=caso[clave]
                m=Mercado(filtros[caso["filtro"]],F,D,**args)
                refs=dict(fb=caso.get("fb",(1.,1.)),db=caso.get("db",(1.,1.)))
                intervalos=[]
                for k in proto["ratios_cdf"]:
                    exterior=m.cdf(k,caso["rho"],**refs)
                    interior=m.cdf(k,caso["rho"],**refs,discreta=True)
                    if (interior["inferior"]<exterior["inferior"]-1e-7 or
                            interior["superior"]>exterior["superior"]+1e-7):
                        raise RuntimeError("Cotas interiores y exteriores contradictorias")
                    intervalos.append(dict(ratio=k,**exterior,
                        alcanzable_inferior=interior["inferior"],alcanzable_superior=interior["superior"],
                        ancho_alcanzado=interior["ancho"]))
                widths=[]; solapan=0
                for row in selected.itertuples():
                    v=m.precio_call(row.strike/F,caso["rho"],**refs)
                    lower,upper=v["inferior"]*F*D,v["superior"]*F*D
                    solapan+=int(lower<=row.ask+1e-7 and upper>=row.bid-1e-7)
                    widths.append((upper-lower)/(row.ask-row.bid))
                resultados.append(dict(**meta,caso=caso["nombre"],estado="ok",
                    filtro=caso["filtro"],filas=len(filtros[caso["filtro"]]),rho=caso["rho"],
                    soporte=args["soporte"],epsilon=args["epsilon"],cdf=intervalos,
                    holdout_n=len(selected),holdout_solapan=solapan,
                    holdout_ancho_spreads_medio=float(np.mean(widths))))
                guardar(m,caso["filtro"],caso["nombre"])
            if perfil is None:
                puntos=np.unique(np.r_[np.linspace(.9,1.1,21),1.])
                m=Mercado(g,F,D,soporte=2,epsilon=proto["epsilon_cdf"],puntos=puntos)
                bandas=[]
                for k in puntos:
                    exterior=m.cdf(k,rho_base)
                    interior=m.cdf(k,rho_base,discreta=True)
                    bandas.append(dict(ratio=float(k),**exterior,
                        alcanzable_inferior=interior["inferior"],alcanzable_superior=interior["superior"],
                        ancho_alcanzado=interior["ancho"]))
                w=[w for w in m.testigos if w["tipo"]=="cdf_discreta" and w["umbral"]==1.]
                xx=np.linspace(.85,1.15,301)
                curvas=[]
                for t in w:
                    p=np.array(t["p"])
                    curvas.append(dict(lado=t["lado"],cdf=[float(p[m.x<=x].sum()) for x in xx]))
                perfil=dict(**meta,rho=rho_base,bandas=bandas,ratios_curvas=xx.tolist(),
                            curvas_extremas=curvas,regla="Primera foto y primer vencimiento, sin seleccionar por resultado")
                guardar(m,"todos","perfil")
        archivo=privado/(tag+"_medidas.json")
        dump(archivo,evidencia); archivo_privados.append(archivo)
        print(tag,"modelos",len(evidencia),"LP acumulados",len(certificados),flush=True)
    agregados=[]
    for nombre in sorted({r["caso"] for r in resultados if r["estado"]=="ok"}):
        grupo=[r for r in resultados if r["caso"]==nombre and r["estado"]=="ok"]
        cdf=[]
        for j,k in enumerate(proto["ratios_cdf"]):
            ws=[r["cdf"][j]["ancho"] for r in grupo]
            cdf.append(dict(ratio=k,mediana_ancho=float(np.median(ws)),
                            mediana_ancho_alcanzado=float(np.median([r["cdf"][j]["ancho_alcanzado"] for r in grupo])),
                            min_ancho=min(ws),max_ancho=max(ws)))
        agregados.append(dict(caso=nombre,rebanadas=len(grupo),
            mediana_rho=float(np.median([r["rho"] for r in grupo])),
            cdf=cdf,holdout_n=sum(r["holdout_n"] for r in grupo),
            holdout_solapan=sum(r["holdout_solapan"] for r in grupo),
            mediana_holdout_ancho_spreads=float(np.median([r["holdout_ancho_spreads_medio"] for r in grupo]))))
    rep=[]
    for f in sorted({r["filtro"] for r in reparaciones}):
        rs=[r for r in reparaciones if r["filtro"]==f and r["rho"] is not None]
        rep.append(dict(filtro=f,rebanadas=len(rs),filas=sum(r["filas"] for r in rs),
            rho_mediana=float(np.median([r["rho"] for r in rs])) if rs else None,
            rho_max=max([r["rho"] for r in rs],default=None),
            sin_reparar=sum(r["rho"]<=1e-6 for r in rs)))
    fuentes=[Path(__file__),folder/"metodo.py",folder/"protocolo.toml"]
    dump(out/"por_rebanada.json",resultados)
    dump(out/"reparaciones.json",reparaciones)
    dump(out/"perfil.json",perfil)
    dump(out/"resumen.json",dict(protocolo=proto,scipy=scipy.__version__,
        sesiones=len({c["fecha"] for c in previo["cortes"]}),cortes=len(previo["cortes"]),
        total_lp=len(certificados),diagnosticos={k:max(d[k] for d in certificados) for k in ("primal","dual","gap")},
        reparaciones=rep,agregado=agregados,
        origen_resumen_sha256_lf=hashlib.sha256(fuente.read_text(encoding="utf-8").encode()).hexdigest(),
        codigo_sha256_lf={p.relative_to(RAIZ).as_posix():hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in fuentes},
        privados_sha256={p.name:sha(p) for p in archivo_privados}))
    print(json.dumps({"reparaciones":rep,"agregado":agregados},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
