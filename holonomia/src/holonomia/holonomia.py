"""Holonomía con precio medio y con precios ejecutables.

Dos conexiones sobre el mismo grafo:

* ``A_mid`` es antisimétrica y es una cocadena de verdad: se le puede aplicar
  Hodge. Mide la inconsistencia del mercado *ignorando* el costo de cruzarlo.
* ``A_exec`` **no** es antisimétrica: ir de ``i`` a ``j`` cuesta el bid y
  volver cuesta el ask, y la comisión se cobra en los dos sentidos. No es una
  cocadena y no se descompone; sólo se integra sobre ciclos.

Con el medio geométrico ``mid = √(bid · ask)`` y el medio spread en logs
``s = ½ log(ask / bid)``, cada pata cumple exactamente, en los dos sentidos,

    A_exec = A_mid − s + log(1 − f)

y por lo tanto, para un ciclo de longitud L,

    H_exec(C) = H_mid(C) − Σ_patas s + L · log(1 − f).

Esa identidad es la que separa «hay curvatura» de «hay dinero»: la holonomía
media tiene que superar el medio spread acumulado y las L comisiones para que
el ciclo sea ejecutable. Se comprueba en los tests.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .grafo import Grafo

# Comisiones de cripto al contado de Alpaca, por nivel de volumen a 30 días.
# Fuente: https://docs.alpaca.markets/docs/crypto-fees (página con fecha de
# actualización 2025-09-24, consultada el 18 de noviembre de 2026).
COMISIONES_ALPACA = {
    1: (0.0015, 0.0025),   # 0 – 100 k USD
    2: (0.0012, 0.0022),   # 100 k – 500 k
    3: (0.0010, 0.0020),   # 500 k – 1 M
    4: (0.0008, 0.0018),   # 1 M – 10 M
    5: (0.0005, 0.0015),   # 10 M – 25 M
    6: (0.0002, 0.0013),   # 25 M – 50 M
    7: (0.0002, 0.0012),   # 50 M – 100 M
    8: (0.0000, 0.0010),   # 100 M +
}


@dataclass(frozen=True)
class Comisiones:
    """Comisión proporcional cobrada sobre el activo recibido, por operación."""

    maker: float = 0.0015
    taker: float = 0.0025

    @classmethod
    def alpaca(cls, nivel: int = 1) -> "Comisiones":
        if nivel not in COMISIONES_ALPACA:
            raise KeyError(f"nivel de comisión desconocido: {nivel}")
        maker, taker = COMISIONES_ALPACA[nivel]
        return cls(maker=maker, taker=taker)

    @classmethod
    def sin_costo(cls) -> "Comisiones":
        return cls(maker=0.0, taker=0.0)


@dataclass(frozen=True)
class Cotizacion:
    """Una cotización de dos lados sobre el par ``base/cotizada``.

    ``bid`` y ``ask`` están en unidades de ``cotizada`` por unidad de ``base``,
    que es como los publica Alpaca.
    """

    simbolo: str
    bid: float
    ask: float
    bid_size: float = math.nan
    ask_size: float = math.nan
    sello_evento: float = math.nan   # segundos UTC del exchange

    @property
    def base(self) -> str:
        return self.simbolo.split("/")[0]

    @property
    def cotizada(self) -> str:
        return self.simbolo.split("/")[1]

    @property
    def cruzado(self) -> bool:
        """Mercado cruzado o bloqueado: ``bid ≥ ask``."""
        return not (self.bid < self.ask)

    def mid(self, tipo: str = "geometrico") -> float:
        if tipo == "geometrico":
            return math.sqrt(self.bid * self.ask)
        if tipo == "aritmetico":
            return 0.5 * (self.bid + self.ask)
        raise ValueError(f"tipo de mid desconocido: {tipo!r}")

    def medio_spread_log(self) -> float:
        """``s = ½ log(ask / bid)``, el medio spread medido en logaritmos."""
        return 0.5 * math.log(self.ask / self.bid)


def cocadena_mid(g: Grafo, cotizaciones, tipo: str = "geometrico") -> np.ndarray:
    """Cocadena ``A_mid`` a partir de cotizaciones, alineada con ``g.aristas``.

    ``cotizaciones`` es un iterable de ``Cotizacion`` o un dict
    ``símbolo -> Cotizacion``. Para el par ``BASE/COTIZADA`` con medio ``m``,
    la arista dirigida ``BASE → COTIZADA`` lleva ``log m``: una unidad de
    ``BASE`` se cambia por ``m`` de ``COTIZADA``.
    """
    cots = list(cotizaciones.values()) if isinstance(cotizaciones, dict) else list(cotizaciones)
    valores = {(c.base, c.cotizada): math.log(c.mid(tipo)) for c in cots}
    return g.cocadena(valores)


def _paso_ejecutable(cot_por_par, a: str, b: str, comision: float) -> float:
    """``log`` de las unidades de ``b`` que deja una unidad de ``a``, con costo."""
    if (a, b) in cot_por_par:          # a es la base: se vende a al bid
        c = cot_por_par[(a, b)]
        bruto = math.log(c.bid)
    elif (b, a) in cot_por_par:        # b es la base: se compra b al ask
        c = cot_por_par[(b, a)]
        bruto = -math.log(c.ask)
    else:
        raise KeyError(f"no hay cotización para el paso {a} → {b}")
    return bruto + math.log1p(-comision)


def _indice_por_par(cotizaciones) -> dict[tuple[str, str], Cotizacion]:
    cots = list(cotizaciones.values()) if isinstance(cotizaciones, dict) else list(cotizaciones)
    return {(c.base, c.cotizada): c for c in cots}


def _pasos(ciclo) -> list[tuple[str, str]]:
    nodos = list(ciclo)
    if len(nodos) > 1 and nodos[0] == nodos[-1]:
        nodos = nodos[:-1]
    if len(nodos) < 2:
        raise ValueError("un ciclo necesita al menos dos monedas")
    return list(zip(nodos, nodos[1:] + nodos[:1]))


def holonomia_ejecutable(cotizaciones, ciclo, comisiones: Comisiones | None = None,
                         usar_taker: bool = True) -> float:
    """``H_exec(C)``: log del factor que devuelve el ciclo, ya con costos.

    ``H_exec > 0`` es arbitraje ejecutable: salir con más de lo que se entró,
    cruzando el spread en cada pata y pagando comisión en cada una. Por
    omisión se cobra *taker*, que es lo que corresponde a cruzar el mercado.
    """
    comisiones = comisiones or Comisiones.alpaca(1)
    f = comisiones.taker if usar_taker else comisiones.maker
    por_par = _indice_por_par(cotizaciones)
    return float(sum(_paso_ejecutable(por_par, a, b, f) for a, b in _pasos(ciclo)))


def medio_spread_ciclo(cotizaciones, ciclo) -> float:
    """``Σ s`` sobre las patas del ciclo: el costo de cruzar, sin comisiones.

    Es la vara contra la que se mide ``H_mid``: por debajo de ella la
    inconsistencia no es ejecutable ni aunque las comisiones fueran cero.
    """
    por_par = _indice_por_par(cotizaciones)
    total = 0.0
    for a, b in _pasos(ciclo):
        c = por_par.get((a, b)) or por_par.get((b, a))
        if c is None:
            raise KeyError(f"no hay cotización para el paso {a} → {b}")
        total += c.medio_spread_log()
    return float(total)


def holonomia_mid(cotizaciones, ciclo, tipo: str = "geometrico") -> float:
    """``H_mid(C)`` directo desde las cotizaciones, sin construir el grafo."""
    por_par = _indice_por_par(cotizaciones)
    total = 0.0
    for a, b in _pasos(ciclo):
        if (a, b) in por_par:
            total += math.log(por_par[(a, b)].mid(tipo))
        elif (b, a) in por_par:
            total -= math.log(por_par[(b, a)].mid(tipo))
        else:
            raise KeyError(f"no hay cotización para el paso {a} → {b}")
    return float(total)


def umbral_ejecutable(cotizaciones, ciclo, comisiones: Comisiones | None = None,
                      usar_taker: bool = True) -> float:
    """Lo que ``H_mid`` tiene que superar para que el ciclo deje dinero.

    Es ``Σ s − L·log(1 − f)``, es decir medio spread acumulado más comisiones.
    Por la identidad del encabezado, ``H_exec = H_mid − umbral``.
    """
    comisiones = comisiones or Comisiones.alpaca(1)
    f = comisiones.taker if usar_taker else comisiones.maker
    L = len(_pasos(ciclo))
    return float(medio_spread_ciclo(cotizaciones, ciclo) - L * math.log1p(-f))
