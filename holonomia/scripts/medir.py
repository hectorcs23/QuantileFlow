"""Mediciones de §2.5 sobre los días capturados. Escribe tablas en resultados/.

    python scripts/medir.py [--delta-t 1.0] [--dias datos_crudos]

Procesa un día a la vez para no cargar la semana entera en memoria.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

from capturar import SUBGRAFO                         # noqa: E402
from holonomia import datos, grafo as G, limpieza, medidas  # noqa: E402
from holonomia.holonomia import Comisiones            # noqa: E402

PB = 1e4
CICLOS_INSIGNIA = (["BTC", "ETH", "USD"], ["BTC", "LTC", "USD"],
                   ["BTC", "ETH", "USDT"], ["USD", "USDC", "USDT"])


def triangulos_dirigidos(g):
    """Un sentido por triángulo: el que empieza en la moneda menor."""
    return [list(c) for c in g.caras]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--delta-t", type=float, default=1.0)
    ap.add_argument("--dias", default="datos_crudos")
    ap.add_argument("--salida", default="resultados")
    ap.add_argument("--paso-hodge", type=int, default=10, help="segundos entre instantes de Hodge")
    args = ap.parse_args()

    salida = RAIZ / args.salida
    salida.mkdir(exist_ok=True)
    com = Comisiones.alpaca(1)
    g = G.desde_simbolos(SUBGRAFO)
    triangulos = triangulos_dirigidos(g)

    print(f"subgrafo: V={g.n_monedas} E={g.n_aristas} triángulos={g.n_caras} "
          f"rango de ciclos={g.rango_ciclos()} b1={g.betti1()}")
    print(f"Δt = {args.delta_t} s, comisión taker = {com.taker:.2%}\n")

    dirs = sorted((RAIZ / args.dias).glob("quotes-*"))
    resumenes, sensibilidades, repartos, descartes, acfs, actividad = [], [], [], [], [], []

    for d in dirs:
        dia = d.name.replace("quotes-", "")
        t0 = time.time()
        df = datos.cargar_quotes(d)
        limpio, reg = limpieza.filtrar(df)
        fila = {"dia": dia, "filas_entrada": reg.filas_entrada, "filas_salida": reg.filas_salida}
        fila.update(reg.motivos)
        descartes.append(fila)
        print(f"[{dia}] {reg.filas_entrada:,} cotizaciones -> {reg.filas_salida:,} "
              f"({', '.join(f'{k}: {v}' for k, v in reg.motivos.items()) or 'sin descartes'})")

        # -- por triángulo ------------------------------------------------
        for tri in triangulos:
            patas = {s for paso in limpieza.pasos_de_ciclo(tri)
                     for s in [limpieza._resolver(paso, set(SUBGRAFO))[0]]}
            p = limpieza.panel(limpio, sorted(patas))
            r = medidas.resumen_de_ciclo(p, tri, com, delta_t=args.delta_t)
            r["dia"] = dia
            resumenes.append(r)

            if tri in CICLOS_INSIGNIA:
                for f in medidas.sensibilidad_delta_t(p, tri, com).to_dict("records"):
                    sensibilidades.append({"dia": dia, "ciclo": " → ".join(tri), **f})
                serie = medidas.serie_de_ciclo(p, tri, com, delta_t=args.delta_t)
                if len(serie) > 1000:
                    malla = medidas.en_malla_regular(serie, "h_mid", "1s")
                    acf = medidas.autocorrelacion(malla, max_lag=300)
                    acfs.append({"dia": dia, "ciclo": " → ".join(tri),
                                 "vida_media_s": medidas.vida_media(acf),
                                 "cobertura": float(malla.notna().mean()),
                                 **{f"acf_{k}": v for k, v in acf.items()}})

        # -- reparto de Hodge en malla regular -----------------------------
        malla = pd.date_range(limpio["ts_exchange"].min().ceil("s"),
                              limpio["ts_exchange"].max().floor("s"),
                              freq=f"{args.paso_hodge}s")
        p_todo = limpieza.panel(limpio, SUBGRAFO, malla=malla)
        rep = medidas.reparto_en_el_tiempo(p_todo, g, delta_t=args.delta_t)
        if not rep.empty:
            rep["dia"] = dia
            repartos.append(rep.reset_index())

        # -- actividad para §2.5 (régimen) ---------------------------------
        vol = medidas.volatilidad_realizada(p_todo, "BTC/USD", paso="5min")
        act = pd.DataFrame({"vol_btc_pb": vol,
                            "quotes": medidas.intensidad(p_todo, SUBGRAFO, paso="5min")})
        act["dia"] = dia
        actividad.append(act.reset_index())

        print(f"        {time.time() - t0:.0f} s")
        # Guardado incremental: una semana son minutos de cómputo y no se
        # pierden por un fallo en el último día.
        pd.DataFrame(resumenes).to_csv(salida / "resumen_por_triangulo.csv", index=False)
        if repartos:
            pd.concat(repartos, ignore_index=True).to_csv(salida / "reparto_hodge.csv", index=False)

    def guardar(nombre, obj):
        ruta = salida / nombre
        obj.to_csv(ruta, index=False)
        print(f"  escrito {ruta}  ({len(obj)} filas)")

    print("\n=== tablas ===")
    guardar("descartes.csv", pd.DataFrame(descartes).fillna(0))
    guardar("resumen_por_triangulo.csv", pd.DataFrame(resumenes))
    guardar("sensibilidad_delta_t.csv", pd.DataFrame(sensibilidades))
    guardar("persistencia.csv", pd.DataFrame(acfs))
    if repartos:
        guardar("reparto_hodge.csv", pd.concat(repartos, ignore_index=True))
    guardar("actividad.csv", pd.concat(actividad, ignore_index=True))

    meta = {"delta_t_s": args.delta_t, "comision_taker": com.taker,
            "pares": list(SUBGRAFO), "dias": [d.name for d in dirs],
            "grafo": {"monedas": g.n_monedas, "aristas": g.n_aristas,
                      "triangulos": g.n_caras, "rango_ciclos": g.rango_ciclos(),
                      "b1": g.betti1()},
            "paso_hodge_s": args.paso_hodge}
    (salida / "parametros.json").write_text(json.dumps(meta, indent=2))
    print(f"  escrito {salida / 'parametros.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
