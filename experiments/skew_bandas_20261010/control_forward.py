"""Control posterior independiente: forward común libre, descuento fijo, solo training.

No se usa para elegir el modelo ni modificar rankings. Publica conteos, nunca F
ni cotizaciones individuales. Comprueba si la incompatibilidad es solo un ancla
equivocada o si ni siquiera existe un forward que quepa en todas las bandas.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
from quantileflow.piloto import cargar_config


def maximo_solapamiento(intervalos):
    a = np.asarray(intervalos,dtype=float)
    if a.size == 0:
        return 0
    if a.ndim != 2 or a.shape[1] != 2 or not np.isfinite(a).all() or (a[:,0] > a[:,1]).any():
        raise ValueError("intervalos inválidos")
    # El máximo de intervalos cerrados se alcanza en uno de sus extremos.
    return max(int(((a[:,0] <= x+1e-9)&(a[:,1] >= x-1e-9)).sum()) for x in a.ravel())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--privado",type=Path,required=True)
    p.add_argument("--resumen",type=Path,default=Path(__file__).parent/"resultados/resumen.json")
    p.add_argument("--salida",type=Path,default=Path(__file__).parent/"resultados/control_forward.json")
    a = p.parse_args()
    resumen = json.loads(a.resumen.read_text(encoding="utf-8"))
    config = RAIZ/"configs/piloto.toml"
    if sha(config) != resumen["config_sha256"]:
        raise ValueError("configuración cambió después del ajuste")
    tasa = cargar_config(config).tasa
    for nombre, huella in resumen["salidas_privadas_sha256"].items():
        ruta = (a.privado/nombre).resolve()
        if not ruta.is_relative_to(a.privado.resolve()) or sha(ruta) != huella:
            raise ValueError("salida privada alterada")
    cortes = []
    for c in resumen["cortes"]:
        etiqueta = c["fecha"]+"_"+c["hora"].replace(":", "")
        e = pd.read_parquet(a.privado/(etiqueta+"_evaluacion.parquet"))
        train = e[e.entrenamiento]
        pares, minimo = 0, 0
        for dias, g in train.groupby("dias"):
            D = math.exp(-tasa*float(dias)/365)
            intervalos = []
            for K, lado in g.groupby("strike"):
                cs, ps = lado[lado.tipo == "C"],lado[lado.tipo == "P"]
                if len(cs) != 1 or len(ps) != 1:
                    continue
                call, put = cs.iloc[0],ps.iloc[0]
                intervalos.append([float(K+(call.bid-put.ask)/D),float(K+(call.ask-put.bid)/D)])
            pares += len(intervalos)
            minimo += len(intervalos)-maximo_solapamiento(intervalos)
        if pares != c["paridad_training"]["pares"]:
            raise ValueError("conteo independiente de pares no coincide")
        cortes.append(dict(fecha=c["fecha"],hora=c["hora"],pares=pares,
            incompatibles_forward_actual=c["paridad_training"]["incompatibles"],
            minimo_incompatibles_cualquier_forward=minimo))
    salida = dict(naturaleza="control posterior descriptivo, no ajuste seleccionado ni predictor",
        descuento=f"fijo a tasa continua {tasa}; no se optimiza descuento",
        resumen_sha256=sha(a.resumen), codigo_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(),
        pares=sum(c["pares"] for c in cortes),
        incompatibles_actual=sum(c["incompatibles_forward_actual"] for c in cortes),
        minimo_incompatibles_forward_libre=sum(c["minimo_incompatibles_cualquier_forward"] for c in cortes),
        cortes=cortes)
    a.salida.write_text(json.dumps(salida,ensure_ascii=False,allow_nan=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in salida.items() if k != "cortes"},indent=2))


if __name__ == "__main__":
    main()
