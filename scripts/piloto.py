"""Ejecuta el piloto sobre tablas normalizadas (Parquet o CSV) y escribe informe y manifiesto.

Uso, desde la raíz del repositorio::

    python scripts/piloto.py --cotizaciones data/normalized/cotizaciones.parquet \
        --subyacente data/normalized/subyacente.parquet --desde 2025-10-20 --hasta 2025-12-01

Las tablas deben seguir los esquemas de ``quantileflow/contrato.py``; un
problema de validación detiene la corrida.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow.corrida import correr  # noqa: E402


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--config", default=str(RAIZ / "configs" / "piloto.toml"))
    a.add_argument("--cotizaciones", required=True)
    a.add_argument("--subyacente", required=True)
    a.add_argument("--desde", required=True)
    a.add_argument("--hasta", required=True)
    a.add_argument("--salida", default=str(RAIZ / "reports" / "piloto"))
    a.add_argument("--titulo", default="Informe piloto de sesiones de apertura")
    args = a.parse_args()
    resultado, manifiesto = correr(args.config, args.cotizaciones, args.subyacente, args.desde, args.hasta,
                                   args.salida, args.titulo)
    print(f"{args.salida}: {manifiesto['sesiones']['n']} sesiones; dictamen: {manifiesto['dictamen']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
