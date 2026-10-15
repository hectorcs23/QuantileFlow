"""Latencia, libro a la llegada, fills parciales, limitadas y flujos de caja."""

import datetime as dt
from decimal import Decimal

import pytest

from btclab.costes import ModeloComisionCuadratica
from btclab.libro import Lado, Libro, Nivel
from btclab.objetivo import Etiqueta
from btclab.replay import (
    ESCENARIOS_RETRASO,
    ErrorReplay,
    EstresMercado,
    Orden,
    PerfilRetrasos,
    ejecutar,
    libro_a_la_llegada,
    liquidar,
)

UTC = dt.timezone.utc


#: Base de tiempos del replay. Se usa timedelta para que los desplazamientos
#: puedan pasar de un minuto sin desbordar el campo de segundos.
BASE = dt.datetime(2026, 10, 15, 4, 0, 0, tzinfo=UTC)


def t(segundos):
    return BASE + dt.timedelta(seconds=segundos)


def modelo():
    return ModeloComisionCuadratica(constante=Decimal("0.07"), verificada=True)


BARATO = Libro(
    "C", t(0), t(0),
    compras_yes=(Nivel(400, Decimal("500")),),
    compras_no=(Nivel(550, Decimal("500")),),
)
CARO = Libro(
    "C", t(10), t(10),
    compras_yes=(Nivel(600, Decimal("500")),),
    compras_no=(Nivel(350, Decimal("500")),),
)


def test_los_retrasos_se_suman_por_etapa():
    p = PerfilRetrasos(datos_s=1.0, calculo_s=0.5, accion_humana_s=8.0)
    assert p.total_s == 9.5
    assert p.llegada(t(0)) == t(0) + dt.timedelta(seconds=9.5)


def test_retraso_negativo_se_rechaza():
    with pytest.raises(ErrorReplay):
        PerfilRetrasos(datos_s=-1.0)


def test_los_escenarios_no_estan_medidos():
    # Sin mediciones del flujo real, la conclusion es provisional.
    for perfil in ESCENARIOS_RETRASO.values():
        assert perfil.medido is False


def test_se_usa_el_libro_de_la_llegada_no_el_de_la_decision():
    orden = Orden(Lado.YES, Decimal("100"), None, t(0), "C")
    corto = ejecutar(orden, [BARATO, CARO], PerfilRetrasos(1, 0.5, 8), modelo(), Decimal("0.5"))
    largo = ejecutar(orden, [BARATO, CARO], PerfilRetrasos(1, 1, 13), modelo(), Decimal("0.5"))
    assert corto.libro_usado_en == t(0)
    assert largo.libro_usado_en == t(10)
    # El libro de la llegada es mas caro: el retraso tiene un coste medible.
    assert largo.coste_total > corto.coste_total


def test_libro_a_la_llegada_nunca_mira_adelante():
    assert libro_a_la_llegada([BARATO, CARO], t(5)) is BARATO
    assert libro_a_la_llegada([BARATO, CARO], t(10)) is CARO
    assert libro_a_la_llegada([BARATO, CARO], t(0)) is BARATO
    assert libro_a_la_llegada([BARATO, CARO], t(9.999)) is BARATO


