"""Transporte en una dimensión y reducción funcional de cuantiles.

En una dimensión, la distancia de Wasserstein de orden ``p`` entre dos
distribuciones se calcula directamente sobre sus funciones cuantil:

    W_p^p(Q_t, Q_{t-1}) = int_0^1 |x_t(u) - x_{t-1}(u)|^p du,

y el mapa de transporte óptimo es el reordenamiento monótono
``T = F_t^{-1} o F_{t-1}``. Las versiones recortadas integran solo sobre el
rango de ``u`` con soporte fiable y deben reportarse como tales.
"""
from __future__ import annotations

import numpy as np


def pesos_trapecio(u):
    """Pesos de cuadratura trapezoidal para una malla creciente ``u``."""
    u = np.asarray(u, dtype=float)
    w = np.zeros_like(u)
    du = np.diff(u)
    w[:-1] += 0.5 * du
    w[1:] += 0.5 * du
    return w


def _mascara(u, rango):
    if rango is None:
        return np.ones_like(u, dtype=bool)
    return (u >= rango[0] - 1e-12) & (u <= rango[1] + 1e-12)


def distancia_wasserstein(xa, xb, u, p=2, rango=None, normalizar_rango=False):
    """``W_p`` entre funciones cuantil muestreadas en la malla ``u``.

    ``rango=(u_lo, u_hi)`` calcula la versión recortada. Con
    ``normalizar_rango=True`` se divide por la longitud del rango (promedio en
    lugar de integral), lo que facilita comparar recortes distintos.
    """
    u = np.asarray(u, dtype=float)
    m = _mascara(u, rango)
    uu = u[m]
    dif = np.abs(np.asarray(xa)[..., m] - np.asarray(xb)[..., m]) ** p
    w = pesos_trapecio(uu)
    integral = np.sum(dif * w, axis=-1)
    if normalizar_rango:
        integral = integral / (uu[-1] - uu[0])
    return integral ** (1.0 / p)


def cambios_firmados(xa, xb):
    """``x_t(u) - x_{t-1}(u)``: negativo en u < 1/2 indica una cola izquierda más larga."""
    return np.asarray(xa) - np.asarray(xb)


def es_monotona(x, eje=-1):
    return bool(np.all(np.diff(x, axis=eje) >= -1e-12))


def reordenar(x, eje=-1):
    """Reordenamiento creciente (Chernozhukov, Fernández-Val y Galichon, 2010).

    Convierte una aproximación con cruces en una función cuantil válida y no
    aumenta la distancia L^p a la función verdadera.
    """
    return np.sort(x, axis=eje)


class ComponentesFuncionales:
    """PCA funcional de funciones cuantil centradas, con cuadratura trapezoidal.

    Se ajusta solo con la muestra de entrenamiento; ``transformar`` proyecta
    observaciones nuevas sin reestimar la media ni las autofunciones.
    """

    def __init__(self, n_componentes=3):
        self.n = n_componentes

    def ajustar(self, X, u):
        X = np.asarray(X, dtype=float)
        self.u = np.asarray(u, dtype=float)
        self.w = pesos_trapecio(self.u)
        self.media = X.mean(axis=0)
        Xc = (X - self.media) * np.sqrt(self.w)
        cov = Xc.T @ Xc / (X.shape[0] - 1)
        valores, vectores = np.linalg.eigh(cov)
        orden = np.argsort(valores)[::-1]
        valores = np.maximum(valores[orden], 0.0)
        vectores = vectores[:, orden]
        # Autofunciones ortonormales en L2(du): phi = v / sqrt(w).
        self.autofunciones = (vectores / np.sqrt(self.w)[:, None])[:, : self.n]
        # Signo convencional: valor positivo en la cola derecha.
        signo = np.sign(self.autofunciones[-1, :])
        signo[signo == 0] = 1.0
        self.autofunciones *= signo
        self.varianzas = valores
        self.proporcion = valores / valores.sum()
        return self

    def transformar(self, X):
        Xc = np.asarray(X, dtype=float) - self.media
        return (Xc * self.w) @ self.autofunciones

    def reconstruir(self, puntajes, asegurar_orden=True):
        X = self.media + np.asarray(puntajes) @ self.autofunciones.T
        return reordenar(X) if asegurar_orden else X
