"""Pruebas de la comparación con Robinhood (sin red, datos sintéticos)."""
import importlib.util
import json
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "experiments" / "comparacion-robinhood"


def cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, RUTA / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


comparar = cargar("comparar")
foto = cargar("foto_alpaca")


def _captura(hora, corte, spot, estado="identificado", sello=None, par=("2026-11-19", "2026-11-20")):
    return {"hora": hora, "corte_utc": corte,
            "spot_spx_implicito": {"estado": estado, "spot": spot, "forward_error": 0.1, "sello_evento_utc": sello},
            "raices": {"SPXW": {"plazo_constante_30d": {"vencimientos": list(par)}}}}


def _resumen(fecha, *capturas):
    return {"fecha": fecha, "capturas": list(capturas)}


def test_spx_compara_con_el_minuto_que_contiene_el_sello():
    barras = {"2026-10-21": {"13:43": [90.0, 91.0, 89.0, 90.0], "13:44": [100.0, 102.0, 99.0, 101.0],
                             "13:59": [110.0, 111.0, 109.0, 110.5]}}
    r = comparar.comparar_spx(barras, [_resumen(
        "2026-10-21",
        _captura("09:45", "2026-10-21T13:45:00.000000Z", 101.5, sello="2026-10-21 13:44:54.4+00:00"),
        _captura("10:00", "2026-10-21T14:00:00.000000Z", 111.5))])  # sin sello: el minuto anterior al corte
    a, b = r["cortes"]
    assert a["diferencia"] == pytest.approx(0.5) and a["dentro"]
    assert b["diferencia"] == pytest.approx(1.0) and not b["dentro"]
    assert r["dentro_del_minuto"] == 1 and r["diferencia"]["n"] == 2


def test_el_minuto_del_sello_sigue_al_horario_de_invierno():
    # 09:45 de Nueva York el 2 de noviembre de 2026 es 14:45 UTC
    c = _captura("09:45", "2026-11-02T14:45:00.000000Z", 1.0, sello="2026-11-02 14:44:55.1+00:00")
    assert comparar.minuto_del_sello(c) == "14:44"
    c["spot_spx_implicito"]["sello_evento_utc"] = None
    assert comparar.minuto_del_sello(c) == "14:44"


def test_spx_omite_niveles_no_identificados_y_dias_sin_barras():
    barras = {"2026-10-21": {"13:44": [1.0, 1.0, 1.0, 1.0]}}
    r = comparar.comparar_spx(barras, [
        _resumen("2026-10-21", _captura("09:45", "2026-10-21T13:45:00Z", 1.0, estado="no_identificado")),
        _resumen("2026-10-22", _captura("09:45", "2026-10-22T13:45:00Z", 1.0))])
    assert r["cortes"] == [] and r["diferencia"] == {"n": 0}


def test_fuera_del_dinero_por_tipo_y_strike():
    assert comparar.fuera_del_dinero("SPXW261120P07425000", 7700.0)
    assert not comparar.fuera_del_dinero("SPXW261120P07825000", 7700.0)
    assert comparar.fuera_del_dinero("SPXW261120C07825000", 7700.0)
    assert not comparar.fuera_del_dinero("SPXW261120C07425000", 7700.0)


def test_simbolo_occ():
    assert comparar.simbolo_occ("SPXW", "2026-11-20", "put", "7725.0000") == "SPXW261120P07725000"
    assert comparar.simbolo_occ("SPXW", "2026-11-20", "call", 7737.5) == "SPXW261120C07737500"


def test_plan_elige_el_vencimiento_a_30_dias_y_centra_los_strikes():
    r = _resumen("2026-11-02",
                 _captura("09:45", "2026-11-02T14:45:00.000000Z", 6818.0, par=("2026-12-01", "2026-12-03")),
                 _captura("10:00", "2026-11-02T15:00:00.000000Z", 6815.0, par=("2026-12-01", "2026-12-03")))
    p = comparar.plan(r)
    assert p["vencimiento"] == "2026-12-03"  # 29 y 31 días empatan: el más lejano
    assert p["strikes"] == [6525, 6625, 6725, 6825, 6925, 7025, 7125]
    assert p["simbolos"][:2] == ["SPXW261203C06525000", "SPXW261203P06525000"] and len(p["simbolos"]) == 14
    assert p["instrumentos"][0]["strike_price"] == "6525.0000"
    assert p["spx"]["start_time"] == "2026-11-02T14:40:00Z" and p["spx"]["end_time"] == "2026-11-02T15:01:00Z"
    assert p["barras"]["09:45"]["start_time"] == "2026-11-02T14:44:45Z"
    assert p["barras"]["10:00"]["end_time"] == "2026-11-02T15:00:15Z"
    ids = {s: f"id{i}" for i, s in enumerate(p["simbolos"])}
    lotes = comparar.plan(r, ids)["lotes"]
    assert [len(x) for x in lotes] == [10, 4] and sum(lotes, []) == [ids[s] for s in p["simbolos"]]


