"""Piloto de medición en sesiones de apertura a plazo constante.

Para cada sesión y hora de corte (la principal y una secundaria solo de diagnóstico):

1. se eligen los vencimientos que encierran el plazo objetivo (días naturales
   hasta el instante contractual de liquidación) o la sesión queda «no
   disponible» con su motivo;
2. cada vencimiento pasa por controles, paridad, volatilidades y asimetrías
   (serie observada de ``cadenas``);
3. RR25 y la asimetría a distancia logarítmica se interpolan a plazo constante
   en varianza total, pata por pata, con bandas que salen de bid y ask;
4. la tabla diaria añade el cambio respecto de la sesión anterior del
   calendario (misma hora y plazo), el movimiento ya observado del subyacente,
   la estabilidad entre horas y etiquetas de 1 y 5 sesiones;
5. el dictamen resume, con criterios verificables, si los datos permiten
   ampliar la historia.

Una medida no identificada queda ausente con su motivo; nunca se rellena. El
piloto valida medición e ingestión: no evalúa capacidad predictiva.

Tres papeles, sin mezclarlos:

* **Señal**: las opciones (``raiz``), con su fuente explícita.
* **Referencia de las opciones** (``subyacente``): el precio que usan los
  controles y las medidas de la cadena. Se toma con la regla **puntual**:
  disponible al corte y no desfasado. En Alpaca es el nivel de SPX inferido
  por paridad, identificado como ``implicito``.
* **Objetivo** (``[objetivo]``): el precio cuyo rendimiento se etiqueta. Debe ser
  observado, no construido con las cotizaciones de las opciones, y se toma con
  la regla **histórica**: el precio vigente en el corte, aunque se publique
  después (SIP con 15 minutos de retraso). Su publicación fija la madurez de
  la etiqueta; nunca entra en una medida del corte. Añadir el objetivo no cambia
  ninguna medida de las opciones.

La referencia también da etiquetas auxiliares (``*_referencia``) y el
movimiento previo, ambos con la regla puntual; son diagnóstico de medición, no
confirmación independiente de una predicción.

Fuentes. Cada serie usa fuentes elegidas de forma explícita cuando hay más de
una (``proveedor/feed``): las opciones de una sesión vienen de una sola fuente,
y la referencia y el objetivo de una sola fuente cada uno en toda la corrida.
Cada fila guarda su procedencia; el cambio diario queda ausente cuando cambia el
segmento de medición (fuente y versión de la configuración).
"""
from __future__ import annotations

import tomllib
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import cadenas, contrato
from .almacen import huella_datos
from .calendario import _fecha, es_sesion, instante, instante_liquidacion, plazo_anios, sesion_desplazada
from .etiquetas import _consultas as _consultas_dividendos
from .etiquetas import etiquetas_retorno, etiquetas_vigentes, movimiento_previo

NAN = float("nan")
PROVEEDORES_SINTETICOS = ("sintetico",)  # generador de quantileflow/sintetico.py


@dataclass(frozen=True)
class ConfigPiloto:
    """Configuración versionada del piloto (ver ``configs/piloto.toml``)."""

    version: str
    raiz: str
    subyacente: str
    ejercicio: str
    liquidacion: str
    calendario: str
    hora_principal: str
    hora_secundaria: str | None
    objetivo_dias: float
    minimo_dias: float
    separacion_maxima_dias: float
    base_dias: float
    delta: float
    factor_strike: float
    hueco_max_k: float
    hueco_max_delta: float
    horizontes: tuple
    latencia_s: float
    retraso_publicacion_s: float
    tasa: float
    rendimiento_dividendo: float
    reglas: cadenas.ReglasCalidad
    dictamen: dict
    feeds_indicativos: tuple
    edad_maxima_precio_s: float
    objetivo_simbolo: str
    objetivo_tipo: str
    objetivo_edad_maxima_s: float
    objetivo_spread_max: float
    objetivo_retraso_s: float
    objetivo_rendimiento: str
    objetivo_margen_proceso_dias: float
    fuente: dict
    huella: str

    @property
    def horas(self):
        return (self.hora_principal,) + ((self.hora_secundaria,) if self.hora_secundaria else ())


