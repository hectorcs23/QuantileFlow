"""Contrato de datos normalizado: símbolos OCC, validación, adaptador y sellos de tiempo."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quantileflow import cadenas as ca
from quantileflow import calendario as cal
from quantileflow import contrato as ct
from quantileflow import sintetico as sn

FECHAS = cal.sesiones("2025-11-17", "2025-11-21")


@pytest.fixture(scope="module")
def mercado():
    escenarios = {FECHAS[1]: ["desfasadas"], FECHAS[2]: ["sin_hora_evento", "spot_desfasado"]}
    return sn.mercado_sintetico(FECHAS, semilla=4, escenarios=escenarios, rango_k=(-0.08, 0.04))


def test_simbolos_occ():
    assert ct.parsear_occ("SPXW  251219C05800000") == {
        "raiz": "SPXW", "vencimiento": dt.date(2025, 12, 19), "tipo": "C", "strike": 5800.0}
    assert ct.parsear_occ("SPY251219P00512500")["strike"] == 512.5
    assert ct.simbolo_occ("SPXW", "2025-12-19", "P", 5812.5) == "SPXW251219P05812500"
    with pytest.raises(ValueError):
        ct.parsear_occ("SPXW 2512C5800")


def test_validador_detecta_problemas(mercado):
    cot, sub, _ = mercado
    assert ct.validar(cot) == [] and ct.validar(sub, ct.SUBYACENTE) == []
    assert "faltan columnas" in ct.validar(cot.drop(columns=["feed"]))[0]
    ingenua = cot.copy()
    ingenua["sello_snapshot_utc"] = ingenua["sello_snapshot_utc"].dt.tz_localize(None)
    assert any("UTC" in p for p in ct.validar(ingenua))
    mala = cot.copy()
    mala.loc[mala.index[0], "tipo"] = "X"
    assert any("tipo" in p for p in ct.validar(mala))
    repetida = pd.concat([cot, cot.iloc[:3]])
    assert any("repetidas" in p for p in ct.validar(repetida))
    cambiada = cot.copy()
    cambiada.loc[cambiada.index[0], "strike"] += 5.0
    assert any("no coincide" in p for p in ct.validar(cambiada))


def test_captura_desde_tabla(mercado):
    cot, sub, verdad = mercado
    fecha = FECHAS[0]
    venc = ct.vencimientos(cot, "SPXW", fecha)
    cap, info = ct.captura_desde_tabla(cot, sub, "SPXW", venc[1], fecha, "09:45", tasa=0.04,
                                       rendimiento_dividendo=0.013)
    t = verdad[(fecha, "09:45", venc[1])]
    assert info["T"] == pytest.approx(t["T"])
    assert info["liquidacion_utc"] == cal.cierre(venc[1])
    assert cap.spot == pytest.approx(verdad["spot"][(fecha, "09:45")])
    assert cap.corte == 9.75 * 3600
    assert np.all((cap.sello <= cap.corte) & (cap.sello >= cap.corte - 20))
    # Solo entran los snapshots de esa sesión hasta el corte: nada de las 10:00.
    a_las_945 = cot[(cot["vencimiento"] == venc[1])
                    & (cot["sello_snapshot_utc"] == cal.instante(fecha, "09:45"))]
    assert info["filas"] == len(a_las_945)
    res = ca.procesar_captura(cap)
    assert abs(res.paridad.forward_global - t["F"]) / t["F"] < 2e-5
    with pytest.raises(ct.SinDatos):
        ct.captura_desde_tabla(cot, sub, "SPXW", dt.date(2026, 1, 16), fecha)
    mezclada = cot.copy()
    mezclada.loc[mezclada.index[0], "liquidacion"] = "AM"
    with pytest.raises(ValueError):
        ct.captura_desde_tabla(mezclada, sub, "SPXW", mezclada["vencimiento"].iloc[0], fecha)


def test_desfasadas_solo_en_la_hora_principal(mercado):
    cot, sub, _ = mercado
    fecha = FECHAS[1]
    venc = ct.vencimientos(cot, "SPXW", fecha)[0]
    principal = ca.controlar(ct.captura_desde_tabla(cot, sub, "SPXW", venc, fecha, "09:45")[0])
    assert principal.resumen().get("desfasada", 0) > 0
    # A las 10:00 también entran las filas de las 09:45: quedan reemplazadas y, además, viejas.
    cap10, _ = ct.captura_desde_tabla(cot, sub, "SPXW", venc, fecha, "10:00")
    secundaria = ca.controlar(cap10)
    nuevas = np.flatnonzero(cap10.sello_snapshot == 10 * 3600)
    viejas = np.flatnonzero(cap10.sello_snapshot < 10 * 3600)
    assert len(nuevas) and len(viejas)
    assert not any("desfasada" in secundaria.motivos[i] for i in nuevas)
    contratos_10 = {(cap10.strike[i], bool(cap10.es_call[i])) for i in nuevas}
    for i in viejas:
        assert "desfasada" in secundaria.motivos[i]
        if (cap10.strike[i], bool(cap10.es_call[i])) in contratos_10:
            assert "reemplazada" in secundaria.motivos[i]


def test_sin_hora_de_evento_no_se_inventa_la_edad(mercado):
    cot, sub, _ = mercado
    fecha = FECHAS[2]
    venc = ct.vencimientos(cot, "SPXW", fecha)[0]
    cap, info = ct.captura_desde_tabla(cot, sub, "SPXW", venc, fecha, "09:45")
    assert np.all(np.isnan(cap.sello)) and np.all(np.isfinite(cap.sello_snapshot))
    controles = ca.controlar(cap)
    assert "desfasada" not in controles.resumen()
    assert any("edad de cotización desconocida" in a for a in controles.alertas)
    assert any("subyacente desfasado 30 s" in a for a in controles.alertas)
    assert controles.valida.sum() > 0


def test_disponibilidad_posterior_al_corte_excluye(mercado):
    cot, sub, _ = mercado
    fecha = FECHAS[0]
    tardia = cot.copy()
    tardia["disponible_utc"] = tardia["sello_snapshot_utc"] + pd.Timedelta(minutes=15)
    venc = ct.vencimientos(tardia, "SPXW", fecha)[0]
    cap, _ = ct.captura_desde_tabla(tardia, sub, "SPXW", venc, fecha)
    controles = ca.controlar(cap)
    assert controles.resumen()["no_disponible_al_corte"] == len(cap.strike)
    assert not controles.valida.any()
    sin_doc = cot.copy()
    sin_doc["disponible_utc"] = pd.NaT
    cap2, _ = ct.captura_desde_tabla(sin_doc, sub, "SPXW", venc, fecha)
    assert "disponibilidad histórica no documentada" in ca.controlar(cap2).alertas


def test_fila_sin_ningun_sello_se_excluye():
    cap, _ = sn.captura_sintetica(strikes=np.arange(95.0, 106.0))
    sello = cap.sello.copy()
    sello[0] = np.nan
    snapshot = np.full(len(sello), cap.corte)
    snapshot[0] = np.nan
    import dataclasses
    rota = dataclasses.replace(cap, sello=sello, sello_snapshot=snapshot)
    motivos = ca.controlar(rota).motivos
    assert motivos[0] == ("sin_sello",)
    assert all("sin_sello" not in m for m in motivos[1:])


# --- Regresiones de la revisión del commit e2b92f0 ------------------------------------

def _subyacente(filas):
    tabla = pd.DataFrame([{"subyacente": "SPX", "bid": np.nan, "ask": np.nan, "proveedor": "x", "feed": "indice",
                           "tipo_precio": "observado", **f} for f in filas])
    for columna in ("sello_evento_utc", "sello_snapshot_utc", "disponible_utc", "recibido_utc"):
        tabla[columna] = pd.to_datetime(tabla[columna], utc=True).dt.as_unit("us")
    return tabla


def test_subyacente_disponible_despues_del_corte_no_se_usa():
    # H3: evento y snapshot antes del corte, pero publicado una hora después.
    fecha = FECHAS[0]
    corte = cal.instante(fecha, "09:45")
    tarde = {"precio": 99999.0, "sello_evento_utc": corte - pd.Timedelta(seconds=1), "sello_snapshot_utc": corte,
             "disponible_utc": corte + pd.Timedelta(hours=1), "recibido_utc": corte + pd.Timedelta(hours=1)}
    with pytest.raises(ct.SinDatos, match="después del corte"):
        ct.spot_al_corte(_subyacente([tarde]), "SPX", fecha, corte)
    antes = corte - pd.Timedelta(seconds=2)
    a_tiempo = {"precio": 5800.0, "sello_evento_utc": corte - pd.Timedelta(seconds=3), "sello_snapshot_utc": antes,
                "disponible_utc": antes, "recibido_utc": antes}
    assert ct.spot_al_corte(_subyacente([a_tiempo, tarde]), "SPX", fecha, corte)[0] == 5800.0
    sin_doc = dict(a_tiempo, disponible_utc=pd.NaT)  # disponibilidad no documentada: se acepta y se informa
    info = ct.precio_al_corte(_subyacente([sin_doc]), "SPX", fecha, corte)
    assert info["precio"] == 5800.0 and info["disponibilidad_documentada"] is False
    assert info["fuente"] == "x/indice" and info["tipo_precio"] == "observado"


def test_subyacente_de_varias_fuentes_exige_elegir_y_tipo_valido():
    fecha = FECHAS[0]
    corte = cal.instante(fecha, "09:45")
    base = {"sello_evento_utc": corte - pd.Timedelta(seconds=1), "sello_snapshot_utc": corte,
            "disponible_utc": corte, "recibido_utc": corte}
    dos = _subyacente([dict(base, precio=5800.0), dict(base, precio=5801.0, feed="implicito_paridad_SPXW",
                                                       tipo_precio="implicito")])
    with pytest.raises(ValueError, match="fuentes"):
        ct.precio_al_corte(dos, "SPX", fecha, corte)
    elegido = ct.precio_al_corte(dos, "SPX", fecha, corte, fuente_elegida="x/implicito_paridad_SPXW")
    assert elegido["precio"] == 5801.0 and elegido["tipo_precio"] == "implicito"
    malo = dos.copy()
    malo.loc[0, "tipo_precio"] = "estimado"
    assert any("tipo_precio" in p for p in ct.validar(malo, ct.SUBYACENTE))


def test_mezcla_de_feeds_en_una_captura_se_rechaza(mercado):
    # H2: calls de un feed y puts de otro en la misma captura.
    cot, sub, _ = mercado
    fecha = FECHAS[0]
    venc = ct.vencimientos(cot, "SPXW", fecha)[0]
    mezcla = cot.copy()
    mezcla.loc[mezcla["tipo"] == "P", "feed"] = "opra"
    with pytest.raises(ValueError, match="feed"):
        ct.captura_desde_tabla(mezcla, sub, "SPXW", venc, fecha)
    otro = cot.copy()
    otro.loc[otro["tipo"] == "P", "proveedor"] = "otro"
    with pytest.raises(ValueError, match="proveedor"):
        ct.captura_desde_tabla(otro, sub, "SPXW", venc, fecha)


# --- Revalidación de d815bdd: regla histórica del precio objetivo ------------------------

def _objetivo(corte, cotizaciones, publicado):
    """Cotizaciones de SPY ``(segundos respecto del corte, bid, ask)`` publicadas en ``publicado``."""
    filas = []
    for segundos, bid, ask in cotizaciones:
        evento = corte + pd.Timedelta(seconds=segundos)
        filas.append({"precio": 0.5 * (bid + ask), "bid": bid, "ask": ask, "sello_evento_utc": evento,
                      "sello_snapshot_utc": corte, "disponible_utc": publicado,
                      "recibido_utc": corte + pd.Timedelta(hours=1)})
    return _subyacente(filas).assign(subyacente="SPY", proveedor="alpaca", feed="sip")


def test_precio_para_etiqueta_usa_la_ultima_cotizacion_valida():
    fecha = FECHAS[0]
    corte = cal.instante(fecha, "09:45")
    publicado = corte + pd.Timedelta(minutes=15)
    reglas = {"edad_maxima_s": 60.0, "spread_relativo_max": 5e-4}
    tabla = _objetivo(corte, [(-30, 580.00, 580.02), (-2, 579.50, 580.60), (1, 590.00, 590.02)], publicado)
    info = ct.precio_para_etiqueta(tabla, "SPY", fecha, corte, **reglas)
    # La de -2 s tiene spread anormal y se descarta; la de +1 s es posterior al corte y no cuenta.
    assert info["precio"] == pytest.approx(580.01) and info["descartadas"] == 1
    assert info["sello_utc"] == corte - pd.Timedelta(seconds=30)
    assert info["disponible_utc"] == publicado and info["disponibilidad_documentada"] is True
    assert info["fuente"] == "alpaca/sip" and info["tipo_precio"] == "observado"
    # Publicado después del corte: vale para la etiqueta, pero la regla puntual no lo admite.
    with pytest.raises(ct.SinDatos, match="después del corte"):
        ct.precio_al_corte(tabla, "SPY", fecha, corte)
    # Si la única cotización de la ventana es anormal, falta el precio.
    with pytest.raises(ct.SinDatos, match="spread anormal"):
        ct.precio_para_etiqueta(tabla, "SPY", fecha, corte, edad_maxima_s=10.0, spread_relativo_max=5e-4)
    raras = _objetivo(corte, [(-5, 580.02, 580.00), (-3, 0.0, 580.00)], publicado)  # cruzada y sin bid
    with pytest.raises(ct.SinDatos, match="cruzadas, sin bid"):
        ct.precio_para_etiqueta(raras, "SPY", fecha, corte, **reglas)
    with pytest.raises(ct.SinDatos, match="sin cotización de SPY en los 60 s previos"):
        ct.precio_para_etiqueta(_objetivo(corte, [(-61, 580.0, 580.02)], publicado), "SPY", fecha, corte, **reglas)
    # Sin disponibilidad documentada, la madurez usa la recepción local.
    sin_doc = ct.precio_para_etiqueta(_objetivo(corte, [(-1, 580.0, 580.02)], pd.NaT), "SPY", fecha, corte, **reglas)
    assert sin_doc["disponible_utc"] == corte + pd.Timedelta(hours=1)
    assert sin_doc["disponibilidad_documentada"] is False
    # Dos fuentes del mismo símbolo: hay que elegir.
    dos = pd.concat([tabla, tabla.assign(feed="iex")], ignore_index=True)
    with pytest.raises(ValueError, match="elija una"):
        ct.precio_para_etiqueta(dos, "SPY", fecha, corte, **reglas)
    assert ct.precio_para_etiqueta(dos, "SPY", fecha, corte, "alpaca/iex", **reglas)["fuente"] == "alpaca/iex"


def test_validacion_de_dividendos_y_su_cobertura():
    base = {"simbolo": "SPY", "fecha_ex": dt.date(2025, 12, 19), "monto": 1.9, "fecha_pago": dt.date(2026, 1, 30),
            "clase": "ordinario", "disponible_utc": pd.NaT, "recibido_utc": pd.Timestamp("2026-01-05T15:20:00Z"),
            "retirado_utc": pd.NaT, "motivo_retiro": "", "proveedor": "alpaca", "feed": "corporate_actions"}

    def tabla(*filas):
        t = pd.DataFrame(list(filas))
        for c in ("disponible_utc", "recibido_utc", "retirado_utc"):
            t[c] = pd.to_datetime(t[c], utc=True)
        return t

    corregida = dict(base, retirado_utc=pd.Timestamp("2026-01-06T15:20:00Z"), motivo_retiro="corregido")
    nueva = dict(base, monto=1.95, recibido_utc=pd.Timestamp("2026-01-06T15:20:00Z"))
    assert ct.validar(tabla(base), ct.DIVIDENDOS) == [] and ct.validar(tabla(corregida, nueva), ct.DIVIDENDOS) == []
    problemas = ct.validar(tabla(base, dict(base, clase="extra", monto=-1.0), base), ct.DIVIDENDOS)
    assert any("clase" in p for p in problemas) and any("monto" in p for p in problemas)
    assert any("repetidas" in p for p in problemas)
    al_reves = dict(base, retirado_utc=pd.Timestamp("2026-01-01T00:00:00Z"), motivo_retiro="otro")
    problemas = ct.validar(tabla(al_reves), ct.DIVIDENDOS)
    assert any("antes de conocerse" in p for p in problemas) and any("motivo_retiro" in p for p in problemas)
    consulta = {"simbolo": "SPY", "desde": dt.date(2025, 1, 1), "hasta": dt.date(2026, 3, 1),
                "campo_fecha": "process_date", "recibido_utc": pd.Timestamp("2026-01-05T15:20:00Z"),
                "estado": "completa", "eventos": 0.0, "calidad": "complete", "tipos": "todos", "consulta": "q1",
                "proveedor": "alpaca", "feed": "corporate_actions"}
    assert ct.validar(pd.DataFrame([consulta]), ct.COBERTURA_DIVIDENDOS) == []  # vacía, pero consultada
    mala = dict(consulta, estado="rara", desde=dt.date(2026, 6, 1), eventos=-1.0)
    problemas = ct.validar(pd.DataFrame([mala]), ct.COBERTURA_DIVIDENDOS)
    assert len(problemas) == 3


def test_dos_capturas_de_la_misma_hora_marcan_la_vieja_como_reemplazada(mercado):
    # Una captura parcial a las 09:44:57 y su repetición a las 09:44:59, a la que le falta un contrato.
    cot, sub, _ = mercado
    fecha = FECHAS[0]
    corte = cal.instante(fecha, "09:45")
    venc = ct.vencimientos(cot, "SPXW", fecha)[0]
    filas = cot[(cot["sello_snapshot_utc"] == corte) & (cot["vencimiento"] == venc)]
    atras = pd.Timedelta(seconds=3)
    primera = filas.assign(sello_snapshot_utc=corte - atras, sello_evento_utc=filas["sello_evento_utc"] - atras,
                           bid=filas["bid"] + 1.0, ask=filas["ask"] + 1.0)
    repeticion = filas.iloc[1:].assign(sello_snapshot_utc=corte - pd.Timedelta(seconds=1))
    cap, info = ct.captura_desde_tabla(pd.concat([primera, repeticion], ignore_index=True), sub, "SPXW", venc, fecha)
    assert info["filas"] == 2 * len(filas) - 1  # todo queda en la captura, para el registro
    motivos = ca.controlar(cap).motivos
    vigentes = [i for i, m in enumerate(motivos) if "reemplazada" not in m]
    assert len(motivos) - len(vigentes) == len(filas) - 1  # las viejas que se repitieron
    claves = {(cap.strike[i], cap.es_call[i]): cap.bid[i] for i in vigentes}
    assert len(claves) == len(vigentes) == len(filas)  # cada contrato una sola vez
    for fila in filas.itertuples():
        esperado = fila.bid + 1.0 if fila.Index == filas.index[0] else fila.bid  # el que falta sale de la primera
        assert claves[(fila.strike, fila.tipo == "C")] == pytest.approx(esperado)