def test_plan_sin_nivel_no_pide_nada():
    r = _resumen("2026-10-21", _captura("09:45", "2026-10-21T13:45:00Z", None, estado="no_identificado"))
    assert "motivo" in comparar.plan(r)


def _instrumento(i, tipo, strike, vencimiento="2026-11-20"):
    return {"id": i, "chain_symbol": "SPXW", "expiration_date": vencimiento, "strike_price": strike, "type": tipo}


def test_importar_instrumentos_arma_el_simbolo_y_exige_los_esperados():
    lista = [_instrumento("a", "put", "7725.0000"), _instrumento("b", "call", "7725.0000")]
    assert comparar.importar_instrumentos(lista) == {"SPXW261120C07725000": "b", "SPXW261120P07725000": "a"}
    with pytest.raises(ValueError, match="faltan"):
        comparar.importar_instrumentos(lista, ["SPXW261120P07825000"])
    with pytest.raises(ValueError, match="dos ids"):
        comparar.importar_instrumentos(lista + [_instrumento("c", "put", "7725.0000")])


def _resultado_barras(i, occ, barras):
    return {"instrument_id": i, "occ_symbol": occ, "interval": "15second", "bars": [
        {"begins_at": t, "open_price": str(o), "high_price": str(h), "low_price": str(l), "close_price": str(c),
         **({"interpolated": True} if interp else {})} for t, (o, h, l, c), interp in barras]}


def test_importar_barras_valida_ids_coherencia_e_interpoladas():
    instrumentos = {"SPXW261120P07725000": "a"}
    r = comparar.importar_barras([_resultado_barras("a", "SPXW  261120P07725000", [
        ("2026-10-21T13:44:45Z", (1.0, 1.2, 0.9, 1.1), False),
        ("2026-10-21T13:45:00Z", (1.1, 1.1, 1.1, 1.1), True)])], instrumentos, "2026-10-21T13:45:00.000000Z")
    assert r["corte_utc"] == "2026-10-21T13:45:00Z" and r["interpoladas"] == 1
    assert r["barras"] == {"SPXW261120P07725000": {"13:44:45": [1.0, 1.2, 0.9, 1.1]}}
    with pytest.raises(ValueError, match="no es"):
        comparar.importar_barras([_resultado_barras("b", "SPXW  261120P07725000", [])], instrumentos,
                                 "2026-10-21T13:45Z")
    with pytest.raises(ValueError, match="incoherente"):
        comparar.importar_barras([_resultado_barras("a", "SPXW  261120P07725000", [
            ("2026-10-21T13:44:45Z", (1.0, 1.05, 0.9, 1.1), False)])], instrumentos, "2026-10-21T13:45Z")
    for t in ("2026-10-21T13:59:45Z", "2026-10-20T13:44:45Z"):  # barras de otro corte o de otro día
        with pytest.raises(ValueError, match="lejos del corte"):
            comparar.importar_barras([_resultado_barras("a", "SPXW  261120P07725000", [
                (t, (1.0, 1.2, 0.9, 1.1), False)])], instrumentos, "2026-10-21T13:45Z")


def test_importar_spx_agrupa_por_fecha_y_minuto():
    r = comparar.importar_spx([{"symbol": "SPX", "interval": "minute", "bars": [
        {"begins_at": "2026-10-21T13:44:00Z", "open_value": "1", "high_value": "2", "low_value": "0.5",
         "close_value": "1.5"},
        {"begins_at": "2026-10-21T13:45:00Z", "open_value": "1", "high_value": "1", "low_value": "1",
         "close_value": "1", "interpolated": True}]}])
    assert r == {"2026-10-21": {"13:44": [1.0, 2.0, 0.5, 1.5]}}


