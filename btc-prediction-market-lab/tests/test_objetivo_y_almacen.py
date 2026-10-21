"""Etiquetas desde el mercado liquidado y almacen append-only."""

import datetime as dt
from decimal import Decimal

import pytest

from btclab.almacen import Almacen, registro_a_observacion
from btclab.contrato import (
    Comisiones,
    EstadoReglas,
    FichaContrato,
    Fuente,
    Operador,
    ReglaLiquidacion,
)
from btclab.dinero import REJILLA_TAPERED_DECI_CENT
from btclab.objetivo import ErrorObjetivo, MomentoDecision, etiqueta_desde_mercado
from btclab.tiempo import Observacion, desde_iso

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 15, 4, 0, tzinfo=UTC)


def ficha(umbral="80833.68", operador=Operador.MAYOR_O_IGUAL):
    return FichaContrato(
        plataforma_visible="Kalshi",
        exchange_subyacente="Kalshi",
        serie="KXBTC15M",
        evento="E",
        contrato="KXBTC15M-TEST",
        moneda="USD",
        apertura=T0,
        fin_negociacion=T0 + dt.timedelta(minutes=15),
        vencimiento_esperado=T0 + dt.timedelta(minutes=15),
        vencimiento_limite=T0 + dt.timedelta(days=7),
        pregunta="BTC up?",
        regla=ReglaLiquidacion(
            indice="BRTI",
            agencia_fuente="CF Benchmarks",
            ventana_promedio_s=60,
            operador=operador,
            umbral=Decimal(umbral),
            umbral_es_promedio_apertura=True,
        ),
        rejilla=REJILLA_TAPERED_DECI_CENT,
        pago_ganador=Decimal("1.00"),
        cantidad_minima=1,
        fracciones_permitidas=True,
        comisiones=Comisiones(
            tipo="quadratic", multiplicador=Decimal("1"),
            constante=Decimal("0.07"), verificada=False,
        ),
        limite_posicion_por_strike=Decimal("25000"),
        estado_reglas=EstadoReglas.COSTS_UNVERIFIED,
        version_reglas="v1",
        fuentes=(Fuente(url="http://x", consultada_en=T0),),
        reglas_faltantes=("constante del calendario de comisiones vigente",),
    )


def test_resultado_yes_da_y_igual_uno():
    e = etiqueta_desde_mercado(
        {"ticker": "C", "result": "yes", "expiration_value": "80900"}, ficha(), T0
    )
    assert e.y == 1
    assert not e.excepcional


def test_resultado_no_da_y_igual_cero():
    e = etiqueta_desde_mercado(
        {"ticker": "C", "result": "no", "expiration_value": "80000"}, ficha(), T0
    )
    assert e.y == 0


def test_el_empate_exacto_reproduce_el_resultado_oficial():
    e = etiqueta_desde_mercado(
        {"ticker": "C", "result": "yes", "expiration_value": "80833.68"}, ficha(), T0
    )
    assert e.y == 1
    assert not e.excepcional


def test_discrepancia_entre_regla_y_resultado_se_marca_excepcional():
    # El oficial dice NO pero la regla (>=) dice YES: nuestra lectura de las
    # reglas no es correcta y el contrato no esta verificado.
    e = etiqueta_desde_mercado(
        {"ticker": "C", "result": "no", "expiration_value": "80833.68"}, ficha(), T0
    )
    assert e.y is None
    assert e.excepcional
    assert "no reproduce el resultado oficial" in e.nota


def test_cancelacion_se_registra_con_reembolso():
    e = etiqueta_desde_mercado({"ticker": "C", "result": "void"}, ficha(), T0)
    assert e.y is None
    assert e.excepcional
    assert e.flujo_caja_por_contrato == {"reembolso_coste": Decimal("1")}


def test_resultado_no_binario_se_marca_excepcional():
    e = etiqueta_desde_mercado({"ticker": "C", "result": "raro"}, ficha(), T0)
    assert e.y is None
    assert e.excepcional


def test_mercado_sin_resultado_falla():
    with pytest.raises(ErrorObjetivo):
        etiqueta_desde_mercado({"ticker": "C", "result": ""}, ficha(), T0)


def test_expiration_value_ilegible_falla():
    with pytest.raises(ErrorObjetivo):
        etiqueta_desde_mercado(
            {"ticker": "C", "result": "yes", "expiration_value": "no-es-numero"},
            ficha(), T0,
        )


# -- momento de decision ----------------------------------------------------


def test_momento_de_decision_a_60s_de_la_apertura():
    m = MomentoDecision(retraso_s=60.0)
    assert m.instante(ficha()) == T0 + dt.timedelta(seconds=60)


def test_momento_inadmisible_si_el_umbral_no_se_conoce():
    ok, motivos = MomentoDecision().admisible(ficha(), umbral_conocido=False, libro_valido=True)
    assert not ok
    assert any("umbral" in m for m in motivos)


def test_momento_inadmisible_sin_libro():
    ok, motivos = MomentoDecision().admisible(ficha(), umbral_conocido=True, libro_valido=False)
    assert not ok
    assert any("libro" in m for m in motivos)


def test_momento_admisible_con_todo_en_orden():
    ok, motivos = MomentoDecision().admisible(ficha(), True, True)
    assert ok
    assert motivos == ()


