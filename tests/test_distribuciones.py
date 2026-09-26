"""Cuantiles desde densidades: sin normalizar masa faltante ni recortar negativos."""
import numpy as np
from scipy.stats import norm

from quantileflow import distribuciones as ds
from quantileflow import sintetico, superficies

U = np.array([0.001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.999])


def test_masa_faltante_sin_ancla_no_identifica_nada():
    x = np.linspace(-2.0, 3.0, 4001)  # falta Phi(-2) = 2.3 % a la izquierda
    c = ds.cuantiles_desde_densidad(x, norm.pdf(x), U)
    assert np.all(c.estado == ds.NO_IDENTIFICADA)
    assert np.all(np.isnan(c.valores))
    assert "no está anclada" in c.motivo


def test_masa_faltante_con_ancla_da_cuantiles_correctos_y_marca_colas():
    x = np.linspace(-2.0, 3.0, 4001)
    c = ds.cuantiles_desde_densidad(x, norm.pdf(x), U, masa_izquierda=norm.cdf(-2.0))
    dentro = (U >= norm.cdf(-2.0)) & (U <= norm.cdf(3.0))
    assert np.array_equal(c.identificado, dentro)
    assert np.allclose(c.valores[dentro], norm.ppf(U[dentro]), atol=1e-4)
    assert np.all(np.isnan(c.valores[~dentro]))
    assert set(c.estado[~dentro]) == {ds.NO_IDENTIFICADA}
    assert np.isclose(c.rango_u[0], norm.cdf(-2.0)) and np.isclose(c.rango_u[1], norm.cdf(3.0), atol=1e-6)
    # Normalizar habría movido la mediana: la del N(0,1) truncado y reescalado no es 0.
    assert abs(c.valores[U == 0.5][0]) < 1e-4
    cdf_normalizada = ds.cdf_desde_densidad(x, norm.pdf(x))
    cdf_normalizada /= cdf_normalizada[-1]
    assert abs(np.interp(0.5, cdf_normalizada, x)) > 0.02


def test_densidad_negativa_invalida_todos_los_niveles():
    x = np.linspace(-6.0, 6.0, 3001)
    p = norm.pdf(x) - 0.2 * np.exp(-0.5 * ((x - 1.5) / 0.05) ** 2)
    assert p.min() < 0.0
    c = ds.cuantiles_desde_densidad(x, p, U, masa_izquierda=0.0)
    assert np.all(c.estado == ds.DENSIDAD_INVALIDA)
    assert np.all(np.isnan(c.valores))
    assert c.diagnostico["puntos_negativos"] > 0 and c.diagnostico["masa_negativa"] > 0.0
    assert "negativa" in c.motivo


def test_negativos_de_redondeo_se_toleran_y_se_reportan():
    x = np.linspace(-8.0, 8.0, 4001)
    p = norm.pdf(x)
    p[[10, 20]] = -1e-14
    c = ds.cuantiles_desde_densidad(x, p, U)
    assert c.completo
    assert c.diagnostico["minimo"] == -1e-14
    assert np.allclose(c.valores, norm.ppf(U), atol=1e-4)


def test_masa_mayor_que_uno_es_invalida():
    x = np.linspace(-8.0, 8.0, 4001)
    c = ds.cuantiles_desde_densidad(x, 1.05 * norm.pdf(x), U)
    assert np.all(c.estado == ds.DENSIDAD_INVALIDA)


def test_rango_identificado_limita_las_colas():
    x = np.linspace(-8.0, 8.0, 4001)
    c = ds.cuantiles_desde_densidad(x, norm.pdf(x), U, rango_x=(-1.0, 1.5))
    dentro = (U >= norm.cdf(-1.0)) & (U <= norm.cdf(1.5))
    assert np.array_equal(c.identificado, dentro)
    assert np.allclose(c.valores[dentro], norm.ppf(U[dentro]), atol=1e-4)
    assert "cola izquierda" in c.motivo and "cola derecha" in c.motivo


def test_cdf_ssvi_analitica_y_cuantiles_sinteticos():
    sup = sintetico.superficie_referencia()
    T = sup.tiempos[1]
    theta = float(sup.theta_en(T))
    phi = float(sup.phi(theta))
    k = np.linspace(-1.2, 0.6, 6001)
    w, w1, w2 = superficies.derivadas_ssvi(k, theta, sup.rho, phi)
    F = superficies.cdf_logmoneyness(k, w, w1)
    p = superficies.densidad_logmoneyness(k, w, w1, w2)
    # La CDF analítica es la integral de la densidad (pendiente del precio = BL).
    assert np.max(np.abs(F - (F[0] + ds.cdf_desde_densidad(k, p)))) < 1e-5
    u = sintetico.malla_u()
    x, cobertura = sintetico.cuantiles_ssvi(theta, sup.rho, phi, u)
    assert cobertura > 1.0 - 1e-4
    assert np.max(np.abs(np.interp(x, k, F) - u)) < 1e-5
