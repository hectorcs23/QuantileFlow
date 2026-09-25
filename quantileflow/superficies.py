"""Superficies de volatilidad implícita: SSVI y un ajuste convexo independiente.

SSVI (Gatheral y Jacquier, 2014) describe la varianza implícita total como

    w(k, theta) = theta/2 * (1 + rho*phi*k + sqrt((phi*k + rho)**2 + 1 - rho**2)),

donde ``theta`` es la varianza total ATM de cada vencimiento. Con la función de
potencia ``phi(theta) = eta / (theta**gamma * (1 + theta)**(1 - gamma))`` son
condiciones suficientes de ausencia de arbitraje estático:

* ``theta`` no decreciente en el vencimiento (calendario),
* ``0 < gamma <= 1/2`` y ``eta * (1 + |rho|) <= 2`` (mariposa y calendario).

El ajuste se hace en **espacio de precios**: el residuo de cada cotización es su
distancia al intervalo [bid, ask] medida en medios spreads, más un término
pequeño hacia el midpoint que solo desempata. El midpoint no se trata como
verdad exacta.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares, lsq_linear

from .opciones import precio_black

# ---------------------------------------------------------------------------
# Forma funcional
# ---------------------------------------------------------------------------


def phi_potencia(theta, eta, gamma):
    """Función de potencia de Gatheral–Jacquier."""
    theta = np.asarray(theta, dtype=float)
    return eta / (theta**gamma * (1.0 + theta) ** (1.0 - gamma))


def varianza_total_ssvi(k, theta, rho, phi):
    """Varianza implícita total ``w(k)`` de una rebanada SSVI."""
    pk = phi * np.asarray(k, dtype=float)
    return 0.5 * theta * (1.0 + rho * pk + np.sqrt((pk + rho) ** 2 + 1.0 - rho**2))


def derivadas_ssvi(k, theta, rho, phi):
    """``w``, ``w'`` y ``w''`` respecto de ``k`` (expresiones analíticas)."""
    k = np.asarray(k, dtype=float)
    pk = phi * k
    raiz = np.sqrt((pk + rho) ** 2 + 1.0 - rho**2)
    w = 0.5 * theta * (1.0 + rho * pk + raiz)
    w1 = 0.5 * theta * phi * (rho + (pk + rho) / raiz)
    w2 = 0.5 * theta * phi**2 * (1.0 - rho**2) / raiz**3
    return w, w1, w2


def funcion_g(w, w1, w2, k):
    """Función ``g(k)`` de Durrleman: la densidad es no negativa si ``g >= 0``."""
    k = np.asarray(k, dtype=float)
    return (1.0 - k * w1 / (2.0 * w)) ** 2 - 0.25 * w1**2 * (1.0 / w + 0.25) + 0.5 * w2


def densidad_logmoneyness(k, w, w1, w2):
    """Densidad Q de ``x = ln(S_T / F)`` evaluada en ``x = k``.

    ``p(k) = g(k) / sqrt(2*pi*w) * exp(-d_menos**2 / 2)`` con
    ``d_menos = -k/sqrt(w) - sqrt(w)/2``. Coincide con la segunda derivada de
    Breeden–Litzenberger expresada en log-moneyness.
    """
    g = funcion_g(w, w1, w2, k)
    raiz_w = np.sqrt(w)
    d_menos = -np.asarray(k) / raiz_w - 0.5 * raiz_w
    return g / np.sqrt(2.0 * np.pi * w) * np.exp(-0.5 * d_menos**2)


def varianza_total_svi_cruda(k, a, b, rho, m, sigma):
    """SVI "raw" sin restricciones (usado solo como contraejemplo)."""
    k = np.asarray(k, dtype=float)
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sigma**2))


def derivadas_svi_cruda(k, a, b, rho, m, sigma):
    k = np.asarray(k, dtype=float)
    raiz = np.sqrt((k - m) ** 2 + sigma**2)
    w = a + b * (rho * (k - m) + raiz)
    w1 = b * (rho + (k - m) / raiz)
    w2 = b * sigma**2 / raiz**3
    return w, w1, w2


