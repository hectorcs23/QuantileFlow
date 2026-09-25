"""Decisión de posición: rendimiento esperado, CVaR y costos en un programa lineal.

Problema (pesos de activos riesgosos ``w``, caja implícita ``1 - sum(w)``):

    min_w  -mu' w + lam * CVaR_alfa(-w' R) + kappa' |w - w_actual|
    s.a.   w en C (presupuesto, concentración, beta, rotación)

Con escenarios ``r_s`` y la fórmula de Rockafellar y Uryasev (2000),

    CVaR_alfa(L) = min_zeta  zeta + 1/((1 - alfa) S) * sum_s (L_s - zeta)^+,

el problema es lineal. ``alfa = 0.95`` promedia el 5 % peor de las pérdidas
simuladas. El CVaR describe esa cola **bajo los escenarios supuestos**; no es un
límite garantizado de pérdida.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog


def var_cvar(perdidas, alfa=0.95):
    """VaR y CVaR empíricos de una muestra de pérdidas (pérdida = -rendimiento)."""
    L = np.sort(np.asarray(perdidas, dtype=float))
    zeta = np.quantile(L, alfa, method="higher")
    cvar = zeta + np.mean(np.maximum(L - zeta, 0.0)) / (1.0 - alfa)
    return float(zeta), float(cvar)


def optimizar_cvar(escenarios, w_actual, lam=1.0, alfa=0.95, costos=0.001, mu=None,
                   w_max=1.0, presupuesto=1.0, rotacion_max=None, betas=None, beta_max=None,
                   cvar_max=None):
    """Resuelve el programa lineal costo–riesgo–rendimiento.

    ``escenarios``: (S, n) rendimientos en exceso sobre caja al horizonte de decisión.
    ``costos``: costo proporcional por unidad de peso negociada (escalar o vector).
    Los costos se pagan con caja: ``sum(w) + costos' (compras + ventas) <= presupuesto``.
    ``cvar_max`` añade un presupuesto de riesgo explícito ``CVaR <= cvar_max``.

    Nota: con ``lam > 0`` y sin restricciones activas, el objetivo es positivamente
    homogéneo en ``w`` (duplicar la posición duplica rendimiento esperado y CVaR),
    así que la solución tiende a caja total o a la frontera de ``C``. Un
    presupuesto de riesgo explícito fija la escala de forma interpretable.
    """
    R = np.asarray(escenarios, dtype=float)
    S, n = R.shape
    w0 = np.asarray(w_actual, dtype=float)
    mu = R.mean(axis=0) if mu is None else np.asarray(mu, dtype=float)
    kappa = np.broadcast_to(np.asarray(costos, dtype=float), (n,))
    # Variables: [w (n), compras (n), ventas (n), zeta (1), z (S)]
    nv = 3 * n + 1 + S
    c = np.concatenate([-mu, kappa, kappa, [lam], np.full(S, lam / ((1.0 - alfa) * S))])

    A_eq = np.zeros((n, nv))
    A_eq[:, :n] = np.eye(n)
    A_eq[:, n:2 * n] = -np.eye(n)
    A_eq[:, 2 * n:3 * n] = np.eye(n)
    b_eq = w0

    filas, b_ub = [], []
    bloque = np.zeros((S, nv))
    bloque[:, :n] = -R
    bloque[:, 3 * n] = -1.0
    bloque[:, 3 * n + 1:] = -np.eye(S)
    filas.append(bloque)
    b_ub.append(np.zeros(S))
    presup = np.zeros((1, nv))
    presup[0, :n] = 1.0
    presup[0, n:3 * n] = np.concatenate([kappa, kappa])
    filas.append(presup)
    b_ub.append([presupuesto])
    if rotacion_max is not None:
        rot = np.zeros((1, nv))
        rot[0, n:3 * n] = 1.0
        filas.append(rot)
        b_ub.append([rotacion_max])
    if betas is not None and beta_max is not None:
        fb = np.zeros((1, nv))
        fb[0, :n] = betas
        filas.append(fb)
        b_ub.append([beta_max])
    if cvar_max is not None:
        fc = np.zeros((1, nv))
        fc[0, 3 * n] = 1.0
        fc[0, 3 * n + 1:] = 1.0 / ((1.0 - alfa) * S)
        filas.append(fc)
        b_ub.append([cvar_max])
    A_ub = np.vstack(filas)
    b_ub = np.concatenate([np.atleast_1d(b) for b in b_ub])

    w_max = np.broadcast_to(np.asarray(w_max, dtype=float), (n,))
    cotas = ([(0.0, float(wm)) for wm in w_max] + [(0.0, None)] * (2 * n)
             + [(None, None)] + [(0.0, None)] * S)
    sol = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=cotas, method="highs")
    if not sol.success:
        raise RuntimeError(f"Programa lineal sin solución: {sol.message}")
    x = sol.x
    w = x[:n]
    zeta = x[3 * n]
    cvar = zeta + x[3 * n + 1:].sum() / ((1.0 - alfa) * S)
    return {
        "w": w,
        "compras": x[n:2 * n],
        "ventas": x[2 * n:3 * n],
        "cvar": float(cvar),
        "rendimiento_esperado": float(mu @ w),
        "costo": float(kappa @ (x[n:2 * n] + x[2 * n:3 * n])),
        "objetivo": float(sol.fun),
    }
