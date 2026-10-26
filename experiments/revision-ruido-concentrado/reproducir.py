"""Corre la evaluación de la rama revisada con entradas regeneradas y la compara con lo publicado.

Usa evaluar_rebanada de experiments/ruido_concentrado_20261022/evaluar.py tal cual. A diferencia de
su main(), no exige las huellas de los Parquet de entrada, que cambian entre máquinas aunque el
contenido usado sea el mismo. Escribe solo en una carpeta privada y muestra las diferencias máximas
con resultados/por_rebanada.json y resultados/reparaciones.json de la rama.

Uso::

    python experiments/revision-ruido-concentrado/reproducir.py --rama RAMA --cohorte nuevas \
        --entradas PRIVADO/entradas --cortes PRIVADO/entradas.json --salida PRIVADO/reproduccion
"""
import argparse
import json
from pathlib import Path
import sys
import time
import tomllib

import numpy as np
import pandas as pd


def clave(r):
    return (r["cohorte"], r["fecha"], r["hora"], round(r["dias"], 9))


def comparar(publicado, rep, filas):
    """Diferencias máximas por rebanada frente a los JSON publicados de la misma cohorte."""
    pub_rep = {clave(r): r for r in json.loads((publicado/"reparaciones.json").read_text(encoding="utf-8"))}
    pub_filas = {(*clave(r), r["caso"]): r
                 for r in json.loads((publicado/"por_rebanada.json").read_text(encoding="utf-8"))}
    dif, distintos = {}, 0
    for r in rep:
        p = pub_rep[clave(r)]
        distintos += p["filas"] != r["filas"] or any(
            p["paridad"][c] != r["paridad"][c] for c in ("pares", "incompatibles", "filas_modificadas_min"))
        for c in ("rho", "media_min", "fraccion_modificada", "participacion_top10"):
            dif[c] = max(dif.get(c, 0.), abs(p[c]-r[c]))
    for r in filas:
        p = pub_filas[(*clave(r), r["caso"])]
        distintos += (p["holdout_n"], p["holdout_solapan"]) != (r["holdout_n"], r["holdout_solapan"])
        dif["ancho_reserva"] = max(dif.get("ancho_reserva", 0.),
                                   abs(p["holdout_ancho_spreads_medio"]-r["holdout_ancho_spreads_medio"]))
        for a, b in zip(p["cdf"], r["cdf"]):
            for c in ("inferior", "superior", "alcanzable_inferior", "alcanzable_superior"):
                dif["cdf"] = max(dif.get("cdf", 0.), abs(a[c]-b[c]))
    return dict(rebanadas=len(rep), casos=len(filas), conteos_distintos=distintos, diferencias_maximas=dif)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rama", type=Path, required=True, help="checkout de codex/ruido-concentrado-20261022")
    ap.add_argument("--cohorte", required=True, choices=("conocidas", "nuevas"))
    for n in ("entradas", "cortes", "salida"):
        ap.add_argument("--"+n, type=Path, required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(a.rama.resolve()))
    from experiments.ruido_concentrado_20261022.evaluar import evaluar_rebanada
    carpeta = a.rama/"experiments"/"ruido_concentrado_20261022"
    proto = tomllib.loads((carpeta/"protocolo.toml").read_text(encoding="utf-8"))
    rep, filas, lp, t0 = [], [], 0, time.time()
    for corte in json.loads(a.cortes.read_text(encoding="utf-8"))["cortes"]:
        tag = corte["fecha"]+"_"+corte["hora"].replace(":", "")
        e = pd.read_parquet(a.entradas/(tag+"_evaluacion.parquet"))
        modelos = json.loads((a.entradas/(tag+"_modelos.json")).read_text(encoding="utf-8"))
        for z in modelos["modelos_fijos"][0]["rebanadas"]:
            mask = np.isclose(e.dias, z["T"]*365, rtol=0, atol=1e-10) & (e.k.abs() <= .1)
            g, h = e[mask & e.entrenamiento], e[mask & e.holdout & e.tipo.eq("C")]
            meta = dict(cohorte=a.cohorte, fecha=corte["fecha"], hora=corte["hora"], dias=z["T"]*365,
                        vencimiento=str(g.vencimiento.iloc[0]))
            r, f, evidencia = evaluar_rebanada(g, h, z, meta, proto)
            rep.append(r); filas.extend(f); lp += sum(len(m["testigos"]) for m in evidencia)
        print(a.cohorte, tag, "LP", lp, f"{time.time()-t0:.0f} s", flush=True)
    a.salida.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in (("reparaciones", rep), ("por_rebanada", filas)):
        (a.salida/f"{a.cohorte}_{nombre}.json").write_text(json.dumps(contenido), encoding="utf-8")
    print(json.dumps(dict(lp=lp, **comparar(carpeta/"resultados", rep, filas)), indent=1))


if __name__ == "__main__":
    main()
