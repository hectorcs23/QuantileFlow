"""Generadores de datos **sintéticos** para ilustrar el método.

Nada de lo que produce este módulo es un dato de mercado ni una estimación
empírica. Los parámetros se eligen para que las figuras sean legibles y
plausibles, no para reproducir un activo real.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from .cadenas import HORA_CORTE, Captura
from .opciones import binomial_crr, precio_black
from .superficies import (Rebanada, SuperficieSSVI, cdf_logmoneyness, derivadas_ssvi, phi_potencia,
                          varianza_total_ssvi)
from .distribuciones import cuantiles_desde_cdf

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


def captura_sintetica(S=100.0, T=30 / DIAS_ANIO, r=0.04, q=0.0, dividendos=(), ejercicio="europeo",
                      strikes=None, superficie=None, corte=HORA_CORTE, edad=5.0, rng=None,
                      ruido_rel=0.0, n_arbol=200, fecha="2026-09-25"):
    """Captura sintética con call y put en cada strike, bid/ask al tick y sellos frescos.

    El precio verdadero sale de la rebanada SSVI de referencia en ``T`` con el
    forward ``(S - VP(dividendos)) e^{(r - q) T}``; si ``ejercicio`` es
    ``"americano"`` se valora con el árbol binomial (dividendos en efectivo con
    el modelo *escrowed*) a la volatilidad de la sonrisa en cada strike. Sin
    ``rng`` no hay ruido: el precio verdadero siempre queda dentro de
    ``[bid, ask]``. Devuelve la captura y un diccionario con la verdad.
    """
    sup = superficie or superficie_referencia()
    vp = sum(m * np.exp(-r * t) for t, m in dividendos if 0.0 < t <= T)
    F = (S - vp) * np.exp((r - q) * T)
    D = np.exp(-r * T)
    K = np.arange(80.0, 120.0 + 1e-9, 1.0) if strikes is None else np.asarray(strikes, dtype=float)
    K2 = np.concatenate([K, K])
    es_call = np.concatenate([np.ones(len(K), bool), np.zeros(len(K), bool)])
    w = sup.w(np.log(K2 / F), T)
    sigma = np.sqrt(w / T)
    if ejercicio == "americano":
        verdadero = np.array([binomial_crr(S, k_, T, r, s_, c_, q, dividendos, n_arbol, americana=True)
                              for k_, s_, c_ in zip(K2, sigma, es_call)])
    else:
        verdadero = precio_black(F, K2, w, D, es_call)
    spread = np.clip(_redondear(0.02 + 0.03 * verdadero, modo="arriba"), 0.01, 0.60)
    mid = verdadero if rng is None else verdadero + rng.normal(0.0, ruido_rel * spread / 2.0)
    bid = np.maximum(_redondear(mid - spread / 2.0, modo="abajo"), 0.0)
    ask = np.maximum(_redondear(mid + spread / 2.0, modo="arriba"), bid + 0.01)
    n = len(K2)
    captura = Captura(strike=K2, es_call=es_call, bid=bid, ask=ask, tam_bid=np.full(n, 10.0),
                      tam_ask=np.full(n, 10.0), sello=np.full(n, corte - edad), T=T, spot=S,
                      sello_spot=corte, tasa=r, dividendos=tuple(dividendos),
                      rendimiento_dividendo=q, ejercicio=ejercicio, corte=corte, fecha=fecha)
    return captura, {"forward": F, "descuento": D, "sigma": sigma, "precio": verdadero}


def cuantiles_ssvi(theta, rho, phi, u, n=3000):
    """Cuantiles de ``x = ln(S_T/F)`` para una rebanada SSVI del mundo sintético.

    Usa la CDF analítica (anclada en ambas colas), sin normalizar ni recortar.
    Devuelve también la probabilidad cubierta por la malla. Si algún nivel no
    queda identificado se lanza un error: aquí sería un fallo del generador.
    """
    sd = np.sqrt(theta)
    k = np.linspace(-14.0 * sd - 0.05, 8.0 * sd + 0.05, n)
    w, w1, _ = derivadas_ssvi(k, theta, rho, phi)
    cdf = cdf_logmoneyness(k, w, w1)
    resultado = cuantiles_desde_cdf(k, cdf, u)
    if not resultado.completo:
        raise ValueError(f"cuantiles SSVI no identificados: {resultado.motivo}")
    return resultado.valores, float(cdf[-1] - cdf[0])


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


# ---------------------------------------------------------------------------
# Mercado sintético tipo SPXW en el esquema normalizado del contrato de datos
# ---------------------------------------------------------------------------

ESCENARIOS = ("desfasadas", "sin_hora_evento", "hueco_calls", "spreads_anchos", "spot_desfasado",
              "sin_subyacente", "objetivo_sin_cotizacion", "objetivo_spread_anormal")


def _tick_indice(precio):
    """Ticks tipo SPX: 0.05 por debajo de 3.00 y 0.10 desde 3.00 (a confirmar con Cboe)."""
    return np.where(np.asarray(precio) < 3.0, 0.05, 0.10)


def _redondear_tick(x, modo):
    tick = _tick_indice(np.maximum(x, 0.0))
    return _redondear(x / tick, 1.0, modo) * tick


def iv_en_delta_ssvi(theta, rho, phi, T, delta, es_call):
    """Volatilidad y log-moneyness de la opción con delta forward ``delta`` en una rebanada SSVI."""
    from scipy.optimize import brentq
    from scipy.stats import norm as _norm

    def exceso(k):
        w = float(varianza_total_ssvi(k, theta, rho, phi))
        d1 = (-k + 0.5 * w) / np.sqrt(w)
        return (_norm.cdf(d1) if es_call else _norm.cdf(-d1)) - delta

    k = brentq(exceso, 0.0, 2.0) if es_call else brentq(exceso, -3.0, 0.0)
    return float(np.sqrt(varianza_total_ssvi(k, theta, rho, phi) / T)), float(k)


def mercado_sintetico(fechas, semilla=0, S0=5800.0, r=0.04, q=0.013, horas=("09:45", "10:00"),
                      raiz="SPXW", subyacente="SPX", paso_strike=10.0, rango_k=(-0.10, 0.05),
                      dias_vencimiento=(18, 48), escenarios=None, sesiones_extra=5,
                      recibido="2026-09-26T12:00:00Z", objetivo="SPY", ex_objetivo=None, dividendo=1.8,
                      hora_eventos="10:21"):
    """Cotizaciones y subyacente sintéticos con el esquema de ``contrato`` (SINTÉTICO).

    Opciones europeas con liquidación PM que vencen los viernes hábiles entre
    ``dias_vencimiento`` días naturales; sonrisa SSVI con nivel y asimetría que
    cambian cada sesión, y ruido dentro del spread. ``escenarios`` asigna a
    cada fecha nombres de ``ESCENARIOS`` que degradan la hora principal:
    cotizaciones desfasadas, snapshot sin hora de evento, hueco de strikes call
    cerca de delta 25, spreads anchos, subyacente desfasado o ausente, objetivo
    sin cotización o con spread anormal. El subyacente se extiende
    ``sesiones_extra`` sesiones para madurar etiquetas.

    ``objetivo`` (si no es ``None``) añade un ETF observado tipo SPY:
    ``subyacente / 10`` más el dividendo que se acumula linealmente y cae en su
    fecha ex (``ex_objetivo``; por omisión, la sesión central de ``fechas``).
    Se publica 15 minutos después del corte, como el SIP de Alpaca sin
    suscripción. Usa su propio generador aleatorio: no cambia el resto.

    Devuelve ``(cotizaciones, subyacente, verdad)``. ``verdad["dividendos"]``
    trae la versión del dividendo (esquema ``contrato.DIVIDENDOS``) y
    ``verdad["cobertura"]``, una consulta completa de eventos por sesión a
    ``hora_eventos`` (``contrato.COBERTURA_DIVIDENDOS``), como el workflow del
    histórico.
    """
    import pandas as pd

    from .calendario import instante, instante_liquidacion, plazo_anios, sesion_desplazada, sesiones
    from .contrato import simbolo_occ

    rng = np.random.default_rng(semilla)
    escenarios = {pd.Timestamp(f).date(): set(v) for f, v in (escenarios or {}).items()}
    fechas = sorted(pd.Timestamp(f).date() for f in fechas)
    todas = fechas + [sesion_desplazada(fechas[-1], i) for i in range(1, sesiones_extra + 1)]
    n = len(todas)
    nivel = np.empty(n)
    rho = np.empty(n)
    nivel[0], rho[0] = 0.16, -0.70
    for t in range(1, n):
        nivel[t] = np.clip(0.16 + 0.85 * (nivel[t - 1] - 0.16) + rng.normal(0.0, 0.012), 0.09, 0.40)
        rho[t] = np.clip(-0.70 + 0.80 * (rho[t - 1] + 0.70) + rng.normal(0.0, 0.05), -0.95, -0.30)
    principal = horas[0]
    spot = {}
    for t, fecha in enumerate(todas):
        base = S0 if t == 0 else spot[(todas[t - 1], principal)]
        sd = nivel[t - 1 if t else 0] / np.sqrt(252.0)
        spot[(fecha, principal)] = base * np.exp(sd * rng.standard_normal() - 0.5 * sd**2)
        for hora in horas[1:]:
            minutos = (instante(fecha, hora) - instante(fecha, principal)).total_seconds() / 60.0
            sd_i = nivel[t] * np.sqrt(minutos / (390.0 * 252.0))
            spot[(fecha, hora)] = spot[(fecha, principal)] * np.exp(sd_i * rng.standard_normal())
    recibido_utc = pd.Timestamp(recibido)
    eta, gamma = 1.1, 0.45
    filas, filas_sub, verdad = [], [], {}
    for t, fecha in enumerate(todas):
        esc = escenarios.get(fecha, set())
        for hora in horas:
            corte = instante(fecha, hora)
            degradar = hora == principal
            if not (degradar and "sin_subyacente" in esc):
                atraso = 30.0 if degradar and "spot_desfasado" in esc else rng.uniform(0.0, 1.0)
                filas_sub.append({"subyacente": subyacente, "precio": spot[(fecha, hora)], "bid": np.nan,
                                  "ask": np.nan, "sello_evento_utc": corte - pd.Timedelta(seconds=atraso),
                                  "sello_snapshot_utc": corte, "disponible_utc": corte,
                                  "recibido_utc": recibido_utc, "proveedor": "sintetico",
                                  "feed": "indice_sintetico", "tipo_precio": "observado"})
            if fecha not in fechas:
                continue
            S = spot[(fecha, hora)]
            venc = [d for d in sesiones(pd.Timestamp(fecha) + pd.Timedelta(days=dias_vencimiento[0]),
                                        pd.Timestamp(fecha) + pd.Timedelta(days=dias_vencimiento[1]))
                    if d.weekday() == 4]
            for v in venc:
                T = plazo_anios(corte, instante_liquidacion(v, "PM"))
                theta = nivel[t] ** 2 * T
                phi = float(phi_potencia(theta, eta, gamma))
                F, D = S * np.exp((r - q) * T), np.exp(-r * T)
                verdad[(fecha, hora, v)] = {"theta": theta, "rho": rho[t], "phi": phi, "T": T, "F": F, "D": D}
                K = np.arange(np.ceil(F * np.exp(rango_k[0]) / paso_strike) * paso_strike,
                              F * np.exp(rango_k[1]), paso_strike)
                for tipo in ("C", "P"):
                    Kt = K
                    if degradar and "hueco_calls" in esc and tipo == "C":
                        Kt = K[(np.log(K / F) < 0.005) | (np.log(K / F) > 0.06)]
                    k = np.log(Kt / F)
                    precio = precio_black(F, Kt, varianza_total_ssvi(k, theta, rho[t], phi), D, tipo == "C")
                    evento = corte - pd.to_timedelta(rng.uniform(0.0, 20.0, len(Kt)), unit="s")
                    if degradar and "desfasadas" in esc and tipo == "P":
                        # Puts cercanos a delta 25 con precios de hace 5 minutos (subyacente 0.5 % más bajo).
                        viejas = (k > -0.06) & (k < -0.02)
                        F_viejo = F * 0.995
                        k_viejo = np.log(Kt / F_viejo)
                        precio_viejo = precio_black(F_viejo, Kt,
                                                    varianza_total_ssvi(k_viejo, theta, rho[t], phi), D, False)
                        precio = np.where(viejas, precio_viejo, precio)
                        evento = evento.where(~viejas, corte - pd.Timedelta(seconds=300))
                    if degradar and "sin_hora_evento" in esc:
                        evento = pd.Series(pd.NaT, index=range(len(Kt)), dtype="datetime64[ns, UTC]")
                    ancho = np.clip(_redondear_tick(0.10 + 0.015 * precio, "arriba"), 0.05, 3.0)
                    if degradar and "spreads_anchos" in esc:
                        ancho = ancho * 5.0
                    mid = precio + rng.normal(0.0, 0.1 * ancho)
                    bid = np.round(np.maximum(_redondear_tick(mid - ancho / 2.0, "abajo"), 0.0), 4)
                    ask = np.round(np.maximum(_redondear_tick(mid + ancho / 2.0, "arriba"),
                                              bid + _tick_indice(bid)), 4)
                    for i in range(len(Kt)):
                        filas.append({
                            "id_contrato": simbolo_occ(raiz, v, tipo, Kt[i]), "raiz": raiz,
                            "subyacente": subyacente, "strike": float(Kt[i]), "tipo": tipo,
                            "ejercicio": "europeo", "liquidacion": "PM", "vencimiento": v,
                            "multiplicador": 100.0, "bid": float(bid[i]), "ask": float(ask[i]),
                            "tam_bid": float(rng.integers(1, 60)), "tam_ask": float(rng.integers(1, 60)),
                            "sello_evento_utc": evento[i] if not isinstance(evento, pd.Series) else evento.iloc[i],
                            "sello_snapshot_utc": corte, "disponible_utc": corte,
                            "recibido_utc": recibido_utc, "proveedor": "sintetico",
                            "feed": "nbbo_intervalos_sintetico"})
    if objetivo:
        rng_obj = np.random.default_rng(semilla + 1_000_003)
        ex = pd.Timestamp(ex_objetivo).date() if ex_objetivo else fechas[len(fechas) // 2]
        previo = ex - dt.timedelta(days=91)
        verdad["objetivo"] = {}
        for fecha in todas:
            esc = escenarios.get(fecha, set())
            dias = (fecha - (previo if fecha < ex else ex)).days
            acumulado = dividendo * dias / 91.0  # el dividendo que se va a pagar, acumulado desde la fecha ex previa
            for hora in horas:
                corte = instante(fecha, hora)
                mid = round(spot[(fecha, hora)] / 10.0 + acumulado, 2)
                verdad["objetivo"][(fecha, hora)] = mid
                if hora == principal and "objetivo_sin_cotizacion" in esc:
                    continue
                medio = 0.5 if hora == principal and "objetivo_spread_anormal" in esc else 0.005
                filas_sub.append({"subyacente": objetivo, "precio": mid, "bid": mid - medio, "ask": mid + medio,
                                  "sello_evento_utc": corte - pd.Timedelta(seconds=rng_obj.uniform(0.0, 1.0)),
                                  "sello_snapshot_utc": corte, "disponible_utc": corte + pd.Timedelta(minutes=15),
                                  "recibido_utc": recibido_utc, "proveedor": "sintetico", "feed": "sip_sintetico",
                                  "tipo_precio": "observado"})
        pago = ex + dt.timedelta(days=42)
        consultas = [{"simbolo": objetivo, "desde": f - dt.timedelta(days=400), "hasta": f + dt.timedelta(days=120),
                      "campo_fecha": "process_date", "recibido_utc": instante(f, hora_eventos), "estado": "completa",
                      "eventos": float(f - dt.timedelta(days=400) <= pago <= f + dt.timedelta(days=120)),
                      "calidad": "complete", "tipos": "todos", "consulta": f"eventos-sinteticos-{f}",
                      "proveedor": "sintetico", "feed": "dividendos_sinteticos"} for f in todas]
        # La descarga de la «verdad», meses después, deja aceptadas las etiquetas de la muestra.
        final = recibido_utc.tz_convert("America/New_York").date()
        consultas.append(dict(consultas[-1], desde=final - dt.timedelta(days=400), hasta=final + dt.timedelta(days=120),
                              recibido_utc=recibido_utc, consulta=f"eventos-sinteticos-{final}"))
        verdad["cobertura"] = pd.DataFrame(consultas)
        verdad["dividendos"] = pd.DataFrame([{
            "simbolo": objetivo, "fecha_ex": ex, "monto": dividendo, "fecha_pago": pago, "clase": "ordinario",
            "proceso_desde": None, "proceso_hasta": None,
            "disponible_utc": pd.Timestamp(ex - dt.timedelta(days=30), tz="UTC"), "recibido_utc": recibido_utc,
            "retirado_utc": pd.NaT, "motivo_retiro": "", "discrepancia": "", "discrepancia_desde_utc": pd.NaT,
            "proveedor": "sintetico", "feed": "dividendos_sinteticos"}])
        for tabla, columnas in ((verdad["dividendos"], ("disponible_utc", "recibido_utc", "retirado_utc",
                                                        "discrepancia_desde_utc")),
                                (verdad["cobertura"], ("recibido_utc",))):
            for columna in columnas:
                tabla[columna] = pd.to_datetime(tabla[columna], utc=True).dt.as_unit("us")
    cotizaciones = pd.DataFrame(filas)
    sub = pd.DataFrame(filas_sub)
    for tabla in (cotizaciones, sub):
        for columna in ("sello_evento_utc", "sello_snapshot_utc", "disponible_utc", "recibido_utc"):
            tabla[columna] = pd.to_datetime(tabla[columna], utc=True).dt.as_unit("us")
    verdad["spot"] = spot
    verdad["nivel"] = dict(zip(todas, nivel))
    verdad["rho"] = dict(zip(todas, rho))
    return cotizaciones, sub, verdad
