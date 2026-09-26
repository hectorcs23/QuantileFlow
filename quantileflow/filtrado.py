"""Filtrado causal de factores: Kalman con ruido de observación variable y EWMA.

Modelo lineal gaussiano:

    f_t = A f_{t-1} + eta_t,        eta_t ~ N(0, Q)
    y_t = H f_t + eps_t,            eps_t ~ N(0, R_t)

``R_t`` depende de la calidad de la sesión (spreads, strikes válidos, error de
ajuste): cuando la calidad cae, el filtro confía menos en la observación. Solo
se implementa el **filtro** (usa información hasta t); un suavizador que use
observaciones futuras no es válido en un backtest.
"""
from __future__ import annotations

import numpy as np


def filtro_kalman(y, A, H, Q, R, f0, P0):
    """Filtro de Kalman con ``R`` variable y observaciones faltantes (NaN).

    Parámetros
    ----------
    y : (T, m) observaciones; una fila con NaN solo ejecuta la predicción.
    R : (T, m, m) o (m, m) covarianza de observación.

    Devuelve medias y covarianzas filtradas, predicciones a un paso y
    ganancias (útiles para diagnosticar cuánto se confía en cada dato).
    """
    y = np.asarray(y, dtype=float)
    if y.ndim == 1:
        y = y[:, None]
    T = y.shape[0]
    A, H, Q = (np.atleast_2d(np.asarray(M, dtype=float)) for M in (A, H, Q))
    R = np.asarray(R, dtype=float)
    if R.ndim < 3:
        R = np.broadcast_to(np.atleast_2d(R), (T,) + np.atleast_2d(R).shape)
    n = A.shape[0]
    f = np.asarray(f0, dtype=float).reshape(n)
    P = np.atleast_2d(np.asarray(P0, dtype=float))
    medias = np.zeros((T, n))
    covs = np.zeros((T, n, n))
    predicciones = np.zeros((T, n))
    ganancias = np.zeros((T, n, y.shape[1]))
    for t in range(T):
        f = A @ f
        P = A @ P @ A.T + Q
        predicciones[t] = f
        if np.all(np.isfinite(y[t])):
            S = H @ P @ H.T + R[t]
            K = P @ H.T @ np.linalg.inv(S)
            f = f + K @ (y[t] - H @ f)
            P = (np.eye(n) - K @ H) @ P
            ganancias[t] = K
        medias[t] = f
        covs[t] = P
    return medias, covs, predicciones, ganancias


def ewma(y, lam):
    """Media exponencial causal ``m_t = lam m_{t-1} + (1 - lam) y_t``.

    Empieza en la primera observación finita: antes de ella la salida es NaN,
    nunca un valor futuro. Una observación faltante posterior conserva la media.
    """
    y = np.asarray(y, dtype=float)
    salida = np.full(y.shape, np.nan)
    m = np.nan
    for t, v in enumerate(y):
        if np.isfinite(v):
            m = v if np.isnan(m) else lam * m + (1.0 - lam) * v
        salida[t] = m
    return salida


def persistencia(y):
    """Pronóstico ingenuo causal: el último valor observado (NaN antes del primero)."""
    y = np.asarray(y, dtype=float)
    salida = np.full(y.shape, np.nan)
    ultimo = np.nan
    for t, v in enumerate(y):
        if np.isfinite(v):
            ultimo = v
        salida[t] = ultimo
    return salida
