"""Precio, PDF, CDF y sensibilidades con la misma reconstrucción; sin red."""
from pathlib import Path
import hashlib
import json
import platform
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy.integrate import quad
from quantileflow.distribucion_pde import resolver_distribucion as resolver
from quantileflow.opciones import precio_bs,griegas_bs


def integrar_pdf(d,k,call):
    nudos = np.r_[d.y[0]-d.h,d.y,d.y[-1]+d.h]
    xs = d.spot*np.exp(nudos)
    py = d.evaluar(xs).pdf*xs
    cortes = sorted(set([*nudos,np.clip(np.log(k/d.spot),nudos[0],nudos[-1])]))
    def f(y):
        pago = d.spot*np.exp(y)-k
        return max(pago if call else -pago,0)*np.interp(y,nudos,py)
    return np.exp(-d.tasa*d.plazo)*sum(quad(f,a,b,epsabs=1e-12,epsrel=1e-12)[0]
        for a,b in zip(cortes[:-1],cortes[1:]))


def main():
    salida = Path(__file__).parent/"resultados"
    salida.mkdir(exist_ok=True)
    filas = []
    for dias in (7,14,30,60,90):
        for sigma in (.15,.25,.45):
            d = resolver(100,dias/365,.04,.013,sigma,nodos=1601,pasos=2400)
            for k in (90.,100.,110.):
                c,p = d.valor_europeo(k),d.valor_europeo(k,False)
                paridad = abs(c.precio-p.precio-np.exp(-.04*dias/365)*(c.media_terminal-k))
                for call,v in ((True,c),(False,p)):
                    delta,gamma,vega = griegas_bs(100,k,dias/365,.04,.013,sigma,call)
                    filas.append(dict(dias=dias,sigma=sigma,strike=k,tipo="C" if call else "P",
                        precio=v.precio,precio_bs=float(precio_bs(100,k,dias/365,.04,.013,sigma,call)),
                        error_precio=abs(v.precio-float(precio_bs(100,k,dias/365,.04,.013,sigma,call))),
                        error_delta=abs(v.delta-float(delta)),error_gamma=abs(v.gamma-float(gamma)),
                        error_vega=abs(v.vega_paralela-float(vega)),error_paridad=paridad,
                        error_media=abs(v.error_media_financiera),error_dualidad=v.error_dualidad,
                        error_adjunto_tangente=abs(v.vega_paralela-v.sensibilidad_vol_nodos.sum()),
                        curvatura_strike=v.curvatura_strike,masa_fronteras=d.masa_fronteras))
    t = pd.DataFrame(filas)
    t.to_csv(salida/"bs_90_casos.csv",index=False)
    d = resolver(100,30/365,.04,.013,.25,nodos=401,pasos=400)
    integrales = []
    for k in (90.,100.,110.):
        for call in (True,False):
            v = d.valor_europeo(k,call)
            ref = integrar_pdf(d,k,call)
            integrales.append(dict(strike=k,tipo="C" if call else "P",precio=v.precio,
                                   integral_independiente=ref,error=abs(v.precio-ref)))
    refinamiento = []
    for n,m in ((201,100),(401,400),(801,1600),(1601,6400)):
        x = resolver(100,90/365,.04,.013,.25,nodos=n,pasos=m).valor_europeo(100)
        refinamiento.append(dict(nodos=n,pasos=m,precio=x.precio,
            error_precio=abs(x.precio-float(precio_bs(100,100,90/365,.04,.013,.25))),
            error_media=abs(x.error_media_financiera)))
    # Recuperar la PDF mediante diferencias segundas de precio por strike.
    ks = np.linspace(90.13,110.13,61)
    curvaturas = []
    h = .01
    for k in ks:
        v,mas,menos = d.valor_europeo(k),d.valor_europeo(k+h),d.valor_europeo(k-h)
        bl = np.exp(d.tasa*d.plazo)*(mas.precio-2*v.precio+menos.precio)/h**2
        curvaturas.append(dict(strike=k,pdf=d.evaluar([k]).pdf[0],pdf_desde_precios=bl,
                              error_pdf=abs(bl-d.evaluar([k]).pdf[0])))
    pd.DataFrame(curvaturas).to_csv(salida/"densidad_desde_precios.csv",index=False)
    informe = dict(presupuesto_datos_usd=0,naturaleza="sintético europeo Q, sigma relativa estática",
        casos=len(filas),malla=dict(nodos=1601,pasos=2400,semiancho=1.5),
        maximos={c:float(t[c].max()) for c in t.columns if c.startswith("error_") or c=="masa_fronteras"},
        integral_independiente=integrales,refinamiento=refinamiento,
        error_bl_finito=max(c["error_pdf"] for c in curvaturas),
        entorno=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__),
        sha256_fuentes_lf={p.relative_to(RAIZ).as_posix():hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
            for p in (Path(__file__),RAIZ/"quantileflow/pde.py",RAIZ/"quantileflow/distribucion_pde.py")})
    (salida/"verificacion.json").write_text(json.dumps(informe,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    fig,axs = plt.subplots(2,2,figsize=(11,8),layout="constrained")
    precios = np.linspace(80.13,120.13,51)
    cs = [d.valor_europeo(k) for k in precios]
    ps = [d.valor_europeo(k,False) for k in precios]
    axs[0,0].plot(precios,[v.precio for v in cs],label="call")
    axs[0,0].plot(precios,[v.precio for v in ps],label="put")
    axs[0,0].set(title="Primas desde la misma PDF",xlabel="Strike",ylabel="Precio por unidad")
    axs[0,0].legend()
    axs[0,1].plot(ks,[c["pdf"] for c in curvaturas],label="PDF reconstruida")
    axs[0,1].plot(ks,[c["pdf_desde_precios"] for c in curvaturas],"--",label="e^(rT) ∂²C/∂K², diferencias")
    axs[0,1].set(title="Densidad recuperada de precios",xlabel="Strike",ylabel="Densidad Q")
    axs[0,1].legend(fontsize=8)
    axs[1,0].plot(precios,[-v.sensibilidad_strike*np.exp(d.tasa*d.plazo) for v in cs],label="−e^(rT) ∂C/∂K")
    axs[1,0].plot(precios,1-d.evaluar(precios).cdf,"--",label="P_Q(S_T > K)")
    axs[1,0].set(title="Pendiente del call y probabilidad de cola",xlabel="Strike",ylabel="Probabilidad Q")
    axs[1,0].legend(fontsize=8)
    for campo,label in (("error_precio","error precio vs BS"),("error_media","error media vs forward")):
        axs[1,1].loglog([x["nodos"] for x in refinamiento],[x[campo] for x in refinamiento],"o-",label=label)
    axs[1,1].set(title="Refinamiento de espacio y tiempo",xlabel="Nodos; pasos aumentan ×4",ylabel="Error absoluto")
    axs[1,1].legend(fontsize=8)
    fig.suptitle("QuantileFlow · valoración consistente con PDF · casos sintéticos · presupuesto $0")
    fig.savefig(salida/"valoracion_pdf.png",dpi=160)
    plt.close(fig)
    print(json.dumps({"casos":len(filas),"maximos":informe["maximos"],
        "error_integral":max(x["error"] for x in integrales),"error_bl_finito":informe["error_bl_finito"]},indent=2))


if __name__ == "__main__":
    main()
