"""Distribuciones implícitas Q: extracción, controles y cuantiles.

Para calls europeas con descuento determinista ``D(t,T)``:

    q(K) = (1 / D) * d^2 C / dK^2          (Breeden–Litzenberger, 1978)
    Q(S_T <= K) = 1 + (1 / D) * dC / dK

La identidad se aplica a precios **ajustados** (una superficie sin arbitraje o
un ajuste convexo), nunca a diferencias de cotizaciones crudas.

Los cuantiles se devuelven con su estado: un nivel cuya cola cae fuera del
tramo respaldado queda como «no identificada» (NaN), y una densidad negativa
invalida el cálculo. No se normaliza la masa ni se recortan negativos.
"""
from __future__ import annotations

from dataclasses import dataclass

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


IDENTIFICADA = "identificada"
NO_IDENTIFICADA = "no identificada"
DENSIDAD_INVALIDA = "densidad inválida"


@dataclass(frozen=True, eq=False)
class Cuantiles:
    """Cuantiles con su estado de identificación, nivel por nivel.

    ``valores`` es NaN donde el cuantil no está identificado: nunca se rellena
    con masa redistribuida ni con una extrapolación. ``estado[i]`` vale
    ``"identificada"``, ``"no identificada"`` (la cola necesaria cae fuera del
    tramo respaldado) o ``"densidad inválida"`` (densidad negativa o masa
    incoherente: ningún cuantil es utilizable).
    """

    u: np.ndarray
    valores: np.ndarray
    estado: np.ndarray
    rango_u: tuple  # probabilidades identificadas [u_min, u_max]; (nan, nan) si no hay
    motivo: str  # explicación del primer problema encontrado; "" si no hay
    diagnostico: dict

    @property
    def identificado(self):
        return self.estado == IDENTIFICADA

    @property
    def completo(self):
        return bool(np.all(self.identificado))


def _sin_cuantiles(u, estado, motivo, diagnostico):
    return Cuantiles(u, np.full(u.shape, np.nan), np.full(u.shape, estado, dtype=object),
                     (np.nan, np.nan), motivo, diagnostico)


def cuantiles_desde_cdf(x, cdf, u, rango_x=None, tol_masa=1e-3, tol_monotonia=1e-10):
    """Cuantiles ``F^{-1}(u)`` de una CDF **anclada** evaluada en la malla ``x``.

    ``cdf[i]`` debe ser la probabilidad absoluta ``Q(X <= x[i])``, incluida la
    masa a la izquierda de la malla. Solo se identifican los niveles ``u``
    dentro de ``[F(x_lo), F(x_hi)]``, donde ``[x_lo, x_hi]`` es la malla o, si se
    da, su intersección con ``rango_x`` (el tramo respaldado por strikes
    fiables). Una CDF que decrece más de ``tol_monotonia`` o que sale de
    ``[0, 1]`` por más de ``tol_masa`` se rechaza entera.
    """
    x = np.asarray(x, dtype=float)
    cdf = np.asarray(cdf, dtype=float)
    u = np.atleast_1d(np.asarray(u, dtype=float))
    if x.ndim != 1 or x.shape != cdf.shape or len(x) < 2 or np.any(np.diff(x) <= 0.0):
        raise ValueError("x debe ser una malla creciente con la misma forma que cdf")
    if np.any(~np.isfinite(u)) or np.any((u < 0.0) | (u > 1.0)):
        raise ValueError("los niveles u deben estar en [0, 1]")
    diagnostico = {"cdf_inicial": float(cdf[0]), "cdf_final": float(cdf[-1])}
    if not np.all(np.isfinite(cdf)):
        return _sin_cuantiles(u, DENSIDAD_INVALIDA, "CDF con valores no finitos", diagnostico)
    caida = float(-np.min(np.diff(cdf), initial=0.0))
    diagnostico["caida_maxima"] = caida
    if caida > tol_monotonia:
        return _sin_cuantiles(u, DENSIDAD_INVALIDA,
                              f"CDF decreciente (caída {caida:.3g}): densidad negativa", diagnostico)
    if cdf[0] < -tol_masa or cdf[-1] > 1.0 + tol_masa:
        return _sin_cuantiles(u, DENSIDAD_INVALIDA,
                              f"CDF fuera de [0, 1]: {cdf[0]:.6g} .. {cdf[-1]:.6g}", diagnostico)
    # Solo corrige redondeo (caídas menores que tol_monotonia).
    cdf = np.maximum.accumulate(cdf)
    x_lo, x_hi = x[0], x[-1]
    if rango_x is not None:
        x_lo, x_hi = max(x_lo, float(rango_x[0])), min(x_hi, float(rango_x[1]))
        if x_lo >= x_hi:
            return _sin_cuantiles(u, NO_IDENTIFICADA, "el rango identificado no cubre la malla",
                                  diagnostico)
    u_lo, u_hi = float(np.interp(x_lo, x, cdf)), float(np.interp(x_hi, x, cdf))
    dentro = (x > x_lo) & (x < x_hi)
    xs = np.concatenate([[x_lo], x[dentro], [x_hi]])
    fs = np.concatenate([[u_lo], cdf[dentro], [u_hi]])
    # En tramos planos se toma el extremo izquierdo: F^{-1}(u) = inf{x : F(x) >= u}.
    unicos, idx = np.unique(fs, return_index=True)
    identificado = (u >= u_lo) & (u <= u_hi)
    valores = np.where(identificado, np.interp(u, unicos, xs[idx]), np.nan)
    estado = np.where(identificado, IDENTIFICADA, NO_IDENTIFICADA).astype(object)
    motivo = ""
    if not np.all(identificado):
        partes = []
        if np.any(u < u_lo):
            partes.append(f"cola izquierda: u < {u_lo:.6g}")
        if np.any(u > u_hi):
            partes.append(f"cola derecha: u > {u_hi:.6g}")
        motivo = "fuera del tramo identificado (" + "; ".join(partes) + ")"
    return Cuantiles(u, valores, estado, (u_lo, u_hi), motivo, diagnostico)


