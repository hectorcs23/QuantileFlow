"""Contraste de IV plana y SSVI con la misma pérdida de bandas en entrenamiento.

No pronostica spot ni calibra volatilidad local. Los datos individuales y los
parámetros estimados de mercado deben permanecer en el repositorio privado.
"""
from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import least_squares

from .opciones import precio_black
from .superficies import (Rebanada, SuperficieSSVI, ajustar_superficie,
                         residuos_banda, varianza_total_ssvi)


@dataclass
class AjusteBandas:
    planas: dict
    superficie: SuperficieSSVI
    diagnostico: dict


def _validar(rebanadas, preferencia, peso):
    if not rebanadas or not 0 <= preferencia <= 1 or not math.isfinite(peso) or peso <= 0:
        raise ValueError("rebanadas y preferencia/peso de banda inválidos")
    if len({r.T for r in rebanadas}) != len(rebanadas):
        raise ValueError("una rebanada por plazo")
    for r in rebanadas:
        if not all(math.isfinite(x) and x > 0 for x in (r.T, r.F, r.D)):
            raise ValueError("plazo/forward/descuento inválidos")
        n = len(r.K)
        if n < 3 or any(np.shape(a) != (n,) for a in (r.bid, r.ask, r.es_call)):
            raise ValueError("cotizaciones insuficientes o formas incompatibles")
        if not all(np.isfinite(a).all() for a in (r.K, r.bid, r.ask)):
            raise ValueError("cotizaciones no finitas")
        if (r.K <= 0).any() or (r.bid < 0).any() or (r.ask <= r.bid).any():
            raise ValueError("bandas inválidas")
        if np.asarray(r.es_call).dtype != bool:
            raise ValueError("tipo de opción debe ser booleano")


def ajustar_bandas(rebanadas, preferencia=.5, peso_mid=.02):
    """Tres inicios fijos por modelo; selección únicamente por pérdida training.

    ``preferencia`` 0/0.5/1 regulariza hacia bid/mid/ask sin modificar las bandas.
    Son perturbaciones deterministas, no muestras de un intervalo de confianza.
    El éxito numérico nunca significa que todas las bandas sean factibles.
    """
    rebanadas = sorted(list(rebanadas), key=lambda r: r.T)
    _validar(rebanadas, preferencia, peso_mid)
    rs = [Rebanada(r.T, r.F, r.D, r.K, r.bid, r.ask, r.es_call,
                   r.bid + preferencia*(r.ask-r.bid)) for r in rebanadas]
    planas, costos, exitos = {}, [], []
    for r in rs:
        def fun(z):
            p = precio_black(r.F, r.K, math.exp(2*float(z[0]))*r.T, r.D, r.es_call)
            return residuos_banda(p, r, peso_mid)
        sols = [least_squares(fun, [math.log(v)], bounds=([math.log(.001)], [math.log(3.)]),
                             max_nfev=1000, ftol=1e-10, xtol=1e-10, gtol=1e-10)
                for v in (.1, .25, .5)]
        buenas = [s for s in sols if s.success and np.isfinite(s.cost)]
        if not buenas:
            raise ValueError("sin ajuste plano convergente")
        sol = min(buenas, key=lambda s: s.cost)
        planas[r.T] = math.exp(float(sol.x[0]))
        costos.append(float(sol.cost))
        exitos.append(bool(sol.success))
    superficies = [ajustar_superficie(rs, rho0=rho, eta0=1., gamma0=.4, peso_mid=peso_mid)
                   for rho in (-.6, 0., .6)]
    buenas = [s for s in superficies if s.info["exito"] and math.isfinite(s.info["costo"])
              and all(s.condiciones().values())]
    if not buenas:
        raise ValueError("sin superficie convergente que cumpla las condiciones")
    superficie = min(buenas, key=lambda s: s.info["costo"])
    return AjusteBandas(planas, superficie, dict(costo_plano=sum(costos),
        costo_ssvi=superficie.info["costo"], convergencia_plana=all(exitos),
        convergencia_ssvi=superficie.info["exito"], condiciones=superficie.condiciones(),
        inicios_por_modelo=3, preferencia=preferencia, peso_mid=peso_mid))


def precios_ajuste(ajuste, rebanada, modelo):
    if modelo == "plano":
        w = ajuste.planas[rebanada.T]**2 * rebanada.T
    elif modelo == "ssvi":
        w = ajuste.superficie.w(np.log(rebanada.K/rebanada.F), rebanada.T)
    else:
        raise ValueError("modelo desconocido")
    return precio_black(rebanada.F, rebanada.K, w, rebanada.D, rebanada.es_call)


def incompatibilidades_paridad(rebanada):
    """Pares C/P cuya banda para C-P excluye D(F-K), con tolerancia 1e-9.

    Cada par disjunto obliga a dejar al menos una cotización fuera de banda para
    cualquier modelo europeo con este forward, aun con una smile perfecta.
    """
    incompatibles, pares = 0, 0
    for K in np.unique(rebanada.K):
        indices = np.where(rebanada.K == K)[0]
        c = indices[rebanada.es_call[indices]]
        p = indices[~rebanada.es_call[indices]]
        if len(c) > 1 or len(p) > 1:
            raise ValueError("par C/P duplicado")
        if len(c) != 1 or len(p) != 1:
            continue
        c, p = int(c[0]), int(p[0])
        teorico = rebanada.D*(rebanada.F-K)
        minimo = rebanada.bid[c]-rebanada.ask[p]
        maximo = rebanada.ask[c]-rebanada.bid[p]
        incompatibles += int(teorico < minimo-1e-9 or teorico > maximo+1e-9)
        pares += 1
    return dict(pares=pares, incompatibles=incompatibles,
                minimo_cotizaciones_fuera=incompatibles)


def valorador_bandas(ajuste, modelo, dinamica="tasa_congelada"):
    """Reprecio bajo hipótesis explícitas; ambas congelan parámetros iniciales.

    tasa_congelada: slice inicial en k futuro, varianza total multiplicada por
    T_restante/T_original. Conserva las cotas de mariposa de cada slice.
    plazo_restante: superficie inicial evaluada en el plazo que queda; puede
    extrapolar antes del primer vencimiento. Ninguna dinámica fue estimada.
    Una IV de strike no se usa como coeficiente de difusión de la PDE.
    """
    if modelo not in ("plano", "ssvi") or dinamica not in ("tasa_congelada", "plazo_restante"):
        raise ValueError("modelo/dinámica desconocidos")
    def valorar(c, spot, e, tasa, q):
        if e.cambio_iv != 0:
            raise ValueError("este contraste no admite shifts aditivos de IV")
        T, restante = c.dte/365, (c.dte-e.dias)/365
        if restante <= 0:
            raise ValueError("el payoff al vencer lo maneja el comparador")
        F = spot*(1+e.retorno_spot)*math.exp((tasa-q)*restante)
        k = math.log(c.strike/F)
        if modelo == "plano":
            w = ajuste.planas[T]**2*restante
        elif dinamica == "plazo_restante":
            w = ajuste.superficie.w(k, restante)
        else:
            th = ajuste.superficie.theta_en(T)
            w = varianza_total_ssvi(k, th*restante/T, ajuste.superficie.rho, ajuste.superficie.phi(th))
        return float(precio_black(F, c.strike, w, math.exp(-tasa*restante), c.es_call))
    return valorar
