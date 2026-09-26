"""Cadenas bid/ask sintéticas: cotizaciones desfasadas, dividendos, strikes ausentes y apertura.

Estas pruebas verifican que el procesamiento de cadenas crudas separa efectos
de datos (desfase, dividendos, ejercicio, huecos, horario) de una posible
señal. No demuestran validez predictiva ni calidad de datos reales.
"""
import dataclasses

import numpy as np
import pytest

from quantileflow import cadenas as ca
from quantileflow import opciones, sintetico


def _filas(cap, strikes, es_call=None):
    return [i for i in range(len(cap.strike))
            if cap.strike[i] in strikes and (es_call is None or bool(cap.es_call[i]) == es_call)]


def _sin_filas(cap, quitar):
    quedan = np.setdiff1d(np.arange(len(cap.strike)), quitar)
    return dataclasses.replace(cap, strike=cap.strike[quedan], es_call=cap.es_call[quedan],
                               bid=cap.bid[quedan], ask=cap.ask[quedan], tam_bid=cap.tam_bid[quedan],
                               tam_ask=cap.tam_ask[quedan], sello=cap.sello[quedan])


def _unir(*capturas, base):
    return dataclasses.replace(base, **{nombre: np.concatenate([getattr(c, nombre) for c in capturas])
                                        for nombre in ("strike", "es_call", "bid", "ask", "tam_bid",
                                                       "tam_ask", "sello")})


@pytest.fixture(scope="module")
def limpia():
    cap, verdad = sintetico.captura_sintetica(q=0.013)
    return cap, verdad, ca.procesar_captura(cap)


@pytest.fixture(scope="module")
def americana():
    K = np.arange(90.0, 110.0 + 1e-9, 1.0)
    divs = ((10 / 365, 1.5),)
    cap, verdad = sintetico.captura_sintetica(ejercicio="americano", dividendos=divs, strikes=K)
    return cap, verdad, ca.procesar_captura(cap)


# --- Cadena limpia ---------------------------------------------------------------

def test_cadena_limpia_sin_residuos_ni_senales(limpia):
    cap, verdad, res = limpia
    p = res.paridad
    assert abs(p.forward_global - verdad["forward"]) < 0.01
    assert abs(p.descuento_global - verdad["descuento"]) < 1e-3
    assert len(p.strike) > 15
    assert not p.fuera_de_banda.any() and not p.interpretable.any()
    assert set(res.controles.resumen()) <= set(ca.MOTIVOS)


def test_asimetria_simetrica_y_por_delta_coinciden_con_la_sonrisa(limpia):
    cap, verdad, res = limpia
    sup = sintetico.superficie_referencia()
    d = np.log1p(0.03)
    s_mas, s_menos = np.sqrt(sup.w(np.array([d, -d]), cap.T) / cap.T)
    a = res.asimetria
    assert a["estado"] == "identificada"
    assert abs(a["iv_call"] - s_mas) < 2e-3 and abs(a["iv_put"] - s_menos) < 2e-3
    lo, hi = a["diferencia_iv_banda"]
    assert lo <= a["diferencia_iv"] <= hi
    # Con sonrisa simétrica la razón de primas valdría 0; aquí la asimetría la hace positiva.
    assert a["razon_simetrica"] > 0.3
    assert res.asimetria_delta["estado"] == "identificada" and res.asimetria_delta["diferencia_iv"] > 0
    assert res.pendiente["estado"] == "identificada" and res.pendiente["pendiente"] < 0


def test_sin_asimetria_la_razon_de_primas_es_nula():
    """Put-call symmetry: con volatilidad plana P(F e^-d) = e^-d C(F e^d)."""
    plana = sintetico.SuperficieSSVI(np.array([0.05, 0.5]), 0.04 * np.array([0.05, 0.5]), rho=0.0,
                                     eta=1e-6, gamma=0.5)
    cap, _ = sintetico.captura_sintetica(superficie=plana)
    a = ca.procesar_captura(cap).asimetria
    assert a["estado"] == "identificada"
    assert abs(a["diferencia_iv"]) < 2e-3
    assert abs(a["razon_simetrica"]) < 0.03


