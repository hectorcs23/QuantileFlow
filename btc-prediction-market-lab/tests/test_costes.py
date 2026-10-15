"""Comisiones cuadraticas, coste ejecutable, EV, ventaja y perdida maxima."""

import datetime as dt
from decimal import Decimal

import pytest

from btclab.costes import (
    EvaluacionCoste,
    ModeloComisionCuadratica,
    elegible,
    evaluar,
)
from btclab.libro import Barrido, Lado, Libro, Nivel

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 15, 4, 0, tzinfo=UTC)


def modelo(verificada=True):
    return ModeloComisionCuadratica(constante=Decimal("0.07"), verificada=verificada)


def barrido(precio_mils, cantidad):
    coste = Decimal(cantidad) * Decimal(precio_mils) / 1000
    return Barrido(
        Decimal(cantidad), Decimal(cantidad), coste, ((precio_mils, Decimal(cantidad)),)
    )


def test_comision_cuadratica_a_mano():
    # 0.07 * 100 * 0.50 * 0.50 = 1.75
    assert modelo().de_barrido(barrido(500, 100)) == Decimal("1.75")


def test_comision_es_maxima_en_el_centro():
    centro = modelo().de_barrido(barrido(500, 1000))
    borde = modelo().de_barrido(barrido(900, 1000))
    assert centro > borde
    # 0.07 * 1000 * 0.9 * 0.1 = 6.30
    assert borde == Decimal("6.30")


def test_comision_simetrica_respecto_al_centro():
    izquierda = modelo().de_barrido(barrido(300, 1000))
    derecha = modelo().de_barrido(barrido(700, 1000))
    assert izquierda == derecha


def test_una_tarifa_plana_subestimaria_el_centro():
    # Una plana de 1 centavo por contrato daria 1.00 para 100 contratos;
    # la cuadratica da 1.75 en el centro. Por eso no se codifica una plana.
    assert modelo().de_barrido(barrido(500, 100)) > Decimal("1.00")


def test_redondeo_hacia_arriba_por_nivel_es_conservador():
    # 1 contrato a 0.50: 0.0175 -> 0.02 por el techo.
    assert modelo().de_barrido(barrido(500, 1)) == Decimal("0.02")
    por_nivel = ModeloComisionCuadratica(
        constante=Decimal("0.07"), verificada=True, redondeo_por_nivel=True
    )
    agregado = ModeloComisionCuadratica(
        constante=Decimal("0.07"), verificada=True, redondeo_por_nivel=False
    )
    multi = Barrido(
        Decimal("2"), Decimal("2"), Decimal("1.0"),
        ((500, Decimal("1")), (510, Decimal("1"))),
    )
    assert por_nivel.de_barrido(multi) >= agregado.de_barrido(multi)


def test_coste_total_es_libro_mas_comisiones():
    libro = Libro(
        "C", T0, T0,
        compras_yes=(Nivel(400, Decimal("100")),),
        compras_no=(Nivel(550, Decimal("100")),),
    )
    # venta de YES = 1 - 0.550 = 0.450
    ev = evaluar(libro, Lado.YES, Decimal("100"), Decimal("0.60"), modelo())
    assert ev.coste_libro == Decimal("45.000")
    assert ev.coste_total == ev.coste_libro + ev.comisiones
    assert ev.coste_unitario == ev.coste_total / Decimal("100")


def test_ev_y_ventaja_a_mano():
    libro = Libro(
        "C", T0, T0,
        compras_yes=(Nivel(400, Decimal("100")),),
        compras_no=(Nivel(550, Decimal("100")),),
    )
    ev = evaluar(libro, Lado.YES, Decimal("100"), Decimal("0.60"), modelo())
    # comision = 0.07*100*0.45*0.55 = 1.7325 -> techo 1.74
    assert ev.comisiones == Decimal("1.74")
    assert ev.coste_total == Decimal("46.740")
    # EV = 100*0.60 - 46.74 = 13.26
    assert ev.valor_esperado == Decimal("13.260")
    # edge = 0.60 - 0.4674 = 0.1326
    assert ev.ventaja == Decimal("0.60") - Decimal("46.740") / Decimal("100")


def test_el_spread_no_se_suma_dos_veces():
    # Comprar al lado de las ventas ya incorpora el spread: el coste unitario es
    # exactamente el precio de venta mas comisiones, nunca venta + spread.
    libro = Libro(
        "C", T0, T0,
        compras_yes=(Nivel(400, Decimal("100")),),
        compras_no=(Nivel(550, Decimal("100")),),
    )
    ev = evaluar(libro, Lado.YES, Decimal("100"), Decimal("0.60"), modelo())
    sin_comision = ev.coste_libro / Decimal("100")
    assert sin_comision == Decimal("0.450")
    assert libro.spread_mils(Lado.YES) == 50
    assert sin_comision < Decimal("0.450") + Decimal("0.050")


def test_perdida_maxima_es_el_coste_total_comprometido():
    libro = Libro(
        "C", T0, T0,
        compras_yes=(Nivel(400, Decimal("100")),),
        compras_no=(Nivel(550, Decimal("100")),),
    )
    ev = evaluar(libro, Lado.YES, Decimal("100"), Decimal("0.60"), modelo())
    assert ev.perdida_maxima == ev.coste_total
    flujos = ev.flujos_por_resultado()
    assert flujos["pierde"] == -ev.coste_total
    assert flujos["gana"] == Decimal("100") - ev.coste_total


def test_comprar_no_usa_las_ventas_de_no():
    libro = Libro(
        "C", T0, T0,
        compras_yes=(Nivel(400, Decimal("100")),),
        compras_no=(Nivel(550, Decimal("100")),),
    )
    # venta de NO = 1 - mejor compra de YES = 1 - 0.400 = 0.600
    ev = evaluar(libro, Lado.NO, Decimal("100"), Decimal("0.60"), modelo())
    assert ev.coste_libro == Decimal("60.000")


def test_ask_yes_mas_ask_no_no_suman_uno():
    # El supuesto prohibido ask_no = 1 - ask_yes daria 0.550; el valor real es
    # 0.600, porque las dos ventas estan separadas por el spread.
    libro = Libro(
        "C", T0, T0,
        compras_yes=(Nivel(400, Decimal("100")),),
        compras_no=(Nivel(550, Decimal("100")),),
    )
    venta_yes = libro.mejor_venta_mils(Lado.YES)
    venta_no = libro.mejor_venta_mils(Lado.NO)
    assert venta_yes == 450
    assert venta_no == 600
    assert venta_yes + venta_no == 1050
    assert venta_yes + venta_no != 1000


def test_probabilidad_fuera_de_rango_falla():
    libro = Libro("C", T0, T0, compras_yes=(), compras_no=(Nivel(550, Decimal("1")),))
    with pytest.raises(Exception):
        evaluar(libro, Lado.YES, Decimal("1"), Decimal("1.5"), modelo())
