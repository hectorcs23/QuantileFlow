"""Comprueba archivos y precios guardados sin volver a usar el constructor del LP."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origen", type=Path, required=True)
    ap.add_argument("--privado", type=Path, required=True)
    a = ap.parse_args()
    folder = Path(__file__).parent / "resultados"
    resumen = json.loads((folder / "resumen.json").read_text(encoding="utf-8"))
    for name, h in resumen["codigo_sha256_lf"].items():
        assert hashlib.sha256((RAIZ / name).read_text(encoding="utf-8").encode()).hexdigest() == h, name
    antiguo = RAIZ / "experiments/forward_fijo_20261014/resultados/resumen.json"
    assert hashlib.sha256(antiguo.read_text(encoding="utf-8").encode()).hexdigest() == resumen["origen_resumen_sha256_lf"]
    for name, h in json.loads(antiguo.read_text(encoding="utf-8"))["privados_sha256"].items():
        assert sha(a.origen / name) == h, name
    publico = json.loads((folder / "por_rebanada.json").read_text(encoding="utf-8"))
    campos = ("fecha", "hora", "dias", "ancho", "grupo", "forward_libre", "descuento_libre", "nivel", "objetivo")
    mapa = {tuple(r[k] for k in campos): r for r in publico}
    assert len(mapa) == len(publico)
    max_error = 0.; casos = 0
    for name, h in resumen["privados_sha256"].items():
        path = a.privado / name
        assert sha(path) == h, name
        tag = name.removesuffix("_lp.json")
        e = pd.read_parquet(a.origen / (tag + "_evaluacion.parquet")).set_index("id_contrato")
        assert e.index.is_unique
        for r in json.loads(path.read_text(encoding="utf-8")):
            g = e.loc[r["ids"]]
            precios = np.asarray(r["precios"])
            assert len(precios) == r["filas"] == len(g)
            assert (g.entrenamiento if r["grupo"] == "training" else g.holdout).all()
            assert (g.k.abs() <= r["ancho"]).all()
            D = r["D"] * r["descuento_ratio_diagnostico"]
            assert r["forward_ratio_diagnostico"] is not None  # esta muestra no tiene D=0
            F = r["F_ancla"] * r["forward_ratio_diagnostico"]
            escala = r["D"] * r["F_ancla"]
            calls = precios + np.where(g.tipo.eq("P"), D * (F - g.strike), 0.)
            t = pd.DataFrame(dict(K=g.strike.to_numpy(), C=calls))
            cc = t.groupby("K").C.mean()
            paridad = (t.C - t.K.map(cc)).abs().max() / escala
            minimo = np.maximum(D * (F - cc.index.to_numpy()), 0.)
            error = max(0., paridad, float(np.max((minimo - cc.to_numpy()) / escala)),
                        float(np.max((cc.to_numpy() - D * F) / escala)))
            ks = np.r_[0., cc.index.to_numpy()]
            vals = np.r_[D * F, cc.to_numpy()]
            slopes = np.diff(vals) / np.diff(ks)
            if r["nivel"] in ("verticales", "convexidad"):
                error = max(error, float(slopes.max()), float((-D - slopes).max()))
            if r["nivel"] == "convexidad":
                error = max(error, float(-np.diff(slopes).min()))
            dist = np.maximum(np.maximum(g.bid.to_numpy() - precios, precios - g.ask.to_numpy()), 0.)
            dist /= (g.ask - g.bid).to_numpy()
            objetivo = dist.max() if r["objetivo"] == "maximo" else dist.mean()
            error = max(error, abs(objetivo - r["relajacion"]))
            assert error < 1e-6, (name, r["nivel"], error)
            pub = mapa.pop(tuple(r[k] for k in campos))
            for key in pub:
                assert pub[key] == r[key], key
            max_error = max(max_error, error); casos += 1
    assert not mapa and casos == resumen["total_LP"]
    salida = dict(LP_verificados=casos, max_error_reconstruccion=max_error,
                  snapshot_y_fuentes_correctos=True, fuente_verificador_sha256_lf=
                  hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest())
    (folder / "verificacion.json").write_text(json.dumps(salida, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(salida, indent=2))


if __name__ == "__main__":
    main()
