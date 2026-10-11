"""Diagnóstico agregado; cotizaciones/rankings por contrato se guardan fuera de Git."""
import argparse
from dataclasses import asdict, replace
import gzip
import hashlib
import json
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
from quantileflow.adaptador_comparador import preparar_comparador
from quantileflow.distribucion_pde import resolver_distribucion
from quantileflow.escenarios import Escenario, comparar_contratos
from quantileflow.piloto import cargar_config


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def integridad(tablas, crudo):
    m = json.loads((tablas/"manifiesto_normalizacion.json").read_text(encoding="utf-8"))
    for nombre, esperado in m["salidas"].items():
        if sha(tablas/f"{nombre}.parquet") != esperado:
            raise ValueError("huella de tabla no coincide con normalización")
    paginas, manifestos = set(), 0
    for tipo in ("capturas", "historico", "eventos"):
        for entrada in m[tipo]:
            ruta = (crudo/entrada["manifiesto"]).resolve()
            if not ruta.is_relative_to(crudo.resolve()) or sha(ruta) != entrada["sha256"]:
                raise ValueError("huella/ruta de manifiesto incorrecta")
            manifestos += 1
            cap = json.loads(ruta.read_text(encoding="utf-8"))
            for solicitud in cap["solicitudes"].values():
                for pg in solicitud["paginas"]:
                    archivo = (crudo/pg["archivo"]).resolve()
                    if not archivo.is_relative_to(crudo.resolve()) or sha(archivo) != pg["sha256"]:
                        raise ValueError("huella/ruta de página incorrecta")
                    cuerpo = gzip.decompress(archivo.read_bytes())
                    if hashlib.sha256(cuerpo).hexdigest() != pg["sha256_contenido"]:
                        raise ValueError("huella de contenido incorrecta")
                    paginas.add(archivo)
    return dict(manifiestos=manifestos, paginas_unicas=len(paginas), estado="huellas correctas",
                tablas_sha256={n:sha(tablas/f"{n}.parquet") for n in ("cotizaciones", "subyacente")},
                manifiesto_normalizacion_sha256=sha(tablas/"manifiesto_normalizacion.json"))


