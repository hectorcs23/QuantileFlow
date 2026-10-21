"""Robinhood adapter: mapping, schema compliance and the provenance it cannot supply.

The fixture is a real read-only capture of ten SPXW contracts taken after the
2026-10-21 close, so it also pins down what Robinhood does *not* give: no venue
timestamp per option quote, and nothing usable at an in-session cut-off when the
capture itself happened after the bell.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from quantileflow import cadenas as ca
from quantileflow import contrato as ct
from quantileflow.sources import robinhood as rh

FIXTURE = Path(__file__).parent / "fixtures" / "robinhood" / "spxw_2026-10-21.json"
SESION = "2026-10-21"


@pytest.fixture(scope="module")
def captura():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tablas(captura):
    return rh.tables(captura)


def _dentro_de_sesion(cot, sub, corte="2026-10-21T13:44:30Z"):
    """Las mismas filas desplazadas a antes de las 09:45, para ejercitar el camino de sesión.

    La captura real es posterior al cierre: sin desplazarla no hay ninguna hora
    de corte válida dentro de la sesión. El desplazamiento solo mueve los sellos;
    precios, tamaños y strikes son los capturados.
    """
    destino = pd.Timestamp(corte)
    cot = cot.assign(sello_snapshot_utc=cot["sello_snapshot_utc"]
                     + (destino - cot["sello_snapshot_utc"].max()))
    salto = destino - sub["sello_snapshot_utc"].max()
    sub = sub.assign(sello_snapshot_utc=sub["sello_snapshot_utc"] + salto,
                     sello_evento_utc=sub["sello_evento_utc"] + salto)
    return cot, sub


def test_mapea_contratos_reales(tablas):
    cot, _ = tablas
    assert len(cot) == 10
    assert set(cot["raiz"]) == {"SPXW"}
    assert set(cot["tipo"]) == {"C", "P"}
    assert set(cot["ejercicio"]) == {"europeo"}      # underlying_type == index
    assert set(cot["liquidacion"]) == {"PM"}         # settle_on_open == false
    assert set(cot["multiplicador"]) == {100.0}
    assert sorted(cot["strike"].unique()) == [7500.0, 7650.0, 7750.0, 7850.0, 8000.0]
    assert "SPXW261120C07500000" in set(cot["id_contrato"])
    fila = cot[cot["id_contrato"] == "SPXW261120P07750000"].iloc[0]
    assert (fila["bid"], fila["ask"], fila["tam_bid"], fila["tam_ask"]) == (104.1, 104.7, 17.0, 9.0)


def test_tablas_cumplen_el_contrato(tablas):
    cot, sub = tablas
    assert ct.validar(cot, ct.COTIZACIONES) == []
    assert ct.validar(sub, ct.SUBYACENTE) == []
    assert float(sub["precio"].iloc[0]) == 7757.17


def test_sin_hora_de_evento_ni_disponibilidad(tablas):
    """Robinhood no publica sello de bolsa por cotización: la edad queda desconocida."""
    cot, sub = tablas
    assert cot["sello_evento_utc"].isna().all()
    assert cot["disponible_utc"].isna().all()
    assert cot["sello_snapshot_utc"].notna().all()
    # El subyacente sí trae venue_timestamp, y se conserva como hora de evento.
    assert sub["sello_evento_utc"].notna().all()


def test_liquidacion_am_cuando_settle_on_open(captura):
    cadena_spx = next(c for c in captura["chains"] if c["symbol"] == "SPX")
    cadena_spxw = next(c for c in captura["chains"] if c["symbol"] == "SPXW")
    assert rh.settlement(cadena_spx) == "AM"
    assert rh.settlement(cadena_spxw) == "PM"
    with pytest.raises(rh.CaptureError, match="settle_on_open"):
        rh.settlement({"symbol": "SPXW"})


def test_rechaza_lo_que_no_puede_inventar(captura):
    huerfana = dict(captura, instruments=[])
    with pytest.raises(rh.CaptureError, match="unknown instrument"):
        rh.quotes_table(huerfana)
    sin_subyacente = dict(captura, underlying={"kind": "index", "quotes": []})
    with pytest.raises(rh.CaptureError, match="underlying.symbol"):
        rh.quotes_table(sin_subyacente)
    sin_cotizaciones = dict(captura, option_quotes=[])
    with pytest.raises(rh.CaptureError, match="no option_quotes"):
        rh.quotes_table(sin_cotizaciones)
    ingenua = dict(captura, captured_at_utc="2026-10-21T21:58:00")
    with pytest.raises(rh.CaptureError, match="without timezone"):
        rh.quotes_table(ingenua)
    desconocido = json.loads(json.dumps(captura))
    desconocido["instruments"][0]["underlying_type"] = "crypto"
    with pytest.raises(rh.CaptureError, match="underlying_type"):
        rh.quotes_table(desconocido)


def test_captura_posterior_al_cierre_no_sirve_en_sesion(tablas):
    """Una captura de después del cierre no cae en ninguna hora de corte de la sesión."""
    cot, sub = tablas
    assert ct.vencimientos(cot, "SPXW", SESION, "15:59") == []
    with pytest.raises(ct.SinDatos):
        ct.captura_desde_tabla(cot, sub, "SPXW", "2026-11-20", SESION, hora="15:59")


def test_camino_completo_hasta_captura(tablas):
    cot, sub = _dentro_de_sesion(*tablas)
    assert ct.vencimientos(cot, "SPXW", SESION, "09:45") == [pd.Timestamp("2026-11-20").date()]
    cap, info = ct.captura_desde_tabla(cot, sub, "SPXW", "2026-11-20", SESION, hora="09:45",
                                       tasa=0.04, rendimiento_dividendo=0.013)
    assert info["liquidacion"] == "PM" and info["filas"] == 10
    assert info["proveedores"] == ["robinhood"]
    assert 29.0 < info["dias"] < 31.0           # el plazo objetivo del piloto
    assert cap.spot == 7757.17
    assert cap.sello is None or pd.isna(cap.sello).all()   # edad desconocida, no fabricada


def test_controles_aceptan_la_captura_real(tablas):
    cot, sub = _dentro_de_sesion(*tablas)
    cap, _ = ct.captura_desde_tabla(cot, sub, "SPXW", "2026-11-20", SESION, hora="09:45")
    reglas = ca.ReglasCalidad(tick_bajo=0.05, tick_alto=0.10, umbral_tick=3.0,
                              spread_ticks_tolerados=2)
    controles = ca.controlar(cap, reglas)
    assert int(controles.valida.sum()) == 10
    assert controles.exclusiones(cap) == []


def test_resumen_no_expone_identificadores_de_cuenta(captura):
    """El resumen que va a logs y manifiestos no lleva ids del proveedor ni de la cuenta."""
    resumen = rh.summary(captura)
    texto = json.dumps(resumen)
    for uuid in [i["id"] for i in captura["instruments"]] + [c["id"] for c in captura["chains"]]:
        assert uuid not in texto
    assert not any(k in texto.lower() for k in ("account", "cuenta", "token", "bearer"))
    assert resumen["roots"] == ["SPXW"] and resumen["contracts"] == 10
    assert "absent" in resumen["event_timestamp"]
