"""Turn Robinhood capture files into the normalized tables the pilot reads.

Takes one or more capture JSON files (the format documented in
``quantileflow/sources/robinhood.py``), archives each one unchanged under
``data/raw/`` addressed by its SHA-256, maps them onto the data contract,
validates, and writes ``quotes.parquet`` and ``underlying.parquet`` plus an
ingest manifest.

Usage, from the repository root::

    python scripts/robinhood_ingest.py captures/*.json --output data/normalized/robinhood

This script reads files. It never logs in, holds a credential or places an
order: fetching is a separate, uncommitted step (see README, "Robinhood").
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantileflow import almacen, contrato  # noqa: E402
from quantileflow.sources import robinhood  # noqa: E402

CLAVE = ["id_contrato", "sello_snapshot_utc"]


def ingest(rutas, salida, raw=None):
    """Map every capture, concatenate, validate and write the normalized tables."""
    salida = Path(salida)
    crudos, resumenes, cotizaciones, subyacentes = [], [], [], []
    for ruta in rutas:
        capture = json.loads(Path(ruta).read_text(encoding="utf-8"))
        if raw is not None:
            crudos.append(almacen.guardar_crudo(ruta, raw))
        resumenes.append(robinhood.summary(capture))
        cot, sub = robinhood.tables(capture)
        cotizaciones.append(cot)
        subyacentes.append(sub)

    cot = pd.concat(cotizaciones, ignore_index=True)
    repetidas = int(cot.duplicated(CLAVE).sum())
    cot = cot.drop_duplicates(CLAVE, ignore_index=True)
    sub = pd.concat(subyacentes, ignore_index=True).drop_duplicates(
        ["subyacente", "sello_snapshot_utc"], ignore_index=True)
    cot = cot.sort_values(CLAVE, ignore_index=True)
    sub = sub.sort_values(["subyacente", "sello_snapshot_utc"], ignore_index=True)

    for tabla, esquema, nombre in ((cot, contrato.COTIZACIONES, "quotes"),
                                   (sub, contrato.SUBYACENTE, "underlying")):
        problemas = contrato.validar(tabla, esquema)
        if problemas:
            raise ValueError(f"{nombre}: " + "; ".join(problemas))

    rutas_salida = {"quotes.parquet": salida / "quotes.parquet",
                    "underlying.parquet": salida / "underlying.parquet"}
    almacen.escribir_tabla(cot, rutas_salida["quotes.parquet"])
    almacen.escribir_tabla(sub, rutas_salida["underlying.parquet"])

    manifest = {
        "ingested_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "captures": resumenes,
        "raw": [{k: v for k, v in c.items() if k != "ruta"} for c in crudos],
        "duplicate_rows_dropped": repetidas,
        "rows": {"quotes": int(len(cot)), "underlying": int(len(sub))},
        "sessions_new_york": sorted({str(t) for t in cot["sello_snapshot_utc"]
                                     .dt.tz_convert("America/New_York").dt.date}),
        "provenance": {
            "sello_evento_utc": "null: Robinhood publishes no venue timestamp for option quotes",
            "disponible_utc": "null: no documented historical availability",
            "recibido_utc": "capture time; says nothing about when the value was publishable",
        },
        "environment": almacen.huella_entorno(ROOT),
        "outputs": almacen.hashes(rutas_salida.values()),
    }
    almacen.escribir_json(manifest, salida / "ingest_manifest.json")
    return cot, sub, manifest


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("captures", nargs="+", help="capture JSON files")
    a.add_argument("--output", default=str(ROOT / "data" / "normalized" / "robinhood"))
    a.add_argument("--raw", default=str(ROOT / "data" / "raw"),
                   help="archive for the untouched captures; 'none' to skip")
    args = a.parse_args()
    raw = None if args.raw.lower() == "none" else args.raw
    cot, sub, manifest = ingest(args.captures, args.output, raw)
    print(f"{args.output}: {len(cot)} quote rows, {len(sub)} underlying rows, "
          f"{len(manifest['captures'])} capture(s), sessions {', '.join(manifest['sessions_new_york'])}")
    if manifest["duplicate_rows_dropped"]:
        print(f"  dropped {manifest['duplicate_rows_dropped']} duplicate contract/snapshot rows")
    print("  no event timestamp from this provider: quote age is unknown by construction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
