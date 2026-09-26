"""Plantilla del informe piloto con datos SINTÉTICOS, por el mismo camino que los reales.

1. Genera un mercado tipo SPXW de 30 sesiones con escenarios de mala calidad.
2. Lo guarda como archivos «del proveedor» inmutables en ``data/raw`` (fuera de Git).
3. Normaliza y valida, escribe Parquet en ``data/normalized/sintetico``.
4. Ejecuta el piloto y escribe ``reports/piloto_sintetico``.

Uso, desde la raíz del repositorio::

    python scripts/piloto_sintetico.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

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
    datos = RAIZ / "data"
    trabajo = datos / "tmp"
    trabajo.mkdir(parents=True, exist_ok=True)
    cot, sub, _ = mercado_sintetico(sesiones(DESDE, HASTA), semilla=7, escenarios=ESCENARIOS)
    crudos = []
    for nombre, tabla in (("cotizaciones_sinteticas.csv", cot), ("subyacente_sintetico.csv", sub)):
        tabla.to_csv(trabajo / nombre, index=False, lineterminator="\n")
        crudos.append(almacen.guardar_crudo(trabajo / nombre, datos / "raw"))
    normal = datos / "normalized" / "sintetico"
    rutas = {}
    for info, esquema, nombre in ((crudos[0], contrato.COTIZACIONES, "cotizaciones.parquet"),
                                  (crudos[1], contrato.SUBYACENTE, "subyacente.parquet")):
        rutas[nombre] = normal / nombre
        almacen.escribir_tabla(contrato.leer_csv_normalizado(info["ruta"], esquema), rutas[nombre])
    salida = RAIZ / "reports" / "piloto_sintetico"
    _, manifiesto = correr(RAIZ / "configs" / "piloto.toml", rutas["cotizaciones.parquet"],
                           rutas["subyacente.parquet"], DESDE, HASTA, salida,
                           "Informe piloto: plantilla con datos sintéticos", aviso="datos sintéticos",
                           crudos=[{k: v for k, v in c.items() if k != "ruta"} for c in crudos])
    print(f"{salida.relative_to(RAIZ)}: {manifiesto['sesiones']['n']} sesiones; dictamen: {manifiesto['dictamen']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
