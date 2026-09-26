"""Calendario bursátil real e instantes contractuales en UTC.

Los tiempos se guardan en UTC y se convierten a Nueva York solo para el
calendario y la presentación. Las sesiones, feriados, cierres anticipados y
cierres extraordinarios salen de ``exchange_calendars`` (calendario ``XNYS``),
no de reglas escritas a mano.

* ``instante(fecha, "09:45")``: hora local de una sesión convertida a UTC.
* ``instante_liquidacion``: liquidación PM al cierre de la sesión de
  vencimiento (13:00 en un cierre anticipado); AM a la apertura, porque el
  valor de liquidación sale de los precios de apertura.
* ``plazo_anios``: tiempo entre dos instantes con base explícita (ACT/365 por
  omisión), en segundos y no en días enteros.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd

NUEVA_YORK = ZoneInfo("America/New_York")
CALENDARIO = "XNYS"


@lru_cache(maxsize=4)
def calendario(codigo=CALENDARIO):
    """Calendario de ``exchange_calendars`` (sesiones desde 2004 hasta un año adelante)."""
    import exchange_calendars as xc

    return xc.get_calendar(codigo, start="2004-01-02")


def _fecha(fecha) -> dt.date:
    return pd.Timestamp(fecha).date()


def es_sesion(fecha, codigo=CALENDARIO) -> bool:
    return bool(calendario(codigo).is_session(pd.Timestamp(_fecha(fecha))))


def sesiones(desde, hasta, codigo=CALENDARIO) -> list[dt.date]:
    """Sesiones entre dos fechas, ambas incluidas."""
    return [s.date() for s in calendario(codigo).sessions_in_range(pd.Timestamp(_fecha(desde)),
                                                                   pd.Timestamp(_fecha(hasta)))]


def sesion_desplazada(fecha, n, codigo=CALENDARIO) -> dt.date:
    """Sesión que está ``n`` sesiones después (o antes, si ``n < 0``) de ``fecha``."""
    return calendario(codigo).session_offset(pd.Timestamp(_fecha(fecha)), int(n)).date()


def sesiones_entre(desde, hasta, codigo=CALENDARIO) -> int:
    """Sesiones transcurridas de ``desde`` a ``hasta`` (0 si son la misma)."""
    return int(calendario(codigo).sessions_distance(pd.Timestamp(_fecha(desde)),
                                                    pd.Timestamp(_fecha(hasta)))) - 1


def apertura(fecha, codigo=CALENDARIO) -> pd.Timestamp:
    return calendario(codigo).session_open(pd.Timestamp(_fecha(fecha))).tz_convert("UTC")


def cierre(fecha, codigo=CALENDARIO) -> pd.Timestamp:
    return calendario(codigo).session_close(pd.Timestamp(_fecha(fecha))).tz_convert("UTC")


def instante(fecha, hora="09:45", codigo=CALENDARIO) -> pd.Timestamp:
    """Hora local de Nueva York de una sesión, en UTC; debe caer dentro de la sesión."""
    fecha = _fecha(fecha)
    if not es_sesion(fecha, codigo):
        raise ValueError(f"{fecha} no es una sesión de {codigo}")
    horas, minutos = (int(x) for x in hora.split(":"))
    local = dt.datetime.combine(fecha, dt.time(horas, minutos), tzinfo=NUEVA_YORK)
    utc = pd.Timestamp(local).tz_convert("UTC")
    if not apertura(fecha, codigo) <= utc <= cierre(fecha, codigo):
        raise ValueError(f"{hora} de {fecha} cae fuera de la sesión")
    return utc


def instante_liquidacion(fecha_vencimiento, liquidacion, codigo=CALENDARIO) -> pd.Timestamp:
    """Instante contractual de liquidación: ``"PM"`` al cierre y ``"AM"`` a la apertura."""
    fecha = _fecha(fecha_vencimiento)
    if not es_sesion(fecha, codigo):
        raise ValueError(f"el vencimiento {fecha} no es una sesión de {codigo}")
    if liquidacion == "PM":
        return cierre(fecha, codigo)
    if liquidacion == "AM":
        return apertura(fecha, codigo)
    raise ValueError("liquidacion debe ser 'AM' o 'PM'")


def plazo_anios(desde_utc, hasta_utc, base_dias=365.0) -> float:
    """Años entre dos instantes con base ``base_dias`` (ACT/365 por omisión)."""
    segundos = (pd.Timestamp(hasta_utc) - pd.Timestamp(desde_utc)).total_seconds()
    return segundos / (base_dias * 86400.0)


def segundos_locales(instante_utc, fecha_sesion) -> float:
    """Segundos desde la medianoche de Nueva York de ``fecha_sesion`` (NaN si el instante es nulo)."""
    if instante_utc is None or pd.isna(instante_utc):
        return float("nan")
    medianoche = pd.Timestamp(dt.datetime.combine(_fecha(fecha_sesion), dt.time(0, 0), tzinfo=NUEVA_YORK))
    return (pd.Timestamp(instante_utc) - medianoche).total_seconds()
