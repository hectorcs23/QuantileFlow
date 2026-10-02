"""Precios ejecutables: lo que de verdad se cobra o se paga al montar la estructura.

La diferencia entre el valor teórico y el precio ejecutable es, en muchas
estructuras con puts, del mismo orden que la ventaja que se persigue. Por eso
aquí no se usa el mid salvo como referencia: el modo por omisión compra al ask y
vende al bid, y encima cobra comisión por pata.

Las cadenas suelen cotizar solo la parte fuera del dinero. La pata que falta se
obtiene por paridad put-call con el forward de la propia rebanada,
``P(K) = C(K) - D (F - K)``, y la cotización resultante queda marcada: hereda la
incertidumbre del forward implícito, no es una cotización observada.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .estructuras import Estructura, claves

MEDIO, ADVERSO = "medio", "adverso"


@dataclass(frozen=True)
class Cotizacion:
    bid: float
    ask: float
    fiable: bool
    motivo: str = ""
    via_paridad: bool = False

    @property
    def mid(self):
        return 0.5 * (self.bid + self.ask)

    @property
    def medio_spread(self):
        return 0.5 * (self.ask - self.bid)


@dataclass(frozen=True)
class Mercado:
    """Cotizaciones de un vencimiento más los parámetros de ejecución."""

    T: float
    F: float
    D: float
    cotizaciones: dict
    comision: float = 0.0            # por pata y unidad de subyacente
    coste_forward: float = 0.0       # fracción de D*F por montar la pata lineal
    multiplicador: float = 1.0
    detalle: dict = field(default_factory=dict)

    def strikes_fiables(self):
        ks = [k for (tipo, k), c in self.cotizaciones.items() if tipo != "forward" and c.fiable]
        return tuple(sorted(set(ks)))

    def rango_fiable(self):
        ks = self.strikes_fiables()
        if len(ks) < 2:
            raise ValueError("no hay dos strikes fiables: la distribución no está identificada")
        return float(min(ks)), float(max(ks))


def _cotizacion_forward(mercado: Mercado):
    justo = mercado.D * mercado.F
    holgura = mercado.coste_forward * justo
    return Cotizacion(justo - holgura, justo + holgura, True, "", False)


def precio_entrada(mercado: Mercado, estructura: Estructura, modo=ADVERSO):
    """Coste neto de montar la estructura (positivo = débito, negativo = crédito).

    Devuelve el precio, el componente de comisiones y el estado de
    identificación. Una pata sin cotización utilizable invalida la estructura
    entera: no se sustituye por un modelo.
    """
    if modo not in (MEDIO, ADVERSO):
        raise ValueError(f"modo desconocido: {modo}")
    total, comisiones, motivos, paridad = 0.0, 0.0, [], False
    for (tipo, strike), cantidad in claves(estructura).items():
        cot = (_cotizacion_forward(mercado) if tipo == "forward"
               else mercado.cotizaciones.get((tipo, strike)))
        if cot is None:
            motivos.append(f"sin cotización para {tipo} {strike}")
            continue
        if not cot.fiable:
            motivos.append(f"{tipo} {strike}: {cot.motivo or 'cotización no utilizable'}")
            continue
        paridad = paridad or cot.via_paridad
        if modo == MEDIO:
            precio = cot.mid
        else:
            precio = cot.ask if cantidad > 0.0 else cot.bid
        total += cantidad * precio
        comisiones += abs(cantidad) * mercado.comision
    if motivos:
        return {"precio": float("nan"), "comisiones": float("nan"), "identificada": False,
                "motivo": "; ".join(motivos), "via_paridad": paridad, "modo": modo}
    return {"precio": float(total), "comisiones": float(comisiones), "identificada": True,
            "motivo": "", "via_paridad": paridad, "modo": modo}


def valor(distribucion, estructura: Estructura, D):
    """Valor presente de la estructura bajo una distribución: ``D * E[pago]``.

    Con ``Q`` da el precio teórico sin arbitraje; con ``P``, lo que la vista
    dice que vale. La diferencia entre ambos es toda la ventaja posible.
    """
    return float(D) * distribucion.esperanza(estructura.pago(distribucion.s))


def cotizaciones_desde_rebanada(reb, spread_relativo_max=0.5, spread_absoluto_min=0.05,
                                completar_por_paridad=True):
    """Convierte una ``quantileflow.superficies.Rebanada`` en cotizaciones por pata.

    Una cotización es utilizable si tiene bid estrictamente positivo y un spread
    que no supera ``max(spread_absoluto_min, spread_relativo_max * mid)``. Un
    bid de cero solo acota el precio por arriba: no identifica nada y se marca.
    """
    cotizaciones = {}
    for K, bid, ask, es_call in zip(np.asarray(reb.K, float), np.asarray(reb.bid, float),
                                    np.asarray(reb.ask, float), np.asarray(reb.es_call, bool)):
        tipo = "call" if es_call else "put"
        mid = 0.5 * (bid + ask)
        tope = max(spread_absoluto_min, spread_relativo_max * mid)
        if bid <= 0.0:
            cot = Cotizacion(bid, ask, False, "bid cero: la cotización solo acota por arriba")
        elif ask - bid > tope:
            cot = Cotizacion(bid, ask, False, f"spread {ask - bid:.3f} mayor que {tope:.3f}")
        else:
            cot = Cotizacion(bid, ask, True)
        cotizaciones[(tipo, round(float(K), 6))] = cot
    if completar_por_paridad:
        for (tipo, K), cot in list(cotizaciones.items()):
            otro = "put" if tipo == "call" else "call"
            if (otro, K) in cotizaciones:
                continue
            signo = 1.0 if otro == "call" else -1.0
            ajuste = signo * reb.D * (reb.F - K)
            bid, ask = cot.bid + ajuste, cot.ask + ajuste
            if bid <= 0.0:
                cotizaciones[(otro, K)] = Cotizacion(
                    max(bid, 0.0), max(ask, 0.0), False,
                    "obtenida por paridad con bid no positivo", True)
            else:
                cotizaciones[(otro, K)] = Cotizacion(bid, ask, cot.fiable,
                                                     cot.motivo, True)
    return cotizaciones


def mercado_desde_rebanada(reb, comision=0.0, coste_forward=0.0, multiplicador=1.0, **kw):
    cotizaciones = cotizaciones_desde_rebanada(reb, **kw)
    return Mercado(T=float(reb.T), F=float(reb.F), D=float(reb.D), cotizaciones=cotizaciones,
                   comision=float(comision), coste_forward=float(coste_forward),
                   multiplicador=float(multiplicador),
                   detalle={"n_cotizaciones": len(cotizaciones),
                            "n_fiables": sum(c.fiable for c in cotizaciones.values())})
