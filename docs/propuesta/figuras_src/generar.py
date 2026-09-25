"""Genera todas las figuras del documento (datos sintéticos, semillas fijas).

Uso, desde la raíz del repositorio::

    python docs/propuesta/figuras_src/generar.py

Las gráficas usan matplotlib con su estilo por defecto y se guardan como PNG en
``docs/propuesta/figuras``.
"""
from __future__ import annotations

import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(RAIZ))

import fig_s1_s2  # noqa: E402
import fig_s3  # noqa: E402
import fig_s4_s5  # noqa: E402
import fig_s6_s7  # noqa: E402


def main():
    rutas = []
    for modulo in (fig_s1_s2, fig_s3, fig_s4_s5, fig_s6_s7):
        rutas += modulo.main()
    for r in rutas:
        print(r.relative_to(RAIZ))
    print(f"{len(rutas)} figuras")


if __name__ == "__main__":
    main()
