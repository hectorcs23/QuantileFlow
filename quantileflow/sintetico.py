"""Generadores de datos **sintéticos** para ilustrar el método.

Nada de lo que produce este módulo es un dato de mercado ni una estimación
empírica. Los parámetros se eligen para que las figuras sean legibles y
plausibles, no para reproducir un activo real.
"""
from __future__ import annotations

import numpy as np

from .opciones import precio_black
from .superficies import (Rebanada, SuperficieSSVI, densidad_logmoneyness, derivadas_ssvi,
                          phi_potencia)
from .distribuciones import cdf_desde_densidad

DIAS_ANIO = 365.0


def superficie_referencia():
    """Superficie SSVI "verdadera" del mundo sintético (índice, subyacente = 100)."""
    tiempos = np.array([7, 30, 60, 91]) / DIAS_ANIO
    vol_atm = np.array([0.17, 0.19, 0.20, 0.205])
    return SuperficieSSVI(tiempos, vol_atm**2 * tiempos, rho=-0.7, eta=1.1, gamma=0.45)


def _redondear(x, tick=0.01, modo="cerca"):
    if modo == "abajo":
        return np.floor(x / tick + 1e-9) * tick
    if modo == "arriba":
        return np.ceil(x / tick - 1e-9) * tick
    return np.round(x / tick) * tick


def cadena_sintetica(rng, superficie=None, S0=100.0, r=0.04, q=0.013, ruido_rel=0.25,
                     pasos=(0.5, 1.0, 2.0, 2.5)):
    """Cotizaciones OTM (puts bajo el forward, calls encima) con spreads realistas.

    El spread crece con el precio y tiene un mínimo de un tick; cuando el precio
    teórico es menor que un par de ticks el bid es cero: esas cotizaciones solo
    acotan el precio por arriba y no identifican la cola.
    """
    sup = superficie or superficie_referencia()
    rebanadas, extras = [], []
    for T, theta, paso in zip(sup.tiempos, sup.thetas, pasos):
        F = S0 * np.exp((r - q) * T)
        D = np.exp(-r * T)
        sd = np.sqrt(theta)
        k_lo, k_hi = -4.8 * sd, 2.8 * sd
        K = np.arange(np.ceil(F * np.exp(k_lo) / paso) * paso, F * np.exp(k_hi), paso)
        es_call = K >= F
        k = np.log(K / F)
        w = sup.w(k, T)
        verdadero = precio_black(F, K, w, D, es_call)
        spread = np.clip(_redondear(0.02 + 0.03 * verdadero, modo="arriba"), 0.01, 0.60)
        mid = verdadero + rng.normal(0.0, ruido_rel * spread / 2.0)
        bid = np.maximum(_redondear(mid - spread / 2.0, modo="abajo"), 0.0)
        ask = np.maximum(_redondear(mid + spread / 2.0, modo="arriba"), bid + 0.01)
        sin_bid = verdadero < 0.025
        bid = np.where(sin_bid, 0.0, bid)
        ask = np.where(sin_bid, np.maximum(ask, 0.03), ask)
        rebanadas.append(Rebanada(T=float(T), F=float(F), D=float(D), K=K, bid=bid, ask=ask,
                                  es_call=es_call))
        extras.append({"verdadero": verdadero, "fiable": bid > 0})
    return rebanadas, extras


def cuantiles_ssvi(theta, rho, phi, u, n=3000):
    """Cuantiles de ``x = ln(S_T/F)`` para una rebanada SSVI."""
    sd = np.sqrt(theta)
    k = np.linspace(-14.0 * sd - 0.05, 8.0 * sd + 0.05, n)
    p = densidad_logmoneyness(k, *derivadas_ssvi(k, theta, rho, phi))
    cdf = cdf_desde_densidad(k, np.maximum(p, 0.0))
    masa = cdf[-1]
    cdf = np.maximum.accumulate(cdf / masa)
    unicos, idx = np.unique(cdf, return_index=True)
    return np.interp(u, unicos, k[idx]), masa


def malla_u(n=199, borde=0.005):
    return np.linspace(borde, 1.0 - borde, n)


def _ar1(rng, n, media, persistencia, sd, x0=None):
    x = np.empty(n)
    x[0] = media if x0 is None else x0
    for t in range(1, n):
        x[t] = media + persistencia * (x[t - 1] - media) + rng.normal(0.0, sd)
    return x