def ranking(r, nombre):
    objetivo = lambda f: f["escenarios"]["objetivo"]["pnl"] if nombre == "ganancia" else f["pnl_minimo_escenarios"]
    filas = sorted(r["contratos"], key=lambda f:(-objetivo(f), f["contrato"]))
    return filas[0]["contrato"] if filas and (nombre == "ganancia" or objetivo(filas[0]) > 0) else "efectivo"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tablas", type=Path, required=True)
    p.add_argument("--crudo", type=Path, required=True)
    p.add_argument("--salida-privada", type=Path, required=True)
    p.add_argument("--salida-publica", type=Path, default=Path(__file__).parent/"resultados")
    p.add_argument("--protocolo", type=Path, default=Path(__file__).with_name("protocolo.toml"))
    args = p.parse_args()
    if args.salida_privada.resolve().is_relative_to(RAIZ) or args.salida_publica.resolve() == args.salida_privada.resolve():
        p.error("la salida privada debe estar fuera del repositorio y separada de la pública")
    proto = tomllib.loads(args.protocolo.read_text(encoding="utf-8"))
    cfg = cargar_config(RAIZ/"configs/piloto.toml")
    integr = integridad(args.tablas, args.crudo)
    q = pd.read_parquet(args.tablas/"cotizaciones.parquet")
    s = pd.read_parquet(args.tablas/"subyacente.parquet")
    args.salida_privada.mkdir(parents=True, exist_ok=True)
    args.salida_publica.mkdir(parents=True, exist_ok=True)
    es = [Escenario("objetivo", proto["dias_salida"], proto["movimiento_objetivo"]),
          Escenario("sin_movimiento", proto["dias_salida"], 0, -.03),
          Escenario("contrario", proto["dias_salida"], -.01)]
    cortes, errores_holdout, ids_nominales = [], [], {}
    for fecha in proto["fechas"]:
        for hora in proto["horas"]:
            r = preparar_comparador(q, s, fecha, hora, cfg.reglas, tasa=cfg.tasa, q=cfg.rendimiento_dividendo,
                modo_descriptivo=True, **{k:proto[k] for k in ("minimo_dias", "maximo_dias", "ancho_atm",
                "ancho_evaluacion", "minimo_entrenamiento", "objetivos_moneyness")})
            if r.evaluacion.empty or not r.evaluacion.holdout.any():
                raise ValueError("corte sin suficientes filas holdout para evaluar")
            e = r.evaluacion.copy()
            cache = {}
            numericos = []
            for _, f in e.iterrows():
                key = (f.dias, f.sigma_plana)
                if key not in cache:
                    cache[key] = resolver_distribucion(r.spot, f.dias/365, cfg.tasa, cfg.rendimiento_dividendo,
                        f.sigma_plana, nodos=proto["nodos"], pasos=proto["pasos"], semiancho=proto["semiancho"])
                d = cache[key]
                precio = d.precio_europeo(f.strike, f.tipo == "C")
                fino_key = (*key, "fino")
                if fino_key not in cache:
                    cache[fino_key] = resolver_distribucion(r.spot, f.dias/365, cfg.tasa, cfg.rendimiento_dividendo,
                        f.sigma_plana, nodos=801, pasos=1200, semiancho=proto["semiancho"])
                fino = cache[fino_key].precio_europeo(f.strike, f.tipo == "C")
                numericos.append((precio, fino))
            e["precio_plano"], e["precio_fino"] = np.array(numericos).T if numericos else ([], [])
            e["error_en_semispreads"] = (e.precio_plano-(e.bid+e.ask)/2)/((e.ask-e.bid)/2)
            h = e[e.holdout]
            errores_holdout.extend(h.error_en_semispreads.tolist())
            capmap = {c.identificador:c for c in r.candidatos}
            grupos = {c.identificador:str(e.loc[e.id_contrato == c.identificador, "vencimiento"].iloc[0]) for c in r.candidatos}
            limites = {c.identificador:int(e.loc[e.id_contrato == c.identificador, "tam_ask"].iloc[0]) for c in r.candidatos}
            spread = float(np.median([(c.ask-c.bid)/2 for c in r.candidatos])) if r.candidatos else .04
            def comparar(cs, spot=r.spot, n=proto["nodos"], pasos=proto["pasos"]):
                return comparar_contratos(cs, spot, es, proto["presupuesto_ficticio"], comision=proto["comision"],
                    semispread_salida=spread, tasa=cfg.tasa, q=cfg.rendimiento_dividendo,
                    motor="pde", nodos=n, pasos=pasos, semiancho=proto["semiancho"],
                    diagnosticos_pde=False, limites_cantidad=limites)
            variantes = []
            nominal = None
            for nivel_iv in proto["variantes_iv"]:
                for entrada in proto["variantes_entrada"]:
                    cs = [replace(c, iv=r.calibraciones[grupos[c.identificador]][nivel_iv],
                         ask=c.bid if entrada == "bid" else ((c.bid+c.ask)/2 if entrada == "mid" else c.ask)) for c in r.candidatos]
                    v = comparar(cs)
                    variantes.append(dict(iv=nivel_iv, entrada=entrada, resultado=v,
                                          ganador=ranking(v, "ganancia"), robusto=ranking(v, "robustez")))
                    if nivel_iv == "mid" and entrada == "ask":
                        nominal = v
            if nominal is None:
                raise ValueError("protocolo requiere IV mid y entrada ask")
            ganador = ranking(nominal, "ganancia")
            ids_nominales[(fecha, hora)] = ganador
            fino = comparar(r.candidatos, n=801, pasos=1200)
            nominal_map = {f["contrato"]:f for f in nominal["contratos"]}
            finom = {f["contrato"]:f for f in fino["contratos"]}
            errores_pnl = [abs(f["escenarios"]["objetivo"]["pnl"]-finom[id]["escenarios"]["objetivo"]["pnl"])
                           for id, f in nominal_map.items() if id in finom]
            # Perturbar la referencia ±un error jackknife; NO llamarlo intervalo de confianza.
            ref = s[(s.captura == f"{fecha}T{hora.replace(':','')}") & (s.subyacente == "SPX")].iloc[0]
            error_ref = float(ref.forward_error/ref.forward) if "forward_error" in ref and pd.notna(ref.forward_error) else 0
            ref_cases = [comparar(r.candidatos, spot=r.spot*(1+signo*error_ref)) for signo in (-1, 1)]
            # Casos por contrato se guardan solo en la carpeta privada.
            etiqueta = f"{fecha}_{hora.replace(':','')}"
            e.to_parquet(args.salida_privada/f"{etiqueta}_evaluacion.parquet", index=False)
            (args.salida_privada/f"{etiqueta}_rankings.json").write_text(json.dumps(dict(
                candidatos=[asdict(c) for c in r.candidatos], calibraciones=r.calibraciones,
                nominal=nominal, fino=fino, variantes=variantes, referencia_perturbada=ref_cases), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            cortes.append(dict(fecha=fecha, hora=hora, apto_puntual=r.apto_puntual, bloqueos=list(r.bloqueos),
                calidad=r.calidad, ajustes=len(r.calibraciones), candidatos=len(r.candidatos),
                evaluables=len(nominal["contratos"]), holdout=len(h),
                dentro_banda_holdout=int(((h.precio_plano >= h.bid)&(h.precio_plano <= h.ask)).sum()),
                dentro_banda_holdout_fino=int(((h.precio_fino >= h.bid)&(h.precio_fino <= h.ask)).sum()),
                mediana_error_abs_en_semispreads=float(h.error_en_semispreads.abs().median()),
                variantes=len(variantes), fraccion_mismo_primero=sum(v["ganador"] == ganador for v in variantes)/len(variantes),
                ganadores_distintos=len({v["ganador"] for v in variantes}), robusto=ranking(nominal, "robustez"),
                primer_ganador_fino_igual=ranking(fino,"ganancia") == ganador,
                max_cambio_pnl_refinamiento=max(errores_pnl, default=0),
                referencia_perturbada_mismo_primero=sum(ranking(v,"ganancia") == ganador for v in ref_cases),
                referencia_error_relativo=error_ref))
            print(f"{fecha} {hora}: {len(h)} holdout, {len(nominal['contratos'])} candidatos comparados; diagnóstico guardado", flush=True)
    fuentes = [Path(__file__), RAIZ/"quantileflow/adaptador_comparador.py", RAIZ/"quantileflow/escenarios.py",
               RAIZ/"quantileflow/distribucion_pde.py", args.protocolo]
    cambios = [ids_nominales[(f, "09:45")] != ids_nominales[(f, "10:00")] for f in proto["fechas"]]
    resumen = dict(version=proto["version"], naturaleza="diagnóstico de feed indicative, no recomendación operable",
        presupuesto_datos=0, presupuesto_operacion_ficticio=proto["presupuesto_ficticio"], integridad=integr,
        cortes=cortes, resumen=dict(cortes=len(cortes), aptos_puntuales=sum(c["apto_puntual"] for c in cortes),
            holdout=sum(c["holdout"] for c in cortes), dentro_banda=sum(c["dentro_banda_holdout"] for c in cortes),
            dentro_banda_fino=sum(c["dentro_banda_holdout_fino"] for c in cortes),
            cortes_con_primero_inestable=sum(c["ganadores_distintos"] > 1 for c in cortes),
            cambios_primero_entre_cortes=sum(cambios), pares_cortes=len(cambios)),
        entorno=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__),
        fuentes_sha256_lf={f.relative_to(RAIZ).as_posix():hashlib.sha256(f.read_text(encoding="utf-8").encode()).hexdigest() for f in fuentes},
        config_piloto_sha256=sha(RAIZ/"configs/piloto.toml"))
    (args.salida_publica/"resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    pd.DataFrame([{k:c[k] for k in ("fecha","hora","holdout","dentro_banda_holdout","dentro_banda_holdout_fino",
        "fraccion_mismo_primero","ganadores_distintos","primer_ganador_fino_igual","max_cambio_pnl_refinamiento")} for c in cortes]).to_csv(args.salida_publica/"metricas_agregadas.csv",index=False)
    fig, axs = plt.subplots(1,3,figsize=(14,4.5),layout="constrained")
    labels=[c["fecha"][5:]+" "+c["hora"] for c in cortes]
    axs[0].bar(range(len(cortes)),[c["dentro_banda_holdout"]/c["holdout"] for c in cortes])
    axs[0].set(title="IV plana: acierto de banda en holdout",ylabel="Fracción dentro de bid/ask",ylim=(0,1))
    axs[1].bar(range(len(cortes)),[c["fraccion_mismo_primero"] for c in cortes])
    axs[1].set(title="Mismo primero bajo nueve perturbaciones",ylabel="Fracción (sin probabilidad estadística)",ylim=(0,1))
    for ax in axs[:2]:
        ax.set_xticks(range(len(cortes)),labels,rotation=70,fontsize=7)
    axs[2].hist(np.clip(errores_holdout,-10,10),bins=np.linspace(-10,10,41))
    axs[2].axvspan(-1,1,color="green",alpha=.15,label="Dentro de bid/ask")
    axs[2].set(title="Desviación firmada del modelo",xlabel="Error / semispread (colas recortadas a ±10)",ylabel="Filas holdout")
    axs[2].legend(fontsize=8)
    fig.suptitle("QuantileFlow · doce cortes de feed gratuito · solo diagnóstico · datos USD 0")
    fig.savefig(args.salida_publica/"diagnostico_cadena.png",dpi=160)
    plt.close(fig)
    print(json.dumps(resumen["resumen"],indent=2))


if __name__ == "__main__":
    main()
