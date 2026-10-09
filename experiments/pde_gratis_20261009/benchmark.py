"""Benchmark sintético reproducible: BS, adjunto, Taylor, malla y PDFs Q."""
from pathlib import Path
import hashlib
import json
import sys
import time

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from quantileflow.opciones import precio_bs, griegas_bs
from quantileflow.pde import resolver_europea as resolver


def main():
    salida = Path(__file__).parent / "resultados"
    salida.mkdir(exist_ok=True)
    filas = []
    inicio = time.perf_counter()
    for dias in (7, 14, 30, 60, 90):
        for sigma in (.15, .25, .45):
            for strike in (90., 100., 110.):
                for call in (True, False):
                    a = resolver(100, strike, dias/365, .04, .013, sigma, call, nodos=1601, pasos=2400)
                    bs = float(precio_bs(100, strike, dias/365, .04, .013, sigma, call))
                    delta, _, vega = griegas_bs(100, strike, dias/365, .04, .013, sigma, call)
                    filas.append(dict(dias=dias, sigma=sigma, strike=strike, tipo="C" if call else "P",
                        precio_pde=a.precio, precio_bs=bs, error_precio=abs(a.precio-bs),
                        error_delta=abs(a.delta-float(delta)), error_vega=abs(a.vega_paralela-float(vega)),
                        error_masa=a.error_masa, error_dualidad=a.error_dualidad,
                        masa_fronteras=a.masa_fronteras, residual_estado=a.error_residual_estado,
                        residual_adjunto=a.error_residual_adjunto))
    tabla = pd.DataFrame(filas)
    tabla.to_csv(salida / "bs_90_casos.csv", index=False)
    base = dict(spot=100, strike=110, plazo=90/365, tasa=.04, q=.01, nodos=301, pasos=160)
    y = np.linspace(-1.5, 1.5, 301)
    sigma, v = .25+.025*np.tanh(3*y), .5+.3*np.cos(4*y)
    a = resolver(**base, volatilidad=sigma)
    g = float(a.sensibilidad_vol_nodos@v)
    h = 1e-5
    fd = (resolver(**base, volatilidad=sigma+h*v).precio
          -resolver(**base, volatilidad=sigma-h*v).precio)/(2*h)
    taylor = [dict(h=h, resto=abs(resolver(**base, volatilidad=sigma+h*v).precio-a.precio-h*g))
              for h in (.002, .001, .0005, .00025)]
    refinamiento = []
    bs = float(precio_bs(100, 100, 90/365, .04, .013, .25))
    for n, m in ((201,100), (401,400), (801,1600), (1601,6400)):
        x = resolver(100,100,90/365,.04,.013,.25,nodos=n,pasos=m)
        refinamiento.append(dict(nodos=n,pasos=m,error_precio=abs(x.precio-bs)))
    # Separar tiempo de espacio: cambiar ambos a la vez puede ocultar cancelaciones.
    espacio = [dict(nodos=n,error_precio=abs(resolver(100,100,90/365,.04,.013,.25,
                nodos=n,pasos=6400).precio-bs)) for n in (201,401,801,1601)]
    tiempo = [dict(pasos=m,error_precio=abs(resolver(100,100,90/365,.04,.013,.25,
                nodos=1601,pasos=m).precio-bs)) for m in (100,400,1600,6400)]
    dominio = [dict(semiancho=l,precio=resolver(100,100,90/365,.04,.013,.45,
                nodos=round(800*l)+1,pasos=2400,semiancho=l).precio) for l in (.5,1.,1.5)]
    informe = {"naturaleza": "sintético europeo, Q; no calibrado ni predictivo", "presupuesto_datos_usd": 0,
        "casos": len(filas), "malla": {"nodos":1601,"pasos":2400,"semiancho":1.5},
        "maximos": {k: float(tabla[k].max()) for k in ("error_precio","error_delta","error_vega",
            "error_masa","error_dualidad","masa_fronteras","residual_estado","residual_adjunto")},
        "adjunto_espacial": {"derivada":g,"diferencias_centrales":fd,"error_absoluto":abs(g-fd),
            "taylor":taylor,"ratios": [taylor[i]["resto"]/taylor[i+1]["resto"] for i in range(3)]},
        "refinamiento_conjunto":refinamiento,"refinamiento_espacio":espacio,"refinamiento_tiempo":tiempo,
        "refinamiento_dominio":dominio,"segundos_benchmark":time.perf_counter()-inicio,
        "sha256_fuentes": {str(p.relative_to(RAIZ)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__),RAIZ/"quantileflow/pde.py",RAIZ/"quantileflow/opciones.py")}}
    (salida / "verificacion.json").write_text(json.dumps(informe,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    fig, axs = plt.subplots(2,2,figsize=(11,8),layout="constrained")
    xs = np.linspace(60,160,1001)
    for spot in (95,100,105):
        x = resolver(spot,105,30/365,.04,.01,.25)
        precios = spot*np.exp(x.log_moneyness)
        pdf = x.masas/((x.log_moneyness[1]-x.log_moneyness[0])*precios)
        axs[0,0].plot(xs,np.interp(xs,precios,pdf),label=f"spot {spot}")
    axs[0,0].set(title="Distribución terminal Q, 30 días",xlabel="Precio terminal",ylabel="Densidad")
    axs[0,0].legend()
    a = resolver(100,110,90/365,.04,.01,.25,nodos=801,pasos=1600)
    h = a.log_moneyness[1]-a.log_moneyness[0]
    axs[0,1].plot(a.log_moneyness,a.sensibilidad_vol_nodos/h)
    axs[0,1].set(title="Kernel adjunto: dónde importa σ(y)",xlabel="y = log(S/S₀)",ylabel="∂precio / ∂σ por unidad y",xlim=(-.6,.6))
    spots = np.linspace(90,110,21)
    for dias in (7,30,90):
        precios = [resolver(s,105,dias/365,.04,.01,.25).precio for s in spots]
        axs[1,0].plot(spots,precios,label=f"{dias} días")
    axs[1,0].set(title="Call K=105: respuesta al spot",xlabel="Spot",ylabel="Prima por unidad")
    axs[1,0].legend()
    for label, valores, campo in (("espacio (tiempo fijo)",espacio,"nodos"),
                                  ("tiempo (malla fija)",tiempo,"pasos")):
        axs[1,1].loglog([v[campo] for v in valores],[v["error_precio"] for v in valores],"o-",label=label)
    axs[1,1].set(title="Convergencia independiente frente a BS",xlabel="Nodos / pasos",ylabel="Error absoluto de prima")
    axs[1,1].legend()
    fig.suptitle("QuantileFlow · benchmark sin datos comprados · escenarios sintéticos")
    fig.savefig(salida/"benchmark_pde.png",dpi=160)
    plt.close(fig)
    print(json.dumps({"casos":len(filas),"maximos":informe["maximos"],"adjunto_error":abs(g-fd)},indent=2))


if __name__ == "__main__":
    main()