def _cotizacion(i, bid, ask, marca, delta="-0.3", actualizada="2026-10-22T14:30:00.5Z"):
    return {"quote": {"instrument_id": i, "bid_price": bid, "ask_price": ask, "bid_size": 5, "ask_size": 7,
                      "mark_price": marca, "implied_volatility": "0.14", "delta": delta, "vega": "8.6",
                      "updated_at": actualizada}}


def test_importar_cotizaciones_exige_que_la_marca_sea_el_punto_medio():
    instrumentos = {"SPXW261120P07725000": "a"}
    r = comparar.importar_cotizaciones([_cotizacion("a", "95.2", "95.8", "95.5")], instrumentos)
    assert r["SPXW261120P07725000"]["marca"] == 95.5 and r["SPXW261120P07725000"]["delta"] == -0.3
    with pytest.raises(ValueError, match="punto medio"):
        comparar.importar_cotizaciones([_cotizacion("a", "95.2", "95.8", "95.9")], instrumentos)
    with pytest.raises(ValueError, match="no está"):
        comparar.importar_cotizaciones([_cotizacion("x", "1", "2", "1.5")], instrumentos)


def test_opciones_usa_el_cierre_de_la_barra_anterior_al_corte():
    barras = {"corte_utc": "2026-10-21T13:45:00Z", "barras": {
        "SPXW261120P07425000": {"13:44:45": [9.0, 9.0, 9.0, 10.0], "13:45:00": [50.0, 50.0, 50.0, 50.0]},
        "SPXW261120C07825000": {"13:44:45": [5.0, 5.0, 5.0, 5.0]},
        "SPXW261120C07925000": {"13:44:45": [1.0, 1.0, 1.0, 1.0]}}}
    q = {"SPXW261120P07425000": {"bid": 9.8, "ask": 10.6, "edad_s": 5.0},
         "SPXW261120C07825000": {"bid": 5.5, "ask": 5.7, "edad_s": 90.0}}
    r = comparar.comparar_opciones(barras, q, nivel=7700.0)
    filas = {f["simbolo"]: f for f in r["contratos"]}
    assert set(filas) == {"SPXW261120P07425000", "SPXW261120C07825000"}  # sin cotización de Alpaca: se omite
    p = filas["SPXW261120P07425000"]
    assert p["diferencia"] == pytest.approx(0.2) and p["en_medios_spreads"] == pytest.approx(0.5)
    assert p["dentro_del_spread"] and p["fresca"] and p["fuera_del_dinero"]
    c = filas["SPXW261120C07825000"]
    assert c["diferencia"] == pytest.approx(0.6) and not c["dentro_del_spread"] and not c["fresca"]
    assert r["frescas"] == 1 and r["dentro_del_spread"] == 1
    assert r["fuera_del_dinero"]["n"] == 2


def test_opciones_descarta_cotizaciones_cruzadas_o_vacias():
    barras = {"corte_utc": "2026-10-21T14:00:00Z",
              "barras": {"SPXW261120C07825000": {"13:59:45": [5.0, 5.0, 5.0, 5.0]}}}
    r = comparar.comparar_opciones(barras, {"SPXW261120C07825000": {"bid": 6.0, "ask": 5.0, "edad_s": 1.0}})
    assert r["contratos"] == [] and r["fuera_del_dinero"]["n"] == 0


