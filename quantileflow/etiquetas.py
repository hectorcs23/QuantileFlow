"""Etiquetas de rendimiento a ``h`` sesiones con la misma hora de inicio y de fin.

La etiqueta de la sesión ``t`` a horizonte ``h`` empieza a la hora de corte de
``t`` y termina a la misma hora de la sesión ``t + h`` del calendario bursátil:
una observación del viernes termina en la siguiente sesión hábil, no
necesariamente el lunes. Cada etiqueta guarda tres instantes en UTC:

* ``decision_at``: corte más la latencia supuesta (cuándo se podría actuar);
* ``label_end_at``: fin del periodo del rendimiento;
* ``label_available_at``: cuándo se conoce la etiqueta: el fin más el retraso
  de publicación o, si es posterior, la disponibilidad documentada de los
  precios inicial y final y, con dividendos, la consulta que la habilita.

Sin dividendos (un índice de precio como la referencia), ``retorno_log`` es el
rendimiento de precio. Con dividendos, es el **total**: un dividendo cuya fecha
ex abre dentro de ``(inicio, fin]`` se suma al precio final, porque quien
tenía el activo al inicio lo cobra; ``retorno_precio_log`` va aparte y
``dividendos`` guarda el monto sumado (NaN si el rendimiento total falta).

Política de dividendos (el proveedor no garantiza cuándo publica un evento):

* **Consulta habilitante**: la primera consulta **completa**, recibida después
  del fin, cuyo intervalo cubre el periodo. Si el proveedor filtra por una
  fecha posterior a la ex (``process_date``), el intervalo debe llegar hasta
  el fin más ``margen_proceso_dias``. Sin ella, el rendimiento total queda
  ausente («sin dividendos confirmados»). Su recepción entra en la madurez: una
  consulta posterior no vuelve disponible una etiqueta en el pasado.
* **Provisional**: el valor con los dividendos conocidos al madurar.
* **Reconciliada**: una consulta completa que cubre el periodo llegó al menos
  ``margen_proceso_dias`` después del fin, cuando cualquier dividendo del
  periodo ya fue procesado y el proveedor lo devuelve siempre.
* **Revisada**: una versión posterior de los dividendos (un anuncio tardío,
  una corrección o una retirada) cambió el valor. La etiqueta gana una fila por
  versión, con ``vigente_desde_utc`` y ``vigente_hasta_utc``; la anterior se
  conserva.

``conocido_hasta`` reconstruye las etiquetas con lo que se sabía en un instante.
Entrenamiento y calibración solo pueden consultar, en un instante simulado,
las versiones vigentes y ya maduras (``etiquetas_maduras``). Si falta un precio,
la etiqueta queda ausente con su motivo; nunca se rellena.
"""
from __future__ import annotations

from collections import namedtuple

import numpy as np
import pandas as pd

from .calendario import CALENDARIO, NUEVA_YORK, _fecha, apertura, es_sesion, instante, sesion_desplazada

try:  # el error concreto depende de la versión de exchange_calendars
    from exchange_calendars.errors import RequestedSessionOutOfBounds as _FueraDeCalendario
except ImportError:  # pragma: no cover
    _FueraDeCalendario = ValueError

POLITICAS = ("provisional", "reconciliada")
INSTANTES = ("inicio_at", "decision_at", "label_end_at", "label_available_at", "vigente_desde_utc",
             "vigente_hasta_utc", "consulta_habilitante_utc", "reconciliada_utc")
_Version = namedtuple("_Version", "abre monto conocida hasta")
_Consulta = namedtuple("_Consulta", "recibido desde hasta por_ex")


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


def _instante(valor):
    return pd.NaT if valor is None or pd.isna(valor) else pd.Timestamp(valor)


def _versiones(tabla, codigo, conocido_hasta):
    """Versiones de dividendos conocidas hasta ``conocido_hasta``: apertura ex, monto, desde y hasta cuándo valen.

    Una versión se conoce desde su anuncio documentado o, si falta, desde la
    consulta que la trajo; un retiro posterior a ``conocido_hasta`` todavía no
    se sabía.
    """
    if tabla is None or len(tabla) == 0:
        return []
    salida = []
    for fila in pd.DataFrame(tabla).itertuples():
        fecha_ex = _fecha(fila.fecha_ex)
        if not es_sesion(fecha_ex, codigo):
            raise ValueError(f"fecha ex {fecha_ex} no es una sesión")
        conocida = _instante(getattr(fila, "disponible_utc", None))
        if pd.isna(conocida):
            conocida = _instante(getattr(fila, "recibido_utc", None))
        hasta = _instante(getattr(fila, "retirado_utc", None))
        if conocido_hasta is not None:
            if conocida > conocido_hasta:
                continue
            if not pd.isna(hasta) and hasta > conocido_hasta:
                hasta = pd.NaT
        salida.append(_Version(apertura(fecha_ex, codigo), float(fila.monto), conocida, hasta))
    return salida