def test_medidas_estables_dentro_de_bid_ask(limpia):
    """Cualquier precio dentro de [bid, ask] da una asimetría dentro de la banda reportada."""
    cap, _, res = limpia
    lo, hi = res.asimetria["diferencia_iv_banda"]
    rng = np.random.default_rng(0)
    for _ in range(25):
        u = rng.uniform(cap.bid, cap.ask)
        movida = dataclasses.replace(cap, bid=u - 5e-5, ask=u + 5e-5)
        v = ca.volatilidades_observadas(movida, res.controles, res.volatilidades.forward,
                                        res.volatilidades.descuento)
        assert lo - 1e-12 <= ca.asimetria_simetrica(v)["diferencia_iv"] <= hi + 1e-12
        # Con el forward reestimado a partir de los precios movidos, el cambio es mínimo.
        completa = ca.procesar_captura(dataclasses.replace(cap, bid=np.maximum(u - 5e-5, 0.0),
                                                           ask=u + 5e-5))
        assert lo - 2e-3 <= completa.asimetria["diferencia_iv"] <= hi + 2e-3


# --- Cotizaciones desfasadas -----------------------------------------------------

def _con_desfasadas(cap):
    """Puts de 95, 100 y 104 con precios de hace 5 minutos, con el subyacente 1 % más bajo."""
    vieja, _ = sintetico.captura_sintetica(S=99.0, q=0.013)
    filas = _filas(cap, (95.0, 100.0, 104.0), es_call=False)
    bid, ask, sello = cap.bid.copy(), cap.ask.copy(), cap.sello.copy()
    bid[filas], ask[filas], sello[filas] = vieja.bid[filas], vieja.ask[filas], cap.corte - 300.0
    return dataclasses.replace(cap, bid=bid, ask=ask, sello=sello)


def test_cotizaciones_desfasadas_se_excluyen_con_motivo(limpia):
    cap, verdad, _ = limpia
    res = ca.procesar_captura(_con_desfasadas(cap))
    assert res.controles.resumen()["desfasada"] == 3
    faltan = {s["strike"]: s for s in res.paridad.sin_pareja}
    for K in (95.0, 100.0, 104.0):
        assert faltan[K]["falta"] == "put" and faltan[K]["motivo"] == "excluida: desfasada"
    assert not res.paridad.interpretable.any()
    assert abs(res.paridad.forward_global - verdad["forward"]) < 0.01


def test_sin_control_de_edad_las_desfasadas_parecen_senal(limpia):
    """El residuo de una cotización vieja es grande: sin el control se leería como señal."""
    cap, verdad, _ = limpia
    res = ca.procesar_captura(_con_desfasadas(cap), ca.ReglasCalidad(edad_maxima=np.inf))
    p = res.paridad
    viejas = np.isin(p.strike, (95.0, 100.0, 104.0))
    assert np.all(p.interpretable[viejas]) and np.all(p.residuo[viejas] < 0)
    assert np.max(np.abs(p.multiplo_ancho[viejas])) > 2.0
    # Las demás no se contaminan: su forward se estima sin las cotizaciones extremas.
    assert not p.fuera_de_banda[~viejas].any()
    assert not p.en_estimacion[np.isin(p.strike, (100.0, 104.0))].any()
    assert abs(p.forward_global - verdad["forward"]) < 0.01


# --- Dividendos y ejercicio anticipado ------------------------------------------

def test_dividendo_discreto_europeo():
    divs = ((10 / 365, 1.2),)
    cap, verdad = sintetico.captura_sintetica(dividendos=divs)
    p = ca.procesar_captura(cap).paridad
    assert abs(p.forward_global - verdad["forward"]) < 0.01
    assert not p.fuera_de_banda.any()
    # Un forward contractual que omite el dividendo fabrica un residuo igual a su valor presente.
    ingenuo = dataclasses.replace(cap, dividendos=()).forward_contractual
    q = ca.residuos_paridad(cap, forward=ingenuo, descuento=verdad["descuento"])
    vp = 1.2 * np.exp(-0.04 * 10 / 365)
    assert np.all(q.fuera_de_banda)
    assert np.allclose(q.residuo, -vp, atol=0.05)


def test_americanas_con_dividendo_estiman_la_prima_y_no_dan_senales(americana):
    cap, verdad, res = americana
    p = res.paridad
    assert abs(p.forward_global - verdad["forward"]) < 0.01
    assert not p.interpretable.any()
    assert np.nanmax(np.abs(p.multiplo_ancho)) < 0.5
    # La prima estimada coincide con la del árbol a la volatilidad verdadera.
    n = len(cap.strike) // 2
    for j, K in enumerate(p.strike):
        i = int(np.flatnonzero(cap.strike[:n] == K)[0])
        verdadera = [opciones.prima_ejercicio_anticipado(cap.spot, K, cap.T, cap.tasa, verdad["sigma"][f],
                                                         es_call=c, dividendos=cap.dividendos, n=200)
                     for f, c in ((i, True), (i + n, False))]
        assert abs(p.prima_ejercicio[j] - (verdadera[0] - verdadera[1])) < 0.02
    assert p.prima_ejercicio[p.strike == 90.0][0] > 0.5  # call ITM antes del ex-dividendo