# ---------------------------------------------------------------------------
# Superficie con función de potencia
# ---------------------------------------------------------------------------


@dataclass
class SuperficieSSVI:
    """Superficie SSVI con ``phi`` de potencia y nodos de varianza ATM."""

    tiempos: np.ndarray  # vencimientos en años, crecientes
    thetas: np.ndarray  # varianza total ATM en cada vencimiento
    rho: float
    eta: float
    gamma: float
    info: dict = field(default_factory=dict)

    def theta_en(self, T):
        """Interpola ``theta`` linealmente en ``T`` (preserva monotonía)."""
        T = np.asarray(T, dtype=float)
        t0, th0 = self.tiempos[0], self.thetas[0]
        dentro = np.interp(T, self.tiempos, self.thetas)
        antes = th0 * T / t0
        pendiente_final = self.thetas[-1] / self.tiempos[-1]
        despues = self.thetas[-1] + pendiente_final * (T - self.tiempos[-1])
        return np.where(T < t0, antes, np.where(T > self.tiempos[-1], despues, dentro))

    def phi(self, theta):
        return phi_potencia(theta, self.eta, self.gamma)

    def w(self, k, T):
        theta = self.theta_en(T)
        return varianza_total_ssvi(k, theta, self.rho, self.phi(theta))

    def derivadas(self, k, T):
        theta = self.theta_en(T)
        return derivadas_ssvi(k, theta, self.rho, self.phi(theta))

    def densidad(self, k, T):
        w, w1, w2 = self.derivadas(k, T)
        return densidad_logmoneyness(k, w, w1, w2)

    def condiciones(self):
        """Verifica las condiciones suficientes de ausencia de arbitraje estático."""
        return condiciones_potencia(self.thetas, self.rho, self.eta, self.gamma)


def condiciones_potencia(thetas, rho, eta, gamma):
    """Condiciones suficientes de Gatheral–Jacquier para la función de potencia."""
    thetas = np.asarray(thetas, dtype=float)
    phi = phi_potencia(thetas, eta, gamma)
    return {
        "calendario_theta_creciente": bool(np.all(np.diff(thetas) >= 0.0)),
        "gamma_en_(0,1/2]": bool(0.0 < gamma <= 0.5),
        "eta(1+|rho|)<=2": bool(eta * (1.0 + abs(rho)) <= 2.0 + 1e-12),
        "mariposa_1": bool(np.all(thetas * phi * (1.0 + abs(rho)) < 4.0)),
        "mariposa_2": bool(np.all(thetas * phi**2 * (1.0 + abs(rho)) <= 4.0 + 1e-12)),
    }


# ---------------------------------------------------------------------------
# Ajuste en espacio de precios
# ---------------------------------------------------------------------------


@dataclass
class Rebanada:
    """Cotizaciones de un vencimiento, ya filtradas (típicamente OTM)."""

    T: float
    F: float
    D: float
    K: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    es_call: np.ndarray
    objetivo: np.ndarray | None = None  # punto interior de referencia (por omisión, el mid)

    @property
    def mid(self):
        if self.objetivo is not None:
            return self.objetivo
        return 0.5 * (self.bid + self.ask)

    @property
    def medio_spread(self):
        return np.maximum(0.5 * (self.ask - self.bid), 0.005)


def residuos_banda(precio, reb: Rebanada, peso_mid=0.02):
    """Distancia al intervalo [bid, ask] en medios spreads, más un término al mid."""
    s = reb.medio_spread
    fuera = (np.maximum(reb.bid - precio, 0.0) + np.maximum(precio - reb.ask, 0.0)) / s
    al_mid = np.sqrt(peso_mid) * (precio - reb.mid) / s
    return np.concatenate([fuera, al_mid])


def _sigmoide(z):
    return 1.0 / (1.0 + np.exp(-z))


def _logit(p):
    return np.log(p / (1.0 - p))


def _desempacar_superficie(z, n):
    rho = 0.999 * np.tanh(z[0])
    gamma = 0.5 * _sigmoide(z[1])
    eta = 2.0 / (1.0 + abs(rho)) * _sigmoide(z[2])
    thetas = np.cumsum(np.exp(z[3 : 3 + n]))
    return thetas, rho, eta, gamma