def _consultas(tabla, conocido_hasta):
    """Consultas de cobertura conocidas hasta ``conocido_hasta``: completas y el resto, por separado."""
    if tabla is None or len(tabla) == 0:
        return [], 0
    completas, otras = [], 0
    for fila in pd.DataFrame(tabla).itertuples():
        recibido = _instante(fila.recibido_utc)
        if conocido_hasta is not None and recibido > conocido_hasta:
            continue
        if fila.estado != "completa":
            otras += 1
            continue
        completas.append(_Consulta(recibido, _fecha(fila.desde), _fecha(fila.hasta), fila.campo_fecha == "ex_date"))
    return sorted(completas), otras


def _cubre(consulta, inicio, fin, margen):
    """Si el intervalo de la consulta incluye todo dividendo con fecha ex en el periodo.

    Con un filtro por una fecha posterior a la ex (proceso o pago), el intervalo
    debe llegar hasta el fin más el margen de procesamiento.
    """
    dia_inicio, dia_fin = inicio.tz_convert(NUEVA_YORK).date(), fin.tz_convert(NUEVA_YORK).date()
    tope = dia_fin if consulta.por_ex else (fin + margen).tz_convert(NUEVA_YORK).date()
    return consulta.desde <= dia_inicio and consulta.hasta >= tope


def _con_dividendos(base, p0, p1, inicio, fin, versiones, consultas, otras, margen):
    """Filas (una por versión) del rendimiento total de una etiqueta con los dos precios."""
    cubren = [q for q in consultas if _cubre(q, inicio, fin, margen)]
    habilitantes = [q.recibido for q in cubren if q.recibido >= fin]
    if not habilitantes:
        if cubren:
            motivo = (f"la última consulta completa de dividendos que cubre el periodo ({cubren[-1].recibido}) "
                      f"es anterior al fin ({fin})")
        elif consultas:
            motivo = "ninguna consulta completa de dividendos cubre el periodo"
        else:
            motivo = "sin consulta completa de dividendos"
        if otras:
            motivo += f"; {otras} consultas parciales o fallidas no cuentan"
        return [dict(base, estado="sin dividendos confirmados", motivo=motivo,
                     vigente_desde_utc=base["label_available_at"])]
    habilitante = min(habilitantes)
    disponible = max(base["label_available_at"], habilitante)
    propias = [v for v in versiones if inicio < v.abre <= fin]
    cambios = sorted({t for v in propias for t in (v.conocida, v.hasta) if not pd.isna(t) and t > disponible})
    tramos = []
    for t in [disponible] + cambios:
        monto = float(sum(v.monto for v in propias if v.conocida <= t and (pd.isna(v.hasta) or v.hasta > t)))
        if not tramos or abs(monto - tramos[-1][1]) > 1e-12:
            tramos.append((t, monto))
    filas = []
    for i, (desde, monto) in enumerate(tramos):
        hasta = tramos[i + 1][0] if i + 1 < len(tramos) else pd.NaT
        reconciliada = next((q.recibido for q in cubren if q.recibido >= max(fin + margen, desde)
                             and (pd.isna(hasta) or q.recibido < hasta)), pd.NaT)
        estado = "revisada" if i else ("reconciliada" if not pd.isna(reconciliada) else "provisional")
        filas.append(dict(base, label_available_at=disponible, dividendos=monto,
                          retorno_log=float(np.log((p1 + monto) / p0)), version=i + 1, vigente_desde_utc=desde,
                          vigente_hasta_utc=hasta, estado_dividendos=estado, consulta_habilitante_utc=habilitante,
                          reconciliada_utc=reconciliada))
    return filas