def config_desde_dict(d: dict) -> ConfigPiloto:
    c = d["calidad"]
    reglas = cadenas.ReglasCalidad(
        margen_apertura=float(c["margen_apertura_s"]), edad_maxima=float(c["edad_maxima_s"]),
        desfase_spot_max=float(c["desfase_spot_max_s"]), spread_relativo_max=float(c["spread_relativo_max"]),
        spread_ticks_tolerados=float(c["spread_ticks_tolerados"]), tamano_minimo=float(c["tamano_minimo"]),
        tick_bajo=float(c["tick_bajo"]), tick_alto=float(c["tick_alto"]), umbral_tick=float(c["umbral_tick"]))
    return ConfigPiloto(
        version=d["piloto"]["version"], raiz=d["instrumento"]["raiz"],
        subyacente=d["instrumento"]["subyacente"], ejercicio=d["instrumento"]["ejercicio"],
        liquidacion=d["instrumento"]["liquidacion"], calendario=d["instrumento"]["calendario"],
        hora_principal=d["horario"]["principal"], hora_secundaria=d["horario"].get("secundaria"),
        objetivo_dias=float(d["plazo"]["objetivo_dias"]), minimo_dias=float(d["plazo"]["minimo_dias"]),
        separacion_maxima_dias=float(d["plazo"]["separacion_maxima_dias"]),
        base_dias=float(d["plazo"]["base_dias_anio"]), delta=float(d["senales"]["delta"]),
        factor_strike=float(d["senales"]["factor_strike"]), hueco_max_k=float(d["senales"]["hueco_max_k"]),
        hueco_max_delta=float(d["senales"]["hueco_max_delta_k"]),
        horizontes=tuple(int(h) for h in d["etiquetas"]["horizontes"]),
        latencia_s=float(d["etiquetas"]["latencia_s"]),
        retraso_publicacion_s=float(d["etiquetas"]["retraso_publicacion_s"]),
        tasa=float(d["referencia"]["tasa"]), rendimiento_dividendo=float(d["referencia"]["rendimiento_dividendo"]),
        reglas=reglas, dictamen=dict(d["dictamen"]), feeds_indicativos=tuple(d["fuente"]["feeds_indicativos"]),
        edad_maxima_precio_s=float(d["etiquetas"]["edad_maxima_precio_s"]),
        objetivo_simbolo=d["objetivo"]["simbolo"], objetivo_tipo=d["objetivo"]["tipo_precio"],
        objetivo_edad_maxima_s=float(d["objetivo"]["edad_maxima_s"]),
        objetivo_spread_max=float(d["objetivo"]["spread_relativo_max"]),
        objetivo_retraso_s=float(d["objetivo"]["retraso_publicacion_s"]),
        objetivo_rendimiento=_rendimiento(d["objetivo"]["rendimiento"]),
        objetivo_margen_proceso_dias=float(d["objetivo"]["margen_proceso_dias"]), fuente=d, huella=huella_datos(d))


def _rendimiento(valor):
    if valor not in ("total", "precio"):
        raise ValueError(f"[objetivo] rendimiento debe ser total o precio, no {valor!r}")
    return valor


def cargar_config(ruta) -> ConfigPiloto:
    with open(ruta, "rb") as f:
        return config_desde_dict(tomllib.load(f))


# ---------------------------------------------------------------------------
# Plazo constante
# ---------------------------------------------------------------------------


def elegir_vencimientos(plazos_dias: dict, cfg: ConfigPiloto):
    """Vencimientos que encierran el objetivo (o el que coincide) y motivo si no hay."""
    validos = sorted((d, v) for v, d in plazos_dias.items() if d >= cfg.minimo_dias)
    iguales = [v for d, v in validos if abs(d - cfg.objetivo_dias) < 1e-9]
    if iguales:
        return [iguales[0]], ""
    antes = [(d, v) for d, v in validos if d < cfg.objetivo_dias]
    despues = [(d, v) for d, v in validos if d > cfg.objetivo_dias]
    if not antes or not despues:
        return [], f"no hay vencimientos a ambos lados de {cfg.objetivo_dias:g} días"
    (d1, v1), (d2, v2) = antes[-1], despues[0]
    if d2 - d1 > cfg.separacion_maxima_dias:
        return [], f"vencimientos a {d1:.1f} y {d2:.1f} días: separación mayor que {cfg.separacion_maxima_dias:g}"
    return [v1, v2], ""


def interpolar_varianza_total(T1, s1, T2, s2, T):
    """Volatilidad en ``T`` interpolando linealmente la varianza total ``s^2 T`` entre dos plazos."""
    if T2 == T1:
        return s1
    w = s1**2 * T1 + (s2**2 * T2 - s1**2 * T1) * (T - T1) / (T2 - T1)
    return float(np.sqrt(w / T)) if w > 0 else NAN


