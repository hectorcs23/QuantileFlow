"""Detección de cambios de régimen: BOCPD (Adams y MacKay, 2007) y umbral simple.

BOCPD mantiene la distribución posterior de la *longitud de corrida* ``r_t``
(sesiones desde el último cambio). Con probabilidad de riesgo ``H`` por sesión:

    P(r_t = r_{t-1} + 1, x_{1:t}) = P(r_{t-1}, x_{1:t-1}) * pi_t^{(r)} * (1 - H)
    P(r_t = 0,           x_{1:t}) = sum_r P(r_{t-1}, x_{1:t-1}) * pi_t^{(r)} * H

donde ``pi_t^{(r)}`` es la predictiva de ``x_t`` con los datos de la corrida.
Se usa una previa Normal–Gamma inversa, cuya predictiva es t de Student.

Una probabilidad alta de cambio dice que los errores o factores recientes se
comportan distinto de lo aprendido; no es una probabilidad de caída del precio.
"""
from __future__ import annotations

import numpy as np
from scipy.special import logsumexp
from scipy.stats import t as t_student


def bocpd(x, riesgo=1 / 100, mu0=0.0, kappa0=1.0, alfa0=1.0, beta0=1.0):
    """Devuelve la matriz ``R[t, r] = P(r_t = r | x_{1:t})`` de tamaño (T+1, T+1)."""
    x = np.asarray(x, dtype=float)
    T = len(x)
    log_R = np.full((T + 1, T + 1), -np.inf)
    log_R[0, 0] = 0.0
    mu = np.array([mu0])
    kappa = np.array([kappa0])
    alfa = np.array([alfa0])
    beta = np.array([beta0])
    log_h, log_1mh = np.log(riesgo), np.log1p(-riesgo)
    for t in range(T):
        escala = np.sqrt(beta * (kappa + 1.0) / (alfa * kappa))
        log_pred = t_student.logpdf(x[t], df=2.0 * alfa, loc=mu, scale=escala)
        previo = log_R[t, : t + 1]
        log_R[t + 1, 1 : t + 2] = previo + log_pred + log_1mh
        log_R[t + 1, 0] = logsumexp(previo + log_pred + log_h)
        log_R[t + 1, : t + 2] -= logsumexp(log_R[t + 1, : t + 2])
        mu_n = (kappa * mu + x[t]) / (kappa + 1.0)
        beta_n = beta + kappa * (x[t] - mu) ** 2 / (2.0 * (kappa + 1.0))
        mu = np.concatenate([[mu0], mu_n])
        kappa = np.concatenate([[kappa0], kappa + 1.0])
        alfa = np.concatenate([[alfa0], alfa + 0.5])
        beta = np.concatenate([[beta0], beta_n])
    return np.exp(log_R)


def resumen_corrida(R):
    """Longitud de corrida más probable y probabilidad de corrida corta (< 10)."""
    mapa = np.argmax(R, axis=1)
    corta = R[:, :10].sum(axis=1)
    return mapa, corta


def detector_umbral(z, umbral=3.0, ventana=5, minimo=2):
    """Alarma cuando al menos ``minimo`` de los últimos ``ventana`` |z| superan el umbral."""
    excede = (np.abs(np.asarray(z, dtype=float)) > umbral).astype(int)
    conteo = np.convolve(excede, np.ones(ventana, dtype=int), mode="full")[: len(excede)]
    return conteo >= minimo
