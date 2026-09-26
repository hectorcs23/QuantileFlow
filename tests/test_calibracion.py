"""Conformal adaptativo: la cota se comprueba en cada prefijo, con secuencias límite y aleatorias.

Cota (``h`` = horizonte, ``N`` = errores evaluados):
``|media(err) - alfa| <= (max(alfa, 1 - alfa) + h * gamma) / (gamma * N)`` y
``alfa_t`` en ``[-h*gamma*(1 - alfa), 1 + h*gamma*alfa]``.
"""
import numpy as np
import pytest

from quantileflow import calibracion as cb


def _comprobar_cota(y, prediccion, alfa, gamma, horizonte=1, ventana=100, minimo=20):
    inferior, superior, errores, alfas = cb.conformal_adaptativo(
        y, prediccion, alfa=alfa, gamma=gamma, ventana=ventana, horizonte=horizonte,
        minimo_calibracion=minimo)
    e = errores[np.isfinite(errores)]
    assert len(e) > 0
    n = np.arange(1, len(e) + 1)
    desvio = np.abs(np.cumsum(e) / n - alfa)
    cota = cb.cota_conformal_adaptativo(alfa, gamma, n, horizonte)
    assert np.all(desvio <= cota + 1e-12), f"prefijo {int(np.argmax(desvio - cota)) + 1} viola la cota"
    a = alfas[np.isfinite(alfas)]
    assert a.max() <= 1.0 + horizonte * gamma * alfa + 1e-12
    assert a.min() >= -horizonte * gamma * (1.0 - alfa) - 1e-12
    return inferior, superior, errores, alfas


PARAMETROS = [(0.1, 0.01, 1), (0.1, 0.01, 5), (0.05, 0.05, 1), (0.5, 0.2, 3), (0.01, 1.0, 1),
              (0.99, 0.05, 2), (0.1, 0.05, 20)]


# --- Extremos del cuantil ------------------------------------------------------

def test_cuantil_conformal_extremos_y_estadistico_de_orden():
    s = np.arange(1.0, 101.0)
    assert cb.cuantil_conformal(s, 1.0) == -np.inf  # conjunto vacío
    assert cb.cuantil_conformal(s, 1.7) == -np.inf
    assert cb.cuantil_conformal(s, 0.0) == np.inf  # conjunto completo
    assert cb.cuantil_conformal(s, -0.3) == np.inf
    assert cb.cuantil_conformal([], 0.1) == np.inf
    assert cb.cuantil_conformal(s[:5], 0.1) == np.inf  # ceil(6 * 0.9) = 6 > 5
    assert cb.cuantil_conformal(s, 0.1) == 91.0  # ceil(101 * 0.9) = 91


def test_cobertura_de_muestra_finita_es_la_nominal():
    # Con puntajes intercambiables y continuos, P(s_{n+1} <= q) = ceil((n+1)(1-alfa)) / (n+1).
    rng = np.random.default_rng(0)
    n, alfa, reps = 20, 0.1, 20000
    s = rng.exponential(size=(reps, n + 1))
    q = np.array([cb.cuantil_conformal(fila[:n], alfa) for fila in s])
    assert abs(np.mean(s[:, n] <= q) - 19 / 21) < 0.006


# --- Secuencias límite -----------------------------------------------------------

@pytest.mark.parametrize("alfa,gamma,h", PARAMETROS)
def test_puntajes_nulos_y_empates(alfa, gamma, h):
    """y == prediccion: todos los puntajes empatan en 0. Antes alfa_t crecía sin límite."""
    n = 1500
    inferior, superior, errores, alfas = _comprobar_cota(np.zeros(n), np.zeros(n), alfa, gamma, h)
    vacio = (inferior == np.inf) & (superior == -np.inf)
    if (1.0 - alfa) / (gamma * alfa) < n / 2:  # alfa_t alcanza 1 dentro de la muestra
        assert vacio.any()
        assert np.all(errores[vacio] == 1.0)
    _comprobar_cota(np.full(n, 3.0), np.full(n, 2.0), alfa, gamma, h)  # empates en 1


