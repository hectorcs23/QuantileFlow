"""Ejecuta el piloto sobre tablas normalizadas (Parquet o CSV) y escribe informe y manifiesto.

Uso, desde la raíz del repositorio::

    python scripts/piloto.py --cotizaciones data/normalized/cotizaciones.parquet \
        --subyacente data/normalized/subyacente.parquet --desde 2025-10-20 --hasta 2025-12-01

Las tablas deben seguir los esquemas de ``quantileflow/contrato.py``; un
problema de validación detiene la corrida. Si una serie trae varias fuentes
(``proveedor/feed``), hay que elegirlas: ``--fuente-opciones alpaca/opra``,
``--fuente-referencia alpaca/implicito_paridad_SPXW_opra`` (subyacente de las
opciones) y ``--fuente-objetivo alpaca/sip`` (precio cuyo rendimiento se
etiqueta). ``--dividendos`` añade los dividendos del objetivo.
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
    a.add_argument("--dividendos", default=None, help="tabla de dividendos (Parquet o CSV), opcional")
    a.add_argument("--fuente-opciones", nargs="+", default=None, help="una o varias fuentes proveedor/feed")
    a.add_argument("--fuente-referencia", default=None, help="fuente proveedor/feed del subyacente de las opciones")
    a.add_argument("--fuente-objetivo", default=None, help="fuente proveedor/feed del precio objetivo")
    args = a.parse_args()
    resultado, manifiesto = correr(args.config, args.cotizaciones, args.subyacente, args.desde, args.hasta,
                                   args.salida, args.titulo, fuentes_opciones=args.fuente_opciones,
                                   fuente_referencia=args.fuente_referencia, fuente_objetivo=args.fuente_objetivo,
                                   dividendos=args.dividendos)
    print(f"{args.salida}: {manifiesto['sesiones']['n']} sesiones; dictamen: {manifiesto['dictamen']}; "
          f"evaluación con precios de mercado: {manifiesto['alcance']['evaluacion_con_precios_de_mercado']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
