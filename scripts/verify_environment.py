"""Record the reference version: commit, environment and test outcome.

Usage, from the repository root::

    python scripts/verify_environment.py

Writes ``reports/verification/<commit>.json``. If the tree has uncommitted
changes the record says so: the reference version must be verified on a clean
commit.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantileflow import almacen  # noqa: E402


def main() -> int:
    environment = almacen.huella_entorno(ROOT)
    proceso = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                             capture_output=True, text=True)
    lineas = [x for x in proceso.stdout.splitlines() if x.strip()]
    record = {
        "date_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "environment": environment,
        "tests": {"exit_code": proceso.returncode, "summary": lineas[-1] if lineas else ""},
    }
    commit = environment["git"]["commit"] or "no_git"
    ruta = ROOT / "reports" / "verification" / f"{commit[:12]}.json"
    almacen.escribir_json(record, ruta)
    estado = "with uncommitted changes" if environment["git"]["uncommitted_changes"] else "clean"
    print(f"{ruta.relative_to(ROOT)}: {record['tests']['summary']} ({estado})")
    return proceso.returncode


if __name__ == "__main__":
    sys.exit(main())