@pytest.mark.parametrize("alfa,gamma,h", PARAMETROS)
def test_puntajes_siempre_crecientes(alfa, gamma, h):
    """Cada puntaje supera a todos los anteriores: solo el conjunto completo cubre."""
    n = 1200
    y = np.arange(n, dtype=float) ** 1.5
    _, superior, errores, _ = _comprobar_cota(y, np.zeros(n), alfa, gamma, h)
    completo = superior == np.inf
    assert np.all(errores[completo & np.isfinite(errores)] == 0.0)


@pytest.mark.parametrize("alfa,gamma,h", PARAMETROS)
def test_alternancia_y_cambio_brusco(alfa, gamma, h):
    n = 1200
    alterna = np.where(np.arange(n) % 2 == 0, 0.0, 1e6)
    _comprobar_cota(alterna, np.zeros(n), alfa, gamma, h)
    brusco = np.where(np.arange(n) < 600, 0.0, 1e3) + np.arange(n) * 1e-9
    _comprobar_cota(brusco, np.zeros(n), alfa, gamma, h)


def _adversario(n, alfa, gamma, h, fallar, ventana=40, minimo=10):
    """Elige cada y[t] viendo el intervalo ya emitido para t: fuera (fallar) o dentro."""
    y = np.full(n, np.nan)
    pred = np.zeros(n)
    for t in range(n):
        prefijo = np.append(y[:t], np.nan)
        inf, sup, _, _ = cb.conformal_adaptativo(prefijo, pred[:t + 1], alfa=alfa, gamma=gamma,
                                                 ventana=ventana, horizonte=h,
                                                 minimo_calibracion=minimo)
        lo, hi = inf[t], sup[t]
        if not np.isfinite(lo) and not np.isfinite(hi):
            y[t] = 0.0  # sin intervalo, vacío o completo: el resultado no depende de y
        elif fallar:
            y[t] = hi + 1.0
        else:
            y[t] = 0.5 * (lo + hi)
    return y, pred


@pytest.mark.parametrize("fallar", [True, False])
@pytest.mark.parametrize("alfa,gamma,h", [(0.1, 0.05, 1), (0.1, 0.05, 4), (0.3, 0.5, 2)])
def test_adversario_que_ve_el_intervalo(alfa, gamma, h, fallar):
    n = 300
    y, pred = _adversario(n, alfa, gamma, h, fallar)
    _comprobar_cota(y, pred, alfa, gamma, h, ventana=40, minimo=10)


# --- Datos aleatorios, huecos y retrasos -----------------------------------------

@pytest.mark.parametrize("semilla", range(6))
@pytest.mark.parametrize("alfa,gamma,h", PARAMETROS)
def test_datos_aleatorios_con_cambios_de_regimen(semilla, alfa, gamma, h):
    rng = np.random.default_rng(semilla)
    n = 1500
    escala = np.repeat(rng.choice([0.3, 1.0, 4.0], size=6), n // 6)
    y = rng.standard_t(3, size=n) * escala
    prediccion = 0.2 * np.sin(np.arange(n) / 40.0)
    _comprobar_cota(y, prediccion, alfa, gamma, h)


def test_huecos_no_cuentan_como_error_ni_calibran():
    rng = np.random.default_rng(9)
    n, alfa, gamma, h = 2000, 0.1, 0.02, 3
    y = rng.normal(size=n) * np.where(np.arange(n) < 1000, 1.0, 2.0)
    prediccion = np.zeros(n)
    y[rng.choice(n, 200, replace=False)] = np.nan
    prediccion[rng.choice(n, 50, replace=False)] = np.nan
    inferior, _, errores, _ = _comprobar_cota(y, prediccion, alfa, gamma, h)
    assert np.all(np.isnan(errores[np.isnan(y)]))
    assert np.all(np.isnan(inferior[np.isnan(prediccion)]))


def test_gamma_cero_no_promete_cota():
    """Nivel fijo: la tasa puede quedar lejos de alfa (aquí nunca hay error)."""
    n = 800
    _, _, errores, alfas = cb.conformal_adaptativo(np.zeros(n), np.zeros(n), alfa=0.1, gamma=0.0,
                                                   ventana=100, minimo_calibracion=20)
    assert np.nanmean(errores) == 0.0
    assert np.all(alfas[np.isfinite(alfas)] == 0.1)
