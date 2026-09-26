"""Registra la versión de referencia: commit, entorno y resultado de las pruebas.

Uso, desde la raíz del repositorio::

    python scripts/verificar_entorno.py

Escribe ``reports/verificacion/<commit>.json``. Si el árbol tiene cambios sin
registrar, el registro lo indica: la versión de referencia debe verificarse
sobre un commit limpio.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow import almacen  # noqa: E402


def main() -> int:
    entorno = almacen.huella_entorno(RAIZ)
    proceso = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RAIZ,
                             capture_output=True, text=True)
    lineas = [x for x in proceso.stdout.splitlines() if x.strip()]
    registro = {
        "fecha_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "entorno": entorno,
        "pruebas": {"codigo_salida": proceso.returncode, "resumen": lineas[-1] if lineas else ""},
    }
    commit = entorno["git"]["commit"] or "sin_git"
    ruta = RAIZ / "reports" / "verificacion" / f"{commit[:12]}.json"
    almacen.escribir_json(registro, ruta)
    estado = "con cambios sin registrar" if entorno["git"]["cambios_sin_registrar"] else "limpio"
    print(f"{ruta.relative_to(RAIZ)}: {registro['pruebas']['resumen']} ({estado})")
    return proceso.returncode


if __name__ == "__main__":
    sys.exit(main())
