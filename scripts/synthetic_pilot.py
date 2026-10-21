"""Pilot report template on SYNTHETIC data, down the same path as real data.

1. Generates an SPXW-like market of 30 sessions with poor-quality scenarios.
2. Stores it as immutable "provider" files under ``data/raw`` (outside Git).
3. Normalizes and validates, writes Parquet to ``data/normalized/synthetic``.
4. Runs the pilot and writes ``reports/synthetic_pilot``.

Usage, from the repository root::

    python scripts/synthetic_pilot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantileflow import almacen, contrato  # noqa: E402
from quantileflow.calendario import sesiones  # noqa: E402
from quantileflow.corrida import correr  # noqa: E402
from quantileflow.sintetico import mercado_sintetico  # noqa: E402

DESDE, HASTA = "2025-10-20", "2025-12-01"  # incluye Acción de Gracias y un cierre anticipado
ESCENARIOS = {
    "2025-10-23": ["desfasadas"],
    "2025-10-29": ["sin_hora_evento"],
    "2025-11-05": ["hueco_calls"],
    "2025-11-12": ["spreads_anchos"],
    "2025-11-18": ["spot_desfasado"],
    "2025-11-20": ["sin_subyacente"],
}


def main() -> int:
    datos = ROOT / "data"
    trabajo = datos / "tmp"
    trabajo.mkdir(parents=True, exist_ok=True)
    cot, sub, _ = mercado_sintetico(sesiones(DESDE, HASTA), semilla=7, escenarios=ESCENARIOS)
    crudos = []
    for nombre, tabla in (("synthetic_quotes.csv", cot), ("synthetic_underlying.csv", sub)):
        tabla.to_csv(trabajo / nombre, index=False, lineterminator="\n")
        crudos.append(almacen.guardar_crudo(trabajo / nombre, datos / "raw"))
    normal = datos / "normalized" / "synthetic"
    rutas = {}
    for info, esquema, nombre in ((crudos[0], contrato.COTIZACIONES, "quotes.parquet"),
                                  (crudos[1], contrato.SUBYACENTE, "underlying.parquet")):
        rutas[nombre] = normal / nombre
        almacen.escribir_tabla(contrato.leer_csv_normalizado(info["ruta"], esquema), rutas[nombre])
    salida = ROOT / "reports" / "synthetic_pilot"
    _, manifiesto = correr(ROOT / "configs" / "pilot.toml", rutas["quotes.parquet"],
                           rutas["underlying.parquet"], DESDE, HASTA, salida,
                           "Pilot report: template on synthetic data", aviso="synthetic data",
                           crudos=[{k: v for k, v in c.items() if k != "ruta"} for c in crudos])
    print(f"{salida.relative_to(ROOT)}: {manifiesto['sessions']['n']} sessions; "
          f"verdict: {manifiesto['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
