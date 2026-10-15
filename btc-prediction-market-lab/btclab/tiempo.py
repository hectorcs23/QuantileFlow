"""Tiempo: UTC como referencia unica, zonas IANA solo para presentacion.

Reglas que este modulo hace cumplir:

* Todo instante interno es ``datetime`` consciente de zona y en UTC.
* ``event_time`` (cuando ocurrio segun la fuente) y ``received_at`` (cuando lo
  recibimos) son campos distintos y nunca se confunden.
* La disponibilidad de un dato se juzga por ``received_at``: un mensaje con
  ``event_time`` antiguo recibido despues de decidir no estaba disponible.
* La presentacion local usa zona IANA y por tanto respeta los cambios de
  horario; nunca se usa un desplazamiento fijo.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc

#: Zona de presentacion por omision. El contrato se expresa en hora de Nueva York
#: ("5 PM EDT" en las reglas de Kalshi), que cambia a EST en invierno; usar la
#: zona IANA evita codificar el desplazamiento.
ZONA_PRESENTACION = "America/New_York"


class ErrorTiempo(ValueError):
    """Instante invalido o ingenuo (sin zona)."""


def ahora() -> dt.datetime:
    """Instante actual en UTC."""
    return dt.datetime.now(tz=UTC)


def exigir_utc(momento: dt.datetime, campo: str = "momento") -> dt.datetime:
    """Devuelve ``momento`` en UTC o falla si es ingenuo.

    Un ``datetime`` sin zona es ambiguo y es la causa habitual de fugas
    temporales, asi que se rechaza en lugar de asumir UTC.
    """
    if not isinstance(momento, dt.datetime):
        raise ErrorTiempo(f"{campo} no es datetime: {momento!r}")
    if momento.tzinfo is None or momento.tzinfo.utcoffset(momento) is None:
        raise ErrorTiempo(f"{campo} es ingenuo (sin zona); se exige UTC explicito")
    return momento.astimezone(UTC)


def desde_iso(texto: str, campo: str = "momento") -> dt.datetime:
    """Convierte ISO-8601 a UTC. Acepta el sufijo ``Z``."""
    if not isinstance(texto, str) or not texto:
        raise ErrorTiempo(f"{campo} vacio o no textual: {texto!r}")
    limpio = texto.strip().replace("Z", "+00:00")
    try:
        momento = dt.datetime.fromisoformat(limpio)
    except ValueError as exc:
        raise ErrorTiempo(f"{campo} no es ISO-8601: {texto!r}") from exc
    return exigir_utc(momento, campo)


def a_iso(momento: dt.datetime) -> str:
    """Serializa a ISO-8601 en UTC con sufijo ``Z``, en milisegundos."""
    utc = exigir_utc(momento)
    return utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def desde_epoch(segundos: float, campo: str = "epoch") -> dt.datetime:
    """Convierte segundos epoch a UTC."""
    try:
        return dt.datetime.fromtimestamp(float(segundos), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise ErrorTiempo(f"{campo} invalido: {segundos!r}") from exc


def a_epoch(momento: dt.datetime) -> int:
    """Segundos epoch enteros (truncados) de un instante UTC."""
    return int(exigir_utc(momento).timestamp())


def presentar(momento: dt.datetime, zona: str = ZONA_PRESENTACION) -> str:
    """Texto legible en zona IANA, con el nombre del desplazamiento vigente.

    Se usa solo para mostrar. El resultado incluye la abreviatura (EDT/EST) para
    que quede constancia de que el cambio de horario fue aplicado por la zona y
    no por una constante.
    """
    local = exigir_utc(momento).astimezone(ZoneInfo(zona))
    return f"{local.isoformat(timespec='seconds')} ({local.tzname()})"


def antiguedad_s(momento: dt.datetime, referencia: dt.datetime) -> float:
    """Segundos entre ``momento`` y ``referencia`` (positivo si es pasado)."""
    return (exigir_utc(referencia) - exigir_utc(momento)).total_seconds()


@dataclass(frozen=True)
class Observacion:
    """Dato con su doble marca temporal y su procedencia.

    ``event_time`` es lo que dice la fuente; ``received_at`` es cuando entro a
    nuestro proceso. Las uniones temporales usan ``received_at``.
    """

    event_time: dt.datetime
    received_at: dt.datetime
    fuente: str
    payload: dict
    secuencia: int | None = None

    def __post_init__(self) -> None:
        exigir_utc(self.event_time, "event_time")
        exigir_utc(self.received_at, "received_at")
        if not self.fuente:
            raise ErrorTiempo("fuente vacia")

    @property
    def latencia_s(self) -> float:
        """Retraso observado entre el evento y su recepcion.

        Puede ser negativa si el reloj de la fuente adelanta al nuestro; se
        reporta tal cual en lugar de recortarla, porque la desalineacion de
        relojes es un hallazgo que debe quedar registrado.
        """
        return antiguedad_s(self.event_time, self.received_at)

    def disponible_en(self, momento: dt.datetime) -> bool:
        """True si la observacion ya habia sido recibida en ``momento``."""
        return exigir_utc(self.received_at) <= exigir_utc(momento)
