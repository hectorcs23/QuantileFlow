"""Utilidades comunes de las figuras.

Las gráficas usan matplotlib con su estilo por defecto: una figura por gráfica,
sin cambiar rcParams, tamaños, colores ni fuentes. Los textos de las gráficas
van en inglés; el documento explica cada figura en su pie.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

SALIDA = Path(__file__).resolve().parent.parent / "figuras"


def guardar(nombre):
    """Guarda la figura actual como PNG (configuración por defecto) y la muestra."""
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / f"{nombre}.png"
    plt.savefig(ruta)
    with warnings.catch_warnings():
        # Al generar en lote el backend no es interactivo y show() no hace nada.
        warnings.simplefilter("ignore")
        plt.show()
    plt.close()
    return ruta


def segmentos(x, y0, y1):
    """Segmentos verticales como una sola serie (NaN separa cada segmento)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    xs = np.column_stack([x, x, np.full(n, np.nan)]).ravel()
    ys = np.column_stack([y0, y1, np.full(n, np.nan)]).ravel()
    return xs, ys


def varias_curvas(xs, ys):
    """Concatena varias curvas en una sola serie separada por NaN (un solo color)."""
    X, Y = [], []
    for x, y in zip(xs, ys):
        X.extend(list(x) + [np.nan])
        Y.extend(list(y) + [np.nan])
    return np.array(X), np.array(Y)
