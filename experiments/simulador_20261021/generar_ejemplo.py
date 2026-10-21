"""Guarda el ejemplo sintético y su figura, sin consultar servicios de mercado."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from quantileflow.simulador import simular


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, default=Path(__file__).parent / "resultados")
    args = parser.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)
    resultado = simular()
    fuentes = [
        "quantileflow/simulador.py", "quantileflow/escenarios.py", "quantileflow/opciones.py",
        "scripts/simulador_opciones.py", "apps/simulador/index.html",
        "apps/simulador/app.js", "apps/simulador/style.css",
        "tests/test_simulador.py", "apps/simulador/verificar_ui.cjs",
        "experiments/simulador_20261021/generar_ejemplo.py",
    ]
    resultado["sha256_fuentes_lf"] = {
        p: hashlib.sha256((RAIZ/p).read_text(encoding="utf-8").encode()).hexdigest()
        for p in fuentes
    }
    # LF explícito para reproducir también fuera de Windows.
    (args.salida/"ejemplo.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False)+"\n",
        encoding="utf-8", newline="\n")
    p = resultado["posiciones"][0]
    top = resultado["posiciones"][:4]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), layout="constrained")
    x = np.arange(len(top))
    a = axes[0].bar(x-.19, [f["pnl_objetivo"] for f in top], .38,
                   color="#17668b", label="Sube 3% en 7 días")
    b = axes[0].bar(x+.19, [f["controles"][-1]["pnl"] for f in top], .38,
                   color="#a3481a", label="Sube 3% en 14 días")
    axes[0].bar_label(a, fmt="$%.0f", padding=4)
    axes[0].bar_label(b, fmt="$%.0f", padding=4)
    axes[0].set_xticks(x, [f"{f['cantidad']} call(s)\nK {f['strike']:g} · {f['dte']:g} DTE"
                          for f in top], fontsize=9)
    axes[0].set(title="El plazo cambia la comparación", ylabel="PnL neto de toda la posición, USD")
    axes[0].set_ylim(-340, 250)
    axes[0].legend(loc="upper right", fontsize=9)
    etiquetas = ["+3% · 7 días", "No se mueve", "Baja 3%", "+3% · IV −5 pp", "+3% · 14 días"]
    vals = [c["pnl"] for c in p["controles"]]
    barras = axes[1].barh(etiquetas, vals, color=["#17668b" if v>=0 else "#a3481a" for v in vals])
    axes[1].bar_label(barras, fmt="$%.0f", padding=5)
    axes[1].invert_yaxis()
    axes[1].set(title="La misma compra: 3 calls K103 / 14 DTE",
                xlabel="PnL neto de la posición, USD", xlim=(-360, 240))
    for ax in axes:
        ax.spines[["top","right"]].set_visible(False)
    axes[0].axhline(0,color="#55656c",lw=.8)
    axes[1].axvline(0,color="#55656c",lw=.8)
    fig.suptitle("QuantileFlow · Presupuesto $300 · Ejemplo sintético, sin probabilidades estimadas",
                 fontsize=13)
    fig.savefig(args.salida/"resultado.png",dpi=160)
    plt.close(fig)
    print(json.dumps({"ganador": resultado["mejor_objetivo"],
                      "capital_reservado": p["capital_reservado"],
                      "efectivo_libre": p["efectivo_libre"],
                      "controles": [{"nombre": c["nombre"], "pnl": c["pnl"]} for c in p["controles"]]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
