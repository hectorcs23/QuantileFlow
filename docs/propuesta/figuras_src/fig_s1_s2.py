"""Figuras de las secciones 1 y 2: horizontes, datos y reconstrucción de Q."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from comun import guardar, segmentos
from quantileflow import distribuciones as ds
from quantileflow import opciones as op
from quantileflow import sintetico as sn
from quantileflow import superficies as sf


# ---------------------------------------------------------------------------
# Sección 1: una distribución a 30 días no se escala a una sesión
# ---------------------------------------------------------------------------

def _acumulacion_varianza():
    v = 0.25**2 / 252  # varianza de una sesión normal
    dias = np.arange(1, 31)
    habil = (dias - 1) % 7 < 5  # el día 1 es lunes
    salto = 0.05**2  # movimiento típico de resultados trimestrales
    incremento = np.where(habil, v, 0.1 * v) + np.where(dias == 10, salto, 0.0)
    W = np.concatenate([[0.0], np.cumsum(incremento)])
    return v, salto, W, int(habil.sum())


def fig_acumulacion_varianza():
    _, _, W, _ = _acumulacion_varianza()
    plt.figure()
    plt.step(np.arange(31), W * 1e4, where="post", label="Assumed accrual (weekends + earnings day)")
    plt.plot([0, 30], [0, W[-1] * 1e4], "--", label="Linear scaling in calendar days")
    plt.xlabel("Calendar days after the decision")
    plt.ylabel("Cumulative total variance (x 1e-4)")
    plt.title("Variance does not accrue uniformly (synthetic data)")
    plt.legend()
    return guardar("s1_acumulacion_varianza")


def fig_riesgo_sesion():
    v, salto, W, n_sesiones = _acumulacion_varianza()
    etiquetas = ["Normal", "Earnings", "Scaled 1/30", f"Scaled 1/{n_sesiones}"]
    valores = np.sqrt([v, v + salto, W[-1] / 30, W[-1] / n_sesiones]) * 100
    plt.figure()
    plt.bar(etiquetas, valores)
    plt.xlabel("Session (true value) or naive scaling of the 30-day variance")
    plt.ylabel("Standard deviation of one session (%)")
    plt.title("One-session risk: true vs naive scaling (synthetic data)")
    return guardar("s1_riesgo_sesion")


# ---------------------------------------------------------------------------
# Sección 2: cotizaciones, ajuste en precios y pérdida por banda
# ---------------------------------------------------------------------------

def datos_cadena():
    rng = np.random.default_rng(7)
    rebanadas, extras = sn.cadena_sintetica(rng)
    superficie = sf.ajustar_superficie(rebanadas)
    return rebanadas, extras, superficie


def fig_cotizaciones_precio(rebanadas, extras, superficie):
    reb, fiable = rebanadas[1], extras[1]["fiable"]
    m = reb.K / reb.F
    K = np.linspace(reb.K.min(), reb.K.max(), 600)
    precio = op.precio_black(reb.F, K, superficie.w(np.log(K / reb.F), reb.T), reb.D, K >= reb.F)
    plt.figure()
    plt.plot(*segmentos(m[fiable], reb.bid[fiable], reb.ask[fiable]), label="Bid-ask interval")
    plt.plot(m[~fiable], reb.ask[~fiable], "v", label="Zero bid (ask is only an upper bound)")
    plt.plot(K / reb.F, precio, label="SSVI fit in price space")
    plt.yscale("log")
    plt.xlabel("Strike / forward (puts below 1, calls above 1)")
    plt.ylabel("OTM option price")
    plt.title("30-day OTM quotes (synthetic data)")
    plt.legend()
    return guardar("s2_cotizaciones_precio")


def fig_cotizaciones_vol(rebanadas, superficie):
    reb = rebanadas[1]
    verdadera = sn.superficie_referencia()
    m = reb.K / reb.F
    iv_bid = op.vol_implicita_black(reb.bid, reb.F, reb.K, reb.T, reb.D, reb.es_call)
    iv_ask = op.vol_implicita_black(reb.ask, reb.F, reb.K, reb.T, reb.D, reb.es_call)
    ok = np.isfinite(iv_bid) & np.isfinite(iv_ask)
    solo_ask = ~np.isfinite(iv_bid) & np.isfinite(iv_ask)
    K = np.linspace(reb.K.min(), reb.K.max(), 600)
    k = np.log(K / reb.F)
    plt.figure()
    plt.plot(*segmentos(m[ok], iv_bid[ok] * 100, iv_ask[ok] * 100), label="Bid-ask interval")
    plt.plot(m[solo_ask], iv_ask[solo_ask] * 100, "v", label="Zero bid (upper bound only)")
    plt.plot(K / reb.F, np.sqrt(superficie.w(k, reb.T) / reb.T) * 100, label="SSVI fit")
    plt.plot(K / reb.F, np.sqrt(verdadera.w(k, reb.T) / reb.T) * 100, "--", label="True smile (unknown)")
    plt.xlabel("Strike / forward")
    plt.ylabel("Implied volatility (%)")
    plt.title("The same chain in implied volatility (synthetic data)")
    plt.legend()
    return guardar("s2_cotizaciones_vol")


def fig_perdida_banda():
    bid, ask = 1.00, 1.20
    s, mid = (ask - bid) / 2, (bid + ask) / 2
    p = np.linspace(0.8, 1.4, 400)
    banda = ((np.maximum(bid - p, 0) + np.maximum(p - ask, 0)) / s) ** 2 + 0.02 * ((p - mid) / s) ** 2
    plt.figure()
    plt.plot(p, ((p - mid) / s) ** 2, label="Squared distance to the midpoint")
    plt.plot(p, banda, label="Distance to [bid, ask] + small midpoint term")
    plt.plot([bid, ask], [0, 0], "ro", label="Bid and ask")
    plt.ylim(-0.3, 8)
    plt.xlabel("Model price")
    plt.ylabel("Loss (squared half-spreads)")
    plt.title("Per-quote loss: midpoint vs bid-ask band")
    plt.legend()
    return guardar("s2_perdida_banda")


# ---------------------------------------------------------------------------
# SSVI y arbitraje estático
# ---------------------------------------------------------------------------

def fig_ssvi_rebanadas(superficie):
    k = np.linspace(-0.45, 0.3, 400)
    plt.figure()
    for T in superficie.tiempos:
        plt.plot(k, superficie.w(k, T) * 100, label=f"T = {T * 365:.0f} days")
    plt.xlabel("Log-moneyness k = ln(K/F)")
    plt.ylabel("Total implied variance w(k, T) (x 1e-2)")
    plt.title("Fitted SSVI slices do not cross (synthetic data)")
    plt.legend()
    return guardar("s2_ssvi_rebanadas")


def fig_ssvi_region(superficie):
    verdadera = sn.superficie_referencia()
    r = np.linspace(0, 1, 200)
    plt.figure()
    plt.fill_between(r, 0, 2 / (1 + r), label=r"Sufficient region: $\eta(1+|\rho|)\leq 2$, $\gamma\leq 1/2$")
    plt.plot(abs(verdadera.rho), verdadera.eta, "gs", label="True parameters")
    plt.plot(abs(superficie.rho), superficie.eta, "ro", label="Fitted parameters")
    plt.xlim(0, 1)
    plt.ylim(0, 2.3)
    plt.xlabel(r"$|\rho|$")
    plt.ylabel(r"$\eta$")
    plt.title("SSVI power-law parameters without static arbitrage")
    plt.legend()
    return guardar("s2_ssvi_region")


def fig_funcion_g():
    k = np.linspace(-1.0, 1.6, 800)
    g_svi = sf.funcion_g(*sf.derivadas_svi_cruda(k, -0.0410, 0.1331, 0.3060, 0.3586, 0.4153), k)
    g_ssvi = sf.funcion_g(*sf.derivadas_ssvi(k, 0.1, -0.35, sf.phi_potencia(0.1, 1.2, 0.45)), k)
    negativo = g_svi < 0
    plt.figure()
    plt.plot(k, g_ssvi, label="Constrained SSVI")
    plt.plot(k, g_svi, label="Unconstrained raw SVI")
    plt.plot(k[negativo][::6], g_svi[negativo][::6], "ro", label="g(k) < 0: negative density")
    plt.plot(k, np.zeros_like(k), "k--", label="g = 0")
    plt.xlabel("Log-moneyness k")
    plt.ylabel("Durrleman g(k)")
    plt.title("Butterfly test: the density is non-negative iff g(k) >= 0")
    plt.legend()
    return guardar("s2_funcion_g")


# ---------------------------------------------------------------------------
# Breeden–Litzenberger: cotizaciones crudas frente a precios ajustados
# ---------------------------------------------------------------------------

def _mid_como_call(reb):
    return np.where(reb.es_call, reb.mid, reb.mid + reb.D * (reb.F - reb.K))


def _densidades(rebanadas, superficie):
    reb = rebanadas[1]
    verdadera = sn.superficie_referencia()
    K = np.linspace(reb.F * 0.6, reb.F * 1.3, 3001)
    C = op.precio_black(reb.F, K, superficie.w(np.log(K / reb.F), reb.T), reb.D, True)
    K_i, q_aj = ds.densidad_breeden_litzenberger(K, C, reb.D)
    q_verdad = verdadera.densidad(np.log(K_i / reb.F), reb.T) / K_i
    return reb, K_i, q_aj, q_verdad


def fig_densidad_cruda(rebanadas, superficie):
    reb, K_i, _, q_verdad = _densidades(rebanadas, superficie)
    K_c, q_c = ds.densidad_breeden_litzenberger(reb.K, _mid_como_call(reb), reb.D)
    negativos = q_c < 0
    plt.figure()
    plt.plot(K_i / reb.F, q_verdad, "--", label="True density (unknown)")
    plt.plot(K_c / reb.F, q_c, "o-", label="Second differences of raw midpoints")
    plt.plot(K_c[negativos] / reb.F, q_c[negativos], "ro", label=f"Negative values ({negativos.sum()})")
    plt.xlim(0.72, 1.18)
    plt.xlabel("Strike / forward")
    plt.ylabel("Risk-neutral density q(K)")
    plt.title("Breeden-Litzenberger on raw quotes (synthetic data)")
    plt.legend()
    return guardar("s2_densidad_cruda")


def fig_densidad_ajustada(rebanadas, superficie):
    reb, K_i, q_aj, q_verdad = _densidades(rebanadas, superficie)
    controles = ds.controles_densidad(K_i, q_aj, reb.F)
    soporte = np.linspace(reb.F * 0.55, reb.F * 1.35, 161)
    q_cv, _, _ = sf.ajuste_convexo(reb, soporte)
    plt.figure()
    plt.plot(K_i / reb.F, q_verdad, "--", label="True density (unknown)")
    plt.plot(K_i / reb.F, q_aj, label=(f"SSVI fit: mass {controles['masa']:.4f}, "
                                       f"mean/F {controles['media_sobre_forward']:.4f}"))
    plt.plot(soporte / reb.F, q_cv / (soporte[1] - soporte[0]), label="Monotone-convex fit (independent check)")
    plt.xlim(0.72, 1.18)
    plt.xlabel("Strike / forward")
    plt.ylabel("Risk-neutral density q(K)")
    plt.title("The same identity on fitted prices (synthetic data)")
    plt.legend()
    return guardar("s2_densidad_ajustada")


# ---------------------------------------------------------------------------
# Opciones americanas: sesgo de tratar precios americanos como europeos
# ---------------------------------------------------------------------------

def _sesgo_americano(es_call):
    S, sigma, r = 100.0, 0.30, 0.045
    dividendo = (20 / 365, 0.80)
    rel = np.linspace(0.8, 1.2, 33)
    curvas = {}
    for T in (30 / 365, 91 / 365):
        divs = (dividendo,) if dividendo[0] < T else ()
        vp = sum(m * np.exp(-r * t) for t, m in divs)
        F, D = (S - vp) * np.exp(r * T), np.exp(-r * T)
        sesgo, medio_spread = [], []
        for K in rel * S:
            eur = float(op.precio_black(F, K, sigma**2 * T, D, es_call))
            eep = op.prima_ejercicio_anticipado(S, K, T, r, sigma, es_call=es_call, dividendos=divs, n=400)
            iv = float(op.vol_implicita_black(eur + eep, F, K, T, D, es_call))
            _, _, vega = op.griegas_bs(S - vp, K, T, r, 0.0, sigma, es_call)
            sesgo.append((iv - sigma) * 100)
            medio_spread.append((0.02 + 0.03 * (eur + eep)) / 2 / float(vega) * 100)
        curvas[round(T * 365)] = (np.array(sesgo), np.array(medio_spread))
    return rel, curvas


def fig_americanas(es_call):
    rel, curvas = _sesgo_americano(es_call)
    plt.figure()
    for dias, (sesgo, medio) in curvas.items():
        plt.plot(rel, sesgo, label=f"Bias, {dias} days")
        plt.plot(rel, medio, "--", label=f"Half spread, {dias} days")
    plt.ylim(-0.05, 2.5)
    plt.xlabel("Strike / spot (OTM: " + ("above 1)" if es_call else "below 1)"))
    plt.ylabel("Implied volatility points")
    if es_call:
        plt.title("American calls with a cash dividend (synthetic data)")
    else:
        plt.title("American puts (synthetic data)")
    plt.legend()
    return guardar("s2_americanas_calls" if es_call else "s2_americanas_puts")


# ---------------------------------------------------------------------------
# Conjunto de superficies plausibles y colas no identificadas
# ---------------------------------------------------------------------------

def _banda(x, lo, hi):
    return np.concatenate([x, [np.nan], x]), np.concatenate([lo, [np.nan], hi])


def datos_bandas(rebanadas, extras):
    reb, ext = rebanadas[1], extras[1]
    rng = np.random.default_rng(11)
    u = sn.malla_u(399, 0.0025)
    k = np.linspace(-0.9, 0.45, 2500)
    K = reb.F * np.exp(k)
    soporte = np.linspace(reb.F * 0.55, reb.F * 1.35, 161)
    h = soporte[1] - soporte[0]
    x_cv = np.log(soporte / reb.F)
    dens_s, cuant_s, dens_c, cuant_c = [], [], [], []
    base, z = sf.ajustar_rebanada(reb)
    for i in range(160):
        virtual = rng.uniform(reb.bid, reb.ask)
        r_i = sf.Rebanada(reb.T, reb.F, reb.D, reb.K, reb.bid, reb.ask, reb.es_call, objetivo=virtual)
        aj, _ = sf.ajustar_rebanada(r_i, peso_mid=0.5, z0=z)
        p = aj.densidad(k)
        dens_s.append(p / K)
        cuant_s.append(ds.cuantiles_desde_densidad(k, p, u))
        if i < 60:
            q, _, _ = sf.ajuste_convexo(r_i, soporte, peso_mid=0.5, peso_suave=1e-4)
            dens_c.append(q / h)
            cdf = np.cumsum(q) - 0.5 * q
            cuant_c.append(np.interp(u, np.maximum.accumulate(cdf), x_cv))
    fiables = reb.K[ext["fiable"]]
    u_min, u_max = ds.soporte_identificado(fiables, reb.F, k, ds.cdf_desde_densidad(k, base.densidad(k)))
    verdad = sn.superficie_referencia().densidad(k, reb.T) / K
    return dict(u=u, k=K / reb.F, soporte=soporte / reb.F, dens_s=np.array(dens_s), cuant_s=np.array(cuant_s),
                dens_c=np.array(dens_c), cuant_c=np.array(cuant_c), verdad=verdad,
                k_min=fiables.min() / reb.F, k_max=fiables.max() / reb.F, u_min=u_min, u_max=u_max)


def fig_bandas_densidad(b):
    lo_s, hi_s = np.percentile(b["dens_s"], [2.5, 97.5], axis=0)
    lo_c, hi_c = np.percentile(b["dens_c"], [2.5, 97.5], axis=0)
    piso = 1e-5
    plt.figure()
    plt.plot(b["k"], b["verdad"], "--", label="True density (unknown)")
    plt.plot(*_banda(b["k"], lo_s, hi_s), label="SSVI band (2.5-97.5%)")
    plt.plot(*_banda(b["soporte"], np.maximum(lo_c, piso), np.maximum(hi_c, piso)),
             label="Monotone-convex band (2.5-97.5%)")
    plt.plot([b["k_min"], b["k_max"]], np.interp([b["k_min"], b["k_max"]], b["k"], b["verdad"]), "gs",
             label="Most extreme reliable strikes")
    plt.yscale("log")
    plt.xlim(0.6, 1.3)
    plt.ylim(piso, 0.4)
    plt.xlabel("Strike / forward (tails beyond the squares are not identified)")
    plt.ylabel("Risk-neutral density q(K), log scale")
    plt.title("Densities compatible with the spreads (synthetic data)")
    plt.legend()
    return guardar("s2_bandas_densidad")


def fig_bandas_cuantiles(b):
    ancho_s = np.diff(np.percentile(b["cuant_s"], [2.5, 97.5], axis=0), axis=0)[0] * 100
    ancho_c = np.diff(np.percentile(b["cuant_c"], [2.5, 97.5], axis=0), axis=0)[0] * 100
    plt.figure()
    plt.semilogy(b["u"], ancho_s, label="SSVI")
    plt.semilogy(b["u"], ancho_c, label="Monotone-convex")
    plt.semilogy([b["u_min"], b["u_max"]], np.interp([b["u_min"], b["u_max"]], b["u"], ancho_s), "gs",
                 label=f"Limits of the identified range: u = {b['u_min']:.3f} and {b['u_max']:.3f}")
    plt.xlabel("Probability level u")
    plt.ylabel("Width of the 95% sensitivity band (pp)")
    plt.title("Quantile uncertainty grows in the tails (synthetic data)")
    plt.legend()
    return guardar("s2_bandas_cuantiles")


def main():
    rutas = [fig_acumulacion_varianza(), fig_riesgo_sesion()]
    rebanadas, extras, superficie = datos_cadena()
    rutas += [fig_cotizaciones_precio(rebanadas, extras, superficie), fig_cotizaciones_vol(rebanadas, superficie),
              fig_perdida_banda(), fig_ssvi_rebanadas(superficie), fig_ssvi_region(superficie), fig_funcion_g(),
              fig_densidad_cruda(rebanadas, superficie), fig_densidad_ajustada(rebanadas, superficie),
              fig_americanas(False), fig_americanas(True)]
    b = datos_bandas(rebanadas, extras)
    rutas += [fig_bandas_densidad(b), fig_bandas_cuantiles(b)]
    return rutas


if __name__ == "__main__":
    for r in main():
        print(r)
