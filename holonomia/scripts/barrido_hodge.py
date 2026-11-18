"""Barrido de Δt para el complejo vivo: ¿cuánto grafo sobrevive y qué curvatura se ve?

    python scripts/barrido_hodge.py [--dia 2026-11-10]

A Δt = 1 s casi ningún par lento está fresco, así que el complejo vivo es un
puñado de aristas y la descomposición de Hodge del grafo entero no es
medible. Aflojar Δt trae más grafo, pero también más rancidez. Este barrido
pone los dos efectos en la misma tabla, que es lo único honesto que se puede
decir sobre el reparto rotacional/armónico en estos datos.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

from capturar import SUBGRAFO                             # noqa: E402
from holonomia import datos, grafo as G, limpieza, medidas  # noqa: E402

DELTAS = (1.0, 2.0, 5.0, 15.0, 60.0, 300.0, 900.0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dia", default="2026-11-10")
    ap.add_argument("--paso", type=int, default=30, help="segundos entre instantes")
    ap.add_argument("--salida", default="resultados")
    args = ap.parse_args()

    g = G.desde_simbolos(SUBGRAFO)
    df = datos.cargar_quotes(RAIZ / "datos_crudos" / f"quotes-{args.dia}")
    limpio, _ = limpieza.filtrar(df)
    malla = pd.date_range(limpio["ts_exchange"].min().ceil("s"),
                          limpio["ts_exchange"].max().floor("s"), freq=f"{args.paso}s")
    p = limpieza.panel(limpio, SUBGRAFO, malla=malla)
    print(f"{args.dia}: {len(malla):,} instantes cada {args.paso} s, grafo completo "
          f"V={g.n_monedas} E={g.n_aristas} caras={g.n_caras} b1={g.betti1()}\n")

    filas = []
    for dt in DELTAS:
        rep = medidas.reparto_en_el_tiempo(p, g, delta_t=dt)
        if rep.empty:
            continue
        con_curv = rep[rep["norma_curvatura_pb"] > 1e-6]
        filas.append({
            "delta_t_s": dt,
            "instantes": len(rep),
            "aristas_mediana": rep["aristas"].median(),
            "caras_mediana": rep["caras"].median(),
            "b1_mediana": rep["b1"].median(),
            "frac_instantes_b1_positivo": float((rep["b1"] > 0).mean()),
            "frac_instantes_con_caras": float((rep["caras"] > 0).mean()),
            "frac_instantes_grafo_entero": float((rep["aristas"] == g.n_aristas).mean()),
            "rotacional_pb_mediana": rep["norma_rotacional_pb"].median(),
            "armonica_pb_mediana": rep["norma_armonica_pb"].median(),
            "curvatura_pb_mediana": rep["norma_curvatura_pb"].median(),
            "curv_frac_rotacional_mediana": (con_curv["curv_frac_rotacional"].median()
                                             if len(con_curv) else float("nan")),
        })
        f = filas[-1]
        print(f"Δt={dt:>6.0f} s  aristas={f['aristas_mediana']:>5.1f}  "
              f"caras={f['caras_mediana']:>5.1f}  b1={f['b1_mediana']:>4.1f}  "
              f"rot={f['rotacional_pb_mediana']:>8.3f} pb  "
              f"arm={f['armonica_pb_mediana']:>8.3f} pb  "
              f"grafo entero en {f['frac_instantes_grafo_entero']:>6.1%}")

    tabla = pd.DataFrame(filas)
    ruta = RAIZ / args.salida / "barrido_hodge.csv"
    tabla.to_csv(ruta, index=False)
    print(f"\nescrito {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
