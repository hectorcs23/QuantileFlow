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
from quantileflow import piloto as pl
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
    assert len(cot) == 20                                     # dos vencimientos x 5 strikes x 2 tipos
    assert sorted({str(v) for v in cot["vencimiento"]}) == ["2026-11-19", "2026-11-20"]
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
    assert ct.vencimientos(cot, "SPXW", SESION, "09:45") == [
        pd.Timestamp("2026-11-19").date(), pd.Timestamp("2026-11-20").date()]
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
    assert resumen["roots"] == ["SPXW"] and resumen["contracts"] == 20
    assert "absent" in resumen["event_timestamp"]


# --- Qué vencimientos pedir -------------------------------------------------
#
# Los vencimientos reales que devolvió la cadena SPXW el 2026-10-21.
VENCIMIENTOS_SPXW = [
    "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28",
    "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05",
    "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13",
    "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23",
    "2026-11-24", "2026-11-25", "2026-11-27", "2026-11-30", "2026-12-03", "2026-12-04",
    "2026-12-11", "2026-12-18", "2026-12-31",
]


@pytest.fixture(scope="module")
def cfg():
    return pl.cargar_config(Path(__file__).resolve().parents[1] / "configs" / "pilot.toml")


def test_plazos_hasta_la_liquidacion():
    dias = rh.maturity_days(VENCIMIENTOS_SPXW, "PM", SESION, "09:45")
    assert dias[pd.Timestamp("2026-11-20").date()] == pytest.approx(30.3, abs=0.05)
    # El vencimiento del día ya liquidó respecto de un corte de las 09:45? No: liquida al cierre.
    assert pd.Timestamp("2026-10-21").date() in dias
    # AM liquida en la apertura, antes que PM: menos plazo para el mismo vencimiento.
    am = rh.maturity_days(["2026-11-20"], "AM", SESION, "09:45")
    assert am[pd.Timestamp("2026-11-20").date()] < dias[pd.Timestamp("2026-11-20").date()]


def test_descarta_vencimientos_que_no_son_sesion():
    # 2026-11-21 y 22 caen en fin de semana; 2026-11-26 es Acción de Gracias.
    dias = rh.maturity_days(["2026-11-20", "2026-11-21", "2026-11-22", "2026-11-26"], "PM",
                            SESION, "09:45")
    assert sorted(str(f) for f in dias) == ["2026-11-20"]


def test_pide_los_dos_vencimientos_que_encierran_el_objetivo(cfg, captura):
    """Con un solo vencimiento la sesión queda sin medir: hay que capturar el par."""
    cadena = next(c for c in captura["chains"] if c["symbol"] == "SPXW")
    elegidos, motivo = rh.bracketing_expirations(cadena, VENCIMIENTOS_SPXW, SESION, cfg)
    assert motivo == ""
    assert [str(f) for f in elegidos] == ["2026-11-19", "2026-11-20"]

    solo_uno, motivo_uno = rh.bracketing_expirations(cadena, ["2026-11-20"], SESION, cfg)
    assert solo_uno == [] and "both sides" in motivo_uno


def test_sin_vencimientos_utiles_da_motivo(cfg, captura):
    cadena = next(c for c in captura["chains"] if c["symbol"] == "SPXW")
    vacio, motivo = rh.bracketing_expirations(cadena, [], SESION, cfg)
    assert vacio == [] and "no expirations" in motivo


def test_el_par_de_vencimientos_da_una_sesion_medida(tablas, cfg):
    """Con los dos vencimientos el piloto mide RR25 a plazo constante; con uno, no.

    Es la razón por la que la captura pide el par: la medición interpola en
    varianza total entre los dos lados del objetivo.
    """
    cot, sub = _dentro_de_sesion(*tablas)
    resultado = pl.ejecutar(cot, sub, [pd.Timestamp(SESION).date()], cfg)
    fila = resultado.principal.iloc[0]
    assert fila["estado_sesion"] == "procesada"
    assert str(fila["vencimiento_1"]) == "2026-11-19" and str(fila["vencimiento_2"]) == "2026-11-20"
    assert fila["dias_1"] < cfg.objetivo_dias < fila["dias_2"]     # encierran los 30 días
    assert fila["rr25_estado"] == "identificada", fila["rr25_motivo"]
    assert fila["rr25_inferior"] < fila["rr25"] < fila["rr25_superior"]
    assert -0.10 < fila["rr25"] < 0.0        # skew de índice: el put de 25 delta paga más
    assert fila["filas_validas"] == 20
    # La edad es desconocida en todas las filas, y el informe lo dice como alerta.
    assert any("quote age unknown" in a for a in fila["alertas"].split(" | "))


def test_un_solo_vencimiento_deja_la_sesion_sin_medir(tablas, cfg):
    cot, sub = _dentro_de_sesion(*tablas)
    uno = cot[cot["vencimiento"].map(str) == "2026-11-20"]
    resultado = pl.ejecutar(uno, sub, [pd.Timestamp(SESION).date()], cfg)
    fila = resultado.principal.iloc[0]
    assert fila["estado_sesion"] != "procesada"
    assert "both sides" in fila["motivo_sesion"]
