"""Figuras de las secciones 6, 7 y 9: decisión, riesgo conjunto, evidencia y calendario."""
from __future__ import annotations

import contourpy
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm, t as t_student

from comun import guardar
from quantileflow import decision as dc
from quantileflow import evidencia as ev
from quantileflow import opciones as op


def _t_copula(rng, n, correlacion, nu):
    C = np.array([[1.0, correlacion], [correlacion, 1.0]])
    z = rng.standard_normal((n, 2)) @ np.linalg.cholesky(C).T
    w = rng.chisquare(nu, size=(n, 1)) / nu
    return norm.ppf(t_student.cdf(z / np.sqrt(w), nu))


# ---------------------------------------------------------------------------
# Dependencia: gaussiana frente a t y calma frente a crisis
# ---------------------------------------------------------------------------

def _fig_copula(nombre, titulo, datos):
    q = norm.ppf(0.025)
    conjunta = (datos[:, 0] < q) & (datos[:, 1] < q)
    plt.figure()
    plt.plot(datos[~conjunta, 0], datos[~conjunta, 1], ".", label="Scenarios")
    plt.plot(datos[conjunta, 0], datos[conjunta, 1], "ro",
             label=f"Both below their 2.5% quantile: {conjunta.mean() * 100:.2f}%")
    plt.xlabel("Asset 1 (standardized)")
    plt.ylabel("Asset 2 (standardized)")
    plt.title(titulo)
    plt.legend()
    return guardar(nombre)


def fig_copulas():
    rng = np.random.default_rng(31)
    n = 4000
    C = np.array([[1.0, 0.5], [0.5, 1.0]])
    gauss = rng.standard_normal((n, 2)) @ np.linalg.cholesky(C).T
    tcop = _t_copula(rng, n, 0.5, 3)
    return [_fig_copula("s6_copula_gauss", "Gaussian copula, correlation 0.5 (synthetic)", gauss),
            _fig_copula("s6_copula_t", "t copula (3 d.o.f.), correlation 0.5 (synthetic)", tcop)]


def fig_calma_crisis():
    rng = np.random.default_rng(33)
    calma = rng.multivariate_normal([0, 0], [[1, 0.3], [0.3, 1]], 1800)
    crisis = rng.multivariate_normal([0, 0], [[6.25, 0.85 * 6.25], [0.85 * 6.25, 6.25]], 200)
    plt.figure()
    plt.plot(calma[:, 0], calma[:, 1], ".", label="Calm regime: correlation 0.30")
    plt.plot(crisis[:, 0], crisis[:, 1], ".", label="Crisis regime: correlation 0.85, volatility x2.5")
    plt.xlabel("Asset 1 return (units of calm volatility)")
    plt.ylabel("Asset 2 return (units of calm volatility)")
    plt.title("Dependence changes with the regime (synthetic)")
    plt.legend()
    return guardar("s6_calma_crisis")


# ---------------------------------------------------------------------------
# CVaR de la cartera y suma de riesgos individuales
# ---------------------------------------------------------------------------

PESOS = np.array([0.40, 0.20, 0.20, 0.15])


def _escenarios_cartera(rng, n, vol_factor=1.0, beta_extra=0.0):
    betas = np.array([1.0, 1.15, 0.9, 1.3]) + beta_extra
    vol_m = 0.022 * vol_factor
    idio = np.array([0.004, 0.022, 0.018, 0.028])
    f = t_student.rvs(4, size=n, random_state=rng) * np.sqrt(2 / 4) * vol_m
    e = t_student.rvs(5, size=(n, 4), random_state=rng) * np.sqrt(3 / 5) * idio
    return 0.001 + f[:, None] * betas + e


def fig_perdidas():
    rng = np.random.default_rng(32)
    perdidas = -(_escenarios_cartera(rng, 20000) @ PESOS) * 100
    var95, cvar95 = dc.var_cvar(perdidas, 0.95)
    bins = np.linspace(-8, 12, 121)
    plt.figure()
    plt.hist(perdidas[perdidas < var95], bins=bins, label="Scenario losses")
    plt.hist(perdidas[perdidas >= var95], bins=bins, label="Worst 5% of scenarios")
    alto = plt.ylim()[1]
    plt.plot([var95, var95], [0, alto], label=f"VaR 95% = {var95:.2f}%")
    plt.plot([cvar95, cvar95], [0, alto], label=f"CVaR 95% = {cvar95:.2f}% (average of the tail)")
    plt.xlabel("Portfolio loss over 5 sessions (%)")
    plt.ylabel("Number of scenarios")
    plt.title("Simulated loss distribution: CVaR is not a loss limit (synthetic)")
    plt.legend()
    return guardar("s6_perdidas")