def plazo_constante(medidas, plazos, T, base_dias=365.0):
    """Medida call - put a plazo ``T`` a partir de una o dos medidas por vencimiento.

    Cada medida trae ``iv_call``, ``iv_put`` y sus bandas; se interpola cada pata
    (mid, bid y ask) y la banda final es ``[call_bid - put_ask, call_ask - put_bid]``.
    Si una pata tiene varianza total claramente decreciente entre vencimientos
    (el ask del largo por debajo del bid del corto) la interpolación no se hace.
    """
    for m, T_i in zip(medidas, plazos):
        if m.get("estado") != "identificada":
            return {"estado": "no identificada",
                    "motivo": f"vencimiento a {T_i * base_dias:.1f} días: {m.get('motivo', '')}"}
    patas = {}
    for pata in ("call", "put"):
        mid = [m[f"iv_{pata}"] for m in medidas]
        bid = [m[f"iv_{pata}_banda"][0] for m in medidas]
        ask = [m[f"iv_{pata}_banda"][1] for m in medidas]
        if len(medidas) == 1:
            patas[pata] = (mid[0], bid[0], ask[0])
            continue
        (T1, T2) = plazos
        if ask[1] ** 2 * T2 < bid[0] ** 2 * T1:
            return {"estado": "no identificada",
                    "motivo": f"varianza total decreciente entre vencimientos en la pata {pata}"}
        patas[pata] = tuple(interpolar_varianza_total(T1, x[0], T2, x[1], T) for x in (mid, bid, ask))
    (sc, bc, ac), (sp, bp, ap) = patas["call"], patas["put"]
    return {"estado": "identificada", "motivo": "", "valor": sc - sp, "inferior": bc - ap, "superior": ac - bp,
            "iv_call": sc, "iv_put": sp}


# ---------------------------------------------------------------------------
# Medición de una sesión
# ---------------------------------------------------------------------------


def _vacia(fecha, hora):
    return {"fecha": _fecha(fecha), "hora": hora, "estado_sesion": "no disponible", "motivo_sesion": "",
            "fuente_opciones": "", "fuente_referencia": "", "tipo_precio_referencia": "", "segmento": "",
            "vencimiento_1": None, "dias_1": NAN, "vencimiento_2": None, "dias_2": NAN, "spot": NAN,
            "forward": NAN, "forward_error": NAN, "tasa_implicita": NAN, "forward_menos_contractual": NAN,
            "log_forward_spot": NAN, "rr25_estado": "no identificada", "rr25": NAN, "rr25_inferior": NAN,
            "rr25_superior": NAN, "rr25_motivo": "", "asim_log_estado": "no identificada", "asim_log": NAN,
            "asim_log_inferior": NAN, "asim_log_superior": NAN, "asim_log_motivo": "",
            "paridad_pares": 0, "paridad_fuera_de_banda": 0, "paridad_interpretables": 0,
            "paridad_mediana_multiplo": NAN, "filas": 0, "filas_validas": 0, "filas_solo_cota": 0,
            "exclusiones": "", "ancho_ticks_mediano": NAN, "edad_mediana_s": NAN, "desfase_spot_s": NAN,
            "n_alertas": 0, "alertas": ""}


