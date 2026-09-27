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

Política de dividendos. El proveedor no garantiza cuándo publica un evento,
así que la política separa tres cosas: la madurez, la aceptación y las
discrepancias.

* **Madurez** (``label_available_at``): llega la **consulta habilitante**, la
  primera consulta completa, recibida después del fin, que puede confirmar
  dividendos (tipos con dividendos en efectivo, calidad ``complete`` y un campo
  de fecha soportado) y cuyo intervalo cubre el periodo. Si el proveedor filtra
  por una fecha posterior a la ex (``process_date``), el intervalo debe llegar
  hasta el fin más ``margen_proceso_dias``. Sin ella, el rendimiento total queda
  ausente («sin dividendos confirmados»). Una consulta posterior no vuelve
  disponible una etiqueta en el pasado.
* **Provisional**: el valor con los dividendos conocidos en cada momento.
* **Aceptada** bajo la política: una de esas consultas llegó al menos
  ``margen_proceso_dias`` después del fin (y del último cambio de valor o de la
  última discrepancia resuelta) sin discrepancias abiertas. Para entonces el
  proveedor ya procesó los dividendos del periodo, y los procesados los devuelve
  siempre; pero 60 días son una regla operativa, no una garantía de
  completitud.
* **Pendiente**: un dividendo del periodo tiene una discrepancia sin resolver
  (faltó en una consulta comparable o, cancelado por una resolución, el
  proveedor lo trae con otros valores). El valor se conserva para diagnóstico,
  pero la etiqueta no se acepta: ni el paso del tiempo ni repetir la ausencia la
  resuelven, solo evidencia fechada (``alpaca.normalizar_eventos``).

Cada etiqueta se parte en **tramos** de valor y estado constantes
(``vigente_desde_utc``, ``vigente_hasta_utc``); ``version`` cuenta los cambios
de valor. ``conocido_hasta`` reconstruye las etiquetas con lo que se sabía en un
instante, y ``etiquetas_maduras`` da la vista de ese instante: el tramo vigente,
sin nada que se supiera después. Si falta un precio, la etiqueta queda ausente
con su motivo; nunca se rellena.
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

POLITICAS = ("provisional", "aceptada")
INSTANTES = ("inicio_at", "decision_at", "label_end_at", "label_available_at", "vigente_desde_utc",
             "vigente_hasta_utc", "consulta_habilitante_utc")
