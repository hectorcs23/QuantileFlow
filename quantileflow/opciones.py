"""Valoración de opciones: Black en forma forward, griegas y árbol binomial.

Convenciones
------------
* ``F``: forward del subyacente al vencimiento; ``D``: factor de descuento D(t,T).
* ``w``: varianza implícita total, ``w = sigma**2 * T``.
* ``k``: log-moneyness relativo al forward, ``k = ln(K/F)``.
* ``es_call``: booleano (o arreglo de booleanos); ``False`` indica put.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr
from scipy.stats import norm


def _d1_d2(F, K, w):
    raiz_w = np.sqrt(np.maximum(w, 1e-300))
    d1 = (np.log(F / K) + 0.5 * w) / raiz_w
    return d1, d1 - raiz_w


def precio_black(F, K, w, D, es_call=True):
    """Precio de una opción europea con el modelo de Black (forward).

    ``C = D [F N(d1) - K N(d2)]`` y ``P = D [K N(-d2) - F N(-d1)]``.
    """
    F = np.asarray(F, dtype=float)
    K = np.asarray(K, dtype=float)
    w = np.asarray(w, dtype=float)
    d1, d2 = _d1_d2(F, K, w)
    # ndtr es la CDF normal sin la sobrecarga de scipy.stats (importa en las inversiones).
    call = D * (F * ndtr(d1) - K * ndtr(d2))
    put = D * (K * ndtr(-d2) - F * ndtr(-d1))
    return np.where(es_call, call, put)


def precio_bs(S, K, T, r, q, sigma, es_call=True):
    """Black–Scholes con rendimiento de dividendo continuo ``q``."""
    F = S * np.exp((r - q) * T)
    D = np.exp(-r * T)
    return precio_black(F, K, np.asarray(sigma) ** 2 * T, D, es_call)


def griegas_bs(S, K, T, r, q, sigma, es_call=True):
    """Delta, gamma y vega (por unidad de volatilidad) de Black–Scholes."""
    S = np.asarray(S, dtype=float)
    F = S * np.exp((r - q) * T)
    d1, _ = _d1_d2(F, K, sigma**2 * T)
    eq = np.exp(-q * T)
    delta = np.where(es_call, eq * norm.cdf(d1), eq * (norm.cdf(d1) - 1.0))
    gamma = eq * norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * eq * norm.pdf(d1) * np.sqrt(T)
    return delta, gamma, vega


def vol_implicita_black(precio, F, K, T, D, es_call=True, vol_min=1e-4, vol_max=5.0):
    """Invierte Black por bisección robusta (Brent). Devuelve NaN si no hay solución.

    Un precio fuera de los límites de no arbitraje (por ejemplo, un bid de cero)
    no tiene volatilidad implícita: se marca como NaN en vez de forzar un valor.
    """
    precio, F, K, es_call = np.broadcast_arrays(
        np.asarray(precio, float), np.asarray(F, float), np.asarray(K, float), np.asarray(es_call)
    )
    salida = np.full(precio.shape, np.nan)
    for i in np.ndindex(precio.shape):
        p, f, k, c = precio[i], F[i], K[i], bool(es_call[i])
        intrinseco = D * max(f - k, 0.0) if c else D * max(k - f, 0.0)
        cota = D * f if c else D * k
        if not (intrinseco < p < cota):
            continue

        def objetivo(s):
            return float(precio_black(f, k, s * s * T, D, c)) - p

        salida[i] = brentq(objetivo, vol_min, vol_max, xtol=1e-10)
    return salida


def binomial_crr(S, K, T, r, sigma, es_call=False, q=0.0, dividendos=(), n=500, americana=True):
    """Árbol binomial de Cox–Ross–Rubinstein con ejercicio anticipado opcional.

    ``dividendos`` es una secuencia de pares ``(t_i, monto)`` pagados en efectivo
    dentro de ``(0, T]``; se usa el modelo de dividendo "escrowed": el árbol
    evoluciona ``S* = S - VP(dividendos futuros)`` y el valor de ejercicio usa
    el precio con dividendos, ``S* + VP``.
    """
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    a = np.exp((r - q) * dt)
    p = (a - d) / (u - d)
    descuento = np.exp(-r * dt)
    divs = [(t, m) for t, m in dividendos if 0.0 < t <= T]

    def vp_dividendos(t):
        return sum(m * np.exp(-r * (ti - t)) for ti, m in divs if ti > t)

    s_estrella = S - vp_dividendos(0.0)
    j = np.arange(n + 1)
    s_final = s_estrella * u ** (n - j) * d**j
    valor = np.maximum(s_final - K, 0.0) if es_call else np.maximum(K - s_final, 0.0)
    for i in range(n - 1, -1, -1):
        valor = descuento * (p * valor[:-1] + (1.0 - p) * valor[1:])
        if americana:
            j = np.arange(i + 1)
            s_nodo = s_estrella * u ** (i - j) * d**j + vp_dividendos(i * dt)
            ejercicio = s_nodo - K if es_call else K - s_nodo
            valor = np.maximum(valor, ejercicio)
    return float(valor[0])


def prima_ejercicio_anticipado(S, K, T, r, sigma, es_call=False, q=0.0, dividendos=(), n=500):
    """Diferencia americana menos europea calculada en el mismo árbol.

    Usar el mismo árbol cancela buena parte del error de discretización, que de
    otro modo contaminaría una cantidad pequeña.
    """
    kw = dict(es_call=es_call, q=q, dividendos=dividendos, n=n)
    return binomial_crr(S, K, T, r, sigma, americana=True, **kw) - binomial_crr(
        S, K, T, r, sigma, americana=False, **kw
    )