def test_vivo_compara_spreads_y_separa_por_delta():
    rh = {"P1": {"bid": 95.2, "ask": 95.8, "marca": 95.5, "delta": -0.42, "actualizado_utc": "2026-10-22T14:30:00Z"},
          "C1": {"bid": 10.0, "ask": 10.4, "marca": 10.2, "delta": 0.62, "actualizado_utc": "2026-10-22T14:30:00Z"},
          "C2": {"bid": 0.0, "ask": 0.1, "marca": 0.05, "delta": 0.01, "actualizado_utc": "2026-10-22T14:30:00Z"}}
    alp = {"P1": {"bid": 94.8, "ask": 96.4, "t": "2026-10-22T14:29:58Z"},
           "C1": {"bid": 10.0, "ask": 10.4, "t": "2026-10-22T14:30:01Z"},
           "C2": {"bid": 0.05, "ask": 0.1, "t": "2026-10-22T14:30:00Z"}}
    r = comparar.comparar_vivo(rh, alp)
    filas = {f["simbolo"]: f for f in r["contratos"]}
    assert set(filas) == {"P1", "C1"}  # sin bid en Robinhood: se omite
    p = filas["P1"]
    assert p["diferencia"] == pytest.approx(0.1) and p["razon_spread"] == pytest.approx(1.6 / 0.6)
    assert p["alpaca_contiene"] and p["marca_dentro"] and not p["igual"] and p["desfase_s"] == -2.0
    assert filas["C1"]["igual"] and not filas["C1"]["fuera_del_dinero"]
    assert r["igual"] == 1 and r["fuera_del_dinero"]["n"] == 1


def test_foto_alpaca_lee_las_cotizaciones_del_snapshot():
    cuerpo = {"snapshots": {"SPXW261120P07725000": {"latestQuote": {
        "bp": 95.0, "ap": 96.0, "bs": 3, "as": 4, "bx": "C", "ax": "W", "t": "2026-10-22T14:30:00Z"}}}}
    assert foto.cotizaciones(cuerpo) == {"SPXW261120P07725000": {
        "bid": 95.0, "ask": 96.0, "bid_size": 3, "ask_size": 4, "bolsa_bid": "C", "bolsa_ask": "W",
        "t": "2026-10-22T14:30:00Z"}}


def test_importar_y_acumulado_de_punta_a_punta(tmp_path):
    resumen = _resumen("2026-10-21", _captura("09:45", "2026-10-21T13:45:00.000000Z", 7727.2,
                                              sello="2026-10-21 13:44:54.4+00:00"))
    p = comparar.plan(resumen)
    crudo = tmp_path / "2026-10-21" / "crudo"
    crudo.mkdir(parents=True)
    lista = [_instrumento(f"id-{s}", "call" if s[-9] == "C" else "put", f"{int(s[-8:]) / 1000:.4f}")
             for s in p["simbolos"]]
    (crudo / "instrumentos.json").write_text(json.dumps(lista), encoding="utf-8")
    (crudo / "spx.json").write_text(json.dumps([{"symbol": "SPX", "interval": "minute", "bars": [
        {"begins_at": "2026-10-21T13:44:00Z", "open_value": "7726", "high_value": "7728", "low_value": "7725",
         "close_value": "7727"}]}]), encoding="utf-8")
    simbolo = p["simbolos"][0]
    (crudo / "cotizaciones.json").write_text(json.dumps([_cotizacion(f"id-{simbolo}", "1.0", "1.2", "1.1",
                                                                     actualizada="2026-10-21T14:29:59.5Z")]),
                                             encoding="utf-8")
    foto_alp = {"enviado_utc": "2026-10-21T14:30:00.6Z", "recibido_utc": "2026-10-21T14:30:01Z", "cotizaciones": {
        simbolo: {"bid": 0.9, "ask": 1.5, "t": "2026-10-21T14:30:00Z"}}}
    (crudo / "alpaca_vivo.json").write_text(json.dumps({**foto_alp, "enviado_utc": "2026-10-21T14:30:35Z"}),
                                            encoding="utf-8")
    with pytest.raises(ValueError, match="no están pareadas"):
        comparar.importar(tmp_path, resumen)
    (crudo / "alpaca_vivo.json").write_text(json.dumps(foto_alp), encoding="utf-8")
    assert comparar.importar(tmp_path, resumen) == ["instrumentos.json", "spx_minutos.json", "vivo.json"]
    dia = comparar.resultados_dia(tmp_path, resumen)
    assert dia["spx"]["cortes"][0]["diferencia"] == pytest.approx(0.2)
    assert dia["vivo"]["n"] == 1 and dia["vivo"]["razon_spread"]["mediana"] == pytest.approx(3.0)
    comparar._escribir(tmp_path / "2026-10-21" / "resultados.json", dia)
    total = comparar.acumulado(tmp_path)
    assert total["dias"] == 1 and total["spx"]["dentro_del_minuto"] == 1
    assert total["vivo"]["dias"] == 1 and total["opciones"]["dias"] == 0
