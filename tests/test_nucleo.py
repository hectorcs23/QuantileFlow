"""Pruebas de propiedades de los bloques matemáticos (datos sintéticos)."""
import numpy as np
import pytest

from quantileflow import (calibracion, decision, distribuciones, evidencia, filtrado, opciones,
                          regimenes, sintetico, superficies, transporte)


@pytest.fixture(scope="module")
def sup():
    return sintetico.superficie_referencia()


@pytest.fixture(scope="module")
def cadena():
    return sintetico.cadena_sintetica(np.random.default_rng(7))


# --- Superficies -------------------------------------------------------------

def test_ssvi_cumple_condiciones_suficientes(sup):
    assert all(sup.condiciones().values())
    k = np.linspace(-1.5, 1.0, 2001)
    for T in sup.tiempos:
        assert superficies.funcion_g(*sup.derivadas(k, T), k).min() >= 0.0
    # Sin arbitraje de calendario: w(k, T) no decrece en T para cada k.
    w = np.array([sup.w(k, T) for T in np.linspace(sup.tiempos[0], sup.tiempos[-1], 40)])
    assert np.all(np.diff(w, axis=0) >= -1e-14)


def test_svi_crudo_de_vogt_tiene_arbitraje_de_mariposa():
    k = np.linspace(-1.5, 1.5, 3001)
    w, w1, w2 = superficies.derivadas_svi_cruda(k, -0.0410, 0.1331, 0.3060, 0.3586, 0.4153)
    assert superficies.funcion_g(w, w1, w2, k).min() < 0.0


def test_ajuste_superficie_respeta_bandas_y_restricciones(cadena):
    rebanadas, _ = cadena
    ajuste = superficies.ajustar_superficie(rebanadas)
    assert ajuste.info["cotizaciones_fuera"] == 0
    assert all(ajuste.condiciones().values())


def test_ajuste_convexo_es_densidad_valida(cadena):
    reb = cadena[0][1]
    soporte = np.linspace(reb.F * 0.55, reb.F * 1.35, 161)
    q, precios, _ = superficies.ajuste_convexo(reb, soporte)
    assert q.min() >= 0.0
    assert abs(q.sum() - 1.0) < 1e-4
    assert abs(q @ soporte / reb.F - 1.0) < 1e-4
    K = np.linspace(soporte[0], soporte[-1], 300)
    C = reb.D * np.maximum(soporte[None, :] - K[:, None], 0.0) @ q
    assert np.all(np.diff(C) <= 1e-12)
    assert np.all(np.diff(C, 2) >= -1e-12)


# --- Distribuciones ------------------------------------------------------------

def test_breeden_litzenberger_coincide_con_densidad_analitica(sup):
    T = sup.tiempos[1]
    F, D = 100.0 * np.exp(0.027 * T), np.exp(-0.04 * T)
    K = np.linspace(55.0, 150.0, 5001)
    C = opciones.precio_black(F, K, sup.w(np.log(K / F), T), D, True)
    K_int, q = distribuciones.densidad_breeden_litzenberger(K, C, D)
    analitica = sup.densidad(np.log(K_int / F), T) / K_int
    assert np.max(np.abs(q - analitica)) < 1e-5
    controles = distribuciones.controles_densidad(K_int, q, F)
    assert controles["pasa"]


# --- Transporte ------------------------------------------------------------------

def test_wasserstein_de_traslacion_es_la_traslacion():
    u = sintetico.malla_u(399, 0.0025)
    x = np.sort(np.random.default_rng(0).normal(size=399))
    assert np.isclose(transporte.distancia_wasserstein(x + 0.3, x, u, rango=(0, 1), normalizar_rango=True), 0.3)
    xb = x * 1.5
    w1 = transporte.distancia_wasserstein(xb, x, u, p=1)
    w2 = transporte.distancia_wasserstein(xb, x, u, p=2)
    assert w1 <= w2 + 1e-12


def test_fpca_reconstruye_y_conserva_orden():
    datos = sintetico.panel_distribuciones(np.random.default_rng(3), n_dias=120, dia_choque=80, dia_evento=100)
    X = datos["mercado"]["latente"]
    fpca = transporte.ComponentesFuncionales(n_componentes=X.shape[1]).ajustar(X, datos["u"])
    assert np.allclose(fpca.reconstruir(fpca.transformar(X), asegurar_orden=False), X, atol=1e-8)
    fpca3 = transporte.ComponentesFuncionales(3).ajustar(X, datos["u"])
    assert transporte.es_monotona(fpca3.reconstruir(fpca3.transformar(X)))


# --- Filtrado y regímenes --------------------------------------------------------

def test_kalman_escalar_converge_a_ganancia_estacionaria():
    q, r = 0.1, 1.0
    _, _, _, K = filtrado.filtro_kalman(np.zeros(200), [[1.0]], [[1.0]], [[q]], r, [0.0], [[1.0]])
    p = (q + np.sqrt(q**2 + 4 * q * r)) / 2.0  # varianza de predicción estacionaria
    assert np.isclose(K[-1, 0, 0], p / (p + r), atol=1e-8)


