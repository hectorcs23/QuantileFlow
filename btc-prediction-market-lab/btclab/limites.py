"""Presupuesto de perdida y limites configurables (Paso 7).

``B`` es capital **segregado** para esta estrategia: no es el patrimonio total ni
el poder de compra con credito. Si no hay presupuesto configurado, el tamano
monetario es cero.

Separacion obligatoria de importes: ``simulated_amount`` es lo que la simulacion
propone; ``suggested_live_amount`` es cero mientras el proyecto no este validado.
Nunca se mezclan en el mismo campo.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from .tiempo import exigir_utc


class ErrorLimites(ValueError):
    """Configuracion de riesgo incoherente."""


@dataclass(frozen=True)
class LimitesRiesgo:
    """Limites que el tamano final debe respetar simultaneamente.

    Los valores por omision son de **simulacion** y estan etiquetados como tales.
    ``presupuesto_configurado`` es la puerta: mientras sea ``False`` no se expone
    ningun importe personal.
    """

    capital_segregado: Decimal
    es_capital_ficticio: bool = True
    presupuesto_configurado: bool = False
    perdida_maxima_por_operacion: Decimal | None = None
    perdida_diaria_maxima: Decimal | None = None
    exposicion_abierta_maxima: Decimal | None = None
    posiciones_abiertas_maximas: int = 1
    fraccion_kelly: Decimal = Decimal("0.25")
    concentracion_maxima_por_contrato: Decimal | None = None
    limite_posicion_exchange: Decimal | None = None
    hora_reinicio_utc: int = 0
    etiqueta: str = "simulacion"

    def __post_init__(self) -> None:
        if self.capital_segregado < 0:
            raise ErrorLimites("capital segregado negativo")
        if not 0 < self.fraccion_kelly <= 1:
            raise ErrorLimites(
                f"fraccion de Kelly fuera de (0,1]: {self.fraccion_kelly}"
            )
        if not 0 <= self.hora_reinicio_utc <= 23:
            raise ErrorLimites("hora_reinicio_utc fuera de [0,23]")
        if self.posiciones_abiertas_maximas < 0:
            raise ErrorLimites("posiciones abiertas maximas negativa")

    @property
    def permite_importe_real(self) -> bool:
        """Solo con presupuesto configurado y capital no ficticio."""
        return self.presupuesto_configurado and not self.es_capital_ficticio


@dataclass
class EstadoRiesgo:
    """Riesgo consumido en la zona de reinicio vigente.

    ``perdidas_realizadas`` son perdidas ya cerradas. ``riesgo_maximo_abierto``
    es la perdida maxima de las posiciones abiertas: se contabiliza contra el
    limite diario porque una compra binaria mantenida a vencimiento puede perder
    todo lo comprometido, y un stop de P&L no lo evita.
    """

    inicio_zona: dt.datetime
    perdidas_realizadas: Decimal = Decimal("0")
    riesgo_maximo_abierto: Decimal = Decimal("0")
    posiciones_abiertas: int = 0
    exposicion_abierta: Decimal = Decimal("0")
    por_contrato: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        exigir_utc(self.inicio_zona, "inicio_zona")

    def zona_vigente(self, momento: dt.datetime, limites: LimitesRiesgo) -> bool:
        """True si ``momento`` cae en la misma zona de reinicio."""
        instante = exigir_utc(momento)
        inicio = self._inicio_para(instante, limites)
        return inicio == self._inicio_para(self.inicio_zona, limites)

    @staticmethod
    def _inicio_para(momento: dt.datetime, limites: LimitesRiesgo) -> dt.datetime:
        base = exigir_utc(momento).replace(
            hour=limites.hora_reinicio_utc, minute=0, second=0, microsecond=0
        )
        if exigir_utc(momento) < base:
            base -= dt.timedelta(days=1)
        return base

    @property
    def riesgo_diario_consumido(self) -> Decimal:
        """Perdidas cerradas mas riesgo maximo de lo que sigue abierto."""
        return self.perdidas_realizadas + self.riesgo_maximo_abierto

    def margen_diario(self, limites: LimitesRiesgo) -> Decimal | None:
        if limites.perdida_diaria_maxima is None:
            return None
        return limites.perdida_diaria_maxima - self.riesgo_diario_consumido

    def limite_diario_agotado(self, limites: LimitesRiesgo) -> bool:
        margen = self.margen_diario(limites)
        return margen is not None and margen <= 0

    def capital_libre(self, limites: LimitesRiesgo) -> Decimal:
        return limites.capital_segregado - self.exposicion_abierta


@dataclass(frozen=True)
class Restriccion:
    """Un limite y su efecto sobre la cantidad."""

    nombre: str
    cantidad_maxima: Decimal | None
    activa: bool
    detalle: str = ""


def restricciones_vigentes(
    limites: LimitesRiesgo,
    estado: EstadoRiesgo,
    momento: dt.datetime,
    coste_unitario: Decimal | None,
) -> tuple[Restriccion, ...]:
    """Traduce cada limite a un tope de cantidad, cuando es traducible.

    ``coste_unitario`` convierte un tope en dinero a un tope en contratos. Si no
    se conoce, el tope en dinero se marca activo con ``cantidad_maxima=None`` y
    el llamador debe tratarlo como bloqueante.
    """
    def a_contratos(dinero: Decimal | None) -> Decimal | None:
        if dinero is None:
            return None
        if coste_unitario is None or coste_unitario <= 0:
            return None
        if dinero <= 0:
            return Decimal("0")
        return dinero / coste_unitario

    salida: list[Restriccion] = []

    if not limites.presupuesto_configurado:
        salida.append(
            Restriccion(
                "presupuesto_no_configurado",
                Decimal("0"),
                True,
                "sin presupuesto configurado el tamano monetario es cero",
            )
        )

    if not estado.zona_vigente(momento, limites):
        salida.append(
            Restriccion(
                "zona_de_reinicio_desalineada",
                None,
                True,
                "el estado de riesgo pertenece a otra zona; recargar antes de decidir",
            )
        )

    libre = estado.capital_libre(limites)
    salida.append(
        Restriccion(
            "capital_libre",
            a_contratos(libre),
            libre <= 0,
            f"capital libre {libre}",
        )
    )

    if limites.perdida_maxima_por_operacion is not None:
        tope = limites.perdida_maxima_por_operacion
        salida.append(
            Restriccion(
                "perdida_maxima_por_operacion",
                a_contratos(tope),
                tope <= 0,
                f"tope por operacion {tope}",
            )
        )

    margen = estado.margen_diario(limites)
    if margen is not None:
        salida.append(
            Restriccion(
                "perdida_diaria_restante",
                a_contratos(margen),
                margen <= 0,
                f"margen diario {margen} "
                f"(realizadas {estado.perdidas_realizadas} + "
                f"abierto {estado.riesgo_maximo_abierto})",
            )
        )

    if limites.exposicion_abierta_maxima is not None:
        resto = limites.exposicion_abierta_maxima - estado.exposicion_abierta
        salida.append(
            Restriccion(
                "exposicion_abierta",
                a_contratos(resto),
                resto <= 0,
                f"exposicion disponible {resto}",
            )
        )

    if estado.posiciones_abiertas >= limites.posiciones_abiertas_maximas:
        salida.append(
            Restriccion(
                "posiciones_abiertas",
                Decimal("0"),
                True,
                f"{estado.posiciones_abiertas} abiertas de "
                f"{limites.posiciones_abiertas_maximas}",
            )
        )

    if limites.concentracion_maxima_por_contrato is not None:
        tope = limites.concentracion_maxima_por_contrato
        salida.append(
            Restriccion(
                "concentracion_por_contrato",
                a_contratos(tope),
                tope <= 0,
                f"tope de concentracion {tope}",
            )
        )

    if limites.limite_posicion_exchange is not None:
        tope = limites.limite_posicion_exchange
        salida.append(
            Restriccion(
                "limite_posicion_exchange",
                a_contratos(tope),
                tope <= 0,
                f"limite del exchange {tope} por strike",
            )
        )

    return tuple(salida)
