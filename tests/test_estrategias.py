"""Pruebas de propiedades del subproyecto de estrategias (datos sintéticos).

Comprueban identidades matemáticas y que las reglas de abstención se activan
cuando deben. No dicen nada sobre la validez predictiva de ninguna vista: eso
no es demostrable con datos generados por el propio código.
"""
import dataclasses

import numpy as np
import pytest

from quantileflow import decision
from estrategias import distribucion as dist
from estrategias import estructuras as est
from estrategias import evaluacion as ev
from estrategias import precios, recomendacion as rec, robustez, sintetico, vista
from estrategias.informe import escribir_informe


@pytest.fixture(scope="module")
def mundo():
    return sintetico.mundo()


@pytest.fixture(scope="module")
def cfg():
    return rec.cargar_config("configs/estrategias.toml")


def sin_costos(mercado):
    """El mismo mercado sin comisiones ni coste de montar el forward."""
    return dataclasses.replace(mercado, comision=0.0, coste_forward=0.0)


def catalogo_de(mundo, cfg):
    return est.catalogo(mundo["mercado"].F, mundo["strikes_fiables"], cfg.distancias, cfg.anchuras)


# --- Distribución -------------------------------------------------------------

def test_q_sintetica_integra_uno_y_su_media_es_el_forward(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    assert abs(q.p.sum() - 1.0) < 1e-12
    assert q.p.min() >= 0.0
    assert abs(q.media / F - 1.0) < 1e-4
    # Las dos reconstrucciones independientes de Q coinciden en lo esencial.
    assert abs(mundo["q_alternativa"].media / F - 1.0) < 1e-4
    assert abs(mundo["q_alternativa"].momentos_log(F)["sd_log"]
               - q.momentos_log(F)["sd_log"]) < 5e-3


@pytest.mark.parametrize("estropear", [
    lambda s, p: (s, p * 2.0),                      # no suma 1
    lambda s, p: (s, np.where(np.arange(len(p)) == 3, -0.1, p)),  # negativa
    lambda s, p: (np.linspace(50.0, 150.0, len(s)), p),           # malla no geométrica
])
def test_distribucion_rechaza_entradas_invalidas(mundo, estropear):
    q = mundo["q"]
    s, p = estropear(q.s.copy(), q.p.copy())
    with pytest.raises(ValueError):
        dist.Distribucion(s, p, q.rango_fiable, "prueba")


def test_integral_de_la_cdf_es_el_precio_del_put(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    for K in F * np.array([0.85, 0.95, 1.0, 1.05]):
        assert abs(ev.integral_cdf(q, 0.0, K) - q.precio_put(K)) < 1e-10


def test_paridad_put_call_en_la_distribucion(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    for K in F * np.array([0.9, 1.0, 1.1]):
        assert abs((q.precio_call(K) - q.precio_put(K)) - (q.media - K)) < 1e-9


def test_cuantiles_son_crecientes_y_coherentes_con_la_cdf(mundo):
    q = mundo["q"]
    u = np.array([0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99])
    x = q.cuantil(u)
    assert np.all(np.diff(x) > 0.0)
    assert np.all(q.cdf(x) >= u - 1e-12)


# --- Vistas -------------------------------------------------------------------

def test_tilt_de_media_alcanza_el_objetivo(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    for r in (-0.02, -0.005, 0.005, 0.02):
        p = vista.tilt_media(q, F, r)
        assert abs(p.media / F - (1.0 + r)) < 1e-10


def test_el_tilt_es_la_deformacion_de_minima_entropia(mundo):
    """Un desplazamiento con la misma media cuesta más entropía relativa."""
    q, F = mundo["q"], mundo["mercado"].F
    r = 0.01
    p_tilt = vista.tilt_media(q, F, r)
    p_desp = vista.desplazar(q, np.log1p(r))
    assert abs(p_desp.media / F - (1.0 + r)) < 1e-3
    assert dist.kl(p_tilt, q) < dist.kl(p_desp, q)


def test_tilt_de_momentos_fija_media_y_dispersion(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    p = vista.tilt_momentos(q, F, 0.008, 0.9)
    assert abs(p.media / F - 1.008) < 1e-6
    assert abs(p.momentos_log(F)["sd_log"] / q.momentos_log(F)["sd_log"] - 0.9) < 1e-6


def test_reponderar_cola_respeta_el_factor_y_puede_preservar_la_media(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    zona = np.log(q.s / F) <= -0.05
    for preservar in (False, True):
        p = vista.reponderar_cola(q, 0.8, -0.05, preservar_media=preservar)
        assert abs(p.p[zona].sum() / q.p[zona].sum() - 0.8) < 1e-12
        assert np.all(p.p[zona] <= q.p[zona] + 1e-15)
        if preservar:
            assert abs(p.media / q.media - 1.0) < 1e-7
        else:
            assert p.media > q.media  # quitar masa de la cola sube el resto


def test_vista_desde_cuantiles_reproduce_los_cuantiles(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    u = np.array([0.05, 0.25, 0.5, 0.75, 0.95])
    objetivo = q.cuantil(u)
    p = vista.desde_cuantiles(q, F, u, np.log(objetivo / F))
    assert np.max(np.abs(p.cuantil(u) / objetivo - 1.0)) < 2e-3


def test_mezcla_promedia_las_probabilidades(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    a, b = vista.tilt_media(q, F, 0.01), vista.tilt_media(q, F, -0.01)
    m = vista.mezcla([a, b], [0.25, 0.75])
    assert np.allclose(m.p, 0.25 * a.p + 0.75 * b.p)
    assert abs(m.media - (0.25 * a.media + 0.75 * b.media)) < 1e-9


# --- Ventaja: la identidad que lo ordena todo ---------------------------------

def test_sin_desacuerdo_la_ventaja_es_exactamente_cero(mundo, cfg):
    """El invariante central: con ``P = Q`` y sin costos, nada tiene ventaja."""
    q, mercado = mundo["q"], sin_costos(mundo["mercado"])
    p = vista.neutral(q)
    for estructura in catalogo_de(mundo, cfg):
        e = ev.evaluar(estructura, p, q, mercado, modo=precios.MEDIO)
        assert abs(e.ventaja_sin_costos) < 1e-12, estructura.nombre
        if e.identificada:
            # Con el mid y sin comisiones, el precio ejecutable es el valor bajo Q
            # salvo el ancho de banda de las cotizaciones.
            assert abs(e.valor_q - e.precio) < 0.05, estructura.nombre


def test_ventaja_de_un_put_corto_es_la_integral_de_la_diferencia_de_cdfs(mundo):
    q, F, D = mundo["q"], mundo["mercado"].F, mundo["mercado"].D
    p = vista.tilt_media(q, F, 0.01)
    mercado = sin_costos(mundo["mercado"])
    for K in (92.0, 95.0, 97.0):
        e = ev.evaluar(est.put_corto(K), p, q, mercado, modo=precios.MEDIO)
        identidad = D * (ev.integral_cdf(q, 0.0, K) - ev.integral_cdf(p, 0.0, K))
        assert abs(e.ventaja_sin_costos - identidad) < 1e-10
        assert abs(ev.ventaja_put_por_strike(p, q, D, [K])[0] - identidad) < 1e-10


def test_ventaja_de_un_spread_es_la_integral_en_su_tramo(mundo):
    q, F, D = mundo["q"], mundo["mercado"].F, mundo["mercado"].D
    p = vista.tilt_media(q, F, 0.01)
    mercado = sin_costos(mundo["mercado"])
    K1, K2 = 92.0, 97.0
    e = ev.evaluar(est.put_spread_alcista(K1, K2), p, q, mercado, modo=precios.MEDIO)
    tramo = ev.ventaja_por_tramos(p, q, D, [K1, K2])[0]["ventaja"]
    assert abs(e.ventaja_sin_costos - tramo) < 1e-10


def test_comprar_y_vender_la_misma_estructura_tienen_ventaja_opuesta(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    p = vista.tilt_media(q, F, 0.01)
    mercado = sin_costos(mundo["mercado"])
    corto = ev.evaluar(est.put_corto(95.0), p, q, mercado, modo=precios.MEDIO)
    largo = ev.evaluar(est.put_largo(95.0), p, q, mercado, modo=precios.MEDIO)
    assert abs(corto.ventaja_sin_costos + largo.ventaja_sin_costos) < 1e-12
    assert abs(corto.ventaja + largo.ventaja) < 1e-12


def test_una_vista_mas_alcista_mejora_la_venta_de_puts(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    mercado = sin_costos(mundo["mercado"])
    ventajas = [ev.evaluar(est.put_corto(95.0), vista.tilt_media(q, F, r), q, mercado,
                           modo=precios.MEDIO).ventaja for r in (-0.01, 0.0, 0.005, 0.01)]
    assert np.all(np.diff(ventajas) > 0.0)
    # Con la vista centrada en el forward lo único que queda es el residuo del
    # ajuste, que no es ventaja. La diferencia restante es que la media de Q no
    # cae exactamente en el forward, así que el tilt de media a cero no devuelve
    # exactamente Q.
    residuo = ev.evaluar(est.put_corto(95.0), vista.neutral(q), q, mercado,
                         modo=precios.MEDIO).residuo_ajuste
    assert abs(q.media / F - 1.0) < 1e-4
    assert ventajas[1] == pytest.approx(residuo, abs=5e-4)
    assert abs(residuo) < 0.05


# --- Riesgo y contabilidad -----------------------------------------------------

def test_var_cvar_discreto_coincide_con_el_del_nucleo():
    rng = np.random.default_rng(3)
    perdidas = rng.normal(size=400)
    var_d, cvar_d = ev.var_cvar_discreto(perdidas, np.full(400, 1 / 400), 0.95)
    var_n, cvar_n = decision.var_cvar(perdidas, 0.95)
    assert var_d == pytest.approx(var_n)
    assert cvar_d == pytest.approx(cvar_n, rel=1e-9)


def test_cvar_no_es_menor_que_var_ni_que_la_perdida_esperada(mundo):
    q, F = mundo["q"], mundo["mercado"].F
    p = vista.tilt_media(q, F, 0.01)
    for estructura in (est.put_corto(95.0), est.put_largo(95.0),
                       est.put_spread_alcista(92.0, 97.0)):
        e = ev.evaluar(estructura, p, q, mundo["mercado"])
        assert e.cvar >= e.var - 1e-12
        assert e.perdida_maxima >= e.cvar - 1e-9


def test_equilibrio_y_extremos_de_un_put_corto(mundo):
    q, D = mundo["q"], mundo["mercado"].D
    p, K = vista.neutral(q), 95.0
    e = ev.evaluar(est.put_corto(K), p, q, mundo["mercado"])
    prima = -(e.precio + e.comisiones) / D          # crédito capitalizado
    assert e.equilibrio == pytest.approx((K - prima,), abs=1e-6)
    assert e.perdida_maxima == pytest.approx(K - prima)
    assert e.ganancia_maxima == pytest.approx(prima)
    assert e.capital == pytest.approx(D * K - (-(e.precio + e.comisiones)))


def test_perdida_maxima_de_un_spread_es_la_anchura_menos_el_credito(mundo):
    q = mundo["q"]
    K1, K2, D = 92.0, 97.0, mundo["mercado"].D
    e = ev.evaluar(est.put_spread_alcista(K1, K2), vista.neutral(q), q, mundo["mercado"])
    credito = -(e.precio + e.comisiones) / D
    assert e.perdida_maxima == pytest.approx((K2 - K1) - credito)
    assert e.ganancia_maxima == pytest.approx(credito)


def test_la_ejecucion_adversa_nunca_es_mejor_que_el_mid(mundo, cfg):
    q, F = mundo["q"], mundo["mercado"].F
    p = vista.tilt_media(q, F, 0.01)
    for estructura in catalogo_de(mundo, cfg):
        a = ev.evaluar(estructura, p, q, mundo["mercado"], modo=precios.ADVERSO)
        m = ev.evaluar(estructura, p, q, mundo["mercado"], modo=precios.MEDIO)
        if a.identificada and m.identificada:
            assert a.ventaja <= m.ventaja + 1e-12, estructura.nombre
            assert a.coste_ejecucion >= -1e-12


def test_una_pata_sin_cotizacion_invalida_la_estructura(mundo):
    q = mundo["q"]
    e = ev.evaluar(est.put_corto(1.0), vista.neutral(q), q, mundo["mercado"])
    assert not e.identificada and "sin cotización" in e.motivo


def test_la_paridad_completa_la_pata_que_falta(mundo):
    mercado = mundo["mercado"]
    reb = mundo["rebanada"]
    for K in mundo["strikes_fiables"][:5]:
        call, put = mercado.cotizaciones[("call", K)], mercado.cotizaciones[("put", K)]
        assert abs((call.mid - put.mid) - reb.D * (reb.F - K)) < 1e-9
        assert call.via_paridad != put.via_paridad


# --- Zona no identificada ------------------------------------------------------

def test_la_zona_sin_cotizaciones_se_mide_y_acota(mundo):
    q, F, D = mundo["q"], mundo["mercado"].F, mundo["mercado"].D
    p = vista.tilt_media(q, F, 0.01)
    lo, _ = q.rango_fiable
    dentro = ev.zona_no_fiable(p, q, est.put_corto(F), D)
    fuera = ev.zona_no_fiable(p, q, est.put_corto(lo * 0.9), D)
    # Un put por debajo del rango fiable depende íntegramente de la extrapolación.
    e_fuera = D * (q.precio_put(lo * 0.9) - p.precio_put(lo * 0.9))
    assert abs(fuera["contribucion"] - e_fuera) < 1e-12
    assert abs(dentro["contribucion"]) <= dentro["cota"] + 1e-12
    assert ev.zona_no_fiable(p, q, est.call_largo(F), D)["cola_abierta"]


# --- Reglas y dictamen ---------------------------------------------------------

def test_el_papel_en_puts_clasifica_por_prima_neta(mundo):
    q = mundo["q"]
    assert rec.papel_en_puts(est.put_spread_alcista(92.0, 97.0), q) == rec.VENDER_PUTS
    assert rec.papel_en_puts(est.put_spread_bajista(92.0, 97.0), q) == rec.COMPRAR_PUTS
    assert rec.papel_en_puts(est.put_corto(95.0), q) == rec.VENDER_PUTS
    assert rec.papel_en_puts(est.collar(95.0, 105.0), q) == rec.COMPRAR_PUTS
    assert rec.papel_en_puts(est.call_largo(105.0), q) == rec.SIN_PUTS


def test_sin_opinion_el_dictamen_es_abstenerse(mundo, cfg):
    q = mundo["q"]
    r = rec.recomendar(catalogo_de(mundo, cfg), vista.neutral(q), q, mundo["mercado"], cfg)
    assert r["dictamen"]["accion"] == rec.ABSTENERSE
    assert r["aptas"] == []
    assert all(f["evaluacion"].ventaja <= 1e-12 for f in r["filas"] if f["evaluacion"].identificada)


def test_una_vista_demasiado_fuerte_cierra_la_puerta(mundo, cfg):
    q, F = mundo["q"], mundo["mercado"].F
    r = rec.recomendar(catalogo_de(mundo, cfg), vista.tilt_media(q, F, 0.05), q,
                       mundo["mercado"], cfg)
    assert r["motivos_globales"] and "KL" in r["motivos_globales"][0]
    assert r["dictamen"]["accion"] == rec.ABSTENERSE


def test_una_vista_alcista_recomienda_vender_puts(mundo, cfg):
    q, F = mundo["q"], mundo["mercado"].F
    p = vista.tilt_media(q, F, 0.01)
    r = rec.recomendar(catalogo_de(mundo, cfg), p, q, mundo["mercado"], cfg,
                       mundo["q_alternativa"])
    assert r["dictamen"]["accion"] == rec.OPERAR
    assert r["dictamen"]["estructura"]["papel"] == rec.VENDER_PUTS
    # Comprar puts con una vista alcista no puede salir a cuenta.
    assert r["dictamen"]["mejor_compra_puts"]["papel"] == rec.COMPRAR_PUTS
    assert not any(f["apta"] for f in r["filas"] if f["papel"] == rec.COMPRAR_PUTS)


def test_una_vista_bajista_da_la_vuelta_al_dictamen(mundo, cfg):
    q, F = mundo["q"], mundo["mercado"].F
    r = rec.recomendar(catalogo_de(mundo, cfg), vista.tilt_media(q, F, -0.01), q,
                       mundo["mercado"], cfg, mundo["q_alternativa"])
    assert r["dictamen"]["accion"] == rec.OPERAR
    assert r["dictamen"]["estructura"]["papel"] == rec.COMPRAR_PUTS
    assert not any(f["apta"] for f in r["filas"] if f["papel"] == rec.VENDER_PUTS)


def test_los_escenarios_de_robustez_no_degeneran_en_q(mundo):
    """El escenario direccional solo aparece si la vista afirma una dirección."""
    q, F = mundo["q"], mundo["mercado"].F
    direccional = robustez.escenarios_estandar(vista.tilt_media(q, F, 0.01), q, F)
    de_cola = robustez.escenarios_estandar(
        vista.reponderar_cola(q, 0.8, -0.05, preservar_media=True), q, F)
    assert any("dispersión" in e.nombre for e in direccional)
    assert not any("dispersión" in e.nombre for e in de_cola)


def test_el_peor_caso_nunca_supera_el_caso_base(mundo, cfg):
    q, F = mundo["q"], mundo["mercado"].F
    p = vista.tilt_media(q, F, 0.01)
    escenarios = robustez.escenarios_estandar(p, q, F, cfg.modo_ejecucion, mundo["q_alternativa"])
    for estructura in catalogo_de(mundo, cfg):
        r = robustez.robustez(estructura, mundo["mercado"], escenarios, cfg.alfa)
        base = r["evaluaciones"]["base"]
        if base.identificada:
            assert r["ventaja_peor_caso"] <= base.ventaja + 1e-12, estructura.nombre


# --- Informe --------------------------------------------------------------------

def test_el_informe_se_escribe_y_es_reproducible(mundo, cfg, tmp_path):
    q, F, mercado = mundo["q"], mundo["mercado"].F, mundo["mercado"]
    p = vista.tilt_media(q, F, 0.01)
    r = rec.recomendar(catalogo_de(mundo, cfg), p, q, mercado, cfg, mundo["q_alternativa"])
    textos = []
    for i in (1, 2):
        salida = tmp_path / f"corrida{i}"
        rutas = escribir_informe(r, p, q, mercado, salida, "Prueba", aviso="datos sintéticos")
        assert rutas["informe"].exists() and rutas["candidatas"].exists()
        textos.append(rutas["informe"].read_text(encoding="utf-8"))
    assert textos[0] == textos[1]
    assert r["dictamen"]["texto"] in textos[0]
    assert "recomendación de inversión" in textos[0]
