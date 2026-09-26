"""Reconstruye desde el crudo las tablas de Alpaca de un rango de sesiones, listas para el piloto.

Uso, desde la raíz del repositorio::

    python scripts/normalizar_alpaca.py --desde 2026-09-28 --hasta 2026-11-06
    python scripts/piloto.py --cotizaciones data/normalized/alpaca/cotizaciones.parquet \
        --subyacente data/normalized/alpaca/subyacente.parquet --desde 2026-09-28 --hasta 2026-11-06

Lee solo el crudo y sus manifiestos (comprobando hashes), añade el nivel
implícito de SPX y escribe las dos tablas y un manifiesto con los manifiestos
de captura usados, la configuración, los fallos del nivel implícito, el entorno
y los hashes de salida. Reprocesar el mismo crudo da los mismos bytes.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow import alpaca, almacen  # noqa: E402
from quantileflow.piloto import cargar_config  # noqa: E402


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--desde", required=True)
    a.add_argument("--hasta", required=True)
    a.add_argument("--datos", default=str(RAIZ / "data"))
    a.add_argument("--config", default=str(RAIZ / "configs" / "captura_alpaca.toml"))
    a.add_argument("--config-piloto", default=str(RAIZ / "configs" / "piloto.toml"))
    a.add_argument("--salida", default=None, help="por omisión, data/normalized/alpaca")
    args = a.parse_args()
    entorno = almacen.huella_entorno(RAIZ)
    datos = Path(args.datos)
    salida = Path(args.salida) if args.salida else datos / "normalized" / "alpaca"
    with open(args.config, "rb") as f:
        bruto = tomllib.load(f)
    piloto = cargar_config(args.config_piloto)
    cot, sub, resumenes, fallos, manifiestos = alpaca.tablas_para_piloto(datos, args.desde, args.hasta,
                                                                         bruto.get("implicito"), piloto.reglas)
    if not manifiestos:
        print(f"no hay capturas entre {args.desde} y {args.hasta} en {datos}", file=sys.stderr)
        return 1
    rutas = {"cotizaciones": salida / "cotizaciones.parquet", "subyacente": salida / "subyacente.parquet"}
    salidas = {nombre: almacen.escribir_tabla(tabla, rutas[nombre])
               for nombre, tabla in (("cotizaciones", cot), ("subyacente", sub))}
    almacen.escribir_json({
        "desde": args.desde, "hasta": args.hasta,
        "config": {"version": bruto["captura"]["version"], "huella": almacen.huella_datos(bruto),
                   "piloto": piloto.version, "huella_piloto": piloto.huella},
        "capturas": [{"manifiesto": m["_ruta"], "sha256": almacen.sha256_archivo(datos / m["_ruta"]),
                      "etiqueta": m["etiqueta"], "modo": m.get("modo"), "feed_opciones": m.get("feed_opciones")}
                     for m in manifiestos],
        "resumenes": resumenes, "implicito_no_identificado": fallos, "entorno": entorno, "salidas": salidas,
    }, salida / "manifiesto_normalizacion.json")
    print(f"{len(manifiestos)} capturas -> {len(cot)} cotizaciones y {len(sub)} filas de subyacente en {salida}")
    for f in fallos:
        print(f"  nivel implícito no identificado en {f['captura']}: {f['motivo']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
