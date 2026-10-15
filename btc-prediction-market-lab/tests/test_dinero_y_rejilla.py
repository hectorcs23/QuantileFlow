"""Dinero exacto, rejilla escalonada y redondeos."""

from decimal import Decimal

import pytest

from btclab.dinero import (
    REJILLA_TAPERED_DECI_CENT,
    ErrorDinero,
    Rejilla,
    a_dolares,
    mils,
    redondear_centavos,
    redondear_centavos_arriba,
)


def test_no_se_acepta_float_para_dinero():
    with pytest.raises(ErrorDinero):
        mils(0.45)


def test_precio_fuera_de_la_rejilla_de_mils_falla():
    with pytest.raises(ErrorDinero):
        mils("0.4555")


def test_ida_y_vuelta_mils_dolares():
    for texto in ("0.000", "0.001", "0.450", "0.999", "1.000"):
        assert a_dolares(mils(texto)) == Decimal(texto)


def test_paso_escalonado_por_tramo():
    r = REJILLA_TAPERED_DECI_CENT
    assert r.paso_en(mils("0.050")) == 1      # $0.001 bajo $0.10
    assert r.paso_en(mils("0.450")) == 10     # $0.010 en el centro
    assert r.paso_en(mils("0.950")) == 1      # $0.001 sobre $0.90
    assert r.paso_en(mils("1.000")) == 1      # el extremo cae en el ultimo tramo


def test_precio_central_de_medio_centavo_no_existe():
    r = REJILLA_TAPERED_DECI_CENT
    assert r.es_valido(mils("0.450")) is True
    assert r.es_valido(mils("0.455")) is False   # no hay medio centavo en el centro
    assert r.es_valido(mils("0.045")) is True    # si existe por debajo de $0.10
    assert r.es_valido(mils("0.955")) is True    # y por encima de $0.90


def test_exigir_valido_falla_con_mensaje():
    with pytest.raises(ErrorDinero):
        REJILLA_TAPERED_DECI_CENT.exigir_valido(mils("0.455"))


def test_rejilla_desde_price_ranges_del_api():
    r = Rejilla.desde_price_ranges(
        [
            {"start": "0.0000", "end": "0.1000", "step": "0.0010"},
            {"start": "0.1000", "end": "0.9000", "step": "0.0100"},
            {"start": "0.9000", "end": "1.0000", "step": "0.0010"},
        ],
        "tapered_deci_cent",
    )
    assert r.paso_en(mils("0.500")) == 10
    assert r.es_valido(mils("0.455")) is False


def test_rejilla_con_huecos_se_rechaza():
    with pytest.raises(ErrorDinero):
        Rejilla.desde_price_ranges(
            [
                {"start": "0.0000", "end": "0.1000", "step": "0.0010"},
                {"start": "0.2000", "end": "1.0000", "step": "0.0100"},
            ]
        )


def test_rejilla_que_no_cubre_el_rango_se_rechaza():
    with pytest.raises(ErrorDinero):
        Rejilla.desde_price_ranges(
            [{"start": "0.0000", "end": "0.5000", "step": "0.0010"}]
        )


def test_redondeo_de_comisiones_siempre_hacia_arriba():
    assert redondear_centavos_arriba(Decimal("0.0175")) == Decimal("0.02")
    assert redondear_centavos_arriba(Decimal("0.0100")) == Decimal("0.01")
    assert redondear_centavos_arriba(Decimal("0.0101")) == Decimal("0.02")
    assert redondear_centavos_arriba(Decimal("1.7500")) == Decimal("1.75")


def test_redondeo_de_presentacion_al_mas_cercano():
    assert redondear_centavos(Decimal("0.0149")) == Decimal("0.01")
    assert redondear_centavos(Decimal("0.0150")) == Decimal("0.02")
