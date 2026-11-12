"""Reconstruye cotizaciones y objetivos desde los testigos; no vuelve a optimizar."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

RAIZ=Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origen",type=Path,required=True)
    ap.add_argument("--privado",type=Path,required=True)
    a=ap.parse_args()
    folder=Path(__file__).parent; out=folder/"resultados"
    resumen=json.loads((out/"resumen.json").read_text(encoding="utf-8"))
    previo_path=RAIZ/"experiments/forward_fijo_20261014/resultados/resumen.json"
    assert hashlib.sha256(previo_path.read_text(encoding="utf-8").encode()).hexdigest()==resumen["origen_resumen_sha256_lf"]
    previo=json.loads(previo_path.read_text(encoding="utf-8"))
    for n,h in previo["privados_sha256"].items():
        assert sha(a.origen/n)==h,n
    for n,h in resumen["codigo_sha256_lf"].items():
        assert hashlib.sha256((RAIZ/n).read_text(encoding="utf-8").encode()).hexdigest()==h,n
    publicos=json.loads((out/"por_rebanada.json").read_text(encoding="utf-8"))
    pub={(r["fecha"],r["hora"],r["dias"],r["caso"]):r for r in publicos if r["estado"]=="ok"}
    maximos=dict(masa=0.,negatividad=0.,bandas_normalizado=0.,referencias=0.,objetivo=0.)
    total=0
    for n,h in resumen["privados_sha256"].items():
        assert sha(a.privado/n)==h,n
        tag=n.replace("_medidas.json","")
        df=pd.read_parquet(a.origen/(tag+"_evaluacion.parquet"))
        anclas=json.loads((a.origen/(tag+"_modelos.json")).read_text(encoding="utf-8"))["modelos_fijos"][0]["rebanadas"]
        for modelo in json.loads((a.privado/n).read_text(encoding="utf-8")):
            F,D=modelo["F"],modelo["D"]
            z=next(z for z in anclas if abs(z["T"]*365-modelo["dias"])<1e-10)
            assert F==z["F"] and D==z["D"]
            base=df[df.entrenamiento & (df.k.abs()<=.10) & np.isclose(df.dias,modelo["dias"],rtol=0,atol=1e-10)]
            if "frescas" in modelo["filtro"]:
                edad=(base.recibido_utc-base.sello_evento_utc).dt.total_seconds()
                base=base[(edad>=0)&(edad<=5)&(base.disponible_utc<=base.recibido_utc)]
            if "otm" in modelo["filtro"]:
                base=base[((base.tipo=="C")&(base.strike>=F))|((base.tipo=="P")&(base.strike<F))]
            assert base.id_contrato.tolist()==modelo["ids"],"Filtro o reserva cambiado"
            held=df.set_index("id_contrato").loc[modelo["holdout_ids"]]
            assert held.holdout.all() and not held.entrenamiento.any()
            xx=np.asarray(modelo["x"]); eps=modelo["epsilon"]
            assert xx[0]==0 and xx[-1]==modelo["soporte"] and np.all(np.diff(xx)>0)
            kk=base.strike.to_numpy()/F
            payoffs=np.maximum(np.where(base.tipo.to_numpy()[:,None]=="C",xx[None,:]-kk[:,None],kk[:,None]-xx[None,:]),0.)
            for t in modelo["testigos"]:
                total+=1
                pp=np.asarray(t["p"]); d=t["d"]; rho=t["rho"]
                assert len(pp)==len(xx) and np.isfinite(pp).all() and np.isfinite(d) and d>0 and rho>=0
                maximos["masa"]=max(maximos["masa"],abs(sum(pp)-1))
                maximos["negatividad"]=max(maximos["negatividad"],max(0.,-float(min(pp))))
                media=float(xx@pp)
                maximos["referencias"]=max(maximos["referencias"],t["fb"][0]-media,media-t["fb"][1],
                                          t["db"][0]-d,d-t["db"][1])
                precio=F*D*d*(payoffs@pp)
                spread=(base.ask-base.bid).to_numpy()
                error=max(float(np.max(base.bid.to_numpy()-rho*spread-precio)),
                          float(np.max(precio-base.ask.to_numpy()-rho*spread)),0.)/(F*D)
                maximos["bandas_normalizado"]=max(maximos["bandas_normalizado"],error)
                if t["tipo"] in ("cdf","cdf_discreta"):
                    k=t["umbral"]
                    if t["tipo"]=="cdf_discreta":
                        payoff=(xx<=k).astype(float)
                    elif t["lado"]=="inferior":
                        payoff=np.where(xx<=k-eps,1.,np.where(xx>=k,0.,(k-xx)/eps))
                    else:
                        payoff=np.where(xx<=k,1.,np.where(xx>=k+eps,0.,(k+eps-xx)/eps))
                    valor=float(pp@payoff)
                    verdadera=float(pp[xx<=k].sum())
                    assert valor<=verdadera+1e-7 if t["lado"]=="inferior" else valor>=verdadera-1e-7
                    clave=(modelo["fecha"],modelo["hora"],modelo["dias"],modelo["caso"])
                    if clave in pub:
                        c=next(c for c in pub[clave]["cdf"] if c["ratio"]==k)
                        campo=("alcanzable_" if t["tipo"]=="cdf_discreta" else "")+t["lado"]
                        assert abs(c[campo]-valor)<1e-7
                elif t["tipo"]=="call":
                    valor=float(d*(pp@np.maximum(xx-t["strike_ratio"],0.)))
                else:
                    valor=rho
                maximos["objetivo"]=max(maximos["objetivo"],abs(valor-t["valor"]))
        print(tag,"testigos verificados",total,flush=True)
    assert total==resumen["total_lp"]
    assert max(maximos.values())<1e-7,maximos
    # Comparaciones de conjuntos anidados; los filtros a igual tolerancia quitan información.
    grupos={}
    for r in pub.values():
        grupos.setdefault((r["fecha"],r["hora"],r["dias"]),{})[r["caso"]]=r
    def contiene(externo,interno):
        for e,i in zip(externo["cdf"],interno["cdf"]):
            assert e["inferior"]<=i["inferior"]+1e-7
            assert e["superior"]>=i["superior"]-1e-7
    comparaciones=0
    for rs in grupos.values():
        b=rs["todos_margen_0.5"]
        contiene(b,rs["todos_margen_0.1"]); contiene(rs["todos_margen_1"],b)
        contiene(rs["referencias_en_banda"],b); contiene(rs["soporte_4F"],b)
        contiene(b,rs["rampa_mitad"]); comparaciones+=5
        for f in ("frescas_5s","otm","otm_frescas_5s"):
            if f+"_rho_comun" in rs:
                contiene(rs[f+"_rho_comun"],b); comparaciones+=1
    reporte=dict(testigos=total,max_errores=maximos,comparaciones_anidadas=comparaciones,
        alcance="Reprecios, masa, media, referencias, bandas y objetivos reconstruidos desde medidas guardadas. Los certificados primal/dual se comprobaron al optimizar.",
        verificador_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(),
        entradas_publicas_sha256={p.name:sha(p) for p in [out/"resumen.json",out/"por_rebanada.json",out/"perfil.json",out/"reparaciones.json"]})
    (out/"verificacion.json").write_text(json.dumps(reporte,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(reporte,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
