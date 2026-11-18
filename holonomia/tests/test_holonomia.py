"""Holonomía con precio medio y con precios ejecutables; comisiones."""
from __future__ import annotations

import math

import numpy as np
import pytest

from holonomia import grafo as G
from holonomia import hodge
from holonomia.holonomia import (COMISIONES_ALPACA, Comisiones, Cotizacion,
                                 cocadena_mid, holonomia_ejecutable, holonomia_mid,
                                 medio_spread_ciclo, umbral_ejecutable)


def mercado_consistente(simbolos, phi, medio_spread):
    """Cotizaciones generadas por un φ, con medio spread simétrico en logs.

    Por construcción ``H_mid = 0`` en todo ciclo: es el control «no hay nada».
    """
    indice = {m: p for m, p in phi.items()}
    cots = {}
    for s in simbolos:
        base, cotizada = s.split("/")
        # A(base→cotizada) = φ_cotizada − φ_base = log(precio del par)
        mid = math.exp(indice[cotizada] - indice[base])
        cots[s] = Cotizacion(simbolo=s,
                             bid=mid * math.exp(-medio_spread),
                             ask=mid * math.exp(+medio_spread))
    return cots


@pytest.fixture
def phi_juguete(simbolos_juguete):
    rng = np.random.default_rng(42)
    monedas = sorted({m for s in simbolos_juguete for m in s.split("/")})
    return {m: float(v) for m, v in zip(monedas, rng.normal(scale=2.0, size=len(monedas)))}


# -- consistencia ---------------------------------------------------------
def test_mercado_consistente_tiene_holonomia_media_cero(simbolos_juguete, phi_juguete):
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=5e-4)
    g = G.desde_simbolos(simbolos_juguete)
    for ciclo in G.ciclos_simples(g, longitud_max=4):
        assert holonomia_mid(cots, ciclo) == pytest.approx(0.0, abs=1e-12)


def test_la_cocadena_mid_coincide_con_la_holonomia_directa(simbolos_juguete, phi_juguete):
    """Dos caminos al mismo número: por el grafo y por las cotizaciones."""
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=1e-3)
    cots["ETH/BTC"] = Cotizacion("ETH/BTC", bid=cots["ETH/BTC"].bid * 1.002,
                                 ask=cots["ETH/BTC"].ask * 1.002)
    g = G.desde_simbolos(simbolos_juguete)
    A = cocadena_mid(g, cots)
    for ciclo in G.ciclos_simples(g, longitud_max=4):
        assert g.holonomia(A, ciclo) == pytest.approx(holonomia_mid(cots, ciclo), abs=1e-12)


# -- la identidad que separa curvatura de dinero -------------------------
@pytest.mark.parametrize("nivel", sorted(COMISIONES_ALPACA))
def test_identidad_entre_holonomia_media_y_ejecutable(simbolos_juguete, phi_juguete, nivel):
    """``H_exec = H_mid − Σ s + L log(1 − f)``, exacta con el medio geométrico."""
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=7e-4)
    cots["ETH/BTC"] = Cotizacion("ETH/BTC", bid=cots["ETH/BTC"].bid * 1.01,
                                 ask=cots["ETH/BTC"].ask * 1.01)
    com = Comisiones.alpaca(nivel)
    g = G.desde_simbolos(simbolos_juguete)
    for ciclo in G.ciclos_simples(g, longitud_max=4):
        L = len(ciclo)
        esperado = (holonomia_mid(cots, ciclo) - medio_spread_ciclo(cots, ciclo)
                    + L * math.log1p(-com.taker))
        assert holonomia_ejecutable(cots, ciclo, com) == pytest.approx(esperado, abs=1e-12)


def test_el_umbral_es_la_diferencia_entre_las_dos_holonomias(simbolos_juguete, phi_juguete):
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=4e-4)
    com = Comisiones.alpaca(1)
    for ciclo in G.ciclos_simples(G.desde_simbolos(simbolos_juguete), longitud_max=4):
        h_exec = holonomia_ejecutable(cots, ciclo, com)
        assert h_exec == pytest.approx(holonomia_mid(cots, ciclo)
                                       - umbral_ejecutable(cots, ciclo, com), abs=1e-12)


# -- el control «no hay nada» --------------------------------------------
def test_sin_curvatura_el_ciclo_siempre_pierde(simbolos_juguete, phi_juguete):
    """Mercado consistente con spread y comisión: nunca hay arbitraje."""
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=5e-4)
    com = Comisiones.alpaca(1)
    for ciclo in G.ciclos_simples(G.desde_simbolos(simbolos_juguete), longitud_max=4):
        assert holonomia_ejecutable(cots, ciclo, com) < 0.0


