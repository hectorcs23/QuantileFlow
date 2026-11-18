"""Filtros, panel sin mirar al futuro y el control de asincronía (§2.6)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from holonomia import limpieza
from holonomia.holonomia import Comisiones

T0 = pd.Timestamp("2026-11-10T15:00:00Z")


def marco(filas):
    """Arma un marco con el esquema de §2.2 desde tuplas (par, bid, ask, t_seg)."""
    df = pd.DataFrame([{"par": p, "bid": b, "ask": a, "bid_size": 1.0, "ask_size": 1.0,
                        "ts_exchange": T0 + pd.Timedelta(seconds=t),
                        "ts_captura": T0 + pd.Timedelta(seconds=60)} for p, b, a, t in filas])
    return df


# -- filtros --------------------------------------------------------------
def test_filtrar_cuenta_cada_motivo():
    df = marco([
        ("BTC/USD", 100.0, 101.0, 0.0),    # buena
        ("BTC/USD", 101.0, 100.0, 1.0),    # cruzada
        ("BTC/USD", 100.0, 100.0, 2.0),    # bloqueada
        ("BTC/USD", 0.0, 100.0, 3.0),      # bid en cero
        ("BTC/USD", 1.0, 1000.0, 4.0),     # medio spread absurdo
        ("BTC/USD", np.nan, 101.0, 5.0),   # no finita
    ])
    limpio, reg = limpieza.filtrar(df)
    assert len(limpio) == 1
    assert reg.filas_entrada == 6 and reg.filas_salida == 1
    assert reg.motivos["cruzado o bloqueado"] == 2
    assert reg.motivos["precio no positivo"] == 1
    assert reg.motivos["medio spread absurdo"] == 1
    assert reg.motivos["no finitos"] == 1
    assert set(reg.como_tabla()["motivo"]) == set(reg.motivos)


def test_filtrar_no_toca_un_marco_limpio():
    df = marco([("BTC/USD", 100.0, 100.5, 0.0), ("ETH/USD", 10.0, 10.05, 1.0)])
    limpio, reg = limpieza.filtrar(df)
    assert len(limpio) == 2 and reg.motivos == {}


def test_exigir_tamanos_descarta_cotizaciones_sin_tamano():
    df = marco([("BTC/USD", 100.0, 100.5, 0.0)])
    df.loc[0, "ask_size"] = 0.0
    assert len(limpieza.filtrar(df, exigir_tamanos=True)[0]) == 0
    assert len(limpieza.filtrar(df, exigir_tamanos=False)[0]) == 1


# -- panel ----------------------------------------------------------------
def test_el_panel_no_mira_hacia_adelante():
    df = marco([("BTC/USD", 100.0, 101.0, 0.0),
                ("BTC/USD", 200.0, 201.0, 10.0),
                ("ETH/USD", 10.0, 10.1, 5.0)])
    p = limpieza.panel(df)
    # en t = 5 s la única cotización de BTC con sello ≤ t es la de t = 0
    assert p.loc[T0 + pd.Timedelta(seconds=5), ("BTC/USD", "bid")] == 100.0
    # antes del primer evento de ETH no hay nada: NaN, no el valor futuro
    assert pd.isna(p.loc[T0, ("ETH/USD", "bid")])
    assert p.loc[T0 + pd.Timedelta(seconds=10), ("BTC/USD", "bid")] == 200.0


def test_edades_miden_la_antiguedad_de_la_cotizacion_vigente():
    df = marco([("BTC/USD", 100.0, 101.0, 0.0), ("ETH/USD", 10.0, 10.1, 7.0)])
    ed = limpieza.edades(limpieza.panel(df))
    assert ed.loc[T0 + pd.Timedelta(seconds=7), "BTC/USD"] == 7.0
    assert ed.loc[T0 + pd.Timedelta(seconds=7), "ETH/USD"] == 0.0


def test_el_panel_exige_que_los_pares_existan():
    with pytest.raises(KeyError, match="LTC/USD"):
        limpieza.panel(marco([("BTC/USD", 1.0, 1.1, 0.0)]), simbolos=["LTC/USD"])


# -- control de asincronía (§2.6) ----------------------------------------
def mercado_asincrono(semilla=0, n=40_000, paso=0.01, vol=2e-4, medio_spread=2e-4,
                      periodos=(0.03, 0.05, 2.0)):
    """Mercado **consistente en todo instante**, muestreado a distintos ritmos.

    Los log-precios siguen un paseo aleatorio común, así que la holonomía
    verdadera es cero siempre. Cada par se cotiza con su propio período: la
    tercera pata es cien veces más lenta que las otras dos. Toda la holonomía
    que aparezca es asincronía, no mercado.
    """
    rng = np.random.default_rng(semilla)
    t = np.arange(n) * paso
    # φ_i = −log(precio de i); USD es el numerario y no se mueve
    phi = {"USD": np.zeros(n)}
    for m in ("BTC", "ETH"):
        phi[m] = np.cumsum(rng.normal(scale=vol * np.sqrt(paso), size=n))

    simbolos = {"BTC/USD": ("BTC", "USD"), "ETH/USD": ("ETH", "USD"), "ETH/BTC": ("ETH", "BTC")}
    filas = []
    for (s, (base, cot)), periodo in zip(simbolos.items(), periodos):
        cada = max(int(round(periodo / paso)), 1)
        idx = np.arange(0, n, cada)
        mid = np.exp(phi[cot][idx] - phi[base][idx])
        filas.append(pd.DataFrame({
            "par": s,
            "bid": mid * np.exp(-medio_spread),
            "ask": mid * np.exp(+medio_spread),
            "bid_size": 1.0, "ask_size": 1.0,
            "ts_exchange": T0 + pd.to_timedelta(t[idx], unit="s"),
            "ts_captura": T0 + pd.Timedelta(seconds=t[-1] + 1),
        }))
    return pd.concat(filas, ignore_index=True).sort_values("ts_exchange").reset_index(drop=True)


def test_el_mercado_asincrono_es_consistente_en_cada_instante():
    """Antes de nada: el generador no mete arbitraje de verdad."""
    df = mercado_asincrono(periodos=(0.03, 0.03, 0.03))   # los tres al mismo ritmo
    p = limpieza.panel(df)
    serie = limpieza.serie_de_ciclo(p, ["BTC", "ETH", "USD"], delta_t=0.001)
    assert len(serie) > 100
    assert np.abs(serie["h_mid"]).max() < 1e-12


def test_la_asincronia_fabrica_holonomia_y_la_sincronizacion_la_quita():
    """El control de §2.6: sin ventana hay curvatura espuria; con ventana, no."""
    df = mercado_asincrono()
    p = limpieza.panel(df)
    ciclo = ["BTC", "ETH", "USD"]

    sin_ventana = limpieza.serie_de_ciclo(p, ciclo, delta_t=None)
    con_ventana = limpieza.serie_de_ciclo(p, ciclo, delta_t=0.05)

    espuria = np.abs(sin_ventana["h_mid"]).median()
    residual = np.abs(con_ventana["h_mid"]).median()

    assert len(con_ventana) > 50, "la ventana no puede dejar el panel vacío"
    assert espuria > 1e-5, "el control no tendría sentido si no apareciera nada"
    assert residual < espuria / 5


@pytest.mark.parametrize("semilla", [0, 1, 2])
def test_la_holonomia_espuria_baja_al_apretar_la_ventana(semilla):
    """Monótona en Δt: es la firma de la asincronía, no de inconsistencia."""
    p = limpieza.panel(mercado_asincrono(semilla=semilla))
    ciclo = ["BTC", "ETH", "USD"]
    medianas = []
    for dt in (2.0, 0.5, 0.1, 0.02):
        serie = limpieza.serie_de_ciclo(p, ciclo, delta_t=dt)
        assert len(serie) > 20
        medianas.append(float(np.abs(serie["h_mid"]).median()))
    assert medianas == sorted(medianas, reverse=True)
    assert medianas[-1] < medianas[0] / 10


def test_la_asincronia_no_crea_arbitraje_ejecutable():
    """La curvatura espuria es chica frente a spread y comisiones: no da dinero."""
    p = limpieza.panel(mercado_asincrono())
    serie = limpieza.serie_de_ciclo(p, ["BTC", "ETH", "USD"], Comisiones.alpaca(1), delta_t=None)
    assert (serie["h_exec"] > 0).sum() == 0


# -- enlace con el resto --------------------------------------------------
def test_la_serie_cumple_la_identidad_entre_las_dos_holonomias():
    p = limpieza.panel(mercado_asincrono(n=4_000))
    serie = limpieza.serie_de_ciclo(p, ["BTC", "ETH", "USD"], Comisiones.alpaca(1), delta_t=1.0)
    assert len(serie) > 10
    assert np.allclose(serie["h_exec"], serie["h_mid"] - serie["umbral"], atol=1e-12)


def test_cocadenas_del_panel_alimenta_a_hodge():
    from holonomia import grafo as G
    from holonomia import hodge

    p = limpieza.panel(mercado_asincrono(n=2_000, periodos=(0.03, 0.03, 0.03)))
    g = G.desde_simbolos(["BTC/USD", "ETH/USD", "ETH/BTC"])
    instantes = list(limpieza.cocadenas_del_panel(p, g, delta_t=0.001))
    assert len(instantes) > 50
    for _, A in instantes[:20]:
        d = hodge.descomponer(g, A)
        assert d.fracciones()["gradiente"] == pytest.approx(1.0, abs=1e-12)


def test_cocadenas_del_panel_avisa_si_falta_una_arista():
    from holonomia import grafo as G

    p = limpieza.panel(mercado_asincrono(n=500), simbolos=["BTC/USD", "ETH/USD"])
    g = G.desde_simbolos(["BTC/USD", "ETH/USD", "ETH/BTC"])
    with pytest.raises(ValueError, match="aristas del grafo"):
        list(limpieza.cocadenas_del_panel(p, g))