def fig_suma_riesgos():
    rng = np.random.default_rng(34)
    grupos = {"Calm": _escenarios_cartera(rng, 20000), "Stress (vol x2, beta +0.2)":
              _escenarios_cartera(rng, 20000, 2.0, 0.2)}
    suma, cartera = [], []
    for Rg in grupos.values():
        suma.append(sum(PESOS[j] * dc.var_cvar(-Rg[:, j], 0.95)[1] for j in range(4)) * 100)
        cartera.append(dc.var_cvar(-(Rg @ PESOS), 0.95)[1] * 100)
    x = np.arange(2)
    plt.figure()
    plt.bar(x - 0.2, suma, 0.4, label="Weighted sum of individual CVaRs")
    plt.bar(x + 0.2, cartera, 0.4, label="CVaR of the portfolio")
    plt.xticks(x, list(grupos.keys()))
    plt.xlabel("Scenario set")
    plt.ylabel("CVaR 95% over 5 sessions (%)")
    plt.title("Joint risk is not the sum of individual risks (synthetic)")
    plt.legend()
    return guardar("s6_suma_riesgos")


# ---------------------------------------------------------------------------
# Estabilidad de la decisión y zona de no operación
# ---------------------------------------------------------------------------

def datos_estabilidad():
    rng = np.random.default_rng(8)
    S, presupuesto = 1000, 0.03
    mu, sd = np.array([0.0020, 0.0012]), np.array([0.032, 0.022])
    z = _t_copula(rng, S, 0.55, 5)
    R = mu + sd * (z - z.mean(axis=0))  # escenarios centrados: la media muestral es exactamente mu
    w_opt = dc.optimizar_cvar(R, np.zeros(2), lam=0.0, costos=0.0, cvar_max=presupuesto, w_max=0.8)["w"]
    mu_hat = R.mean(axis=0)
    boot, valores = [], []
    for _ in range(300):
        # Incertidumbre supuesta: escenarios remuestreados para la cola y rendimiento
        # esperado con desviación estándar del 30% de su valor.
        Rb = R[rng.integers(0, S, S)]
        mub = mu_hat * (1.0 + 0.3 * rng.standard_normal(2))
        boot.append(dc.optimizar_cvar(Rb, np.zeros(2), lam=0.0, costos=0.0, cvar_max=presupuesto, w_max=0.8,
                                      mu=mub)["w"])
        valores.append(mub @ w_opt)
    malla = np.linspace(0, 0.8, 121)
    WA, WB = np.meshgrid(malla, malla)
    cvar = np.empty_like(WA)
    for i in range(WA.shape[0]):
        perd = -(R[:, [0]] * WA[i][None, :] + R[:, [1]] * WB[i][None, :])
        zeta = np.quantile(perd, 0.95, axis=0, method="higher")
        cvar[i] = zeta + np.mean(np.maximum(perd - zeta, 0.0), axis=0) / 0.05
    factible = (cvar <= presupuesto) & (WA + WB <= 1.0)
    # Región casi óptima: factible y con rendimiento esperado a menos de una
    # desviación estándar bootstrap del valor del óptimo puntual.
    casi = factible & (mu_hat[0] * WA + mu_hat[1] * WB >= mu_hat @ w_opt - np.std(valores))
    return dict(WA=WA, WB=WB, cvar=cvar, casi=casi, boot=np.array(boot), w_opt=w_opt, presupuesto=presupuesto)


def _contorno(d, campo, nivel):
    """Todas las líneas de nivel como una sola serie separada por NaN."""
    lineas = contourpy.contour_generator(d["WA"], d["WB"], campo).lines(nivel)
    return np.vstack([np.vstack([ln, [np.nan, np.nan]]) for ln in lineas])


def fig_region_estable(d):
    frontera = _contorno(d, d["cvar"], d["presupuesto"])
    region = _contorno(d, d["casi"].astype(float), 0.5)
    actual = np.array([0.25, 0.25])
    excedida = np.array([0.52, 0.34])
    cand = np.column_stack([d["WA"][d["casi"]], d["WB"][d["casi"]]])
    destino = cand[np.argmin(np.abs(cand - excedida).sum(axis=1))]
    plt.figure()
    plt.plot(d["boot"][:, 0], d["boot"][:, 1], ".", label="Optimal weights, 300 bootstrap resamples")
    plt.plot(frontera[:, 0], frontera[:, 1], label="Risk budget: CVaR 95% = 3%")
    plt.plot(region[:, 0], region[:, 1], "--", label="Boundary of the near-optimal region")
    plt.plot(d["w_opt"][0], d["w_opt"][1], "ro", label="Point estimate of the optimum")
    plt.plot(actual[0], actual[1], "gs", label="Current portfolio inside the region: hold")
    plt.plot([excedida[0], destino[0]], [excedida[1], destino[1]], "o-",
             label="Portfolio above budget: trade only to the region")
    plt.xlim(0, 0.8)
    plt.ylim(0, 0.8)
    plt.xlabel("Weight in asset A")
    plt.ylabel("Weight in asset B")
    plt.title("Near-optimal region vs point optimum (synthetic)")
    plt.legend()
    return guardar("s6_region_estable")


