"""Pantalla y registro de cada decision (Paso 12).

Un objeto ``Decision`` reune todo lo que hay que mostrar y todo lo que hay que
guardar. Dos invariantes:

* **Cada importe declara si es ficticio, simulado o real.** El campo
  ``clase_importe`` es obligatorio y el registro lo serializa junto al numero,
  para que un valor no pueda leerse fuera de contexto.
* **La recomendacion caduca.** ``valid_until`` y ``condiciones_invalidez`` se
  guardan siempre; una senal vieja no se presenta como vigente.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from .contrato import FichaContrato
from .dinero import a_dolares
from .libro import Lado, Libro
from .probabilidad import Prediccion
from .sizing import PropuestaTamano
from .tiempo import a_iso, exigir_utc, presentar


class ClaseImporte(str, Enum):
    """Naturaleza de un importe mostrado."""

    FICTICIO = "ficticio"
    SIMULADO = "simulado"
    REAL = "real"


class ErrorDecision(ValueError):
    """Decision mal formada."""


@dataclass(frozen=True)
class CalidadDatos:
    """Estado de los datos en el momento de decidir."""

    antiguedad_libro_s: float | None
    antiguedad_spot_s: float | None
    huecos_detectados: int
    secuencias_rotas: int
    motivos: tuple[str, ...] = ()

    @property
    def utilizable(self) -> bool:
        return not self.motivos


@dataclass(frozen=True)
class Decision:
    """Una decision registrable, operar o no operar."""

    decision_id: str
    decidido_en: dt.datetime
    ficha: FichaContrato
    libro: Libro
    prediccion: Prediccion
    propuesta: PropuestaTamano
    calidad: CalidadDatos
    clase_importe: ClaseImporte
    valid_until: dt.datetime
    version_configuracion: str
    margen_operativo: Decimal
    condiciones_invalidez: tuple[str, ...] = ()
    coste_evaluado: dict = field(default_factory=dict)
    fill: dict | None = None
    resultado: dict | None = None

    def __post_init__(self) -> None:
        exigir_utc(self.decidido_en, "decidido_en")
        exigir_utc(self.valid_until, "valid_until")
        if self.valid_until < self.decidido_en:
            raise ErrorDecision("valid_until anterior a la decision")
        if not self.decision_id:
            raise ErrorDecision("decision sin identificador")

    @property
    def opera(self) -> bool:
        return self.propuesta.opera and self.calidad.utilizable

    def vigente_en(self, momento: dt.datetime) -> bool:
        return exigir_utc(momento) <= self.valid_until

    @property
    def motivos(self) -> tuple[str, ...]:
        """Todos los motivos de no operar, sin duplicados."""
        return tuple(
            dict.fromkeys(
                tuple(self.calidad.motivos) + tuple(self.propuesta.motivos_no_operar)
            )
        )

    # -- pantalla -------------------------------------------------------

    def pantalla(self) -> str:
        """Texto para mostrar, con todo lo que el Paso 12 exige."""
        lado = self.propuesta.lado
        regla = self.ficha.regla
        lineas = [
            f"Proveedor: {self.ficha.plataforma_visible} "
            f"(exchange: {self.ficha.exchange_subyacente})",
            f"Contrato:  {self.ficha.contrato}",
            f"Pregunta:  {self.ficha.pregunta}",
            f"Umbral:    {regla.umbral} ({regla.operador.value}; "
            f"empate liquida {'YES' if regla.operador.empate_liquida_yes else 'NO'})",
            f"Vencimiento: {presentar(self.ficha.vencimiento_esperado, self.ficha.zona_presentacion)}"
            f"  | restante: {self.ficha.tiempo_restante_s(self.decidido_en):.0f}s",
            f"Indice:    {regla.indice} ({regla.agencia_fuente}), "
            f"promedio de {regla.ventana_promedio_s}s",
            f"Antiguedad: libro {self.calidad.antiguedad_libro_s}s, "
            f"spot {self.calidad.antiguedad_spot_s}s",
        ]

        cuantiles = self.prediccion.cuantiles
        if cuantiles:
            claves = sorted(cuantiles)
            lineas.append(
                "Rango de liquidacion: "
                + ", ".join(f"{k}={cuantiles[k]}" for k in claves)
            )
        for intervalo in self.prediccion.intervalos:
            lineas.append(
                f"  IC {float(intervalo.nivel):.0%}: "
                f"[{intervalo.inferior}, {intervalo.superior}]"
            )

        banda = self.prediccion.banda
        lineas.append(
            f"Probabilidad central: p_yes={self.prediccion.p_yes} "
            f"p_no={self.prediccion.p_no}"
        )
        if banda is None:
            lineas.append("Banda: no disponible (tamano monetario desactivado)")
        else:
            lineas.append(
                f"Banda aproximada de p_yes: [{banda.inferior}, {banda.superior}] "
                f"({banda.metodo}"
                f"{'' if banda.defendible else '; NO DEFENDIBLE'})"
            )
            robust = self.prediccion.p_robust(lado)
            lineas.append(
                f"Probabilidad conservadora del lado {lado.value}: {robust}"
            )

        compra = self.libro.mejor_compra_mils(lado)
        venta = self.libro.mejor_venta_mils(lado)
        lineas.append(
            f"Lado {lado.value}: compra={a_dolares(compra) if compra is not None else '-'} "
            f"venta={a_dolares(venta) if venta is not None else '-'}"
        )
        if self.coste_evaluado:
            lineas.append(
                "Coste para la cantidad: "
                + ", ".join(f"{k}={v}" for k, v in sorted(self.coste_evaluado.items()))
            )

        etiqueta = self.clase_importe.value.upper()
        lineas += [
            f"Cantidad propuesta: {self.propuesta.cantidad_simulada}",
            f"Capital en riesgo ({etiqueta}): {self.propuesta.simulated_amount}",
            f"Perdida maxima ({etiqueta}): {self.propuesta.perdida_maxima_simulada}",
            f"Importe sugerido real: {self.propuesta.suggested_live_amount}",
            f"Margen operativo exigido: {self.margen_operativo}",
            f"Estado de validacion: {self.ficha.estado_reglas.value}",
            f"Valido hasta: {a_iso(self.valid_until)}",
            f"DECISION: {'OPERAR' if self.opera else 'NO OPERAR'}",
        ]
        if not self.opera:
            lineas.append("Motivos:")
            lineas += [f"  - {m}" for m in self.motivos]
        if self.condiciones_invalidez:
            lineas.append("Caduca si:")
            lineas += [f"  - {c}" for c in self.condiciones_invalidez]
        return "\n".join(lineas)

    # -- registro -------------------------------------------------------

    def registro(self) -> dict:
        """Objeto plano para el almacen de decisiones."""
        lado = self.propuesta.lado
        return {
            "decision_id": self.decision_id,
            "decidido_en": a_iso(self.decidido_en),
            "valid_until": a_iso(self.valid_until),
            "condiciones_invalidez": list(self.condiciones_invalidez),
            "contrato": self.ficha.contrato,
            "serie": self.ficha.serie,
            "evento": self.ficha.evento,
            "horizonte_s": self.ficha.tiempo_restante_s(self.decidido_en),
            "version_reglas": self.ficha.version_reglas,
            "huella_ficha": self.ficha.huella(),
            "estado_reglas": self.ficha.estado_reglas.value,
            "version_configuracion": self.version_configuracion,
            "calidad": {
                "antiguedad_libro_s": self.calidad.antiguedad_libro_s,
                "antiguedad_spot_s": self.calidad.antiguedad_spot_s,
                "huecos_detectados": self.calidad.huecos_detectados,
                "secuencias_rotas": self.calidad.secuencias_rotas,
                "motivos": list(self.calidad.motivos),
            },
            "prediccion": self.prediccion.resumen(),
            "cotizaciones": {
                "libro_received_at": a_iso(self.libro.received_at),
                "mejor_compra_mils": self.libro.mejor_compra_mils(lado),
                "mejor_venta_mils": self.libro.mejor_venta_mils(lado),
                "spread_mils": self.libro.spread_mils(lado),
                "imbalance": (
                    str(self.libro.imbalance())
                    if self.libro.imbalance() is not None
                    else None
                ),
            },
            "costes": {k: str(v) for k, v in sorted(self.coste_evaluado.items())},
            "restricciones_activas": list(self.propuesta.restricciones_activas),
            "lado": lado.value,
            "clase_importe": self.clase_importe.value,
            "cantidad_propuesta": str(self.propuesta.cantidad_simulada),
            "cantidad_optima_sin_reduccion": str(
                self.propuesta.cantidad_optima_sin_reduccion
            ),
            "simulated_amount": str(self.propuesta.simulated_amount),
            "suggested_live_amount": str(self.propuesta.suggested_live_amount),
            "perdida_maxima": str(self.propuesta.perdida_maxima_simulada),
            "margen_operativo": str(self.margen_operativo),
            "opera": self.opera,
            "motivos_no_operar": list(self.motivos),
            "fill": self.fill,
            "resultado": self.resultado,
        }


def nuevo_decision_id(
    contrato: str, decidido_en: dt.datetime, version_configuracion: str
) -> str:
    """Identificador reproducible de una decision."""
    crudo = f"{contrato}|{a_iso(decidido_en)}|{version_configuracion}"
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


def caducidad(
    decidido_en: dt.datetime, antiguedad_max_s: float
) -> tuple[dt.datetime, tuple[str, ...]]:
    """``valid_until`` y las condiciones que invalidan la senal antes."""
    return (
        exigir_utc(decidido_en) + dt.timedelta(seconds=antiguedad_max_s),
        (
            "cambia la mejor compra o la mejor venta del lado elegido",
            "la profundidad al precio evaluado disminuye",
            f"el libro supera {antiguedad_max_s:.0f}s de antiguedad",
            "se detecta hueco de datos o secuencia rota",
            "se agota el limite de perdida diaria",
        ),
    )