def test_bocpd_detecta_cambio_de_varianza():
    rng = np.random.default_rng(1)
    x = np.concatenate([rng.normal(0, 1, 150), rng.normal(0, 3, 100)])
    R = regimenes.bocpd(x, riesgo=1 / 200)
    mapa, _ = regimenes.resumen_corrida(R)
    # Al final, la corrida más probable empezó cerca de la sesión 150.
    assert abs((len(x) - mapa[-1]) - 150) < 15


# --- Calibración -----------------------------------------------------------------

def test_crps_por_cuantiles_aproxima_forma_cerrada():
    taus = (np.arange(2000) + 0.5) / 2000
    from scipy.stats import norm
    y = np.array([-1.2, 0.0, 0.7])
    aprox = calibracion.crps_desde_cuantiles(y, norm.ppf(taus)[None, :].repeat(3, 0), taus)
    assert np.allclose(aprox, calibracion.crps_normal(y, 0.0, 1.0), atol=2e-3)


def test_conformal_adaptativo_cumple_cota_de_largo_plazo():
    rng = np.random.default_rng(2)
    n = 3000
    sigma = np.where(np.arange(n) < 1500, 1.0, 2.5)
    y = rng.normal(0, sigma)
    alfa, gamma = 0.1, 0.01
    _, _, errores, _ = calibracion.conformal_adaptativo(y, np.zeros(n), alfa=alfa, gamma=gamma)
    e = errores[np.isfinite(errores)]
    cota = (max(alfa, 1 - alfa) + gamma) / (gamma * len(e))
    assert abs(e.mean() - alfa) <= cota + 1e-12


# --- Decisión --------------------------------------------------------------------

def test_cvar_del_programa_lineal_coincide_con_el_empirico():
    rng = np.random.default_rng(4)
    R = rng.multivariate_normal([0.004, 0.002], [[0.0016, 0.0006], [0.0006, 0.0009]], size=2000)
    sol = decision.optimizar_cvar(R, np.array([0.3, 0.3]), lam=0.5, costos=0.0, w_max=0.8)
    _, cvar = decision.var_cvar(-(R @ sol["w"]), 0.95)
    assert np.isclose(sol["cvar"], cvar, rtol=1e-6, atol=1e-9)


def test_costos_altos_producen_no_operacion():
    rng = np.random.default_rng(5)
    R = rng.multivariate_normal([0.004, 0.002], [[0.0016, 0.0006], [0.0006, 0.0009]], size=1000)
    w0 = np.array([0.25, 0.35])
    sol = decision.optimizar_cvar(R, w0, lam=1.0, costos=0.5)
    assert np.allclose(sol["w"], w0, atol=1e-9)


# --- Evidencia -------------------------------------------------------------------

def test_maximo_sharpe_esperado_aproxima_montecarlo():
    rng = np.random.default_rng(6)
    n_obs, n_ensayos = 500, 50
    sr = rng.normal(size=(4000, n_ensayos, n_obs)).mean(axis=2) / 1.0
    maximos = sr.max(axis=1)
    aprox = evidencia.maximo_sharpe_esperado(n_ensayos, 1.0 / n_obs)
    assert abs(maximos.mean() - aprox) / aprox < 0.05


def test_walk_forward_purga_etiquetas_que_cruzan():
    h = 20
    for entrenamiento, prueba in evidencia.particiones_walk_forward(600, 300, 60, horizonte=h, embargo=5):
        assert entrenamiento.max() + h < prueba.min()


def test_opciones_americanas_y_europeas():
    europea = opciones.binomial_crr(100, 100, 0.25, 0.04, 0.2, es_call=True, americana=False, n=800)
    assert np.isclose(europea, float(opciones.precio_bs(100, 100, 0.25, 0.04, 0.0, 0.2, True)), atol=5e-3)
    assert opciones.prima_ejercicio_anticipado(100, 110, 0.25, 0.04, 0.2) > 0.0


def test_objetivo_homogeneo_lleva_a_extremos():
    """Con CVaR como penalización y sin costos, la solución salta de los límites a caja total."""
    rng = np.random.default_rng(8)
    S, nu = 1000, 5
    mu, sd = np.array([0.0020, 0.0012]), np.array([0.032, 0.022])
    L = np.linalg.cholesky(np.array([[1.0, 0.55], [0.55, 1.0]]))
    z = rng.standard_normal((S, 2)) @ L.T
    g = rng.chisquare(nu, size=(S, 1)) / nu
    R = mu + sd * z / np.sqrt(g) * np.sqrt((nu - 2) / nu)
    w_bajo = decision.optimizar_cvar(R, np.array([0.3, 0.3]), lam=0.01, costos=0.0, w_max=0.8)["w"]
    w_alto = decision.optimizar_cvar(R, np.array([0.3, 0.3]), lam=0.02, costos=0.0, w_max=0.8)["w"]
    assert np.isclose(w_bajo.sum(), 1.0) or np.any(np.isclose(w_bajo, 0.8))
    assert np.allclose(w_alto, 0.0, atol=1e-9)
