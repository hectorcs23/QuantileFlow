"""Adaptador experimental de cadenas normalizadas al comparador europeo.

SPXW PM; separa entrenamiento ATM y validación por strike. La IV plana por
vencimiento es un baseline diagnóstico, no una superficie calibrada de mercado.
"""
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from . import cadenas, contrato
from .calendario import instante
from .escenarios import ContratoEscenario
from .opciones import vol_implicita_black


@dataclass(frozen=True)
class PreparacionComparador:
    spot: float
    candidatos: tuple
    calibraciones: dict
    calidad: dict
    evaluacion: pd.DataFrame  # filas individuales: conservar en privado
    bloqueos: tuple

    @property
    def apto_puntual(self):
        return not self.bloqueos


def preparar_comparador(cotizaciones, referencias, fecha, hora, reglas=cadenas.ReglasCalidad(),
                        *, tasa=.04, q=.013, modo_descriptivo=False, minimo_dias=1., maximo_dias=45.,
                        ancho_atm=.01, ancho_evaluacion=.03, minimo_entrenamiento=6,
                        objetivos_moneyness=(-.015, 0., .015)):
    """Una foto causal; no consulta proveedores ni usa el segundo corte al ajustar.

    Las cotizaciones indicativas y referencias implícitas bloquean el modo puntual.
    modo_descriptivo permite diagnosticar sin retirar esos bloqueos del resultado.
    Cada tercer strike es holdout para ambos lados; entrenamiento ATM en los otros.
    """
    if not all(math.isfinite(v) for v in (tasa, q, minimo_dias, maximo_dias, ancho_atm, ancho_evaluacion)):
        raise ValueError("parámetros no finitos")
    if not (0 < minimo_dias <= maximo_dias and 0 < ancho_atm <= ancho_evaluacion
            and isinstance(minimo_entrenamiento, int) and minimo_entrenamiento >= 2):
        raise ValueError("protocolo inválido")
    if not objetivos_moneyness or not all(math.isfinite(v) and abs(v) <= ancho_evaluacion for v in objetivos_moneyness):
        raise ValueError("objetivos de moneyness inválidos")
    corte = instante(fecha, hora)
    etiqueta = f"{fecha}T{hora.replace(':', '')}"
    filas = cotizaciones[(cotizaciones.captura == etiqueta) & (cotizaciones.raiz == "SPXW")].copy().reset_index(drop=True)
    refs = referencias[(referencias.captura == etiqueta) & (referencias.subyacente == "SPX")].copy()
    if filas.empty or len(refs) != 1:
        raise ValueError("requiere una cadena SPXW y una referencia SPX por corte")
    if contrato.validar(filas) or contrato.validar(refs, contrato.SUBYACENTE):
        raise ValueError("tablas incompatibles con contrato normalizado")
    if set(zip(filas.proveedor, filas.feed)) not in ({("alpaca", "indicative")}, {("alpaca", "opra")}):
        raise ValueError("feed desconocido o mezclado")
    if not filas.ejercicio.eq("europeo").all() or not filas.liquidacion.eq("PM").all():
        raise ValueError("solo SPXW europeo PM")
    if not filas.subyacente.eq("SPX").all():
        raise ValueError("subyacente incompatible")
    for col in ("sello_evento_utc", "sello_snapshot_utc", "disponible_utc", "recibido_utc"):
        if filas[col].isna().any() or (filas[col] > corte).any() or refs[col].isna().any() or (refs[col] > corte).any():
            raise ValueError("sello desconocido o posterior al corte")
    if filas.id_contrato.duplicated().any():
        raise ValueError("contratos duplicados en la foto")
    for col in ("strike", "bid", "ask", "tam_bid", "tam_ask", "multiplicador"):
        if not np.isfinite(filas[col]).all():
            raise ValueError("datos numéricos no finitos")
    if (filas.multiplicador <= 0).any() or (filas.multiplicador % 1 != 0).any():
        raise ValueError("multiplicador no entero positivo")
    ref = refs.iloc[0]
    if not math.isfinite(ref.precio) or ref.precio <= 0:
        raise ValueError("spot inválido")
    bloqueos = []
    if filas.feed.iloc[0] == "indicative":
        bloqueos.append("feed indicative: cotizaciones modificadas, no precios ejecutables")
    if ref.tipo_precio == "implicito":
        bloqueos.append("SPX implícito por paridad, sin referencia independiente")
    edad_ref = (corte-ref.sello_evento_utc).total_seconds()
    if edad_ref > reglas.desfase_spot_max:
        bloqueos.append("referencia desfasada respecto del corte")
    candidatos, calibraciones, evaluacion = [], {}, []
    calidad = dict(filas=len(filas), validas=0, elegibles=0, entrenamiento=0, holdout=0,
                   edad_referencia_s=edad_ref, motivos={}, vencimientos=[], modo_descriptivo=bool(modo_descriptivo))
    for venc, g in filas.groupby("vencimiento", sort=True):
        cap, info = contrato.captura_de_filas(g, fecha, corte, ref.precio, ref.sello_evento_utc, tasa, q)
        ctrl = cadenas.controlar(cap, reglas)
        calidad["validas"] += int(ctrl.valida.sum())
        for motivo, cuenta in ctrl.resumen().items():
            calidad["motivos"][motivo] = calidad["motivos"].get(motivo, 0)+cuenta
        calidad["vencimientos"].append(dict(dias=info["dias"], filas=len(g), validas=int(ctrl.valida.sum())))
        if not minimo_dias <= info["dias"] <= maximo_dias:
            continue
        gg = g.loc[ctrl.valida].copy()
        if gg.empty:
            continue
        F, D = cap.forward_contractual, math.exp(-tasa*cap.T)
        gg["k"] = np.log(gg.strike/F)
        gg = gg[gg.k.abs() <= ancho_evaluacion].copy()
        if gg.empty:
            continue
        ks = sorted(gg.strike.unique())
        reserva = {k for j, k in enumerate(ks) if j % 3 == 0}
        gg["entrenamiento"] = (~gg.strike.isin(reserva)) & (gg.k.abs() <= ancho_atm)
        for nombre, precios in (("iv_mid", (gg.bid+gg.ask)/2), ("iv_bid", gg.bid), ("iv_ask", gg.ask)):
            gg[nombre] = vol_implicita_black(precios.to_numpy(), F, gg.strike.to_numpy(), cap.T, D,
                                            gg.tipo.eq("C").to_numpy())
        finitas = np.isfinite(gg[["iv_mid", "iv_bid", "iv_ask"]]).all(axis=1)
        calidad["iv_no_identificada"] = calidad.get("iv_no_identificada", 0)+int((~finitas).sum())
        gg = gg[finitas].copy()
        train = gg[gg.entrenamiento]
        if len(train) < minimo_entrenamiento or train.strike.nunique() < 3:
            continue
        sig = dict(mid=float(train.iv_mid.median()), bid=float(train.iv_bid.median()), ask=float(train.iv_ask.median()))
        calibraciones[str(venc)] = dict(**sig, dias=info["dias"], filas_entrenamiento=len(train))
        calidad["entrenamiento"] += len(train)
        calidad["holdout"] += int(gg.strike.isin(reserva).sum())
        calidad["elegibles"] += len(gg)
        gg["holdout"] = gg.strike.isin(reserva)
        gg["sigma_plana"] = sig["mid"]
        gg["dias"] = info["dias"]
        evaluacion.append(gg)
        for tipo in ("C", "P"):
            propias = gg[gg.tipo == tipo]
            if propias.empty:
                continue
            usados = set()
            for objetivo in objetivos_moneyness:
                i = (propias.k-objetivo).abs().idxmin()
                r = propias.loc[i]
                if r.id_contrato in usados:
                    continue
                usados.add(r.id_contrato)
                candidatos.append(ContratoEscenario(r.id_contrato, float(r.strike), info["dias"], tipo == "C",
                                  "europeo", sig["mid"], float(r.bid), float(r.ask), int(r.multiplicador)))
    if not calibraciones:
        bloqueos.append("sin suficientes cotizaciones ATM para ajustar")
    if bloqueos and not modo_descriptivo:
        candidatos = []
    return PreparacionComparador(float(ref.precio), tuple(candidatos), calibraciones, calidad,
                                pd.concat(evaluacion, ignore_index=True) if evaluacion else pd.DataFrame(), tuple(bloqueos))
