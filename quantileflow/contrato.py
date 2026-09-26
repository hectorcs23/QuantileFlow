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
No mezcla estilos de ejercicio ni de liquidación dentro de una captura.
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
}

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


def spot_al_corte(subyacente: pd.DataFrame, simbolo, fecha, corte_utc):
    """Último precio del subyacente conocido al corte y su hora (evento o, si falta, snapshot)."""
    filas = _del_dia_hasta(subyacente[subyacente["subyacente"] == simbolo], fecha, corte_utc)
    if "sello_evento_utc" in filas:
        filas = filas[filas["sello_evento_utc"].isna() | (filas["sello_evento_utc"] <= corte_utc)]
    if filas.empty:
        raise SinDatos(f"sin precio de {simbolo} al corte de {fecha}")
    referencia = filas["sello_evento_utc"].fillna(filas["sello_snapshot_utc"])
    fila = filas.loc[referencia.idxmax()]
    return float(fila["precio"]), referencia.max(), pd.isna(fila["sello_evento_utc"])


def vencimientos(cotizaciones: pd.DataFrame, raiz, fecha, hora="09:45") -> list:
    """Vencimientos de ``raiz`` con snapshots de esa sesión anteriores o iguales al corte."""
    corte_utc = instante(fecha, hora)
    filas = _del_dia_hasta(cotizaciones[cotizaciones["raiz"] == raiz], fecha, corte_utc)
    return sorted({_fecha(v) for v in filas["vencimiento"]})


def captura_desde_tabla(cotizaciones: pd.DataFrame, subyacente: pd.DataFrame, raiz, vencimiento,
                        fecha, hora="09:45", tasa=0.0, rendimiento_dividendo=0.0, dividendos=(),
                        base_dias=365.0, codigo=CALENDARIO):
    """``Captura`` de una raíz y un vencimiento a la hora de corte de una sesión.

    ``dividendos`` son pares ``(instante_utc, monto)``. Devuelve la captura y un
    diccionario con el corte, la liquidación, el plazo y la procedencia.
    """
    corte_utc = instante(fecha, hora, codigo)
    vencimiento = _fecha(vencimiento)
    filas = cotizaciones[(cotizaciones["raiz"] == raiz)
                         & (cotizaciones["vencimiento"].map(_fecha) == vencimiento)]
    filas = _del_dia_hasta(filas, fecha, corte_utc)
    if filas.empty:
        raise SinDatos(f"sin cotizaciones de {raiz} {vencimiento} al corte {hora} de {fecha}")
    for columna in ("ejercicio", "liquidacion", "subyacente"):
        if filas[columna].nunique() != 1:
            raise ValueError(f"{columna} mezclado dentro de una captura: {sorted(filas[columna].unique())}")
    ejercicio, liquidacion = filas["ejercicio"].iloc[0], filas["liquidacion"].iloc[0]
    liquida_utc = instante_liquidacion(vencimiento, liquidacion, codigo)
    T = plazo_anios(corte_utc, liquida_utc, base_dias)
    if T <= 0:
        raise SinDatos(f"{raiz} {vencimiento} ya liquidó antes del corte")
    spot, sello_spot_utc, spot_sin_evento = spot_al_corte(subyacente, filas["subyacente"].iloc[0], fecha,
                                                          corte_utc)

    def locales(columna):
        if columna not in filas:
            return None
        return np.array([segundos_locales(x, fecha) for x in filas[columna]], dtype=float)

    divs = tuple((plazo_anios(corte_utc, t, base_dias), float(m)) for t, m in dividendos)
    captura = Captura(
        strike=filas["strike"].to_numpy(float), es_call=(filas["tipo"] == "C").to_numpy(),
        bid=filas["bid"].to_numpy(float), ask=filas["ask"].to_numpy(float),
        tam_bid=filas["tam_bid"].to_numpy(float), tam_ask=filas["tam_ask"].to_numpy(float),
        sello=locales("sello_evento_utc"), T=T, spot=spot,
        sello_spot=segundos_locales(sello_spot_utc, fecha), tasa=tasa, dividendos=divs,
        rendimiento_dividendo=rendimiento_dividendo, ejercicio=ejercicio,
        corte=segundos_locales(corte_utc, fecha), fecha=str(_fecha(fecha)),
        sello_snapshot=locales("sello_snapshot_utc"), disponible=locales("disponible_utc"))
    info = {
        "raiz": raiz, "vencimiento": vencimiento, "hora": hora, "corte_utc": corte_utc,
        "liquidacion": liquidacion, "liquidacion_utc": liquida_utc, "T": T, "dias": T * base_dias,
        "filas": len(filas), "proveedores": sorted(filas["proveedor"].unique()),
        "feeds": sorted(filas["feed"].unique()), "spot_sin_hora_de_evento": bool(spot_sin_evento),
    }
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
