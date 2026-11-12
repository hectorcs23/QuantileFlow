"""Tangentes, adjuntos, CDF inversa, reconstrucción y referencia lognormal."""
import numpy as np
import pytest
from scipy.stats import norm

from quantileflow.distribucion_pde import resolver_distribucion


@pytest.mark.parametrize("dias",[7,30,90])
def test_contra_distribucion_lognormal_y_derivadas(dias):
    t, s0, sigma, mu = dias/365,100.,.25,.04-.013-.25**2/2
    d = resolver_distribucion(s0,t,.04,.013,sigma,nodos=3201,pasos=2400)
    xs = np.array([95.13,100.13,105.13])
    a = d.evaluar(xs)
    std = sigma*np.sqrt(t)
    z = (np.log(xs/s0)-mu*t)/std
    pdf = norm.pdf(z)/(xs*std)
    zs, zt = np.sqrt(t)-z/sigma,-mu/std-z/(2*t)
    assert np.max(abs(a.pdf-pdf)) < .00008
    assert np.max(abs(a.cdf-norm.cdf(z))) < .00012
    assert np.max(abs(a.cdf_spot+norm.pdf(z)/(s0*std))) < .00008
    assert np.max(abs(a.cdf_sigma-norm.pdf(z)*zs)) < .0015
    assert np.max(abs(a.cdf_plazo-norm.pdf(z)*zt)) < .013
    assert np.max(abs(a.pdf_sigma-pdf*(-z*zs-1/sigma))) < .001
    assert np.max(abs(a.pdf_plazo-pdf*(-z*zt-1/(2*t)))) < .014
    assert np.max(abs(a.pdf_spot-pdf*z/(s0*std))) < .00025
    for alpha in (.05,.5,.95):
        c = d.cuantil(alpha)
        za = norm.ppf(alpha)
        q = s0*np.exp(mu*t+sigma*np.sqrt(t)*za)
        assert abs(c.precio-q) < .008
        assert abs(c.sensibilidad_sigma-q*(-sigma*t+np.sqrt(t)*za)) < .03
        assert abs(c.sensibilidad_plazo-q*(mu+sigma*za/(2*np.sqrt(t)))) < .15
        assert c.sensibilidad_spot == pytest.approx(c.precio/s0)


@pytest.mark.parametrize("campo,atributo,epsilon",[("spot","spot",1e-4),
    ("volatilidad","sigma",1e-5),("plazo","plazo",1e-6)])
def test_tangentes_pdf_cdf_y_cuantiles_por_perturbacion(campo,atributo,epsilon):
    p = dict(spot=100.,plazo=30/365,tasa=.04,q=.013,volatilidad=.25,nodos=401,pasos=250)
    d = resolver_distribucion(**p)
    mas = resolver_distribucion(**(p | {campo:p[campo]+epsilon}))
    menos = resolver_distribucion(**(p | {campo:p[campo]-epsilon}))
    xs = [95.13,100.13,105.13]
    a, b, c = d.evaluar(xs),mas.evaluar(xs),menos.evaluar(xs)
    for variable in ("pdf","cdf"):
        fd = (getattr(b,variable)-getattr(c,variable))/(2*epsilon)
        np.testing.assert_allclose(fd,getattr(a,f"{variable}_{atributo}"),rtol=2e-6,atol=2e-8)
    for alpha in (.05,.5,.95):
        fd = (mas.cuantil(alpha).precio-menos.cuantil(alpha).precio)/(2*epsilon)
        assert fd == pytest.approx(getattr(d.cuantil(alpha),f"sensibilidad_{atributo}"),rel=3e-7,abs=3e-6)


def test_adjunto_espacial_cdf_cuantil_taylor_y_tangente_paralela():
    y = np.linspace(-1.5,1.5,301)
    sigma, v = .25+.025*np.tanh(3*y),.5+.3*np.cos(4*y)
    p = dict(spot=100,plazo=60/365,tasa=.04,q=.013,nodos=301,pasos=180)
    d = resolver_distribucion(**p,volatilidad=sigma)
    x, alpha, h = 110.13,.05,1e-5
    g = d.gradiente_vol_cdf(x)
    assert g.sum() == pytest.approx(d.evaluar([x]).cdf_sigma[0],rel=1e-9,abs=1e-10)
    gq = d.gradiente_vol_cuantil(alpha)
    assert gq.sum() == pytest.approx(d.cuantil(alpha).sensibilidad_sigma,rel=1e-9)
    mas = resolver_distribucion(**p,volatilidad=sigma+h*v)
    menos = resolver_distribucion(**p,volatilidad=sigma-h*v)
    fd = (mas.evaluar([x]).cdf[0]-menos.evaluar([x]).cdf[0])/(2*h)
    assert g@v == pytest.approx(fd,rel=1e-7)
    fdq = (mas.cuantil(alpha).precio-menos.cuantil(alpha).precio)/(2*h)
    assert gq@v == pytest.approx(fdq,rel=2e-7)
    restos = []
    for h in (.002,.001,.0005):
        nuevo = resolver_distribucion(**p,volatilidad=sigma+h*v).evaluar([x]).cdf[0]
        restos.append(abs(nuevo-d.evaluar([x]).cdf[0]-h*(g@v)))
    assert 3.8 < restos[0]/restos[1] < 4.2
    assert 3.8 < restos[1]/restos[2] < 4.2