def medir(cotizaciones, referencia, fecha, hora, cfg: ConfigPiloto, fuente_referencia=None):
    """Fila de una sesión y hora, y el detalle por vencimiento (capturas y resultados).

    ``referencia`` es la tabla del subyacente de las opciones (regla puntual).
    """
    fila, detalle = _vacia(fecha, hora), {}
    corte = instante(fecha, hora, cfg.calendario)
    sesion = contrato._del_dia_hasta(cotizaciones[cotizaciones["raiz"] == cfg.raiz], fecha, corte)
    fuentes = sorted(set(contrato.fuente(sesion))) if len(sesion) else []
    if len(fuentes) > 1:
        fila["motivo_sesion"] = f"varias fuentes de cotizaciones en la sesión ({', '.join(fuentes)}): no se mezclan"
        return fila, detalle
    if fuentes:
        fila.update(fuente_opciones=fuentes[0], segmento=f"{fuentes[0]}|{cfg.version}")
    plazos = {}
    for v in contrato.vencimientos(cotizaciones, cfg.raiz, fecha, hora):
        if es_sesion(v, cfg.calendario):
            liquida = instante_liquidacion(v, cfg.liquidacion, cfg.calendario)
            plazos[v] = plazo_anios(corte, liquida, cfg.base_dias) * cfg.base_dias
    elegidos, motivo = elegir_vencimientos(plazos, cfg)
    if not elegidos:
        fila["motivo_sesion"] = motivo
        return fila, detalle
    for v in elegidos:
        try:
            cap, info = contrato.captura_desde_tabla(
                cotizaciones, referencia, cfg.raiz, v, fecha, hora, cfg.tasa, cfg.rendimiento_dividendo,
                base_dias=cfg.base_dias, codigo=cfg.calendario, fuente_subyacente=fuente_referencia)
        except contrato.SinDatos as error:
            fila["motivo_sesion"] = str(error)
            return fila, {}
        if cap.ejercicio != cfg.ejercicio or info["liquidacion"] != cfg.liquidacion:
            raise ValueError(f"{v}: ejercicio o liquidación distintos de la configuración")
        res = cadenas.procesar_captura(cap, cfg.reglas, distancia=cfg.factor_strike - 1.0, delta=cfg.delta,
                                       hueco_max=cfg.hueco_max_k, hueco_max_delta=cfg.hueco_max_delta)
        detalle[v] = {"captura": cap, "info": info, "resultado": res,
                      "calidad": cadenas.metricas_calidad(res, cfg.reglas)}
    T = cfg.objetivo_dias / cfg.base_dias
    plazos_T = [detalle[v]["info"]["T"] for v in elegidos]
    for nombre, clave in (("rr25", "asimetria_delta"), ("asim_log", "asimetria")):
        m = plazo_constante([getattr(detalle[v]["resultado"], clave) for v in elegidos], plazos_T, T,
                            cfg.base_dias)
        fila[f"{nombre}_estado"], fila[f"{nombre}_motivo"] = m["estado"], m["motivo"]
        if m["estado"] == "identificada":
            fila[nombre], fila[f"{nombre}_inferior"], fila[f"{nombre}_superior"] = (
                m["valor"], m["inferior"], m["superior"])
    for i, v in enumerate(elegidos, start=1):
        fila[f"vencimiento_{i}"], fila[f"dias_{i}"] = v, plazos[v]
    cercano = min(elegidos, key=lambda v: abs(plazos[v] - cfg.objetivo_dias))
    obs = cadenas.fila_informe(detalle[cercano]["resultado"])
    info = detalle[cercano]["info"]
    fila.update(fuente_referencia=info["fuente_subyacente"], tipo_precio_referencia=info["tipo_precio_subyacente"])
    fila.update(estado_sesion="procesada", spot=detalle[cercano]["captura"].spot, forward=obs["obs_forward"],
                forward_error=obs["obs_forward_error"], tasa_implicita=obs["obs_tasa_implicita"],
                forward_menos_contractual=obs["obs_forward_menos_contractual"],
                log_forward_spot=obs["obs_log_forward_spot"])
    calidades = [detalle[v]["calidad"] for v in elegidos]
    exclusiones = Counter()
    for c in calidades:
        exclusiones.update(c["exclusiones"])
    multiplos = np.concatenate([np.abs(detalle[v]["resultado"].paridad.multiplo_ancho) for v in elegidos])
    alertas = sorted({f"{v}: {a}" for v in elegidos for a in detalle[v]["resultado"].alertas})
    fila.update(
        paridad_pares=sum(c["pares_completos"] for c in calidades),
        paridad_fuera_de_banda=sum(int(detalle[v]["resultado"].paridad.fuera_de_banda.sum()) for v in elegidos),
        paridad_interpretables=sum(int(detalle[v]["resultado"].paridad.interpretable.sum()) for v in elegidos),
        paridad_mediana_multiplo=float(np.nanmedian(multiplos)) if np.any(np.isfinite(multiplos)) else NAN,
        filas=sum(c["filas"] for c in calidades), filas_validas=sum(c["filas_validas"] for c in calidades),
        filas_solo_cota=sum(c["filas_solo_cota"] for c in calidades),
        exclusiones="; ".join(f"{k}={n}" for k, n in sorted(exclusiones.items())),
        ancho_ticks_mediano=float(np.nanmean([c["ancho_ticks_mediano"] for c in calidades])),
        edad_mediana_s=float(np.nanmean([c["edad_mediana_s"] for c in calidades]))
        if any(np.isfinite(c["edad_mediana_s"]) for c in calidades) else NAN,
        desfase_spot_s=calidades[0]["desfase_spot_s"], n_alertas=len(alertas), alertas=" | ".join(alertas))
    return fila, detalle


# ---------------------------------------------------------------------------
# Tabla diaria, etiquetas y dictamen
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class ResultadoPiloto:
    principal: pd.DataFrame  # una fila por sesión a la hora principal
    completa: pd.DataFrame  # todas las horas
    etiquetas: pd.DataFrame
    detalles: dict  # (fecha, hora) -> vencimiento -> captura, resultado y calidad
    dictamen: dict
    config: ConfigPiloto


