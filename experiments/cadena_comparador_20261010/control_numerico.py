"""Contrasta el baseline plano con Black–Scholes analítico, solo agregados públicos."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import numpy as np
import pandas as pd
from quantileflow.opciones import precio_bs
from quantileflow.piloto import cargar_config


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--privados", type=Path, required=True)
    p.add_argument("--tablas", type=Path, required=True)
    p.add_argument("--resumen", type=Path, default=Path(__file__).parent/"resultados/resumen.json")
    args = p.parse_args()
    resumen = json.loads(args.resumen.read_text(encoding="utf-8"))
    cfg = cargar_config(RAIZ/"configs/piloto.toml")
    refs = pd.read_parquet(args.tablas/"subyacente.parquet")
    resultados = []
    for c in resumen["cortes"]:
        fecha, hora = c["fecha"], c["hora"]
        e = pd.read_parquet(args.privados/f"{fecha}_{hora.replace(':','')}_evaluacion.parquet")
        e = e[e.holdout]
        ref = refs[(refs.captura == f"{fecha}T{hora.replace(':','')}") & (refs.subyacente == "SPX")].iloc[0]
        bs = precio_bs(ref.precio, e.strike.to_numpy(), e.dias.to_numpy()/365, cfg.tasa,
                       cfg.rendimiento_dividendo, e.sigma_plana.to_numpy(), e.tipo.eq("C").to_numpy())
        ancho = ((e.ask-e.bid)/2).to_numpy()
        resultados.append(dict(fecha=fecha, hora=hora, holdout=len(e),
            dentro_banda_bs=int(((bs >= e.bid)&(bs <= e.ask)).sum()),
            max_error_pde_bs=float(np.max(abs(e.precio_plano.to_numpy()-bs))),
            max_error_fino_bs=float(np.max(abs(e.precio_fino.to_numpy()-bs))),
            mediana_error_pde_bs_en_semispreads=float(np.median(abs(e.precio_plano.to_numpy()-bs)/ancho)),
            mediana_error_modelo_bs_en_semispreads=float(np.median(abs(bs-(e.bid+e.ask).to_numpy()/2)/ancho))))
    d = dict(naturaleza="control analítico del mismo baseline de IV plana, no ajuste nuevo",
        dentro_banda_bs=sum(c["dentro_banda_bs"] for c in resultados), holdout=sum(c["holdout"] for c in resultados),
        cortes=resultados, sha256_resumen=hashlib.sha256(args.resumen.read_bytes()).hexdigest(),
        fuente_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest())
    args.resumen.with_name("control_numerico.json").write_text(json.dumps(d, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:d[k] for k in ("dentro_banda_bs", "holdout")}))


if __name__ == "__main__":
    main()