CALIDADES_COBERTURA = ("complete",)  # los eventos procesados siempre vuelven; con "all" hay registros sin fecha ex
CAMPOS_POR_EX = ("ex_date",)
CAMPOS_POSTERIORES_A_EX = ("process_date", "payable_date")
_Version = namedtuple("_Version", "abre monto conocida hasta discrepancia desde_discrepancia fecha_ex")
_DISCREPANCIAS = {"ausente": "ausente en una consulta comparable",
                  "reaparece_cancelado": "cancelado por una resolución y de nuevo en el proveedor con otros valores"}
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
    """Versiones de dividendos conocidas hasta ``conocido_hasta``: apertura ex, monto, vigencia y discrepancia.

    Una versión se conoce desde su anuncio documentado o, si falta, desde la
    consulta que la trajo. Lo que ocurrió después de ``conocido_hasta`` (un
    retiro, una ausencia) todavía no se sabía.
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
        desde = _instante(getattr(fila, "discrepancia_desde_utc", None))
        if conocido_hasta is not None:
            if conocida > conocido_hasta:
                continue
            hasta = hasta if pd.isna(hasta) or hasta <= conocido_hasta else pd.NaT
            desde = desde if pd.isna(desde) or desde <= conocido_hasta else pd.NaT
        tipo = getattr(fila, "discrepancia", "") if not pd.isna(desde) else ""
        if not pd.isna(desde) and tipo not in _DISCREPANCIAS:
            raise ValueError(f"discrepancia desconocida en el dividendo con fecha ex {fecha_ex}: {tipo!r}")
        salida.append(_Version(apertura(fecha_ex, codigo), float(fila.monto), conocida, hasta, tipo, desde, fecha_ex))
    return salida


def _consultas(tabla, conocido_hasta):
    """Consultas que pueden confirmar dividendos, conocidas hasta ``conocido_hasta``, y cuántas no cuentan.

    Cuentan las completas que pidieron dividendos en efectivo (``tipos`` =
    ``todos`` o con ``cash_dividend``), con un filtro de calidad admitido y un
    campo de fecha soportado.
    """
    if tabla is None or len(tabla) == 0:
        return [], {}
    completas, descartadas = [], {}
    for fila in pd.DataFrame(tabla).itertuples():
        recibido = _instante(fila.recibido_utc)
        if conocido_hasta is not None and recibido > conocido_hasta:
            continue
        tipos = str(fila.tipos).split(",")
        if fila.estado != "completa":
            razon = "parciales o fallidas"
        elif fila.tipos != "todos" and "cash_dividend" not in tipos:
            razon = "sin dividendos en los tipos pedidos"
        elif fila.calidad not in CALIDADES_COBERTURA:
            razon = f"con calidad distinta de {', '.join(CALIDADES_COBERTURA)}"
        elif fila.campo_fecha not in CAMPOS_POR_EX + CAMPOS_POSTERIORES_A_EX:
            razon = "con un campo de fecha no soportado"
        else:
            completas.append(_Consulta(recibido, _fecha(fila.desde), _fecha(fila.hasta),
                                       fila.campo_fecha in CAMPOS_POR_EX))
            continue
        descartadas[razon] = descartadas.get(razon, 0) + 1
    return sorted(completas), descartadas


def _cubre(consulta, inicio, fin, margen):
    """Si el intervalo de la consulta incluye todo dividendo con fecha ex en el periodo.

    Con un filtro por una fecha posterior a la ex (proceso o pago), el intervalo
    debe llegar hasta el fin más el margen de procesamiento.
    """
    dia_inicio, dia_fin = inicio.tz_convert(NUEVA_YORK).date(), fin.tz_convert(NUEVA_YORK).date()
    tope = dia_fin if consulta.por_ex else (fin + margen).tz_convert(NUEVA_YORK).date()
    return consulta.desde <= dia_inicio and consulta.hasta >= tope


def _con_dividendos(base, p0, p1, inicio, fin, versiones, consultas, descartadas, margen):
    """Filas (una por tramo de valor y estado) del rendimiento total de una etiqueta con los dos precios."""
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
        for razon, n in sorted(descartadas.items()):
            motivo += f"; {n} consultas {razon} no cuentan"
        return [dict(base, estado="sin dividendos confirmados", motivo=motivo,
                     vigente_desde_utc=base["label_available_at"])]
    disponible = max(base["label_available_at"], min(habilitantes))
    propias = [v for v in versiones if inicio < v.abre <= fin]
    aceptadoras = [q.recibido for q in cubren if q.recibido >= fin + margen]
    instantes = sorted({disponible} | {t for v in propias for t in (v.conocida, v.hasta, v.desde_discrepancia)
                                       if not pd.isna(t) and t > disponible}
                       | {t for t in aceptadoras if t > disponible})
    tramos, cambio_valor, fin_discrepancia, monto_previo, abiertas_previas = [], disponible, disponible, None, False
    for t in instantes:
        vigentes = [v for v in propias if v.conocida <= t and (pd.isna(v.hasta) or v.hasta > t)]
        monto = round(float(sum(v.monto for v in vigentes)), 10)  # redondeado: los tramos comparan exacto
        abiertas = [v for v in vigentes if not pd.isna(v.desde_discrepancia) and v.desde_discrepancia <= t]
        if monto_previo is not None and monto != monto_previo:
            cambio_valor = t
        if abiertas_previas and not abiertas:
            fin_discrepancia = t
        desde_aceptable = max(fin + margen, cambio_valor, fin_discrepancia)
        if abiertas:
            estado = "pendiente"
            motivo = "; ".join(f"dividendo con fecha ex {v.fecha_ex} ({v.monto:g}) {_DISCREPANCIAS[v.discrepancia]} "
                               f"desde {v.desde_discrepancia}, sin resolver" for v in abiertas)
        else:
            estado = "aceptada" if any(desde_aceptable <= q <= t for q in aceptadoras) else "provisional"
            motivo = ""
        if not tramos or (monto, estado, motivo) != (tramos[-1]["dividendos"], tramos[-1]["estado_dividendos"],
                                                     tramos[-1]["motivo"]):
            version = tramos[-1]["version"] + (monto != tramos[-1]["dividendos"]) if tramos else 1
            tramos.append({"vigente_desde_utc": t, "dividendos": monto, "estado_dividendos": estado,
                           "motivo": motivo, "version": version})
        monto_previo, abiertas_previas = monto, bool(abiertas)
    filas = []
    for i, tramo in enumerate(tramos):
        hasta = tramos[i + 1]["vigente_desde_utc"] if i + 1 < len(tramos) else pd.NaT
        filas.append(dict(base, **tramo, label_available_at=disponible, vigente_hasta_utc=hasta, tramo=i + 1,
                          retorno_log=float(np.log((p1 + tramo["dividendos"]) / p0)),
                          consulta_habilitante_utc=min(habilitantes)))
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
    consultas, descartadas = _consultas(cobertura, corte)
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
                    "motivo": "", "version": 1, "tramo": 1, "vigente_desde_utc": pd.NaT,
                    "vigente_hasta_utc": pd.NaT, "estado_dividendos": "", "consulta_habilitante_utc": pd.NaT}
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
                    filas += _con_dividendos(fila, p0, p1, inicio, fin, versiones, consultas, descartadas, margen)
                    continue
                fila.update(retorno_log=fila["retorno_precio_log"], estado_dividendos="no aplica")
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
    """Vista de ``instante_simulado`` (UTC): las etiquetas completas ya maduras, en el tramo vigente entonces.

    El estado que devuelve es el de ese instante, y ``vigente_hasta_utc`` queda
    nulo: lo que se supo después no se expone. Con ``politica="provisional"``
    entran también las pendientes, marcadas; con ``"aceptada"``, solo las
    aceptadas bajo la política (y las series sin dividendos).
    """
    if politica not in POLITICAS:
        raise ValueError(f"politica debe ser una de {POLITICAS}")
    t = pd.Timestamp(instante_simulado)
    e = etiquetas
    conocidas = e["label_available_at"].notna() & (e["label_available_at"] <= t) & (e["estado"] == "ok")
    if "vigente_desde_utc" in e:
        conocidas &= (e["vigente_desde_utc"] <= t) & (e["vigente_hasta_utc"].isna() | (e["vigente_hasta_utc"] > t))
    if politica == "aceptada":
        conocidas &= e["estado_dividendos"].isin(("aceptada", "no aplica"))
    vista = e[conocidas].copy()
    if "vigente_hasta_utc" in vista:
        vista["vigente_hasta_utc"] = pd.Series(pd.NaT, index=vista.index, dtype=e["vigente_hasta_utc"].dtype)
    return vista


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