def test_americanas_tratadas_como_europeas_sesgan_el_forward(americana):
    cap, verdad, _ = americana
    ingenua = ca.residuos_paridad(dataclasses.replace(cap, ejercicio="europeo"))
    assert abs(ingenua.forward_global - verdad["forward"]) > 0.1


def test_americanas_con_subyacente_desfasado_no_se_interpretan(americana):
    cap, _, res = americana
    bid, ask = cap.bid.copy(), cap.ask.copy()
    i = _filas(cap, (100.0,), es_call=False)[0]
    bid[i] += 0.4
    ask[i] += 0.4
    movida = dataclasses.replace(cap, bid=bid, ask=ask)
    primas = res.primas.copy()
    primas[i] = ca.primas_ejercicio(movida, [i])[i]
    sincronizada = ca.residuos_paridad(movida, ca.controlar(movida), primas)
    assert sincronizada.interpretable[sincronizada.strike == 100.0][0]
    desfasada = dataclasses.replace(movida, sello_spot=cap.corte - 30.0)
    p = ca.residuos_paridad(desfasada, ca.controlar(desfasada), primas)
    assert not p.interpretable.any()
    assert "subyacente desfasado" in p.motivo_no_interpretable[int(np.flatnonzero(p.strike == 100.0)[0])]


# --- Strikes ausentes ------------------------------------------------------------

def test_strikes_ausentes_se_documentan(limpia):
    cap, verdad, _ = limpia
    incompleta = _sin_filas(cap, _filas(cap, (90.0, 91.0), es_call=False) + _filas(cap, (103.0,), es_call=True))
    res = ca.procesar_captura(incompleta)
    faltan = {s["strike"]: s for s in res.paridad.sin_pareja}
    assert faltan[90.0]["falta"] == "put" and faltan[90.0]["motivo"] == "sin cotización"
    assert faltan[103.0]["falta"] == "call" and faltan[103.0]["presente"] == "put"
    assert not np.isin((90.0, 91.0, 103.0), res.paridad.strike).any()
    assert abs(res.paridad.forward_global - verdad["forward"]) < 0.01
    assert res.asimetria["estado"] == "identificada"


def test_hueco_en_la_cola_deja_la_asimetria_no_identificada(limpia):
    cap, _, _ = limpia
    hueco = _sin_filas(cap, _filas(cap, tuple(np.arange(102.0, 107.0)), es_call=True))
    res = ca.procesar_captura(hueco)
    assert res.asimetria["estado"] == "no identificada"
    assert "call" in res.asimetria["motivo"]
    fila = ca.fila_informe(res)
    assert np.isnan(fila["obs_dif_iv_k"]) and fila["obs_asimetria_estado"] == "no identificada"
    # El objetivo put de -3 % cae en K = 97.3: sin los puts de 96 y 97 el tramo 95-98 es muy ancho.
    sin_puts = ca.procesar_captura(_sin_filas(cap, _filas(cap, (96.0, 97.0), es_call=False)))
    assert sin_puts.asimetria["estado"] == "no identificada" and "put" in sin_puts.asimetria["motivo"]


# --- Ventanas de apertura y hora de corte ----------------------------------------

def _con_historia(cap):
    """Añade a cada contrato una fila de preapertura, una de la ventana de apertura y una posterior."""
    pre, _ = sintetico.captura_sintetica(S=101.0, q=0.013, corte=ca.HORA_APERTURA - 55.0)
    ventana, _ = sintetico.captura_sintetica(S=100.5, q=0.013, corte=ca.HORA_APERTURA + 65.0)
    futura, _ = sintetico.captura_sintetica(S=102.0, q=0.013, corte=cap.corte + 35.0)
    return _unir(cap, pre, ventana, futura, base=cap)