def test_sin_libro_previo_la_orden_se_rechaza():
    orden = Orden(Lado.YES, Decimal("100"), None, t(0), "C")
    f = ejecutar(orden, [CARO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"))
    assert f.estado == "rechazada"
    assert not f.ejecutada


def test_libro_demasiado_viejo_se_rechaza():
    orden = Orden(Lado.YES, Decimal("100"), None, t(0), "C")
    f = ejecutar(
        orden, [BARATO], PerfilRetrasos(1, 1, 30), modelo(), Decimal("0.5"),
        antiguedad_max_s=5.0,
    )
    assert f.estado == "rechazada"


def test_limitada_superada_a_la_llegada_no_ejecuta():
    # Una orden limitada no garantiza ejecucion.
    orden = Orden(Lado.YES, Decimal("100"), 500, t(0), "C")
    f = ejecutar(orden, [BARATO, CARO], PerfilRetrasos(1, 1, 13), modelo(), Decimal("0.5"))
    assert f.estado == "no_ejecutada"
    assert f.cantidad_llenada == Decimal("0")


def test_limitada_alcanzable_si_ejecuta():
    orden = Orden(Lado.YES, Decimal("100"), 500, t(0), "C")
    f = ejecutar(orden, [BARATO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"))
    assert f.estado == "completa"


def test_fill_parcial_por_profundidad():
    orden = Orden(Lado.YES, Decimal("900"), None, t(0), "C")
    f = ejecutar(orden, [BARATO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"))
    assert f.estado == "parcial"
    assert f.cantidad_llenada == Decimal("500")


def test_el_estres_encarece_y_reduce_profundidad():
    orden = Orden(Lado.YES, Decimal("100"), None, t(0), "C")
    normal = ejecutar(orden, [BARATO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"))
    duro = ejecutar(
        orden, [BARATO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"),
        estres=EstresMercado(Decimal("0.5"), 20, "duro"),
    )
    assert duro.coste_total > normal.coste_total
    grande = Orden(Lado.YES, Decimal("400"), None, t(0), "C")
    recortado = ejecutar(
        grande, [BARATO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"),
        estres=EstresMercado(Decimal("0.5"), 0, "mitad"),
    )
    assert recortado.estado == "parcial"


def test_cantidad_no_positiva_se_rechaza():
    with pytest.raises(ErrorReplay):
        Orden(Lado.YES, Decimal("0"), None, t(0), "C")


# -- liquidacion ------------------------------------------------------------


def fill_completo():
    orden = Orden(Lado.YES, Decimal("100"), None, t(0), "C")
    return ejecutar(orden, [BARATO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"))


def test_gana_cobra_un_dolar_por_contrato():
    f = fill_completo()
    etiqueta = Etiqueta("C", 1, Decimal("81000"), "yes", "v1", t(30))
    fc = liquidar(f, etiqueta)
    assert fc.resultado == "gana"
    assert fc.cobrado == Decimal("100")
    assert fc.neto == Decimal("100") - f.coste_total


def test_pierde_no_cobra_nada_y_pierde_el_coste():
    f = fill_completo()
    etiqueta = Etiqueta("C", 0, Decimal("79000"), "no", "v1", t(30))
    fc = liquidar(f, etiqueta)
    assert fc.cobrado == Decimal("0")
    assert fc.neto == -f.coste_total


def test_comprar_no_gana_cuando_yes_pierde():
    orden = Orden(Lado.NO, Decimal("100"), None, t(0), "C")
    f = ejecutar(orden, [BARATO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"))
    etiqueta = Etiqueta("C", 0, Decimal("79000"), "no", "v1", t(30))
    assert liquidar(f, etiqueta).resultado == "gana"


def test_cancelacion_reembolsa_el_coste_y_no_fuerza_perdida():
    f = fill_completo()
    etiqueta = Etiqueta(
        "C", None, None, "void", "v1", t(30), excepcional=True,
        flujo_caja_por_contrato={"reembolso_coste": Decimal("1")},
    )
    fc = liquidar(f, etiqueta)
    assert fc.excepcional is True
    assert fc.neto == Decimal("0")


def test_pago_especial_por_contrato():
    f = fill_completo()
    etiqueta = Etiqueta(
        "C", None, None, "especial", "v1", t(30), excepcional=True,
        flujo_caja_por_contrato={"pago_por_contrato": Decimal("0.5")},
    )
    fc = liquidar(f, etiqueta)
    assert fc.cobrado == Decimal("50.0")


def test_flujo_excepcional_con_clave_desconocida_falla():
    f = fill_completo()
    etiqueta = Etiqueta(
        "C", None, None, "raro", "v1", t(30), excepcional=True,
        flujo_caja_por_contrato={"inventado": Decimal("1")},
    )
    with pytest.raises(ErrorReplay):
        liquidar(f, etiqueta)


def test_los_fondos_quedan_inmovilizados_hasta_la_liquidacion():
    f = fill_completo()
    etiqueta = Etiqueta("C", 1, Decimal("81000"), "yes", "v1", t(300))
    fc = liquidar(f, etiqueta)
    assert fc.inmovilizado_desde == f.llegada_en
    assert fc.liberado_en == t(300)
    assert fc.liberado_en > fc.inmovilizado_desde


def test_orden_no_ejecutada_no_deja_posicion():
    orden = Orden(Lado.YES, Decimal("100"), 100, t(0), "C")
    f = ejecutar(orden, [BARATO], PerfilRetrasos(0, 0, 0), modelo(), Decimal("0.5"))
    etiqueta = Etiqueta("C", 1, Decimal("81000"), "yes", "v1", t(30))
    fc = liquidar(f, etiqueta)
    assert fc.resultado == "sin_posicion"
    assert fc.neto == Decimal("0")
