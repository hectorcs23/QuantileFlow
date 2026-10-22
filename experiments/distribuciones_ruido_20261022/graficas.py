"""Figuras y diferencias efectivamente alcanzadas por testigos admisibles."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--privado",type=Path,required=True)
    a=ap.parse_args()
    out=Path(__file__).parent/"resultados"
    verificacion=json.loads((out/"verificacion.json").read_text(encoding="utf-8"))
    for nombre,h in verificacion["entradas_publicas_sha256"].items():
        assert hashlib.sha256((out/nombre).read_bytes()).hexdigest()==h,nombre
    resumen=json.loads((out/"resumen.json").read_text(encoding="utf-8"))
    perfil=json.loads((out/"perfil.json").read_text(encoding="utf-8"))
    rows=json.loads((out/"por_rebanada.json").read_text(encoding="utf-8"))
    repara={r["filtro"]:r for r in resumen["reparaciones"]}
    agg={r["caso"]:r for r in resumen["agregado"]}
    filtros=["todos","frescas_5s","otm","otm_frescas_5s"]
    labels=["Todas","Recientes\n≤5 segundos","Fuera del\ndinero (OTM)","OTM y\nrecientes"]
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout="constrained")
    values=[repara[f]["rho_mediana"] for f in filtros]
    bars=axes[0].bar(labels,values,color="#17668b",width=.6)
    axes[0].bar_label(bars,fmt="%.2f",padding=5)
    axes[0].set(title="OTM reduce el conflicto, no lo elimina",
        ylabel="Mínima ampliación de bandas (spreads por lado)\nMediana de 48 combinaciones",ylim=(0,3.))
    for x,f in enumerate(filtros):
        axes[0].text(x,.07,f"{repara[f]['filas']:,} filas",ha="center",fontsize=9,color="white",
                     bbox=dict(facecolor="#17668b",edgecolor="none",pad=2))
    propios=["todos_margen_0.5"]+[f+"_rho_propio" for f in filtros[1:]]
    comunes=["todos_margen_0.5"]+[f+"_rho_comun" for f in filtros[1:]]
    xx=np.arange(4)
    for dx,keys,name,color in [(-.18,propios,"Mínimo propio + 0.5 spread","#17668b"),
                               (.18,comunes,"Mismo margen que todas las cotizaciones","#a3481a")]:
        v=[100*agg[k]["cdf"][2]["mediana_ancho"] for k in keys]
        bars=axes[1].bar(xx+dx,v,.36,label=name,color=color)
        axes[1].bar_label(bars,fmt="%.1f",padding=4,fontsize=9)
    axes[1].set_xticks(xx,labels)
    axes[1].set(title="Menos conflicto no identifica una única distribución",
        ylabel="Ancho mediano de la banda de CDF en F\n(puntos porcentuales)",ylim=(0,32))
    axes[1].legend(loc="upper left",fontsize=8)
    for ax in axes: ax.spines[["top","right"]].set_visible(False)
    fig.suptitle("QuantileFlow · Camino B · 6 sesiones conocidas, 12 fotos, 48 foto/vencimiento",fontsize=13)
    fig.savefig(out/"ruido_y_filtros.png",dpi=165)
    plt.close(fig)

    fig,ax=plt.subplots(figsize=(10,6),layout="constrained")
    xs=np.array([b["ratio"] for b in perfil["bandas"]])
    lo=np.array([b["inferior"] for b in perfil["bandas"]])*100
    hi=np.array([b["superior"] for b in perfil["bandas"]])*100
    # Monotonía de CDF: entre dos umbrales, usar la cota inferior izquierda
    # y superior derecha. No inventar una interpolación lineal de las cotas.
    escalones=np.column_stack([xs[:-1],xs[1:]]).ravel()
    ax.fill_between(escalones,np.repeat(lo[:-1],2),np.repeat(hi[1:],2),color="#d6e4ea",
                    label="Envolvente conservadora entre umbrales")
    ax.scatter(xs,lo,color="#829eab",s=8); ax.scatter(xs,hi,color="#829eab",s=8)
    for curve,color,label,style in zip(perfil["curvas_extremas"],["#17668b","#a3481a"],
        ["Distribución admisible A","Distribución admisible B"],["-","--"]):
        ax.step(perfil["ratios_curvas"],np.array(curve["cdf"])*100,where="post",
                color=color,lw=1.8,label=label,linestyle=style)
    at=next(b for b in perfil["bandas"] if b["ratio"]==1.)
    ax.vlines(1,100*at["inferior"],100*at["superior"],color="#192c38",lw=2.5)
    ax.annotate(f"Dos medidas: {100*at['alcanzable_inferior']:.1f}% y {100*at['alcanzable_superior']:.1f}%\nen el mismo umbral F",
        xy=(1,100*at["superior"]),xytext=(1.035,38),
        arrowprops=dict(arrowstyle="-",color="#192c38"),fontsize=11)
    ax.set(xlim=(.9,1.1),ylim=(0,100),xlabel="Precio terminal / forward de referencia (1 = F)",
        ylabel="Probabilidad acumulada neutral al riesgo, %",
        title=f"Mismos precios y margen: dos distribuciones diferentes\n{perfil['fecha']} · {perfil['hora']} ET · {perfil['dias']:.1f} días")
    ax.legend(loc="upper left",fontsize=9)
    ax.spines[["top","right"]].set_visible(False)
    fig.savefig(out/"cdf_admisibles.png",dpi=165)
    plt.close(fig)

    # Un ancho exterior no prueba por sí solo que todo él sea alcanzable.
    # Cuantificar además diferencias de CDF reales entre las dos medidas guardadas.
    gaps={}
    for name,expected in resumen["privados_sha256"].items():
        p=a.privado/name
        assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
        for model in json.loads(p.read_text(encoding="utf-8")):
            if model["caso"] not in agg: continue
            xx=np.array(model["x"])
            ww=[t for t in model["testigos"] if t["tipo"]=="cdf_discreta" and t["umbral"]==1.]
            if len(ww)!=2: raise ValueError("Faltan testigos en F")
            real=[float(np.array(w["p"])[xx<=1.].sum()) for w in ww]
            gaps.setdefault(model["caso"],[]).append(abs(real[1]-real[0]))
    tabla={k:dict(mediana_diferencia_alcanzada=float(np.median(v)),max_diferencia=max(v))
           for k,v in gaps.items()}
    base=[r for r in rows if r.get("caso")=="todos_margen_0.5"]
    cambios={}
    for k in ("soporte_4F","rampa_mitad","referencias_en_banda"):
        ctrl={(r["fecha"],r["hora"],r["dias"]):r for r in rows if r.get("caso")==k}
        ds=[]
        for b in base:
            r=ctrl[b["fecha"],b["hora"],b["dias"]]
            ds.extend(abs(c[l]-d[l]) for c,d in zip(b["cdf"],r["cdf"]) for l in ("inferior","superior"))
        cambios[k]=max(ds)
    extra=dict(diferencias_de_cdf_alcanzadas=tabla,max_cambio_cota_cdf=cambios,
        graficas_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest())
    (out/"controles.json").write_text(json.dumps(extra,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(extra,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
