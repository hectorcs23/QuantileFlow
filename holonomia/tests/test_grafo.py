"""Topología del grafo: aristas, triángulos, ciclos y números de Betti."""
from __future__ import annotations

import numpy as np
import pytest

from holonomia import grafo as G


def test_cuadrado_sin_diagonal_no_tiene_triangulos():
    g = G.desde_aristas([("A", "B"), ("B", "C"), ("C", "D"), ("A", "D")])
    assert g.monedas == ("A", "B", "C", "D")
    assert g.n_aristas == 4
    assert g.caras == ()
    assert g.rango_ciclos() == 1
    assert g.betti1() == 1          # el hueco del cuadrado


def test_triangulo_relleno_no_tiene_parte_armonica():
    g = G.desde_aristas([("A", "B"), ("B", "C"), ("A", "C")])
    assert g.caras == (("A", "B", "C"),)
    assert g.rango_ciclos() == 1
    assert g.betti1() == 0


def test_quitar_la_cara_abre_el_hueco():
    """Mismo grafo, distinto complejo: el armónico depende de qué es operable."""
    aristas = [("A", "B"), ("B", "C"), ("A", "C")]
    assert G.desde_aristas(aristas).betti1() == 0
    assert G.desde_aristas(aristas, caras=[]).betti1() == 1


def test_grafo_de_alpaca_tiene_la_forma_inventariada(simbolos_alpaca):
    g = G.desde_simbolos(simbolos_alpaca)
    assert g.n_monedas == 37
    assert g.n_aristas == 73
    assert g.n_componentes() == 1
    assert g.n_caras == 60
    assert g.rango_ciclos() == 37


def test_el_complejo_de_cliques_de_alpaca_no_deja_parte_armonica(simbolos_alpaca):
    """Resultado estructural, no empírico: con los 60 triángulos, b₁ = 0.

    Los 60 triángulos generan todo el espacio de ciclos, así que la parte
    armónica es idénticamente cero sea cual sea el precio. Medir armónico en
    este mercado exige quitar caras: las que no son operables.
    """
    g = G.desde_simbolos(simbolos_alpaca)
    assert g.betti1() == 0


def test_quitar_triangulos_no_operables_abre_huecos(simbolos_alpaca):
    todas = G.desde_simbolos(simbolos_alpaca).caras
    operables = [c for c in todas if "USDT" not in c]
    g = G.desde_simbolos(simbolos_alpaca, caras=operables)
    assert g.betti1() > 0


def test_d1_compuesto_con_d0_es_cero(simbolos_juguete):
    """``d1 ∘ d0 = 0``: es lo que hace ortogonales gradiente y rotacional."""
    g = G.desde_simbolos(simbolos_juguete)
    producto = (g.d1() @ g.d0()).toarray()
    assert np.allclose(producto, 0.0)


def test_holonomia_de_un_gradiente_es_cero(simbolos_juguete):
    g = G.desde_simbolos(simbolos_juguete)
    rng = np.random.default_rng(0)
    phi = rng.normal(size=g.n_monedas)
    A = g.d0() @ phi
    for ciclo in G.ciclos_simples(g, longitud_max=4):
        assert g.holonomia(A, ciclo) == pytest.approx(0.0, abs=1e-12)


def test_la_holonomia_cambia_de_signo_al_invertir_el_ciclo(simbolos_juguete):
    g = G.desde_simbolos(simbolos_juguete)
    rng = np.random.default_rng(1)
    A = rng.normal(size=g.n_aristas)
    ciclo = ["BTC", "ETH", "USD"]
    assert g.holonomia(A, ciclo) == pytest.approx(-g.holonomia(A, ciclo[::-1]))


def test_ciclos_simples_no_repite_orientaciones():
    g = G.desde_aristas([("A", "B"), ("B", "C"), ("A", "C")])
    ciclos = G.ciclos_simples(g, longitud_max=3)
    assert len(ciclos) == 1
    assert sorted(ciclos[0]) == ["A", "B", "C"]


def test_ciclos_simples_encuentra_el_cuadrado():
    g = G.desde_aristas([("A", "B"), ("B", "C"), ("C", "D"), ("A", "D")])
    assert G.ciclos_simples(g, longitud_max=3) == []
    ciclos = G.ciclos_simples(g, longitud_max=4)
    assert len(ciclos) == 1
    assert sorted(ciclos[0]) == ["A", "B", "C", "D"]


def test_cocadena_rechaza_valores_incompatibles():
    g = G.desde_aristas([("A", "B")])
    g.cocadena({("A", "B"): 1.0, ("B", "A"): -1.0})       # coherente
    with pytest.raises(ValueError, match="incompatibles"):
        g.cocadena({("A", "B"): 1.0, ("B", "A"): 1.0})


def test_cara_con_arista_inexistente_es_error():
    with pytest.raises(ValueError, match="arista inexistente"):
        G.Grafo(monedas=("A", "B", "C"), aristas=(("A", "B"),), caras=(("A", "B", "C"),))
