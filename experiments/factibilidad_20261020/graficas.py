"""Gráfica de agregados; sin cotizaciones por contrato ni anclas de mercado."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    out = Path(__file__).parent / "resultados"
    r = json.loads((out / "resumen.json").read_text(encoding="utf-8"))
    a = pd.DataFrame(r["agregado"])
    a = a[(a.ancho == .1) & a.grupo.eq("training") & a.objetivo.eq("maximo")]
    levels = ["paridad_cotas", "verticales", "convexidad"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 6), layout="constrained", gridspec_kw={"width_ratios": [1.05, 1]})
    x = np.arange(3)
    for j, (f, d, label, color) in enumerate([
        (False, False, "F y D de referencia", "#355e8d"),
        (True, False, "F libre; D de referencia", "#2a9d8f"),
        (True, True, "F y D libres (control extremo)", "#d58b39")]):
        g = a[(a.forward_libre == f) & (a.descuento_libre == d)].set_index("nivel").loc[levels]
        bars = ax[0].bar(x + (j - 1) * .25, g.mediana_relajacion, .23, label=label, color=color)
        ax[0].bar_label(bars, fmt="%.2f", padding=3, fontsize=9)
    ax[0].set_xticks(x, ["Paridad\ny cotas", "+ Diferencias\nentre strikes", "+ Convexidad"])
    ax[0].set(ylabel="Mediana del mínimo ajuste máximo (spreads completos)",
              title="Liberar las referencias ayuda, pero no resuelve", ylim=(0, 3.2))
    ax[0].legend(loc="upper left", fontsize=8)
    ax[0].spines[["top", "right"]].set_visible(False)
    df = pd.DataFrame(json.loads((out / "por_rebanada.json").read_text(encoding="utf-8")))
    df = df[(df.ancho == .1) & df.grupo.eq("training") & df.objetivo.eq("maximo")
            & df.nivel.eq("convexidad") & df.descuento_libre].copy()
    df["foto"] = df.fecha.str[5:] + " " + df.hora
    df["plazo"] = df.groupby("foto").dias.rank(method="dense").astype(int)
    z = df.pivot(index="foto", columns="plazo", values="relajacion").sort_index()
    im = ax[1].imshow(z.to_numpy(), cmap="YlOrRd", aspect="auto", vmin=0, vmax=12)
    for i in range(len(z)):
        for j in range(4):
            v = z.iloc[i, j]
            ax[1].text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                       color="white" if v > 6 else "#222222")
    ax[1].set_xticks(range(4), ["1", "2", "3", "4"])
    ax[1].set_yticks(range(len(z)), z.index, fontsize=8)
    ax[1].set(title="48 de 48 combinaciones requieren ajuste",
              xlabel="Vencimiento, de menor a mayor (alrededor de 30 días)")
    fig.colorbar(im, ax=ax[1], label="Mínimo ajuste máximo / spread original")
    fig.suptitle("No basta con cambiar de superficie: las bandas son incompatibles", fontsize=14)
    fig.text(.01, -.045, "6 sesiones conocidas · 12 fotos · entrenamiento, ventana ±0.10 en log(K/F inicial)\n"
             "Cada número mide el peor ajuste necesario; no significa que todos los precios requieran ese cambio.",
             fontsize=9)
    fig.savefig(out / "diagnostico_bandas.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
