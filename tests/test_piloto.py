"""Piloto: plazo constante, tabla diaria, etiquetas, dictamen y reproducibilidad (datos sintéticos)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantileflow import calendario as cal
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
    cot, sub, _ = mercado
    return pl.ejecutar(cot, sub, FECHAS, cfg)


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
    spot = {f: verdad["spot"][(f, cfg.hora_principal)] for f in FECHAS}
    assert p.loc[FECHAS[0], "ret_1"] == pytest.approx(np.log(spot[FECHAS[1]] / spot[FECHAS[0]]))
    assert p.loc[FECHAS[3], "retorno_previo"] == pytest.approx(np.log(spot[FECHAS[3]] / spot[FECHAS[2]]))
    miercoles = FECHAS[-2]  # su siguiente sesión es el viernes 28
    assert p.loc[miercoles, "ret_1"] == pytest.approx(np.log(spot[FECHAS[-1]] / spot[miercoles]))
    assert (p["estado_ret_5"] == "ok").all()  # el subyacente sintético cubre cinco sesiones más


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


def test_precio_objetivo_desfasado_o_tardio_deja_la_etiqueta_ausente(cfg, mercado):
    # H3: la frescura y la disponibilidad del precio objetivo llegan a las etiquetas.
    cot, sub, _ = mercado
    fechas = FECHAS[:3]
    viejo = sub.copy()
    dia = viejo["sello_snapshot_utc"].dt.tz_convert("America/New_York").dt.date == fechas[1]
    viejo.loc[dia, "sello_evento_utc"] = viejo.loc[dia, "sello_evento_utc"] - pd.Timedelta(minutes=10)
    r = pl.ejecutar(cot, viejo, fechas, cfg)
    e = r.etiquetas[r.etiquetas["horizonte"] == 1].set_index("sesion")
    assert e.loc[fechas[0], "estado"] == "sin precio final" and "desfasado" in e.loc[fechas[0], "motivo"]
    tarde = sub.copy()
    tarde.loc[dia, "disponible_utc"] = tarde.loc[dia, "disponible_utc"] + pd.Timedelta(hours=2)
    e = pl.ejecutar(cot, tarde, fechas, cfg).etiquetas
    e = e[e["horizonte"] == 1].set_index("sesion")
    assert e.loc[fechas[0], "estado"] == "sin precio final" and "después del corte" in e.loc[fechas[0], "motivo"]


def test_procedencia_en_la_tabla_diaria(resultado):
    p = resultado.principal
    assert set(p["fuente_opciones"]) == {"sintetico/nbbo_intervalos_sintetico"}
    assert set(p["fuente_subyacente"]) == {"sintetico/indice_sintetico"}
    assert set(p["tipo_precio_subyacente"]) == {"observado"}
    assert set(r["fuente"] for _, r in resultado.etiquetas.iterrows()) == {"sintetico/indice_sintetico"}
    assert resultado.dictamen["alcance"]["precio_objetivo"] == "observado"
    assert resultado.dictamen["alcance"]["evaluacion_con_precios_de_mercado"] == "no permitida: datos sintéticos"
