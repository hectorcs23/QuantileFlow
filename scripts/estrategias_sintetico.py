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
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from estrategias.corrida import correr  # noqa: E402
from estrategias.recomendacion import cargar_config  # noqa: E402
from estrategias.sintetico import mundo  # noqa: E402

# Las cinco vistas tienen un contenido informativo parecido (KL sobre Q del
# orden de 0.01 a 0.015 nats, salvo la neutral), así que la comparación entre
# los informes aísla el **tipo** de opinión, no su intensidad.
VISTAS = {
    "alcista": ({"tipo": "tilt_media", "retorno": 0.01},
                "Vista alcista: +1 % sobre el forward, deformación mínima de Q"),
    # +0.82 % gasta la misma entropía relativa que el +1 % de la vista anterior:
    # exigir que la subida no adelgace la cola por su cuenta sale más caro en
    # información, así que a igual presupuesto la dirección afirmable es menor.
    "alcista_misma_vol": ({"tipo": "tilt_momentos", "retorno": 0.0082, "factor_vol": 1.0},
                          "Vista alcista con la dispersión del mercado: solo dirección, "
                          "al mismo presupuesto de información"),
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
    cfg = cargar_config(RAIZ / "configs" / "estrategias.toml")
    m = mundo()
    base = RAIZ / "reports" / "estrategias_sintetico"
    for nombre, (especificacion, titulo) in VISTAS.items():
        salida = base / nombre
        resultado, p, manifiesto = correr(
            cfg, m, salida, f"Estrategias con puts: {titulo}",
            aviso="datos sintéticos", especificacion_vista=especificacion)
        print(f"{salida.relative_to(RAIZ)}: {manifiesto['candidatas']['aptas']} de "
              f"{manifiesto['candidatas']['n']} candidatas aptas; "
              f"{manifiesto['dictamen']['accion']}"
              + (f" -> {manifiesto['dictamen']['estructura']}"
                 if manifiesto["dictamen"]["estructura"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
