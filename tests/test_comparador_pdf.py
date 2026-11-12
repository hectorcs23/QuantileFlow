"""Contabilidad independiente, horizontes y decisiones condicionadas del comparador."""
from dataclasses import replace

import pytest

from quantileflow.comparador import comparar_con_pdf
from quantileflow.escenarios import ContratoEscenario, Escenario, comparar_contratos, valor_en_escenario
from quantileflow.opciones import precio_bs


def contrato(**kw):
    return replace(ContratoEscenario("C100", 100, 30, True, "europeo", .25, 2.8, 3.), **kw)


def comparar(cs, es, presupuesto=700, **kw):
    return comparar_con_pdf(cs, 100, es, presupuesto, es[0].nombre, nodos=401, pasos=400, **kw)


@pytest.mark.parametrize("call", [True, False])
@pytest.mark.parametrize("retorno,choque", [(.03, -.05), (-.04, .05)])
def test_reprecio_y_pnl_con_oraculo_bs_independiente(call, retorno, choque):
    c = contrato(es_call=call)
    e = Escenario("salida", 7, retorno, choque)
    r = comparar([c], [e], comision=1., semispread_salida=.1, tasa=.04, q=.013)
    f = r["contratos"][0]
    esperado = float(precio_bs(100*(1+retorno), 100, 23/365, .04, .013, .25+choque, call))
    assert f["contratos"] == 2
    assert f["escenarios"]["salida"]["valor_teorico"] == pytest.approx(esperado, abs=.004)
    assert f["pnl_objetivo"] == pytest.approx(2*(max(0, esperado-.1)*100-302), abs=.8)
    assert f["capital_reservado"] == 604
    assert f["efectivo_libre"] == 96
    assert f["perdida_maxima_costos_asumidos"] <= 700
    dx = f["escenarios"]["salida"]["diagnostico_pde"]
    assert 0 <= dx["probabilidad_q_itm_al_vencimiento"] <= 1
    assert dx["cuantil_q_05"] < dx["cuantil_q_95"]
    assert dx["error_dualidad"] < 1e-10


def test_limite_de_perdida_reserva_ambas_comisiones_y_deja_caja():
    e = [Escenario("vence_sin_valor", 30, -.5)]
    assert not comparar([contrato()], e, limite_perdida=301.99, comision=1.)["contratos"]
    r = comparar([contrato()], e, limite_perdida=302, comision=1.)
    f = r["contratos"][0]
    assert f["contratos"] == 1 and f["pnl_objetivo"] == -302
    assert f["efectivo_libre"] == 398
    assert r["alternativa_robusta"] == "efectivo"
    assert not comparar([contrato()], e, limite_perdida=0)["contratos"]


def test_vencimiento_exacto_y_no_usar_stock_posterior_para_opcion_vencida():
    e = [Escenario("movimiento", 7, .05)]
    r = comparar([contrato(dte=7), contrato(identificador="vence6", dte=6)], e)
    f = r["contratos"][0]
    assert f["escenarios"]["movimiento"]["valor_teorico"] == 5.
    assert f["escenarios"]["movimiento"]["precio_salida_asumido"] == 5.
    assert f["escenarios"]["movimiento"]["diagnostico_pde"] == {}
    assert r["excluidos"] == [{"contrato": "vence6", "motivo": "vence antes de un escenario"}]


def test_rankings_separan_dolares_porcentaje_y_robustez_sin_score():
    # Payoffs exactos a S=110: A +400 sobre 400; B +500 sobre 600;
    # C +120 sobre 480 (dos contratos de multiplicador 10).
    # A S=105, A pierde 100, B queda en cero y C gana 20.
    cs = [contrato(identificador="A", strike=102, ask=4, bid=4),
          contrato(identificador="B", strike=99, ask=6, bid=6),
          contrato(identificador="C", strike=80, ask=24, bid=24, multiplicador=10)]
    es = [Escenario("objetivo", 30, .10), Escenario("adverso", 30, .05)]
    r = comparar(cs, es, comision=0, semispread_salida=0)
    assert r["rankings"]["ganancia_objetivo"] == ["B", "A", "C"]
    assert r["rankings"]["retorno_objetivo"] == ["A", "B", "C"]
    assert r["rankings"]["robustez"] == ["C", "B", "A"]
    assert r["alternativa_robusta"] == "C"