def _cambios(principal: pd.DataFrame, cfg: ConfigPiloto) -> pd.DataFrame:
    por_fecha = principal.set_index("fecha")
    extra = {c: [] for c in ("dias_naturales_desde_anterior", "cambio_rr25", "cambio_rr25_inferior",
                             "cambio_rr25_superior", "cambio_rr25_motivo", "cambio_asim_log")}
    for fecha in principal["fecha"]:
        previa = sesion_desplazada(fecha, -1, cfg.calendario)
        extra["dias_naturales_desde_anterior"].append((fecha - previa).days)
        if previa not in por_fecha.index:
            valores, motivo = (NAN,) * 4, "sesión anterior fuera de la muestra"
        else:
            a, b = por_fecha.loc[fecha], por_fecha.loc[previa]
            if a["segmento"] and b["segmento"] and a["segmento"] != b["segmento"]:
                # Una diferencia de medición entre fuentes no es un cambio económico.
                valores = (NAN,) * 4
                motivo = f"cambio de segmento de medición: {b['segmento']} -> {a['segmento']}"
            elif a["rr25_estado"] == b["rr25_estado"] == "identificada":
                valores = (a["rr25"] - b["rr25"], a["rr25_inferior"] - b["rr25_superior"],
                           a["rr25_superior"] - b["rr25_inferior"],
                           a["asim_log"] - b["asim_log"] if a["asim_log_estado"] == b["asim_log_estado"]
                           == "identificada" else NAN)
                motivo = ""
            else:
                valores, motivo = (NAN,) * 4, "RR25 no identificada hoy o en la sesión anterior"
        for clave, valor in zip(("cambio_rr25", "cambio_rr25_inferior", "cambio_rr25_superior",
                                 "cambio_asim_log"), valores):
            extra[clave].append(valor)
        extra["cambio_rr25_motivo"].append(motivo)
    return principal.assign(**extra)


def _candidatas(tabla, fechas, cfg: ConfigPiloto):
    """Sesiones de la muestra y posteriores con filas en ``tabla`` (para madurar etiquetas)."""
    locales = tabla["sello_snapshot_utc"].dt.tz_convert("America/New_York").dt.date if len(tabla) else []
    return sorted({d for d in set(locales) if d >= min(fechas) and es_sesion(d, cfg.calendario)} | set(fechas))


def _precios_referencia(referencia, fechas, cfg: ConfigPiloto, fuente_referencia=None) -> pd.DataFrame:
    """Precio de referencia a la hora principal con la regla **puntual** (señales y etiquetas auxiliares).

    Solo cuenta un precio disponible al corte y con una antigüedad no mayor que
    ``edad_maxima_precio_s``; si no, queda NaN con su motivo.
    """
    filas = {}
    for d in _candidatas(referencia, fechas, cfg):
        corte = instante(d, cfg.hora_principal, cfg.calendario)
        try:
            info = contrato.precio_al_corte(referencia, cfg.subyacente, d, corte, fuente_referencia)
        except contrato.SinDatos as error:
            filas[d] = {"precio": NAN, "disponible_utc": pd.NaT, "motivo": str(error)}
            continue
        edad = (corte - info["sello_utc"]).total_seconds()
        if edad > cfg.edad_maxima_precio_s:
            filas[d] = {"precio": NAN, "disponible_utc": pd.NaT,
                        "motivo": f"precio de {cfg.subyacente} desfasado {edad:.0f} s al corte de {d}"}
            continue
        filas[d] = {"precio": info["precio"], "disponible_utc": info["disponible_utc"], "motivo": ""}
    return pd.DataFrame.from_dict(filas, orient="index", columns=["precio", "disponible_utc", "motivo"])


def _precios_objetivo(objetivo, fechas, cfg: ConfigPiloto, fuente_objetivo=None) -> pd.DataFrame:
    """Precio objetivo a la hora principal con la regla **histórica** (``contrato.precio_para_etiqueta``).

    Su disponibilidad (quizá posterior al corte) solo fija la madurez de la etiqueta.
    """
    filas = {}
    for d in _candidatas(objetivo, fechas, cfg):
        corte = instante(d, cfg.hora_principal, cfg.calendario)
        try:
            info = contrato.precio_para_etiqueta(objetivo, cfg.objetivo_simbolo, d, corte, fuente_objetivo,
                                                 cfg.objetivo_edad_maxima_s, cfg.objetivo_spread_max)
        except contrato.SinDatos as error:
            filas[d] = {"precio": NAN, "disponible_utc": pd.NaT, "motivo": str(error)}
            continue
        filas[d] = {"precio": info["precio"], "disponible_utc": info["disponible_utc"], "motivo": ""}
    return pd.DataFrame.from_dict(filas, orient="index", columns=["precio", "disponible_utc", "motivo"])


