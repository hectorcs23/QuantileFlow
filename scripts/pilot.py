"""Run the pilot over normalized tables (Parquet or CSV) and write report and manifest.

Usage, from the repository root::

    python scripts/pilot.py --quotes data/normalized/quotes.parquet \
        --underlying data/normalized/underlying.parquet --from 2025-10-20 --to 2025-12-01

The tables must follow the schemas in ``quantileflow/contrato.py``; a validation
problem stops the run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantileflow.corrida import correr  # noqa: E402


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--config", default=str(ROOT / "configs" / "pilot.toml"))
    a.add_argument("--quotes", required=True, help="normalized quotes table")
    a.add_argument("--underlying", required=True, help="normalized underlying table")
    a.add_argument("--from", dest="desde", required=True, metavar="YYYY-MM-DD")
    a.add_argument("--to", dest="hasta", required=True, metavar="YYYY-MM-DD")
    a.add_argument("--output", default=str(ROOT / "reports" / "pilot"))
    a.add_argument("--title", default="Opening-session pilot report")
    args = a.parse_args()
    _, manifest = correr(args.config, args.quotes, args.underlying, args.desde, args.hasta,
                         args.output, args.title)
    print(f"{args.output}: {manifest['sessions']['n']} sessions; verdict: {manifest['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
