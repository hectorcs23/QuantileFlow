"""Revisa la operación de la captura en un rango de sesiones: cortes, puntualidad, respaldo, SIP y dividendos.

Uso, desde la raíz del repositorio::

    python scripts/revisar_operacion.py --datos ../QuantileFlow-datos --desde 2026-09-28 --hasta 2026-10-02

Lee los registros de ``ejecuciones/`` y los manifiestos del repositorio de datos,
y ``resoluciones_dividendos.csv`` si existe (``quantileflow/operacion.py``).
Escribe en ``reports/operacion/<desde>_<hasta>/`` un informe Markdown y un
resumen JSON. Solo son agregados (estados, tiempos y conteos), nunca
cotizaciones. El código de salida es 0 si ningún corte del rango quedó
``parcial``, ``fallida`` o ``perdida``.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow import alpaca, almacen, operacion  # noqa: E402


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--desde", required=True, help="primera sesión")
    a.add_argument("--hasta", required=True, help="última sesión")
    a.add_argument("--datos", default=str(RAIZ / "data"))
    a.add_argument("--config", default=str(RAIZ / "configs" / "captura_alpaca.toml"))
    a.add_argument("--resoluciones", default=None,
                   help="resoluciones de dividendos (CSV); por omisión, <datos>/resoluciones_dividendos.csv si existe")
    a.add_argument("--salida", default=None, help="por omisión, reports/operacion/<desde>_<hasta>")
    args = a.parse_args()
    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)["captura"]
    datos = Path(args.datos)
    ruta_res = Path(args.resoluciones) if args.resoluciones else datos / "resoluciones_dividendos.csv"
    resoluciones = alpaca.cargar_resoluciones(ruta_res) if ruta_res.is_file() else None
    revision = operacion.revisar(datos, args.desde, args.hasta, cfg["horas"], cfg["adelanto_s"], cfg["calendario"],
                                 resoluciones=resoluciones)
    salida = Path(args.salida) if args.salida else RAIZ / "reports" / "operacion" / f"{args.desde}_{args.hasta}"
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "informe.md").write_text(operacion.informe(revision), encoding="utf-8")
    almacen.escribir_json(revision, salida / "resumen.json")
    r = revision["resumen"]
    print(f"{r['sesiones']} sesiones, {r['cortes']} cortes: "
          + ", ".join(f"{n} {k}" for k, n in r["estados"].items() if n) + f" -> {salida}")
    return 1 if any(r["estados"][k] for k in ("parcial", "fallida", "perdida")) else 0


if __name__ == "__main__":
    sys.exit(main())
