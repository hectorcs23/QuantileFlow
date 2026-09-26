"""Diagnóstico de las capturas de Alpaca de una fecha: cobertura, calidad del feed y medidas.

Uso, desde la raíz del repositorio::

    python scripts/verificar_alpaca.py --fecha 2026-09-28

Lee el crudo y los manifiestos de ``data/raw/alpaca`` (comprobando hashes),
procesa cada vencimiento con los controles y medidas del piloto y escribe en
``reports/verificacion_alpaca/<fecha>/`` un resumen en JSON, un informe
Markdown y dos gráficas. Solo publica **agregados y medidas derivadas**
(conteos, anchos, volatilidades implícitas, residuos relativos): nunca
cotizaciones individuales, que no se pueden redistribuir.

Una captura inmediata hecha con el mercado cerrado usa las últimas cotizaciones
de la sesión con el corte en su cierre. Como se recibió después del corte, la
verificación omite para ella las horas de snapshot y de disponibilidad (con
ellas, todas las filas quedarían «no disponibles al corte») y lo declara.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow import alpaca, almacen, cadenas, contrato, implicito  # noqa: E402
from quantileflow.calendario import _fecha  # noqa: E402
from quantileflow.piloto import cargar_config, elegir_vencimientos, plazo_constante  # noqa: E402

TICKS = {"SPXW": (0.05, 0.10, 3.0), "SPX": (0.05, 0.10, 3.0), "SPY": (0.01, 0.01, 3.0)}  # bajo, alto, umbral
TICK_CENTAVO = (0.01, 0.01, 3.0)  # raíces sin tabla: grilla de un centavo (no discrimina)
K_MIN_GRAFICA, K_MAX_GRAFICA = -0.25, 0.12  # región central de la sonrisa en la gráfica


def en_grilla(precios, raiz):
    """Fracción de precios positivos que caen en la grilla de ticks de la bolsa."""
    bajo, alto, umbral = TICKS.get(raiz, TICK_CENTAVO)
    p = np.asarray(precios, float)
    p = p[p > 0]
    tick = np.where(p < umbral, bajo, alto)
    return float(np.mean(np.isclose(np.round(p / tick) * tick, p, atol=1e-6))) if len(p) else float("nan")


def mediana(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else float("nan")


def cuantil(x, q):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.quantile(x, q)) if len(x) else float("nan")


def diagnostico(res: cadenas.ResultadoObservado, filas: pd.DataFrame, raiz, corte_utc) -> dict:
    """Calidad propia del feed: grilla de ticks, anchos cerca del dinero, edad, agrupación y paridad."""
    c, ctl, p, v = res.captura, res.controles, res.paridad, res.volatilidades
    F = v.forward
    k = np.log(c.strike / F)
    cerca = ctl.valida & (np.abs(k) <= 0.05)
    ancho = c.ask - c.bid
    evento = pd.to_datetime(filas["sello_evento_utc"], utc=True)
    segundos = evento.dt.floor("s").value_counts()
    edades = c.corte - c.sello
    usados = p.en_estimacion & np.isfinite(p.multiplo_ancho)
    return {
        "bid_en_grilla": en_grilla(c.bid, raiz), "ask_en_grilla": en_grilla(c.ask, raiz),
        "ancho_mediano_cerca": mediana(ancho[cerca]), "ancho_relativo_mediano_cerca": mediana((ancho / c.mid)[cerca]),
        "ancho_ticks_mediano_cerca": mediana((ancho / ctl_tick(raiz, c.mid))[cerca]),
        "edad_mediana_s": mediana(edades), "edad_p90_s": cuantil(edades, 0.9),
        "segundos_distintos": int(len(segundos)),
        "fraccion_en_3_segundos": float(segundos.iloc[:3].sum() / len(evento)) if len(evento) else float("nan"),
        "paridad_pares": int(len(p.strike)),
        "paridad_fuera_de_banda": float(np.mean(p.fuera_de_banda[usados])) if usados.any() else float("nan"),
        "paridad_mediana_abs_multiplo": mediana(np.abs(p.multiplo_ancho[usados])),
        "paridad_p90_abs_multiplo": cuantil(np.abs(p.multiplo_ancho[usados]), 0.9),
        "forward": p.forward_global, "forward_error": p.forward_error,
        "tasa_implicita": p.tasa_implicita, "tasa_error": p.tasa_error,
    }


def ctl_tick(raiz, precio):
    bajo, alto, umbral = TICKS.get(raiz, TICK_CENTAVO)
    return np.where(np.asarray(precio) < umbral, bajo, alto)


def graficas(resultados, salida, titulo):
    """Sonrisa con bandas bid/ask y residuos de paridad del vencimiento más cercano a 30 días."""
    rutas = {}
    venc, dias, res = resultados
    v, p = res.volatilidades, res.paridad
    plt.figure()
    for es_call, nombre in ((False, "OTM puts"), (True, "OTM calls")):
        m = (v.es_call == es_call) & np.isfinite(v.iv) & (v.k >= K_MIN_GRAFICA) & (v.k <= K_MAX_GRAFICA)
        plt.errorbar(v.k[m], v.iv[m] * 100, yerr=[(v.iv[m] - v.iv_bid[m]) * 100, (v.iv_ask[m] - v.iv[m]) * 100],
                     fmt="o", markersize=3, capsize=2, label=nombre)
    plt.xlabel("Log-moneyness k = ln(K/F), central region")
    plt.ylabel("Implied volatility (%), mid with bid-ask band")
    plt.title(f"{titulo}: {venc} ({dias:.1f} days)")
    plt.legend()
    rutas["sonrisa"] = salida / "sonrisa_30d.png"
    plt.savefig(rutas["sonrisa"])
    plt.close()

    plt.figure()
    k = np.log(p.strike / v.forward)
    dentro = ~p.fuera_de_banda
    plt.plot(k[dentro], p.multiplo_ancho[dentro], "o", markersize=3, label="Inside the bid-ask band")
    plt.plot(k[~dentro], p.multiplo_ancho[~dentro], "x", label="Outside the band")
    plt.axhline(0.5, color="k", linestyle="--", linewidth=1)
    plt.axhline(-0.5, color="k", linestyle="--", linewidth=1)
    plt.xlabel("Log-moneyness k = ln(K/F)")
    plt.ylabel("Parity residual / bid-ask width of the pair")
    plt.title(f"Put-call parity residuals: {venc}")
    plt.legend()
    rutas["paridad"] = salida / "paridad_30d.png"
    plt.savefig(rutas["paridad"])
    plt.close()
    return rutas


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--fecha", required=True)
    a.add_argument("--datos", default=str(RAIZ / "data"))
    a.add_argument("--config", default=str(RAIZ / "configs" / "captura_alpaca.toml"))
    a.add_argument("--config-piloto", default=str(RAIZ / "configs" / "piloto.toml"))
    a.add_argument("--salida", default=None)
    args = a.parse_args()
    fecha = _fecha(args.fecha)
    with open(args.config, "rb") as f:
        cfg_imp = tomllib.load(f)["implicito"]
    piloto = cargar_config(args.config_piloto)
    reglas, tasa, q = piloto.reglas, piloto.tasa, piloto.rendimiento_dividendo
    datos = Path(args.datos)
    salida = Path(args.salida) if args.salida else RAIZ / "reports" / "verificacion_alpaca" / str(fecha)
    salida.mkdir(parents=True, exist_ok=True)

    cot, sub, resumenes, manifiestos = alpaca.normalizar(datos, fecha, fecha)
    if not manifiestos:
        print(f"no hay capturas de {fecha} en {datos}", file=sys.stderr)
        return 1
    informe = {"fecha": str(fecha), "capturas": []}
    figura = None
    for m, resumen in zip(manifiestos, resumenes):
        corte = pd.Timestamp(m["corte_utc"])
        filas_m = cot[cot["captura"] == m["etiqueta"]].copy()
        fuera = bool(len(filas_m)) and filas_m["recibido_utc"].max() > corte
        if fuera:  # cotizaciones de una sesión ya cerrada: sin horas de snapshot ni disponibilidad
            filas_m = filas_m.drop(columns=["sello_snapshot_utc", "disponible_utc"])
        pags = [p for e in m["solicitudes"].values() if e["tipo"] in ("cadena", "acciones") for p in e["paginas"]]
        entrada = {
            "etiqueta": m["etiqueta"], "modo": m.get("modo"), "hora": m["hora"], "corte_utc": m["corte_utc"],
            "feed_opciones": m.get("feed_opciones"), "cuenta": m.get("cuenta"),
            "desfase_reloj_s": m.get("reloj", {}).get("desfase_s"),
            "duracion_s": (pd.Timestamp(m["fin_utc"]) - pd.Timestamp(m["inicio_utc"])).total_seconds(),
            "respuestas": len(pags), "bytes": int(sum(p.get("bytes_contenido", p["bytes"]) for p in pags)),
            "errores": len(m["errores"]),
            "respuestas_despues_del_corte": len(m["respuestas_despues_del_corte"]),
            "recibida_despues_del_cierre": fuera, "cobertura": resumen, "raices": {},
        }
        # Nivel implícito de SPX con el vencimiento SPXW más cercano.
        spx = filas_m[filas_m["raiz"] == cfg_imp["raiz"]]
        spot_spx = {"estado": "sin filas"}
        for venc in sorted({_fecha(x) for x in spx["vencimiento"]}):
            try:
                spot_spx = implicito.spot_implicito(spx[spx["vencimiento"].map(_fecha) == venc], m["fecha"], corte,
                                                    cfg_imp["tasa"], cfg_imp["rendimiento_dividendo"], reglas,
                                                    cfg_imp["minimo_pares"])
            except contrato.SinDatos:
                continue
            if spot_spx["estado"] == "identificado" or spot_spx["T"] * 365 > cfg_imp["dias_max"]:
                break
        spy = sub[(sub["captura"] == m["etiqueta"]) & (sub["subyacente"] == "SPY")]
        spot_spy = float(spy["precio"].iloc[-1]) if len(spy) else float("nan")
        entrada["spot_spx_implicito"] = {k: (str(v) if k in ("vencimiento", "sello_evento_utc") else v)
                                         for k, v in spot_spx.items()}
        entrada["spot_spy_iex"] = spot_spy
        if spot_spx.get("estado") == "identificado" and np.isfinite(spot_spy):
            entrada["razon_spx_spy"] = spot_spx["spot"] / spot_spy
        spots = {"SPXW": spot_spx.get("spot", float("nan")), "SPY": spot_spy}
        sellos_spot = {"SPXW": pd.Timestamp(spot_spx["sello_evento_utc"]) if "sello_evento_utc" in spot_spx else None,
                       "SPY": spy["sello_evento_utc"].iloc[-1] if len(spy) else None}

        for raiz in sorted(filas_m["raiz"].unique()):
            filas_r = filas_m[filas_m["raiz"] == raiz]
            por_venc, medidas, plazos = {}, {}, {}
            for venc in sorted({_fecha(x) for x in filas_r["vencimiento"]}):
                filas = filas_r[filas_r["vencimiento"].map(_fecha) == venc]
                try:
                    cap, info = contrato.captura_de_filas(filas, m["fecha"], corte, spots.get(raiz, np.nan),
                                                          sellos_spot.get(raiz),
                                                          tasa, q)
                except contrato.SinDatos as error:
                    por_venc[str(venc)] = {"estado": str(error)}
                    continue
                res = cadenas.procesar_captura(cap, reglas, distancia=piloto.factor_strike - 1.0, delta=piloto.delta,
                                               hueco_max=piloto.hueco_max_k, hueco_max_delta=piloto.hueco_max_delta)
                calidad = cadenas.metricas_calidad(res, reglas)
                fila = cadenas.fila_informe(res)
                por_venc[str(venc)] = {
                    "dias": info["dias"], "filas": calidad["filas"], "filas_validas": calidad["filas_validas"],
                    "exclusiones": calidad["exclusiones"], "alertas": list(res.alertas),
                    "diagnostico": diagnostico(res, filas, raiz, corte),
                    "rr25": {k: fila[k] for k in ("obs_rr25_estado", "obs_rr25", "obs_rr25_inferior",
                                                  "obs_rr25_superior")},
                    "asim_log": {k: fila[k] for k in ("obs_asim_log_estado", "obs_asim_log", "obs_asim_log_inferior",
                                                      "obs_asim_log_superior")},
                    "pendiente": res.pendiente}
                medidas[venc], plazos[venc] = res, info["dias"]
            elegidos, motivo = elegir_vencimientos(plazos, piloto)
            constante = {"motivo": motivo}
            if elegidos:
                T = piloto.objetivo_dias / piloto.base_dias
                for nombre, clave in (("rr25", "asimetria_delta"), ("asim_log", "asimetria")):
                    constante[nombre] = plazo_constante([getattr(medidas[v], clave) for v in elegidos],
                                                        [plazos[v] / piloto.base_dias for v in elegidos], T)
                constante["vencimientos"] = [str(v) for v in elegidos]
                if figura is None and raiz == "SPXW":
                    cercano = min(elegidos, key=lambda v: abs(plazos[v] - piloto.objetivo_dias))
                    figura = (cercano, plazos[cercano], medidas[cercano])
            entrada["raices"][raiz] = {"vencimientos": por_venc, "plazo_constante_30d": constante,
                                       "exclusiones_totales": dict(sum((Counter(x.get("exclusiones", {}))
                                                                        for x in por_venc.values()), Counter()))}
        informe["capturas"].append(entrada)

    rutas = graficas(figura, salida, f"SPXW {fecha}") if figura else {}
    almacen.escribir_json(informe, salida / "resumen.json")
    escribir_markdown(informe, salida, rutas)
    print(f"{salida.relative_to(RAIZ) if salida.is_relative_to(RAIZ) else salida}: "
          f"{len(informe['capturas'])} capturas")
    return 0


def _n(x, factor=1.0, dec=2):
    try:
        return "" if x is None or not np.isfinite(float(x)) else f"{float(x) * factor:.{dec}f}"
    except (TypeError, ValueError):
        return str(x)


def escribir_markdown(informe, salida, rutas):
    lineas = [f"# Verificación de capturas de Alpaca: {informe['fecha']}", "",
              "Generado por `scripts/verificar_alpaca.py` desde el crudo. Solo agregados y medidas derivadas.", ""]
    for c in informe["capturas"]:
        lineas += [f"## Captura `{c['etiqueta']}`", "",
                   f"- Modo {c['modo']}, corte {c['corte_utc']}, feed de opciones `{c['feed_opciones']}`, "
                   f"cuenta {c['cuenta']}; desfase del reloj local {_n(c['desfase_reloj_s'], 1, 3)} s.",
                   f"- {c['respuestas']} respuestas ({c['bytes'] / 1e6:.1f} MB sin comprimir) "
                   f"en {c['duracion_s']:.2f} s; "
                   f"errores {c['errores']}; respuestas después del corte {c['respuestas_despues_del_corte']}.",
                   f"- Cobertura: {c['cobertura'].get('con_cotizacion', 0)} contratos con cotización de "
                   f"{c['cobertura'].get('snapshots', 0)}; sin cotización {c['cobertura'].get('sin_cotizacion', 0)}; "
                   f"sin metadatos {c['cobertura'].get('sin_metadatos', 0)}."]
        if c["recibida_despues_del_cierre"]:
            lineas.append("- **Recibida con el mercado cerrado**: cotizaciones del cierre; se omitieron las horas de "
                          "snapshot y de disponibilidad. No es una sesión del piloto.")
        s = c["spot_spx_implicito"]
        lineas.append(f"- SPX implícito: {s.get('estado')}"
                      + (f", {_n(s.get('spot'))} con {s.get('pares')} pares del {s.get('vencimiento')} "
                         f"(error del forward {_n(s.get('forward_error'), 1, 3)})" if s.get("estado") == "identificado"
                         else f" ({s.get('motivo', '')})")
                      + f"; SPY (IEX) {_n(c['spot_spy_iex'])}"
                      + (f"; razón SPX/SPY {_n(c.get('razon_spx_spy'), 1, 4)}." if "razon_spx_spy" in c else "."))
        lineas.append("")
        for raiz, r in c["raices"].items():
            lineas += [f"### {raiz}", "",
                       "| Vencimiento | Días | Válidas/filas | Bid en grilla | Ancho cerca (ticks) "
                       "| Edad mediana (s) | Pares | Fuera de banda | Mediana abs(res)/ancho | Tasa implícita "
                       "| RR25 (pts) |",
                       "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for venc, x in r["vencimientos"].items():
                if "diagnostico" not in x:
                    lineas.append(f"| {venc} | | {x['estado']} | | | | | | | | |")
                    continue
                d = x["diagnostico"]
                rr = _n(x["rr25"]["obs_rr25"], 100) or x["rr25"]["obs_rr25_estado"]
                # A pocos días la pendiente de C - P no identifica el descuento: no se muestra la tasa.
                tasa = f"{_n(d['tasa_implicita'], 100, 2)} %" if x["dias"] >= 7 else "—"
                lineas.append(f"| {venc} | {x['dias']:.1f} | {x['filas_validas']}/{x['filas']} | "
                              f"{_n(d['bid_en_grilla'], 100, 0)} % | {_n(d['ancho_ticks_mediano_cerca'], 1, 1)} | "
                              f"{_n(d['edad_mediana_s'], 1, 0)} | {d['paridad_pares']} | "
                              f"{_n(d['paridad_fuera_de_banda'], 100, 0)} % | "
                              f"{_n(d['paridad_mediana_abs_multiplo'], 1, 2)} | {tasa} | "
                              f"{rr} |")
            ex = r["exclusiones_totales"]
            lineas += ["", "Exclusiones: " + (", ".join(f"{k} {n}" for k, n in sorted(ex.items(), key=lambda t: -t[1]))
                                              or "ninguna") + "."]
            pc = r["plazo_constante_30d"]
            if "rr25" in pc:
                rr, al = pc["rr25"], pc["asim_log"]
                lineas.append(f"A 30 días ({', '.join(pc['vencimientos'])}): RR25 {rr['estado']}"
                              + (f" = {_n(rr['valor'], 100)} puntos, banda [{_n(rr['inferior'], 100)}, "
                                 f"{_n(rr['superior'], 100)}]" if rr["estado"] == "identificada"
                                 else f" ({rr['motivo']})")
                              + f"; asimetría logarítmica {al['estado']}"
                              + (f" = {_n(al['valor'], 100)} puntos." if al["estado"] == "identificada"
                                 else f" ({al['motivo']})."))
            else:
                lineas.append(f"A 30 días: no disponible ({pc['motivo']}).")
            lineas.append("")
    for nombre, ruta in rutas.items():
        lineas += [f"![{nombre}]({Path(ruta).name})", ""]
    (salida / "informe.md").write_text("\n".join(lineas), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
