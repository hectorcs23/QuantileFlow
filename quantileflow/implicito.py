"""Subyacente implícito por paridad, cuando el proveedor no da el nivel del índice.

Alpaca no publica el nivel de SPX. En su lugar se usa el forward de la paridad
put-call ``C - P = D (F - K)`` del vencimiento más cercano con pares
suficientes, estimado con los mismos controles y la misma estimación fuera de
muestra que el resto del piloto (``cadenas``). Con plazos de horas o días la
pendiente no identifica ``D``: el descuento se fija con la tasa de referencia.
El forward se lleva a contado con la tasa y el rendimiento de dividendo de
referencia, ``S = F e^{-(r - q) T}``; con el vencimiento del mismo día la
conversión mueve el nivel menos de una centésima de punto porcentual.

La serie resultante es un **subyacente implícito**, no el índice publicado: se
registra como tal (``feed = implicito_paridad_<raíz>``), con el vencimiento
usado, los pares, el error jackknife del forward y, como hora del evento, la
mediana de las horas de las cotizaciones de los pares usados. Las etiquetas
calculadas con ella son rendimientos del nivel implícito.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import cadenas, contrato
from .calendario import CALENDARIO, _fecha

EXTRAS = ["vencimiento_usado", "dias_usados", "forward", "forward_error", "pares", "captura"]


def spot_implicito(filas: pd.DataFrame, fecha, corte_utc, tasa, rendimiento_dividendo=0.0,
                   reglas: cadenas.ReglasCalidad = cadenas.ReglasCalidad(), minimo_pares=5, base_dias=365.0,
                   codigo=CALENDARIO) -> dict:
    """Nivel implícito a partir de las filas de un vencimiento (una raíz europea).

    Devuelve ``estado`` («identificado» o «no identificado» con ``motivo``) y,
    si se identifica, ``spot``, ``forward``, ``forward_error``, ``pares``,
    ``T`` y ``sello_evento_utc``.
    """
    cap, info = contrato.captura_de_filas(filas, fecha, corte_utc, tasa=tasa,
                                          rendimiento_dividendo=rendimiento_dividendo, base_dias=base_dias,
                                          codigo=codigo)
    if cap.americana:
        raise ValueError("el subyacente implícito solo se estima con opciones europeas")
    controles = cadenas.controlar(cap, reglas)
    paridad = cadenas.residuos_paridad(cap, controles, descuento=np.exp(-tasa * cap.T), minimo_pares=minimo_pares)
    usados = paridad.en_estimacion & np.isfinite(paridad.residuo)
    if not np.isfinite(paridad.forward_global) or usados.sum() < minimo_pares:
        return {"estado": "no identificado", "vencimiento": info["vencimiento"], "T": cap.T,
                "motivo": f"{int(usados.sum())} pares válidos; se piden {minimo_pares}"}
    _, ic, ip, _ = cadenas.pares_mismo_strike(cap, controles)
    sellos = np.concatenate([cap.sello[ic[usados]], cap.sello[ip[usados]]])
    sellos = sellos[np.isfinite(sellos)]
    sello_utc = (pd.Timestamp(corte_utc) + pd.Timedelta(seconds=float(np.median(sellos) - cap.corte))
                 if len(sellos) else pd.NaT)
    F = paridad.forward_global
    return {"estado": "identificado", "motivo": "", "vencimiento": info["vencimiento"], "T": cap.T,
            "spot": float(F * np.exp(-(tasa - rendimiento_dividendo) * cap.T)), "forward": float(F),
            "forward_error": float(paridad.forward_error), "pares": int(usados.sum()),
            "sello_evento_utc": sello_utc}


def subyacente_implicito(cotizaciones: pd.DataFrame, capturas, raiz, subyacente, tasa, rendimiento_dividendo=0.0,
                         reglas: cadenas.ReglasCalidad = cadenas.ReglasCalidad(), minimo_pares=5, dias_max=7.0,
                         base_dias=365.0, codigo=CALENDARIO):
    """Filas ``SUBYACENTE`` implícitas, una por captura, y el motivo de las que no se identifican.

    ``capturas`` son tuplas ``(etiqueta, fecha_sesion, corte_utc)``; se usan las
    filas de ``raiz`` con esa etiqueta en la columna ``captura``. Se prueba del
    vencimiento más cercano hacia afuera, hasta ``dias_max`` días.
    """
    filas_salida, fallos = [], []
    for etiqueta, fecha, corte_utc in capturas:
        corte_utc = pd.Timestamp(corte_utc)
        propias = cotizaciones[(cotizaciones["captura"] == etiqueta) & (cotizaciones["raiz"] == raiz)]
        resultado, motivos = None, []
        for vencimiento in sorted({_fecha(v) for v in propias["vencimiento"]}):
            filas = propias[propias["vencimiento"].map(_fecha) == vencimiento]
            try:
                r = spot_implicito(filas, fecha, corte_utc, tasa, rendimiento_dividendo, reglas, minimo_pares,
                                   base_dias, codigo)
            except contrato.SinDatos as error:  # ya liquidó
                motivos.append(f"{vencimiento}: {error}")
                continue
            if r["T"] * base_dias > dias_max:
                motivos.append(f"{vencimiento}: más de {dias_max:g} días")
                break
            if r["estado"] == "identificado":
                resultado = r
                break
            motivos.append(f"{vencimiento}: {r['motivo']}")
        if resultado is None:
            fallos.append({"captura": etiqueta, "motivo": "; ".join(motivos) or f"sin filas de {raiz}"})
            continue
        usadas = propias[propias["vencimiento"].map(_fecha) == resultado["vencimiento"]]
        filas_salida.append({
            "subyacente": subyacente, "precio": resultado["spot"], "bid": np.nan, "ask": np.nan,
            "sello_evento_utc": resultado["sello_evento_utc"],
            "sello_snapshot_utc": usadas["sello_snapshot_utc"].max(), "disponible_utc": usadas["disponible_utc"].max(),
            "recibido_utc": usadas["recibido_utc"].max(), "proveedor": "|".join(sorted(usadas["proveedor"].unique())),
            "feed": f"implicito_paridad_{raiz}_" + "|".join(sorted(usadas["feed"].unique())),
            "vencimiento_usado": resultado["vencimiento"], "dias_usados": resultado["T"] * base_dias,
            "forward": resultado["forward"], "forward_error": resultado["forward_error"],
            "pares": resultado["pares"], "captura": etiqueta})
    tabla = pd.DataFrame(filas_salida, columns=list(contrato.SUBYACENTE) + EXTRAS)
    for columna in ("sello_evento_utc", "sello_snapshot_utc", "disponible_utc", "recibido_utc"):
        tabla[columna] = pd.to_datetime(tabla[columna], utc=True).dt.as_unit("us")
    for columna in ("precio", "bid", "ask"):
        tabla[columna] = tabla[columna].astype(float)
    return tabla, fallos
