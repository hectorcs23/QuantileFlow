"""Uniones temporales sin informacion futura (Paso 2).

Toda union mira **hacia atras** y usa ``received_at``, no ``event_time``. Un
mensaje con marca antigua recibido despues de decidir no estaba disponible, y
usarlo es la fuga temporal mas comun en este tipo de problema.

Lo que este modulo prohibe por construccion:

* Usar un registro cuyo ``received_at`` sea posterior al momento de decision.
* Usar una vela que aun no habia cerrado en ese momento.
* Rellenar huecos con datos posteriores: un hueco se devuelve como ``None`` y
  queda registrado.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Sequence

from .tiempo import Observacion, exigir_utc


class ErrorUnion(ValueError):
    """Union mal planteada."""


@dataclass(frozen=True)
class ResultadoUnion:
    """Lo que se encontro disponible, y por que falta si falta."""

    observacion: Observacion | None
    antiguedad_s: float | None
    motivo: str = ""

    @property
    def disponible(self) -> bool:
        return self.observacion is not None


def ultimo_disponible(
    observaciones: Sequence[Observacion],
    momento: dt.datetime,
    antiguedad_max_s: float | None = None,
) -> ResultadoUnion:
    """Ultima observacion recibida en o antes de ``momento``.

    ``antiguedad_max_s`` descarta cotizaciones caducadas: en un mercado de 15
    minutos un dato de hace un minuto puede ser inservible, y presentarlo como
    vigente es precisamente lo que el Paso 12 prohibe.
    """
    instante = exigir_utc(momento)
    candidata: Observacion | None = None
    for observacion in observaciones:
        if observacion.received_at <= instante:
            if candidata is None or observacion.received_at > candidata.received_at:
                candidata = observacion

    if candidata is None:
        return ResultadoUnion(None, None, "sin observaciones recibidas antes del momento")

    antiguedad = (instante - candidata.received_at).total_seconds()
    if antiguedad_max_s is not None and antiguedad > antiguedad_max_s:
        return ResultadoUnion(
            None,
            antiguedad,
            f"cotizacion caducada: {antiguedad:.3f}s > {antiguedad_max_s:.3f}s",
        )
    return ResultadoUnion(candidata, antiguedad)


def unir_hacia_atras(
    momentos: Sequence[dt.datetime],
    observaciones: Sequence[Observacion],
    antiguedad_max_s: float | None = None,
) -> list[ResultadoUnion]:
    """Union as-of hacia atras para una lista de momentos de decision."""
    ordenadas = sorted(observaciones, key=lambda o: o.received_at)
    return [
        ultimo_disponible(ordenadas, momento, antiguedad_max_s) for momento in momentos
    ]


def vela_cerrada_en(
    fin_periodo: dt.datetime, momento: dt.datetime, margen_s: float = 0.0
) -> bool:
    """True si la vela que termina en ``fin_periodo`` ya habia cerrado.

    ``margen_s`` permite exigir un retraso adicional de publicacion: la vela no
    solo tiene que haber terminado, tambien tiene que haber estado disponible.
    """
    return exigir_utc(fin_periodo) + dt.timedelta(seconds=margen_s) <= exigir_utc(
        momento
    )


def velas_disponibles(
    velas: Sequence[dict],
    momento: dt.datetime,
    clave_fin: str = "fin_periodo",
    margen_s: float = 0.0,
) -> list[dict]:
    """Filtra a las velas cerradas y publicadas en ``momento``.

    Las velas deben traer su fin de periodo como ``datetime`` en UTC. Una vela en
    curso se descarta: usar su cierre equivaldria a conocer el futuro del minuto.
    """
    salida = []
    for vela in velas:
        fin = vela.get(clave_fin)
        if fin is None:
            raise ErrorUnion(f"vela sin {clave_fin}: {vela!r}")
        if vela_cerrada_en(fin, momento, margen_s):
            salida.append(vela)
    return salida


@dataclass(frozen=True)
class Hueco:
    """Intervalo sin datos entre dos recepciones consecutivas."""

    desde: dt.datetime
    hasta: dt.datetime

    @property
    def duracion_s(self) -> float:
        return (self.hasta - self.desde).total_seconds()


def detectar_huecos(
    observaciones: Sequence[Observacion], intervalo_esperado_s: float
) -> tuple[Hueco, ...]:
    """Intervalos entre recepciones que exceden lo esperado.

    Un hueco no se interpola: queda registrado para el reporte de cobertura y
    para decidir no operar.
    """
    if intervalo_esperado_s <= 0:
        raise ErrorUnion("intervalo esperado no positivo")
    ordenadas = sorted(observaciones, key=lambda o: o.received_at)
    huecos = []
    for previa, siguiente in zip(ordenadas, ordenadas[1:]):
        separacion = (siguiente.received_at - previa.received_at).total_seconds()
        if separacion > intervalo_esperado_s:
            huecos.append(Hueco(previa.received_at, siguiente.received_at))
    return tuple(huecos)


def detectar_saltos_secuencia(
    observaciones: Sequence[Observacion],
) -> tuple[tuple[int, int], ...]:
    """Pares ``(previa, siguiente)`` con secuencia no consecutiva.

    Tras un salto, el libro reconstruido por deltas deja de ser valido y hace
    falta un snapshot nuevo.
    """
    con_secuencia = [o for o in observaciones if o.secuencia is not None]
    ordenadas = sorted(con_secuencia, key=lambda o: o.secuencia)
    saltos = []
    for previa, siguiente in zip(ordenadas, ordenadas[1:]):
        if siguiente.secuencia != previa.secuencia + 1:
            saltos.append((previa.secuencia, siguiente.secuencia))
    return tuple(saltos)