def test_solo_cuenta_la_ultima_cotizacion_valida_antes_del_corte(limpia):
    cap, _, base = limpia
    completa = _con_historia(cap)
    res = ca.procesar_captura(completa)
    n = len(cap.strike)
    motivos = res.controles.motivos
    assert np.array_equal(res.controles.valida[:n], base.controles.valida)
    assert not res.controles.valida[n:].any()
    assert all({"reemplazada", "antes_de_apertura"} <= set(m) for m in motivos[n:2 * n])
    assert all({"reemplazada", "ventana_de_apertura"} <= set(m) for m in motivos[2 * n:3 * n])
    assert all("posterior_al_corte" in m for m in motivos[3 * n:])
    # Ni la historia ni el futuro cambian nada de lo calculado con la captura limpia.
    assert np.allclose(res.paridad.residuo, base.paridad.residuo)
    assert res.asimetria["diferencia_iv"] == pytest.approx(base.asimetria["diferencia_iv"])


def test_ultima_cotizacion_en_la_ventana_de_apertura_excluye_el_contrato(limpia):
    cap, _, _ = limpia
    completa = _con_historia(cap)
    sin_frescas = _sin_filas(completa, _filas(cap, (99.0, 101.0)))  # solo índices de la parte limpia
    res = ca.procesar_captura(sin_frescas)
    assert not np.isin((99.0, 101.0), res.paridad.strike).any()
    tabla = [e for e in res.controles.exclusiones(sin_frescas) if e["strike"] in (99.0, 101.0)]
    en_ventana = [e for e in tabla if "ventana_de_apertura" in e["motivos"]]
    assert len(en_ventana) == 4 and all("reemplazada" not in e["motivos"] for e in en_ventana)
    assert all("desfasada" in e["motivos"] for e in en_ventana)


def test_subyacente_en_la_ventana_de_apertura_genera_alerta(limpia):
    cap, _, _ = limpia
    res = ca.procesar_captura(dataclasses.replace(cap, sello_spot=ca.HORA_APERTURA + 30.0))
    assert any("ventana de apertura" in a for a in res.alertas)
    assert any("desfasado" in a for a in res.alertas)


# --- Serie observada frente a superficie ajustada --------------------------------

def test_residuos_observados_y_superficie_ajustada_son_series_distintas(limpia):
    cap, _, _ = limpia
    bid, ask = cap.bid.copy(), cap.ask.copy()
    i = _filas(cap, (98.0,), es_call=False)[0]
    bid[i] += 0.25
    ask[i] += 0.25
    res = ca.procesar_captura(dataclasses.replace(cap, bid=bid, ask=ask))
    antes = res.paridad.residuo.copy()
    ajuste = ca.ajustar_captura(res)
    assert np.array_equal(res.paridad.residuo, antes)  # el ajuste no toca lo observado
    assert np.max(np.abs(ajuste.residuo_paridad)) < 1e-10  # el ajuste impone la paridad
    j = int(np.flatnonzero(res.paridad.strike == 98.0)[0])
    assert res.paridad.interpretable[j] and res.paridad.interpretable.sum() == 1
    fila = ca.fila_informe(res, ajuste)
    assert fila["obs_paridad_interpretables"] == 1 and fila["aj_paridad_max_abs"] < 1e-10
    assert fila["aj_cotizaciones_fuera"] > 0  # la cotización desviada tensiona el ajuste
    with pytest.raises(ValueError):
        res.captura.bid[0] = 1.0  # la captura cruda es inmutable


# --- Cambios entre sesiones --------------------------------------------------------

def test_diferencias_con_calendario_explicito(limpia):
    cap, _, res = limpia
    viernes = ca.fila_informe(res)
    otra = ca.procesar_captura(dataclasses.replace(_con_desfasadas(cap), fecha="2026-09-28"))
    lunes = ca.fila_informe(otra)
    cambio = ca.diferencia_diaria(lunes, viernes)
    assert cambio["dias_naturales"] == 3 and cambio["sesiones"] == 1 and cambio["cruza_dias_no_habiles"]
    assert cambio["tipo"] == "apertura–apertura"
    assert cambio["cambio_obs_dif_iv_k"] == pytest.approx(lunes["obs_dif_iv_k"] - viernes["obs_dif_iv_k"])
    martes = dict(lunes, fecha="2026-09-29")
    feriado = ca.diferencia_diaria(martes, viernes, feriados=["2026-09-28"])
    assert feriado["dias_naturales"] == 4 and feriado["sesiones"] == 1
    assert not ca.diferencia_diaria(martes, lunes)["cruza_dias_no_habiles"]
    with pytest.raises(ValueError):
        ca.diferencia_diaria(viernes, lunes)
