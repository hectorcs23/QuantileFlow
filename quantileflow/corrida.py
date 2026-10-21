"""Corrida reproducible del piloto: entradas validadas, informe y manifiesto.

El manifiesto registra configuración (versión y huella), hashes de los archivos
de entrada y de salida, proveedores y feeds, intervalo de recepción de los
datos, commit y estado del árbol, exclusiones y dictamen. Reprocesar los mismos
archivos con la misma configuración produce las mismas tablas.

Se escribe como ``manifest.json``, con claves en inglés: es una salida que se
lee, no una estructura interna.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from pathlib import Path

import pandas as pd

from . import almacen, contrato, vocabulario
from .calendario import sesiones
from .informe import _exclusiones, escribir_informe
from .piloto import cargar_config, ejecutar


def leer_entrada(ruta, esquema) -> pd.DataFrame:
    """Tabla normalizada desde Parquet o CSV, validada contra su esquema."""
    ruta = Path(ruta)
    if ruta.suffix == ".parquet":
        tabla = almacen.leer_tabla(ruta)
        problemas = contrato.validar(tabla, esquema)
        if problemas:
            raise ValueError(f"{ruta}: " + "; ".join(problemas))
        return tabla
    return contrato.leer_csv_normalizado(ruta, esquema)


def correr(config, cotizaciones, subyacente, desde, hasta, salida, titulo, aviso="", crudos=()):
    """Ejecuta el piloto entre dos fechas y escribe informe y manifiesto en ``salida``."""
    # Estado del código al empezar, antes de escribir salidas que Git vería como archivos nuevos.
    entorno = almacen.huella_entorno(Path(__file__).resolve().parents[1])
    cfg = cargar_config(config)
    cot = leer_entrada(cotizaciones, contrato.COTIZACIONES)
    sub = leer_entrada(subyacente, contrato.SUBYACENTE)
    fechas = sesiones(desde, hasta, cfg.calendario)
    resultado = ejecutar(cot, sub, fechas, cfg)
    salida = Path(salida)
    rutas = escribir_informe(resultado, salida, titulo, aviso)
    exclusiones = Counter()
    for texto in resultado.principal["exclusiones"]:
        exclusiones.update(_exclusiones(texto))
    # Claves en inglés: el manifiesto es una salida que se lee.
    manifiesto = {
        "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "config": {"path": str(config), "version": cfg.version, "fingerprint": cfg.huella},
        "inputs": {nombre: {"path": str(ruta), "sha256": almacen.sha256_archivo(ruta)}
                   for nombre, ruta in (("quotes", cotizaciones), ("underlying", subyacente))},
        "raw": list(crudos),
        "providers": sorted(cot["proveedor"].unique()), "feeds": sorted(cot["feed"].unique()),
        "received_utc": [str(cot["recibido_utc"].min()), str(cot["recibido_utc"].max())],
        "sessions": {"from": str(fechas[0]), "to": str(fechas[-1]), "n": len(fechas)},
        "cutoffs": list(cfg.horas), "verdict": resultado.dictamen["veredicto"],
        "exclusions_primary_cutoff": {vocabulario.motivo(k): v
                                     for k, v in sorted(exclusiones.items())},
        "environment": entorno,
        "outputs": almacen.hashes(rutas.values()),
    }
    almacen.escribir_json(manifiesto, salida / "manifest.json")
    return resultado, manifiesto
