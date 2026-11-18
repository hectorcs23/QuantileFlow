"""Baja un día de cotizaciones cripto de Alpaca al crudo inmutable.

    python scripts/capturar.py 2026-11-10 [--destino datos_crudos] [--pares subgrafo]

Un directorio por día y por conjunto de pares. Volver a correrlo con el mismo
día no reescribe nada si ya existe el manifiesto: el crudo es inmutable.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from holonomia import datos  # noqa: E402

# Subgrafo líquido de la Fase 1: nueve monedas, 26 pares, todos los cruces
# cripto-cripto que hacen la holonomía no trivial.
SUBGRAFO = (
    "BTC/USD", "BTC/USDT", "BTC/USDC",
    "ETH/USD", "ETH/USDT", "ETH/USDC", "ETH/BTC",
    "LTC/USD", "LTC/USDT", "LTC/USDC", "LTC/BTC",
    "BCH/USD", "BCH/USDT", "BCH/USDC", "BCH/BTC",
    "LINK/USD", "LINK/USDT", "LINK/USDC", "LINK/BTC",
    "UNI/USD", "UNI/USDT", "UNI/USDC", "UNI/BTC",
    "USDT/USD", "USDT/USDC", "USDC/USD",
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dia", help="fecha UTC, AAAA-MM-DD")
    p.add_argument("--destino", default="datos_crudos")
    p.add_argument("--horas", type=float, default=24.0, help="horas desde las 00:00 UTC")
    args = p.parse_args()

    dia = dt.date.fromisoformat(args.dia)
    inicio = dt.datetime.combine(dia, dt.time(0, 0), tzinfo=dt.timezone.utc)
    fin = inicio + dt.timedelta(hours=args.horas)
    destino = Path(args.destino) / f"quotes-{args.dia}"

    if (destino / "manifiesto.json").exists():
        print(f"ya existe, no se toca: {destino}")
        return 0

    print(f"bajando {len(SUBGRAFO)} pares, {inicio:%Y-%m-%d %H:%M} a {fin:%Y-%m-%d %H:%M} UTC")
    datos.descargar_quotes(SUBGRAFO, inicio.isoformat().replace("+00:00", "Z"),
                           fin.isoformat().replace("+00:00", "Z"), destino)
    total = sum(f.stat().st_size for f in destino.glob("*.gz"))
    print(f"listo: {destino}  ({len(list(destino.glob('*.gz')))} páginas, {total/2**20:.1f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