def ajustar_superficie(rebanadas, rho0=-0.6, eta0=1.0, gamma0=0.4, peso_mid=0.02,
                       previo: SuperficieSSVI | None = None, peso_previo=0.0):
    """Ajusta una superficie SSVI con restricciones suficientes por construcción.

    La parametrización garantiza ``theta`` creciente, ``gamma`` en (0, 1/2) y
    ``eta (1+|rho|) < 2``. ``previo`` y ``peso_previo`` regularizan hacia el
    ajuste de la sesión anterior.
    """
    rebanadas = sorted(rebanadas, key=lambda r: r.T)
    n = len(rebanadas)
    tiempos = np.array([r.T for r in rebanadas])
    theta_ini = []
    for r in rebanadas:
        cerca = np.argsort(np.abs(np.log(r.K / r.F)))[:2]
        m = float(np.mean(r.mid[cerca]))
        # Aproximación ATM: precio ~ 0.4 D F sqrt(w)
        theta_ini.append(max((m / (0.4 * r.D * r.F)) ** 2, 1e-5))
    theta_ini = np.maximum.accumulate(np.array(theta_ini) * (1 + 1e-3 * np.arange(n)))
    incrementos = np.diff(np.concatenate([[0.0], theta_ini]))
    incrementos = np.maximum(incrementos, 1e-6)
    eta_rel = np.clip(eta0 * (1 + abs(rho0)) / 2.0, 0.05, 0.95)
    z0 = np.concatenate([[np.arctanh(rho0 / 0.999), _logit(gamma0 / 0.5), _logit(eta_rel)],
                         np.log(incrementos)])
    z_previo = None
    if previo is not None and peso_previo > 0:
        inc_p = np.maximum(np.diff(np.concatenate([[0.0], previo.theta_en(tiempos)])), 1e-6)
        z_previo = np.concatenate([
            [np.arctanh(previo.rho / 0.999), _logit(previo.gamma / 0.5),
             _logit(np.clip(previo.eta * (1 + abs(previo.rho)) / 2.0, 1e-4, 1 - 1e-4))],
            np.log(inc_p)])

    def residuos(z):
        thetas, rho, eta, gamma = _desempacar_superficie(z, n)
        partes = []
        for th, r in zip(thetas, rebanadas):
            k = np.log(r.K / r.F)
            w = varianza_total_ssvi(k, th, rho, phi_potencia(th, eta, gamma))
            partes.append(residuos_banda(precio_black(r.F, r.K, w, r.D, r.es_call), r, peso_mid))
        if z_previo is not None:
            partes.append(np.sqrt(peso_previo) * (z - z_previo))
        return np.concatenate(partes)

    sol = least_squares(residuos, z0, method="trf", x_scale="jac", max_nfev=4000)
    thetas, rho, eta, gamma = _desempacar_superficie(sol.x, n)
    fuera = 0
    for th, r in zip(thetas, rebanadas):
        k = np.log(r.K / r.F)
        w = varianza_total_ssvi(k, th, rho, phi_potencia(th, eta, gamma))
        p = precio_black(r.F, r.K, w, r.D, r.es_call)
        fuera += int(np.sum((p < r.bid - 1e-9) | (p > r.ask + 1e-9)))
    info = {"costo": float(sol.cost), "exito": bool(sol.success), "cotizaciones_fuera": fuera}
    return SuperficieSSVI(tiempos, thetas, float(rho), float(eta), float(gamma), info)


@dataclass
class RebanadaSSVI:
    """Una sola rebanada SSVI con ``phi`` libre (sujeta a las cotas de mariposa)."""

    T: float
    theta: float
    rho: float
    phi: float

    def w(self, k):
        return varianza_total_ssvi(k, self.theta, self.rho, self.phi)

    def derivadas(self, k):
        return derivadas_ssvi(k, self.theta, self.rho, self.phi)

    def densidad(self, k):
        return densidad_logmoneyness(k, *self.derivadas(k))


def _phi_max(theta, rho):
    base = theta * (1.0 + abs(rho))
    return min(4.0 / base * 0.999, 2.0 / np.sqrt(base))


