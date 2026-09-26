"""Reglas de puntuación, diagnósticos de calibración y conformal adaptativo.

* Pinball (cuantílica): ``rho_tau(e) = e * (tau - 1{e < 0})`` con ``e = y - q``.
* CRPS: ``int (F(z) - 1{y <= z})^2 dz = 2 int_0^1 rho_tau(y - F^{-1}(tau)) dtau``.
* Brier: ``mean((p - o)^2)`` para eventos binarios.

El conformal adaptativo (Gibbs y Candès, 2021) actualiza el nivel efectivo

    alfa_{t+1} = alfa_t + gamma * (alfa - err_t).

Con ``gamma > 0`` y retroalimentación con retraso ``h`` (horizonte), para
**cualquier** secuencia se cumple, tras ``N`` intervalos evaluados,

    |media(err) - alfa| <= (max(alfa, 1 - alfa) + h * gamma) / (gamma * N),

siempre que ``alfa_t >= 1`` produzca el conjunto vacío (error seguro) y
``alfa_t <= 0`` el conjunto completo. Así ``alfa_t`` queda en
``[-h*gamma*(1 - alfa), 1 + h*gamma*alfa]``. Con ``h = 1`` es la cota de Gibbs y
Candès. Es una cota sobre el promedio: no garantiza la cobertura de una sesión
particular ni la de cada régimen, y parte de ella puede venir de intervalos
vacíos o infinitos, que no informan. Con ``gamma = 0`` no hay cota.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm


def perdida_pinball(y, q, tau):
    e = np.asarray(y, dtype=float) - np.asarray(q, dtype=float)
    return e * (tau - (e < 0))


def crps_normal(y, mu, sigma):
    """CRPS cerrado para un pronóstico normal."""
    z = (np.asarray(y) - mu) / sigma
    return sigma * (z * (2.0 * norm.cdf(z) - 1.0) + 2.0 * norm.pdf(z) - 1.0 / np.sqrt(np.pi))


def crps_desde_cuantiles(y, cuantiles, taus):
    """Aproxima el CRPS con pronósticos cuantílicos en una malla uniforme de ``taus``."""
    cuantiles = np.asarray(cuantiles, dtype=float)
    perdidas = perdida_pinball(np.asarray(y)[..., None], cuantiles, np.asarray(taus))
    return 2.0 * perdidas.mean(axis=-1)


def brier(p, o):
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(o, dtype=float)) ** 2))


def curva_fiabilidad(p, o, n_bins=10):
    """Frecuencia observada frente a probabilidad media por intervalo de ``p``."""
    p = np.asarray(p, dtype=float)
    o = np.asarray(o, dtype=float)
    bordes = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bordes) - 1, 0, n_bins - 1)
    media_p, frecuencia, conteo = [], [], []
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        media_p.append(p[m].mean())
        frecuencia.append(o[m].mean())
        conteo.append(int(m.sum()))
    return np.array(media_p), np.array(frecuencia), np.array(conteo)


def cuantil_conformal(puntajes, alfa):
    """Umbral ``q`` del conjunto ``{y : |y - prediccion| <= q}`` de nivel ``1 - alfa``.

    Es el ``ceil((n + 1)(1 - alfa))``-ésimo puntaje ordenado (corrección de
    muestra finita). Convenciones de los extremos, necesarias para la cota del
    conformal adaptativo:

    * ``alfa >= 1`` -> ``-inf``: conjunto **vacío**, que siempre cuenta como error;
    * ``alfa <= 0``, sin puntajes o con rango mayor que ``n`` -> ``+inf``: conjunto
      completo.
    """
    puntajes = np.asarray(puntajes, dtype=float)
    if alfa >= 1.0:
        return -np.inf
    n = len(puntajes)
    if alfa <= 0.0 or n == 0:
        return np.inf
    rango = int(np.ceil((n + 1) * (1.0 - alfa)))
    if rango > n:
        return np.inf
    return float(np.partition(puntajes, rango - 1)[rango - 1])


def cota_conformal_adaptativo(alfa, gamma, n, horizonte=1):
    """Cota determinista de ``|media(err) - alfa|`` tras ``n`` intervalos evaluados."""
    return (max(alfa, 1.0 - alfa) + horizonte * gamma) / (gamma * n)


def conformal_adaptativo(y, prediccion, alfa=0.1, gamma=0.005, ventana=250, horizonte=1,
                         minimo_calibracion=30):
    """Intervalos ``prediccion ± cuantil`` con actualización ACI y retroalimentación madura.

    ``prediccion[t]`` es el pronóstico del objetivo ``y[t]`` hecho en ``t - horizonte``.
    En la sesión de decisión ``d`` solo se conocen los objetivos ``y[s]`` con
    ``s <= d``; por eso el nivel se actualiza con el error de ``y[d]`` y el
    intervalo nuevo es para ``y[d + horizonte]``. Con ``gamma = 0`` se obtiene
    conformal por ventana con nivel fijo (sin cota de largo plazo).

    Un intervalo vacío se representa con ``inferior = +inf`` y ``superior = -inf``;
    uno completo, con ``-inf`` y ``+inf``. Un objetivo o pronóstico ausente (NaN)
    no emite intervalo, no cuenta como error y no entra en la calibración. La
    cota del módulo vale con ``N`` = número de errores evaluados
    (``cota_conformal_adaptativo``).
    """
    if horizonte < 1:
        raise ValueError("horizonte debe ser al menos 1")
    y = np.asarray(y, dtype=float)
    prediccion = np.asarray(prediccion, dtype=float)
    T = len(y)
    puntajes = np.abs(y - prediccion)
    inferior = np.full(T, np.nan)
    superior = np.full(T, np.nan)
    alfas = np.full(T, np.nan)
    errores = np.full(T, np.nan)
    emitido = np.zeros(T, dtype=bool)
    a = alfa
    for d in range(T):
        if emitido[d] and np.isfinite(y[d]):
            errores[d] = float(not (inferior[d] <= y[d] <= superior[d]))
            a = a + gamma * (alfa - errores[d])
        t = d + horizonte
        if t >= T or not np.isfinite(prediccion[t]):
            continue
        disponibles = puntajes[max(0, d + 1 - ventana): d + 1]
        disponibles = disponibles[np.isfinite(disponibles)]
        if len(disponibles) < minimo_calibracion:
            continue
        q = cuantil_conformal(disponibles, a)
        inferior[t], superior[t] = prediccion[t] - q, prediccion[t] + q
        alfas[t] = a
        emitido[t] = True
    return inferior, superior, errores, alfas
