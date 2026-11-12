"""Prueba manual aislada de indicative/IEX; plan por omisión, sin llamar API."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "experiments/expiraciones_20261008/captura_propuesta.toml"


def validar(config, destino):
    c = config["captura"]
    if c["feed_opciones"] != "indicative" or c["feed_acciones"] != "iex":
        raise ValueError("esta prueba admite exclusivamente indicative/IEX; presupuesto $0")
    if config["historico"]["feed"] != "sip":
        raise ValueError("no cambiar el histórico del piloto en esta prueba")
    if not (1 <= c["hilos"] <= 12 and 0 <= c["reintentos"] <= 2 and 0 < c["plazo_s"] <= 60
            and 0 < c["ventana_contratos_dias"] <= 120):
        raise ValueError("configuración fuera de los límites de la prueba")
    if destino is not None:
        destino = Path(destino).resolve()
        if destino.exists():
            raise ValueError("usar un directorio nuevo: no mezclar con el almacén diario")
        if any((p / ".git").exists() for p in (destino, *destino.parents)):
            raise ValueError("el destino de datos debe estar fuera de cualquier checkout Git")
    return destino


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=CONFIG)
    p.add_argument("--datos", type=Path)
    p.add_argument("--ejecutar", action="store_true", help="una captura inmediata, privada; requiere claves en entorno")
    args = p.parse_args()
    try:
        texto = args.config.read_text(encoding="utf-8")
        config = tomllib.loads(texto)
        destino = validar(config, args.datos)
        if args.ejecutar and (destino is None or not all(os.environ.get(k) for k in
                ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"))):
            raise ValueError("para ejecutar hacen falta --datos nuevo y claves ya configuradas en el entorno")
    except (ValueError, KeyError, OSError, tomllib.TOMLDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({"presupuesto_datos_usd": 0, "modo": "ejecutar" if args.ejecutar else "plan sin red",
        "version": config["captura"]["version"],
        "plazos_dias": {o["raiz"]: o.get("objetivos_dias",[o.get("objetivo_dias")])
                        for o in config["captura"]["opciones"]},
        "timeout_proceso_s": 180, "feeds": ["indicative", "iex"],
        "advertencia": "captura inmediata diagnóstica; no activa horarios ni valida elegibilidad causal"},
        ensure_ascii=False, indent=2))
    if not args.ejecutar:
        return 0
    # Mismo TOML que se validó: copia privada para evitar cambios entre lectura y ejecución.
    destino.mkdir(parents=True, exist_ok=False)
    cfg = destino / "config_prueba.toml"
    cfg.write_text(texto, encoding="utf-8")
    try:
        resultado = subprocess.run([sys.executable, str(RAIZ / "scripts/capturar_alpaca.py"),
            "--config", str(cfg), "--datos", str(destino), "--ahora", "--plazo-s", "60"],
            timeout=180, check=False)
        return resultado.returncode
    except subprocess.TimeoutExpired:
        print("plazo global de 180 s vencido; crudo recibido permanece en el directorio privado", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
