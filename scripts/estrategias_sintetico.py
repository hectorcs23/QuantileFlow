"""Informe del recomendador de estrategias con datos SINTÉTICOS.

Construye una cadena sintética a unos 30 días, reconstruye la distribución
implícita por el mismo camino que se usaría con cotizaciones reales, declara una
vista y evalúa el catálogo entero. Escribe ``reports/estrategias_sintetico/``.

Además de la vista por omisión de ``configs/estrategias.toml``, genera un
informe por cada vista de contraste: sirven para ver qué cambia en la
recomendación cuando cambia **solo** la opinión, con el mismo mercado.

Uso, desde la raíz del repositorio::

    python scripts/estrategias_sintetico.py
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from estrategias.corrida import correr  # noqa: E402
from estrategias.recomendacion import cargar_config  # noqa: E402
from estrategias.sintetico import mundo  # noqa: E402

# Las intensidades se declaran explícitamente. No se iguala el KL de las vistas:
# los resultados pueden cambiar por tipo e intensidad de opinión.
VISTAS = {
    "alcista": ({"tipo": "tilt_media", "retorno": 0.01},
                "Vista alcista: +1 % sobre el forward, deformación mínima de Q"),
    "alcista_misma_vol": ({"tipo": "tilt_momentos", "retorno": 0.0082, "factor_vol": 1.0},
                          "Vista paramétrica alcista con la dispersión del mercado; sin certificado de mínimo KL"),
    "cola_cara": ({"tipo": "reponderar_cola", "factor": 0.8, "umbral_log": -0.05,
                   "preservar_media": True},
                  "Vista de cola pura: la caída de más del 5 % está sobrevalorada un 20 %, "
                  "sin opinión sobre la dirección"),
    "bajista": ({"tipo": "tilt_media", "retorno": -0.01},
                "Vista bajista: -1 % sobre el forward"),
    "sin_opinion": ({"tipo": "neutral"},
                    "Sin opinión: P = Q, el control negativo del método"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, default=RAIZ / "reports" / "estrategias_sintetico")
    args = parser.parse_args()
    cfg = cargar_config(RAIZ / "configs" / "estrategias.toml")
    m = mundo()
    base = args.salida.resolve()
    for nombre, (especificacion, titulo) in VISTAS.items():
        salida = base / nombre
        resultado, p, manifiesto = correr(
            cfg, m, salida, f"Estrategias con puts: {titulo}",
            aviso="datos sintéticos", especificacion_vista=especificacion)
        print(f"{salida}: {manifiesto['candidatas']['aptas']} de "
              f"{manifiesto['candidatas']['n']} candidatas aptas; "
              f"{manifiesto['dictamen']['accion']}"
              + (f" -> {manifiesto['dictamen']['estructura']}"
                 if manifiesto["dictamen"]["estructura"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