def dictamen(principal: pd.DataFrame, cfg: ConfigPiloto) -> dict:
    """Veredicto sobre los datos con criterios verificables (umbrales de la configuración)."""
    u = cfg.dictamen
    n = len(principal)
    fraccion_rr = float((principal["rr25_estado"] == "identificada").mean()) if n else 0.0
    fraccion_cambio = float(principal["cambio_rr25"].notna().iloc[1:].mean()) if n > 1 else 0.0
    ancho = (principal["rr25_superior"] - principal["rr25_inferior"]).median()
    if "dif_rr25_secundaria" in principal and principal["dif_rr25_secundaria"].notna().any() and ancho > 0:
        estabilidad = float(principal["dif_rr25_secundaria"].abs().median() / ancho)
    else:
        estabilidad = NAN
    alertas = float((principal["n_alertas"] > 0).mean()) if n else 0.0
    etiquetas = float((principal["estado_ret_1_objetivo"] == "ok").mean()) if n else 0.0

    def criterio(nombre, valor, umbral, cumple, critico):
        return {"criterio": nombre, "valor": valor, "umbral": umbral, "cumple": bool(cumple),
                "critico": bool(critico and not cumple)}

    criterios = [
        criterio("Sesiones en la muestra", n, f">= {u['min_sesiones']}", n >= u["min_sesiones"], True),
        criterio("RR25 a 30 días identificada a la hora principal", fraccion_rr, f">= {u['rr25_apto']}",
                 fraccion_rr >= u["rr25_apto"], fraccion_rr < u["rr25_minimo"]),
        criterio("Cambio diario de RR25 disponible", fraccion_cambio, f">= {u['cambio_rr25_minimo']}",
                 fraccion_cambio >= u["cambio_rr25_minimo"], False),
        criterio("Estabilidad 09:45-10:00 (mediana de la diferencia absoluta / ancho de banda)", estabilidad,
                 f"<= {u['estabilidad_max']}", np.isfinite(estabilidad) and estabilidad <= u["estabilidad_max"],
                 False),
        criterio("Sesiones con alertas de sincronía, edad o disponibilidad", alertas, f"<= {u['alertas_max']}",
                 alertas <= u["alertas_max"], False),
        criterio("Etiqueta del objetivo a 1 sesión disponible", etiquetas, f">= {u['etiquetas_min']}",
                 etiquetas >= u["etiquetas_min"], True),
    ]
    if any(c["critico"] for c in criterios):
        veredicto = "insuficiente"
    elif all(c["cumple"] for c in criterios):
        veredicto = "apto para ampliar historia"
    else:
        veredicto = "apto con limitaciones"
    return {"veredicto": veredicto, "criterios": criterios}


def _elegir_fuentes(tabla, nombre, elegidas):
    """Filas de las fuentes elegidas; sin elección, exige que haya una sola."""
    presentes = sorted(set(contrato.fuente(tabla))) if len(tabla) else []
    if elegidas is None:
        if len(presentes) > 1:
            raise ValueError(f"{nombre}: hay varias fuentes ({', '.join(presentes)}); "
                             "elija explícitamente cuáles usar")
        return tabla, tuple(presentes)
    elegidas = tuple(elegidas)
    if presentes and not set(elegidas) & set(presentes):
        raise ValueError(f"{nombre}: ninguna fuente elegida está en los datos ({', '.join(presentes)})")
    return tabla[contrato.fuente(tabla).isin(elegidas)], elegidas


def alcance(fuentes_opciones, fuente_referencia, tipo_referencia, fuente_objetivo, tipo_objetivo,
            cfg: ConfigPiloto, cobertura=None) -> dict:
    """Qué permite concluir la muestra según sus fuentes, aparte de la aptitud de los datos.

    ``cobertura``: consultas de dividendos del objetivo (``contrato.COBERTURA_DIVIDENDOS``).
    """
    indicativas = [f for f in fuentes_opciones if f.split("/", 1)[-1] in cfg.feeds_indicativos]
    sinteticas = [f for f in (*fuentes_opciones, fuente_referencia or "", fuente_objetivo or "")
                  if f.split("/", 1)[0] in PROVEEDORES_SINTETICOS]
    motivos = []
    if sinteticas:
        motivos.append("datos sintéticos")
    if indicativas:
        motivos.append("cotizaciones indicativas, modificadas por el proveedor (" + ", ".join(indicativas) + ")")
    if not fuente_objetivo:
        motivos.append("sin precio objetivo")
    elif tipo_objetivo != "observado":
        motivos.append("precio objetivo inferido de las mismas opciones: no es independiente de las señales")
    tipos = {"observado": "observado", "implicito": "inferido por paridad de las opciones"}
    otro = cfg.objetivo_simbolo != cfg.subyacente
    # Solo cuentan las consultas que pueden confirmar dividendos (las mismas que usan las etiquetas).
    validas, descartadas = _consultas_dividendos(cobertura, None) if cobertura is not None else ([], {})
    no_cuentan = "".join(f"; {n} consultas {razon} no cuentan" for razon, n in sorted(descartadas.items()))
    if cfg.objetivo_rendimiento == "precio":
        dividendos = "no se usan: rendimiento de precio"
    elif not validas:
        dividendos = ("sin consulta completa que pueda confirmar dividendos: el rendimiento total queda ausente"
                      + no_cuentan)
    else:
        dividendos = (f"{len(validas)} consultas completas que pueden confirmar dividendos, la última recibida el "
                      f"{validas[-1].recibido.isoformat()}{no_cuentan}. Cada etiqueta madura con la primera "
                      "posterior a su fin que cubre el periodo (provisional). Queda aceptada bajo la política de "
                      f"{cfg.objetivo_margen_proceso_dias:g} días (una regla, no una garantía de completitud) con "
                      "una recibida después de ese margen, del último cambio de valor y de la última discrepancia "
                      "resuelta, sin discrepancias abiertas. Con una discrepancia sin resolver (un dividendo "
                      "ausente en una consulta comparable, uno cancelado por una resolución que el proveedor "
                      "vuelve a traer con otros valores, o uno recibido sin fecha ex o sin monto que podría caer "
                      "en el periodo) queda pendiente: solo la resuelve evidencia fechada")
    return {
        "fuentes_opciones": list(fuentes_opciones), "fuente_referencia": fuente_referencia or "",
        "tipo_precio_referencia": tipo_referencia or "", "simbolo_objetivo": cfg.objetivo_simbolo,
        "fuente_objetivo": fuente_objetivo or "", "tipo_precio_objetivo": tipo_objetivo or "",
        "medicion": "sintética" if sinteticas else ("indicativa" if indicativas
                                                    else "cotizaciones sin modificar según el proveedor"),
        "referencia_opciones": tipos.get(tipo_referencia, "sin precio"),
        "precio_objetivo": tipos.get(tipo_objetivo, "sin precio"),
        "instrumento_objetivo": (f"{cfg.objetivo_simbolo}, distinto de {cfg.subyacente}: otro instrumento, con sus "
                                 "dividendos, gastos y diferencias de seguimiento" if otro else cfg.subyacente),
        "rendimiento_objetivo": ("total: dividendos en efectivo sumados en su fecha ex; el de precio va aparte"
                                 if cfg.objetivo_rendimiento == "total" else "de precio, sin dividendos"),
        "dividendos_objetivo": dividendos,
        "evaluacion_con_precios_de_mercado": "permitida" if not motivos else "no permitida: " + "; ".join(motivos),
    }


