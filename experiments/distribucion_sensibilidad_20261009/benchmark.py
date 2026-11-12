"""Sensibilidad de distribuciones sintéticas Q, sin red ni datos comprados."""
from pathlib import Path
from dataclasses import asdict
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
from scipy.stats import norm
from quantileflow.distribucion_pde import resolver_distribucion as resolver


def referencia(xs, spot, t, sigma, r=.04, q=.013):
    mu, std = r-q-sigma*sigma/2,sigma*np.sqrt(t)
    z = (np.log(xs/spot)-mu*t)/std
    pdf, phi = norm.pdf(z)/(xs*std),norm.pdf(z)
    zs, zt = np.sqrt(t)-z/sigma,-mu/std-z/(2*t)
    return dict(pdf=pdf,cdf=norm.cdf(z),pdf_spot=pdf*z/(spot*std),
        pdf_sigma=pdf*(-z*zs-1/sigma),pdf_plazo=pdf*(-z*zt-1/(2*t)),
        cdf_spot=-phi/(spot*std),cdf_sigma=phi*zs,cdf_plazo=phi*zt)


def main():
    salida = Path(__file__).parent/"resultados"
    salida.mkdir(exist_ok=True)
    filas, cuantiles = [],[]
    xs = np.array([95.13,100.13,105.13])
    for dias in (7,14,30,60,90):
        for sigma in (.15,.25,.45):
            t = dias/365
            d = resolver(100,t,.04,.013,sigma,nodos=3201,pasos=2400)
            a,ref = d.evaluar(xs),referencia(xs,100,t,sigma)
            fila = dict(dias=dias,sigma=sigma,masa_fronteras=d.masa_fronteras,
                error_masa=d.error_masa_pre_normalizacion,error_masa_tangentes=d.error_masa_tangentes)
            for campo,exacta in ref.items():
                fila["error_"+campo] = float(np.max(abs(getattr(a,campo)-exacta)))
            errores_q,errores_qs,errores_qt = [],[],[]
            for alpha in (.01,.05,.5,.95,.99):
                c = d.cuantil(alpha)
                z = norm.ppf(alpha)
                exacta = 100*np.exp((.04-.013-sigma*sigma/2)*t+sigma*np.sqrt(t)*z)
                eqs = exacta*(-sigma*t+np.sqrt(t)*z)
                eqt = exacta*(.04-.013-sigma*sigma/2+sigma*z/(2*np.sqrt(t)))
                errores_q.append(abs(c.precio-exacta))
                errores_qs.append(abs(c.sensibilidad_sigma-eqs))
                errores_qt.append(abs(c.sensibilidad_plazo-eqt))
                cuantiles.append(dict(dias=dias,sigma=sigma,alpha=alpha,precio=c.precio,
                    precio_lognormal=exacta,sensibilidad_spot=c.sensibilidad_spot,
                    sensibilidad_sigma=c.sensibilidad_sigma,sensibilidad_plazo=c.sensibilidad_plazo,
                    condicion=c.condicion_inversa_cdf))
            fila.update(error_cuantil=max(errores_q),error_cuantil_sigma=max(errores_qs),
                        error_cuantil_plazo=max(errores_qt))
            filas.append(fila)
    tabla = pd.DataFrame(filas)
    tabla.to_csv(salida/"verificacion_lognormal.csv",index=False)
    pd.DataFrame(cuantiles).to_csv(salida/"cuantiles.csv",index=False)

    p = dict(spot=100,plazo=30/365,tasa=.04,q=.013,volatilidad=.25,nodos=1601,pasos=2400)
    base = resolver(**p)
    cola,cuantil = base.probabilidad_cola(105),base.cuantil(.05)
    variantes = [("base",{}),("spot +1",{"spot":101}),
                 ("IV +1 punto porcentual",{"volatilidad":.26}),
                 ("un día transcurrido",{"plazo":29/365})]
    escenarios = []
    modelos = []
    for etiqueta,cambio in variantes:
        d = base if not cambio else resolver(**(p | cambio))
        modelos.append((etiqueta,d))
        ds,dv,dt = cambio.get("spot",100)-100,cambio.get("volatilidad",.25)-.25,cambio.get("plazo",30/365)-30/365
        q05,q50,q95 = (d.cuantil(alpha).precio for alpha in (.05,.5,.95))
        escenarios.append(dict(escenario=etiqueta,spot=d.spot,plazo_dias=d.plazo*365,
            sigma=cambio.get("volatilidad",.25),prob_bajo_95=d.probabilidad_cola(95,False).probabilidad,
            prob_sobre_105=d.probabilidad_cola(105).probabilidad,q05=q05,q50=q50,q95=q95,
            prob_sobre_105_lineal=cola.probabilidad+ds*cola.sensibilidad_spot+dv*cola.sensibilidad_sigma+dt*cola.sensibilidad_plazo,
            q05_lineal=cuantil.precio+ds*cuantil.sensibilidad_spot+dv*cuantil.sensibilidad_sigma+dt*cuantil.sensibilidad_plazo))
    pd.DataFrame(escenarios).to_csv(salida/"escenarios_sinteticos.csv",index=False)

    # Campo no constante: tangente paralela y adjunto para todos los nodos.
    y = np.linspace(-1.5,1.5,401)
    sigma, v = .25+.025*np.tanh(3*y),.5+.3*np.cos(4*y)
    p2 = dict(spot=100,plazo=60/365,tasa=.04,q=.013,nodos=401,pasos=300)
    d = resolver(**p2,volatilidad=sigma)
    g, gq = d.gradiente_vol_cdf(110.13),d.gradiente_vol_cuantil(.05)
    h = 1e-5
    mas,menos = resolver(**p2,volatilidad=sigma+h*v),resolver(**p2,volatilidad=sigma-h*v)
    fd = (mas.evaluar([110.13]).cdf[0]-menos.evaluar([110.13]).cdf[0])/(2*h)
    fdq = (mas.cuantil(.05).precio-menos.cuantil(.05).precio)/(2*h)
    taylor = []
    for h in (.002,.001,.0005):
        nuevo = resolver(**p2,volatilidad=sigma+h*v).evaluar([110.13]).cdf[0]
        taylor.append(dict(h=h,resto=abs(nuevo-d.evaluar([110.13]).cdf[0]-h*float(g@v))))
    informe = dict(naturaleza="modelo sintético europeo Q; no calibrado ni predictivo",presupuesto_datos_usd=0,
        casos_distribucion=len(filas),cuantiles=len(cuantiles),malla=dict(nodos=3201,pasos=2400,semiancho=1.5),
        maximos={c:float(tabla[c].max()) for c in tabla.columns if c.startswith("error_") or c=="masa_fronteras"},
        adjunto=dict(cdf=float(g@v),cdf_fd=float(fd),error_cdf=abs(float(g@v)-fd),
            cuantil=float(gq@v),cuantil_fd=float(fdq),error_cuantil=abs(float(gq@v)-fdq),
            error_vs_tangente_paralela=abs(g.sum()-d.evaluar([110.13]).cdf_sigma[0]),taylor=taylor,
            ratios=[taylor[i]["resto"]/taylor[i+1]["resto"] for i in range(2)]),
        ejemplo_base=dict(cola_sobre_105=asdict(cola),cuantil_05=asdict(cuantil)),
        entorno=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__),
        sha256_fuentes_lf={path.relative_to(RAIZ).as_posix():hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
            for path in (Path(__file__),RAIZ/"quantileflow/pde.py",RAIZ/"quantileflow/distribucion_pde.py")})
    (salida/"verificacion.json").write_text(json.dumps(informe,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    fig,axs = plt.subplots(2,3,figsize=(15,8),layout="constrained")
    xs = np.linspace(75.013,125.013,501)
    for etiqueta,modelo in modelos:
        m = modelo.evaluar(xs)
        axs[0,0].plot(xs,m.pdf,label=etiqueta)
        axs[0,2].plot(xs,m.cdf,label=etiqueta)
    axs[0,0].set(title="PDF terminal Q por escenario",xlabel="Precio terminal",ylabel="Densidad")
    axs[0,0].legend(fontsize=8)
    m = base.evaluar(xs)
    for vals,label in ((m.pdf_spot,"spot +1: ∂PDF/∂S₀"),(m.pdf_sigma*.01,"IV +1 pp"),
                       (-m.pdf_plazo/365,"un día transcurrido")):
        axs[0,1].plot(xs,vals,label=label)
    axs[0,1].axhline(0,color="gray",lw=.5)
    axs[0,1].set(title="Cambio lineal de PDF (con signo)",xlabel="Precio terminal",ylabel="Cambio de densidad")
    axs[0,1].legend(fontsize=8)
    axs[0,2].axvline(105,color="gray",ls="--",lw=.7)
    axs[0,2].set(title="CDF y umbral fijo 105",xlabel="Precio terminal",ylabel="P_Q(S_T ≤ x)")
    tq = pd.DataFrame(cuantiles)
    for alpha in (.05,.5,.95):
        sub = tq[(tq.sigma==.25)&(tq.alpha==alpha)]
        axs[1,0].plot(sub.dias,sub.precio,"o-",label=f"cuantil {alpha:.0%}")
    axs[1,0].set(title="Cuantiles por plazo · σ=25 %",xlabel="Días restantes",ylabel="Precio terminal")
    axs[1,0].legend(fontsize=8)
    spots = np.linspace(90,110,81)
    fijo = 1-base.evaluar(105*100/spots).cdf
    axs[1,1].plot(spots,fijo,label="strike fijo 105")
    axs[1,1].plot(spots,np.full_like(spots,base.probabilidad_retorno(.05).probabilidad),label="retorno +5 %")
    axs[1,1].set(title="Dos eventos diferentes",xlabel="Spot actual",ylabel="Probabilidad Q de superar umbral")
    axs[1,1].legend(fontsize=8)
    g = base.gradiente_vol_cdf(105)
    axs[1,2].plot(base.y,g/base.h)
    axs[1,2].axhline(0,color="gray",lw=.5)
    axs[1,2].set(title="Kernel adjunto de CDF en 105",xlabel="y = log(S/S₀)",ylabel="Sensibilidad a σ(y)",xlim=(-.4,.4))
    fig.suptitle("QuantileFlow · sensibilidad de distribuciones Q · escenarios sintéticos · presupuesto $0")
    fig.savefig(salida/"sensibilidad_distribucion.png",dpi=160)
    plt.close(fig)
    print(json.dumps({"maximos":informe["maximos"],"adjunto":informe["adjunto"],"escenarios":escenarios},indent=2))


if __name__ == "__main__":
    main()
