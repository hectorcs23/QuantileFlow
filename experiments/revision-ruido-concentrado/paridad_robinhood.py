"""Paridad put-call con las cotizaciones de Robinhood frente a las de Alpaca. Solo imprime agregados.

Cada par call/put del mismo strike admite F en [K+(Cbid-Pask)/D, K+(Cask-Pbid)/D].
- En vivo (bid y ask de las dos fuentes en el mismo instante): ¿hay un F común a todos los pares?
  ¿cuántos pares quedan fuera del F que más pares admite?
- Al corte (marca de Robinhood y mid de la captura de Alpaca): F implícito por par, K+(C-P)/D, y su
  dispersión entre strikes. Con cotizaciones coherentes, todos los pares dan casi el mismo F.
- Con --rama (checkout de codex/ruido-concentrado-20261022): reparación mínima de cada fuente en la
  foto en vivo, rho (uniforme) y b* (media L1 con cap rho+0.5), con F libre en ±0.25 %.

Uso::

    python experiments/revision-ruido-concentrado/paridad_robinhood.py --privado RAMA_ROBINHOOD --datos DATOS
"""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ/"experiments"/"comparacion-robinhood"))
import comparar  # noqa: E402


def descuento(simbolo, fecha, tasa):
    return math.exp(-tasa*(pd.Timestamp("20"+simbolo[4:10])-pd.Timestamp(fecha)).days/365)


def intervalos(cotizaciones, D):
    """Intervalo de F que admite cada par con bid y ask válidos en el call y el put."""
    lados = {}
    for s, q in cotizaciones.items():
        if q.get("bid") is not None and q.get("ask") is not None and 0 <= q["bid"] <= q["ask"]:
            lados.setdefault(int(s[-8:])/1000, {})[s[-9]] = (q["bid"], q["ask"])
    return [(K+(v["C"][0]-v["P"][1])/D, K+(v["C"][1]-v["P"][0])/D) for K, v in lados.items() if len(v) == 2]


def maximo_comun(iv):
    """Mayor número de intervalos que comparten un punto."""
    n = mejor = 0
    for _, fin in sorted([(a, 0) for a, _ in iv]+[(b, 1) for _, b in iv]):
        n += 1 if fin == 0 else -1
        mejor = max(mejor, n)
    return mejor


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--privado", type=Path, required=True, help="clon de la rama robinhood")
    ap.add_argument("--datos", type=Path, required=True, help="capturas de Alpaca")
    ap.add_argument("--tasa", type=float, default=0.04, help="la de configs/piloto.toml")
    ap.add_argument("--rama", type=Path, help="checkout de codex/ruido-concentrado-20261022")
    a = ap.parse_args()
    if a.rama:
        sys.path.insert(0, str(a.rama.resolve()))
        from experiments.ruido_concentrado_20261022.metodo import MercadoL1
    print("En vivo: pares, ¿F común?, pares fuera del mejor F")
    for ruta in sorted(a.privado.glob("*/vivo.json")):
        v = json.loads(ruta.read_text(encoding="utf-8"))
        rh, alp = v["robinhood"]["cotizaciones"], v["alpaca"]["cotizaciones"]
        D = descuento(next(iter(rh)), ruta.parent.name, a.tasa)
        for fuente, cot in (("Robinhood", rh), ("Alpaca", alp)):
            iv = intervalos(cot, D)
            comun = max(x for x, _ in iv) <= min(y for _, y in iv)
            print(f"  {ruta.parent.name} {fuente:9} {len(iv)} {'sí' if comun else 'no'} {len(iv)-maximo_comun(iv)}")
        if a.rama:
            iv = intervalos(rh, D)
            F = (max(x for x, _ in iv)+min(y for _, y in iv))/2  # centro del F común de Robinhood
            for fuente, cot in (("Robinhood", rh), ("Alpaca", alp)):
                t = pd.DataFrame([dict(strike=int(s[-8:])/1000, tipo=s[-9], bid=q["bid"], ask=q["ask"])
                                  for s, q in sorted(cot.items())
                                  if q.get("bid") is not None and q["ask"] > q["bid"] >= 0])
                m = MercadoL1(t, F, D)
                rho = m.reparar(fb=(.9975, 1.0025))
                print(f"    reparación {fuente}: rho {rho:.2f}, b* {m.reparar_l1(rho+.5, fb=(.9975, 1.0025)):.3f}")
    print("Al corte: desviación y rango del F implícito entre strikes (puntos)")
    desv = {"Robinhood": [], "Alpaca": []}
    for ruta in sorted(a.privado.glob("*/barras_*.json")):
        fecha, b = ruta.parent.name, json.loads(ruta.read_text(encoding="utf-8"))
        corte = pd.Timestamp(b["corte_utc"])
        previa = (corte-pd.Timedelta(seconds=15)).strftime("%H:%M:%S")
        hora = corte.tz_convert("America/New_York").strftime("%H:%M")
        alp = comparar.cotizaciones_alpaca(a.datos, fecha, hora, b["barras"])
        D = descuento(next(iter(b["barras"])), fecha, a.tasa)
        precios = {}
        for s, barras in b["barras"].items():
            if previa in barras and s in alp:
                precios.setdefault(int(s[-8:])/1000, {})[s[-9]] = (barras[previa][3], (alp[s]["bid"]+alp[s]["ask"])/2)
        pares = {K: v for K, v in precios.items() if len(v) == 2}
        F = {f: [K+(v["C"][j]-v["P"][j])/D for K, v in pares.items()] for j, f in enumerate(("Robinhood", "Alpaca"))}
        for f in F:
            desv[f].append(float(np.std(F[f])))
        print(f"  {fecha} {hora} {len(pares)} pares"
              + "".join(f"  {f} {np.std(F[f]):.2f} ({np.ptp(F[f]):.2f})" for f in F))
    print("  mediana de la desviación: " + ", ".join(f"{f} {np.median(d):.2f}" for f, d in desv.items()))


if __name__ == "__main__":
    main()