def test_abstencion_aunque_itm_q_sea_alta_y_escenarios_favorables():
    c = contrato(strike=70, ask=60, bid=59)
    r = comparar([c], [Escenario("sube", 3, .02)], presupuesto=7000)
    f = r["contratos"][0]
    assert f["escenarios"]["sube"]["diagnostico_pde"]["probabilidad_q_itm_al_vencimiento"] > .99
    assert f["pnl_objetivo"] < 0
    assert r["alternativa_robusta"] == "efectivo"
    assert r["probabilidades"] == "no estimadas"


def test_pde_no_convierte_americano_ni_dividendos_en_europeo():
    e = [Escenario("hoy", 0, 0)]
    with pytest.raises(ValueError, match="europeo"):
        comparar([contrato(ejercicio="americano")], e)
    with pytest.raises(ValueError, match="efectivo"):
        valor_en_escenario(contrato(), 100, e[0], dividendos=((10, 1),), motor="pde")
    # El motor anterior sigue disponible, con tratamiento americano separado.
    assert valor_en_escenario(contrato(es_call=False, strike=130, ejercicio="americano"),
                             100, e[0]) >= 30


def test_empates_son_deterministas_e_invariantes_al_orden():
    cs = [contrato(identificador="B"), contrato(identificador="A")]
    es = [Escenario("vence", 30, .1)]
    a, b = comparar(cs, es), comparar(reversed(cs), es)
    assert a["rankings"] == b["rankings"]
    assert a["rankings"]["robustez"] == ["A", "B"]


@pytest.mark.parametrize("limite", [-1, float("inf"), float("nan")])
def test_limites_invalidos(limite):
    with pytest.raises(ValueError):
        comparar([contrato()], [Escenario("hoy", 0, 0)], limite_perdida=limite)


def test_nombres_duplicados_y_objetivo_inexistente_rechazados():
    e = Escenario("hoy", 0, 0)
    with pytest.raises(ValueError, match="únicos"):
        comparar([contrato()], [e, e])
    with pytest.raises(ValueError, match="únicos"):
        comparar([contrato(), contrato()], [e])
    with pytest.raises(ValueError, match="objetivo"):
        comparar_con_pdf([contrato()], 100, [e], 500, "inexistente")


def test_generador_dividendos_reutilizado_por_cada_contrato_clasico():
    cs = [contrato(identificador="A"), contrato(identificador="B")]
    es = [Escenario("hoy", 0, 0)]
    r = comparar_contratos(cs, 100, es, 700, dividendos=((d, m) for d, m in [(10, 1.)]))
    a, b = [f["escenarios"]["hoy"]["valor_teorico"] for f in r["contratos"]]
    assert a == b


def test_dominio_corto_no_produce_ganador_por_error_de_truncamiento():
    c = contrato(dte=365, iv=.6)
    r = comparar_con_pdf([c], 100, [Escenario("hoy", 0, .03)], 700, "hoy",
                         nodos=101, pasos=100, semiancho=.1)
    assert not r["contratos"]
    assert r["alternativa_robusta"] == "efectivo"
    assert r["excluidos"][0]["motivo"] == "dominio o momento numérico insuficiente"


def test_sensibilidades_de_entrada_describen_cambios_pequenos_no_cambios_grandes():
    c = contrato()
    e = [Escenario("hoy", 0, 0), Escenario("pequeno", .0001, .00001, .00001)]
    r = comparar([c], e)
    f = r["contratos"][0]
    g = f["sensibilidad_entrada"]
    aproximado = g["delta"]*.001 + .5*g["gamma"]*.001**2 + g["vega_por_punto_iv"]*.001 + g["theta_por_dia"]*.0001
    real = f["escenarios"]["pequeno"]["valor_teorico"]-f["escenarios"]["hoy"]["valor_teorico"]
    assert real == pytest.approx(aproximado, abs=1e-7)
