"""Etiquetas de rendimiento a ``h`` sesiones con la misma hora de inicio y de fin.

La etiqueta de la sesión ``t`` a horizonte ``h`` empieza a la hora de corte de
``t`` y termina a la misma hora de la sesión ``t + h`` del calendario bursátil:
una observación del viernes termina en la siguiente sesión hábil, no
necesariamente el lunes. Cada etiqueta guarda tres instantes en UTC:

* ``decision_at``: corte más la latencia supuesta (cuándo se podría actuar);
* ``label_end_at``: fin del periodo del rendimiento;
* ``label_available_at``: cuándo se conoce la etiqueta: el fin más el retraso
  de publicación o, si es posterior, la disponibilidad documentada de los
  precios inicial y final y de los dividendos que se suman.

Con una tabla de dividendos, ``retorno_log`` es el rendimiento total: un
dividendo cuya fecha ex abre dentro de ``(inicio, fin]`` se suma al precio
final, porque quien tenía el activo al inicio lo cobra. ``retorno_precio_log``
excluye los dividendos y ``dividendos`` guarda el monto sumado, para auditar la
diferencia. Si la consulta de dividendos más reciente es anterior al fin, el
rendimiento total queda ausente («sin dividendos confirmados»): un dividendo
anunciado después no estaría en la tabla. Sin tabla, las dos columnas son el
rendimiento de precio (un índice de precio como la referencia).

Entrenamiento y calibración solo pueden consultar etiquetas con
``label_available_at`` anterior o igual al instante simulado
(``etiquetas_maduras``). Si falta un precio, la etiqueta queda ausente con su
motivo; nunca se rellena.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calendario import CALENDARIO, _fecha, apertura, es_sesion, instante, sesion_desplazada

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


def _por_fecha(valores):
    if valores is None:
        return {}
    return {_fecha(f): v for f, v in pd.Series(valores).items()}


def _dividendos(tabla, codigo):
    """``(apertura_ex_utc, monto, disponible_utc)`` de cada dividendo y la cobertura de la tabla.

    La cobertura es el mayor ``consultado_utc`` (NaT si la tabla está vacía o no
    lo trae): hasta ese instante la lista está completa.
    """
    if tabla is None or len(tabla) == 0:
        return [], pd.NaT
    cobertura = pd.to_datetime(tabla["consultado_utc"], utc=True).max() if "consultado_utc" in tabla else pd.NaT
    salida = []
    for fila in pd.DataFrame(tabla).itertuples():
        fecha_ex = _fecha(fila.fecha_ex)
        if not es_sesion(fecha_ex, codigo):
            raise ValueError(f"fecha ex {fecha_ex} no es una sesión")
        disponible = getattr(fila, "disponible_utc", pd.NaT)
        if pd.isna(disponible):
            disponible = getattr(fila, "recibido_utc", pd.NaT)
        salida.append((apertura(fecha_ex, codigo), float(fila.monto), disponible))
    return salida, cobertura


def etiquetas_retorno(precios, hora="09:45", horizontes=(1, 5), latencia_s=0.0,
                      retraso_publicacion_s=0.0, codigo=CALENDARIO, disponibles=None,
                      motivos=None, dividendos=None) -> pd.DataFrame:
    """Rendimientos logarítmicos a ``horizontes`` sesiones desde ``hora`` hasta ``hora``.

    ``precios`` es una serie indexada por fecha de sesión con el precio a
    ``hora``; un NaN o una fecha ausente deja sin etiqueta a las observaciones
    que la necesitan. ``disponibles`` (instante UTC por sesión) retrasa la
    madurez hasta que el precio se publicó; ``motivos`` explica por qué falta un
    precio y pasa a la columna ``motivo``. ``dividendos`` (columnas ``fecha_ex``,
    ``monto``, ``disponible_utc`` o ``recibido_utc`` y ``consultado_utc``;
    puede estar vacía) entra en el rendimiento total y en la madurez.
    """
    serie = _serie_por_sesion(precios, codigo)
    disponibles, motivos = _por_fecha(disponibles), _por_fecha(motivos)
    pagos, cobertura = _dividendos(dividendos, codigo)
    latencia = pd.Timedelta(seconds=float(latencia_s))
    retraso = pd.Timedelta(seconds=float(retraso_publicacion_s))

    def motivo(fecha):
        texto = motivos.get(fecha)
        return texto if isinstance(texto, str) and texto else f"sin precio de la sesión {fecha}"

    filas = []
    for fecha in serie.index:
        inicio = instante(fecha, hora, codigo)
        p0 = serie[fecha]
        for h in horizontes:
            fila = {"sesion": fecha, "horizonte": int(h), "inicio_at": inicio,
                    "decision_at": inicio + latencia, "sesion_fin": None, "label_end_at": pd.NaT,
                    "label_available_at": pd.NaT, "precio_inicio": p0, "precio_fin": np.nan,
                    "dividendos": 0.0, "retorno_log": np.nan, "retorno_precio_log": np.nan, "estado": "ok",
                    "motivo": ""}
            try:
                fin_fecha = sesion_desplazada(fecha, h, codigo)
                fin = instante(fin_fecha, hora, codigo)
            except (_FueraDeCalendario, ValueError):
                fila["estado"] = "fin fuera del calendario"
                filas.append(fila)
                continue
            p1 = serie.get(fin_fecha, np.nan)
            cobrados = [(monto, disp) for abre, monto, disp in pagos if inicio < abre <= fin]
            publicado = [fin + retraso] + [pd.Timestamp(disponibles[f]) for f in (fecha, fin_fecha)
                                           if f in disponibles and not pd.isna(disponibles[f])]
            publicado += [pd.Timestamp(disp) for _, disp in cobrados if not pd.isna(disp)]
            dividendo = float(sum(monto for monto, _ in cobrados))
            fila.update(sesion_fin=fin_fecha, label_end_at=fin, label_available_at=max(publicado),
                        precio_fin=p1, dividendos=dividendo)
            if not np.isfinite(p0):
                fila.update(estado="sin precio inicial", motivo=motivo(fecha))
            elif not np.isfinite(p1):
                fila.update(estado="sin precio final", motivo=motivo(fin_fecha))
            else:
                fila["retorno_precio_log"] = float(np.log(p1 / p0))
                if dividendos is not None and not cobertura >= fin:
                    fila.update(estado="sin dividendos confirmados",
                                motivo=f"dividendos consultados hasta {cobertura}, antes del fin {fin}"
                                if not pd.isna(cobertura) else "sin consulta de dividendos")
                else:
                    fila["retorno_log"] = float(np.log((p1 + dividendo) / p0))
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