def test_momento_fuera_de_negociacion_es_inadmisible():
    ok, motivos = MomentoDecision(retraso_s=2000.0).admisible(ficha(), True, True)
    assert not ok


# -- almacen ----------------------------------------------------------------


def test_el_almacen_solo_anade(tmp_path):
    a = Almacen(tmp_path / "datos")
    for i in range(3):
        a.anadir(
            "libro",
            Observacion(
                event_time=desde_iso("2026-10-15T12:00:00Z"),
                received_at=desde_iso(f"2026-10-15T12:00:0{i}Z"),
                fuente="test",
                payload={"i": i},
            ),
            contrato="C",
        )
    registros = [r for r in a.leer("libro") if not r.get("_corrupto")]
    assert len(registros) == 3
    assert [r["payload"]["i"] for r in registros] == [0, 1, 2]


def test_una_revision_entra_como_registro_nuevo(tmp_path):
    a = Almacen(tmp_path / "datos")
    for recibido, valor in (("12:00:00", "original"), ("12:05:00", "revisado")):
        a.anadir(
            "indice",
            Observacion(
                event_time=desde_iso("2026-10-15T12:00:00Z"),
                received_at=desde_iso(f"2026-10-15T{recibido}Z"),
                fuente="test",
                payload={"v": valor},
            ),
        )
    registros = list(a.leer("indice"))
    # El estado de informacion de las 12:01 sigue siendo reconstruible.
    disponibles = [r for r in registros if r["received_at"] <= "2026-10-15T12:01:00.000Z"]
    assert len(disponibles) == 1
    assert disponibles[0]["payload"]["v"] == "original"


def test_linea_corrupta_no_aborta_la_lectura(tmp_path):
    a = Almacen(tmp_path / "datos")
    a.anadir(
        "libro",
        Observacion(
            event_time=desde_iso("2026-10-15T12:00:00Z"),
            received_at=desde_iso("2026-10-15T12:00:00Z"),
            fuente="test",
            payload={"i": 0},
        ),
    )
    ruta = a.ruta("libro", "2026-10-15")
    with ruta.open("a", encoding="utf-8") as destino:
        destino.write("{esto no es json\n")
    registros = list(a.leer("libro"))
    assert len(registros) == 2
    assert sum(1 for r in registros if r.get("_corrupto")) == 1


def test_el_manifiesto_cambia_con_el_contenido(tmp_path):
    a = Almacen(tmp_path / "datos")
    def anadir(valor):
        a.anadir(
            "libro",
            Observacion(
                event_time=desde_iso("2026-10-15T12:00:00Z"),
                received_at=desde_iso("2026-10-15T12:00:00Z"),
                fuente="test",
                payload={"i": valor},
            ),
        )
    anadir(1)
    primero = a.hash_flujo("libro")
    anadir(2)
    assert a.hash_flujo("libro") != primero
    manifiesto = a.manifiesto({"nota": "prueba"})
    assert manifiesto["flujos"]["libro"] == a.hash_flujo("libro")
    assert manifiesto["extra"]["nota"] == "prueba"


def test_reconstruir_observacion_desde_el_registro(tmp_path):
    a = Almacen(tmp_path / "datos")
    original = Observacion(
        event_time=desde_iso("2026-10-15T12:00:00Z"),
        received_at=desde_iso("2026-10-15T12:00:02Z"),
        fuente="kalshi:libro",
        payload={"x": 1},
        secuencia=5,
    )
    a.anadir("libro", original, contrato="C")
    registro = next(iter(a.leer("libro")))
    vuelta = registro_a_observacion(registro)
    assert vuelta.event_time == original.event_time
    assert vuelta.received_at == original.received_at
    assert vuelta.secuencia == 5
    assert vuelta.latencia_s == 2.0


def test_flujo_con_nombre_invalido_se_rechaza(tmp_path):
    a = Almacen(tmp_path / "datos")
    with pytest.raises(Exception):
        a.ruta("../fuga", "2026-10-15")


# -- horizonte: la ventana de liquidacion, no el vencimiento ----------------


def test_el_horizonte_termina_en_el_cierre_de_negociacion():
    # Las reglas de la serie de 15 minutos promedian los 60 s previos al cierre
    # de negociacion. El vencimiento esperado llega despues, cuando el exchange
    # publica, y usarlo anadiria difusion que el objetivo no tiene.
    f = ficha()
    assert f.fin_ventana_liquidacion == f.fin_negociacion
    en_apertura = f.apertura
    assert f.tiempo_restante_s(en_apertura) == 900.0


def test_el_vencimiento_se_mide_aparte_para_el_capital():
    f = ficha()
    # La ficha de prueba tiene vencimiento esperado igual al cierre; lo que
    # importa es que son dos cuentas distintas y no se confunden.
    assert f.tiempo_hasta_vencimiento_s(f.apertura) >= f.tiempo_restante_s(f.apertura)


def test_un_vencimiento_posterior_no_alarga_el_horizonte():
    import datetime as dt_
    from dataclasses import replace

    f = ficha()
    mas_tarde = replace(
        f,
        vencimiento_esperado=f.fin_negociacion + dt_.timedelta(minutes=5),
        vencimiento_limite=f.vencimiento_limite,
    )
    assert mas_tarde.tiempo_restante_s(f.apertura) == 900.0
    assert mas_tarde.tiempo_hasta_vencimiento_s(f.apertura) == 1200.0
