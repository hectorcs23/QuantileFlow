"""Contrato de datos normalizado y adaptador de tablas a ``Captura``.

Esquemas
--------
``COTIZACIONES``: una fila por contrato y snapshot (o actualización) del
proveedor. ``SUBYACENTE``: nivel del índice o precio del subyacente. Todos los
instantes van en UTC con zona explícita; la hora de Nueva York solo se usa para
el calendario y la presentación. Se distinguen cuatro instantes:

* ``sello_evento_utc``: última actualización de la cotización (nulo si el
  proveedor no la da; entonces la edad de la cotización es desconocida);
* ``sello_snapshot_utc``: hora del snapshot entregado por el proveedor;
* ``disponible_utc``: hora documentada en que el dato histórico estuvo
  disponible (nula si no está documentada);
* ``recibido_utc``: hora de descarga o recepción local. No demuestra cuándo
  estuvo disponible un dato histórico.

El adaptador toma, para una raíz, un vencimiento y una hora de corte, los
snapshots de esa sesión anteriores o iguales al corte; los controles de
``cadenas`` deciden después qué filas valen y por qué se excluyen las demás.
No mezcla estilos de ejercicio, liquidaciones, proveedores ni feeds dentro de una
captura. La fuente de una fila es ``proveedor/feed``.

Dos reglas para elegir un precio, según su uso:

* **Puntual** (``precio_al_corte``): información conocida en el corte, para
  señales, controles y el subyacente de referencia de las opciones. Exige que
  el precio estuviera disponible al corte.
* **Histórica** (``precio_para_etiqueta``): el precio vigente en el corte para
  construir una etiqueta, que puede haberse publicado después (p. ej., SIP con
  15 minutos de retraso). Su publicación fija la madurez de la etiqueta; nunca
  entra como dato conocido en el corte.

``DIVIDENDOS``: dividendos en efectivo por fecha ex, para el rendimiento total.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .cadenas import Captura
from .calendario import (CALENDARIO, _fecha, instante, instante_liquidacion, plazo_anios,
                         segundos_locales)

# nombre: (tipo, obligatorio, descripción)
COTIZACIONES = {
    "id_contrato": ("texto", True, "símbolo OCC del contrato"),
    "raiz": ("texto", True, "raíz de la clase de opciones (SPX, SPXW, SPY...)"),
    "subyacente": ("texto", True, "símbolo del subyacente (SPX, SPY...)"),
    "strike": ("real", True, "precio de ejercicio"),
    "tipo": ("texto", True, "C (call) o P (put)"),
    "ejercicio": ("texto", True, "europeo o americano"),
    "liquidacion": ("texto", True, "AM (precios de apertura) o PM (cierre)"),
    "vencimiento": ("fecha", True, "fecha de vencimiento del contrato"),
    "multiplicador": ("real", True, "unidades del subyacente por contrato"),
    "bid": ("real", True, "mejor precio de compra (0 si no hay)"),
    "ask": ("real", True, "mejor precio de venta"),
    "tam_bid": ("real", True, "tamaño en el bid"),
    "tam_ask": ("real", True, "tamaño en el ask"),
    "sello_evento_utc": ("instante", False, "última actualización de la cotización"),
    "sello_snapshot_utc": ("instante", True, "hora del snapshot del proveedor"),
    "disponible_utc": ("instante", False, "disponibilidad histórica documentada"),
    "recibido_utc": ("instante", True, "descarga o recepción local"),
    "proveedor": ("texto", True, "proveedor de los datos"),
    "feed": ("texto", True, "feed o producto concreto (p. ej., NBBO por intervalos)"),
}

SUBYACENTE = {
    "subyacente": ("texto", True, "símbolo del subyacente"),
    "precio": ("real", True, "nivel del índice o precio de referencia"),
    "bid": ("real", False, "mejor precio de compra, si existe"),
    "ask": ("real", False, "mejor precio de venta, si existe"),
    "sello_evento_utc": ("instante", False, "hora del último cálculo o actualización"),
    "sello_snapshot_utc": ("instante", True, "hora del snapshot del proveedor"),
    "disponible_utc": ("instante", False, "disponibilidad histórica documentada"),
    "recibido_utc": ("instante", True, "descarga o recepción local"),
    "proveedor": ("texto", True, "proveedor de los datos"),
    "feed": ("texto", True, "feed o producto concreto"),
    "tipo_precio": ("texto", True, "observado (publicado por la fuente) o implicito (inferido de las opciones)"),
}
TIPOS_PRECIO = ("observado", "implicito")

DIVIDENDOS = {
    "simbolo": ("texto", True, "símbolo que paga el dividendo"),
    "fecha_ex": ("fecha", True, "primera sesión que cotiza sin derecho al dividendo"),
    "monto": ("real", True, "dividendo en efectivo por acción"),
    "fecha_pago": ("fecha", False, "fecha de pago"),
    "clase": ("texto", True, "ordinario o especial"),
    "disponible_utc": ("instante", False, "anuncio documentado (nulo si el proveedor no lo da)"),
    "recibido_utc": ("instante", True, "descarga o recepción local"),
    "proveedor": ("texto", True, "proveedor de los datos"),
    "feed": ("texto", True, "producto concreto"),
}
CLASES_DIVIDENDO = ("ordinario", "especial")

_OCC = re.compile(r"^([A-Z0-9]{1,6})\s*(\d{6})([CP])(\d{8})$")


class SinDatos(ValueError):
    """No hay filas utilizables para construir la captura pedida."""


def parsear_occ(simbolo: str) -> dict:
    """Raíz, vencimiento, tipo y strike de un símbolo OCC (con o sin relleno de espacios)."""
    m = _OCC.match(simbolo.strip().upper())
    if not m:
        raise ValueError(f"símbolo OCC no reconocido: {simbolo!r}")
    raiz, fecha, tipo, strike = m.groups()
    vencimiento = pd.Timestamp(f"20{fecha[:2]}-{fecha[2:4]}-{fecha[4:]}").date()
    return {"raiz": raiz, "vencimiento": vencimiento, "tipo": tipo, "strike": int(strike) / 1000.0}


def simbolo_occ(raiz, vencimiento, tipo, strike) -> str:
    """Símbolo OCC compacto: raíz + AAMMDD + C/P + strike x 1000 en ocho dígitos."""
    return f"{raiz}{pd.Timestamp(vencimiento):%y%m%d}{tipo}{int(round(strike * 1000)):08d}"


def _es_utc(serie) -> bool:
    return isinstance(serie.dtype, pd.DatetimeTZDtype) and str(serie.dtype.tz) == "UTC"


def validar(tabla: pd.DataFrame, esquema=COTIZACIONES) -> list[str]:
    """Problemas de una tabla frente a su esquema (lista vacía si cumple)."""
    problemas = []
    faltan = [c for c in esquema if c not in tabla.columns]
    if faltan:
        return [f"faltan columnas: {', '.join(faltan)}"]
    for columna, (tipo, obligatorio, _) in esquema.items():
        serie = tabla[columna]
        if obligatorio and serie.isna().any():
            problemas.append(f"{columna}: {int(serie.isna().sum())} valores nulos en una columna obligatoria")
        if tipo == "instante" and not _es_utc(serie):
            problemas.append(f"{columna}: debe ser un instante con zona UTC explícita")
        if tipo == "real" and not pd.api.types.is_numeric_dtype(serie):
            problemas.append(f"{columna}: debe ser numérica")
    if esquema is SUBYACENTE and not problemas and not tabla["tipo_precio"].isin(TIPOS_PRECIO).all():
        problemas.append("tipo_precio: solo se admite observado o implicito")
    if esquema is DIVIDENDOS and not problemas:
        if not tabla["clase"].isin(CLASES_DIVIDENDO).all():
            problemas.append("clase: solo se admite ordinario o especial")
        if (tabla["monto"] <= 0).any():
            problemas.append("monto: debe ser positivo")
        claves = tabla[["simbolo", "fecha_ex", "clase", "monto"]].astype(str)
        if claves.duplicated().any():
            problemas.append(f"{int(claves.duplicated().sum())} dividendos repetidos")
    if esquema is COTIZACIONES and not problemas:
        if not tabla["tipo"].isin(["C", "P"]).all():
            problemas.append("tipo: solo se admite C o P")
        if not tabla["ejercicio"].isin(["europeo", "americano"]).all():
            problemas.append("ejercicio: solo se admite europeo o americano")
        if not tabla["liquidacion"].isin(["AM", "PM"]).all():
            problemas.append("liquidacion: solo se admite AM o PM")
        if (tabla["strike"] <= 0).any():
            problemas.append("strike: debe ser positivo")
        if ((tabla["bid"] < 0) | (tabla["ask"] < 0)).any():
            problemas.append("bid/ask: no pueden ser negativos")
        claves = tabla[["id_contrato", "sello_snapshot_utc"]]
        if claves.duplicated().any():
            problemas.append(f"{int(claves.duplicated().sum())} filas repetidas por contrato y snapshot")
        for fila in tabla.drop_duplicates("id_contrato").itertuples():
            try:
                occ = parsear_occ(fila.id_contrato)
            except ValueError as error:
                problemas.append(str(error))
                continue
            esperado = (fila.raiz, _fecha(fila.vencimiento), fila.tipo, float(fila.strike))
            if (occ["raiz"], occ["vencimiento"], occ["tipo"], occ["strike"]) != esperado:
                problemas.append(f"{fila.id_contrato}: no coincide con raiz/vencimiento/tipo/strike")
    return problemas


def _del_dia_hasta(tabla, fecha, corte_utc):
    """Filas con snapshot en la fecha de sesión (hora de Nueva York) y no posterior al corte."""
    snapshot = tabla["sello_snapshot_utc"]
    local = snapshot.dt.tz_convert("America/New_York").dt.date
    return tabla[(local == _fecha(fecha)) & (snapshot <= corte_utc)]


def fuente(tabla: pd.DataFrame) -> pd.Series:
    """Fuente de cada fila: ``proveedor/feed``."""
    return tabla["proveedor"].astype(str) + "/" + tabla["feed"].astype(str)


def precio_al_corte(subyacente: pd.DataFrame, simbolo, fecha, corte_utc, fuente_elegida=None) -> dict:
    """Último precio de ``simbolo`` que ya se conocía al corte, con su procedencia.

    Descarta las filas con snapshot o evento posterior al corte y las que, según
    su ``disponible_utc`` documentada, se publicaron después (una disponibilidad
    no documentada se acepta y queda indicada). Si el símbolo tiene varias
    fuentes hay que elegir una: los precios de fuentes distintas no se mezclan.
    """
    filas = _del_dia_hasta(subyacente[subyacente["subyacente"] == simbolo], fecha, corte_utc)
    filas = filas[filas["sello_evento_utc"].isna() | (filas["sello_evento_utc"] <= corte_utc)]
    if fuente_elegida is not None:
        filas = filas[fuente(filas) == fuente_elegida]
    elif len(filas) and fuente(filas).nunique() > 1:
        raise ValueError(f"{simbolo}: varias fuentes de precio ({', '.join(sorted(set(fuente(filas))))}); "
                         "elija una")
    if filas.empty:
        raise SinDatos(f"sin precio de {simbolo} al corte de {fecha}")
    a_tiempo = filas[filas["disponible_utc"].isna() | (filas["disponible_utc"] <= corte_utc)]
    if a_tiempo.empty:
        raise SinDatos(f"precio de {simbolo} disponible solo después del corte de {fecha}")
    referencia = a_tiempo["sello_evento_utc"].fillna(a_tiempo["sello_snapshot_utc"])
    fila = a_tiempo.loc[referencia.idxmax()]
    return {"precio": float(fila["precio"]), "sello_utc": referencia.max(),
            "sin_evento": bool(pd.isna(fila["sello_evento_utc"])), "disponible_utc": fila["disponible_utc"],
            "disponibilidad_documentada": not pd.isna(fila["disponible_utc"]),
            "fuente": f"{fila['proveedor']}/{fila['feed']}", "tipo_precio": fila["tipo_precio"]}


def precio_para_etiqueta(tabla: pd.DataFrame, simbolo, fecha, corte_utc, fuente_elegida=None,
                         edad_maxima_s=float("inf"), spread_relativo_max=float("inf")) -> dict:
    """Precio vigente en el corte para construir una etiqueta (regla histórica, no puntual).

    Convención: el mid de la **última cotización válida** con evento no
    posterior al corte y no más vieja que ``edad_maxima_s``. Es válida si
    ``bid > 0``, ``ask >= bid`` y su spread relativo no supera
    ``spread_relativo_max``; si la fuente no da bid/ask (un índice o un nivel
    implícito), vale el precio. No exige que el precio estuviera disponible en el
    corte: devuelve cuándo lo estuvo (la documentada o, si falta, la recepción)
    para fijar la madurez. Una barra con sello 09:45 no sirve: abarca operaciones
    posteriores.
    """
    corte_utc = pd.Timestamp(corte_utc)
    filas = _del_dia_hasta(tabla[tabla["subyacente"] == simbolo], fecha, corte_utc)
    if fuente_elegida is not None:
        filas = filas[fuente(filas) == fuente_elegida]
    elif len(filas) and fuente(filas).nunique() > 1:
        raise ValueError(f"{simbolo}: varias fuentes de precio ({', '.join(sorted(set(fuente(filas))))}); "
                         "elija una")
    evento = filas["sello_evento_utc"].fillna(filas["sello_snapshot_utc"])
    filas = filas[(evento <= corte_utc) & ((corte_utc - evento).dt.total_seconds() <= edad_maxima_s)]
    if filas.empty:
        raise SinDatos(f"sin cotización de {simbolo} en los {edad_maxima_s:g} s previos al corte de {fecha}")
    bid, ask = filas["bid"].astype(float), filas["ask"].astype(float)
    con_libro = bid.notna() & ask.notna()
    mid = 0.5 * (bid + ask)
    with np.errstate(divide="ignore", invalid="ignore"):
        valida = ~con_libro | ((bid > 0) & (ask >= bid) & ((ask - bid) / mid <= spread_relativo_max))
    valida &= filas["precio"].notna()
    if not valida.any():
        raise SinDatos(f"cotizaciones de {simbolo} cruzadas, sin bid o con spread anormal "
                       f"(> {spread_relativo_max:g}) antes del corte de {fecha}")
    validas = filas[valida]
    referencia = validas["sello_evento_utc"].fillna(validas["sello_snapshot_utc"])
    fila = validas.loc[referencia.idxmax()]
    disponible = fila["disponible_utc"] if not pd.isna(fila["disponible_utc"]) else fila["recibido_utc"]
    return {"precio": float(mid[fila.name]) if con_libro[fila.name] else float(fila["precio"]),
            "sello_utc": referencia.max(), "disponible_utc": disponible,
            "disponibilidad_documentada": not pd.isna(fila["disponible_utc"]),
            "descartadas": int((~valida).sum()), "fuente": f"{fila['proveedor']}/{fila['feed']}",
            "tipo_precio": fila["tipo_precio"]}


def spot_al_corte(subyacente: pd.DataFrame, simbolo, fecha, corte_utc, fuente_elegida=None):
    """Último precio del subyacente conocido al corte y su hora (evento o, si falta, snapshot)."""
    info = precio_al_corte(subyacente, simbolo, fecha, corte_utc, fuente_elegida)
    return info["precio"], info["sello_utc"], info["sin_evento"]


def vencimientos(cotizaciones: pd.DataFrame, raiz, fecha, hora="09:45") -> list:
    """Vencimientos de ``raiz`` con snapshots de esa sesión anteriores o iguales al corte."""
    corte_utc = instante(fecha, hora)
    filas = _del_dia_hasta(cotizaciones[cotizaciones["raiz"] == raiz], fecha, corte_utc)
    return sorted({_fecha(v) for v in filas["vencimiento"]})


def _plazo_de_filas(filas, corte_utc, base_dias, codigo):
    """Ejercicio, liquidación, instante de liquidación y plazo de filas de una sola raíz y vencimiento."""
    for columna in ("raiz", "vencimiento", "ejercicio", "liquidacion", "subyacente", "proveedor", "feed"):
        if filas[columna].map(str).nunique() != 1:
            raise ValueError(f"{columna} mezclado dentro de una captura: {sorted(filas[columna].map(str).unique())}")
    raiz, vencimiento = filas["raiz"].iloc[0], _fecha(filas["vencimiento"].iloc[0])
    liquida_utc = instante_liquidacion(vencimiento, filas["liquidacion"].iloc[0], codigo)
    T = plazo_anios(corte_utc, liquida_utc, base_dias)
    if T <= 0:
        raise SinDatos(f"{raiz} {vencimiento} ya liquidó antes del corte")
    return filas["ejercicio"].iloc[0], filas["liquidacion"].iloc[0], liquida_utc, T


def captura_de_filas(filas: pd.DataFrame, fecha, corte_utc, spot=float("nan"), sello_spot_utc=None, tasa=0.0,
                     rendimiento_dividendo=0.0, dividendos=(), base_dias=365.0, codigo=CALENDARIO):
    """``Captura`` de filas ya elegidas (una raíz y un vencimiento) con un corte explícito.

    No filtra por sesión ni por corte: eso lo hace quien elige las filas
    (``captura_desde_tabla`` a una hora de sesión). Sin subyacente (``spot``
    NaN), los controles y referencias que lo usan no se aplican; así se estima,
    por ejemplo, un subyacente implícito por paridad. ``dividendos`` son pares
    ``(instante_utc, monto)``. Devuelve la captura y un diccionario con el corte,
    la liquidación, el plazo y la procedencia.
    """
    if filas.empty:
        raise SinDatos("sin filas para la captura")
    ejercicio, liquidacion, liquida_utc, T = _plazo_de_filas(filas, corte_utc, base_dias, codigo)

    def locales(columna):
        if columna not in filas:
            return None
        return np.array([segundos_locales(x, fecha) for x in filas[columna]], dtype=float)

    divs = tuple((plazo_anios(corte_utc, t, base_dias), float(m)) for t, m in dividendos)
    captura = Captura(
        strike=filas["strike"].to_numpy(float), es_call=(filas["tipo"] == "C").to_numpy(),
        bid=filas["bid"].to_numpy(float), ask=filas["ask"].to_numpy(float),
        tam_bid=filas["tam_bid"].to_numpy(float), tam_ask=filas["tam_ask"].to_numpy(float),
        sello=locales("sello_evento_utc"), T=T, spot=float(spot),
        sello_spot=segundos_locales(sello_spot_utc, fecha), tasa=tasa, dividendos=divs,
        rendimiento_dividendo=rendimiento_dividendo, ejercicio=ejercicio,
        corte=segundos_locales(corte_utc, fecha), fecha=str(_fecha(fecha)),
        sello_snapshot=locales("sello_snapshot_utc"), disponible=locales("disponible_utc"))
    info = {
        "raiz": filas["raiz"].iloc[0], "vencimiento": _fecha(filas["vencimiento"].iloc[0]), "corte_utc": corte_utc,
        "liquidacion": liquidacion, "liquidacion_utc": liquida_utc, "T": T, "dias": T * base_dias,
        "filas": len(filas), "proveedores": sorted(filas["proveedor"].unique()),
        "feeds": sorted(filas["feed"].unique()),
    }
    return captura, info


def captura_desde_tabla(cotizaciones: pd.DataFrame, subyacente: pd.DataFrame, raiz, vencimiento,
                        fecha, hora="09:45", tasa=0.0, rendimiento_dividendo=0.0, dividendos=(),
                        base_dias=365.0, codigo=CALENDARIO, fuente_subyacente=None):
    """``Captura`` de una raíz y un vencimiento a la hora de corte de una sesión.

    ``dividendos`` son pares ``(instante_utc, monto)``. Devuelve la captura y un
    diccionario con el corte, la liquidación, el plazo y la procedencia de las
    cotizaciones y del subyacente.
    """
    corte_utc = instante(fecha, hora, codigo)
    vencimiento = _fecha(vencimiento)
    filas = cotizaciones[(cotizaciones["raiz"] == raiz)
                         & (cotizaciones["vencimiento"].map(_fecha) == vencimiento)]
    filas = _del_dia_hasta(filas, fecha, corte_utc)
    if filas.empty:
        raise SinDatos(f"sin cotizaciones de {raiz} {vencimiento} al corte {hora} de {fecha}")
    _plazo_de_filas(filas, corte_utc, base_dias, codigo)  # mezclas y vencimientos liquidados, antes del spot
    spot = precio_al_corte(subyacente, filas["subyacente"].iloc[0], fecha, corte_utc, fuente_subyacente)
    captura, info = captura_de_filas(filas, fecha, corte_utc, spot["precio"], spot["sello_utc"], tasa,
                                     rendimiento_dividendo, dividendos, base_dias, codigo)
    info.update(hora=hora, spot_sin_hora_de_evento=spot["sin_evento"], fuente=fuente(filas).iloc[0],
                fuente_subyacente=spot["fuente"], tipo_precio_subyacente=spot["tipo_precio"],
                disponibilidad_subyacente_documentada=spot["disponibilidad_documentada"])
    return captura, info


def leer_csv_normalizado(ruta, esquema=COTIZACIONES) -> pd.DataFrame:
    """Lee un CSV que ya sigue un esquema, con tipos explícitos, y lo valida.

    Los instantes deben venir con zona (ISO 8601 con desfase); se convierten a
    UTC con resolución de microsegundos. Un problema de validación detiene la
    lectura: no se corrige en silencio.
    """
    tabla = pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[""])
    for columna, (tipo, _, _) in esquema.items():
        if columna not in tabla:
            continue
        if tipo == "real":
            tabla[columna] = pd.to_numeric(tabla[columna], errors="raise").astype(float)
        elif tipo == "instante":
            valores = tabla[columna]
            sin_zona = valores.notna() & ~valores.fillna("").str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$")
            if sin_zona.any():
                raise ValueError(f"{columna}: instantes sin zona horaria en {int(sin_zona.sum())} filas")
            tabla[columna] = pd.to_datetime(valores, utc=True, format="ISO8601").dt.as_unit("us")
        elif tipo == "fecha":
            tabla[columna] = pd.to_datetime(tabla[columna], format="%Y-%m-%d").dt.date
    problemas = validar(tabla, esquema)
    if problemas:
        raise ValueError(f"{ruta}: " + "; ".join(problemas))
    return tabla
