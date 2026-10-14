"""Ancla de paridad estimada exclusivamente con pares de entrenamiento.

No estima spot futuro físico. El óptimo de pérdida cuadrática por banda no
maximiza necesariamente el número de pares compatibles.
"""
from dataclasses import replace
import math
import numpy as np
from quantileflow.superficies import Rebanada


def intervalos_forward(reb: Rebanada):
    if not math.isfinite(reb.D) or reb.D <= 0:
        raise ValueError("descuento inválido")
    if not all(np.isfinite(a).all() for a in (reb.K, reb.bid, reb.ask)):
        raise ValueError("datos no finitos")
    if (reb.ask <= reb.bid).any() or (reb.bid < 0).any() or (reb.K <= 0).any():
        raise ValueError("bandas inválidas")
    intervalos = []
    for K in np.unique(reb.K):
        ids = np.flatnonzero(reb.K == K)
        calls = ids[reb.es_call[ids]]
        puts = ids[~reb.es_call[ids]]
        if len(calls) > 1 or len(puts) > 1:
            raise ValueError("par duplicado")
        if len(calls) != 1 or len(puts) != 1:
            continue
        c, p = int(calls[0]), int(puts[0])
        intervalos.append((K+(reb.bid[c]-reb.ask[p])/reb.D,
                           K+(reb.ask[c]-reb.bid[p])/reb.D))
    a = np.asarray(intervalos, dtype=float).reshape(-1, 2)
    if len(a) < 2 or not np.isfinite(a).all() or (a[:, 0] <= 0).any():
        raise ValueError("se requieren al menos dos pares con intervalos positivos")
    return a


def estimar_forward(reb, peso_mid=.02):
    """Raíz única de la derivada de una pérdida convexa, por bisección.

L(F)=sum[(F-clip(F,l,u))²/h² + peso_mid*(F-mid)²/h²].
Con peso positivo la derivada es estrictamente creciente. No usa holdout,
el F inicial, IV invertidas ni inicializaciones seleccionadas por resultado.
"""
    if not math.isfinite(peso_mid) or peso_mid <= 0:
        raise ValueError("peso positivo requerido")
    a = intervalos_forward(reb)
    medio = a.mean(axis=1)
    h = (a[:, 1]-a[:, 0])/2
    if (h <= 0).any():
        raise ValueError("semiancho nulo")
    lo, hi = float(a[:, 0].min()), float(a[:, 1].max())
    for _ in range(80):
        F = (lo+hi)/2
        grad = np.sum((F-np.clip(F, a[:, 0], a[:, 1])+peso_mid*(F-medio))/h**2)
        if grad > 0:
            hi = F
        else:
            lo = F
    return (lo+hi)/2


def cambiar_forward(reb, F):
    if not math.isfinite(F) or F <= 0:
        raise ValueError("forward inválido")
    return replace(reb, F=float(F))
