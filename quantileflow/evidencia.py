"""Diagnósticos de evidencia: sesgo de selección, bootstrap por bloques y particiones.

* Máximo Sharpe esperado bajo la nula entre ``N`` ensayos independientes
  (Bailey y López de Prado, 2014):

      E[max SR] ~ sqrt(V[SR]) * ((1 - g) Z^{-1}(1 - 1/N) + g Z^{-1}(1 - 1/(N e))),

  con ``g`` la constante de Euler–Mascheroni.
* Sharpe probabilístico / deflactado: probabilidad de que el Sharpe verdadero
  supere un umbral, corrigiendo por asimetría y curtosis de los rendimientos.

Son diagnósticos adicionales del sesgo de selección; no certifican una ventaja.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

EULER_MASCHERONI = 0.5772156649015329


def maximo_sharpe_esperado(n_ensayos, var_sr):
    n = np.asarray(n_ensayos, dtype=float)
    g = EULER_MASCHERONI
    return np.sqrt(var_sr) * ((1.0 - g) * norm.ppf(1.0 - 1.0 / n) + g * norm.ppf(1.0 - 1.0 / (n * np.e)))


def sharpe_probabilistico(sr, sr_ref, n_obs, asimetria=0.0, curtosis=3.0):
    """PSR con ``sr`` y ``sr_ref`` por periodo (no anualizados)."""
    den = np.sqrt(1.0 - asimetria * sr + (curtosis - 1.0) / 4.0 * sr**2)
    return norm.cdf((sr - sr_ref) * np.sqrt(n_obs - 1.0) / den)


def sharpe_deflactado(sr, n_obs, n_ensayos, var_sr_ensayos, asimetria=0.0, curtosis=3.0):
    """DSR: PSR usando como umbral el máximo esperado bajo la nula."""
    umbral = maximo_sharpe_esperado(n_ensayos, var_sr_ensayos)
    return sharpe_probabilistico(sr, umbral, n_obs, asimetria, curtosis)


def bootstrap_bloques(x, largo_bloque, n_rep=2000, rng=None, estadistico=None):
    """Bootstrap de bloques móviles; conserva la dependencia dentro de cada bloque."""
    rng = np.random.default_rng(rng)
    x = np.asarray(x, dtype=float)
    n = len(x)
    k = int(np.ceil(n / largo_bloque))
    inicios = rng.integers(0, n - largo_bloque + 1, size=(n_rep, k))
    idx = (inicios[..., None] + np.arange(largo_bloque)).reshape(n_rep, -1)[:, :n]
    muestras = x[idx]
    if estadistico is None:
        return muestras.mean(axis=1)
    return np.array([estadistico(m) for m in muestras])


def particiones_walk_forward(n, inicio_prueba, tam_prueba, horizonte, embargo=0, ventana_max=None):
    """Genera pares ``(entrenamiento, prueba)`` en orden temporal, con purga.

    La etiqueta de la observación ``i`` usa rendimientos de ``(i, i + horizonte]``.
    Se purgan del entrenamiento las observaciones cuya etiqueta cruza el inicio
    del bloque de prueba, y se deja además un ``embargo`` de seguridad.
    """
    pares = []
    a = inicio_prueba
    while a < n:
        b = min(a + tam_prueba, n)
        fin_entrenamiento = a - horizonte - embargo
        ini_entrenamiento = 0 if ventana_max is None else max(0, fin_entrenamiento - ventana_max)
        if fin_entrenamiento > ini_entrenamiento:
            pares.append((np.arange(ini_entrenamiento, fin_entrenamiento), np.arange(a, b)))
        a = b
    return pares


def n_efectivo_solapado(n, horizonte):
    """Tamaño efectivo aproximado con rendimientos solapados de ``horizonte`` sesiones.

    Con autocorrelación ``1 - k/h`` inducida por el solapamiento,
    ``n_eff = n / (1 + 2 sum_{k<h} (1 - k/h)) = n / h``.
    """
    h = np.asarray(horizonte, dtype=float)
    return np.asarray(n, dtype=float) / h


def n_efectivo_activos(n_activos, correlacion_media):
    """Número efectivo de activos independientes con correlación media común."""
    n = np.asarray(n_activos, dtype=float)
    return n / (1.0 + (n - 1.0) * np.asarray(correlacion_media, dtype=float))
