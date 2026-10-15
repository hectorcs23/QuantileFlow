#!/usr/bin/env python3
"""Reporte de cobertura del almacen (entrega de la Fase B)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btclab.almacen import Almacen
from btclab.cobertura import auditar, suficiente_para


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--raiz", default="datos/captura")
    analizador.add_argument("--salida", default="")
    analizador.add_argument("--intervalo-libro", type=float, default=10.0)
    analizador.add_argument("--intervalo-spot", type=float, default=10.0)
    argumentos = analizador.parse_args()

    almacen = Almacen(Path(argumentos.raiz))
    reporte = auditar(
        almacen,
        {
            "libro": argumentos.intervalo_libro,
            "mercado": argumentos.intervalo_libro,
            "spot": argumentos.intervalo_spot,
        },
    )
    # Minimos declarados antes de mirar los datos; ver docs/protocolo.md.
    ok, motivos = suficiente_para(
        reporte,
        {
            "observaciones_por_flujo": {"libro": 2000, "mercado": 2000, "spot": 2000},
            "contratos_con_resultado": 200,
        },
    )
    reporte["suficiente_para_fase_C"] = ok
    reporte["motivos_insuficiencia"] = list(motivos)

    texto = json.dumps(reporte, indent=2, ensure_ascii=False)
    if argumentos.salida:
        Path(argumentos.salida).write_text(texto + "\n", encoding="utf-8")
        print(f"escrito en {argumentos.salida}")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