def panel_distribuciones(rng, n_dias=260, tau=30 / DIAS_ANIO, dia_choque=170, dia_evento=205,
                         u=None):
    """Panel diario de distribuciones Q a vencimiento constante para mercado y acción A.

    Estado latente por sesión: nivel de volatilidad, asimetría ``rho`` y peso de
    alas ``eta``. El mercado sufre un choque común en ``dia_choque``; la acción A
    recibe además una deformación idiosincrática de la cola izquierda en
    ``dia_evento`` sin movimiento de precio (la "innovación" que se busca medir).
    Las observaciones añaden ruido de ajuste proporcional a la calidad de la
    sesión; en algunos días falta la observación (NaN).
    """
    u = malla_u() if u is None else u
    n = n_dias
    # --- Mercado -----------------------------------------------------------
    z_m = rng.standard_t(5, size=n) * np.sqrt(3 / 5)  # varianza unitaria
    z_m[dia_choque] = -4.5
    z_m[dia_evento] = 0.1
    log_sig = np.empty(n)
    media_log = np.log(0.17)
    log_sig[0] = media_log
    for t in range(1, n):
        # Efecto apalancamiento: un día de -2 desviaciones sube la volatilidad ~8 %.
        log_sig[t] = (media_log + 0.965 * (log_sig[t - 1] - media_log) - 0.04 * z_m[t]
                      + rng.normal(0.0, 0.035))
        if t == dia_choque:
            log_sig[t] += 0.30
    sig_m = np.exp(log_sig)
    ret_m = z_m * sig_m / np.sqrt(252)
    rho_m = np.clip(_ar1(rng, n, -0.68, 0.95, 0.012), -0.95, -0.3)
    rho_m[dia_choque:] += -0.12 * 0.93 ** np.arange(n - dia_choque)
    eta_rel_m = np.clip(_ar1(rng, n, 0.80, 0.9, 0.02), 0.3, 0.97)

    # --- Acción A ----------------------------------------------------------
    beta_a = 1.1
    idio = rng.standard_t(5, size=n) * np.sqrt(3 / 5) * 0.012
    idio[dia_evento] = 0.0005
    ret_a = beta_a * ret_m + idio
    log_sig_a = np.log(sig_m * 1.35) + _ar1(rng, n, 0.0, 0.9, 0.02)
    log_sig_a[dia_evento:] += 0.10 * 0.9 ** np.arange(n - dia_evento)
    rho_a = np.clip(_ar1(rng, n, -0.45, 0.93, 0.015), -0.95, -0.1)
    rho_a[dia_choque:] += -0.08 * 0.93 ** np.arange(n - dia_choque)
    rho_a[dia_evento:] += -0.30 * 0.9 ** np.arange(n - dia_evento)
    eta_rel_a = np.clip(_ar1(rng, n, 0.75, 0.9, 0.02), 0.3, 0.97)
    eta_rel_a[dia_evento:] = np.minimum(eta_rel_a[dia_evento:] + 0.15 * 0.9 ** np.arange(n - dia_evento), 0.98)
    sig_a = np.exp(log_sig_a)

    # --- Calidad de cotizaciones ------------------------------------------
    calidad = np.ones(n)
    calidad[60:76] = 4.0  # spreads amplios varias sesiones
    calidad[rng.choice(n, 8, replace=False)] *= 2.0
    faltante = np.zeros(n, dtype=bool)
    faltante[[i for i in (95, 96, 140) if i < n]] = True

    def construir(sig, rho, eta_rel, ruido):
        X = np.empty((n, len(u)))
        params = np.empty((n, 3))
        for t in range(n):
            th = sig[t] ** 2 * tau
            r_ = rho[t]
            eta = eta_rel[t] * 2.0 / (1.0 + abs(r_))
            if ruido is not None:
                th *= np.exp(ruido[t, 0])
                r_ = np.clip(r_ + ruido[t, 1], -0.97, 0.0)
                eta = min(eta * np.exp(ruido[t, 2]), 0.995 * 2.0 / (1.0 + abs(r_)))
            ph = phi_potencia(th, eta, 0.45)
            X[t], _ = cuantiles_ssvi(th, r_, ph, u)
            params[t] = (th, r_, eta)
        return X, params

    ruido_m = rng.normal(0.0, 1.0, size=(n, 3)) * np.array([0.03, 0.012, 0.02]) * calidad[:, None]
    ruido_a = rng.normal(0.0, 1.0, size=(n, 3)) * np.array([0.04, 0.015, 0.025]) * calidad[:, None]
    X_m, par_m = construir(sig_m, rho_m, eta_rel_m, None)
    Y_m, par_om = construir(sig_m, rho_m, eta_rel_m, ruido_m)
    X_a, par_a = construir(sig_a, rho_a, eta_rel_a, None)
    Y_a, par_oa = construir(sig_a, rho_a, eta_rel_a, ruido_a)
    Y_m[faltante] = np.nan
    Y_a[faltante] = np.nan
    return {
        "u": u, "tau": tau, "dia_choque": dia_choque, "dia_evento": dia_evento,
        "mercado": {"latente": X_m, "observado": Y_m, "ret": ret_m, "vol": sig_m,
                    "parametros": par_m, "parametros_obs": par_om},
        "accion": {"latente": X_a, "observado": Y_a, "ret": ret_a, "vol": sig_a,
                   "parametros": par_a, "parametros_obs": par_oa},
        "calidad": calidad, "faltante": faltante,
    }
