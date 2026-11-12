"""Presupuesto común: contratos completos, caja, riesgo y exposición monetaria."""
from dataclasses import replace

import pytest

from quantileflow.escenarios import ContratoEscenario, Escenario
from quantileflow.posiciones import comparar_posiciones


def candidatos():
    # Primas inventadas para verificar contabilidad con payoffs exactos.
    return [ContratoEscenario("barato", 108, 30, True, "europeo", .25, 1., 1.),
            ContratoEscenario("caro", 105, 30, True, "europeo", .25, 3., 3.)]


def comparar(cs=None, **opciones):
    kw = dict(comision=0, semispread_salida=0, nodos=401, pasos=400)
    kw.update(opciones)
    return comparar_posiciones(candidatos() if cs is None else cs, 100,
        [Escenario("objetivo", 30, .10), Escenario("menor_subida", 30, .07)],
        300, "objetivo", **kw)


def test_tres_de_cien_superan_uno_de_trescientos_por_posicion_no_por_contrato():
    r = comparar()
    barato, caro = r["posiciones"]
    assert (barato["cantidad"], caro["cantidad"]) == (3, 1)
    b, c = [f["escenarios"]["objetivo"] for f in (barato, caro)]
    assert b["pnl_por_contrato"] == pytest.approx(100)
    assert c["pnl_por_contrato"] == pytest.approx(200)
    assert b["pnl_posicion"] == pytest.approx(300)
    assert c["pnl_posicion"] == pytest.approx(200)
    assert b["capital_final_incluyendo_caja"] == pytest.approx(600)
    assert b["retorno_presupuesto"] == pytest.approx(1)
    assert r["comparacion_presupuesto"]["mejor_en_objetivo_incluyendo_caja"] == "barato"
    # Ser más barato no garantiza ser mejor ante una subida menor.
    assert barato["escenarios"]["menor_subida"]["pnl_posicion"] == -300
    assert caro["escenarios"]["menor_subida"]["pnl_posicion"] == -100
    assert r["alternativa_robusta"] == "efectivo"


def test_comisiones_cambian_cantidad_y_caja_sin_rebasar_trescientos():
    r = comparar(comision=.65)
    assert r["excluidos"] == [{"contrato": "caro", "motivo": "no cabe en presupuesto"}]
    f = r["posiciones"][0]
    assert f["cantidad"] == 2
    assert f["prima_por_contrato"] == 100
    assert f["capital_reservado_por_contrato"] == pytest.approx(101.3)
    assert f["desembolso_entrada"] == pytest.approx(201.3)
    assert f["reserva_comision_cierre"] == pytest.approx(1.3)
    assert f["capital_reservado"] == pytest.approx(202.6)
    assert f["efectivo_libre"] == pytest.approx(97.4)
    objetivo = f["escenarios"]["objetivo"]
    assert objetivo["pnl_posicion"] == pytest.approx(197.4)
    assert objetivo["capital_final_incluyendo_caja"] == pytest.approx(497.4)
    assert objetivo["retorno_presupuesto"] == pytest.approx(197.4 / 300)
    assert objetivo["retorno_capital_reservado"] == pytest.approx(197.4 / 202.6)


def test_multiplicador_real_y_sensibilidad_total_no_suponen_cien():
    c = replace(candidatos()[0], multiplicador=10, bid=10., ask=10.)
    r = comparar([c])
    f, base = r["posiciones"][0], r["contratos"][0]
    assert f["cantidad"] == 3
    assert f["prima_total"] == 300
    assert f["escenarios"]["objetivo"]["pnl_posicion"] == pytest.approx(-240)
    for campo, valor in f["sensibilidad_posicion"].items():
        assert valor == pytest.approx(30 * base["sensibilidad_entrada"][campo])
    assert r["comparacion_presupuesto"]["mejor_en_objetivo_incluyendo_caja"] == "efectivo"


@pytest.mark.parametrize("opciones", [{"limite_perdida": 100}, {"limites_cantidad": {"barato": 1, "caro": 0}}])
def test_limites_conservan_el_presupuesto_original_para_comparar(opciones):
    r = comparar(**opciones)
    f = r["posiciones"][0]
    assert f["cantidad"] == 1
    assert f["capital_reservado"] == 100
    assert f["efectivo_libre"] == 200
    assert f["escenarios"]["objetivo"]["capital_final_incluyendo_caja"] == pytest.approx(400)
    assert f["escenarios"]["objetivo"]["retorno_presupuesto"] == pytest.approx(1 / 3)


def test_sin_capital_arriesgable_conserva_caja_y_no_inventa_ganador():
    r = comparar(limite_perdida=0)
    assert r["posiciones"] == []
    v = r["comparacion_presupuesto"]
    assert v["mejor_en_objetivo_incluyendo_caja"] == "efectivo"
    assert v["efectivo"] == {"capital_inicial": 300, "capital_final": 300, "pnl": 0.}
    assert v["probabilidades_escenarios"] == "no estimadas"


def test_cashflow_independiente_antes_de_vencer():
    c = replace(candidatos()[0], strike=105)
    r = comparar_posiciones([c], 100, [Escenario("objetivo", 7, .03)], 300,
        "objetivo", comision=.65, semispread_salida=.04, nodos=401, pasos=400)
    f, base = r["posiciones"][0], r["contratos"][0]
    # 300 iniciales - 201.30 pagados + venta neta de dos contratos.
    venta = 2 * (100 * base["escenarios"]["objetivo"]["precio_salida_asumido"] - .65)
    assert f["escenarios"]["objetivo"]["capital_final_incluyendo_caja"] == pytest.approx(98.7 + venta)
    assert f["capital_reservado"] + f["efectivo_libre"] == pytest.approx(300)
