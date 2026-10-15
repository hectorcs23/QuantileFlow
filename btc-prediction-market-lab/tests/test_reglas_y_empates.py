"""Reglas de liquidacion, operador y tratamiento del empate."""

import datetime as dt
from decimal import Decimal

import pytest

from btclab.contrato import (
    ErrorContrato,
    Operador,
    ReglaLiquidacion,
    operador_desde_strike_type,
)


def regla(operador, umbral="80000", **kwargs):
    return ReglaLiquidacion(
        indice="BRTI",
        agencia_fuente="CF Benchmarks",
        ventana_promedio_s=60,
        operador=operador,
        umbral=Decimal(umbral),
        **kwargs,
    )


def test_empate_con_mayor_o_igual_liquida_yes():
    # Los terminos del contrato: "at least X" significa "X o mayor".
    r = regla(Operador.MAYOR_O_IGUAL)
    assert r.resuelve_yes(Decimal("80000")) is True
    assert r.operador.empate_liquida_yes is True


def test_empate_con_mayor_estricto_liquida_no():
    # "Above X" significa estrictamente mayor que X.
    r = regla(Operador.MAYOR)
    assert r.resuelve_yes(Decimal("80000")) is False
    assert r.operador.empate_liquida_yes is False


def test_un_centavo_arriba_y_abajo_del_umbral():
    r = regla(Operador.MAYOR_O_IGUAL, umbral="80833.68")
    assert r.resuelve_yes(Decimal("80833.68")) is True
    assert r.resuelve_yes(Decimal("80833.69")) is True
    assert r.resuelve_yes(Decimal("80833.67")) is False


def test_menor_y_menor_o_igual():
    assert regla(Operador.MENOR).resuelve_yes(Decimal("80000")) is False
    assert regla(Operador.MENOR_O_IGUAL).resuelve_yes(Decimal("80000")) is True
    assert regla(Operador.MENOR).resuelve_yes(Decimal("79999")) is True


def test_rango_cerrado_incluye_los_dos_extremos():
    r = regla(Operador.RANGO_CERRADO, umbral_superior=Decimal("81000"))
    assert r.resuelve_yes(Decimal("80000")) is True
    assert r.resuelve_yes(Decimal("81000")) is True
    assert r.resuelve_yes(Decimal("81000.01")) is False


def test_rango_sin_umbral_superior_falla():
    with pytest.raises(ErrorContrato):
        regla(Operador.RANGO_CERRADO)


def test_sin_datos_liquida_no_por_omision():
    # "If no data is available or incomplete ... then affected strikes resolve to No."
    r = regla(Operador.MAYOR_O_IGUAL)
    assert r.sin_datos_liquida == "no"
    assert r.resuelve_yes(None) is False


def test_sin_datos_con_cancelacion_exige_flujo_real():
    r = regla(Operador.MAYOR_O_IGUAL, sin_datos_liquida="cancela")
    with pytest.raises(ErrorContrato):
        r.resuelve_yes(None)


def test_strike_type_desconocido_no_se_interpreta():
    assert operador_desde_strike_type("greater_or_equal") is Operador.MAYOR_O_IGUAL
    assert operador_desde_strike_type("greater") is Operador.MAYOR
    with pytest.raises(ErrorContrato):
        operador_desde_strike_type("inventado")


def test_ventana_de_promedio_debe_ser_positiva():
    with pytest.raises(ErrorContrato):
        ReglaLiquidacion(
            indice="BRTI",
            agencia_fuente="CF",
            ventana_promedio_s=0,
            operador=Operador.MAYOR,
            umbral=Decimal("1"),
        )
