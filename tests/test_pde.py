"""Verificación numérica independiente: BS, perturbaciones, Taylor y dominio."""
import numpy as np
import pytest

from quantileflow.opciones import precio_bs, griegas_bs
from quantileflow.pde import resolver_europea


@pytest.mark.parametrize("es_call", [True, False])
@pytest.mark.parametrize("dias", [7, 30, 90])
def test_convergencia_bs_y_dualidad(dias, es_call):
    args = (100, 103, dias/365, .04, .013, .25, es_call)
    a = resolver_europea(*args, nodos=1601, pasos=2400)
    bs = float(precio_bs(*args))
    delta, _, vega = griegas_bs(*args)
    assert abs(a.precio-bs) < .0015
    assert abs(a.delta-delta) < .00012
    assert abs(a.vega_paralela-vega) < .015
    assert a.masas.min() >= 0
    assert a.error_masa < 2e-11
    assert a.error_dualidad < 2e-9
    assert a.error_residual_estado < 2e-12
    assert a.error_residual_adjunto < 2e-9
    assert a.masa_fronteras < 1e-20


@pytest.mark.parametrize("es_call", [True, False])
def test_adjunto_parametros_y_delta_por_perturbacion(es_call):
    p = dict(spot=100., strike=104., plazo=60/365, tasa=.04, q=.013,
             volatilidad=.25, es_call=es_call, nodos=301, pasos=120)
    a = resolver_europea(**p)
    for nombre, sensibilidad in [("spot", a.delta), ("volatilidad", a.vega_paralela),
                                 ("tasa", a.rho), ("q", a.sensibilidad_q)]:
        h = 1e-4 if nombre == "spot" else 1e-5
        arriba = resolver_europea(**(p | {nombre: p[nombre]+h})).precio
        abajo = resolver_europea(**(p | {nombre: p[nombre]-h})).precio
        assert (arriba-abajo)/(2*h) == pytest.approx(sensibilidad, rel=2e-7, abs=2e-7)


def test_adjunto_espacial_y_resto_taylor():
    n = 301
    y = np.linspace(-1.5, 1.5, n)
    sigma = .25+.025*np.tanh(3*y)
    direccion = .5+.3*np.cos(4*y)
    p = dict(spot=100, strike=110, plazo=90/365, tasa=.04, q=.01, nodos=n, pasos=160)
    a = resolver_europea(**p, volatilidad=sigma)
    gradiente = a.sensibilidad_vol_nodos@direccion
    h = 1e-5
    fd = (resolver_europea(**p, volatilidad=sigma+h*direccion).precio
          -resolver_europea(**p, volatilidad=sigma-h*direccion).precio)/(2*h)
    assert fd == pytest.approx(gradiente, rel=1e-7)
    restos = [abs(resolver_europea(**p, volatilidad=sigma+h*direccion).precio-a.precio-h*gradiente)
              for h in (.002, .001, .0005)]
    assert 3.8 < restos[0]/restos[1] < 4.2
    assert 3.8 < restos[1]/restos[2] < 4.2


def test_refinamiento_y_masa_no_garantiza_dominio_suficiente():
    args = (100, 100, 90/365, .04, .013, .45)
    bs = float(precio_bs(*args))
    gruesa = resolver_europea(*args, nodos=201, pasos=100)
    fina = resolver_europea(*args, nodos=801, pasos=1600)
    assert abs(fina.precio-bs) < abs(gruesa.precio-bs)/8
    corta = resolver_europea(*args, nodos=101, pasos=1600, semiancho=.15)
    assert corta.error_masa < 1e-10
    assert corta.masa_fronteras > .001
    assert abs(corta.precio-bs) > 1


@pytest.mark.parametrize("cambio", [dict(spot=0), dict(plazo=0), dict(volatilidad=-.2),
                                  dict(volatilidad=[.2, .3]), dict(nodos=100), dict(pasos=True),
                                  dict(tasa=float("nan")), dict(es_call="call"),
                                  dict(tasa=10., volatilidad=.01, nodos=5)])
def test_rechaza_entradas_invalidas(cambio):
    p = dict(spot=100, strike=105, plazo=30/365, tasa=.04, q=.01, volatilidad=.25)
    with pytest.raises(ValueError):
        resolver_europea(**(p | cambio))
