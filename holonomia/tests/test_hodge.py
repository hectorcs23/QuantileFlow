"""Los controles obligatorios de §2.6 sobre la descomposición de Hodge."""
from __future__ import annotations

import numpy as np
import pytest

from holonomia import grafo as G
from holonomia import hodge


# -- 1. sintético consistente --------------------------------------------
def test_sintetico_consistente_no_tiene_curvatura(simbolos_alpaca):
    """Precios generados con un φ: toda H = 0 y rotacional = armónico = 0."""
    g = G.desde_simbolos(simbolos_alpaca)
    rng = np.random.default_rng(20261118)
    phi = rng.normal(scale=5.0, size=g.n_monedas)
    A = g.d0() @ phi

    d = hodge.descomponer(g, A)
    assert np.linalg.norm(d.rotacional) == pytest.approx(0.0, abs=1e-10)
    assert np.linalg.norm(d.armonico) == pytest.approx(0.0, abs=1e-10)
    assert np.allclose(d.gradiente, A, atol=1e-10)
    for ciclo in G.ciclos_simples(g, longitud_max=3):
        assert g.holonomia(A, ciclo) == pytest.approx(0.0, abs=1e-10)


def test_el_potencial_recuperado_reproduce_los_precios(simbolos_juguete):
    g = G.desde_simbolos(simbolos_juguete)
    rng = np.random.default_rng(7)
    phi = rng.normal(size=g.n_monedas)
    d = hodge.descomponer(g, g.d0() @ phi)
    # φ sólo está fijado salvo una constante: se compara ya centrado
    assert np.allclose(d.potencial, phi - phi.mean(), atol=1e-10)
    precios = hodge.precios_implicitos(g, d, "USD")
    assert precios["USD"] == pytest.approx(1.0)


# -- 2. arbitraje inyectado ----------------------------------------------
def test_arbitraje_inyectado_se_recupera_exactamente(simbolos_alpaca):
    """Un ε conocido en un par reaparece en los ciclos que lo contienen.

    Con b₁ = 0 el armónico es nulo, así que todo el ε tiene que quedar en la
    parte rotacional: la holonomía calculada sólo con el rotacional coincide
    con la de A, y la del gradiente es cero.
    """
    g = G.desde_simbolos(simbolos_alpaca)
    rng = np.random.default_rng(4)
    A = g.d0() @ rng.normal(scale=5.0, size=g.n_monedas)

    eps = 3.7e-4
    par = ("BTC", "ETH")                      # ETH/BTC, canónica (BTC, ETH)
    k = g.indice_arista[par]
    A_arb = A.copy()
    A_arb[k] += eps

    d = hodge.descomponer(g, A_arb)
    assert np.linalg.norm(d.armonico) == pytest.approx(0.0, abs=1e-10)

    for ciclo in G.ciclos_simples(g, longitud_max=3):
        pasos = list(zip(ciclo, ciclo[1:] + ciclo[:1]))
        if par in pasos:
            esperado = eps
        elif par[::-1] in pasos:
            esperado = -eps
        else:
            esperado = 0.0
        assert g.holonomia(A_arb, ciclo) == pytest.approx(esperado, abs=1e-12)
        assert g.holonomia(d.rotacional, ciclo) == pytest.approx(esperado, abs=1e-10)
        assert g.holonomia(d.gradiente, ciclo) == pytest.approx(0.0, abs=1e-10)


# -- 3. hueco topológico (el «c₁» de juguete) ----------------------------
def test_hueco_topologico_deja_todo_en_el_armonico():
    """Cuadrado sin diagonal y circulación constante: puro armónico."""
    g = G.desde_aristas([("A", "B"), ("B", "C"), ("C", "D"), ("A", "D")])
    assert g.betti1() == 1

    c = 0.25
    A = g.cocadena({("A", "B"): c, ("B", "C"): c, ("C", "D"): c, ("D", "A"): c})
    d = hodge.descomponer(g, A)

    assert np.linalg.norm(d.gradiente) == pytest.approx(0.0, abs=1e-12)
    assert np.linalg.norm(d.rotacional) == pytest.approx(0.0, abs=1e-12)
    assert np.allclose(d.armonico, A, atol=1e-12)
    assert g.holonomia(A, ["A", "B", "C", "D"]) == pytest.approx(4 * c)
    assert d.fracciones()["armonico"] == pytest.approx(1.0)


