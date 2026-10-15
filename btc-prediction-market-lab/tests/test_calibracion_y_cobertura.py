"""Calibracion sigmoide, metricas y cobertura de intervalos."""

import numpy as np
import pytest

from btclab.calibracion import (
    CalibradorSigmoide,
    ErrorCalibracion,
    brier,
    calibracion_por_grupo,
    cobertura_intervalos,
    error_calibracion_esperado,
    fiabilidad,
    log_loss,
)
from btclab.modelos import LogisticaRegularizada, logit


def datos(n=4000, semilla=7):
    rng = np.random.default_rng(semilla)
    x = rng.normal(size=(n, 2))
    p = 1.0 / (1.0 + np.exp(-(0.8 * x[:, 0] - 0.5 * x[:, 1])))
    y = (rng.random(n) < p).astype(int)
    return x, y, p


def test_brier_y_logloss_en_casos_conocidos():
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert brier([0.5, 0.5], [1, 0]) == 0.25
    assert log_loss([1.0], [1]) < 1e-9


def test_metricas_con_longitudes_incompatibles_fallan():
    with pytest.raises(ErrorCalibracion):
        brier([0.5], [1, 0])
    with pytest.raises(ErrorCalibracion):
        brier([], [])


def test_la_logistica_recupera_los_coeficientes():
    x, y, _ = datos()
    m = LogisticaRegularizada(regularizacion=1.0).ajustar(x, y)
    assert m.convergio
    assert abs(m.coeficientes[1] - 0.8) < 0.1
    assert abs(m.coeficientes[2] + 0.5) < 0.1


def test_la_logistica_rechaza_variables_faltantes():
    x, y, _ = datos(100)
    x[0, 0] = np.nan
    with pytest.raises(Exception):
        LogisticaRegularizada().ajustar(x, y)


def test_la_logistica_sin_ajustar_no_predice():
    with pytest.raises(Exception):
        LogisticaRegularizada().probabilidad(np.zeros((1, 2)))


def test_el_calibrador_corrige_una_escala_mal_puesta():
    x, y, _ = datos()
    m = LogisticaRegularizada().ajustar(x, y)
    p = m.probabilidad(x)
    # Aplastamos deliberadamente el logit por un factor 0.3.
    p_mal = 1.0 / (1.0 + np.exp(-(0.3 * logit(p))))
    antes = error_calibracion_esperado(p_mal, y)
    cal = CalibradorSigmoide().ajustar(p_mal, y)
    despues = error_calibracion_esperado(cal.calibrar(p_mal), y)
    assert despues < antes / 2
    # La pendiente recuperada debe deshacer el factor: 1/0.3 ~ 3.33
    assert abs(cal.a - 1 / 0.3) < 0.5


def test_el_calibrador_sin_ajustar_falla():
    with pytest.raises(ErrorCalibracion):
        CalibradorSigmoide().calibrar([0.5])


def test_el_calibrador_rechaza_objetivo_no_binario():
    with pytest.raises(ErrorCalibracion):
        CalibradorSigmoide().ajustar([0.5, 0.6], [0.5, 1])


def test_la_fiabilidad_avisa_de_tramos_escasos():
    p = [0.05] * 5 + [0.5] * 100
    y = [0] * 5 + [1] * 50 + [0] * 50
    tramos, avisos = fiabilidad(p, y, minimo_por_tramo=20)
    assert any("no informativo" in a for a in avisos)
    assert all(t.n > 0 for t in tramos)


def test_cobertura_de_intervalos():
    inf = [0.0] * 100
    sup = [1.0] * 100
    real = [0.5] * 95 + [2.0] * 5
    c = cobertura_intervalos(inf, sup, real, nivel_nominal=0.95)
    assert c.cobertura == 0.95
    assert c.desvio == 0.0
    assert c.ancho_medio == 1.0


def test_cobertura_detecta_intervalos_estrechos():
    inf = [0.4] * 100
    sup = [0.6] * 100
    real = [0.5] * 50 + [0.9] * 50
    c = cobertura_intervalos(inf, sup, real, nivel_nominal=0.95)
    assert c.cobertura == 0.5
    assert c.desvio < 0


def test_calibracion_por_grupo_agrupa_los_escasos():
    p = [0.5] * 100
    y = [1, 0] * 50
    grupos = ["grande"] * 90 + ["raro"] * 10
    salida, avisos = calibracion_por_grupo(p, y, grupos, minimo_por_grupo=30)
    assert "grande" in salida
    assert "raro" not in salida
    assert "agrupado_escaso" in salida
    assert any("raro" in a for a in avisos)
