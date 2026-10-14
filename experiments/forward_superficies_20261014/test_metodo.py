import math
import numpy as np
import pytest
from scipy.optimize import minimize_scalar
from quantileflow.opciones import precio_black
from quantileflow.superficies import Rebanada
from experiments.forward_superficies_20261014.metodo import intervalos_forward, estimar_forward, cambiar_forward


def reb_sintetica(F=102., referencia=100., ancho=.1):
    K = np.repeat([95., 100., 105., 110.], 2)
    calls = np.tile([True, False], 4)
    p = precio_black(F, K, .04*.1, math.exp(-.04*.1), calls)
    return Rebanada(.1, referencia, math.exp(-.04*.1), K, p-ancho, p+ancho, calls)


def test_recupera_forward_con_ancla_incorrecta():
    r = reb_sintetica()
    assert estimar_forward(r) == pytest.approx(102., abs=1e-10)
    r2 = cambiar_forward(r, 900.)
    assert estimar_forward(r2) == pytest.approx(estimar_forward(r), abs=1e-10)


def test_optimo_convexo_con_bandas_incompatibles_independiente():
    r = reb_sintetica()
    r.bid[0] += .3
    r.ask[0] += .3
    a = intervalos_forward(r)
    h = np.diff(a, axis=1).ravel()/2
    def objetivo(F):
        return np.sum(((F-np.clip(F,a[:,0],a[:,1]))/h)**2+.02*((F-a.mean(axis=1))/h)**2)
    independiente = minimize_scalar(objetivo, bounds=(a.min(),a.max()),method='bounded',options={'xatol':1e-11})
    F = estimar_forward(r)
    assert objetivo(F) <= objetivo(independiente.x)+1e-10


def test_forward_solo_ve_training_y_no_reparte_pares():
    r = reb_sintetica()
    train = Rebanada(r.T,r.F,r.D,r.K[:6],r.bid[:6],r.ask[:6],r.es_call[:6])
    esperado = estimar_forward(train)
    r.bid[6:] += 100
    r.ask[6:] += 100
    assert estimar_forward(train) == esperado


def test_rechaza_duplicados_y_bandera_mala():
    r = reb_sintetica()
    r.K[2:4] = r.K[:2]
    with pytest.raises(ValueError,match='duplicado'): estimar_forward(r)
    with pytest.raises(ValueError): cambiar_forward(r,float('nan'))
    with pytest.raises(ValueError): estimar_forward(reb_sintetica(),0)


def test_escala_y_orden_no_cambian_regla():
    r = reb_sintetica()
    ids = np.arange(len(r.K))[::-1]
    scale = 17.3
    r2 = Rebanada(r.T,scale*r.F,r.D,scale*r.K[ids],scale*r.bid[ids],scale*r.ask[ids],r.es_call[ids])
    assert estimar_forward(r2)/scale == pytest.approx(estimar_forward(r),abs=1e-10)