def ejecutar(cotizaciones: pd.DataFrame, subyacente: pd.DataFrame, fechas, cfg: ConfigPiloto,
             fuentes_opciones=None, fuente_referencia=None, fuente_objetivo=None,
             dividendos: pd.DataFrame | None = None, cobertura: pd.DataFrame | None = None) -> ResultadoPiloto:
    """Mide todas las sesiones y horas, añade cambios, estabilidad y etiquetas, y dictamina.

    ``subyacente`` trae la referencia de las opciones (``cfg.subyacente``) y el
    objetivo (``cfg.objetivo_simbolo``). ``fuentes_opciones`` (una o varias),
    ``fuente_referencia`` y ``fuente_objetivo`` (``proveedor/feed``) son
    obligatorias cuando los datos traen más de una fuente para esa serie.
    ``dividendos`` (versiones, ``contrato.DIVIDENDOS``) y ``cobertura``
    (consultas, ``contrato.COBERTURA_DIVIDENDOS``) sirven al rendimiento total
    del objetivo, con la política de ``etiquetas``: sin una consulta completa
    posterior al fin que cubra el periodo, queda ausente con su motivo; el de
    precio se calcula igual.
    """
    fechas = sorted({_fecha(f) for f in fechas})
    no_sesiones = [f for f in fechas if not es_sesion(f, cfg.calendario)]
    if no_sesiones:
        raise ValueError(f"fechas que no son sesiones: {no_sesiones}")
    cotizaciones, fuentes_op = _elegir_fuentes(cotizaciones[cotizaciones["raiz"] == cfg.raiz],
                                               f"opciones {cfg.raiz}", fuentes_opciones)
    referencia, fuentes_ref = _elegir_fuentes(
        subyacente[subyacente["subyacente"] == cfg.subyacente], f"referencia {cfg.subyacente}",
        None if fuente_referencia is None else (fuente_referencia,))
    objetivo, fuentes_obj = _elegir_fuentes(
        subyacente[subyacente["subyacente"] == cfg.objetivo_simbolo], f"objetivo {cfg.objetivo_simbolo}",
        None if fuente_objetivo is None else (fuente_objetivo,))
    fuente_ref = fuentes_ref[0] if fuentes_ref else None
    fuente_obj = fuentes_obj[0] if fuentes_obj else None
    tipo_ref = "|".join(sorted(set(referencia["tipo_precio"]))) if len(referencia) else ""
    tipo_obj = "|".join(sorted(set(objetivo["tipo_precio"]))) if len(objetivo) else ""
    if tipo_obj and tipo_obj != cfg.objetivo_tipo:
        raise ValueError(f"el objetivo {cfg.objetivo_simbolo} debe ser {cfg.objetivo_tipo}; "
                         f"la fuente {fuente_obj} da precios {tipo_obj}")
    filas, detalles = [], {}
    for fecha in fechas:
        for hora in cfg.horas:
            fila, detalle = medir(cotizaciones, referencia, fecha, hora, cfg, fuente_ref)
            filas.append(fila)
            detalles[(fecha, hora)] = detalle
    completa = pd.DataFrame(filas)
    principal = completa[completa["hora"] == cfg.hora_principal].reset_index(drop=True)
    principal = _cambios(principal, cfg)
    if cfg.hora_secundaria:
        secundaria = completa[completa["hora"] == cfg.hora_secundaria].set_index("fecha")["rr25"]
        principal["rr25_secundaria"] = principal["fecha"].map(secundaria)
        principal["dif_rr25_secundaria"] = principal["rr25_secundaria"] - principal["rr25"]
    total = cfg.objetivo_rendimiento == "total"
    divs = dividendos if dividendos is not None else pd.DataFrame(columns=list(contrato.DIVIDENDOS))
    cob = cobertura if cobertura is not None else pd.DataFrame(columns=list(contrato.COBERTURA_DIVIDENDOS))
    divs_obj = divs[divs["simbolo"] == cfg.objetivo_simbolo] if total else None
    cob_obj = cob[cob["simbolo"] == cfg.objetivo_simbolo] if total else None
    series = []
    for serie, precios, simbolo, fuente, tipo, retraso, pagos, consultas in (
            ("objetivo", _precios_objetivo(objetivo, fechas, cfg, fuente_obj), cfg.objetivo_simbolo, fuente_obj,
             tipo_obj, max(cfg.retraso_publicacion_s, cfg.objetivo_retraso_s), divs_obj, cob_obj),
            ("referencia", _precios_referencia(referencia, fechas, cfg, fuente_ref), cfg.subyacente, fuente_ref,
             tipo_ref, cfg.retraso_publicacion_s, None, None)):
        # El retraso del objetivo es un piso: una etiqueta ausente tampoco se conoce antes de la publicación.
        # La referencia es un índice de precio: sin dividendos.
        e = etiquetas_retorno(precios["precio"], cfg.hora_principal, cfg.horizontes, cfg.latencia_s, retraso,
                              cfg.calendario, disponibles=precios["disponible_utc"], motivos=precios["motivo"],
                              dividendos=pagos, cobertura=consultas,
                              margen_proceso_dias=cfg.objetivo_margen_proceso_dias)
        series.append(e.assign(serie=serie, simbolo=simbolo, fuente=fuente or "", tipo_precio=tipo))
        vigentes = etiquetas_vigentes(e)
        for h in cfg.horizontes:
            eh = vigentes[vigentes["horizonte"] == h].set_index("sesion")
            principal[f"ret_{h}_{serie}"] = principal["fecha"].map(eh["retorno_log"])
            if serie == "objetivo":
                principal[f"ret_precio_{h}_{serie}"] = principal["fecha"].map(eh["retorno_precio_log"])
                principal[f"div_{h}_{serie}"] = principal["fecha"].map(eh["dividendos"])
                principal[f"estado_div_{h}_{serie}"] = principal["fecha"].map(eh["estado_dividendos"])
                principal[f"version_{h}_{serie}"] = principal["fecha"].map(eh["version"])
            principal[f"estado_ret_{h}_{serie}"] = principal["fecha"].map(eh["estado"])
        if serie == "referencia":
            principal["retorno_previo_referencia"] = principal["fecha"].map(
                movimiento_previo(precios["precio"], cfg.calendario))
    etiquetas = pd.concat(series, ignore_index=True)
    principal["fuente_objetivo"], principal["tipo_precio_objetivo"] = fuente_obj or "", tipo_obj
    veredicto = dictamen(principal, cfg)
    veredicto["alcance"] = alcance(fuentes_op, fuente_ref, tipo_ref, fuente_obj, tipo_obj, cfg, cob_obj)
    h1 = cfg.horizontes[0]
    estados = principal.loc[principal[f"estado_ret_{h1}_objetivo"] == "ok", f"estado_div_{h1}_objetivo"]
    veredicto["alcance"]["estados_rendimiento_objetivo"] = {k: int((estados == k).sum())
                                                          for k in ("provisional", "aceptada", "pendiente")}
    revisadas = principal.loc[principal[f"estado_ret_{h1}_objetivo"] == "ok", f"version_{h1}_objetivo"]
    veredicto["alcance"]["revisadas_objetivo"] = int((revisadas > 1).sum())
    # La prueba de la política: etiquetas cuyo valor cambió después de haber quedado aceptadas.
    obj = etiquetas[(etiquetas["serie"] == "objetivo") & (etiquetas["horizonte"] == h1) & (etiquetas["estado"] == "ok")]
    aceptada = obj[obj["estado_dividendos"] == "aceptada"].groupby("sesion")["version"].min()
    ultima = obj.groupby("sesion")["version"].max()
    veredicto["alcance"]["revisadas_tras_aceptar_objetivo"] = int((ultima.reindex(aceptada.index) > aceptada).sum())
    return ResultadoPiloto(principal, completa, etiquetas, detalles, veredicto, cfg)
