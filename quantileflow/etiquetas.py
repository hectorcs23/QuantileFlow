"""Etiquetas de rendimiento a ``h`` sesiones con la misma hora de inicio y de fin.

La etiqueta de la sesión ``t`` a horizonte ``h`` empieza a la hora de corte de
``t`` y termina a la misma hora de la sesión ``t + h`` del calendario bursátil:
una observación del viernes termina en la siguiente sesión hábil, no
necesariamente el lunes. Cada etiqueta guarda tres instantes en UTC:

* ``decision_at``: corte más la latencia supuesta (cuándo se podría actuar);
* ``label_end_at``: fin del periodo del rendimiento;
* ``label_available_at``: cuándo se conoce la etiqueta (fin más el retraso de
  publicación).

Entrenamiento y calibración solo pueden consultar etiquetas con
``label_available_at`` anterior o igual al instante simulado
(``etiquetas_maduras``). Si falta un precio, la etiqueta queda ausente con su
motivo; nunca se rellena.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calendario import CALENDARIO, _fecha, es_sesion, instante, sesion_desplazada

try:  # el error concreto depende de la versión de exchange_calendars
    from exchange_calendars.errors import RequestedSessionOutOfBounds as _FueraDeCalendario
except ImportError:  # pragma: no cover
    _FueraDeCalendario = ValueError


def _serie_por_sesion(precios, codigo):
    serie = pd.Series(np.asarray(pd.Series(precios).to_numpy(), dtype=float),
                      index=[_fecha(f) for f in pd.Series(precios).index])
    if serie.index.has_duplicates:
        raise ValueError("hay fechas repetidas en la serie de precios")
    no_sesiones = [f for f in serie.index if not es_sesion(f, codigo)]
    if no_sesiones:
        raise ValueError(f"fechas que no son sesiones: {no_sesiones[:3]}")
    return serie.sort_index()


def etiquetas_retorno(precios, hora="09:45", horizontes=(1, 5), latencia_s=0.0,
                      retraso_publicacion_s=0.0, codigo=CALENDARIO) -> pd.DataFrame:
    """Rendimientos logarítmicos a ``horizontes`` sesiones desde ``hora`` hasta ``hora``.

    ``precios`` es una serie indexada por fecha de sesión con el precio a
    ``hora``; un NaN o una fecha ausente deja sin etiqueta a las observaciones
    que la necesitan.
    """
    serie = _serie_por_sesion(precios, codigo)
    latencia = pd.Timedelta(seconds=float(latencia_s))
    retraso = pd.Timedelta(seconds=float(retraso_publicacion_s))
    filas = []
    for fecha in serie.index:
        inicio = instante(fecha, hora, codigo)
        p0 = serie[fecha]
        for h in horizontes:
            fila = {"sesion": fecha, "horizonte": int(h), "inicio_at": inicio,
                    "decision_at": inicio + latencia, "sesion_fin": None, "label_end_at": pd.NaT,
                    "label_available_at": pd.NaT, "precio_inicio": p0, "precio_fin": np.nan,
                    "retorno_log": np.nan, "estado": "ok"}
            try:
                fin_fecha = sesion_desplazada(fecha, h, codigo)
                fin = instante(fin_fecha, hora, codigo)
            except (_FueraDeCalendario, ValueError):
                fila["estado"] = "fin fuera del calendario"
                filas.append(fila)
                continue
            p1 = serie.get(fin_fecha, np.nan)
            fila.update(sesion_fin=fin_fecha, label_end_at=fin, label_available_at=fin + retraso,
                        precio_fin=p1)
            if not np.isfinite(p0):
                fila["estado"] = "sin precio inicial"
            elif not np.isfinite(p1):
                fila["estado"] = "sin precio final"
            else:
                fila["retorno_log"] = float(np.log(p1 / p0))
            filas.append(fila)
    return pd.DataFrame(filas)


def etiquetas_maduras(etiquetas: pd.DataFrame, instante_simulado) -> pd.DataFrame:
    """Etiquetas completas que ya se conocían en ``instante_simulado`` (UTC)."""
    instante_simulado = pd.Timestamp(instante_simulado)
    conocidas = etiquetas["label_available_at"].notna() & (etiquetas["label_available_at"] <= instante_simulado)
    return etiquetas[conocidas & (etiquetas["estado"] == "ok")]


def movimiento_previo(precios, codigo=CALENDARIO) -> pd.Series:
    """Rendimiento logarítmico desde la sesión anterior del calendario hasta cada sesión.

    Es el movimiento ya observado del subyacente al decidir; NaN si falta la
    sesión anterior.
    """
    serie = _serie_por_sesion(precios, codigo)
    salida = {}
    for fecha in serie.index:
        previa = sesion_desplazada(fecha, -1, codigo)
        p_previo = serie.get(previa, np.nan)
        salida[fecha] = float(np.log(serie[fecha] / p_previo)) if np.isfinite(p_previo) else np.nan
    return pd.Series(salida, name="retorno_previo")
