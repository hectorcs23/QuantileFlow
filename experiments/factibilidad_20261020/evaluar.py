"""Diagnóstico gratuito sobre el snapshot histórico, sin cambiar sus reservas."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tomllib
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import numpy as np
import pandas as pd
import scipy
from experiments.factibilidad_20261020.metodo import diagnosticar


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origen", type=Path, required=True)
    ap.add_argument("--privado", type=Path, required=True)
    a = ap.parse_args()
    origen, privado = a.origen.resolve(), a.privado.resolve()
    if privado.is_relative_to(RAIZ) or privado == origen:
        raise ValueError("salida privada debe estar fuera de Git y del origen")
    privado.mkdir(parents=True, exist_ok=True)
    folder = Path(__file__).parent
    out = folder / "resultados"; out.mkdir(exist_ok=True)
    proto = tomllib.loads((folder / "protocolo.toml").read_text(encoding="utf-8"))
    origen_resumen = RAIZ / "experiments/forward_fijo_20261014/resultados/resumen.json"
    anterior = json.loads(origen_resumen.read_text(encoding="utf-8"))
    for name, h in anterior["privados_sha256"].items():
        if sha(origen / name) != h:
            raise ValueError("el snapshot privado cambió: " + name)
    rows = []
    for cut in anterior["cortes"]:
        tag = cut["fecha"] + "_" + cut["hora"].replace(":", "")
        e = pd.read_parquet(origen / (tag + "_evaluacion.parquet"))
        modelos = json.loads((origen / (tag + "_modelos.json")).read_text(encoding="utf-8"))
        detalles = []
        if not e.raiz.eq("SPXW").all() or not e.tipo.isin(["C", "P"]).all():
            raise ValueError("universo europeo SPXW inesperado")
        if (e.entrenamiento & e.holdout).any() or not (e.entrenamiento | e.holdout).all():
            raise ValueError("reservas inválidas")
        for ancho in proto["anchos"]:
            for grupo in proto["grupos"]:
                for z in modelos["modelos_fijos"][0]["rebanadas"]:
                    mask = (e.entrenamiento if grupo == "training" else e.holdout)
                    g = e[mask & (e.k.abs() <= ancho) & np.isclose(e.dias, z["T"] * 365, rtol=0, atol=1e-10)]
                    if g.empty:
                        raise ValueError("grupo vacío")
                    for libre, descuento_libre in ((False, False), (True, False), (True, True)):
                        for nivel in proto["niveles"]:
                            objetivos = ("maximo", "media") if nivel == "convexidad" else ("maximo",)
                            for objetivo in objetivos:
                                r = diagnosticar(g, z["F"], z["D"], forward_libre=libre,
                                                 descuento_libre=descuento_libre,
                                                 nivel=nivel, objetivo=objetivo)
                                meta = dict(fecha=cut["fecha"], hora=cut["hora"],
                                    dias=z["T"] * 365, ancho=ancho, grupo=grupo)
                                detalles.append(dict(**meta, **{k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in r.items()},
                                                     ids=g.id_contrato.tolist(), F_ancla=z["F"], D=z["D"]))
                                rows.append(dict(**meta, **{k: v for k, v in r.items()
                                    if k not in ("precios", "relajaciones_por_fila", "forward_ratio_diagnostico", "descuento_ratio_diagnostico")}))
        dump(privado / (tag + "_lp.json"), detalles)
        print(tag, "LPs", len(detalles), "máxima violación", max(r["violacion_primal"] for r in detalles), flush=True)
    df = pd.DataFrame(rows)
    agregados = []
    campos = ["ancho", "grupo", "forward_libre", "descuento_libre", "nivel", "objetivo"]
    for key, g in df.groupby(campos, sort=True):
        meta = dict(zip(campos, key))
        agregados.append(dict(**meta, rebanadas=len(g), filas=int(g.filas.sum()),
            factibles=int(g.factible_sin_relajar.sum()),
            mediana_relajacion=float(g.relajacion.median()),
            p95_relajacion=float(g.relajacion.quantile(.95)),
            max_relajacion=float(g.relajacion.max()),
            media_distancia_spreads_ponderada=float(np.average(g.media_distancia_spreads, weights=g.filas)),
            media_distancia_precio_ponderada=float(np.average(g.media_distancia_precio, weights=g.filas))))
    # Las restricciones añadidas no deben reducir el mínimo; liberar F no debe empeorarlo.
    maximos = df[df.objetivo.eq("maximo")]
    for _, g in maximos.groupby(["fecha", "hora", "dias", "ancho", "grupo", "forward_libre", "descuento_libre"]):
        v = g.set_index("nivel").loc[proto["niveles"]].relajacion.to_numpy()
        if np.min(np.diff(v)) < -1e-6:
            raise ValueError("las restricciones anidadas redujeron el mínimo")
    for _, g in df[~df.descuento_libre].groupby(["fecha", "hora", "dias", "ancho", "grupo", "nivel", "objetivo"]):
        v = g.set_index("forward_libre").relajacion
        if v[True] > v[False] + 1e-6:
            raise ValueError("liberar F empeoró el óptimo")
    for _, g in df[df.forward_libre].groupby(["fecha", "hora", "dias", "ancho", "grupo", "nivel", "objetivo"]):
        v = g.set_index("descuento_libre").relajacion
        if v[True] > v[False] + 1e-6:
            raise ValueError("liberar D empeoró el óptimo")
    fuentes = [Path(__file__), folder / "metodo.py", folder / "protocolo.toml"]
    dump(out / "resumen.json", dict(protocolo=proto, sesiones=len({r["fecha"] for r in rows}),
        cortes=len(anterior["cortes"]), total_LP=len(rows), agregado=agregados,
        max_violacion_primal=float(df.violacion_primal.max()),
        max_violacion_dual=float(df.violacion_dual.max()),
        max_brecha_primal_dual=float(df.brecha_primal_dual.max()),
        origen_resumen_sha256_lf=hashlib.sha256(origen_resumen.read_text(encoding="utf-8").encode()).hexdigest(),
        scipy=scipy.__version__,
        codigo_sha256_lf={p.relative_to(RAIZ).as_posix(): hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in fuentes},
        privados_sha256={p.name: sha(p) for p in sorted(privado.glob("*_lp.json"))}))
    dump(out / "por_rebanada.json", rows)
    print(df[df.nivel.eq("convexidad")].groupby(["ancho", "grupo", "forward_libre", "descuento_libre", "objetivo"])
          .agg(factibles=("factible_sin_relajar", "sum"), mediana=("relajacion", "median"),
               maximo=("relajacion", "max")).to_string(), flush=True)


if __name__ == "__main__":
    main()
