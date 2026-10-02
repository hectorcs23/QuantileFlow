"""Distribuciones discretas sobre una malla logarítmica común.

Todas las distribuciones del subproyecto (la implícita ``Q`` y la vista ``P``)
viven sobre la **misma malla de precios**, geométrica y uniforme en
``x = ln(S/F)``. Esa decisión hace exactas las operaciones que necesitamos:

* esperanzas y precios de opciones son sumas finitas, no cuadraturas;
* un tilt exponencial reponderá la malla sin interpolar;
* un desplazamiento del rendimiento es un reindexado entero de la malla;
* la divergencia de Kullback–Leibler entre ``P`` y ``Q`` es finita y directa;
* la identidad ``E[(K - S)^+] = int_0^K F(s) ds`` se cumple sin error de malla.

Nada aquí normaliza masa que falte ni extrapola colas. El rango respaldado por
cotizaciones fiables viaja con la distribución (``rango_fiable``) y sirve para
acotar, más adelante, el error de cualquier estructura cuyo pago dependa de la
zona no identificada.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

TOL_MASA = 1e-6
TOL_MALLA = 1e-9


def malla_precios(F, sd_log, n=1201, anchura=6.0):
    """Malla geométrica centrada en el forward: ``F * exp(k)`` con ``k`` uniforme.

    ``sd_log`` es la desviación típica de ``ln(S_T/F)`` que se usa para fijar la
    extensión; ``anchura`` la mide en esas unidades. La malla debe cubrir la
    masa relevante: las comprobaciones de construcción avisan si no lo hace.
    """
    if not (sd_log > 0.0 and n >= 3 and anchura > 0.0):
        raise ValueError("sd_log, n y anchura deben ser positivos (n >= 3)")
    k = np.linspace(-anchura * sd_log, anchura * sd_log, int(n))
    return float(F) * np.exp(k)


@dataclass(frozen=True, eq=False)
class Distribucion:
    """Distribución discreta de ``S_T`` sobre una malla geométrica.

    ``s`` es el soporte (creciente, positivo, con paso constante en logaritmo) y
    ``p`` las probabilidades, no negativas y con suma 1. ``rango_fiable`` es el
    intervalo de precios respaldado por cotizaciones utilizables; fuera de él la
    forma de la distribución proviene de una extrapolación y no se considera
    identificada.
    """

    s: np.ndarray
    p: np.ndarray
    rango_fiable: tuple
    origen: str
    detalle: dict = field(default_factory=dict)

    def __post_init__(self):
        s = np.asarray(self.s, dtype=float)
        p = np.asarray(self.p, dtype=float)
        if s.ndim != 1 or s.shape != p.shape or len(s) < 3:
            raise ValueError("s y p deben ser vectores de la misma longitud (>= 3)")
        if not np.all(np.isfinite(s)) or not np.all(np.isfinite(p)):
            raise ValueError("s y p deben ser finitos")
        if s[0] <= 0.0 or np.any(np.diff(s) <= 0.0):
            raise ValueError("el soporte debe ser positivo y creciente")
        pasos = np.diff(np.log(s))
        if np.max(np.abs(pasos - pasos[0])) > TOL_MALLA * max(1.0, abs(pasos[0])):
            raise ValueError("el soporte debe tener paso constante en logaritmo")
        if p.min() < -TOL_MASA:
            raise ValueError(f"probabilidades negativas (mínimo {p.min():.3g})")
        if abs(p.sum() - 1.0) > 1e-8:
            raise ValueError(f"las probabilidades suman {p.sum():.8f}, no 1")
        lo, hi = float(self.rango_fiable[0]), float(self.rango_fiable[1])
        if not (lo < hi):
            raise ValueError("rango_fiable debe ser un intervalo (lo, hi) con lo < hi")
        object.__setattr__(self, "s", s)
        object.__setattr__(self, "p", np.maximum(p, 0.0))
        object.__setattr__(self, "rango_fiable", (lo, hi))

    # --- malla ---------------------------------------------------------------

    @property
    def paso_log(self):
        return float(np.log(self.s[1] / self.s[0]))

    def misma_malla(self, otra: "Distribucion"):
        return (self.s.shape == otra.s.shape
                and np.allclose(self.s, otra.s, rtol=1e-12, atol=0.0))

    def con(self, p, origen, **detalle):
        """Copia con otras probabilidades sobre la misma malla y rango fiable."""
        d = dict(self.detalle)
        d.update(detalle)
        return Distribucion(self.s, p, self.rango_fiable, origen, d)

    # --- momentos y cuantiles -------------------------------------------------

    @property
    def media(self):
        return float(self.p @ self.s)

    def momentos_log(self, referencia=None):
        """Media y desviación típica de ``ln(S_T / referencia)`` (por omisión, la media)."""
        ref = float(referencia) if referencia is not None else self.media
        x = np.log(self.s / ref)
        m = float(self.p @ x)
        v = float(self.p @ (x - m) ** 2)
        tercero = float(self.p @ (x - m) ** 3)
        sd = float(np.sqrt(max(v, 0.0)))
        asimetria = tercero / sd**3 if sd > 0.0 else float("nan")
        return {"media_log": m, "sd_log": sd, "asimetria_log": asimetria}

    @property
    def acumulada(self):
        return np.cumsum(self.p)

    def cdf(self, x):
        """``F(x) = P(S_T <= x)``, continua por la derecha."""
        idx = np.searchsorted(self.s, np.asarray(x, dtype=float), side="right")
        acum = np.concatenate([[0.0], self.acumulada])
        return acum[idx]

    def cuantil(self, u):
        """``inf{x : F(x) >= u}``; ``nan`` fuera de ``[0, 1]``."""
        u = np.atleast_1d(np.asarray(u, dtype=float))
        idx = np.searchsorted(self.acumulada, u, side="left")
        valido = (u >= 0.0) & (u <= 1.0)
        idx = np.clip(idx, 0, len(self.s) - 1)
        return np.where(valido, self.s[idx], np.nan)

    # --- precios de pagos elementales ----------------------------------------

    def esperanza(self, pago):
        """``E[g(S_T)]`` para un pago evaluado en la malla."""
        return float(self.p @ np.asarray(pago, dtype=float))

    def precio_put(self, K):
        return float(self.p @ np.maximum(float(K) - self.s, 0.0))

    def precio_call(self, K):
        return float(self.p @ np.maximum(self.s - float(K), 0.0))

    def masa_fuera(self):
        """Masa a la izquierda y a la derecha del rango respaldado por cotizaciones."""
        lo, hi = self.rango_fiable
        return float(self.p[self.s < lo].sum()), float(self.p[self.s > hi].sum())

    def resumen(self, F=None):
        izq, der = self.masa_fuera()
        base = {"origen": self.origen, "media": self.media,
                "masa_izquierda_no_fiable": izq, "masa_derecha_no_fiable": der}
        base.update(self.momentos_log(F))
        if F is not None:
            base["media_sobre_forward"] = self.media / float(F)
        return base


# ---------------------------------------------------------------------------
# Construcción
# ---------------------------------------------------------------------------


def desde_cdf(s, cdf, rango_fiable, origen, **detalle):
    """Distribución discreta a partir de una CDF **anclada** evaluada en la malla.

    La probabilidad del punto ``s_j`` es el incremento de la CDF en su celda. La
    masa que queda fuera de la malla se acumula en los extremos y se reporta en
    ``detalle``: la malla debe elegirse para que sea despreciable, porque un
    átomo en el extremo distorsiona los pagos que dependen de esa cola.
    """
    s = np.asarray(s, dtype=float)
    cdf = np.asarray(cdf, dtype=float)
    if s.shape != cdf.shape:
        raise ValueError("s y cdf deben tener la misma forma")
    caida = float(-np.min(np.diff(cdf), initial=0.0))
    if caida > 1e-10:
        raise ValueError(f"CDF decreciente (caída {caida:.3g}): la densidad sería negativa")
    bordes = np.concatenate([[s[0]], np.sqrt(s[1:] * s[:-1]), [s[-1]]])
    f_bordes = np.interp(bordes, s, cdf)
    p = np.diff(f_bordes)
    masa_izq, masa_der = float(cdf[0]), float(1.0 - cdf[-1])
    p[0] += masa_izq
    p[-1] += masa_der
    total = p.sum()
    detalle = {"masa_fuera_malla_izquierda": masa_izq, "masa_fuera_malla_derecha": masa_der,
               "suma_antes_de_normalizar": float(total), **detalle}
    return Distribucion(s, p / total, rango_fiable, origen, detalle)


def desde_probabilidades(s, p, rango_fiable, origen, tol=1e-4, **detalle):
    """Distribución a partir de pesos no negativos; normaliza y registra el ajuste."""
    p = np.maximum(np.asarray(p, dtype=float), 0.0)
    total = float(p.sum())
    if abs(total - 1.0) > tol:
        raise ValueError(f"los pesos suman {total:.6f}: fuera de la tolerancia {tol:g}")
    return Distribucion(s, p / total, rango_fiable, origen,
                        {"suma_antes_de_normalizar": total, **detalle})


def kl(p: Distribucion, q: Distribucion):
    """``KL(P || Q) = sum p ln(p/q)`` en nats; ``inf`` si ``P`` carga donde ``Q`` no.

    Mide cuánto se aparta la vista del mercado. Es el precio informativo de la
    opinión: con ``KL`` grande, la recomendación la produce la vista, no el dato.
    """
    if not p.misma_malla(q):
        raise ValueError("ambas distribuciones deben compartir la malla")
    positivos = p.p > 0.0
    if np.any(q.p[positivos] <= 0.0):
        return float("inf")
    return float(np.sum(p.p[positivos] * np.log(p.p[positivos] / q.p[positivos])))
