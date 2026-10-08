"""Puente analítico precio-densidad; NO implementa aún una PDE ni un adjunto.

Datos sintéticos europeos con volatilidad constante. La diferenciación es
respecto al spot inicial, manteniendo plazo, tasa, dividendo e IV fijos.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import quad

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quantileflow.opciones import griegas_bs, precio_bs


def densidad(s, spot, plazo, tasa, dividendo, iv):
    s = np.asarray(s, dtype=float)
    ancho = iv * math.sqrt(plazo)
    z = (np.log(s / spot) - (tasa-dividendo-iv**2/2)*plazo)/ancho
    return np.exp(-z*z/2)/(s*ancho*math.sqrt(2*math.pi))


def derivada_spot(s, spot, plazo, tasa, dividendo, iv):
    ancho = iv * math.sqrt(plazo)
    z = (np.log(np.asarray(s)/spot)-(tasa-dividendo-iv**2/2)*plazo)/ancho
    return densidad(s, spot, plazo, tasa, dividendo, iv)*z/(spot*ancho)


def verificar():
    errores_precio, errores_delta, errores_masa, errores_masa_derivada = [], [], [], []
    casos = 0
    for spot in (80., 100., 130.):
        for dias in (7., 14., 30., 60., 90.):
            for iv in (.15, .25, .45):
                plazo, tasa, q = dias/365, .04, .01
                mu, ancho = (tasa-q-iv**2/2)*plazo, iv*math.sqrt(plazo)
                inferior, superior = spot*math.exp(mu-10*ancho), spot*math.exp(mu+10*ancho)
                p = lambda s: float(densidad(s, spot, plazo, tasa, q, iv))
                dp = lambda s: float(derivada_spot(s, spot, plazo, tasa, q, iv))
                masa = quad(p, inferior, superior, epsabs=1e-11, epsrel=1e-11)[0]
                masa_derivada = quad(dp, inferior, superior, epsabs=1e-11, epsrel=1e-11)[0]
                errores_masa.append(abs(masa-1))
                errores_masa_derivada.append(abs(masa_derivada))
                for ratio in (.8, .95, 1., 1.05, 1.2):
                    strike = spot*ratio
                    inicio = max(strike, inferior)
                    valor = math.exp(-tasa*plazo)*quad(lambda s: (s-strike)*p(s), inicio, superior,
                                                        epsabs=1e-10, epsrel=1e-10)[0]
                    delta = math.exp(-tasa*plazo)*quad(lambda s: (s-strike)*dp(s), inicio, superior,
                                                        epsabs=1e-10, epsrel=1e-10)[0]
                    referencia = float(precio_bs(spot, strike, plazo, tasa, q, iv))
                    referencia_delta = float(griegas_bs(spot, strike, plazo, tasa, q, iv)[0])
                    errores_precio.append(abs(valor-referencia))
                    errores_delta.append(abs(delta-referencia_delta))
                    casos += 1
    assert max(errores_precio) < 1e-8
    assert max(errores_delta) < 1e-9
    assert max(errores_masa) < 1e-10
    assert max(errores_masa_derivada) < 1e-10
    spot, strike, plazo, tasa, q, iv = 100., 105., 30/365, .04, 0., .25
    fd = []
    delta = float(griegas_bs(spot, strike, plazo, tasa, q, iv)[0])
    for h in (1e-1, 1e-2, 1e-3, 1e-4):
        aproximacion = float((precio_bs(spot+h, strike, plazo, tasa, q, iv)-
                              precio_bs(spot-h, strike, plazo, tasa, q, iv))/(2*h))
        fd.append({"paso_spot_dolares": h, "delta_fd": aproximacion,
                   "error_absoluto": abs(aproximacion-delta)})
    assert min(f["error_absoluto"] for f in fd) < 1e-8
    puntos = np.linspace(75., 135., 1201)
    h = 1e-3
    kernel_fd = (densidad(puntos,spot+h,plazo,tasa,q,iv)-densidad(puntos,spot-h,plazo,tasa,q,iv))/(2*h)
    error_kernel = float(np.max(np.abs(kernel_fd-derivada_spot(puntos,spot,plazo,tasa,q,iv))))
    assert error_kernel < 1e-8
    return {"tipo": "verificacion_analitica_sintetica_no_solver_pde",
            "casos_call": casos, "error_precio_max_usd_por_accion": max(errores_precio),
            "error_delta_max": max(errores_delta), "error_masa_max": max(errores_masa),
            "error_integral_derivada_masa_max": max(errores_masa_derivada),
            "error_kernel_spot_vs_fd_max": error_kernel, "delta_ejemplo": delta,
            "precio_ejemplo_spot_100": float(precio_bs(spot,strike,plazo,tasa,q,iv)),
            "precio_ejemplo_spot_105": float(precio_bs(105.,strike,plazo,tasa,q,iv)),
            "diferencias_finitas": fd, "distribucion": "Q, neutral al riesgo",
            "mantenido_fijo": ["plazo", "tasa", "dividendo continuo", "IV constante"],
            "colas_cuadratura": "10 desviaciones en log-precio; cotas fijas al evaluar integrales"}


def figura(destino):
    s = np.linspace(65., 145., 1800)
    args = (30/365, .04, 0., .25)
    fig, axs = plt.subplots(1,2,figsize=(12,4.4),layout="constrained")
    for spot,color in ((100.,"#17638c"),(105.,"#ab5819")):
        axs[0].plot(s,densidad(s,spot,*args),label=f"Spot inicial ${spot:.0f}",color=color)
    axs[0].set(xlabel="Precio terminal ($)",ylabel="Densidad Q (1/$)",title="Cambio de spot con IV y plazo fijos")
    axs[0].legend()
    derivada = derivada_spot(s,100.,*args)
    axs[1].plot(s,derivada,color="#17638c")
    axs[1].fill_between(s,derivada,0,where=derivada>=0,color="#178268",alpha=.35,label="Aumenta masa")
    axs[1].fill_between(s,derivada,0,where=derivada<0,color="#ab5819",alpha=.35,label="Disminuye masa")
    axs[1].axhline(0,color="#666666",lw=.7)
    axs[1].set(xlabel="Precio terminal ($)",ylabel="∂p/∂S₀ (1/$²)",
               title="Sensibilidad local de la distribución")
    axs[1].legend()
    for ax in axs:
        ax.grid(alpha=.15)
    fig.suptitle("Ejemplo sintético europeo: 30 días, IV 25%, r 4%, q 0%\nLa derivada redistribuye masa; no es una probabilidad ni un pronóstico",fontsize=12)
    fig.savefig(destino,dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    salida = Path(__file__).parent/"resultados"
    salida.mkdir(exist_ok=True)
    resultado = verificar()
    (salida/"verificacion.json").write_text(json.dumps(resultado,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    figura(salida/"sensibilidad_densidad.png")
    print(json.dumps(resultado,ensure_ascii=False,indent=2))
