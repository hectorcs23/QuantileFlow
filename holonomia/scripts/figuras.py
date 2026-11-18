"""Figuras de la Fase 1 a partir de las tablas de resultados/.

    python scripts/figuras.py [--dia 2026-11-10]

Estilo por defecto de matplotlib, una figura por gráfica, etiquetas en inglés.
El ciclo insignia (BTC → ETH → USD) se recalcula del crudo para las figuras
que necesitan la serie entera y no sólo el resumen.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

from holonomia import datos, limpieza, medidas            # noqa: E402
from holonomia.holonomia import Comisiones                # noqa: E402

PB = 1e4
INSIGNIA = ["BTC", "ETH", "USD"]
PATAS = ["ETH/BTC", "BTC/USD", "ETH/USD"]
RES = RAIZ / "resultados"


def serie_insignia(dia: str, delta_t: float = 1.0) -> pd.DataFrame:
    df = datos.cargar_quotes(RAIZ / "datos_crudos" / f"quotes-{dia}")
    limpio, _ = limpieza.filtrar(df)
    p = limpieza.panel(limpio, PATAS)
    return limpieza.serie_de_ciclo(p, INSIGNIA, Comisiones.alpaca(1), delta_t=delta_t)


# -- 1. distribución de H_mid frente al medio spread ---------------------
def figura_distribucion(serie: pd.DataFrame, dia: str) -> None:
    h = serie["h_mid"].to_numpy() * PB
    s = float(serie["medio_spread"].median() * PB)

    plt.figure()
    plt.hist(h, bins=200, label='Mid-price holonomy')
    plt.axvline(s, label='Median half-spread of the cycle')
    plt.axvline(-s)
    plt.xlabel('Holonomy H_mid (basis points)')
    plt.ylabel('Number of synchronised instants')
    plt.title(f'Holonomy of BTC -> ETH -> USD, {dia}')
    plt.legend()
    plt.savefig(RES / "fig1_distribucion_h_mid.png")
    plt.show()


# -- 2. curvatura contra costo, por triángulo ----------------------------
def figura_curvatura_contra_costo(resumen: pd.DataFrame) -> None:
    r = resumen[resumen["instantes"] > 1000].groupby("ciclo").median(numeric_only=True)
    x = r["mediana_medio_spread_pb"].to_numpy()
    y = r["mediana_abs_h_mid_pb"].to_numpy()
    u = r["mediana_umbral_pb"].to_numpy()
    recta = np.linspace(min(x.min(), y.min()) * 0.5, max(x.max(), u.max()) * 1.5, 50)

    plt.figure()
    plt.loglog(x, y, 'o', label='Triangles: median |H_mid| vs half-spread')
    plt.loglog(recta, recta, label='Break-even without fees')
    plt.loglog(u, y, 'gs', label='Same triangles vs full threshold (with fees)')
    plt.xlabel('Cost of crossing the cycle (basis points)')
    plt.ylabel('Median |H_mid| (basis points)')
    plt.title('Curvature against execution cost, 34 triangles')
    plt.legend()
    plt.savefig(RES / "fig2_curvatura_contra_costo.png")
    plt.show()


# -- 3. sensibilidad a Δt -------------------------------------------------
def figura_sensibilidad(sens: pd.DataFrame) -> None:
    plt.figure()
    for ciclo, g in sens.groupby("ciclo"):
        m = g.groupby("delta_t_s")["mediana_abs_h_mid_pb"].median()
        plt.semilogx(m.index, m.to_numpy(), 'o-', label=ciclo)
    plt.xlabel('Synchronisation window dt (seconds)')
    plt.ylabel('Median |H_mid| (basis points)')
    plt.title('Holonomy against the synchronisation window')
    plt.legend()
    plt.savefig(RES / "fig3_sensibilidad_delta_t.png")
    plt.show()


# -- 4. persistencia ------------------------------------------------------
def figura_persistencia(pers: pd.DataFrame) -> None:
    cols = sorted((c for c in pers.columns if c.startswith("acf_")),
                  key=lambda c: int(c.split("_")[1]))
    lags = [int(c.split("_")[1]) for c in cols]

    plt.figure()
    for ciclo, g in pers.groupby("ciclo"):
        curva = g[cols].median(numeric_only=True).to_numpy()
        plt.plot(lags, curva, label=ciclo)
        vm = float(g["vida_media_s"].median())
        if np.isfinite(vm):
            plt.plot(vm, 0.5, 'ro')
    plt.plot([], [], 'ro', label='Half-life (ACF = 0.5)')
    plt.xlabel('Lag (seconds)')
    plt.ylabel('Autocorrelation of H_mid')
    plt.title('Persistence of the mid-price holonomy')
    plt.legend()
    plt.savefig(RES / "fig4_persistencia.png")
    plt.show()


# -- 5. reparto de Hodge --------------------------------------------------
def figura_reparto(rep: pd.DataFrame) -> None:
    rep = rep.copy()
    rep["t"] = pd.to_datetime(rep["t"], utc=True, format="ISO8601")
    # El reparto se reporta en puntos base, no como fracción de ||A||^2: los
    # log-precios son de orden 10 y la curvatura de orden 1e-4, así que la
    # fracción del gradiente sale 1 siempre y no dice nada.
    por_hora = rep.set_index("t").resample("1h").median(numeric_only=True).dropna(how="all")
    horas = range(len(por_hora))

    plt.figure()
    plt.semilogy(horas, por_hora["norma_rotacional_pb"].clip(lower=1e-6),
                 label='Curl norm (local inconsistency)')
    plt.semilogy(horas, por_hora["norma_armonica_pb"].clip(lower=1e-6),
                 label='Harmonic norm (global inconsistency)')
    plt.xlabel('Hours since the start of the sample')
    plt.ylabel('Norm of the component (basis points)')
    plt.title('Hodge split of the live subgraph, hourly medians')
    plt.legend()
    plt.savefig(RES / "fig5_reparto_hodge.png")
    plt.show()

    plt.figure()
    plt.plot(horas, por_hora["aristas"], label='Live edges (of 26)')
    plt.plot(horas, por_hora["caras"], label='Operable triangles (2-cells)')
    plt.plot(horas, por_hora["b1"], 'o-', label='b1 of the live complex')
    plt.xlabel('Hours since the start of the sample')
    plt.ylabel('Count')
    plt.title('Live complex: how much topology survives synchronisation')
    plt.legend()
    plt.savefig(RES / "fig6_complejo_vivo.png")
    plt.show()


def figura_reparto_por_delta_t(barrido: pd.DataFrame) -> None:
    """Cuánto del grafo vive, y qué curvatura se ve, según se afloje Δt."""
    plt.figure()
    plt.semilogx(barrido["delta_t_s"], barrido["aristas_mediana"], 'o-',
                 label='Live edges (of 26)')
    plt.semilogx(barrido["delta_t_s"], barrido["caras_mediana"], 'o-',
                 label='Operable triangles')
    plt.semilogx(barrido["delta_t_s"], barrido["b1_mediana"], 'o-',
                 label='b1 of the live complex')
    plt.xlabel('Synchronisation window dt (seconds)')
    plt.ylabel('Median count over the day')
    plt.title('How much of the complex is alive at each window')
    plt.legend()
    plt.savefig(RES / "fig8_complejo_vs_delta_t.png")
    plt.show()

    plt.figure()
    plt.loglog(barrido["delta_t_s"], barrido["rotacional_pb_mediana"], 'o-',
               label='Curl norm')
    plt.loglog(barrido["delta_t_s"], barrido["armonica_pb_mediana"], 'o-',
               label='Harmonic norm')
    plt.xlabel('Synchronisation window dt (seconds)')
    plt.ylabel('Median norm (basis points)')
    plt.title('Local against global inconsistency, by window')
    plt.legend()
    plt.savefig(RES / "fig9_curvatura_vs_delta_t.png")
    plt.show()


# -- 6. régimen -----------------------------------------------------------
def figura_regimen(serie: pd.DataFrame, actividad: pd.DataFrame, dia: str) -> None:
    act = actividad[actividad["dia"] == dia].copy()
    col_t = "t" if "t" in act.columns else act.columns[0]
    act[col_t] = pd.to_datetime(act[col_t], utc=True, format="ISO8601")
    act = act.set_index(col_t)

    curva = (serie["h_mid"].abs() * PB).resample("5min").median()
    junto = pd.DataFrame({"h": curva, "vol": act["vol_btc_pb"]}).dropna()
    junto = junto[junto["vol"] > 0]

    cortes = pd.qcut(junto["vol"], 8, duplicates="drop")
    binned = junto.groupby(cortes, observed=True).median()

    plt.figure()
    plt.loglog(junto["vol"], junto["h"], 'o', label='5-minute buckets')
    plt.loglog(binned["vol"], binned["h"], 'o-', label='Median by volatility octile')
    plt.xlabel('Realised volatility of BTC/USD over 5 minutes (basis points)')
    plt.ylabel('Median |H_mid| in the bucket (basis points)')
    plt.title(f'Curvature against market activity, {dia}')
    plt.legend()
    plt.savefig(RES / "fig7_regimen.png")
    plt.show()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dia", default="2026-11-10")
    args = ap.parse_args()

    resumen = pd.read_csv(RES / "resumen_por_triangulo.csv")
    sens = pd.read_csv(RES / "sensibilidad_delta_t.csv")
    pers = pd.read_csv(RES / "persistencia.csv")
    rep = pd.read_csv(RES / "reparto_hodge.csv")
    act = pd.read_csv(RES / "actividad.csv")

    print(f"serie insignia de {args.dia} ...")
    serie = serie_insignia(args.dia)
    print(f"  {len(serie):,} instantes sincronizados")

    figura_distribucion(serie, args.dia)
    figura_curvatura_contra_costo(resumen)
    figura_sensibilidad(sens)
    figura_persistencia(pers)
    figura_reparto(rep)
    figura_regimen(serie, act, args.dia)
    print("figuras escritas en", RES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
