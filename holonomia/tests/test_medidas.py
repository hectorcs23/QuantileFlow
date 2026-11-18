"""Mediciones de §2.5: resumen por ciclo, persistencia y reparto de Hodge."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from holonomia import grafo as G
from holonomia import limpieza, medidas
from holonomia.holonomia import Comisiones

from test_limpieza import T0, mercado_asincrono


# -- persistencia ---------------------------------------------------------
def test_la_acf_de_un_ar1_es_rho_a_la_k():
    rho = 0.9
    rng = np.random.default_rng(0)
    x = np.zeros(200_000)
    for i in range(1, len(x)):
        x[i] = rho * x[i - 1] + rng.normal()
    serie = pd.Series(x, index=pd.date_range(T0, periods=len(x), freq="1s"))
    acf = medidas.autocorrelacion(serie, max_lag=20)
    assert acf[0] == pytest.approx(1.0)
    for k in (1, 5, 10):
        assert acf[k] == pytest.approx(rho ** k, abs=0.02)


def test_la_vida_media_coincide_con_la_teorica():
    rho = 0.9
    acf = pd.Series({k: rho ** k for k in range(40)})
    assert medidas.vida_media(acf) == pytest.approx(np.log(0.5) / np.log(rho), abs=0.05)


def test_la_vida_media_avisa_cuando_no_decae():
    assert np.isnan(medidas.vida_media(pd.Series({k: 0.99 for k in range(10)})))


def test_la_acf_salta_los_huecos():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(size=5_000),
                  index=pd.date_range(T0, periods=5_000, freq="1s"))
    x.iloc[1000:2000] = np.nan
    acf = medidas.autocorrelacion(x, max_lag=5)
    assert acf[0] == pytest.approx(1.0)
    assert abs(acf[3]) < 0.1


# -- resumen por ciclo ----------------------------------------------------
def test_un_mercado_consistente_no_deja_nada_que_explotar():
    p = limpieza.panel(mercado_asincrono(n=4_000, periodos=(0.03, 0.03, 0.03)))
    r = medidas.resumen_de_ciclo(p, ["BTC", "ETH", "USD"], Comisiones.alpaca(1), delta_t=0.001)
    assert r["instantes"] > 50
    assert r["mediana_abs_h_mid_pb"] == pytest.approx(0.0, abs=1e-8)
    assert r["frac_h_exec_positiva"] == 0.0
    assert r["frac_fuera_del_spread"] == 0.0
    assert r["mediana_umbral_pb"] > r["mediana_medio_spread_pb"]   # las comisiones suman


def test_el_resumen_devuelve_fila_vacia_si_no_hay_instantes():
    """Sin ningún instante con las tres patas frescas, el resumen sale vacío.

    Se quita el arranque, donde los tres pares cotizan a la vez por
    construcción del generador, para que no quede ni una coincidencia exacta.
    """
    df = mercado_asincrono(n=500)
    df = df[df["ts_exchange"] > df["ts_exchange"].min()]
    p = limpieza.panel(df)
    r = medidas.resumen_de_ciclo(p, ["BTC", "ETH", "USD"], delta_t=1e-9)
    assert r["instantes"] == 0
    assert "mediana_abs_h_mid_pb" not in r


def test_resumen_por_ciclo_arma_una_tabla():
    p = limpieza.panel(mercado_asincrono(n=2_000, periodos=(0.03, 0.03, 0.03)))
    tabla = medidas.resumen_por_ciclo(p, [["BTC", "ETH", "USD"], ["USD", "ETH", "BTC"]],
                                      delta_t=0.01)
    assert len(tabla) == 2
    assert {"ciclo", "instantes", "mediana_abs_h_mid_pb"} <= set(tabla.columns)


# -- sensibilidad a Δt ----------------------------------------------------
def test_la_sensibilidad_detecta_la_asincronia():
    p = limpieza.panel(mercado_asincrono())
    tabla = medidas.sensibilidad_delta_t(p, ["BTC", "ETH", "USD"],
                                         deltas=(2.0, 0.5, 0.1, 0.02))
    assert len(tabla) == 4
    med = tabla["mediana_abs_h_mid_pb"].to_list()
    assert med == sorted(med, reverse=True)


# -- reparto de Hodge en el tiempo ---------------------------------------
def test_con_todo_fresco_no_hay_parte_armonica():
    p = limpieza.panel(mercado_asincrono(n=2_000, periodos=(0.03, 0.03, 0.03)))
    g = G.desde_simbolos(["BTC/USD", "ETH/USD", "ETH/BTC"])
    r = medidas.reparto_en_el_tiempo(p, g, delta_t=0.05, malla=p.index[::20])
    assert len(r) > 10
    assert (r["b1"] == 0).all()
    assert r["frac_armonico"].max() == pytest.approx(0.0, abs=1e-12)
    assert r["caras"].max() == 1


def test_una_pata_rancia_deja_al_triangulo_sin_instantes_evaluables():
    """Una pata lenta no «abre un hueco»: borra el ciclo del complejo fresco.

    Con tres aristas, perder una deja un camino sin ciclos, así que el
    instante no aporta nada y ``reparto_en_el_tiempo`` lo salta. El efecto
    medible es que casi no quedan instantes evaluables, mientras que con las
    tres patas al mismo ritmo quedan casi todos. Que la pérdida de una cara
    deje parte **armónica** necesita un grafo más grande: eso es el test
    siguiente.
    """
    g = G.desde_simbolos(["BTC/USD", "ETH/USD", "ETH/BTC"])
    rapido = limpieza.panel(mercado_asincrono(n=3_000, periodos=(0.03, 0.03, 0.03)))
    lento = limpieza.panel(mercado_asincrono(n=3_000, periodos=(0.03, 0.03, 5.0)))

    r_rapido = medidas.reparto_en_el_tiempo(rapido, g, delta_t=0.1, malla=rapido.index[::10])
    r_lento = medidas.reparto_en_el_tiempo(lento, g, delta_t=0.1, malla=lento.index[::10])

    assert len(r_rapido) > 50
    assert len(r_lento) < len(r_rapido) / 10
    assert (r_rapido["caras"] == 1).all()


def test_quitar_una_cara_de_un_cuadrado_deja_parte_armonica():
    """El mecanismo, aislado: cuatro monedas, un cruce que se vuelve rancio."""
    rng = np.random.default_rng(3)
    n, paso = 3_000, 0.01
    t = np.arange(n) * paso
    phi = {"USD": np.zeros(n)}
    for m in ("BTC", "ETH", "LTC"):
        phi[m] = np.cumsum(rng.normal(scale=2e-4 * np.sqrt(paso), size=n))
    pares = {"BTC/USD": 0.02, "ETH/USD": 0.02, "LTC/USD": 0.02,
             "ETH/BTC": 0.02, "LTC/BTC": 0.02}
    filas = []
    for s, periodo in pares.items():
        base, cot = s.split("/")
        idx = np.arange(0, n, max(int(periodo / paso), 1))
        mid = np.exp(phi[cot][idx] - phi[base][idx])
        filas.append(pd.DataFrame({"par": s, "bid": mid * 0.9999, "ask": mid * 1.0001,
                                   "bid_size": 1.0, "ask_size": 1.0,
                                   "ts_exchange": T0 + pd.to_timedelta(t[idx], unit="s"),
                                   "ts_captura": T0}))
    df = pd.concat(filas, ignore_index=True)
    g = G.desde_simbolos(list(pares))
    assert g.betti1() == 0                      # con las 5 aristas, sin huecos
    gf = medidas.subgrafo_fresco(g, {("BTC", "USD"), ("ETH", "USD"), ("LTC", "USD"),
                                     ("BTC", "ETH")})
    assert gf.n_caras == 1 and gf.betti1() == 0
    gf2 = medidas.subgrafo_fresco(g, {("BTC", "ETH"), ("BTC", "LTC"),
                                      ("ETH", "USD"), ("LTC", "USD")})
    assert gf2.n_caras == 0 and gf2.betti1() == 1   # el cuadrado sin diagonal

    r = medidas.reparto_en_el_tiempo(limpieza.panel(df), g, delta_t=1.0,
                                     malla=limpieza.panel(df).index[::5])
    assert len(r) > 10
    assert set(r.columns) >= {"b1", "frac_gradiente", "frac_rotacional", "frac_armonico"}
    assert np.allclose(r[["frac_gradiente", "frac_rotacional", "frac_armonico"]].sum(axis=1), 1.0)


# -- actividad ------------------------------------------------------------
def test_la_volatilidad_realizada_crece_con_la_volatilidad_verdadera():
    baja = limpieza.panel(mercado_asincrono(n=6_000, vol=1e-4, periodos=(0.03,) * 3))
    alta = limpieza.panel(mercado_asincrono(n=6_000, vol=1e-3, periodos=(0.03,) * 3))
    v_baja = medidas.volatilidad_realizada(baja, "BTC/USD", paso="10s").median()
    v_alta = medidas.volatilidad_realizada(alta, "BTC/USD", paso="10s").median()
    assert v_alta > 5 * v_baja


def test_la_intensidad_cuenta_cotizaciones_nuevas():
    df = mercado_asincrono(n=6_000, periodos=(0.1, 0.1, 1.0))
    p = limpieza.panel(df)
    i = medidas.intensidad(p, ["BTC/USD", "ETH/USD", "ETH/BTC"], paso="10s")
    esperado = len(df[df["ts_exchange"] < df["ts_exchange"].min() + pd.Timedelta("10s")])
    assert abs(i.iloc[0] - esperado) <= 3


def test_la_vida_media_interpola_aunque_la_acf_tenga_huecos():
    """Con pocos datos la ACF sale con NaN sueltos; el cruce igual se ubica."""
    rho = 0.9
    acf = pd.Series({k: rho ** k for k in range(40)})
    acf.loc[6] = np.nan          # justo antes del cruce de ½
    vm = medidas.vida_media(acf)
    assert np.isfinite(vm)
    assert vm == pytest.approx(np.log(0.5) / np.log(rho), abs=0.4)


def test_la_vida_media_es_cero_si_ya_arranca_bajo_un_medio():
    assert medidas.vida_media(pd.Series({0: 0.2, 1: 0.1})) == 0.0


def test_la_holonomia_crece_con_la_antiguedad_cuando_es_asincronia():
    """Control positivo: en el mercado asíncrono, la rancidez sí se nota."""
    p = limpieza.panel(mercado_asincrono())
    tabla = medidas.holonomia_por_antiguedad(p, ["BTC", "ETH", "USD"], delta_t=2.0)
    assert len(tabla) >= 4
    assert (tabla["mediana_abs_h_mid_pb"].iloc[-1]
            > 3 * tabla["mediana_abs_h_mid_pb"].iloc[0])


def test_la_holonomia_no_depende_de_la_antiguedad_si_el_mercado_es_consistente():
    """Control negativo: sin inconsistencia ni deriva relativa, sale plano en cero."""
    p = limpieza.panel(mercado_asincrono(vol=0.0, periodos=(0.03, 0.05, 2.0)))
    tabla = medidas.holonomia_por_antiguedad(p, ["BTC", "ETH", "USD"], delta_t=2.0)
    assert len(tabla) >= 4
    assert tabla["mediana_abs_h_mid_pb"].max() < 1e-8
