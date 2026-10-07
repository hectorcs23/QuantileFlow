"""Genera una figura agregada; no accede a cotizaciones individuales."""
import json
import os
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(HERE / "matplotlib"))
import matplotlib.pyplot as plt
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--resultados", type=Path, default=HERE / "resultados")
parser.add_argument("--figura", type=Path, default=HERE / "HALLAZGOS_INTRADIA.png")
args = parser.parse_args()
d = json.loads((args.resultados / "resultados.json").read_text(encoding="utf-8"))
dates = d["fechas"]
n_dates = len(dates)
labels = [f"{int(day[8:])} oct" if day[5:7] == "10" else day for day in dates]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False})
fig = plt.figure(figsize=(13.5, 9.5), facecolor="#f6f8fc")
gs = fig.add_gridspec(2, 2, left=.07, right=.97, top=.84, bottom=.22, hspace=.5, wspace=.3)
axes = [fig.add_subplot(gs[0, :]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])]
blue, green, red = "#2268a2", "#159584", "#ce6e4c"
for ax in axes:
    ax.set_facecolor("#f6f8fc")
    ax.grid(axis="y", color="#dce3eb", linewidth=.7)
    ax.set_axisbelow(True)
for j, root in enumerate(["SPXW", "SPY"]):
    s = [r for r in d["rr25"] if r["raiz"] == root]
    y = np.array([r["cambio"] for r in s])
    lo = np.array([r["cambio_inferior"] for r in s])
    hi = np.array([r["cambio_superior"] for r in s])
    axes[0].errorbar(np.arange(n_dates) + (j-.5)*.15, y, yerr=[y-lo, hi-y],
                     fmt="o", color=[blue,green][j], label=root, capsize=5, markersize=8, linewidth=2)
axes[0].axhline(0, color="#5d6878", linewidth=1, linestyle="--")
axes[0].set_xticks(range(n_dates), labels)
axes[0].set_xlim(-.45, n_dates-.55)
axes[0].set_ylabel("Cambio de RR25 (puntos de IV)")
rr_spxw = [r for r in d["rr25"] if r["raiz"] == "SPXW"]
inside = sum(not r["intervalos_separados"] for r in rr_spxw)
axes[0].set_title(f"1. Cambio entre cortes: SPXW dentro de las bandas en {inside}/{n_dates} sesiones", loc="left", weight="bold", pad=15)
axes[0].legend(frameon=False, ncol=2, loc="upper left")

monthly = [r for r in d["cambios"] if r["segmento"] == "plazo_mensual"]
bottom = np.zeros(n_dates)
for key, label, color in [("persisten_mismo_signo", "Persiste, mismo signo", blue),
                          ("regresan_a_banda", "Vuelve a la banda", green),
                          ("cambian_signo_fuera", "Cambia de signo, fuera", red)]:
    values = np.array([100*r[key]/r["fuera_0945"] if r["fuera_0945"] else 0. for r in monthly])
    axes[1].bar(range(n_dates), values, bottom=bottom, color=color, label=label, width=.65)
    for i, v in enumerate(values):
        axes[1].text(i, bottom[i]+v/2, f"{v:.0f}%", ha="center", va="center", color="white", weight="bold")
    bottom += values
axes[1].set_xticks(range(n_dates), [f'{label}\nn={r["fuera_0945"]}' for label, r in zip(labels, monthly)])
axes[1].set_ylim(0, 100)
axes[1].set_ylabel("Pares fuera de banda a las 09:45 (%)")
axes[1].set_title("2. Poca persistencia a 15 minutos\nSPXW, vencimientos de alrededor de un mes", loc="left", weight="bold", fontsize=12, pad=15)
axes[1].legend(frameon=False, bbox_to_anchor=(0,-.2), loc="upper left", fontsize=9)

sel = {r["segmento"]: r for r in d["seleccion_vs_reajuste"]}
for j, (key, label, color) in enumerate([
    ("todos_base", "Base", blue),
    ("cohorte_comun_base", "Recientes, referencia base", green),
    ("cohorte_comun_reajustada", "Recientes, recalculado", red)]):
    vals = [100*sel[seg][key]["fraccion_fuera"] for seg in ["0DTE", "plazo_mensual"]]
    x = np.arange(2)+(j-1)*.24
    axes[2].bar(x, vals, width=.22, color=color, label=label)
    for a,b in zip(x, vals):
        axes[2].text(a,b+1,f"{b:.1f}", ha="center", fontsize=9)
axes[2].set_xticks(range(2), ["Vencen ese día", "Alrededor de un mes"])
axes[2].set_ylim(0, 60)
axes[2].set_ylabel("Fuera de banda (%)")
axes[2].set_title("3. La frescura no elimina los residuos\nEdad ≤10 s; separación call–put ≤2 s", loc="left", weight="bold", fontsize=12, pad=15)
axes[2].legend(frameon=False, bbox_to_anchor=(0,-.2), loc="upper left", fontsize=9)
fig.suptitle("QuantileFlow · primera prueba de calls y puts", x=.07, y=.975, ha="left", fontsize=21, weight="bold")
fig.text(.07,.921,f"{n_dates} sesiones · mismas parejas para medir persistencia · feed indicative", fontsize=13, color="#435269")
fig.text(.07,.035,"Bandas bid–ask: no son intervalos de confianza. Residuos respecto de una referencia estimada; no prueban arbitraje ni predicción.", fontsize=9.5,color="#435269")
fig.savefig(args.figura, dpi=170, facecolor=fig.get_facecolor())
plt.close(fig)
print("Figura generada.")