def fig_histograma_pesos(d):
    pesos = d["boot"][:, 0] * 100
    lo, hi = np.percentile(pesos, [10, 90])
    plt.figure()
    plt.hist(pesos, bins=np.linspace(0, 60, 31), label="Bootstrap optimal weight of A")
    alto = plt.ylim()[1]
    plt.plot([d["w_opt"][0] * 100] * 2, [0, alto], label=f"Point estimate: {d['w_opt'][0] * 100:.1f}%")
    plt.plot([lo, lo, np.nan, hi, hi], [0, alto, np.nan, 0, alto], "--",
             label=f"10th-90th percentile: {lo:.0f}% to {hi:.0f}%")
    plt.xlabel("Optimal weight in asset A (%)")
    plt.ylabel("Number of resamples")
    plt.title("A precise-looking weight hides a wide range (synthetic)")
    plt.legend()
    return guardar("s6_histograma_pesos")


# ---------------------------------------------------------------------------
# Rama de opciones: revaluación completa frente a aproximaciones
# ---------------------------------------------------------------------------

def _fig_opcion(nombre, titulo, pendiente_vol):
    S0, K, T, r, q, sig = 100.0, 100.0, 30 / 365, 0.04, 0.013, 0.20
    dt = 1 / 365
    mov = np.linspace(-0.25, 0.25, 201)
    S1 = S0 * (1 + mov)
    dvol = pendiente_vol * mov
    p0 = float(op.precio_bs(S0, K, T, r, q, sig, True))
    delta, gamma, vega = (float(x) for x in op.griegas_bs(S0, K, T, r, q, sig, True))
    theta_dia = float(op.precio_bs(S0, K, T - dt, r, q, sig, True)) - p0
    dS = S1 - S0
    completo = op.precio_bs(S1, K, T - dt, r, q, np.maximum(sig + dvol, 0.02), True) - p0
    plt.figure()
    plt.plot(mov * 100, completo, label="Full revaluation")
    plt.plot(mov * 100, theta_dia + delta * dS, label="Delta")
    plt.plot(mov * 100, theta_dia + delta * dS + 0.5 * gamma * dS**2, label="Delta-gamma")
    if pendiente_vol:
        plt.plot(mov * 100, theta_dia + delta * dS + 0.5 * gamma * dS**2 + vega * dvol, label="Delta-gamma-vega")
    plt.xlabel("One-day move of the underlying (%)")
    plt.ylabel("P&L of one ATM 30-day call")
    plt.title(titulo)
    plt.legend()
    return guardar(nombre)


def fig_opciones():
    return [_fig_opcion("s6_opcion_spot", "Greek approximations vs full revaluation: spot only", 0.0),
            _fig_opcion("s6_opcion_vol", "Same call when volatility rises as the price falls", -0.8)]


# ---------------------------------------------------------------------------
# Sección 7: sesgo de selección, bootstrap por bloques y tamaño efectivo
# ---------------------------------------------------------------------------

def _n_ensayos():
    return np.unique(np.round(np.logspace(0.3, 3, 40)).astype(int))


def fig_maximo_sharpe():
    rng = np.random.default_rng(41)
    n = _n_ensayos()
    plt.figure()
    for anios in (1, 2, 4):
        plt.semilogx(n, ev.maximo_sharpe_esperado(n, 1.0 / (252 * anios)) * np.sqrt(252),
                     label=f"{anios} year{'s' if anios > 1 else ''} of daily data")
    marcas = [5, 20, 100, 500]
    mc = [(rng.standard_normal((2000, N)) / np.sqrt(504)).max(axis=1).mean() * np.sqrt(252) for N in marcas]
    plt.semilogx(marcas, mc, "ro", label="Monte Carlo check (2 years)")
    plt.xlabel("Number of variants tried N")
    plt.ylabel("Expected maximum annual Sharpe ratio")
    plt.title("Best of N strategies with no true edge")
    plt.legend()
    return guardar("s7_maximo_sharpe")


