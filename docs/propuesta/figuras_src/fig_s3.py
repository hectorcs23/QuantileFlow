"""Figuras de la sección 3: transporte, dinámica y extracción de señal."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize

from comun import guardar, varias_curvas
from quantileflow import filtrado as fl
from quantileflow import sintetico as sn
from quantileflow import superficies as sf
from quantileflow import transporte as tr

TAU = 30 / 365
ENTRENAMIENTO = 150  # sesiones usadas para ajustar FPCA, filtros y expectativas


def panel():
    return sn.panel_distribuciones(np.random.default_rng(3))


def _cuantiles(theta, rho, eta_rel, u, gamma=0.45):
    eta = eta_rel * 2.0 / (1.0 + abs(rho))
    return sn.cuantiles_ssvi(theta, rho, sf.phi_potencia(theta, eta, gamma), u)[0]


def _densidad(theta, rho, eta, k, gamma=0.45):
    return sf.densidad_logmoneyness(k, *sf.derivadas_ssvi(k, theta, rho, sf.phi_potencia(theta, eta, gamma)))


# ---------------------------------------------------------------------------
# Transporte entre dos sesiones y W2 sobre cuantiles
# ---------------------------------------------------------------------------

def fig_densidades_choque(p):
    d = p["dia_choque"]
    par = p["mercado"]["parametros"]
    k = np.linspace(-0.5, 0.25, 1500)
    plt.figure()
    plt.plot(k * 100, _densidad(*par[d - 1], k), label="Q on the session before the shock")
    plt.plot(k * 100, _densidad(*par[d], k), label="Q on the shock session")
    plt.xlabel("x = ln(S_T / F) at 30 days (%)")
    plt.ylabel("Risk-neutral density of x")
    plt.title("Implied distribution before and after a common shock (synthetic)")
    plt.legend()
    return guardar("s3_densidades_choque")


def fig_mapa_transporte(p):
    u = p["u"]
    d = p["dia_choque"]
    x0, x1 = p["mercado"]["latente"][d - 1] * 100, p["mercado"]["latente"][d] * 100
    marcas = np.interp([0.05, 0.5, 0.95], u, np.arange(len(u))).round().astype(int)
    plt.figure()
    plt.plot(x0, x1, label="Monotone map T = F_t^-1 o F_(t-1)")
    plt.plot(x0, x0, "k--", label="Identity (no change)")
    plt.plot(x0[marcas], x1[marcas], "ro", label="Quantiles u = 0.05, 0.50, 0.95")
    plt.xlabel("Quantile before the shock, x_(t-1)(u) (%)")
    plt.ylabel("Same quantile after the shock, x_t(u) (%)")
    plt.title("1-D optimal transport map between two sessions (synthetic)")
    plt.legend()
    return guardar("s3_mapa_transporte")


def fig_funciones_cuantil(p):
    u = p["u"]
    d = p["dia_choque"]
    x0, x1 = p["mercado"]["latente"][d - 1], p["mercado"]["latente"][d]
    w2 = tr.distancia_wasserstein(x1, x0, u) * 100
    w2r = tr.distancia_wasserstein(x1, x0, u, rango=(0.05, 0.95)) * 100
    w1 = tr.distancia_wasserstein(x1, x0, u, p=1) * 100
    plt.figure()
    plt.plot(u, x0 * 100, label="x_(t-1)(u)")
    plt.plot(u, x1 * 100, label=f"x_t(u): W2 = {w2:.2f} pp, trimmed W2 = {w2r:.2f}, W1 = {w1:.2f}")
    plt.plot([0.05, 0.95], np.interp([0.05, 0.95], u, x1 * 100), "gs", label="Trimming limits u = 0.05, 0.95")
    plt.xlabel("Probability level u")
    plt.ylabel("Quantile of ln(S_T/F) (%)")
    plt.title("W2 is the L2 distance between quantile functions (synthetic)")
    plt.legend()
    return guardar("s3_funciones_cuantil")


# ---------------------------------------------------------------------------
# Cambios firmados: tres deformaciones arquetípicas
# ---------------------------------------------------------------------------

def _arquetipos():
    u = sn.malla_u(399, 0.0025)
    base = dict(theta=0.19**2 * TAU, rho=-0.68, eta_rel=0.80)
    x_base = _cuantiles(**base, u=u)
    variantes = [
        ("More dispersion (ATM vol +12%)", dict(base, theta=base["theta"] * 1.25)),
        ("Heavier left tail (rho -0.68 to -0.80)", dict(base, rho=-0.80)),
        ("Wings only (relative eta 0.80 to 0.95)", dict(base, eta_rel=0.95)),
    ]
    return u, x_base, [(nombre, _cuantiles(**par, u=u)) for nombre, par in variantes]


def fig_cambios_firmados():
    u, x_base, variantes = _arquetipos()
    plt.figure()
    for nombre, x in variantes:
        plt.plot(u, (x - x_base) * 100, label=nombre)
    plt.plot(u, np.zeros_like(u), "k--", label="No change")
    plt.xlabel("Probability level u")
    plt.ylabel("Signed change of the quantile, dx(u) (pp)")
    plt.title("Signed quantile changes for three deformations")
    plt.legend()
    return guardar("s3_cambios_firmados")


def fig_distancias_arquetipos():
    u, x_base, variantes = _arquetipos()
    medidas = ["W1", "W2", "Trimmed W2 (average)"]
    x = np.arange(3)
    plt.figure()
    for i, (nombre, xv) in enumerate(variantes):
        valores = [tr.distancia_wasserstein(xv, x_base, u, p=1) * 100,
                   tr.distancia_wasserstein(xv, x_base, u) * 100,
                   tr.distancia_wasserstein(xv, x_base, u, rango=(0.05, 0.95), normalizar_rango=True) * 100]
        plt.bar(x + (i - 1) * 0.27, valores, 0.27, label=nombre)
    plt.xticks(x, medidas)
    plt.ylim(0, 1.05)
    plt.xlabel("Distance (trimmed version averages over u in [0.05, 0.95])")
    plt.ylabel("Distance (pp of log return)")
    plt.title("A single magnitude does not say what changed")
    plt.legend()
    return guardar("s3_distancias_arquetipos")


# ---------------------------------------------------------------------------
# Mapa temporal de cuantiles y distancias diarias
# ---------------------------------------------------------------------------

def fig_mapa_cuantiles(p):
    u = p["u"]
    Y = p["mercado"]["observado"]
    n = Y.shape[0]
    dev = (Y - np.nanmean(Y[:ENTRENAMIENTO], axis=0)) * 100
    plt.figure()
    plt.imshow(dev.T, aspect="auto", origin="lower", extent=[-0.5, n - 0.5, u[0], u[-1]])
    plt.colorbar(label="x_t(u) minus its training mean (pp)")
    plt.xlabel("Session (blank columns: missing snapshots)")
    plt.ylabel("Probability level u")
    plt.title("Time map of quantiles (synthetic; common shock at 170)")
    return guardar("s3_mapa_cuantiles")


def fig_distancias_diarias(p):
    u = p["u"]
    Y = p["mercado"]["observado"]
    n = Y.shape[0]
    w2 = np.full(n, np.nan)
    w2r = np.full(n, np.nan)
    for t in range(1, n):
        if np.all(np.isfinite(Y[t])) and np.all(np.isfinite(Y[t - 1])):
            w2[t] = tr.distancia_wasserstein(Y[t], Y[t - 1], u) * 100
            w2r[t] = tr.distancia_wasserstein(Y[t], Y[t - 1], u, rango=(0.05, 0.95)) * 100
    malos = np.where(p["calidad"] > 2.5)[0]
    plt.figure()
    plt.plot(np.arange(n), w2, label="W2, full range")
    plt.plot(np.arange(n), w2r, label="W2 trimmed to u in [0.05, 0.95]")
    plt.plot(malos, w2[malos], "ro", label="Sessions with wide spreads (part is fitting noise)")
    plt.xlabel("Session")
    plt.ylabel("Distance between consecutive sessions (pp)")
    plt.title("Daily Wasserstein distances (synthetic)")
    plt.legend()
    return guardar("s3_distancias_diarias")


# ---------------------------------------------------------------------------
# Velocidad y aceleración: amplificación del ruido de medición
# ---------------------------------------------------------------------------

def _series_ruido(p):
    rng = np.random.default_rng(21)
    f = np.log(p["mercado"]["vol"])
    y = f + rng.normal(0.0, 0.02, size=f.size)
    return [("Level", f - f.mean(), y - f.mean()), ("Velocity", np.diff(f), np.diff(y)),
            ("Acceleration", np.diff(f, 2), np.diff(y, 2))]


def fig_senal_ruido(p):
    series = _series_ruido(p)
    nombres = [s[0] for s in series]
    snr = [np.var(v) / np.var(o - v) for _, v, o in series]
    plt.figure()
    plt.bar(nombres, snr)
    plt.yscale("log")
    plt.xlabel("Transformation of the observed factor (noise sd x1, x1.41, x2.45)")
    plt.ylabel("Signal variance / noise variance (log scale)")
    plt.title("Differencing amplifies measurement noise (synthetic)")
    return guardar("s3_senal_ruido")


def fig_aceleracion(p):
    _, verdad, obs = _series_ruido(p)[2]
    t = np.arange(len(verdad))
    plt.figure()
    plt.plot(t, verdad, label="Latent acceleration")
    plt.plot(t, obs - verdad, label="Measurement noise in the acceleration")
    plt.xlabel("Session")
    plt.ylabel("Second difference of log volatility")
    plt.title("Acceleration: noise is comparable to the signal (synthetic)")
    plt.legend()
    return guardar("s3_aceleracion")


# ---------------------------------------------------------------------------
# PCA funcional de cuantiles
# ---------------------------------------------------------------------------

def fpca_entrenamiento(p):
    Y = p["mercado"]["observado"]
    entrenamiento = Y[:ENTRENAMIENTO][np.all(np.isfinite(Y[:ENTRENAMIENTO]), axis=1)]
    return tr.ComponentesFuncionales(6).ajustar(entrenamiento, p["u"])


def fig_fpca_autofunciones(p):
    fpca = fpca_entrenamiento(p)
    nombres = ["dispersion", "asymmetry", "tails"]
    plt.figure()
    for i, nm in enumerate(nombres):
        plt.plot(p["u"], fpca.autofunciones[:, i],
                 label=f"PC{i + 1} ({nm}): {fpca.proporcion[i] * 100:.2g}% of variance")
    plt.xlabel("Probability level u")
    plt.ylabel("Eigenfunction phi_j(u)")
    plt.title("Functional PCA of quantiles, training sessions only (synthetic)")
    plt.legend()
    return guardar("s3_fpca_autofunciones")


def fig_fpca_varianza(p):
    fpca = fpca_entrenamiento(p)
    plt.figure()
    plt.bar([f"PC{i}" for i in range(1, 7)], fpca.proporcion[:6] * 100)
    plt.yscale("log")
    plt.xlabel("Component")
    plt.ylabel("Explained variance (%, log scale)")
    plt.title("Tail components explain little total variance (synthetic)")
    return guardar("s3_fpca_varianza")


# ---------------------------------------------------------------------------
# Kalman frente a EWMA y persistencia
# ---------------------------------------------------------------------------

def _nll_kalman(params, y, calidad):
    a = np.tanh(params[0])
    q, r0 = np.exp(params[1]), np.exp(params[2])
    f, P, nll = y[np.isfinite(y)][0], 1.0, 0.0
    for t, v in enumerate(y):
        f, P = a * f, a * a * P + q
        if np.isfinite(v):
            S = P + r0 * calidad[t] ** 2
            e = v - f
            nll += np.log(S) + e * e / S
            K = P / S
            f, P = f + K * e, (1 - K) * P
    return 0.5 * nll


def datos_kalman(p):
    fpca = fpca_entrenamiento(p)
    Y, X, calidad = p["mercado"]["observado"], p["mercado"]["latente"], p["calidad"]
    n = Y.shape[0]
    obs = np.full(n, np.nan)
    ok = np.all(np.isfinite(Y), axis=1)
    obs[ok] = fpca.transformar(Y[ok])[:, 0]
    verdad = fpca.transformar(X)[:, 0]
    # Parámetros del filtro por máxima verosimilitud, solo con sesiones de entrenamiento.
    sol = minimize(_nll_kalman, x0=[1.5, np.log(1e-4), np.log(1e-4)],
                   args=(obs[:ENTRENAMIENTO], calidad[:ENTRENAMIENTO]), method="Nelder-Mead",
                   options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-8})
    a, q, r0 = np.tanh(sol.x[0]), np.exp(sol.x[1]), np.exp(sol.x[2])
    medias, covs, _, _ = fl.filtro_kalman(obs, [[a]], [[1.0]], [[q]], (r0 * calidad**2).reshape(-1, 1, 1),
                                         [obs[0]], [[r0]])
    return dict(obs=obs, verdad=verdad, kal=medias[:, 0], sd=np.sqrt(covs[:, 0, 0]), ewma=fl.ewma(obs, 0.85),
                pers=fl.persistencia(obs), calidad=calidad, n=n)


def fig_kalman(p, k):
    t = np.arange(k["n"])
    v = slice(40, 215)
    plt.figure()
    plt.plot(t[v], k["obs"][v], ".", label="Daily observation")
    plt.plot(t[v], k["verdad"][v], "--", label="Latent factor (unknown)")
    plt.plot(t[v], k["ewma"][v], label="EWMA (lambda = 0.85)")
    plt.plot(t[v], k["kal"][v], label="Kalman filter")
    banda_x = np.concatenate([t[v], [np.nan], t[v]])
    banda_y = np.concatenate([(k["kal"] - 2 * k["sd"])[v], [np.nan], (k["kal"] + 2 * k["sd"])[v]])
    plt.plot(banda_x, banda_y, ":", label="Kalman +/- 2 sd")
    plt.xlabel("Session (wide spreads in 60-75, common shock at 170)")
    plt.ylabel("Score of PC1 (dispersion)")
    plt.title("Causal filtering of the first factor (synthetic)")
    plt.legend()
    return guardar("s3_kalman")


def fig_kalman_error(p, k):
    t = np.arange(k["n"])
    d = p["dia_choque"]
    malos = k["calidad"] > 2.5
    periodos = {"Normal quality": (~malos) & (t >= ENTRENAMIENTO) & ((t < d) | (t > d + 10)),
                "Wide spreads": malos,
                "10 sessions after shock": (t >= d) & (t <= d + 10)}
    x = np.arange(3)
    plt.figure()
    for i, (nombre, est) in enumerate([("Persistence", k["pers"]), ("EWMA", k["ewma"]), ("Kalman", k["kal"])]):
        rmse = [np.sqrt(np.nanmean((est[m] - k["verdad"][m]) ** 2)) for m in periodos.values()]
        plt.bar(x + (i - 1) * 0.27, rmse, 0.27, label=nombre)
    plt.xticks(x, list(periodos.keys()))
    plt.xlabel("Evaluation window")
    plt.ylabel("Root mean squared error vs latent factor")
    plt.title("No filter wins everywhere (synthetic)")
    plt.legend()
    return guardar("s3_kalman_error")


# ---------------------------------------------------------------------------
# Innovación condicionada a la información base
# ---------------------------------------------------------------------------

def _innovaciones(p, activo, u0=0.05):
    """Cambio observado de la cola menos su expectativa con información base.

    La expectativa es una regresión lineal ajustada solo con sesiones de
    entrenamiento; fuera de esa ventana el residuo es fuera de muestra.
    """
    u = p["u"]
    X = p[activo]["observado"]
    n = X.shape[0]
    xq = np.array([np.interp(u0, u, X[t]) if np.all(np.isfinite(X[t])) else np.nan for t in range(n)])
    dx = np.full(n, np.nan)
    dx[1:] = np.diff(xq)
    r_propio, r_m = p[activo]["ret"], p["mercado"]["ret"]
    base = np.column_stack([np.ones(n), r_propio, np.abs(r_propio), r_m, np.abs(r_m)])
    entren = np.isfinite(dx) & (np.arange(n) < ENTRENAMIENTO)
    beta, *_ = np.linalg.lstsq(base[entren], dx[entren], rcond=None)
    esperado = base @ beta
    return dx * 100, esperado * 100, (dx - esperado) * 100


def fig_innovacion_dispersion(p):
    dx, esp, _ = _innovaciones(p, "accion")
    t = np.arange(len(dx))
    ev, ch = p["dia_evento"], p["dia_choque"]
    entren = t < ENTRENAMIENTO
    lim = np.array([-11.5, 4.5])
    plt.figure()
    plt.plot(esp[entren], dx[entren], ".", label="Training sessions")
    plt.plot(esp[~entren], dx[~entren], ".", label="Out-of-sample sessions")
    plt.plot(lim, lim, "k--", label="Observed = expected")
    plt.plot(esp[ev], dx[ev], "ro", label="Idiosyncratic tail event (no price move)")
    plt.plot(esp[ch], dx[ch], "gs", label="Common market shock")
    plt.xlabel("Expected change given base information (pp)")
    plt.ylabel("Observed change of x_t(0.05) (pp)")
    plt.title("Stock A: observed vs expected left-tail change (synthetic)")
    plt.legend(loc="upper left")
    return guardar("s3_innovacion_dispersion")


def fig_innovacion_serie(p):
    _, _, inn_a = _innovaciones(p, "accion")
    _, _, inn_m = _innovaciones(p, "mercado")
    t = np.arange(len(inn_a))
    ev, ch = p["dia_evento"], p["dia_choque"]
    ok = np.isfinite(inn_a) & np.isfinite(inn_m) & (t < ENTRENAMIENTO)
    beta = np.sum(inn_a[ok] * inn_m[ok]) / np.sum(inn_m[ok] ** 2)
    relativa = inn_a - beta * inn_m
    plt.figure()
    plt.plot(t, inn_m, label="Market innovation")
    plt.plot(t, relativa, label=f"Stock A relative to market (beta = {beta:.2f})")
    plt.plot(ch, relativa[ch], "gs", label="Common shock: mostly cancels")
    plt.plot(ev, relativa[ev], "ro", label="Event specific to A")
    plt.xlabel("Session (expectation model fitted on sessions < 150)")
    plt.ylabel("Innovation of the 5% quantile (pp)")
    plt.title("Idiosyncratic innovation vs common shock (synthetic)")
    plt.legend()
    return guardar("s3_innovacion_serie")


# ---------------------------------------------------------------------------
# Deformación por plazo: 7, 30 y 60 días
# ---------------------------------------------------------------------------

def _fig_plazos(nombre, titulo, f_theta, f_rho):
    u = sn.malla_u(399, 0.0025)
    plazos = np.array([7, 30, 60]) / 365
    theta = np.array([0.30, 0.31, 0.315]) ** 2 * plazos
    plt.figure()
    for T, th in zip(plazos, theta):
        x0 = _cuantiles(th, -0.45, 0.75, u)
        x1 = _cuantiles(f_theta(th, round(T * 365)), f_rho(-0.45), 0.75, u)
        plt.plot(u, (x1 - x0) / np.sqrt(T) * 100, label=f"{T * 365:.0f}-day distribution")
    plt.xlabel("Probability level u")
    plt.ylabel("dx(u) / sqrt(tau) (pp per sqrt-year)")
    plt.title(titulo)
    plt.legend()
    return guardar(nombre)


def fig_plazos_comun():
    alza = {7: 1.35, 30: 1.25, 60: 1.18}
    return _fig_plazos("s3_plazos_comun", "Common volatility shock across tenors",
                       lambda th, d: th * alza[d] ** 2, lambda r: r - 0.06)


def fig_plazos_evento():
    return _fig_plazos("s3_plazos_evento", "Earnings event inside the next 7 days",
                       lambda th, d: th + 0.045**2, lambda r: r - 0.10)


# ---------------------------------------------------------------------------
# Las marginales no identifican trayectorias ni probabilidades de tocar un stop
# ---------------------------------------------------------------------------

def datos_trayectorias():
    rng = np.random.default_rng(5)
    S0, sigma, T2, pasos, n = 100.0, 0.25, 60 / 365, 120, 20000
    dt = T2 / pasos
    z = rng.standard_normal((n, pasos))
    log_s = np.log(S0) + np.cumsum(-0.5 * sigma**2 * dt + sigma * np.sqrt(dt) * z, axis=1)
    S = np.exp(np.concatenate([np.full((n, 1), np.log(S0)), log_s], axis=1))
    X1s, X2s = np.sort(S[:, pasos // 2]), np.sort(S[:, -1])
    return dict(S=S, dias=np.linspace(0, T2, pasos + 1) * 365, X1s=X1s, X2s=X2s, S0=S0, T2=T2 * 365,
                muestra=rng.choice(n, 70, replace=False), rangos=np.sort(rng.choice(n, 70, replace=False)))


def fig_trayectorias_difusion(d, stop=90.0):
    toca = d["S"].min(axis=1) <= stop
    m = d["muestra"]
    plt.figure()
    plt.plot(*varias_curvas([d["dias"]] * (~toca[m]).sum(), d["S"][m][~toca[m]]), label="Paths that do not touch")
    plt.plot(*varias_curvas([d["dias"]] * toca[m].sum(), d["S"][m][toca[m]]), label="Paths that touch the stop")
    plt.plot([0, d["T2"]], [stop, stop], "k--", label=f"Stop at {stop:.0f}")
    plt.xlabel("Days (marginals fixed at day 30 and day 60)")
    plt.ylabel("Price")
    plt.title(f"Diffusion: P(touch stop) = {toca.mean() * 100:.1f}% (synthetic)")
    plt.legend()
    return guardar("s3_trayectorias_difusion")


def fig_trayectorias_transporte(d, stop=90.0):
    toca = np.minimum(d["X1s"], d["X2s"]) <= stop
    dias = [0, d["T2"] / 2, d["T2"]]
    r = d["rangos"]
    caminos = np.column_stack([np.full(len(r), d["S0"]), d["X1s"][r], d["X2s"][r]])
    plt.figure()
    plt.plot(*varias_curvas([dias] * (~toca[r]).sum(), caminos[~toca[r]]), label="Paths that do not touch")
    plt.plot(*varias_curvas([dias] * toca[r].sum(), caminos[toca[r]]), label="Paths that touch the stop")
    plt.plot([0, d["T2"]], [stop, stop], "k--", label=f"Stop at {stop:.0f}")
    plt.xlabel("Days (same marginals at day 30 and day 60 as the diffusion)")
    plt.ylabel("Price")
    plt.title(f"Monotone transport read as paths: P = {toca.mean() * 100:.1f}% (synthetic)")
    plt.legend()
    return guardar("s3_trayectorias_transporte")


def main():
    p = panel()
    k = datos_kalman(p)
    d = datos_trayectorias()
    return [fig_densidades_choque(p), fig_mapa_transporte(p), fig_funciones_cuantil(p), fig_cambios_firmados(),
            fig_distancias_arquetipos(), fig_mapa_cuantiles(p), fig_distancias_diarias(p), fig_senal_ruido(p),
            fig_aceleracion(p), fig_fpca_autofunciones(p), fig_fpca_varianza(p), fig_kalman(p, k),
            fig_kalman_error(p, k), fig_innovacion_dispersion(p), fig_innovacion_serie(p), fig_plazos_comun(),
            fig_plazos_evento(), fig_trayectorias_difusion(d), fig_trayectorias_transporte(d)]


if __name__ == "__main__":
    for r in main():
        print(r)
