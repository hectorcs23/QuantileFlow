"""Comparación cerrada de bandas y smile; los resultados individuales son privados."""
import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import tomllib

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from experiments.cadena_comparador_20261010.evaluar_cadena import integridad, ranking, sha
from quantileflow.adaptador_comparador import preparar_comparador
from quantileflow.ajuste_bandas import (ajustar_bandas, precios_ajuste,
    incompatibilidades_paridad, valorador_bandas)
from quantileflow.escenarios import Escenario, comparar_contratos
from quantileflow.piloto import cargar_config
from quantileflow.superficies import Rebanada, funcion_g


def rebanadas(filas, spot, tasa, q):
    resultado = []
    for _, g in filas.groupby("dias", sort=True):
        T = float(g.dias.iloc[0])/365
        resultado.append(Rebanada(T, spot*math.exp((tasa-q)*T), math.exp(-tasa*T),
            g.strike.to_numpy(float), g.bid.to_numpy(float), g.ask.to_numpy(float), g.tipo.eq("C").to_numpy()))
    return resultado


def metricas(filas, columna):
    p = filas[columna].to_numpy()
    error = np.abs(p-(filas.bid.to_numpy()+filas.ask.to_numpy())/2)/((filas.ask-filas.bid).to_numpy()/2)
    return dict(filas=len(filas), dentro=int(((p >= filas.bid)&(p <= filas.ask)).sum()),
                mediana_error_semispreads=float(np.median(error)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for campo in ("tablas", "crudo", "salida-privada"):
        p.add_argument("--"+campo, type=Path, required=True)
    p.add_argument("--salida-publica", type=Path, default=Path(__file__).parent/"resultados")
    p.add_argument("--protocolo", type=Path, default=Path(__file__).with_name("protocolo.toml"))
    a = p.parse_args()
    privada, publica = a.salida_privada.resolve(), a.salida_publica.resolve()
    if (privada.is_relative_to(RAIZ) or publica.is_relative_to(privada) or privada.is_relative_to(publica)):
        p.error("salidas privadas y públicas deben estar fuera una de otra; privados fuera de Git")
    proto = tomllib.loads(a.protocolo.read_text(encoding="utf-8"))
    cfg = cargar_config(RAIZ/"configs/piloto.toml")
    evidencia = integridad(a.tablas, a.crudo)
    qs = pd.read_parquet(a.tablas/"cotizaciones.parquet")
    refs = pd.read_parquet(a.tablas/"subyacente.parquet")
    privada.mkdir(parents=True, exist_ok=True)
    publica.mkdir(parents=True, exist_ok=True)
    escenarios = [Escenario(nombre, proto["dias_salida"], mov) for nombre, mov in
                  zip(("objetivo", "sin_movimiento", "contrario"), proto["movimientos"])]
    cortes, primeros = [], {}
    for fecha in proto["fechas"]:
        for hora in proto["horas"]:
            prep = preparar_comparador(qs, refs, fecha, hora, cfg.reglas, modo_descriptivo=True,
                tasa=cfg.tasa, q=cfg.rendimiento_dividendo, ancho_atm=proto["ancho_evaluacion"],
                **{k:proto[k] for k in ("ancho_evaluacion", "minimo_dias", "maximo_dias",
                                      "minimo_entrenamiento", "objetivos_moneyness")})
            e = prep.evaluacion.copy()
            if e.empty or not e.holdout.any() or not (~e.holdout).equals(e.entrenamiento):
                raise ValueError("split debe cubrir exactamente training y holdout disjuntos")
            trains = rebanadas(e[e.entrenamiento], prep.spot, cfg.tasa, cfg.rendimiento_dividendo)
            paridades = [incompatibilidades_paridad(r) for r in trains]
            ajustes = {v:ajustar_bandas(trains, v, proto["peso_mid"]) for v in proto["preferencias_banda"]}
            nominal = ajustes[.5]
            e = e.drop(columns="sigma_plana")  # mediana del adaptador, no ajuste de este experimento
            for modelo in ("plano", "ssvi"):
                e["modelo_"+modelo] = np.nan
                for dias, g in e.groupby("dias", sort=True):
                    reb = rebanadas(g, prep.spot, cfg.tasa, cfg.rendimiento_dividendo)[0]
                    e.loc[g.index, "modelo_"+modelo] = precios_ajuste(nominal, reb, modelo)
            limites = {c.identificador:int(e.loc[e.id_contrato == c.identificador, "tam_ask"].iloc[0])
                       for c in prep.candidatos}
            spread = float(np.median([(c.ask-c.bid)/2 for c in prep.candidatos]))
            def comparar(ajuste, modelo, entrada, dinamica):
                cs = []
                for c in prep.candidatos:
                    T = c.dte/365
                    F = prep.spot*math.exp((cfg.tasa-cfg.rendimiento_dividendo)*T)
                    iv = ajuste.planas[T] if modelo == "plano" else float(
                        np.sqrt(ajuste.superficie.w(math.log(c.strike/F),T)/T))
                    cs.append(replace(c, iv=iv, ask=c.bid if entrada == "bid" else
                              ((c.bid+c.ask)/2 if entrada == "mid" else c.ask)))
                return comparar_contratos(cs, prep.spot, escenarios, proto["presupuesto_ficticio"],
                    comision=proto["comision"], semispread_salida=spread,
                    tasa=cfg.tasa, q=cfg.rendimiento_dividendo, limites_cantidad=limites,
                    valorador=valorador_bandas(ajuste, modelo, dinamica))
            privado = dict(diagnosticos={str(v):fit.diagnostico for v, fit in ajustes.items()}, rankings={})
            medidas, ganadores = {}, {}
            for modelo in ("plano", "ssvi"):
                variantes = [dict(preferencia=v, entrada=entrada,
                    resultado=comparar(ajustes[v], modelo, entrada, proto["dinamica_nominal"]))
                    for v in proto["preferencias_banda"] for entrada in proto["entradas"]]
                base = next(v["resultado"] for v in variantes if v["preferencia"] == .5 and v["entrada"] == "ask")
                ganador = ranking(base, "ganancia")
                ganadores[modelo] = ganador
                primeros[(fecha, hora, modelo)] = ganador
                alternativo = comparar(nominal, modelo, "ask", proto["dinamica_alternativa"])
                gs = [ranking(v["resultado"], "ganancia") for v in variantes]
                robustos = [ranking(v["resultado"], "robustez") for v in variantes]
                medidas[modelo] = dict(train=metricas(e[e.entrenamiento], "modelo_"+modelo),
                    holdout=metricas(e[e.holdout], "modelo_"+modelo),
                    ganadores_distintos=len(set(gs)), mismo_primero=sum(g == ganador for g in gs),
                    casos=len(gs), cambio_dinamica=ranking(alternativo,"ganancia") != ganador,
                    robusto_efectivo=ranking(base,"robustez") == "efectivo",
                    casos_robusto_efectivo=sum(g == "efectivo" for g in robustos))
                privado["rankings"][modelo] = dict(variantes=variantes, alternativo=alternativo)
            # Malla diagnóstica; el certificado original es analítico, no esta malla.
            k = np.linspace(-2, 2, 4001)
            gmin = min(float(funcion_g(*nominal.superficie.derivadas(k,T), k).min())
                       for T in nominal.superficie.tiempos)
            etiqueta = fecha+"_"+hora.replace(":", "")
            e.to_parquet(privada/(etiqueta+"_evaluacion.parquet"), index=False)
            privado["parametros"] = {str(v):dict(planas={str(T):s for T,s in fit.planas.items()},
                tiempos=fit.superficie.tiempos.tolist(), thetas=fit.superficie.thetas.tolist(),
                rho=fit.superficie.rho, eta=fit.superficie.eta, gamma=fit.superficie.gamma)
                for v,fit in ajustes.items()}
            (privada/(etiqueta+"_ajustes.json")).write_text(
                json.dumps(privado, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
            extrapoladas = sum((c.dte-proto["dias_salida"])/365 < nominal.superficie.tiempos[0]
                              for c in prep.candidatos)
            cortes.append(dict(fecha=fecha, hora=hora, apto_puntual=prep.apto_puntual,
                bloqueos=list(prep.bloqueos), vencimientos=len(trains), candidatos=len(prep.candidatos),
                dias_min=float(e.dias.min()), dias_max=float(e.dias.max()),
                paridad_training=dict(pares=sum(x["pares"] for x in paridades),
                    incompatibles=sum(x["incompatibles"] for x in paridades)),
                convergencia=all(f.diagnostico["convergencia_ssvi"] for f in ajustes.values()),
                condiciones_todas=all(all(f.superficie.condiciones().values()) for f in ajustes.values()),
                g_min_malla=gmin, medidas=medidas,
                ganador_plano_ssvi_igual=ganadores["plano"] == ganadores["ssvi"],
                candidatos_extrapolados_dinamica_alternativa=int(extrapoladas)))
            print(f"{fecha} {hora}: {len(e[e.holdout])} holdout; plano {medidas['plano']['holdout']['dentro']}, SSVI {medidas['ssvi']['holdout']['dentro']}", flush=True)
    total = dict(cortes=len(cortes), sesiones=len(proto["fechas"]),
                 aptos_puntuales=sum(c["apto_puntual"] for c in cortes),
                 pares_paridad_training=sum(c["paridad_training"]["pares"] for c in cortes),
                 incompatibles_training=sum(c["paridad_training"]["incompatibles"] for c in cortes),
                 cortes_ganador_igual=sum(c["ganador_plano_ssvi_igual"] for c in cortes))
    for modelo in ("plano", "ssvi"):
        total[modelo] = dict(holdout=sum(c["medidas"][modelo]["holdout"]["filas"] for c in cortes),
            dentro=sum(c["medidas"][modelo]["holdout"]["dentro"] for c in cortes),
            cortes_primero_inestable=sum(c["medidas"][modelo]["ganadores_distintos"] > 1 for c in cortes),
            cambios_entre_cortes=sum(primeros[(f,"09:45",modelo)] != primeros[(f,"10:00",modelo)] for f in proto["fechas"]),
            cambios_dinamica=sum(c["medidas"][modelo]["cambio_dinamica"] for c in cortes),
            cortes_robusto_efectivo=sum(c["medidas"][modelo]["robusto_efectivo"] for c in cortes))
    fuentes = [Path(__file__), a.protocolo, RAIZ/"quantileflow/ajuste_bandas.py",
        RAIZ/"quantileflow/superficies.py", RAIZ/"quantileflow/escenarios.py",
        RAIZ/"quantileflow/adaptador_comparador.py",
        RAIZ/"quantileflow/opciones.py", RAIZ/"quantileflow/cadenas.py",
        RAIZ/"quantileflow/contrato.py", RAIZ/"quantileflow/calendario.py",
        RAIZ/"experiments/cadena_comparador_20261010/evaluar_cadena.py"]
    resumen = dict(version=proto["version"], presupuesto_datos=0,
        naturaleza="holdout transversal de indicative; no pronóstico ni precios ejecutables",
        integridad=evidencia, config_sha256=sha(RAIZ/"configs/piloto.toml"),
        fuentes_sha256_lf={f.relative_to(RAIZ).as_posix():hashlib.sha256(f.read_text(encoding="utf-8").encode()).hexdigest() for f in fuentes},
        salidas_privadas_sha256={f.name:sha(f) for f in sorted(privada.glob("*_evaluacion.parquet"))}
            | {f.name:sha(f) for f in sorted(privada.glob("*_ajustes.json"))},
        entorno=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,pandas=pd.__version__),
        protocolo=proto, total=total, cortes=cortes)
    (publica/"resumen.json").write_text(json.dumps(resumen,ensure_ascii=False,allow_nan=False,indent=2)+"\n", encoding="utf-8")
    fig, axs = plt.subplots(1,3, figsize=(15,4.7),layout="constrained")
    x = np.arange(len(cortes))
    for modelo, color, offset in (("plano","#4f7cac",-.18),("ssvi","#dc7359",.18)):
        axs[0].bar(x+offset,[c["medidas"][modelo]["holdout"]["dentro"]/c["medidas"][modelo]["holdout"]["filas"] for c in cortes],width=.35,label=modelo,color=color)
        axs[1].plot(x,[c["medidas"][modelo]["holdout"]["mediana_error_semispreads"] for c in cortes],"o-",label=modelo,color=color)
        axs[2].bar(x+offset,[c["medidas"][modelo]["mismo_primero"]/9 for c in cortes],width=.35,label=modelo,color=color)
    axs[0].set(title="Cotizaciones reservadas dentro de banda", ylabel="Fracción",ylim=(0,1))
    axs[1].set(title="Error absoluto en validación",ylabel="Mediana / semispread",yscale="log")
    axs[2].set(title="Mismo primero en nueve perturbaciones",ylabel="Fracción de casos (no confianza)",ylim=(0,1))
    labels = [c["fecha"][5:]+" "+c["hora"] for c in cortes]
    for ax in axs:
        ax.set_xticks(x,labels,rotation=70,fontsize=7)
        ax.legend(fontsize=8)
    fig.suptitle("QuantileFlow · mismos datos y pérdida para ambos modelos · 6 sesiones · USD 0")
    fig.savefig(publica/"skew_bandas.png",dpi=160)
    plt.close(fig)
    print(json.dumps(total,indent=2))


if __name__ == "__main__":
    main()