def fig_sharpe_deflactado():
    n = _n_ensayos()
    T = 504
    plt.figure()
    for sr_anual in (1.0, 1.5, 2.0):
        plt.semilogx(n, ev.sharpe_deflactado(sr_anual / np.sqrt(252), T, n, 1.0 / T, asimetria=-0.5, curtosis=6.0),
                     label=f"Observed annual Sharpe {sr_anual:.1f}")
    plt.semilogx([n[0], n[-1]], [0.95, 0.95], "k--", label="0.95")
    plt.xlabel("Number of variants tried N (2 years daily, skew -0.5, kurtosis 6)")
    plt.ylabel("Deflated Sharpe ratio (probability)")
    plt.title("The same result is worth less after more trials")
    plt.legend()
    return guardar("s7_sharpe_deflactado")


def _serie_diferencias(rng, media, n=500):
    e = rng.standard_t(5, n) * 0.08
    x = np.empty(n)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = 0.35 * x[i - 1] + e[i]
    return x - x.mean() + media


def _fig_bootstrap(nombre, titulo, media, semilla):
    rng = np.random.default_rng(semilla)
    medias = ev.bootstrap_bloques(_serie_diferencias(rng, media), largo_bloque=20, n_rep=4000, rng=rng)
    lo, hi = np.percentile(medias, [5, 95])
    plt.figure()
    plt.hist(medias, bins=60, label="Block-bootstrap means (block length 20)")
    alto = plt.ylim()[1]
    plt.plot([lo, lo, np.nan, hi, hi], [0, alto, np.nan, 0, alto], "--",
             label=f"90% interval: [{lo:.3f}, {hi:.3f}]")
    plt.plot([0, 0], [0, alto], "k-", label="No improvement")
    plt.xlim(-0.03, 0.05)
    plt.xlabel("Mean loss improvement of model D over model C")
    plt.ylabel("Number of resamples")
    plt.title(titulo)
    plt.legend()
    return guardar(nombre)


def fig_bootstrap():
    return [_fig_bootstrap("s7_bootstrap_distinguible", "Improvement distinguishable from zero (synthetic)",
                           0.022, 42),
            _fig_bootstrap("s7_bootstrap_insuficiente", "Insufficient evidence: interval contains zero (synthetic)",
                           0.006, 43)]


def fig_obs_efectivas():
    horizontes = np.array([1, 5, 20])
    plt.figure()
    plt.bar([f"{h} session{'s' if h > 1 else ''}" for h in horizontes], ev.n_efectivo_solapado(500, horizontes))
    plt.xlabel("Forecast horizon with overlapping labels")
    plt.ylabel("Effective number of observations out of 500 sessions")
    plt.title("Overlapping labels shrink the effective sample")
    return guardar("s7_obs_efectivas")


def fig_activos_efectivos():
    rho = np.linspace(0, 0.95, 100)
    plt.figure()
    for n_act in (5, 20):
        plt.plot(rho, ev.n_efectivo_activos(n_act, rho), label=f"{n_act} assets")
    plt.xlabel("Average correlation between assets")
    plt.ylabel("Equivalent number of independent assets")
    plt.title("Several correlated stocks are not several samples")
    plt.legend()
    return guardar("s7_activos_efectivos")


# ---------------------------------------------------------------------------
# Sección 9: calendario tentativo de construcción
# ---------------------------------------------------------------------------

def fig_calendario():
    etapas = ["Data", "Distrib.", "Dynamics", "Forecast", "Decision", "Paper"]
    inicio = np.array([0.0, 1.0, 2.5, 3.5, 5.0, 6.0])
    minimo = np.array([1.5, 2.0, 1.5, 2.0, 1.5, 1.0])
    maximo = np.array([2.5, 3.0, 2.5, 3.0, 2.0, 1.5])
    x = np.arange(len(etapas))
    plt.figure()
    plt.bar(x, minimo, bottom=inicio, label="Base duration (illustrative split)")
    plt.bar(x, maximo - minimo, bottom=inicio + minimo, label="Possible overrun")
    plt.plot([-0.5, len(etapas) - 0.5], [6, 6], "k--", label="Integrated prototype: 6 to 10 weeks")
    plt.plot([-0.5, len(etapas) - 0.5], [10, 10], "k--")
    plt.xticks(x, etapas)
    plt.xlabel("Stage (engineering only; excludes prospective evaluation)")
    plt.ylabel("Weeks from start")
    plt.title("Tentative build sequence, to be revised after the data audit")
    plt.legend()
    return guardar("s9_calendario")


def main():
    rutas = fig_copulas() + [fig_calma_crisis(), fig_perdidas(), fig_suma_riesgos()]
    d = datos_estabilidad()
    rutas += [fig_region_estable(d), fig_histograma_pesos(d)] + fig_opciones()
    rutas += [fig_maximo_sharpe(), fig_sharpe_deflactado()] + fig_bootstrap()
    rutas += [fig_obs_efectivas(), fig_activos_efectivos(), fig_calendario()]
    return rutas


if __name__ == "__main__":
    for r in main():
        print(r)
