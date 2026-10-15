"""Derivacion complementaria, profundidad y barridos."""

import datetime as dt
from decimal import Decimal

from btclab.libro import Lado, Libro, Nivel

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 15, 4, 0, tzinfo=UTC)


def libro_profundo():
    return Libro(
        "C", T0, T0,
        compras_yes=(
            Nivel(400, Decimal("100")),
            Nivel(390, Decimal("200")),
            Nivel(380, Decimal("300")),
        ),
        compras_no=(
            Nivel(550, Decimal("50")),
            Nivel(540, Decimal("150")),
            Nivel(530, Decimal("400")),
        ),
    )


def test_venta_derivada_del_lado_opuesto():
    libro = libro_profundo()
    # mejor compra de NO = 0.550 -> mejor venta de YES = 0.450
    assert libro.mejor_compra_mils(Lado.NO) == 550
    assert libro.mejor_venta_mils(Lado.YES) == 450
    assert libro.mejor_compra_mils(Lado.NO) + libro.mejor_venta_mils(Lado.YES) == 1000


def test_escalera_de_ventas_ordenada_de_barata_a_cara():
    precios = [n.precio_mils for n in libro_profundo().ventas(Lado.YES)]
    assert precios == sorted(precios)
    assert precios == [450, 460, 470]


def test_libro_vacio_por_un_lado_no_tiene_ventas_del_otro():
    libro = Libro("C", T0, T0, compras_yes=(Nivel(400, Decimal("1")),), compras_no=())
    assert libro.mejor_venta_mils(Lado.YES) is None
    assert libro.mejor_venta_mils(Lado.NO) == 600


def test_barrido_consume_un_solo_nivel_si_alcanza():
    b = libro_profundo().barrer(Lado.YES, Decimal("50"))
    assert b.completo
    assert len(b.niveles_usados) == 1
    assert b.coste_bruto == Decimal("50") * Decimal("0.450")


def test_barrido_consume_varios_niveles_y_encarece_el_medio():
    b = libro_profundo().barrer(Lado.YES, Decimal("200"))
    assert b.completo
    # 50 a 0.450 + 150 a 0.460 = 22.5 + 69.0 = 91.5
    assert b.coste_bruto == Decimal("91.500")
    assert b.precio_medio > Decimal("0.450")
    assert b.peor_precio_mils == 460


def test_barrido_parcial_cuando_falta_profundidad():
    b = libro_profundo().barrer(Lado.YES, Decimal("10000"))
    assert not b.completo
    assert b.cantidad_llenada == Decimal("600")  # 50 + 150 + 400


def test_limite_corta_el_barrido():
    b = libro_profundo().barrer(Lado.YES, Decimal("500"), limite_mils=460)
    assert b.cantidad_llenada == Decimal("200")
    assert b.peor_precio_mils == 460


def test_limite_por_debajo_del_mejor_no_llena_nada():
    b = libro_profundo().barrer(Lado.YES, Decimal("100"), limite_mils=440)
    assert b.cantidad_llenada == Decimal("0")
    assert b.precio_medio is None


def test_cantidad_cero_o_negativa_no_ejecuta():
    assert libro_profundo().barrer(Lado.YES, Decimal("0")).cantidad_llenada == 0
    assert libro_profundo().barrer(Lado.YES, Decimal("-5")).cantidad_llenada == 0


def test_profundidad_hasta_un_precio():
    libro = libro_profundo()
    assert libro.profundidad(Lado.YES, 450) == Decimal("50")
    assert libro.profundidad(Lado.YES, 460) == Decimal("200")
    assert libro.profundidad(Lado.YES, 470) == Decimal("600")


def test_verificacion_contra_mercado_detecta_desajuste():
    libro = libro_profundo()
    coherente = {
        "yes_bid_dollars": "0.4000",
        "no_bid_dollars": "0.5500",
        "yes_ask_dollars": "0.4500",
        "no_ask_dollars": "0.6000",
    }
    assert libro.verificar_contra_mercado(coherente) == ()
    desajustado = dict(coherente, yes_ask_dollars="0.4600")
    assert libro.verificar_contra_mercado(desajustado) != ()


def test_calidad_marca_cotizacion_caducada():
    libro = libro_profundo()
    tarde = T0 + dt.timedelta(seconds=30)
    motivos = libro.calidad(tarde, antiguedad_max_s=5.0)
    assert any("caducada" in m for m in motivos)
    assert libro.calidad(T0, antiguedad_max_s=5.0) == ()


def test_calidad_marca_libro_sin_snapshot():
    libro = Libro(
        "C", T0, T0,
        compras_yes=(Nivel(400, Decimal("1")),),
        compras_no=(Nivel(550, Decimal("1")),),
        es_snapshot=False,
    )
    assert any("snapshot" in m for m in libro.calidad(T0, 5.0))


def test_desde_payload_del_api_real():
    payload = {
        "orderbook_fp": {
            "yes_dollars": [["0.3300", "10.00"], ["0.3200", "20.00"]],
            "no_dollars": [["0.6600", "30.00"]],
        }
    }
    libro = Libro.desde_payload("C", payload, T0)
    assert libro.mejor_compra_mils(Lado.YES) == 330
    assert libro.mejor_venta_mils(Lado.YES) == 340
    assert libro.ventas(Lado.YES)[0].cantidad == Decimal("30.00")
