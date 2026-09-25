"""Pronósticos físicos P: regresión cuantílica regularizada y corrección de cruces.

Las variables derivadas de Q entran como regresores; el objetivo es el
rendimiento efectivamente realizado después de cada snapshot. Ninguna salida de
Q se etiqueta como probabilidad física por decreto.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from .transporte import reordenar


def regresion_cuantilica(X, y, tau, lam=0.0):
    """Minimiza ``sum rho_tau(y - X b) + lam * sum_{j>=1} |b_j|`` como programa lineal.

    ``X`` debe incluir la columna de unos en la posición 0 (no penalizada).
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = X.shape
    # Variables: [b+ (p), b- (p), u+ (n), u- (n)] con y - X(b+ - b-) = u+ - u-
    pen = np.full(p, lam)
    pen[0] = 0.0
    c = np.concatenate([pen, pen, np.full(n, tau), np.full(n, 1.0 - tau)])
    A_eq = np.hstack([X, -X, np.eye(n), -np.eye(n)])
    sol = linprog(c, A_eq=A_eq, b_eq=y, bounds=[(0, None)] * (2 * p + 2 * n), method="highs")
    if not sol.success:
        raise RuntimeError(sol.message)
    return sol.x[:p] - sol.x[p:2 * p]


def predecir_cuantiles(X, coeficientes, corregir_cruces=True):
    """Matriz (n, n_tau) de cuantiles; opcionalmente reordenada para evitar cruces."""
    Q = np.asarray(X, dtype=float) @ np.asarray(coeficientes, dtype=float).T
    return reordenar(Q, eje=1) if corregir_cruces else Q