def test_el_mismo_cuadrado_con_diagonal_no_deja_armonico():
    """Al rellenar el hueco, la misma circulación pasa a ser rotacional."""
    g = G.desde_aristas([("A", "B"), ("B", "C"), ("C", "D"), ("A", "D"), ("A", "C")])
    assert g.betti1() == 0
    c = 0.25
    A = g.cocadena({("A", "B"): c, ("B", "C"): c, ("C", "D"): c, ("D", "A"): c,
                    ("A", "C"): 0.0})
    d = hodge.descomponer(g, A)
    assert np.linalg.norm(d.armonico) == pytest.approx(0.0, abs=1e-12)
    assert d.fracciones()["rotacional"] > 0.0


# -- 4. ortogonalidad y reconstrucción -----------------------------------
@pytest.mark.parametrize("semilla", [0, 1, 2, 3, 4])
def test_ortogonalidad_y_reconstruccion(simbolos_alpaca, semilla):
    g = G.desde_simbolos(simbolos_alpaca)
    rng = np.random.default_rng(semilla)
    A = rng.normal(size=g.n_aristas)
    d = hodge.descomponer(g, A)

    assert hodge.error_reconstruccion(A, d) == pytest.approx(0.0, abs=1e-10)
    escala = np.linalg.norm(A) ** 2
    for nombre, valor in hodge.residuos_ortogonalidad(d).items():
        assert valor < 1e-10 * max(escala, 1.0), nombre
    assert sum(d.fracciones().values()) == pytest.approx(1.0)


def test_ortogonalidad_tambien_con_huecos():
    """Con b₁ > 0 las tres partes son no triviales y siguen siendo ortogonales."""
    aristas = [("A", "B"), ("B", "C"), ("C", "D"), ("A", "D"), ("A", "C")]
    g = G.desde_aristas(aristas, caras=[("A", "B", "C")])   # sólo una cara operable
    assert g.betti1() == 1
    rng = np.random.default_rng(11)
    A = rng.normal(size=g.n_aristas)
    d = hodge.descomponer(g, A)
    assert hodge.error_reconstruccion(A, d) == pytest.approx(0.0, abs=1e-12)
    for valor in hodge.residuos_ortogonalidad(d).values():
        assert valor < 1e-12 * max(np.linalg.norm(A) ** 2, 1.0)
    for parte in ("gradiente", "rotacional", "armonico"):
        assert d.fracciones()[parte] > 1e-6


# -- 5. contraste independiente ------------------------------------------
def test_la_enumeracion_directa_coincide_con_la_descomposicion(simbolos_juguete):
    """H por suma de aristas = H del rotacional + H del armónico."""
    g = G.desde_simbolos(simbolos_juguete)
    rng = np.random.default_rng(99)
    A = rng.normal(size=g.n_aristas)
    d = hodge.descomponer(g, A)
    for ciclo in G.ciclos_simples(g, longitud_max=4):
        directo = g.holonomia(A, ciclo)
        por_partes = g.holonomia(d.rotacional, ciclo) + g.holonomia(d.armonico, ciclo)
        assert directo == pytest.approx(por_partes, abs=1e-10)
        assert g.holonomia(d.gradiente, ciclo) == pytest.approx(0.0, abs=1e-10)


# -- 6. invariancia de gauge ---------------------------------------------
@pytest.mark.parametrize("semilla", [0, 1, 2])
def test_invariancia_de_gauge(simbolos_alpaca, semilla):
    """Sumar un gradiente arbitrario no mueve H ni las normas de rot y arm."""
    g = G.desde_simbolos(simbolos_alpaca)
    rng = np.random.default_rng(semilla)
    A = rng.normal(size=g.n_aristas)
    d = hodge.descomponer(g, A)

    chi = rng.normal(scale=10.0, size=g.n_monedas)
    A_gauge = A + g.d0() @ chi
    d_gauge = hodge.descomponer(g, A_gauge)

    assert np.allclose(d_gauge.rotacional, d.rotacional, atol=1e-10)
    assert np.allclose(d_gauge.armonico, d.armonico, atol=1e-10)
    for ciclo in G.ciclos_simples(g, longitud_max=3)[:25]:
        assert g.holonomia(A_gauge, ciclo) == pytest.approx(g.holonomia(A, ciclo), abs=1e-10)


