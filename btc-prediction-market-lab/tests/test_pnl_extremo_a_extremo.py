"""P&L de extremo a extremo, contrastado con una cuenta hecha a mano.

Escenario cerrado y verificable con lapiz:

* Libro: mejor compra de NO a $0.550 y profundidad de 500 contratos.
  => mejor venta de YES = 1 - 0.550 = $0.450.
* Compramos 100 YES al mercado, sin retraso.
  A(100) = 100 * 0.450 = $45.000
  F(100) = techo(0.07 * 100 * 0.45 * 0.55) = techo(1.7325) = $1.74
  C(100) = $46.740
* Si YES gana: cobramos 100 * $1 = $100 -> neto = $53.260
* Si YES pierde: cobramos $0 -> neto = -$46.740
* Perdida maxima = C(100) = $46.740
"""

import datetime as dt
from decimal import Decimal

from btclab.costes import ModeloComisionCuadratica, evaluar
from btclab.libro import Lado, Libro, Nivel
from btclab.objetivo import Etiqueta
from btclab.replay import Orden, PerfilRetrasos, ejecutar, liquidar

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 15, 4, 0, 0, tzinfo=UTC)

LIBRO = Libro(
    "KXBTC15M-TEST", T0, T0,
    compras_yes=(Nivel(440, Decimal("500")),),
    compras_no=(Nivel(550, Decimal("500")),),
)
MODELO = ModeloComisionCuadratica(constante=Decimal("0.07"), verificada=True)

COSTE_LIBRO = Decimal("45.000")
COMISION = Decimal("1.74")
COSTE_TOTAL = Decimal("46.740")


def test_coste_coincide_con_la_cuenta_a_mano():
    ev = evaluar(LIBRO, Lado.YES, Decimal("100"), Decimal("0.55"), MODELO)
    assert LIBRO.mejor_venta_mils(Lado.YES) == 450
    assert ev.coste_libro == COSTE_LIBRO
    assert ev.comisiones == COMISION
    assert ev.coste_total == COSTE_TOTAL


def test_flujos_por_resultado_coinciden_a_mano():
    ev = evaluar(LIBRO, Lado.YES, Decimal("100"), Decimal("0.55"), MODELO)
    flujos = ev.flujos_por_resultado()
    assert flujos["gana"] == Decimal("53.260")
    assert flujos["pierde"] == -COSTE_TOTAL


def fill():
    orden = Orden(Lado.YES, Decimal("100"), None, T0, "KXBTC15M-TEST")
    return ejecutar(orden, [LIBRO], PerfilRetrasos(0, 0, 0), MODELO, Decimal("0.55"))


def test_pnl_ganador_extremo_a_extremo():
    f = fill()
    assert f.estado == "completa"
    assert f.coste_total == COSTE_TOTAL
    etiqueta = Etiqueta(
        "KXBTC15M-TEST", 1, Decimal("80900"), "yes", "v1",
        T0 + dt.timedelta(minutes=16),
    )
    fc = liquidar(f, etiqueta)
    assert fc.pagado == COSTE_TOTAL
    assert fc.cobrado == Decimal("100")
    assert fc.neto == Decimal("53.260")


def test_pnl_perdedor_extremo_a_extremo():
    f = fill()
    etiqueta = Etiqueta(
        "KXBTC15M-TEST", 0, Decimal("80700"), "no", "v1",
        T0 + dt.timedelta(minutes=16),
    )
    fc = liquidar(f, etiqueta)
    assert fc.neto == -COSTE_TOTAL
    # La perdida maxima declarada antes de operar coincide con la realizada.
    ev = evaluar(LIBRO, Lado.YES, Decimal("100"), Decimal("0.55"), MODELO)
    assert ev.perdida_maxima == -fc.neto


def test_el_ev_es_consistente_con_los_flujos():
    p = Decimal("0.55")
    ev = evaluar(LIBRO, Lado.YES, Decimal("100"), p, MODELO)
    flujos = ev.flujos_por_resultado()
    esperado = p * flujos["gana"] + (Decimal(1) - p) * flujos["pierde"]
    assert ev.valor_esperado == esperado


def test_la_suma_de_los_dos_lados_pierde_las_comisiones():
    # Comprar YES y NO a la vez garantiza $1 por par, pero las comisiones y el
    # spread hacen que la combinacion pierda: no hay arbitraje gratis.
    yes = evaluar(LIBRO, Lado.YES, Decimal("100"), Decimal("0.5"), MODELO)
    no = evaluar(LIBRO, Lado.NO, Decimal("100"), Decimal("0.5"), MODELO)
    coste_par = yes.coste_total + no.coste_total
    assert coste_par > Decimal("100")


def test_pnl_acumulado_de_una_serie_de_contratos():
    # Tres contratos identicos, dos ganados y uno perdido.
    resultados = [1, 1, 0]
    neto = Decimal("0")
    for y in resultados:
        f = fill()
        etiqueta = Etiqueta(
            "KXBTC15M-TEST", y, Decimal("80800"), "yes" if y else "no", "v1",
            T0 + dt.timedelta(minutes=16),
        )
        neto += liquidar(f, etiqueta).neto
    # 2 * 53.260 - 46.740 = 59.780
    assert neto == Decimal("59.780")
