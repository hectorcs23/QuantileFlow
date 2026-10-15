#!/usr/bin/env python3
"""Capturador prospectivo de la serie de 15 minutos.

Uso:

    python3 scripts/capturar.py --duracion 3600 --periodo 5 --raiz datos/captura

No requiere credenciales: solo lee endpoints publicos. Escribe JSONL por
anadido y un manifiesto al terminar. Ctrl-C detiene de forma ordenada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btclab.almacen import Almacen
from btclab.captura import Capturador
from btclab.kalshi import ClienteKalshi, CuboFichas


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--serie", default="KXBTC15M")
    analizador.add_argument("--raiz", default="datos/captura")
    analizador.add_argument("--duracion", type=float, default=300.0,
                            help="segundos de captura; 0 = sin limite")
    analizador.add_argument("--periodo", type=float, default=5.0,
                            help="segundos objetivo entre ciclos")
    analizador.add_argument("--fichas-por-segundo", type=float, default=8.0,
                            help="presupuesto de tasa; bajo a proposito")
    analizador.add_argument("--sin-spot", action="store_true")
    argumentos = analizador.parse_args()

    almacen = Almacen(Path(argumentos.raiz))
    cliente = ClienteKalshi(
        cubo=CuboFichas(fichas_por_segundo=argumentos.fichas_por_segundo)
    )
    capturador = Capturador(
        almacen=almacen,
        cliente=cliente,
        serie=argumentos.serie,
        periodo_s=argumentos.periodo,
        capturar_spot=not argumentos.sin_spot,
    )

    print(f"capturando {argumentos.serie} en {almacen.raiz} ...", flush=True)
    resumen = capturador.correr(
        duracion_s=None if argumentos.duracion <= 0 else argumentos.duracion
    )
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
