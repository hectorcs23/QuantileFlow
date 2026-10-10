"""Integral de PDF independiente, identidades, perturbaciones y convergencia."""
import numpy as np
import pytest
from scipy.integrate import quad

from quantileflow.distribucion_pde import resolver_distribucion
from quantileflow.opciones import precio_bs
from quantileflow.pde import resolver_europea


def integral_pdf(d,strike,call):
    # Reconstruir densidad desde la API pública, sin usar el integrador de payoff.
    nudos = np.r_[d.y[0]-d.h,d.y,d.y[-1]+d.h]
    xs = d.spot*np.exp(nudos)
    py = d.evaluar(xs).pdf*xs
    puntos = sorted(set([*nudos,np.clip(np.log(strike/d.spot),nudos[0],nudos[-1])]))
    def integrando(y):
        intrinseco = d.spot*np.exp(y)-strike
        return max(intrinseco if call else -intrinseco,0)*np.interp(y,nudos,py)
    return np.exp(-d.tasa*d.plazo)*sum(quad(integrando,a,b,epsabs=1e-12,epsrel=1e-12)[0]
        for a,b in zip(puntos[:-1],puntos[1:]))


@pytest.mark.parametrize("call",[True,False])
@pytest.mark.parametrize("strike",[70.,100.,130.])
def test_precio_es_integral_de_pdf_y_adapter_unico(call,strike):
    p = dict(spot=100,plazo=60/365,tasa=.04,q=.013,volatilidad=.25,nodos=301,pasos=250)
    d = resolver_distribucion(**p)
    v = d.valor_europeo(strike,call)
    assert v.precio == pytest.approx(integral_pdf(d,strike,call),abs=2e-11)
    a = resolver_europea(strike=strike,es_call=call,**p)
    assert a.precio == v.precio and a.delta == v.delta
    assert a.vega_paralela == v.vega_paralela
    assert v.error_dualidad < 1e-10
    assert v.error_residual_adjunto < 1e-10


@pytest.mark.parametrize("call",[True,False])
def test_derivadas_precio_y_densidad_por_perturbaciones(call):
    p = dict(spot=100.,plazo=60/365,tasa=.04,q=.013,volatilidad=.25,nodos=401,pasos=300)
    d = resolver_distribucion(**p)
    k, h = 104.13,.001
    v = d.valor_europeo(k,call)
    for campo,sensibilidad,paso in [("spot",v.delta,1e-4),("volatilidad",v.vega_paralela,1e-5),
        ("plazo",v.sensibilidad_plazo,1e-6),("tasa",v.rho,1e-5),("q",v.sensibilidad_q,1e-5)]:
        mas = resolver_distribucion(**(p|{campo:p[campo]+paso})).valor_europeo(k,call).precio
        menos = resolver_distribucion(**(p|{campo:p[campo]-paso})).valor_europeo(k,call).precio
        assert (mas-menos)/(2*paso) == pytest.approx(sensibilidad,rel=1e-6,abs=1e-6)
    mas,menos = d.valor_europeo(k+h,call),d.valor_europeo(k-h,call)
    assert (mas.precio-menos.precio)/(2*h) == pytest.approx(v.sensibilidad_strike,abs=1e-8)
    assert (mas.precio-2*v.precio+menos.precio)/h**2 == pytest.approx(v.curvatura_strike,abs=5e-8)
    pmas = resolver_distribucion(**(p|{"spot":100+h})).valor_europeo(k,call).precio
    pmenos = resolver_distribucion(**(p|{"spot":100-h})).valor_europeo(k,call).precio
    assert (pmas-2*v.precio+pmenos)/h**2 == pytest.approx(v.gamma,abs=2e-7)
    assert v.sensibilidad_vol_nodos.sum() == pytest.approx(v.vega_paralela,abs=2e-10)


def test_paridad_forma_por_strike_y_momento_financiero_converge():
    d = resolver_distribucion(100,90/365,.04,.013,.25,nodos=401,pasos=400)
    descuento = np.exp(-d.tasa*d.plazo)
    calls,puts = [],[]
    for k in (1.,90.,100.,110.,500.):
        c,p = d.valor_europeo(k),d.valor_europeo(k,False)
        assert c.precio-p.precio == pytest.approx(descuento*(c.media_terminal-k),abs=2e-11)
        assert c.precio >= 0 and p.precio >= 0 and c.gamma >= 0
        assert c.delta-p.delta == pytest.approx(descuento*c.media_terminal/100,abs=2e-13)
        assert c.curvatura_strike == p.curvatura_strike
        calls.append(c.precio)
        puts.append(p.precio)
    assert np.all(np.diff(calls) <= 0) and np.all(np.diff(puts) >= 0)
    errores = []
    for n,m in ((201,100),(801,1600)):
        v = resolver_distribucion(100,90/365,.04,.013,.25,nodos=n,pasos=m).valor_europeo(100)
        errores.append((abs(v.precio-float(precio_bs(100,100,90/365,.04,.013,.25))),abs(v.error_media_financiera)))
    assert errores[1][0] < errores[0][0]/8
    assert errores[1][1] < errores[0][1]/8


def test_adjunto_local_vega_campo_y_taylor():
    y = np.linspace(-1.5,1.5,301)
    s,v = .25+.025*np.tanh(3*y),.5+.3*np.cos(4*y)
    p = dict(spot=100,plazo=90/365,tasa=.04,q=.013,nodos=301,pasos=180)
    a = resolver_distribucion(**p,volatilidad=s).valor_europeo(110)
    grad = a.sensibilidad_vol_nodos@v
    h = 1e-5
    mas = resolver_distribucion(**p,volatilidad=s+h*v).valor_europeo(110).precio
    menos = resolver_distribucion(**p,volatilidad=s-h*v).valor_europeo(110).precio
    assert (mas-menos)/(2*h) == pytest.approx(grad,rel=1e-7)
    restos = [abs(resolver_distribucion(**p,volatilidad=s+h*v).valor_europeo(110).precio-a.precio-h*grad)
              for h in (.002,.001,.0005)]
    assert 3.8 < restos[0]/restos[1] < 4.2
    assert 3.8 < restos[1]/restos[2] < 4.2


@pytest.mark.parametrize("strike",[0,-1,float("nan"),float("inf")])
def test_strike_invalido(strike):
    d = resolver_distribucion(100,30/365,.04,.013,.25,nodos=101,pasos=20)
    with pytest.raises(ValueError):
        d.valor_europeo(strike)


def test_tipo_opcion_invalido():
    d = resolver_distribucion(100,30/365,.04,.013,.25,nodos=101,pasos=20)
    with pytest.raises(ValueError):
        d.valor_europeo(100,"put")
