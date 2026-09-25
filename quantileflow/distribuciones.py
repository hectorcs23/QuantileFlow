"""Distribuciones implícitas Q: extracción, controles y cuantiles.

Para calls europeas con descuento determinista ``D(t,T)``:

    q(K) = (1 / D) * d^2 C / dK^2          (Breeden–Litzenberger, 1978)
    Q(S_T <= K) = 1 + (1 / D) * dC / dK

La identidad se aplica a precios **ajustados** (una superficie sin arbitraje o
un ajuste convexo), nunca a diferencias de cotizaciones crudas.
"""
from __future__ import annotations

import numpy as np


def segunda_derivada(x, y):
    """Diferencias centrales de segundo orden en malla (posiblemente) no uniforme."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    h1 = x[1:-1] - x[:-2]
    h2 = x[2:] - x[1:-1]
    d2 = 2.0 * ((y[2:] - y[1:-1]) / h2 - (y[1:-1] - y[:-2]) / h1) / (h1 + h2)
    return x[1:-1], d2


def densidad_breeden_litzenberger(K, C, D):
    """Densidad de ``S_T`` en los strikes interiores de ``K``."""
    K_int, d2 = segunda_derivada(K, C)
    return K_int, d2 / D


def trapecio(y, x):
    """Integral por trapecios (evita depender de la versión de NumPy)."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(x)))


def controles_densidad(K, q, F, tol_masa=0.02, tol_media=0.005):
    """Controles mínimos de una densidad extraída.

    Devuelve la masa integrada, la media relativa al forward, la fracción de
    puntos negativos y si pasa los umbrales. La masa que falta suele estar en
    las colas no cubiertas por strikes; se reporta, no se inventa.
    """
    K = np.asarray(K, dtype=float)
    q = np.asarray(q, dtype=float)
    masa = trapecio(q, K)
    media = trapecio(K * q, K) / max(masa, 1e-12)
    negativos = float(np.mean(q < -1e-10))
    return {
        "masa": masa,
        "media_sobre_forward": media / F,
        "fraccion_negativa": negativos,
        "minimo": float(q.min()),
        "pasa": bool(negativos == 0.0 and abs(masa - 1.0) < tol_masa and abs(media / F - 1.0) < tol_media),
    }


def cdf_desde_densidad(x, p):
    """CDF acumulando la densidad por trapecios (sin normalizar)."""
    x = np.asarray(x, dtype=float)
    p = np.asarray(p, dtype=float)
    incrementos = 0.5 * (p[1:] + p[:-1]) * np.diff(x)
    return np.concatenate([[0.0], np.cumsum(incrementos)])


def cuantiles_desde_densidad(x, p, u, normalizar=True):
    """Cuantiles ``F^{-1}(u)`` por interpolación inversa de la CDF.

    Con ``normalizar=True`` se reparte la masa faltante de forma proporcional;
    úsese solo cuando la malla cubre las colas. La CDF se fuerza monótona.
    """
    cdf = cdf_desde_densidad(x, np.maximum(p, 0.0))
    if normalizar:
        cdf = cdf / cdf[-1]
    cdf = np.maximum.accumulate(cdf)
    # Eliminar tramos planos para que la interpolación inversa esté bien definida.
    unicos, idx = np.unique(cdf, return_index=True)
    return np.interp(u, unicos, np.asarray(x)[idx])


def soporte_identificado(K_fiables, F, x_malla, cdf_malla):
    """Rango de probabilidades ``[u_min, u_max]`` respaldado por strikes fiables.

    Más allá del strike fiable más extremo, la cola depende de la extrapolación;
    esos cuantiles se marcan como no identificados.
    """
    k_min = np.log(np.min(K_fiables) / F)
    k_max = np.log(np.max(K_fiables) / F)
    u_min = float(np.interp(k_min, x_malla, cdf_malla))
    u_max = float(np.interp(k_max, x_malla, cdf_malla))
    return u_min, u_max
