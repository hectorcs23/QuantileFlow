"""Figuras de las secciones 4 y 5: de Q a P, regímenes y confianza medible."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

from comun import guardar
from quantileflow import calibracion as cb
from quantileflow import distribuciones as ds
from quantileflow import pronostico as pr
from quantileflow import regimenes as rg
from quantileflow import superficies as sf


# ---------------------------------------------------------------------------
# Sección 4: Q no es P
# ---------------------------------------------------------------------------

def datos_q_p():
    tau = 30 / 365
    k = np.linspace(-0.7, 0.4, 4000)
    th_q = 0.19**2 * tau
    q = sf.densidad_logmoneyness(k, *sf.derivadas_ssvi(k, th_q, -0.70, sf.phi_potencia(th_q, 1.1, 0.45)))
    # Supuesto ilustrativo para P: menor dispersión, cola izquierda más delgada y media mayor.
    th_p = 0.155**2 * tau
    base = sf.densidad_logmoneyness(k, *sf.derivadas_ssvi(k, th_p, -0.45, sf.phi_potencia(th_p, 1.1, 0.45)))
    p = np.interp(k - np.log(1.005), k, base)
    p /= ds.trapecio(p, k)
    return k, q, p


def fig_q_vs_p():
    k, q, p = datos_q_p()
    media_q, media_p = ds.trapecio(np.exp(k) * q, k), ds.trapecio(np.exp(k) * p, k)
    cola_q = ds.trapecio(q[k < -0.10], k[k < -0.10]) * 100
    cola_p = ds.trapecio(p[k < -0.10], k[k < -0.10]) * 100
    plt.figure()
    plt.plot(k * 100, q, label=f"Q (measured): E[S_T]/F = {media_q:.3f}, P(x < -10%) = {cola_q:.1f}%")
    plt.plot(k * 100, p, label=f"P (assumed here): E[S_T]/F = {media_p:.3f}, P(x < -10%) = {cola_p:.1f}%")
    plt.xlim(-40, 20)
    plt.xlabel("x = ln(S_T / F) at 30 days (%)")
    plt.ylabel("Density of x")
    plt.title("Two different distributions of the same asset (illustrative)")
    plt.legend()
    return guardar("s4_q_vs_p")


def fig_nucleo():
    k, q, p = datos_q_p()
    cuerpo = (q > 1e-3) & (p > 1e-3)
    plt.figure()
    plt.semilogy(k[cuerpo] * 100, (q / p)[cuerpo], label="q(x) / p(x) implied by the assumption")
    plt.semilogy([-40, 20], [1, 1], "k--", label="Ratio = 1")
    plt.xlim(-40, 20)
    plt.xlabel("x = ln(S_T / F) at 30 days (%)")
    plt.ylabel("q(x) / p(x), log scale")
    plt.title("Projected pricing kernel: not identified without assumptions")
    plt.legend()
    return guardar("s4_nucleo")


def fig_pinball():
    e = np.linspace(-1, 1, 201)
    plt.figure()
    for t in (0.05, 0.50, 0.95):
        plt.plot(e, cb.perdida_pinball(e, 0.0, t), label=f"tau = {t:.2f}")
    plt.xlabel("Error e = y - q")
    plt.ylabel("Pinball loss rho_tau(e)")
    plt.title("Quantile (pinball) loss")
    plt.legend()
    return guardar("s4_pinball")


def datos_cruces():
    rng = np.random.default_rng(12)
    n = 70
    z = rng.uniform(0.10, 0.30, n)
    y = (0.002 + z * np.sqrt(5 / 252) * rng.standard_t(6, n) * np.sqrt(4 / 6)) * 100
    taus = [0.05, 0.25, 0.50, 0.75, 0.95]
    X = np.column_stack([np.ones(n), z])
    coef = np.array([pr.regresion_cuantilica(X, y, t) for t in taus])
    zz = np.linspace(0.0, 0.42, 300)
    Xz = np.column_stack([np.ones_like(zz), zz])
    return z, y, taus, zz, pr.predecir_cuantiles(Xz, coef, False), pr.predecir_cuantiles(Xz, coef, True)


def _fig_cuantiles(nombre, titulo, reordenado):
    z, y, taus, zz, crudo, ordenado = datos_cruces()
    curvas = ordenado if reordenado else crudo
    plt.figure()
    plt.plot(z, y, ".", label="Training data (feature range 0.10-0.30)")
    for j, t in enumerate(taus):
        plt.plot(zz, curvas[:, j], label=f"tau = {t:.2f}")
    cruce = np.where(np.any(np.diff(crudo, axis=1) < 0, axis=1))[0]
    if not reordenado and len(cruce):
        i = cruce[len(cruce) // 2]
        plt.plot(zz[i], crudo[i, 1], "ro", label="Crossing: 25% quantile below the 5% one")
    plt.xlabel("Q-derived feature (e.g., 30-day implied volatility)")
    plt.ylabel("Return over the next 5 sessions (%)")
    plt.title(titulo)
    plt.legend()
    return guardar(nombre)


def fig_cruces():
    return _fig_cuantiles("s4_cruces", "Separately estimated quantile regressions (synthetic)", False)


def fig_reordenado():
    return _fig_cuantiles("s4_reordenado", "The same quantiles after rearrangement (synthetic)", True)


# ---------------------------------------------------------------------------
# Sección 5: BOCPD frente a umbral
# ---------------------------------------------------------------------------

def datos_bocpd():
    rng = np.random.default_rng(14)
    n, cambio = 260, 160
    z = np.concatenate([rng.normal(0, 1, cambio), rng.normal(0.3, 2.2, n - cambio)])
    R = rg.bocpd(z, riesgo=1 / 120)
    mapa, corta = rg.resumen_corrida(R)
    return z, R, mapa, corta, rg.detector_umbral(z, umbral=2.5, ventana=5, minimo=2), cambio


def fig_umbral(d):
    z, _, _, _, alarma, cambio = d
    t = np.arange(1, len(z) + 1)
    plt.figure()
    plt.plot(t, z, ".", label="Standardized forecast error")
    plt.plot([1, len(z)], [2.5, 2.5], "k--", label="Threshold |z| = 2.5")
    plt.plot([1, len(z)], [-2.5, -2.5], "k--")
    plt.plot(t[alarma], np.full(alarma.sum(), 7.0), "ro", label="Alarm: 2 of the last 5 beyond the threshold")
    plt.xlabel(f"Session (true change at {cambio})")
    plt.ylabel("Standardized error")
    plt.title("Forecast errors and a simple threshold detector (synthetic)")
    plt.legend()
    return guardar("s5_umbral")


def fig_corrida(d):
    z, R, mapa, _, _, cambio = d
    n = len(z)
    plt.figure()
    plt.imshow(np.log10(np.maximum(R[1:, :n], 1e-8)).T, aspect="auto", origin="lower",
               extent=[0.5, n + 0.5, -0.5, n - 0.5])
    plt.colorbar(label="log10 posterior probability")
    plt.plot(np.arange(1, n + 1), mapa[1:], label="Most probable run length")
    plt.ylim(0, 200)
    plt.xlabel(f"Session (true change at {cambio})")
    plt.ylabel("Run length r_t (sessions since last change)")
    plt.title("BOCPD run-length posterior (synthetic)")
    plt.legend()
    return guardar("s5_corrida")


def fig_cambio_reciente(d):
    z, _, _, corta, _, cambio = d
    t = np.arange(1, len(z) + 1)
    serie = corta[1:].copy()
    serie[:10] = np.nan  # en el arranque toda corrida es corta por construcción
    plt.figure()
    plt.plot(t, serie, label="P(r_t < 10 | data)")
    plt.plot(cambio + 1, np.nanmax(serie), "ro", label="Maximum after the true change")
    plt.xlabel("Session")
    plt.ylabel("Probability of a recent change")
    plt.title("A change probability is not a probability of a price fall")
    plt.legend()
    return guardar("s5_cambio_reciente")


# ---------------------------------------------------------------------------
# Calibración: diagrama de fiabilidad y PIT
# ---------------------------------------------------------------------------

def fig_fiabilidad():
    rng = np.random.default_rng(15)
    n = 1500
    p_real = rng.beta(2.2, 3.0, n)
    o = rng.uniform(size=n) < p_real
    logit = np.log(p_real / (1 - p_real))
    p_cal = 1 / (1 + np.exp(-(logit + rng.normal(0, 0.25, n))))
    p_conf = 1 / (1 + np.exp(-(2.2 * logit + rng.normal(0, 0.25, n))))
    plt.figure()
    for pr_, nombre in [(p_cal, "Calibrated"), (p_conf, "Overconfident")]:
        mp, fr, _ = cb.curva_fiabilidad(pr_, o, 10)
        plt.plot(mp, fr, "o-", label=f"{nombre} (Brier = {cb.brier(pr_, o):.3f})")
    plt.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    plt.xlabel("Forecast probability")
    plt.ylabel("Observed frequency")
    plt.title("Reliability diagram for an event forecast (synthetic)")
    plt.legend()
    return guardar("s5_fiabilidad")


def fig_pit():
    rng = np.random.default_rng(16)
    y = rng.normal(size=4000)
    plt.figure()
    for nombre, escala in [("Calibrated", 1.0), ("Overconfident (intervals too narrow)", 0.6),
                           ("Underconfident (intervals too wide)", 1.6)]:
        plt.hist(norm.cdf(y / escala), bins=10, range=(0, 1), density=True, histtype="step", label=nombre)
    plt.xlabel("PIT value F(y)")
    plt.ylabel("Density (uniform = 1 if calibrated)")
    plt.title("PIT histograms of distribution forecasts (synthetic)")
    plt.legend()
    return guardar("s5_pit")


# ---------------------------------------------------------------------------
# Conformal adaptativo con desplazamiento de distribución
# ---------------------------------------------------------------------------

def datos_conformal():
    rng = np.random.default_rng(16)
    n = 1000
    sigma = np.where(np.arange(n) < 500, 1.0, 2.0)
    sigma[750:] = 1.4
    y = rng.standard_t(5, n) * np.sqrt(3 / 5) * sigma
    pred = np.zeros(n)
    fijo = cb.conformal_adaptativo(y, pred, alfa=0.10, gamma=0.0, ventana=250)
    adaptativo = cb.conformal_adaptativo(y, pred, alfa=0.10, gamma=0.01, ventana=250)
    return y, fijo, adaptativo


def _movil(e, v=50):
    salida = np.full(len(e), np.nan)
    for i in range(v, len(e)):
        seg = e[i - v:i]
        seg = seg[np.isfinite(seg)]
        if len(seg) > v // 2:
            salida[i] = 1 - seg.mean()
    return salida


def fig_conformal_intervalos(d):
    y, fijo, adapt = d
    t = np.arange(len(y))
    plt.figure()
    plt.plot(t, y, ".", label="Realized value")
    plt.plot(np.concatenate([t, [np.nan], t]), np.concatenate([fijo[0], [np.nan], fijo[1]]),
             label="Fixed-level conformal (window 250)")
    plt.plot(np.concatenate([t, [np.nan], t]), np.concatenate([adapt[0], [np.nan], adapt[1]]),
             label="Adaptive conformal (gamma = 0.01)")
    plt.xlabel("Session (volatility doubles at 500, falls to 1.4x at 750)")
    plt.ylabel("Value (arbitrary units)")
    plt.title("90% intervals under a distribution shift (synthetic)")
    plt.legend()
    return guardar("s5_conformal_intervalos")


def fig_conformal_cobertura(d):
    y, fijo, adapt = d
    t = np.arange(len(y))
    plt.figure()
    plt.plot(t, _movil(fijo[2]), label=f"Fixed level (long-run {100 * (1 - np.nanmean(fijo[2])):.1f}%)")
    plt.plot(t, _movil(adapt[2]), label=f"Adaptive (long-run {100 * (1 - np.nanmean(adapt[2])):.1f}%)")
    plt.plot([0, len(y)], [0.9, 0.9], "k--", label="Nominal 90%")
    plt.xlabel("Session")
    plt.ylabel("Coverage over the last 50 sessions")
    plt.title("Long-run coverage can hide local failures (synthetic)")
    plt.legend()
    return guardar("s5_conformal_cobertura")


def fig_conformal_alfa(d):
    y, _, adapt = d
    t = np.arange(len(y))
    plt.figure()
    plt.plot(t, adapt[3], label="alpha_t (adaptive)")
    plt.plot([0, len(y)], [0.1, 0.1], "k--", label="Target alpha = 0.10")
    plt.xlabel("Session")
    plt.ylabel("Effective miscoverage level alpha_t")
    plt.title("ACI update: alpha_(t+1) = alpha_t + gamma (alpha - err_t)")
    plt.legend()
    return guardar("s5_conformal_alfa")


def main():
    rutas = [fig_q_vs_p(), fig_nucleo(), fig_pinball(), fig_cruces(), fig_reordenado()]
    b = datos_bocpd()
    rutas += [fig_umbral(b), fig_corrida(b), fig_cambio_reciente(b), fig_fiabilidad(), fig_pit()]
    c = datos_conformal()
    rutas += [fig_conformal_intervalos(c), fig_conformal_cobertura(c), fig_conformal_alfa(c)]
    return rutas


if __name__ == "__main__":
    for r in main():
        print(r)