def test_reconstruccion_positiva_normalizada_y_complemento_colas():
    d = resolver_distribucion(100,90/365,.04,.013,.25,nodos=401,pasos=500)
    nudos = np.r_[d.y[0]-d.h,d.y,d.y[-1]+d.h]
    py = np.r_[0,d.pesos/d.h,0]
    assert np.trapezoid(py,nudos) == pytest.approx(1,abs=5e-13)
    xs = 100*np.exp(np.linspace(-1.6,1.6,2001))
    m = d.evaluar(xs)
    assert m.pdf.min() >= 0
    assert m.cdf[0] == 0 and m.cdf[-1] == 1
    assert np.diff(m.cdf).min() > -5e-15
    assert d.error_masa_pre_normalizacion < 1e-10
    assert d.error_masa_tangentes < 1e-12
    for alpha in (.01,.05,.5,.95,.99):
        q = d.cuantil(alpha)
        assert d.evaluar([q.precio]).cdf[0] == pytest.approx(alpha,abs=1e-13)
    abajo, arriba = d.probabilidad_cola(95),d.probabilidad_cola(95,False)
    assert abajo.probabilidad+arriba.probabilidad == pytest.approx(1)
    assert abajo.sensibilidad_sigma == -arriba.sensibilidad_sigma
    assert abajo.sensibilidad_plazo == -arriba.sensibilidad_plazo
    assert abajo.sensibilidad_spot == -arriba.sensibilidad_spot
    for x in (-1,0,100*np.exp(2)):
        assert np.all(d.gradiente_vol_cdf(x) == 0)


def test_kinks_pdf_solo_spot_y_cuantiles_mal_condicionados():
    d = resolver_distribucion(100,30/365,.04,.013,.25,nodos=401,pasos=250)
    m = d.evaluar([100,100.13])
    assert not m.pdf_spot_diferenciable[0] and np.isnan(m.pdf_spot[0])
    assert m.pdf_spot_diferenciable[1] and np.isfinite(m.pdf_spot[1])
    assert np.all(np.isfinite(m.cdf_spot))
    with pytest.raises(ValueError,match="condicionado"):
        d.cuantil(.05,densidad_minima=1000)
    with pytest.raises(ValueError,match="condicionado"):
        d.cuantil(1e-15)


@pytest.mark.parametrize("alpha",[0,1,-.5,float("nan")])
def test_probabilidad_cuantil_invalida(alpha):
    d = resolver_distribucion(100,30/365,.04,.013,.25,nodos=101,pasos=20)
    with pytest.raises(ValueError):
        d.cuantil(alpha)


def test_umbrales_invalidos():
    d = resolver_distribucion(100,30/365,.04,.013,.25,nodos=101,pasos=20)
    for xs in ([],[float("nan")],[[100]]):
        with pytest.raises(ValueError):
            d.evaluar(xs)
    with pytest.raises(ValueError):
        d.gradiente_vol_cdf(float("inf"))
    assert d.evaluar([np.nextafter(0.,1.)]).cdf[0] == 0


def test_refinar_malla_para_derivada_pdf_spot():
    xs = np.array([95.13,100.13,105.13])
    t,sigma = 7/365,.25
    std = sigma*np.sqrt(t)
    z = (np.log(xs/100)-(.04-.013-sigma**2/2)*t)/std
    exacta = norm.pdf(z)/(xs*std)*z/(100*std)
    errores = []
    for n in (401,3201):
        d = resolver_distribucion(100,t,.04,.013,sigma,nodos=n,pasos=2400)
        errores.append(np.max(abs(d.evaluar(xs).pdf_spot-exacta)))
    assert errores[-1] < errores[0]/4


def test_umbrales_relativos_invariantes_y_masa_de_derivadas_cero():
    p = dict(plazo=30/365,tasa=.04,q=.013,volatilidad=.25,nodos=401,pasos=200)
    a,b = resolver_distribucion(100,**p),resolver_distribucion(110,**p)
    for ret in (-.05,.05):
        cola = a.probabilidad_retorno(ret)
        assert cola.sensibilidad_spot == 0
        assert cola.probabilidad == pytest.approx(b.probabilidad_retorno(ret).probabilidad,abs=1e-14)
    assert a.probabilidad_cola(105).probabilidad != pytest.approx(b.probabilidad_cola(105).probabilidad)
    nudos = np.r_[a.y[0]-a.h,a.y,a.y[-1]+a.h]
    medios = (nudos[1:]+nudos[:-1])/2
    xs = 100*np.exp(medios)
    assert abs(np.sum(a.evaluar(xs).pdf_spot*xs*a.h)) < 1e-12
    xs = 100*np.exp(nudos)
    m = a.evaluar(xs)
    for derivada in (m.pdf_sigma,m.pdf_plazo):
        assert abs(np.trapezoid(derivada*xs,nudos)) < 1e-12


def test_no_modifica_ni_comparte_vector_sigma_del_usuario():
    sigma = np.full(101,.25)
    d = resolver_distribucion(100,30/365,.04,.013,sigma,nodos=101,pasos=20)
    assert sigma.flags.writeable
    sigma[:] = .30
    assert np.all(d.sigma == .25)
    assert not d.pesos.flags.writeable