def etiquetas_retorno(precios, hora="09:45", horizontes=(1, 5), latencia_s=0.0,
                      retraso_publicacion_s=0.0, codigo=CALENDARIO, disponibles=None,
                      motivos=None, dividendos=None, cobertura=None, margen_proceso_dias=60.0,
                      conocido_hasta=None) -> pd.DataFrame:
    """Rendimientos logarítmicos a ``horizontes`` sesiones desde ``hora`` hasta ``hora``.

    ``precios`` es una serie indexada por fecha de sesión con el precio a
    ``hora``; un NaN o una fecha ausente deja sin etiqueta a las observaciones
    que la necesitan. ``disponibles`` (instante UTC por sesión) retrasa la
    madurez hasta que el precio se publicó; ``motivos`` explica por qué falta un
    precio y pasa a la columna ``motivo``.

    Con ``dividendos`` (versiones, esquema ``contrato.DIVIDENDOS``) o
    ``cobertura`` (consultas, ``contrato.COBERTURA_DIVIDENDOS``), el
    rendimiento es total y sigue la política del módulo; cualquiera de las dos
    puede estar vacía. ``conocido_hasta`` limita todo a lo recibido hasta ese
    instante.
    """
    serie = _serie_por_sesion(precios, codigo)
    disponibles, motivos = _por_fecha(disponibles), _por_fecha(motivos)
    total = dividendos is not None or cobertura is not None
    corte = None if conocido_hasta is None else pd.Timestamp(conocido_hasta)
    versiones = _versiones(dividendos, codigo, corte)
    consultas, otras = _consultas(cobertura, corte)
    margen = pd.Timedelta(days=float(margen_proceso_dias))
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
                    "dividendos": np.nan if total else 0.0, "retorno_log": np.nan, "retorno_precio_log": np.nan,
                    "estado": "ok",
                    "motivo": "", "version": 1, "vigente_desde_utc": pd.NaT, "vigente_hasta_utc": pd.NaT,
                    "estado_dividendos": "", "consulta_habilitante_utc": pd.NaT, "reconciliada_utc": pd.NaT}
            try:
                fin_fecha = sesion_desplazada(fecha, h, codigo)
                fin = instante(fin_fecha, hora, codigo)
            except (_FueraDeCalendario, ValueError):
                fila["estado"] = "fin fuera del calendario"
                filas.append(fila)
                continue
            p1 = serie.get(fin_fecha, np.nan)
            publicado = [fin + retraso] + [pd.Timestamp(disponibles[f]) for f in (fecha, fin_fecha)
                                           if f in disponibles and not pd.isna(disponibles[f])]
            fila.update(sesion_fin=fin_fecha, label_end_at=fin, label_available_at=max(publicado), precio_fin=p1)
            fila["vigente_desde_utc"] = fila["label_available_at"]
            if not np.isfinite(p0):
                fila.update(estado="sin precio inicial", motivo=motivo(fecha))
            elif not np.isfinite(p1):
                fila.update(estado="sin precio final", motivo=motivo(fin_fecha))
            else:
                fila["retorno_precio_log"] = float(np.log(p1 / p0))
                if total:
                    filas += _con_dividendos(fila, p0, p1, inicio, fin, versiones, consultas, otras, margen)
                    continue
                fila.update(retorno_log=fila["retorno_precio_log"], estado_dividendos="no aplica",
                            reconciliada_utc=fila["label_available_at"])
            filas.append(fila)
    tabla = pd.DataFrame(filas)
    for columna in INSTANTES:  # siempre con zona y en microsegundos, también si una columna queda vacía
        if columna in tabla:
            tabla[columna] = pd.to_datetime(tabla[columna], utc=True).dt.as_unit("us")
    return tabla


def etiquetas_vigentes(etiquetas: pd.DataFrame) -> pd.DataFrame:
    """La versión vigente (la última conocida) de cada etiqueta."""
    if "vigente_hasta_utc" not in etiquetas:
        return etiquetas
    return etiquetas[etiquetas["vigente_hasta_utc"].isna()]


def etiquetas_maduras(etiquetas: pd.DataFrame, instante_simulado, politica="provisional") -> pd.DataFrame:
    """Etiquetas completas que ya se conocían en ``instante_simulado`` (UTC), en su versión de ese instante.

    Con ``politica="reconciliada"``, solo las ya reconciliadas en ese instante.
    """
    if politica not in POLITICAS:
        raise ValueError(f"politica debe ser una de {POLITICAS}")
    t = pd.Timestamp(instante_simulado)
    e = etiquetas
    conocidas = e["label_available_at"].notna() & (e["label_available_at"] <= t) & (e["estado"] == "ok")
    if "vigente_desde_utc" in e:
        conocidas &= (e["vigente_desde_utc"] <= t) & (e["vigente_hasta_utc"].isna() | (e["vigente_hasta_utc"] > t))
    if politica == "reconciliada":
        conocidas &= e["reconciliada_utc"].notna() & (e["reconciliada_utc"] <= t)
    return e[conocidas]


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
