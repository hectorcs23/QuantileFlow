from dataclasses import replace

import pytest

from quantileflow.escenarios import (ContratoEscenario, Escenario, comparar_contratos,
                                    sensibilidad_europea, valor_en_escenario)


def contrato(**kw):
    return replace(ContratoEscenario("C100", 100, 30, True, "europeo", .25, 2.8, 3.), **kw)


def test_sensibilidad_coincide_con_reprecio_pequeno_y_put_call_parity():
    c = contrato()
    s = sensibilidad_europea(100, 100, 30, .25)
    base = valor_en_escenario(c, 100, Escenario("hoy", 0, 0))
    subida = valor_en_escenario(c, 100, Escenario("sube", 0, .0001))
    assert subida-base == pytest.approx(s['delta']*.01+.5*s['gamma']*.01**2, abs=1e-8)
    put = sensibilidad_europea(100, 100, 30, .25, es_call=False)
    assert s['delta']-put['delta'] == pytest.approx(1.)
    assert s['gamma'] == pytest.approx(put['gamma'])


def test_valor_al_vencimiento_y_rechazo_escenario_posterior():
    assert valor_en_escenario(contrato(), 100, Escenario("vence", 30, .05)) == pytest.approx(5)
    with pytest.raises(ValueError, match="después"):
        valor_en_escenario(contrato(), 100, Escenario("tarde", 31, .05))


def test_presupuesto_spread_costos_contratos_enteros_y_sin_probabilidades():
    c = contrato()
    r = comparar_contratos([c], 100, [Escenario("hoy", 0, 0)], 700, comision=1., semispread_salida=.1)
    a = r['contratos'][0]
    assert a['contratos'] == 2
    assert a['desembolso'] == 602
    assert a['efectivo_sobrante'] == 98
    assert a['reserva_comision_cierre'] == 2 and a['efectivo_libre'] == 96
    assert a['escenarios']['hoy']['pnl'] == pytest.approx(
        2*(a['escenarios']['hoy']['valor_teorico']-.1)*100-2-602)
    assert r['probabilidades'] == 'no estimadas'


def test_presupuesto_reserva_tambien_comision_de_salida():
    r = comparar_contratos([contrato()], 100, [Escenario('pierde', 30, -.5)], 301.5, comision=1.)
    assert not r['contratos']  # prima + entrada cabrían; falta reservar el cierre
    r = comparar_contratos([contrato()], 100, [Escenario('pierde', 30, -.5)], 302, comision=1.)
    assert r['contratos'][0]['escenarios']['pierde']['pnl'] == -302


def test_vencimiento_corto_no_se_premia_por_usar_precio_posterior():
    r = comparar_contratos([contrato(dte=7)], 100, [Escenario("tarde", 14, .05)], 500)
    assert not r['contratos'] and r['excluidos'][0]['motivo'] == 'vence antes de un escenario'


def test_americano_put_ejercicio_anticipado_y_convergencia_call_sin_dividendos():
    deep = contrato(strike=130, es_call=False, ejercicio='americano')
    assert valor_en_escenario(deep, 100, Escenario('hoy', 0, 0)) >= 30
    c = contrato()
    europea = valor_en_escenario(c, 100, Escenario('hoy', 0, 0))
    americana = valor_en_escenario(replace(c, ejercicio='americano'), 100, Escenario('hoy', 0, 0), pasos=1000)
    assert americana == pytest.approx(europea, abs=.005)


def test_dividendos_futuros_se_reubican_al_reprecio_y_invalidos_se_rechazan():
    c = contrato(ejercicio='americano')
    despues = valor_en_escenario(c, 100, Escenario('salida', 14, .03), dividendos=((10, 1), (20, .5)))
    equivalente = valor_en_escenario(replace(c, dte=16), 103, Escenario('hoy', 0, 0), dividendos=((6, .5),))
    assert despues == pytest.approx(equivalente)
    with pytest.raises(ValueError):
        valor_en_escenario(c, 100, Escenario('mal', 0, 0), dividendos=((20, -1),))


def test_iv_baja_y_tiempo_pueden_compensar_subida_del_subyacente():
    c = contrato()
    base = valor_en_escenario(c, 100, Escenario('hoy', 0, 0))
    futuro = valor_en_escenario(c, 100, Escenario('sube', 25, .01, -.15))
    assert futuro < base
