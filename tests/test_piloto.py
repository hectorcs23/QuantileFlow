"""Piloto: plazo constante, tabla diaria, etiquetas, dictamen y reproducibilidad (datos sintéticos)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantileflow import calendario as cal
from quantileflow import etiquetas as et
from quantileflow import piloto as pl
from quantileflow import sintetico as sn
from quantileflow.corrida import correr

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / "configs" / "piloto.toml"
FECHAS = cal.sesiones("2025-11-19", "2025-11-28")  # incluye Acción de Gracias y un cierre anticipado
ESCENARIOS = {FECHAS[2]: ["hueco_calls"]}


@pytest.fixture(scope="module")
def cfg():
    return pl.cargar_config(CONFIG)


@pytest.fixture(scope="module")
def mercado():
    return sn.mercado_sintetico(FECHAS, semilla=11, escenarios=ESCENARIOS, rango_k=(-0.08, 0.04))


@pytest.fixture(scope="module")
def resultado(cfg, mercado):
    cot, sub, verdad = mercado
    return pl.ejecutar(cot, sub, FECHAS, cfg, dividendos=verdad["dividendos"], cobertura=verdad["cobertura"])


# --- Plazo constante ----------------------------------------------------------------

def test_interpolacion_en_varianza_total():
    T1, T2 = 23 / 365, 37 / 365
    assert pl.interpolar_varianza_total(T1, 0.2, T2, 0.25, T1) == pytest.approx(0.2)
    assert pl.interpolar_varianza_total(T1, 0.2, T2, 0.25, T2) == pytest.approx(0.25)
    medio = pl.interpolar_varianza_total(T1, 0.2, T2, 0.2, 30 / 365)
    assert medio == pytest.approx(0.2)  # volatilidad plana: varianza total lineal en T
    assert np.isnan(pl.interpolar_varianza_total(T1, 0.3, T2, 0.01, 1.2 * T2))


def _medida(c, p, ancho=0.004):
    return {"estado": "identificada", "iv_call": c, "iv_call_banda": (c - ancho, c + ancho),
            "iv_put": p, "iv_put_banda": (p - ancho, p + ancho)}


def test_plazo_constante_bandas_y_casos_invalidos():
    T1, T2, T = 25 / 365, 32 / 365, 30 / 365
    m = pl.plazo_constante([_medida(0.15, 0.21), _medida(0.155, 0.212)], [T1, T2], T)
    assert m["estado"] == "identificada"
    assert m["inferior"] < m["valor"] < m["superior"]
    assert m["valor"] == pytest.approx(m["iv_call"] - m["iv_put"])
    unica = pl.plazo_constante([_medida(0.15, 0.21)], [T], T)
    assert unica["valor"] == pytest.approx(-0.06)
    decreciente = pl.plazo_constante([_medida(0.30, 0.21), _medida(0.10, 0.21)], [T1, T2], T)
    assert decreciente["estado"] == "no identificada" and "call" in decreciente["motivo"]
    ausente = pl.plazo_constante([_medida(0.15, 0.21), {"estado": "no identificada", "motivo": "hueco"}],
                                 [T1, T2], T)
    assert ausente["estado"] == "no identificada" and "32.0 días: hueco" in ausente["motivo"]


def test_eleccion_de_vencimientos(cfg):
    assert pl.elegir_vencimientos({"a": 22.3, "b": 29.3, "c": 36.3}, cfg) == (["b", "c"], "")
    assert pl.elegir_vencimientos({"a": 30.0, "b": 37.0}, cfg) == (["a"], "")
    assert pl.elegir_vencimientos({"a": 40.0, "b": 47.0}, cfg)[0] == []
    lejos = pl.elegir_vencimientos({"a": 20.0, "b": 41.0}, cfg)
    assert lejos[0] == [] and "separación" in lejos[1]
    assert pl.elegir_vencimientos({"a": 5.0, "b": 33.0}, cfg)[0] == []  # menos del mínimo de días


# --- Tabla diaria ------------------------------------------------------------------

def test_rr25_a_30_dias_coincide_con_la_verdad(resultado, mercado, cfg):
    _, _, verdad = mercado
    p = resultado.principal
    comprobadas = 0
    for _, fila in p[p["rr25_estado"] == "identificada"].iterrows():
        detalle = resultado.detalles[(fila["fecha"], cfg.hora_principal)]
        patas = {}
        for v in detalle:
            t = verdad[(fila["fecha"], cfg.hora_principal, v)]
            patas[v] = [sn.iv_en_delta_ssvi(t["theta"], t["rho"], t["phi"], t["T"], 0.25, c)[0]
                        for c in (True, False)]
        (v1, v2), T = list(detalle), cfg.objetivo_dias / cfg.base_dias
        T1, T2 = detalle[v1]["info"]["T"], detalle[v2]["info"]["T"]
        esperado = (pl.interpolar_varianza_total(T1, patas[v1][0], T2, patas[v2][0], T)
                    - pl.interpolar_varianza_total(T1, patas[v1][1], T2, patas[v2][1], T))
        assert fila["rr25"] == pytest.approx(esperado, abs=2.5e-3)
        assert fila["rr25_inferior"] <= fila["rr25"] <= fila["rr25_superior"]
        comprobadas += 1
    assert comprobadas >= len(FECHAS) - 2


def test_hueco_cambios_y_calendario(resultado):
    p = resultado.principal.set_index("fecha")
    hueco = p.loc[FECHAS[2]]
    assert hueco["rr25_estado"] == "no identificada" and "calls" in hueco["rr25_motivo"]
    siguiente = p.loc[FECHAS[3]]
    assert np.isnan(siguiente["cambio_rr25"]) and "no identificada" in siguiente["cambio_rr25_motivo"]
    viernes = p.loc[FECHAS[-1]]  # 2025-11-28, tras el feriado del jueves
    miercoles = p.loc[FECHAS[-2]]
    assert viernes["dias_naturales_desde_anterior"] == 2
    assert viernes["cambio_rr25"] == pytest.approx(viernes["rr25"] - miercoles["rr25"])
    assert viernes["cambio_rr25_inferior"] <= viernes["cambio_rr25"] <= viernes["cambio_rr25_superior"]
    assert np.isnan(p.loc[FECHAS[0], "cambio_rr25"])  # la sesión anterior está fuera de la muestra


def test_etiquetas_y_movimiento_previo(resultado, mercado, cfg):
    _, _, verdad = mercado
    p = resultado.principal.set_index("fecha")
    # Referencia de las opciones (SPX, regla puntual): etiquetas auxiliares y movimiento previo.
    spot = {f: verdad["spot"][(f, cfg.hora_principal)] for f in FECHAS}
    assert p.loc[FECHAS[0], "ret_1_referencia"] == pytest.approx(np.log(spot[FECHAS[1]] / spot[FECHAS[0]]))
    assert p.loc[FECHAS[3], "retorno_previo_referencia"] == pytest.approx(
        np.log(spot[FECHAS[3]] / spot[FECHAS[2]]))
    miercoles = FECHAS[-2]  # su siguiente sesión es el viernes 28
    assert p.loc[miercoles, "ret_1_referencia"] == pytest.approx(np.log(spot[FECHAS[-1]] / spot[miercoles]))
    # Objetivo (SPY observado, regla histórica): el mid de la última cotización válida.
    spy = {f: verdad["objetivo"][(f, cfg.hora_principal)] for f in FECHAS}
    assert p.loc[FECHAS[0], "ret_1_objetivo"] == pytest.approx(np.log(spy[FECHAS[1]] / spy[FECHAS[0]]))
    assert p.loc[miercoles, "ret_1_objetivo"] == pytest.approx(np.log(spy[FECHAS[-1]] / spy[miercoles]))
    for serie in ("objetivo", "referencia"):  # el sintético cubre cinco sesiones más
        assert (p[f"estado_ret_5_{serie}"] == "ok").all()


def test_estabilidad_y_dictamen(resultado):
    p = resultado.principal
    ok = p["rr25"].notna()
    ancho = (p["rr25_superior"] - p["rr25_inferior"])[ok]
    assert (p.loc[ok, "dif_rr25_secundaria"].abs() < ancho).all()
    d = resultado.dictamen
    assert len(d["criterios"]) == 6
    assert d["veredicto"] == "insuficiente"  # pocas sesiones: criterio crítico
    assert [c for c in d["criterios"] if c["critico"]][0]["criterio"] == "Sesiones en la muestra"


# --- Corrida reproducible ----------------------------------------------------------

def _escribir(tablas, carpeta):
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre, tabla in zip(("cot.csv", "sub.csv"), tablas):
        tabla.to_csv(carpeta / nombre, index=False, lineterminator="\n")
        rutas.append(carpeta / nombre)
    return rutas


def test_replay_y_datos_posteriores_al_corte(tmp_path, mercado):
    cot, sub, _ = mercado
    fechas = FECHAS[:3]
    rutas = _escribir((cot, sub), tmp_path / "a")
    _, m1 = correr(CONFIG, *rutas, fechas[0], fechas[-1], tmp_path / "salida1", "prueba")
    _, m2 = correr(CONFIG, *rutas, fechas[0], fechas[-1], tmp_path / "salida2", "prueba")
    for archivo in ("tabla_diaria.csv", "tabla_todas_las_horas.csv", "etiquetas.csv"):
        assert m1["salidas"][archivo] == m2["salidas"][archivo]
        assert (tmp_path / "salida1" / archivo).read_bytes() == (tmp_path / "salida2" / archivo).read_bytes()
    assert m1["entradas"]["cotizaciones"]["sha256"] == m2["entradas"]["cotizaciones"]["sha256"]
    # Snapshots posteriores a los dos cortes, con precios absurdos: no cambian nada.
    tarde = cot.copy()
    tarde["sello_snapshot_utc"] = tarde["sello_snapshot_utc"] + pd.Timedelta(minutes=45)
    tarde["sello_evento_utc"] = tarde["sello_evento_utc"] + pd.Timedelta(minutes=45)
    tarde["disponible_utc"] = tarde["disponible_utc"] + pd.Timedelta(minutes=45)
    tarde["bid"] = tarde["bid"] * 3.0
    tarde["ask"] = tarde["ask"] * 3.0 + 1.0
    rutas_tarde = _escribir((pd.concat([cot, tarde], ignore_index=True), sub), tmp_path / "b")
    _, m3 = correr(CONFIG, *rutas_tarde, fechas[0], fechas[-1], tmp_path / "salida3", "prueba")
    assert m3["entradas"]["cotizaciones"]["sha256"] != m1["entradas"]["cotizaciones"]["sha256"]
    assert m3["salidas"]["tabla_diaria.csv"] == m1["salidas"]["tabla_diaria.csv"]


# --- Regresiones de la revisión del commit e2b92f0 ------------------------------------

def test_fuentes_explicitas_y_cambio_ausente_en_la_transicion(cfg, mercado):
    # H2: un día con feed indicativo y el siguiente con OPRA.
    cot, sub, _ = mercado
    fechas = FECHAS[:2]
    mezcla = cot.copy()
    segundo = mezcla["sello_snapshot_utc"].dt.tz_convert("America/New_York").dt.date == fechas[1]
    mezcla.loc[~segundo, "feed"] = "indicative"
    mezcla.loc[segundo, "feed"] = "opra"
    with pytest.raises(ValueError, match="fuentes"):
        pl.ejecutar(mezcla, sub, fechas, cfg)  # hay dos fuentes y ninguna elegida
    ambas = pl.ejecutar(mezcla, sub, fechas, cfg, fuentes_opciones=("sintetico/indicative", "sintetico/opra"))
    p = ambas.principal.set_index("fecha")
    assert list(p["fuente_opciones"]) == ["sintetico/indicative", "sintetico/opra"]
    assert np.isnan(p.loc[fechas[1], "cambio_rr25"]) and "segmento" in p.loc[fechas[1], "cambio_rr25_motivo"]
    assert ambas.dictamen["alcance"]["evaluacion_con_precios_de_mercado"].startswith("no permitida")
    solo = pl.ejecutar(mezcla, sub, fechas, cfg, fuentes_opciones=("sintetico/opra",)).principal.set_index("fecha")
    assert solo.loc[fechas[0], "estado_sesion"] == "no disponible"
    # Dos fuentes en la misma sesión: la sesión queda no disponible, nunca se mezclan.
    doble = pd.concat([cot, cot.assign(feed="opra", sello_snapshot_utc=cot["sello_snapshot_utc"]
                                       - pd.Timedelta(seconds=1))], ignore_index=True)
    r = pl.ejecutar(doble, sub, fechas[:1], cfg,
                    fuentes_opciones=("sintetico/nbbo_intervalos_sintetico", "sintetico/opra"))
    assert r.principal.loc[0, "estado_sesion"] == "no disponible"
    assert "varias fuentes" in r.principal.loc[0, "motivo_sesion"]


def _serie(resultado, serie, horizonte=1):
    e = et.etiquetas_vigentes(resultado.etiquetas)
    return e[(e["serie"] == serie) & (e["horizonte"] == horizonte)].set_index("sesion")


def _del_dia(tabla, simbolo, fecha, hora=None):
    filas = (tabla["subyacente"] == simbolo) & (
        tabla["sello_snapshot_utc"].dt.tz_convert("America/New_York").dt.date == fecha)
    return filas & (tabla["sello_snapshot_utc"] == cal.instante(fecha, hora)) if hora else filas


def test_referencia_desfasada_o_tardia_deja_ausentes_sus_etiquetas(cfg, mercado):
    # H3, regla puntual: la frescura y la disponibilidad de la referencia llegan a sus etiquetas.
    cot, sub, _ = mercado
    fechas = FECHAS[:3]
    dia = _del_dia(sub, "SPX", fechas[1])
    viejo = sub.copy()
    viejo.loc[dia, "sello_evento_utc"] = viejo.loc[dia, "sello_evento_utc"] - pd.Timedelta(minutes=10)
    e = _serie(pl.ejecutar(cot, viejo, fechas, cfg), "referencia")
    assert e.loc[fechas[0], "estado"] == "sin precio final" and "desfasado" in e.loc[fechas[0], "motivo"]
    tarde = sub.copy()
    tarde.loc[dia, "disponible_utc"] = tarde.loc[dia, "disponible_utc"] + pd.Timedelta(hours=2)
    e = _serie(pl.ejecutar(cot, tarde, fechas, cfg), "referencia")
    assert e.loc[fechas[0], "estado"] == "sin precio final" and "después del corte" in e.loc[fechas[0], "motivo"]


def test_procedencia_en_la_tabla_diaria(resultado):
    p = resultado.principal
    assert set(p["fuente_opciones"]) == {"sintetico/nbbo_intervalos_sintetico"}
    assert set(p["fuente_referencia"]) == {"sintetico/indice_sintetico"}
    assert set(p["tipo_precio_referencia"]) == {"observado"}
    assert set(p["fuente_objetivo"]) == {"sintetico/sip_sintetico"}
    assert set(p["tipo_precio_objetivo"]) == {"observado"}
    procedencia = resultado.etiquetas.groupby("serie")[["simbolo", "fuente", "tipo_precio"]].first()
    assert procedencia.loc["objetivo"].tolist() == ["SPY", "sintetico/sip_sintetico", "observado"]
    assert procedencia.loc["referencia"].tolist() == ["SPX", "sintetico/indice_sintetico", "observado"]
    a = resultado.dictamen["alcance"]
    assert a["precio_objetivo"] == "observado" and a["simbolo_objetivo"] == "SPY"
    assert a["instrumento_objetivo"].startswith("SPY, distinto de SPX")
    assert a["evaluacion_con_precios_de_mercado"] == "no permitida: datos sintéticos"


# --- Revalidación de d815bdd: señal, referencia y objetivo separados -------------------

def test_medidas_de_las_opciones_no_cambian_al_anadir_el_objetivo(cfg, mercado, resultado):
    cot, sub, _ = mercado
    sin_spy = pl.ejecutar(cot, sub[sub["subyacente"] != "SPY"], FECHAS, cfg)
    pd.testing.assert_frame_equal(sin_spy.completa, resultado.completa)
    medidas = [c for c in resultado.principal.columns if not c.endswith("_objetivo")]
    assert "rr25" in medidas and "ret_1_referencia" in medidas
    pd.testing.assert_frame_equal(sin_spy.principal[medidas], resultado.principal[medidas])
    referencia = [r.etiquetas[r.etiquetas["serie"] == "referencia"].reset_index(drop=True)
                  for r in (sin_spy, resultado)]
    pd.testing.assert_frame_equal(*referencia)
    # Sin objetivo, sus etiquetas quedan ausentes con motivo y el alcance lo declara.
    assert sin_spy.principal["ret_1_objetivo"].isna().all()
    assert "sin cotización de SPY" in _serie(sin_spy, "objetivo").iloc[0]["motivo"]
    assert "sin precio objetivo" in sin_spy.dictamen["alcance"]["evaluacion_con_precios_de_mercado"]


def test_etiqueta_del_objetivo_madura_con_su_publicacion_y_su_consulta(resultado, mercado, cfg):
    # El SPY sintético se publica 15 minutos después del corte (SIP sin suscripción) y los dividendos se consultan a
    # las 10:21, como el workflow del histórico: la etiqueta madura con lo último de las dos cosas.
    e = et.etiquetas_vigentes(resultado.etiquetas)
    e = e[e["estado"] == "ok"]
    objetivo, referencia = e[e["serie"] == "objetivo"], e[e["serie"] == "referencia"]
    assert len(objetivo) == len(referencia) > 0
    esperado = [cal.instante(f, "10:21") for f in objetivo["sesion_fin"]]
    assert list(objetivo["label_available_at"]) == esperado
    assert (objetivo["consulta_habilitante_utc"] == objetivo["label_available_at"]).all()
    assert (referencia["label_available_at"] == referencia["label_end_at"]).all()
    # Todos los tramos de la primera etiqueta: la vista de un instante da el vigente entonces, sin el futuro.
    primera, todas = objetivo.iloc[0], resultado.etiquetas
    tramos = todas[(todas["serie"] == "objetivo") & (todas["sesion"] == primera["sesion"])
                   & (todas["horizonte"] == primera["horizonte"])]
    assert list(tramos["estado_dividendos"]) == ["provisional", "aceptada"]
    assert et.etiquetas_maduras(tramos, esperado[0] - pd.Timedelta(seconds=1)).empty
    vista = et.etiquetas_maduras(tramos, esperado[0])
    assert len(vista) == 1 and vista.iloc[0]["estado_dividendos"] == "provisional"
    assert vista["vigente_hasta_utc"].isna().all()
    assert et.etiquetas_maduras(tramos, esperado[0], politica="aceptada").empty
    # Con la consulta a las 09:50, manda la publicación del SIP: 15 minutos después del corte.
    cot, sub, verdad = mercado
    temprana = verdad["cobertura"].assign(recibido_utc=verdad["cobertura"]["recibido_utc"] - pd.Timedelta(minutes=31))
    r = pl.ejecutar(cot, sub, FECHAS, cfg, dividendos=verdad["dividendos"], cobertura=temprana)
    o = _serie(r, "objetivo")
    o = o[o["estado"] == "ok"]
    assert len(o) and (o["label_available_at"] - o["label_end_at"] == pd.Timedelta(minutes=15)).all()


def test_objetivo_con_la_regla_historica(cfg, mercado):
    cot, sub, verdad = mercado
    fechas = FECHAS[:3]
    corte = cal.instante(fechas[1], cfg.hora_principal)
    fila = _del_dia(sub, "SPY", fechas[1], cfg.hora_principal)
    # Publicado dos horas tarde: vale para la etiqueta, que madura con esa publicación.
    tarde = sub.copy()
    tarde.loc[fila, "disponible_utc"] = corte + pd.Timedelta(hours=2)
    e = _serie(pl.ejecutar(cot, tarde, fechas, cfg, dividendos=verdad["dividendos"], cobertura=verdad["cobertura"]),
               "objetivo")
    spy = {f: verdad["objetivo"][(f, cfg.hora_principal)] for f in fechas}
    assert e.loc[fechas[0], "estado"] == "ok"
    assert e.loc[fechas[0], "retorno_log"] == pytest.approx(np.log(spy[fechas[1]] / spy[fechas[0]]))
    assert e.loc[fechas[0], "label_available_at"] == corte + pd.Timedelta(hours=2)
    # Una cotización con evento posterior al corte nunca se usa, aunque sea la única del día.
    futura = sub.copy()
    futura.loc[fila, "sello_evento_utc"] = corte + pd.Timedelta(seconds=1)
    e = _serie(pl.ejecutar(cot, futura, fechas, cfg), "objetivo")
    assert e.loc[fechas[0], "estado"] == "sin precio final"
    assert "sin cotización de SPY en los 60 s previos" in e.loc[fechas[0], "motivo"]
    # Más vieja que la edad máxima: tampoco.
    vieja = sub.copy()
    vieja.loc[fila, "sello_evento_utc"] = corte - pd.Timedelta(seconds=61)
    assert _serie(pl.ejecutar(cot, vieja, fechas, cfg), "objetivo").loc[fechas[1], "estado"] == "sin precio inicial"


def test_objetivo_observado_y_de_una_fuente_elegida(cfg, mercado, resultado):
    cot, sub, _ = mercado
    fechas = FECHAS[:3]
    spy = sub["subyacente"] == "SPY"
    inferido = sub.copy()
    inferido.loc[spy, "tipo_precio"] = "implicito"
    with pytest.raises(ValueError, match="debe ser observado"):
        pl.ejecutar(cot, inferido, fechas, cfg)
    otra = sub[spy].assign(feed="iex", precio=sub["precio"] + 0.05, bid=sub["bid"] + 0.05, ask=sub["ask"] + 0.05)
    dos = pd.concat([sub, otra], ignore_index=True)
    with pytest.raises(ValueError, match="objetivo SPY: hay varias fuentes"):
        pl.ejecutar(cot, dos, fechas, cfg)
    base = pl.ejecutar(cot, sub, fechas, cfg).principal
    for fuente in ("sintetico/sip_sintetico", "sintetico/iex"):
        r = pl.ejecutar(cot, dos, fechas, cfg, fuente_objetivo=fuente)
        assert set(r.principal["fuente_objetivo"]) == {fuente}
        assert set(r.etiquetas.loc[r.etiquetas["serie"] == "objetivo", "fuente"]) == {fuente}
        medidas = [c for c in base.columns if not c.endswith("_objetivo")]
        pd.testing.assert_frame_equal(r.principal[medidas], base[medidas])
    elegida = pl.ejecutar(cot, dos, fechas, cfg, fuente_objetivo="sintetico/sip_sintetico").principal
    pd.testing.assert_frame_equal(elegida, base)
    with pytest.raises(ValueError, match="ninguna fuente elegida"):
        pl.ejecutar(cot, sub, fechas, cfg, fuente_objetivo="alpaca/sip")


def test_dividendo_ausencia_y_spread_anormal_del_objetivo(cfg):
    # Ejemplos de la convención: fecha ex dentro del periodo, sin cotización y spread anormal.
    escenarios = {FECHAS[1]: ["objetivo_sin_cotizacion"], FECHAS[5]: ["objetivo_spread_anormal"]}
    cot, sub, verdad = sn.mercado_sintetico(FECHAS, semilla=11, escenarios=escenarios, rango_k=(-0.08, 0.04))
    r = pl.ejecutar(cot, sub, FECHAS, cfg, dividendos=verdad["dividendos"], cobertura=verdad["cobertura"])
    p = r.principal.set_index("fecha")
    spy = {f: verdad["objetivo"][(f, cfg.hora_principal)] for f in FECHAS}
    ex, monto = verdad["dividendos"].loc[0, "fecha_ex"], verdad["dividendos"].loc[0, "monto"]
    viernes = FECHAS[2]
    assert ex == FECHAS[3] and monto == 1.8
    # Del viernes al lunes ex: el rendimiento total suma el dividendo y el de precio no.
    assert p.loc[viernes, "div_1_objetivo"] == monto
    assert p.loc[viernes, "ret_1_objetivo"] == pytest.approx(np.log((spy[ex] + monto) / spy[viernes]))
    assert p.loc[viernes, "ret_precio_1_objetivo"] == pytest.approx(np.log(spy[ex] / spy[viernes]))
    assert p.loc[viernes, "ret_precio_1_objetivo"] < p.loc[viernes, "ret_1_objetivo"] - 0.002
    # El que empieza a las 09:45 del día ex ya no lo cobra; el de 5 sesiones que lo cruza, sí.
    assert p.loc[ex, "div_1_objetivo"] == 0.0 and p.loc[viernes, "div_5_objetivo"] == monto
    # Una etiqueta ausente no atribuye dividendos: la de 5 sesiones del 19 termina el 26, sin precio válido.
    assert p.loc[FECHAS[0], "estado_ret_5_objetivo"] == "sin precio final"
    assert np.isnan(p.loc[FECHAS[0], "div_5_objetivo"])
    assert p.loc[ex, "ret_1_objetivo"] == p.loc[ex, "ret_precio_1_objetivo"]
    # La referencia es un índice de precio: sin dividendos.
    assert (r.etiquetas.loc[r.etiquetas["serie"] == "referencia", "dividendos"] == 0.0).all()
    # Sin cotización del objetivo: etiquetas ausentes con motivo, en las dos puntas.
    e = _serie(r, "objetivo")
    assert e.loc[FECHAS[0], "estado"] == "sin precio final"
    assert e.loc[FECHAS[0], "label_available_at"] == cal.instante(FECHAS[1]) + pd.Timedelta(minutes=15)
    assert e.loc[FECHAS[1], "estado"] == "sin precio inicial"
    assert "sin cotización de SPY" in e.loc[FECHAS[1], "motivo"]
    # Spread anormal como única cotización al corte: ausente con motivo.
    assert e.loc[FECHAS[5], "estado"] == "sin precio inicial" and "spread anormal" in e.loc[FECHAS[5], "motivo"]
    # Nada de esto toca la referencia ni las medidas de las opciones.
    base = pl.ejecutar(cot, sub[sub["subyacente"] != "SPY"], FECHAS, cfg).principal
    medidas = [c for c in base.columns if not c.endswith("_objetivo")]
    pd.testing.assert_frame_equal(p.reset_index()[medidas], base[medidas])


def test_revisiones_despues_de_madurar_y_de_aceptarse(cfg, mercado, resultado):
    # Revalidación de a5e2748, §4: los 60 días son una política, no una garantía; se miden las revisiones.
    a = resultado.dictamen["alcance"]
    assert (a["revisadas_objetivo"], a["revisadas_tras_aceptar_objetivo"]) == (0, 0)
    cot, sub, verdad = mercado
    d = verdad["dividendos"]
    tarde = pd.Timestamp("2026-10-01T15:00:00Z")  # corregido después de la consulta que acepta (26 de septiembre)
    corregido = pd.concat([d.assign(retirado_utc=tarde, motivo_retiro="corregido"),
                           d.assign(monto=1.85, recibido_utc=tarde)], ignore_index=True)
    r = pl.ejecutar(cot, sub, FECHAS, cfg, dividendos=corregido, cobertura=verdad["cobertura"])
    a = r.dictamen["alcance"]
    assert (a["revisadas_objetivo"], a["revisadas_tras_aceptar_objetivo"]) == (1, 1)
    assert a["estados_rendimiento_objetivo"]["provisional"] == 1  # vuelve a provisional hasta otra consulta
    viernes = FECHAS[2]
    p = r.principal.set_index("fecha")
    assert (p.loc[viernes, "div_1_objetivo"], p.loc[viernes, "version_1_objetivo"]) == (1.85, 2)
    # Madurada con la corrección ya conocida (antes de aceptarse), la revisión no cuenta como posterior.
    temprano = pd.Timestamp("2025-12-01T15:00:00Z")
    antes = pd.concat([d.assign(retirado_utc=temprano, motivo_retiro="corregido"),
                       d.assign(monto=1.85, recibido_utc=temprano)], ignore_index=True)
    a = pl.ejecutar(cot, sub, FECHAS, cfg, dividendos=antes, cobertura=verdad["cobertura"]).dictamen["alcance"]
    assert (a["revisadas_objetivo"], a["revisadas_tras_aceptar_objetivo"]) == (1, 0)


def test_rendimiento_total_sin_dividendos_queda_ausente(cfg, mercado, resultado):
    cot, sub, _ = mercado
    sin = pl.ejecutar(cot, sub, FECHAS, cfg)  # sin tabla de dividendos
    p, con = sin.principal, resultado.principal
    assert p["ret_1_objetivo"].isna().all() and (p["estado_ret_1_objetivo"] == "sin dividendos confirmados").all()
    pd.testing.assert_series_equal(p["ret_precio_1_objetivo"], con["ret_precio_1_objetivo"])
    assert sin.dictamen["alcance"]["dividendos_objetivo"].startswith("sin consulta")
    criterio = next(c for c in sin.dictamen["criterios"] if c["criterio"].startswith("Etiqueta del objetivo"))
    assert criterio["valor"] == 0.0 and criterio["critico"]
    # Revalidación de a5e2748, P2: una consulta que solo pidió splits tampoco habilita, y el alcance lo dice.
    _, _, verdad = mercado
    splits = verdad["cobertura"].assign(tipos="forward_split")
    solo = pl.ejecutar(cot, sub, FECHAS, cfg, dividendos=verdad["dividendos"], cobertura=splits)
    assert (solo.principal["estado_ret_1_objetivo"] == "sin dividendos confirmados").all()
    assert solo.dictamen["alcance"]["dividendos_objetivo"] == (
        "sin consulta completa que pueda confirmar dividendos: el rendimiento total queda ausente; "
        f"{len(splits)} consultas sin dividendos en los tipos pedidos no cuentan")
    # Con la convención de precio no hacen falta: las dos columnas coinciden.
    datos = dict(cfg.fuente, objetivo=dict(cfg.fuente["objetivo"], rendimiento="precio"))
    precio = pl.ejecutar(cot, sub, FECHAS, pl.config_desde_dict(datos)).principal
    pd.testing.assert_series_equal(precio["ret_1_objetivo"], precio["ret_precio_1_objetivo"], check_names=False)
    assert (precio["div_1_objetivo"] == 0.0).all()
    with pytest.raises(ValueError, match="rendimiento debe ser total o precio"):
        pl.config_desde_dict(dict(cfg.fuente, objetivo=dict(cfg.fuente["objetivo"], rendimiento="ajustado")))