def test_invariancia_de_gauge_con_huecos():
    aristas = [("A", "B"), ("B", "C"), ("C", "D"), ("A", "D"), ("A", "C")]
    g = G.desde_aristas(aristas, caras=[("A", "B", "C")])
    rng = np.random.default_rng(5)
    A = rng.normal(size=g.n_aristas)
    d = hodge.descomponer(g, A)
    d2 = hodge.descomponer(g, A + g.d0() @ rng.normal(scale=3.0, size=g.n_monedas))
    assert np.allclose(d2.rotacional, d.rotacional, atol=1e-12)
    assert np.allclose(d2.armonico, d.armonico, atol=1e-12)


# -- varios ---------------------------------------------------------------
def test_descomponer_rechaza_no_finitos(simbolos_juguete):
    g = G.desde_simbolos(simbolos_juguete)
    A = np.zeros(g.n_aristas)
    A[0] = np.nan
    with pytest.raises(ValueError, match="no finitos"):
        hodge.descomponer(g, A)


def test_dimension_del_armonico_es_betti1():
    """El espacio armónico tiene exactamente dimensión b₁: se mide por rango."""
    aristas = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("A", "E"),
               ("A", "C"), ("C", "E")]
    g = G.desde_aristas(aristas, caras=[])
    b1 = g.betti1()
    rng = np.random.default_rng(3)
    muestras = np.array([hodge.descomponer(g, rng.normal(size=g.n_aristas)).armonico
                         for _ in range(20)])
    assert np.linalg.matrix_rank(muestras, tol=1e-9) == b1


def test_la_fraccion_sobre_la_norma_total_la_domina_el_gradiente():
    """Advertencia convertida en test: con log-precios reales la fracción miente.

    Un mercado con 2 pb de arbitraje triangular y precios de orden ``e^10``
    da ``frac_gradiente ≈ 1 − 1e-10``. Ese número no dice nada del mercado:
    dice que los log-precios son grandes. ``fracciones_de_curvatura`` sí dice.
    """
    g = G.desde_aristas([("A", "B"), ("B", "C"), ("A", "C")])
    rng = np.random.default_rng(0)
    phi = rng.normal(scale=10.0, size=g.n_monedas)
    A = g.d0() @ phi
    A[g.indice_arista[("A", "B")]] += 2e-4          # 2 pb de inconsistencia

    d = hodge.descomponer(g, A)
    assert d.fracciones()["gradiente"] > 1 - 1e-8
    assert d.fracciones()["rotacional"] < 1e-8
    # la misma inconsistencia, vista dentro de la curvatura
    assert d.fracciones_de_curvatura()["rotacional"] == pytest.approx(1.0)
    # proyección de ε·e_AB sobre el único triángulo: ‖ε v/‖v‖²‖ = ε/√3
    assert d.norma_curvatura() == pytest.approx(2e-4 / np.sqrt(3), rel=1e-9)


def test_fracciones_de_curvatura_reparte_entre_local_y_global():
    aristas = [("A", "B"), ("B", "C"), ("C", "D"), ("A", "D"), ("A", "C")]
    g = G.desde_aristas(aristas, caras=[("A", "B", "C")])
    rng = np.random.default_rng(8)
    A = rng.normal(size=g.n_aristas)
    d = hodge.descomponer(g, A)
    frc = d.fracciones_de_curvatura()
    assert sum(frc.values()) == pytest.approx(1.0)
    assert frc["rotacional"] > 0 and frc["armonico"] > 0
    assert d.norma_curvatura() == pytest.approx(
        np.linalg.norm(d.rotacional + d.armonico), rel=1e-10)


def test_sin_curvatura_las_fracciones_de_curvatura_son_cero():
    g = G.desde_aristas([("A", "B"), ("B", "C"), ("A", "C")])
    rng = np.random.default_rng(1)
    d = hodge.descomponer(g, g.d0() @ rng.normal(size=g.n_monedas))
    assert d.fracciones_de_curvatura() == {"rotacional": 0.0, "armonico": 0.0}
    assert d.norma_curvatura() == pytest.approx(0.0, abs=1e-12)