def cuantiles_desde_densidad(x, p, u, masa_izquierda=None, rango_x=None, tol_masa=1e-3,
                             tol_negativa=1e-8):
    """Cuantiles ``F^{-1}(u)`` de una densidad en malla, sin inventar masa.

    * **No normaliza.** La CDF es ``masa_izquierda + int_{x[0]}^x p``. La masa a
      la izquierda de la malla se obtiene de la pendiente de los precios
      (``1 + C'(K)/D`` o ``cdf_logmoneyness``), no de la densidad. Si no se da,
      solo se acepta una malla que contenga toda la masa salvo ``tol_masa`` (y
      el error de probabilidad queda acotado por ``tol_masa``); si falta más, la
      CDF no está anclada y ningún cuantil se identifica.
    * **No recorta negativos.** Si ``p`` baja de ``-tol_negativa * max|p|`` la
      densidad es inválida y ningún cuantil se devuelve.
    * La masa que falta a la derecha deja sin identificar los niveles
      ``u > F(x[-1])``; ``rango_x`` limita además la identificación al tramo
      respaldado por strikes fiables (véase ``cuantiles_desde_cdf``).
    """
    x = np.asarray(x, dtype=float)
    p = np.asarray(p, dtype=float)
    u = np.atleast_1d(np.asarray(u, dtype=float))
    if x.ndim != 1 or x.shape != p.shape or len(x) < 2 or np.any(np.diff(x) <= 0.0):
        raise ValueError("x debe ser una malla creciente con la misma forma que p")
    if not np.all(np.isfinite(p)):
        return _sin_cuantiles(u, DENSIDAD_INVALIDA, "densidad con valores no finitos", {})
    escala = max(float(np.max(np.abs(p))), 1e-300)
    negativos = p < -tol_negativa * escala
    diagnostico = {
        "masa_malla": trapecio(p, x),
        "masa_negativa": -trapecio(np.minimum(p, 0.0), x),
        "minimo": float(p.min()),
        "puntos_negativos": int(negativos.sum()),
    }
    if negativos.any():
        return _sin_cuantiles(
            u, DENSIDAD_INVALIDA,
            f"densidad negativa en {int(negativos.sum())} de {len(p)} puntos "
            f"(mínimo {p.min():.3g}); no se recorta", diagnostico)
    if masa_izquierda is None:
        if diagnostico["masa_malla"] < 1.0 - tol_masa:
            return _sin_cuantiles(
                u, NO_IDENTIFICADA,
                f"falta masa fuera de la malla ({1.0 - diagnostico['masa_malla']:.3g}) y no se "
                "conoce la masa izquierda: la CDF no está anclada", diagnostico)
        masa_izquierda = 0.0
    if not 0.0 <= masa_izquierda <= 1.0:
        raise ValueError("masa_izquierda debe estar en [0, 1]")
    diagnostico["masa_izquierda"] = float(masa_izquierda)
    cdf = masa_izquierda + cdf_desde_densidad(x, p)
    # Negativos tolerados (redondeo) solo pueden producir caídas de este orden.
    tol_monotonia = tol_negativa * escala * float(np.max(np.diff(x))) + 1e-15
    resultado = cuantiles_desde_cdf(x, cdf, u, rango_x, tol_masa, tol_monotonia)
    diagnostico.update(resultado.diagnostico)
    diagnostico["masa_derecha"] = 1.0 - float(cdf[-1])
    return Cuantiles(resultado.u, resultado.valores, resultado.estado, resultado.rango_u,
                     resultado.motivo, diagnostico)


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
