"""Mundo **sintético** para ejercitar el subproyecto de extremo a extremo.

No hay datos de mercado. La cadena viene de ``quantileflow.sintetico`` y la
distribución implícita se reconstruye por el mismo camino que se usaría con
cotizaciones reales: ajuste de la rebanada y lectura de su CDF. Como contraste
se construye una segunda ``Q`` con el ajuste convexo no paramétrico, que no
supone ninguna forma de sonrisa; sirve de perturbación en ``robustez``.

Ninguna cifra de aquí dice nada sobre ningún activo.
"""
from __future__ import annotations

import numpy as np

from quantileflow import sintetico as nucleo
from quantileflow import superficies

from .distribucion import desde_cdf, desde_probabilidades, malla_precios
from .precios import mercado_desde_rebanada

DIAS_ANIO = 365.0


def q_desde_rebanada_ssvi(reb, malla, rango_fiable, peso_mid=0.02):
    """``Q`` a partir del ajuste SSVI de una rebanada (CDF analítica, sin normalizar masa)."""
    ajuste, _ = superficies.ajustar_rebanada(reb, peso_mid=peso_mid)
    k = np.log(np.asarray(malla, dtype=float) / reb.F)
    cdf = ajuste.cdf(k)
    d = desde_cdf(malla, cdf, rango_fiable, "Q implícita (ajuste SSVI de la rebanada)",
                  theta=ajuste.theta, rho=ajuste.rho, phi=ajuste.phi, forward=float(reb.F))
    return d, ajuste


def q_desde_ajuste_convexo(reb, malla, rango_fiable, submuestreo=8, tol=2e-3):
    """``Q`` no paramétrica: densidad discreta con precios monótonos y convexos.

    Se resuelve sobre un submuestreo de la malla (el problema tiene una variable
    por punto de soporte) y el resultado se coloca en la malla común como
    átomos. Es deliberadamente más tosca: su papel es discrepar.
    """
    soporte = np.asarray(malla, dtype=float)[::int(submuestreo)]
    q, _, _ = superficies.ajuste_convexo(reb, soporte)
    p = np.zeros(len(malla))
    p[::int(submuestreo)] = q
    return desde_probabilidades(malla, p, rango_fiable,
                                "Q implícita (ajuste convexo no paramétrico)", tol=tol,
                                submuestreo=int(submuestreo), forward=float(reb.F),
                                media_sobre_forward=float(q @ soporte) / reb.F)


def mundo(semilla=7, indice_vencimiento=1, n_malla=2001, anchura=12.0, comision=0.01,
          coste_forward=0.0005, spread_relativo_max=0.5, spread_absoluto_min=0.05,
          con_q_alternativa=True):
    """Rebanada sintética a unos 30 días con su mercado, su malla y dos estimaciones de ``Q``."""
    rebanadas, extras = nucleo.cadena_sintetica(np.random.default_rng(semilla))
    reb, extra = rebanadas[indice_vencimiento], extras[indice_vencimiento]
    mercado = mercado_desde_rebanada(reb, comision=comision, coste_forward=coste_forward,
                                     spread_relativo_max=spread_relativo_max,
                                     spread_absoluto_min=spread_absoluto_min)
    rango = mercado.rango_fiable()
    sd = float(np.sqrt(nucleo.superficie_referencia().theta_en(reb.T)))
    malla = malla_precios(reb.F, sd, n=n_malla, anchura=anchura)
    q, ajuste = q_desde_rebanada_ssvi(reb, malla, rango)
    q_alt = q_desde_ajuste_convexo(reb, malla, rango) if con_q_alternativa else None
    return {"rebanada": reb, "mercado": mercado, "malla": malla, "q": q, "q_alternativa": q_alt,
            "ajuste": ajuste, "rango_fiable": rango, "sd_log": sd,
            "strikes_fiables": mercado.strikes_fiables(),
            "verdad": {"fiable": extra["fiable"], "precio": extra["verdadero"]},
            "dias": float(reb.T * DIAS_ANIO)}
