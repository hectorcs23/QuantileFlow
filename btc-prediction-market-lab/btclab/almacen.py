"""Almacen append-only del crudo, con manifiesto (Paso 2).

Reglas que impone:

* El payload original se guarda intacto. Las variables derivadas se recalculan
  desde el crudo, nunca al contrario.
* Cada registro lleva ``event_time``, ``received_at``, fuente, contrato,
  secuencia y unidad.
* El archivo es de solo anadir. No se reescriben registros pasados: una revision
  entra como registro nuevo con su propio ``received_at``, de modo que el estado
  de informacion de cualquier momento anterior sigue siendo reconstruible.
* El manifiesto guarda hash del contenido y huella del entorno para poder
  repetir una corrida.

Formato: JSONL, una linea por registro. Se eligio frente a Parquet porque
``pyarrow`` no esta disponible en el entorno auditado y el capturador debe poder
ejecutarse sin instalar nada.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator

from .tiempo import Observacion, a_iso, ahora, desde_iso


class ErrorAlmacen(RuntimeError):
    """Fallo de escritura o lectura del almacen."""


def _serializar(objeto):
    if isinstance(objeto, Decimal):
        return str(objeto)
    raise TypeError(f"no serializable: {type(objeto)}")


@dataclass
class Almacen:
    """Carpeta de datos con escritura por anadido.

    Los registros se agrupan por ``flujo`` (por ejemplo ``libro``, ``mercado``,
    ``spot``, ``resultado``) y por dia UTC, para que una corrida pueda leer solo
    el tramo que necesita.
    """

    raiz: Path

    def __post_init__(self) -> None:
        self.raiz = Path(self.raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)

    def ruta(self, flujo: str, dia: str) -> Path:
        if not flujo or "/" in flujo or ".." in flujo:
            raise ErrorAlmacen(f"flujo invalido: {flujo!r}")
        carpeta = self.raiz / flujo
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta / f"{dia}.jsonl"

    def anadir(
        self,
        flujo: str,
        observacion: Observacion,
        contrato: str = "",
        unidad: str = "",
    ) -> None:
        """Escribe un registro. Nunca modifica lo ya escrito."""
        registro = {
            "event_time": a_iso(observacion.event_time),
            "received_at": a_iso(observacion.received_at),
            "fuente": observacion.fuente,
            "contrato": contrato,
            "secuencia": observacion.secuencia,
            "unidad": unidad,
            "latencia_s": observacion.latencia_s,
            "payload": observacion.payload,
        }
        dia = a_iso(observacion.received_at)[:10]
        linea = json.dumps(
            registro, default=_serializar, ensure_ascii=False, sort_keys=True
        )
        ruta = self.ruta(flujo, dia)
        try:
            with ruta.open("a", encoding="utf-8") as destino:
                destino.write(linea + "\n")
        except OSError as exc:
            raise ErrorAlmacen(f"no se pudo escribir en {ruta}: {exc}") from exc

    def leer(self, flujo: str, dias: Iterable[str] | None = None) -> Iterator[dict]:
        """Lee registros en orden de archivo.

        Una linea corrupta no aborta la lectura: se cuenta como hueco y se omite,
        porque un archivo truncado por una caida es un caso esperado.
        """
        carpeta = self.raiz / flujo
        if not carpeta.exists():
            return
        archivos = (
            sorted(carpeta.glob("*.jsonl"))
            if dias is None
            else [self.ruta(flujo, d) for d in sorted(dias)]
        )
        for archivo in archivos:
            if not archivo.exists():
                continue
            with archivo.open("r", encoding="utf-8") as origen:
                for numero, linea in enumerate(origen, start=1):
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        registro = json.loads(linea)
                    except json.JSONDecodeError:
                        yield {
                            "_corrupto": True,
                            "_archivo": str(archivo),
                            "_linea": numero,
                        }
                        continue
                    yield registro

    def flujos(self) -> tuple[str, ...]:
        return tuple(
            sorted(p.name for p in self.raiz.iterdir() if p.is_dir())
        )

    def hash_flujo(self, flujo: str) -> str:
        """Hash del contenido de un flujo, para el manifiesto."""
        digest = hashlib.sha256()
        carpeta = self.raiz / flujo
        if not carpeta.exists():
            return ""
        for archivo in sorted(carpeta.glob("*.jsonl")):
            digest.update(archivo.name.encode("utf-8"))
            with archivo.open("rb") as origen:
                for bloque in iter(lambda: origen.read(1 << 20), b""):
                    digest.update(bloque)
        return digest.hexdigest()[:16]

    def manifiesto(self, extra: dict | None = None) -> dict:
        """Huella de datos y entorno de una corrida."""
        datos = {
            "generado_en": a_iso(ahora()),
            "raiz": str(self.raiz),
            "flujos": {f: self.hash_flujo(f) for f in self.flujos()},
            "entorno": {
                "python": sys.version.split()[0],
                "plataforma": platform.platform(),
                "pid_usuario": os.getuid() if hasattr(os, "getuid") else None,
            },
        }
        if extra:
            datos["extra"] = extra
        return datos

    def escribir_manifiesto(self, extra: dict | None = None) -> Path:
        destino = self.raiz / "manifiesto.json"
        contenido = json.dumps(
            self.manifiesto(extra), default=_serializar, indent=2, ensure_ascii=False
        )
        destino.write_text(contenido + "\n", encoding="utf-8")
        return destino


def registro_a_observacion(registro: dict) -> Observacion:
    """Reconstruye una ``Observacion`` desde una linea del almacen."""
    if registro.get("_corrupto"):
        raise ErrorAlmacen(f"registro corrupto: {registro}")
    return Observacion(
        event_time=desde_iso(registro["event_time"], "event_time"),
        received_at=desde_iso(registro["received_at"], "received_at"),
        fuente=registro["fuente"],
        payload=registro["payload"],
        secuencia=registro.get("secuencia"),
    )
