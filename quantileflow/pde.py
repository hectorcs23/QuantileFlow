"""Benchmark europeo de difusión logarítmica, forward y adjunto discretos.

Malla fija de y=log(S/S0), tasas constantes y dividendo continuo. Volatilidad
escalar o espacial estática en esas coordenadas; no es una IV calibrada.
Euler implícito, fronteras reflectantes lejanas y payoff promediado por celda.
El delta mantiene fija esa volatilidad en coordenadas relativas al spot.
No implementa ejercicio americano, dividendos en efectivo ni predicción.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.linalg.lapack import dgttrf, dgttrs


@dataclass(frozen=True)
class ResultadoPDE:
    precio: float
    delta: float
    vega_paralela: float  # por incremento absoluto de volatilidad, no por punto porcentual
    rho: float  # por incremento absoluto de tasa
    sensibilidad_q: float
    log_moneyness: np.ndarray
    masas: np.ndarray
    sensibilidad_vol_nodos: np.ndarray
    masa_fronteras: float
    error_dualidad: float
    error_masa: float
    error_residual_estado: float
    error_residual_adjunto: float


def _payoff_celdas(y, h, spot, strike, es_call):
    """Promedio uniforme en log-precio; derivada analítica con límites móviles."""
    a, b = y-h/2, y+h/2
    log_strike = math.log(strike/spot)
    # La identidad put = call - S + K vale también para el promedio por celda.
    inicio = np.clip(log_strike, a, b)
    largo = b-inicio
    integral_exp = np.exp(inicio)*np.expm1(largo)
    call = (spot*integral_exp-strike*largo)/h
    delta_call = integral_exp/h
    if es_call:
        return call, delta_call
    promedio_exp = np.exp(a)*np.expm1(h)/h
    return call-spot*promedio_exp+strike, delta_call-promedio_exp


def resolver_europea(spot, strike, plazo, tasa, q, volatilidad, es_call=True,
                     nodos=801, pasos=800, semiancho=1.5):
    """Resuelve precio, masas terminales Q y gradiente espacial por un adjunto.

    ``plazo`` en años, ``q`` rendimiento continuo. Para sigma escalar,
    ``vega_paralela`` converge a vega BS. Para un vector de longitud ``nodos``
    es la sensibilidad a sumar el mismo incremento de sigma en todos los nodos.
    El dominio reflectante conserva masa pero puede sesgar precios si es corto:
    inspeccionar fronteras y comprobar refinamiento de dominio/malla/tiempo.
    """
    if not all(math.isfinite(x) for x in (spot,strike,plazo,tasa,q,semiancho)):
        raise ValueError("parámetros no finitos")
    if min(spot,strike,plazo,semiancho) <= 0:
        raise ValueError("spot, strike, plazo y dominio deben ser positivos")
    if (isinstance(nodos,bool) or not isinstance(nodos,int) or nodos < 5 or nodos%2 != 1
            or isinstance(pasos,bool) or not isinstance(pasos,int) or pasos < 1):
        raise ValueError("nodos debe ser impar >=5 y pasos un entero positivo")
    if not isinstance(es_call,(bool,np.bool_)):
        raise ValueError("es_call debe ser booleano")
    sigma = np.asarray(volatilidad,dtype=float)
    if sigma.ndim == 0:
        sigma = np.full(nodos,float(sigma))
    elif sigma.shape != (nodos,):
        raise ValueError("volatilidad espacial debe tener un valor por nodo")
    if not np.all(np.isfinite(sigma)) or np.any(sigma <= 0):
        raise ValueError("volatilidad debe ser finita y positiva")
    y = np.linspace(-semiancho,semiancho,nodos)
    h, dt = y[1]-y[0], plazo/pasos
    mu, difusion = tasa-q-sigma**2/2, sigma**2/2
    arriba, abajo = difusion/h**2+mu/(2*h), difusion/h**2-mu/(2*h)
    if np.any(arriba < 0) or np.any(abajo < 0):
        raise ValueError("malla demasiado gruesa para conservar positividad; aumentar nodos")
    arriba[-1], abajo[0] = 0., 0.  # no hay flujo exterior
    diagonal = 1+dt*(arriba+abajo)
    inferior, superior = -dt*arriba[:-1], -dt*abajo[1:]
    *lu, info = dgttrf(inferior.copy(),diagonal.copy(),superior.copy())
    if info != 0:
        raise RuntimeError(f"factorización tridiagonal falló: {info}")

    def aplicar(v, transpuesta=False):
        out = diagonal*v
        if transpuesta:
            out[:-1] += inferior*v[1:]
            out[1:] += superior*v[:-1]
        else:
            out[1:] += inferior*v[:-1]
            out[:-1] += superior*v[1:]
        return out

    def resolver(b, transpuesta=False):
        x, flag = dgttrs(*lu,np.asfortranarray(b[:,None]),trans="T" if transpuesta else "N")
        if flag != 0:
            raise RuntimeError(f"solución tridiagonal falló: {flag}")
        return x[:,0]

    historia = np.empty((pasos+1,nodos))
    historia[0] = 0.
    historia[0,nodos//2] = 1.
    error_estado, error_masa = 0., 0.
    for k in range(pasos):
        historia[k+1] = resolver(historia[k])
        error_estado = max(error_estado,float(np.max(np.abs(aplicar(historia[k+1])-historia[k]))))
        error_masa = max(error_masa,abs(float(historia[k+1].sum())-1))
    masas = historia[-1]
    if float(np.min(masas)) < -1e-12:
        raise RuntimeError("el estado perdió positividad")
    payoff, derivada_payoff = _payoff_celdas(y,h,spot,strike,es_call)
    descuento = math.exp(-tasa*plazo)
    precio = float(descuento*(payoff@masas))
    delta = float(descuento*(derivada_payoff@masas))
    dual = descuento*payoff
    grad_sigma, grad_mu = np.zeros(nodos), 0.
    error_adjunto = 0.
    ds_arriba, ds_abajo = sigma/h**2-sigma/(2*h), sigma/h**2+sigma/(2*h)
    # R_k = A m_(k+1) - m_k. Con el adjunto positivo de J, la contribución
    # es -lambda_k^T A_theta m_(k+1) = dt lambda_k^T G_theta m_(k+1).
    for k in range(pasos-1,-1,-1):
        siguiente = resolver(dual,transpuesta=True)  # A^T lambda_k = lambda_(k+1)
        error_adjunto = max(error_adjunto,float(np.max(np.abs(aplicar(siguiente,True)-dual))))
        # El multiplicador de R_k es lambda_k: A^T lambda_k = lambda_(k+1).
        diferencias = np.diff(siguiente)
        m = historia[k+1]
        grad_sigma[:-1] += dt*m[:-1]*ds_arriba[:-1]*diferencias
        grad_sigma[1:] -= dt*m[1:]*ds_abajo[1:]*diferencias
        grad_mu += float(dt/(2*h)*np.dot(m[:-1]+m[1:],diferencias))
        dual = siguiente
    dualidad = abs(precio-float(dual[nodos//2]))
    return ResultadoPDE(precio,delta,float(grad_sigma.sum()),grad_mu-plazo*precio,-grad_mu,
                        y,masas.copy(),grad_sigma,float(masas[0]+masas[-1]),dualidad,error_masa,
                        error_estado,error_adjunto)
