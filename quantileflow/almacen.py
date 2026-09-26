"""Almacenamiento reproducible: crudo inmutable, tablas Parquet, manifiestos y entorno.

Disposición propuesta (``data/`` queda fuera de Git; la licencia del
proveedor decide qué muestras pueden ir a ``tests/fixtures``)::

    data/raw/          archivos originales inmutables, direccionados por su SHA-256
    data/normalized/   cotizaciones y subyacente normalizados (Parquet)
    data/labels/       etiquetas con su fecha de disponibilidad
    configs/           configuración del piloto y reglas versionadas
    reports/           informes, tablas y gráficas generados (no se editan a mano)

Cada corrida escribe un manifiesto con los hashes de entradas y salidas, el
commit, la configuración y las exclusiones: reprocesar los mismos archivos con
la misma configuración debe dar exactamente las mismas salidas.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pandas as pd

PAQUETES = ("numpy", "scipy", "matplotlib", "pandas", "pyarrow", "exchange_calendars", "pytest")


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def sha256_archivo(ruta) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def guardar_crudo(origen, directorio) -> dict:
    """Copia un archivo original a ``directorio/<hash[:2]>/<hash>_<nombre>`` en solo lectura.

    Guardar dos veces el mismo contenido no hace nada; si el destino existe con
    otro contenido, falla en lugar de sobrescribir.
    """
    origen = Path(origen)
    h = sha256_archivo(origen)
    destino = Path(directorio) / h[:2] / f"{h}_{origen.name}"
    if destino.exists():
        if sha256_archivo(destino) != h:
            raise RuntimeError(f"{destino} existe con otro contenido: el crudo no se sobrescribe")
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)
        os.chmod(destino, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return {"ruta": str(destino), "sha256": h, "bytes": destino.stat().st_size, "nombre": origen.name}


def escribir_tabla(tabla: pd.DataFrame, ruta) -> str:
    """Escribe una tabla en Parquet (sin índice) y devuelve su SHA-256."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_parquet(ruta, index=False, engine="pyarrow")
    return sha256_archivo(ruta)


def leer_tabla(ruta) -> pd.DataFrame:
    return pd.read_parquet(ruta, engine="pyarrow")


def escribir_json(datos, ruta) -> str:
    """JSON determinista (claves ordenadas); devuelve el SHA-256 del archivo."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8")
    return sha256_archivo(ruta)


def huella_datos(datos) -> str:
    """SHA-256 de una estructura (p. ej., la configuración) serializada de forma canónica."""
    return sha256_bytes(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))


def estado_git(directorio=".") -> dict:
    """Commit completo y si el árbol de trabajo tiene cambios sin registrar."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=directorio, capture_output=True,
                                text=True, check=True).stdout.strip()
        cambios = subprocess.run(["git", "status", "--porcelain"], cwd=directorio, capture_output=True,
                                 text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "cambios_sin_registrar": None}
    return {"commit": commit, "cambios_sin_registrar": bool(cambios)}


def huella_entorno(directorio=".") -> dict:
    """Versión de Python, plataforma, versiones de paquetes y estado de Git."""
    versiones = {}
    for paquete in PAQUETES:
        try:
            versiones[paquete] = metadata.version(paquete)
        except metadata.PackageNotFoundError:
            versiones[paquete] = None
    return {"python": sys.version.split()[0], "plataforma": platform.platform(),
            "paquetes": versiones, "git": estado_git(directorio)}


def hashes(rutas) -> dict:
    """Mapa nombre de archivo -> SHA-256 (orden estable)."""
    return {Path(r).name: sha256_archivo(r) for r in sorted(rutas, key=lambda r: Path(r).name)}
