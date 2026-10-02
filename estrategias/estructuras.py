"""Estructuras con opciones: patas, pago al vencimiento y catálogo de candidatas.

Una estructura es una combinación de patas europeas al **mismo vencimiento**.
Cada pata es ``(tipo, strike, cantidad)`` con cantidad positiva para posición
comprada y negativa para vendida:

* ``put``      pago ``max(K - S_T, 0)``;
* ``call``     pago ``max(S_T - K, 0)``;
* ``forward``  pago ``S_T``, con precio justo ``D * F`` (evita contabilizar
  dividendos y financiación del contado: sirve como referencia direccional).

El catálogo incluye, junto a las estructuras con puts, las alternativas que
expresan la misma dirección de otra forma. Esa comparación es el punto: vender
puts no es la única manera de decir «creo que sube», y casi nunca es la mejor
cuando la opinión es sobre la magnitud del movimiento y no sobre la cola.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TIPOS = ("put", "call", "forward")
ALCISTA, BAJISTA, COBERTURA = "alcista", "bajista", "cobertura"


@dataclass(frozen=True)
class Pata:
    tipo: str
    strike: float
    cantidad: float

    def __post_init__(self):
        if self.tipo not in TIPOS:
            raise ValueError(f"tipo desconocido: {self.tipo}")
        if self.tipo == "forward":
            if np.isfinite(self.strike):
                raise ValueError("una pata forward no lleva strike")
        elif not (np.isfinite(self.strike) and self.strike > 0.0):
            raise ValueError("el strike debe ser finito y positivo")
        if self.cantidad == 0.0:
            raise ValueError("una pata con cantidad cero no aporta nada")

    @property
    def clave(self):
        return (self.tipo, None if self.tipo == "forward" else round(float(self.strike), 6))

    def pago(self, s):
        s = np.asarray(s, dtype=float)
        if self.tipo == "put":
            return self.cantidad * np.maximum(self.strike - s, 0.0)
        if self.tipo == "call":
            return self.cantidad * np.maximum(s - self.strike, 0.0)
        return self.cantidad * s


@dataclass(frozen=True)
class Estructura:
    nombre: str
    patas: tuple
    direccion: str
    descripcion: str = ""

    def __post_init__(self):
        if not self.patas:
            raise ValueError("una estructura necesita al menos una pata")
        if self.direccion not in (ALCISTA, BAJISTA, COBERTURA):
            raise ValueError(f"dirección desconocida: {self.direccion}")

    def pago(self, s):
        return sum(p.pago(s) for p in self.patas)

    @property
    def pendiente_derecha(self):
        """Pendiente del pago cuando ``S_T -> infinito``."""
        return float(sum(p.cantidad for p in self.patas if p.tipo in ("call", "forward")))

    @property
    def perdida_no_acotada(self):
        return self.pendiente_derecha < 0.0

    @property
    def vende_volatilidad(self):
        """Verdadero si la estructura es neta vendedora de convexidad."""
        return sum(p.cantidad for p in self.patas if p.tipo in ("put", "call")) < 0.0

    @property
    def strikes(self):
        return tuple(sorted({float(p.strike) for p in self.patas if p.tipo != "forward"}))


# ---------------------------------------------------------------------------
# Constructores
# ---------------------------------------------------------------------------


def put_corto(K):
    return Estructura(f"put corto {K:g}", (Pata("put", K, -1.0),), ALCISTA,
                      "Cobra prima; pierde si el subyacente cae por debajo del strike. "
                      "Expresa «la caída que paga el mercado está sobrevalorada».")


def put_largo(K):
    return Estructura(f"put largo {K:g}", (Pata("put", K, 1.0),), BAJISTA,
                      "Paga prima; gana en la caída. Expresa «la caída está infravalorada» "
                      "o cubre una exposición existente.")


def put_spread_alcista(K_bajo, K_alto):
    if not K_bajo < K_alto:
        raise ValueError("K_bajo debe ser menor que K_alto")
    return Estructura(f"put spread alcista {K_bajo:g}/{K_alto:g}",
                      (Pata("put", K_alto, -1.0), Pata("put", K_bajo, 1.0)), ALCISTA,
                      "Vende el put alto y compra el bajo: cobra prima con pérdida acotada "
                      "por la anchura. Expresa una opinión sobre un tramo concreto de la cola.")


def put_spread_bajista(K_bajo, K_alto):
    if not K_bajo < K_alto:
        raise ValueError("K_bajo debe ser menor que K_alto")
    return Estructura(f"put spread bajista {K_bajo:g}/{K_alto:g}",
                      (Pata("put", K_alto, 1.0), Pata("put", K_bajo, -1.0)), BAJISTA,
                      "Compra el put alto y vende el bajo: paga menos prima a cambio de "
                      "renunciar a la caída por debajo del strike bajo.")


def call_largo(K):
    return Estructura(f"call largo {K:g}", (Pata("call", K, 1.0),), ALCISTA,
                      "Paga prima; gana con el movimiento al alza. Expresa una opinión "
                      "sobre la magnitud de la subida, no sobre la cola izquierda.")


def call_spread_alcista(K_bajo, K_alto):
    if not K_bajo < K_alto:
        raise ValueError("K_bajo debe ser menor que K_alto")
    return Estructura(f"call spread alcista {K_bajo:g}/{K_alto:g}",
                      (Pata("call", K_bajo, 1.0), Pata("call", K_alto, -1.0)), ALCISTA,
                      "Compra la call baja y vende la alta: coste acotado y ganancia acotada.")


def reversal_riesgo(K_put, K_call):
    if not K_put < K_call:
        raise ValueError("K_put debe ser menor que K_call")
    return Estructura(f"reversal de riesgo -{K_put:g}p/+{K_call:g}c",
                      (Pata("put", K_put, -1.0), Pata("call", K_call, 1.0)), ALCISTA,
                      "Vende el put y compra la call: posición direccional casi sin prima "
                      "neta, con la pérdida de un put corto y la ganancia de una call larga.")


def forward_largo():
    return Estructura("forward largo", (Pata("forward", float("nan"), 1.0),), ALCISTA,
                      "Exposición lineal: la referencia contra la que se mide si merece la "
                      "pena pagar o cobrar convexidad.")


def forward_corto():
    return Estructura("forward corto", (Pata("forward", float("nan"), -1.0),), BAJISTA,
                      "Exposición lineal bajista.")


def put_protectora(K):
    return Estructura(f"put protectora {K:g}",
                      (Pata("forward", float("nan"), 1.0), Pata("put", K, 1.0)), COBERTURA,
                      "Exposición larga con suelo: el motivo habitual para **comprar** puts "
                      "no es predecir la caída, sino acotarla.")


def collar(K_put, K_call):
    if not K_put < K_call:
        raise ValueError("K_put debe ser menor que K_call")
    return Estructura(f"collar {K_put:g}/{K_call:g}",
                      (Pata("forward", float("nan"), 1.0), Pata("put", K_put, 1.0),
                       Pata("call", K_call, -1.0)), COBERTURA,
                      "Exposición larga con suelo y techo: financia el put vendiendo la call.")


def catalogo(F, strikes, distancias=(0.03, 0.05, 0.08), anchuras=(0.05,)):
    """Candidatas razonables alrededor del forward a partir de los strikes disponibles.

    ``distancias`` son separaciones relativas del forward (``0.05`` sitúa el put
    en ``0.95 F`` y la call en ``1.05 F``) y se redondean al strike cotizado más
    próximo; ``anchuras``, las separaciones relativas entre las patas de los
    spreads. El catálogo no decide nada: solo enumera lo que después se evalúa
    con la misma vara, incluidas las alternativas sin puts que sirven de
    contraste.
    """
    strikes = np.sort(np.asarray(strikes, dtype=float))
    if len(strikes) < 2:
        raise ValueError("hacen falta al menos dos strikes")

    def cercano(objetivo):
        return float(strikes[int(np.argmin(np.abs(strikes - objetivo)))])

    fracciones = sorted({float(d) for d in distancias})
    candidatas, vistos = [], set()

    def anadir(e):
        if e.nombre not in vistos:
            vistos.add(e.nombre)
            candidatas.append(e)

    for f in fracciones:
        k_put = cercano(F * (1.0 - f))
        k_call = cercano(F * (1.0 + f))
        if k_put >= F or k_call <= F:
            continue
        anadir(put_corto(k_put))
        anadir(put_largo(k_put))
        anadir(call_largo(k_call))
        anadir(reversal_riesgo(k_put, k_call))
        anadir(put_protectora(k_put))
        anadir(collar(k_put, k_call))
        for a in anchuras:
            k_bajo = cercano(k_put * (1.0 - float(a)))
            if k_bajo < k_put:
                anadir(put_spread_alcista(k_bajo, k_put))
                anadir(put_spread_bajista(k_bajo, k_put))
            k_arriba = cercano(k_call * (1.0 + float(a)))
            if k_arriba > k_call:
                anadir(call_spread_alcista(k_call, k_arriba))
    anadir(forward_largo())
    anadir(forward_corto())
    return candidatas


def claves(estructura: Estructura):
    """Patas agregadas por clave: lo que hay que cotizar realmente."""
    agregadas = {}
    for p in estructura.patas:
        agregadas[p.clave] = agregadas.get(p.clave, 0.0) + p.cantidad
    return {k: v for k, v in agregadas.items() if v != 0.0}
