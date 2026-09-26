"""Diagnóstico de capturas: elegibilidad al corte y calidad del feed, sin confundir las dos.

La **elegibilidad** usa siempre los controles estrictos del piloto con todos los
sellos (evento, snapshot y disponibilidad): una captura programada que llegó
después de su corte no aporta ninguna fila válida a esa decisión, aunque sus
cotizaciones sean anteriores.

El **modo descriptivo del cierre** es otra cosa y solo existe si se pide. Sirve
para describir el feed con las últimas cotizaciones de una sesión ya cerrada, y
exige una captura inmediata, recibida con la sesión cerrada y cortada en su
cierre según el calendario. Entonces se omiten las horas de snapshot y de
disponibilidad (con ellas no quedaría ninguna fila) y el resultado se declara no
elegible para el piloto. La elegibilidad estricta se informa igual.

Solo produce agregados y medidas derivadas: nunca cotizaciones individuales.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from . import alpaca, cadenas, contrato, implicito
from .calendario import CALENDARIO, _fecha, cierre, es_sesion
from .piloto import ConfigPiloto, elegir_vencimientos, plazo_constante

TICKS = {"SPXW": (0.05, 0.10, 3.0), "SPX": (0.05, 0.10, 3.0), "SPY": (0.01, 0.01, 3.0)}  # bajo, alto, umbral
TICK_CENTAVO = (0.01, 0.01, 3.0)  # raíces sin tabla: grilla de un centavo (no discrimina)


def tick(raiz, precio):
    bajo, alto, umbral = TICKS.get(raiz, TICK_CENTAVO)
    return np.where(np.asarray(precio) < umbral, bajo, alto)


def en_grilla(precios, raiz):
    """Fracción de precios positivos que caen en la grilla de ticks de la bolsa."""
    p = np.asarray(precios, float)
    p = p[p > 0]
    t = tick(raiz, p)
    return float(np.mean(np.isclose(np.round(p / t) * t, p, atol=1e-6))) if len(p) else float("nan")


def mediana(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else float("nan")


def cuantil(x, q):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.quantile(x, q)) if len(x) else float("nan")


def calidad_feed(res: cadenas.ResultadoObservado, filas: pd.DataFrame, raiz) -> dict:
    """Grilla de ticks, anchos cerca del dinero, edad, agrupación de sellos y paridad."""
    c, ctl, p, v = res.captura, res.controles, res.paridad, res.volatilidades
    k = np.log(c.strike / v.forward)
    cerca = ctl.valida & (np.abs(k) <= 0.05)
    ancho = c.ask - c.bid
    evento = pd.to_datetime(filas["sello_evento_utc"], utc=True)
    segundos = evento.dt.floor("s").value_counts()
    edades = c.corte - c.sello
    usados = p.en_estimacion & np.isfinite(p.multiplo_ancho)
    return {
        "bid_en_grilla": en_grilla(c.bid, raiz), "ask_en_grilla": en_grilla(c.ask, raiz),
        "ancho_mediano_cerca": mediana(ancho[cerca]), "ancho_relativo_mediano_cerca": mediana((ancho / c.mid)[cerca]),
        "ancho_ticks_mediano_cerca": mediana((ancho / tick(raiz, c.mid))[cerca]),
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


def modo_descriptivo(manifiesto: dict, pedido: bool, codigo=CALENDARIO):
    """Si el modo descriptivo del cierre se aplica a una captura, y por qué (o por qué no)."""
    if not pedido:
        return False, "no pedido: controles estrictos"
    if manifiesto.get("modo") != "inmediata":
        return False, "solo se aplica a capturas inmediatas; esta es programada: controles estrictos"
    fecha = _fecha(manifiesto["fecha"])
    if not es_sesion(fecha, codigo):
        return False, f"{fecha} no es sesión: controles estrictos"
    fin_sesion = cierre(fecha, codigo)
    if pd.Timestamp(manifiesto["corte_utc"]) != fin_sesion:
        return False, "el corte no es el cierre de la sesión: controles estrictos"
    recibidas = [pd.Timestamp(p["recibido_utc"]) for e in manifiesto["solicitudes"].values() if e["tipo"] == "cadena"
                 for p in e["paginas"]]
    if not recibidas or min(recibidas) <= fin_sesion:
        return False, "la captura no se recibió con la sesión cerrada: controles estrictos"
    return True, f"captura inmediata recibida con la sesión del {fecha} cerrada; corte en su cierre"


def _nivel_implicito(filas, fecha, corte, cfg_imp, reglas):
    spx = filas[filas["raiz"] == cfg_imp["raiz"]]
    resultado = {"estado": "sin filas"}
    for venc in sorted({_fecha(x) for x in spx["vencimiento"]}):
        try:
            resultado = implicito.spot_implicito(spx[spx["vencimiento"].map(_fecha) == venc], fecha, corte,
                                                 cfg_imp["tasa"], cfg_imp["rendimiento_dividendo"], reglas,
                                                 cfg_imp["minimo_pares"])
        except contrato.SinDatos:
            continue
        if resultado["estado"] == "identificado" or resultado["T"] * 365 > cfg_imp["dias_max"]:
            break
    return resultado


def medir_captura(filas_m, sub_m, fecha, corte, cfg_imp, piloto: ConfigPiloto):
    """Medidas por raíz y vencimiento de las filas de una captura, con el nivel implícito de SPX."""
    reglas = piloto.reglas
    spot_spx = _nivel_implicito(filas_m, fecha, corte, cfg_imp, reglas)
    spy = sub_m[sub_m["subyacente"] == "SPY"]
    spot_spy = float(spy["precio"].iloc[-1]) if len(spy) else float("nan")
    spots = {cfg_imp["raiz"]: spot_spx.get("spot", float("nan")), "SPY": spot_spy}
    sellos = {cfg_imp["raiz"]: spot_spx.get("sello_evento_utc"), "SPY": spy["sello_evento_utc"].iloc[-1]
              if len(spy) else None}
    raices, figura = {}, None
    for raiz in sorted(filas_m["raiz"].unique()):
        filas_r = filas_m[filas_m["raiz"] == raiz]
        por_venc, medidas, plazos = {}, {}, {}
        for venc in sorted({_fecha(x) for x in filas_r["vencimiento"]}):
            filas = filas_r[filas_r["vencimiento"].map(_fecha) == venc]
            try:
                cap, info = contrato.captura_de_filas(filas, fecha, corte, spots.get(raiz, np.nan), sellos.get(raiz),
                                                      piloto.tasa, piloto.rendimiento_dividendo)
            except contrato.SinDatos as error:
                por_venc[str(venc)] = {"estado": str(error), "filas": len(filas), "filas_validas": 0}
                continue
            res = cadenas.procesar_captura(cap, reglas, distancia=piloto.factor_strike - 1.0, delta=piloto.delta,
                                           hueco_max=piloto.hueco_max_k, hueco_max_delta=piloto.hueco_max_delta)
            calidad = cadenas.metricas_calidad(res, reglas)
            fila = cadenas.fila_informe(res)
            por_venc[str(venc)] = {
                "dias": info["dias"], "filas": calidad["filas"], "filas_validas": calidad["filas_validas"],
                "exclusiones": calidad["exclusiones"], "alertas": list(res.alertas),
                "diagnostico": calidad_feed(res, filas, raiz),
                "rr25": {k: fila[k] for k in ("obs_rr25_estado", "obs_rr25", "obs_rr25_inferior", "obs_rr25_superior")},
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
            if figura is None and raiz == cfg_imp["raiz"]:
                cercano = min(elegidos, key=lambda v: abs(plazos[v] - piloto.objetivo_dias))
                figura = (cercano, plazos[cercano], medidas[cercano])
        raices[raiz] = {"vencimientos": por_venc, "plazo_constante_30d": constante,
                        "exclusiones_totales": dict(sum((Counter(x.get("exclusiones", {})) for x in por_venc.values()),
                                                        Counter())),
                        "filas_validas": int(sum(x.get("filas_validas", 0) for x in por_venc.values()))}
    niveles = {"spot_spx_implicito": {k: (str(v) if k in ("vencimiento", "sello_evento_utc") else v)
                                      for k, v in spot_spx.items()},
               "spot_spy_iex": spot_spy}
    if spot_spx.get("estado") == "identificado" and np.isfinite(spot_spy):
        niveles["razon_spx_spy"] = spot_spx["spot"] / spot_spy
    return raices, niveles, figura


def diagnosticar(datos, fecha, cfg_imp: dict, piloto: ConfigPiloto, cierre_descriptivo=False, codigo=CALENDARIO):
    """Diagnóstico de todas las capturas de una fecha: ``(informe, figura)``.

    Para cada captura, ``elegibilidad`` sale siempre de los controles
    estrictos; ``raices`` y los niveles salen del modo descriptivo solo si se
    aplica (``descriptivo_cierre``), y si no, de los mismos controles estrictos.
    """
    fecha = _fecha(fecha)
    cot, sub, resumenes, manifiestos = alpaca.normalizar(datos, fecha, fecha)
    informe, figura = {"fecha": str(fecha), "capturas": []}, None
    for m, resumen in zip(manifiestos, resumenes):
        corte = pd.Timestamp(m["corte_utc"])
        filas_m = cot[cot["captura"] == m["etiqueta"]]
        sub_m = sub[sub["captura"] == m["etiqueta"]]
        estricto, niveles_estrictos, fig_estricta = medir_captura(filas_m, sub_m, m["fecha"], corte, cfg_imp, piloto)
        descriptivo, motivo = modo_descriptivo(m, cierre_descriptivo, codigo)
        if descriptivo:
            relajadas = filas_m.drop(columns=["sello_snapshot_utc", "disponible_utc"])
            raices, niveles, fig = medir_captura(relajadas, sub_m, m["fecha"], corte, cfg_imp, piloto)
        else:
            raices, niveles, fig = estricto, niveles_estrictos, fig_estricta
        figura = figura or fig
        pags = [p for e in m["solicitudes"].values() if e["tipo"] in ("cadena", "acciones") for p in e["paginas"]]
        informe["capturas"].append({
            "etiqueta": m["etiqueta"], "modo": m.get("modo"), "hora": m["hora"], "corte_utc": m["corte_utc"],
            "estado": alpaca.estado_manifiesto(m), "feed_opciones": m.get("feed_opciones"), "cuenta": m.get("cuenta"),
            "desfase_reloj_s": m.get("reloj", {}).get("desfase_s"),
            "duracion_s": (pd.Timestamp(m["fin_utc"]) - pd.Timestamp(m["inicio_utc"])).total_seconds(),
            "respuestas": len(pags), "bytes": int(sum(p.get("bytes_contenido", p["bytes"]) for p in pags)),
            "errores": len(m["errores"]), "respuestas_despues_del_corte": len(m["respuestas_despues_del_corte"]),
            "cobertura": resumen,
            "elegibilidad": {"filas": int(len(filas_m)),
                             "filas_validas_al_corte": int(sum(r["filas_validas"] for r in estricto.values())),
                             "por_raiz": {r: v["filas_validas"] for r, v in estricto.items()},
                             "nivel_implicito": niveles_estrictos["spot_spx_implicito"].get("estado")},
            "descriptivo_cierre": descriptivo, "motivo_modo": motivo, **niveles, "raices": raices,
        })
    return informe, figura
