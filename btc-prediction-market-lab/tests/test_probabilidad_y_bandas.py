"""p_no = 1 - p_yes, y la banda conservadora de cada lado."""

from decimal import Decimal

import pytest

from btclab.libro import Lado
from btclab.probabilidad import (
    BandaProbabilidad,
    ErrorProbabilidad,
    Prediccion,
)


def banda(inferior, superior, defendible=True):
    return BandaProbabilidad(
        inferior=Decimal(inferior),
        superior=Decimal(superior),
        metodo="bootstrap por bloques",
        supuestos="dependencia intradia",
        defendible=defendible,
    )


def test_p_no_es_el_complemento_exacto():
    for valor in ("0", "0.001", "0.37", "0.5", "0.999", "1"):
        p = Prediccion(p_yes=Decimal(valor), banda=None)
        assert p.p_no == Decimal(1) - Decimal(valor)
        assert p.p_yes + p.p_no == Decimal(1)


def test_p_robust_yes_es_la_cota_inferior():
    p = Prediccion(p_yes=Decimal("0.52"), banda=banda("0.40", "0.62"))
    assert p.p_robust(Lado.YES) == Decimal("0.40")


def test_p_robust_no_es_uno_menos_la_cota_superior():
    # El error clasico seria 1 - L = 0.60, que es la cota SUPERIOR de p_no.
    p = Prediccion(p_yes=Decimal("0.52"), banda=banda("0.40", "0.62"))
    assert p.p_robust(Lado.NO) == Decimal("0.38")
    assert p.p_robust(Lado.NO) != Decimal(1) - Decimal("0.40")


def test_banda_de_p_no_es_la_reflejada():
    p = Prediccion(p_yes=Decimal("0.52"), banda=banda("0.40", "0.62"))
    assert p.banda_p_no == (Decimal("0.38"), Decimal("0.60"))


def test_la_conservadora_nunca_supera_la_central():
    p = Prediccion(p_yes=Decimal("0.52"), banda=banda("0.40", "0.62"))
    assert p.p_robust(Lado.YES) <= p.p_central(Lado.YES)
    assert p.p_robust(Lado.NO) <= p.p_central(Lado.NO)


def test_las_dos_conservadoras_no_suman_uno():
    # Suman menos de 1: es el precio de ser conservador en ambos lados a la vez.
    p = Prediccion(p_yes=Decimal("0.52"), banda=banda("0.40", "0.62"))
    assert p.p_robust(Lado.YES) + p.p_robust(Lado.NO) < Decimal(1)


def test_sin_banda_no_hay_probabilidad_conservadora():
    p = Prediccion(p_yes=Decimal("0.52"), banda=None)
    assert p.p_robust(Lado.YES) is None
    assert p.p_robust(Lado.NO) is None


def test_banda_no_defendible_desactiva_la_conservadora():
    p = Prediccion(p_yes=Decimal("0.52"), banda=banda("0.1", "0.9", defendible=False))
    assert p.p_robust(Lado.YES) is None
    assert p.p_robust(Lado.NO) is None


def test_banda_que_no_contiene_la_central_es_un_error():
    with pytest.raises(ErrorProbabilidad):
        Prediccion(p_yes=Decimal("0.70"), banda=banda("0.40", "0.62"))


def test_banda_exige_metodo_y_supuestos():
    with pytest.raises(ErrorProbabilidad):
        BandaProbabilidad(
            inferior=Decimal("0.4"), superior=Decimal("0.6"),
            metodo="", supuestos="algo",
        )
    with pytest.raises(ErrorProbabilidad):
        BandaProbabilidad(
            inferior=Decimal("0.4"), superior=Decimal("0.6"),
            metodo="algo", supuestos="",
        )


def test_resumen_expone_las_dos_conservadoras_y_nunca_1_menos_L():
    p = Prediccion(p_yes=Decimal("0.52"), banda=banda("0.40", "0.62"))
    r = p.resumen()
    assert r["p_robust_yes"] == "0.40"
    assert r["p_robust_no"] == "0.38"


# -- predicciones no usables ------------------------------------------------


def test_probabilidad_de_certeza_absoluta_es_degenerada():
    b = BandaProbabilidad(
        inferior=Decimal("1"), superior=Decimal("1"),
        metodo="m", supuestos="s",
    )
    p = Prediccion(p_yes=Decimal("1"), banda=b)
    assert p.degenerada is True
    assert any("degenerada" in m for m in p.motivos_no_usable())


def test_banda_de_ancho_cero_es_degenerada():
    b = BandaProbabilidad(
        inferior=Decimal("0.5"), superior=Decimal("0.5"),
        metodo="m", supuestos="s",
    )
    assert Prediccion(p_yes=Decimal("0.5"), banda=b).degenerada is True


def test_certeza_excesiva_se_rechaza_sin_ser_degenerada():
    b = BandaProbabilidad(
        inferior=Decimal("0.990"), superior=Decimal("0.999"),
        metodo="m", supuestos="s",
    )
    p = Prediccion(p_yes=Decimal("0.997"), banda=b)
    assert p.degenerada is False
    assert any("certeza excesiva" in m for m in p.motivos_no_usable())


def test_prediccion_razonable_es_usable():
    p = Prediccion(p_yes=Decimal("0.55"), banda=banda("0.50", "0.62"))
    assert p.motivos_no_usable() == ()


def test_sin_banda_la_prediccion_no_es_usable():
    p = Prediccion(p_yes=Decimal("0.55"), banda=None)
    assert any("sin banda" in m for m in p.motivos_no_usable())
