"""Óptimos independientes, soporte y rechazo de probabilidades inválidas."""
import numpy as np
import pytest
from scipy.optimize import minimize
from estrategias.distribucion import Distribucion, desde_probabilidades, kl
from estrategias.vista import tilt_media, tilt_momentos, reponderar_cola


def referencia():
    s = np.geomspace(60., 150., 5)
    return Distribucion(s, np.array([.1, .15, .4, .2, .15]), (60., 150.), "sintético")


def optimo_directo(q, media, indices_fijos=(), pesos_fijos=()):
    # Optimización en probabilidades, independiente de la parametrización tilt.
    def objetivo(p):
        return np.sum(p * np.log(p / q.p))
    restricciones = [
        {"type": "eq", "fun": lambda p: p.sum() - 1},
        {"type": "eq", "fun": lambda p: p @ q.s / media - 1},
    ]
    if len(indices_fijos):
        restricciones.append({"type": "eq", "fun": lambda p: p[indices_fijos] - pesos_fijos})
    sol = minimize(objetivo, q.p.copy(), method="SLSQP", bounds=[(1e-12, 1)] * len(q.p),
                   constraints=restricciones, options={"ftol": 1e-13, "maxiter": 1000})
    assert sol.success, sol.message
    return q.con(sol.x, "óptimo directo")


@pytest.mark.parametrize("retorno", [-.08, .08])
def test_media_minimiza_kl_frente_a_optimizacion_directa(retorno):
    q = referencia()
    p = tilt_media(q, q.media, retorno)
    independiente = optimo_directo(q, q.media * (1 + retorno))
    assert p.media == pytest.approx(independiente.media, abs=1e-8)
    assert kl(p, q) == pytest.approx(kl(independiente, q), abs=1e-10)
    assert np.max(abs(p.p - independiente.p)) < 1e-6


def test_compensacion_de_cola_minimiza_kl_y_respeta_cada_peso_fijado():
    q = referencia()
    zona = np.flatnonzero(np.log(q.s / q.media) <= -.15)
    p = reponderar_cola(q, .8, -.15, preservar_media=True)
    independiente = optimo_directo(q, q.media, zona, .8 * q.p[zona])
    assert p.media == pytest.approx(q.media, abs=1e-8)
    assert p.p[zona] == pytest.approx(.8 * q.p[zona], abs=1e-12)
    assert kl(p, q) == pytest.approx(kl(independiente, q), abs=1e-10)


@pytest.mark.parametrize("constructor", ["directo", "helper"])
def test_negativos_materiales_rechazados_antes_de_recortar(constructor):
    q = referencia()
    p = np.array([-.1, .2, .3, .3, .2])
    with pytest.raises(ValueError, match="negativas"):
        (Distribucion if constructor == "directo" else desde_probabilidades)(
            q.s, p, q.rango_fiable, "inválido")


def test_redondeo_minimo_se_registra_y_conserva_masa():
    q = referencia()
    p = np.array([-1e-14, .2, .3, .3, .2 + 1e-14])
    d = desde_probabilidades(q.s, p, q.rango_fiable, "redondeo")
    assert d.p.min() == 0
    assert d.p.sum() == pytest.approx(1., abs=1e-15)
    assert d.detalle["masa_negativa_corregida"] == 1e-14
    directo = Distribucion(q.s, p, q.rango_fiable, "redondeo")
    assert directo.p.sum() == pytest.approx(1., abs=1e-15)
    assert directo.detalle["masa_negativa_corregida_constructor"] == 1e-14


@pytest.mark.parametrize("valor", [np.nan, np.inf, -np.inf])
def test_no_finitos_no_se_normalizan(valor):
    q = referencia()
    with pytest.raises(ValueError, match="finito"):
        desde_probabilidades(q.s, [valor, .2, .3, .3, .2], q.rango_fiable, "inválido")


def test_media_respeta_ceros_del_soporte_y_rechaza_objetivo_inaccesible():
    q = referencia().con([0, .25, .5, .25, 0], "soporte interior")
    with pytest.raises(ValueError, match="soporte"):
        tilt_media(q, q.s[-1], 0.)
    p = tilt_media(q, q.media, .01)
    assert p.p[0] == p.p[-1] == 0


def test_solo_media_por_ambas_apis_da_el_mismo_resultado():
    q = referencia()
    assert tilt_momentos(q, q.media, .03).p == pytest.approx(tilt_media(q, q.media, .03).p)


def test_cdf_que_se_cruzan_pueden_dar_ventaja_positiva_para_el_put():
    s = np.array([60., 90., 135.])
    q = Distribucion(s, [0., .8, .2], (60, 135), "Q sintética")
    p = Distribucion(s, [.1, 0., .9], (60, 135), "P sintética")
    assert p.cdf(75) > q.cdf(75)
    assert p.cdf(95) < q.cdf(95)
    assert q.precio_put(100) - p.precio_put(100) == pytest.approx(4.)
