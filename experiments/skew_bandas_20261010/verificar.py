"""Recalcula precios agregados independientemente y audita huellas/publicación."""
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
from scipy.special import ndtr
from quantileflow.piloto import cargar_config


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--privado",type=Path,required=True)
    p.add_argument("--tablas",type=Path,required=True)
    a=p.parse_args()
    carpeta=Path(__file__).parent/"resultados"
    r=json.loads((carpeta/"resumen.json").read_text(encoding="utf-8"))
    for nombre,esperado in r["fuentes_sha256_lf"].items():
        if hashlib.sha256((RAIZ/nombre).read_text(encoding="utf-8").encode()).hexdigest() != esperado:
            raise ValueError("código difiere de la corrida")
    for nombre,esperado in r["salidas_privadas_sha256"].items():
        archivo=(a.privado/nombre).resolve()
        if not archivo.is_relative_to(a.privado.resolve()) or sha(archivo) != esperado:
            raise ValueError("datos individuales de la corrida alterados")
    if sha(a.tablas/"subyacente.parquet") != r["integridad"]["tablas_sha256"]["subyacente"]:
        raise ValueError("referencias distintas")
    cfg=cargar_config(RAIZ/"configs/piloto.toml")
    if sha(RAIZ/"configs/piloto.toml") != r["config_sha256"]:
        raise ValueError("configuración distinta")
    refs=pd.read_parquet(a.tablas/"subyacente.parquet")
    max_error=0.
    filas=0
    ids=set()
    for c in r["cortes"]:
        nombre=c["fecha"]+"_"+c["hora"].replace(":","")
        e=pd.read_parquet(a.privado/(nombre+"_evaluacion.parquet"))
        ids.update(e.id_contrato)
        if not np.array_equal(~e.holdout,e.entrenamiento):
            raise ValueError("split inconsistente")
        por_strike=e.groupby(["vencimiento","strike"])["holdout"].nunique()
        if not por_strike.eq(1).all():
            raise ValueError("call y put del mismo strike separados en el split")
        params=json.loads((a.privado/(nombre+"_ajustes.json")).read_text(encoding="utf-8"))["parametros"]["0.5"]
        etiqueta=c["fecha"]+"T"+c["hora"].replace(":","")
        spot=float(refs[(refs.captura == etiqueta)&(refs.subyacente == "SPX")].precio.iloc[0])
        T=e.dias.to_numpy()/365
        F=spot*np.exp((cfg.tasa-cfg.rendimiento_dividendo)*T)
        D=np.exp(-cfg.tasa*T)
        K=e.strike.to_numpy()
        k=np.log(K/F)
        theta=np.interp(T,params["tiempos"],params["thetas"])
        phi=params["eta"]/(theta**params["gamma"]*(1+theta)**(1-params["gamma"]))
        rho=params["rho"]
        wssvi=theta/2*(1+rho*phi*k+np.sqrt((phi*k+rho)**2+1-rho**2))
        wflat=np.array([params["planas"][str(t)]**2*t for t in T])
        for modelo,w in (("plano",wflat),("ssvi",wssvi)):
            sqrt=np.sqrt(w)
            d1=(-k+w/2)/sqrt
            d2=d1-sqrt
            call=D*(F*ndtr(d1)-K*ndtr(d2))
            put=D*(K*ndtr(-d2)-F*ndtr(-d1))
            price=np.where(e.tipo.eq("C"),call,put)
            max_error=max(max_error,float(np.abs(price-e["modelo_"+modelo]).max()))
            for grupo,mask in (("train",e.entrenamiento.to_numpy()),("holdout",e.holdout.to_numpy())):
                n=int(((price[mask] >= e.bid.to_numpy()[mask])&(price[mask] <= e.ask.to_numpy()[mask])).sum())
                if n != c["medidas"][modelo][grupo]["dentro"]:
                    raise ValueError("conteo independiente no coincide")
        filas+=len(e)
    if max_error > 1e-8:
        raise ValueError("precio independiente no coincide")
    control=json.loads((carpeta/"control_forward.json").read_text(encoding="utf-8"))
    if control["resumen_sha256"] != sha(carpeta/"resumen.json"):
        raise ValueError("control de forward desactualizado")
    if control["codigo_sha256_lf"] != hashlib.sha256(Path(__file__).with_name("control_forward.py").read_text(encoding="utf-8").encode()).hexdigest():
        raise ValueError("control de forward cambió")
    archivos=list(carpeta.glob("*.json"))
    for archivo in archivos:
        texto=archivo.read_text(encoding="utf-8")
        if any(id in texto for id in ids):
            raise ValueError("identificador real en salida pública")
        def recorrer(valor):
            if isinstance(valor,dict):
                if set(valor)&{"bid","ask","strike","id_contrato","valor_teorico","precio"}:
                    raise ValueError("campo individual en salida pública")
                for v in valor.values(): recorrer(v)
            elif isinstance(valor,list):
                for v in valor: recorrer(v)
        recorrer(json.loads(texto))
    evidencia=dict(cortes=len(r["cortes"]),filas_recalculadas=filas,precios_recalculados=2*filas,
        max_error_precio_independiente=max_error,conteos_train_y_holdout_reproducidos=True,
        fuentes_y_salidas_privadas_sha256_correctas=True,split_por_strike_verificado=True,
        privacidad_json="sin identificadores ni campos individuales de mercado",
        resumen_sha256=sha(carpeta/"resumen.json"),control_sha256=sha(carpeta/"control_forward.json"),
        codigo_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest())
    (carpeta/"verificacion.json").write_text(json.dumps(evidencia,ensure_ascii=False,allow_nan=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(evidencia,indent=2))


if __name__ == "__main__":
    main()