def ajustar_rebanada(reb: Rebanada, peso_mid=0.02, z0=None):
    """Ajusta ``(theta, rho, phi)`` de una rebanada respetando las cotas de mariposa.

    Condiciones: ``theta*phi*(1+|rho|) < 4`` y ``theta*phi**2*(1+|rho|) <= 4``.
    """
    k = np.log(reb.K / reb.F)

    def desempacar(z):
        theta = np.exp(z[0])
        rho = 0.999 * np.tanh(z[1])
        phi = _phi_max(theta, rho) * _sigmoide(z[2])
        return theta, rho, phi

    if z0 is None:
        cerca = np.argsort(np.abs(k))[:2]
        m = float(np.mean(reb.mid[cerca]))
        theta0 = max((m / (0.4 * reb.D * reb.F)) ** 2, 1e-5)
        phi0 = min(0.4 * _phi_max(theta0, 0.6), 1.0 / np.sqrt(theta0))
        z0 = np.array([np.log(theta0), np.arctanh(-0.6 / 0.999), _logit(phi0 / _phi_max(theta0, 0.6))])

    def residuos(z):
        theta, rho, phi = desempacar(z)
        w = varianza_total_ssvi(k, theta, rho, phi)
        return residuos_banda(precio_black(reb.F, reb.K, w, reb.D, reb.es_call), reb, peso_mid)

    sol = least_squares(residuos, z0, method="trf", x_scale="jac", max_nfev=3000)
    theta, rho, phi = desempacar(sol.x)
    return RebanadaSSVI(reb.T, float(theta), float(rho), float(phi)), sol.x


# ---------------------------------------------------------------------------
# Comparación independiente: precios monótonos y convexos por construcción
# ---------------------------------------------------------------------------


def ajuste_convexo(reb: Rebanada, soporte, peso_mid=0.02, peso_suave=1e-5):
    """Ajusta una densidad discreta ``q_j >= 0`` sobre ``soporte``.

    Los precios ``C(K) = D * sum_j q_j (x_j - K)^+`` (y análogos para puts) son
    decrecientes y convexos en ``K`` para cualquier ``q >= 0``; además se exige
    ``sum q = 1`` y ``sum q x = F`` (media compatible con el forward). No usa
    ninguna forma paramétrica de volatilidad: sirve como contraste de SSVI.
    """
    x = np.asarray(soporte, dtype=float)
    m = len(x)
    nK = len(reb.K)
    A = np.where(reb.es_call[:, None], np.maximum(x[None, :] - reb.K[:, None], 0.0),
                 np.maximum(reb.K[:, None] - x[None, :], 0.0)) * reb.D
    s = reb.medio_spread
    L = np.diff(np.eye(m), n=2, axis=0) * m**2
    grande = 1e4
    # Variables [q (m), p (nK)]: p es un precio libre dentro de [bid, ask]; la
    # distancia (A q - p) / s reproduce la pérdida por banda y el problema
    # completo es mínimos cuadrados lineales con cotas (convexo).
    filas = [
        np.hstack([A / s[:, None], -np.diag(1.0 / s)]),
        np.hstack([np.sqrt(peso_mid) * A / s[:, None], np.zeros((nK, nK))]),
        np.hstack([np.sqrt(peso_suave) * L, np.zeros((m - 2, nK))]),
        np.hstack([grande * np.ones((1, m)), np.zeros((1, nK))]),
        np.hstack([grande * (x / reb.F)[None, :], np.zeros((1, nK))]),
    ]
    objetivo = np.concatenate([np.zeros(nK), np.sqrt(peso_mid) * reb.mid / s, np.zeros(m - 2),
                               [grande], [grande]])
    inferior = np.concatenate([np.zeros(m), reb.bid])
    superior = np.concatenate([np.full(m, np.inf), np.maximum(reb.ask, reb.bid + 1e-9)])
    sol = lsq_linear(np.vstack(filas), objetivo, bounds=(inferior, superior), method="trf",
                     lsmr_tol="auto", max_iter=5000, tol=1e-12)
    q = np.maximum(sol.x[:m], 0.0)
    return q, A @ q, sol