def test_sin_spread_ni_comision_el_ciclo_queda_plano(simbolos_juguete, phi_juguete):
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=0.0)
    for ciclo in G.ciclos_simples(G.desde_simbolos(simbolos_juguete), longitud_max=4):
        assert holonomia_ejecutable(cots, ciclo, Comisiones.sin_costo()) == pytest.approx(0.0, abs=1e-12)


# -- arbitraje inyectado, visto desde la ejecución -----------------------
def test_un_arbitraje_pequeno_no_sobrevive_a_los_costos(simbolos_juguete, phi_juguete):
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=5e-4)
    eps = 1e-3                           # 10 pb: menos que spread + 3 × 25 pb
    c = cots["ETH/BTC"]
    cots["ETH/BTC"] = Cotizacion("ETH/BTC", bid=c.bid * math.exp(eps), ask=c.ask * math.exp(eps))
    ciclo = ["BTC", "ETH", "USD"]
    assert holonomia_mid(cots, ciclo) == pytest.approx(-eps, abs=1e-12)
    assert holonomia_ejecutable(cots, ciclo[::-1], Comisiones.alpaca(1)) < 0.0


def test_un_arbitraje_grande_si_sobrevive(simbolos_juguete, phi_juguete):
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=5e-4)
    eps = 0.05                           # 500 pb: muy por encima de los costos
    c = cots["ETH/BTC"]
    cots["ETH/BTC"] = Cotizacion("ETH/BTC", bid=c.bid * math.exp(eps), ask=c.ask * math.exp(eps))
    ciclo = ["USD", "ETH", "BTC"]        # el sentido que gana
    assert holonomia_mid(cots, ciclo) == pytest.approx(eps, abs=1e-12)
    assert holonomia_ejecutable(cots, ciclo, Comisiones.alpaca(1)) > 0.0
    assert holonomia_ejecutable(cots, ciclo[::-1], Comisiones.alpaca(1)) < 0.0


def test_los_dos_sentidos_no_pueden_ganar_a_la_vez(simbolos_juguete, phi_juguete):
    """``H_exec`` no es antisimétrica, y su parte simétrica es el costo."""
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=3e-4)
    com = Comisiones.alpaca(1)
    for ciclo in G.ciclos_simples(G.desde_simbolos(simbolos_juguete), longitud_max=4):
        ida = holonomia_ejecutable(cots, ciclo, com)
        vuelta = holonomia_ejecutable(cots, ciclo[::-1], com)
        assert ida + vuelta < 0.0
        assert not (ida > 0.0 and vuelta > 0.0)


# -- detalles de las cotizaciones ----------------------------------------
def test_medio_geometrico_parte_el_spread_exactamente_en_logs():
    c = Cotizacion("BTC/USD", bid=74291.527, ask=74317.91)
    s = c.medio_spread_log()
    assert math.log(c.bid) == pytest.approx(math.log(c.mid("geometrico")) - s)
    assert math.log(c.ask) == pytest.approx(math.log(c.mid("geometrico")) + s)


def test_los_dos_medios_casi_coinciden():
    c = Cotizacion("BTC/USD", bid=74291.527, ask=74317.91)
    assert c.mid("geometrico") == pytest.approx(c.mid("aritmetico"), rel=1e-6)


def test_mercado_cruzado_se_detecta():
    assert Cotizacion("BTC/USD", bid=100.0, ask=99.0).cruzado
    assert Cotizacion("BTC/USD", bid=100.0, ask=100.0).cruzado      # bloqueado
    assert not Cotizacion("BTC/USD", bid=99.0, ask=100.0).cruzado


def test_comisiones_de_alpaca_bajan_con_el_volumen():
    niveles = sorted(COMISIONES_ALPACA)
    makers = [Comisiones.alpaca(n).maker for n in niveles]
    takers = [Comisiones.alpaca(n).taker for n in niveles]
    assert makers == sorted(makers, reverse=True)
    assert takers == sorted(takers, reverse=True)
    assert Comisiones.alpaca(1).taker == 0.0025


def test_paso_sin_cotizacion_es_error(simbolos_juguete, phi_juguete):
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=1e-4)
    with pytest.raises(KeyError, match="XRP"):
        holonomia_ejecutable(cots, ["XRP", "BTC", "USD"], Comisiones.alpaca(1))


# -- enlace con Hodge -----------------------------------------------------
def test_un_mercado_consistente_es_puro_gradiente(simbolos_juguete, phi_juguete):
    cots = mercado_consistente(simbolos_juguete, phi_juguete, medio_spread=6e-4)
    g = G.desde_simbolos(simbolos_juguete)
    d = hodge.descomponer(g, cocadena_mid(g, cots))
    assert d.fracciones()["gradiente"] == pytest.approx(1.0, abs=1e-12)
    precios = hodge.precios_implicitos(g, d, "USD")
    assert precios["BTC"] == pytest.approx(cots["BTC/USD"].mid(), rel=1e-12)
