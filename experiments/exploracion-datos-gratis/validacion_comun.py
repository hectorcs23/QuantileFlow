"""Provenance and strict JSON for retrospective exploratory validation."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import numpy as np


def limpio(value):
    if isinstance(value, dict):
        return {str(k): limpio(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [limpio(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def guardar(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(limpio(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def procedencia(repo, archivos, parametros):
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    scripts = sorted((Path(__file__).parent).glob('*.py'))
    return {'generado_utc': datetime.now(timezone.utc).isoformat(), 'commit_base': commit,
            'codigo_sha256': {p.name: sha(p) for p in scripts},
            'archivos_sha256': {p.name: sha(p) for p in archivos},
            'parametros': parametros, 'python': platform.python_version(),
            'dependencias': {name: importlib.metadata.version(name) for name in
                             ('numpy', 'pandas', 'scipy', 'exchange_calendars')},
            'diseno': 'Validación retrospectiva; la historia ya fue examinada, no es un holdout nuevo.'}
