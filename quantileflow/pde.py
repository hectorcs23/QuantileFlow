"""Benchmark europeo de difusión logarítmica, forward y adjunto discretos.

Malla fija de y=log(S/S0), tasas constantes y dividendo continuo. Volatilidad
escalar o espacial estática en esas coordenadas; no es una IV calibrada.
Euler implícito, fronteras reflectantes lejanas y PDF triangular para el payoff.
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


def _operador_log(plazo, tasa, q, volatilidad, nodos, pasos, semiancho):
    """Operador común de valoración y distribución; no duplicar discretizaciones."""
    if not all(math.isfinite(x) for x in (plazo,tasa,q,semiancho)):
        raise ValueError("parámetros no finitos")
    if min(plazo,semiancho) <= 0:
        raise ValueError("plazo y dominio deben ser positivos")
    if (isinstance(nodos,bool) or not isinstance(nodos,int) or nodos < 5 or nodos%2 != 1
            or isinstance(pasos,bool) or not isinstance(pasos,int) or pasos < 1):
        raise ValueError("nodos debe ser impar >=5 y pasos un entero positivo")
    sigma = np.asarray(volatilidad,dtype=float).copy()
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
        vector = b.ndim == 1
        x, flag = dgttrs(*lu,np.asfortranarray(b[:,None] if vector else b),trans="T" if transpuesta else "N")
        if flag != 0:
            raise RuntimeError(f"solución tridiagonal falló: {flag}")
        return x[:,0] if vector else x

    return y, h, dt, sigma, arriba, abajo, aplicar, resolver


def _adjunto_log(historia, terminal, sigma, h, dt, aplicar, resolver):
    """Gradientes sigma nodal y deriva, sin descuento explícito del funcional."""
    dual = terminal.copy()
    grad_sigma, grad_mu = np.zeros(len(sigma)), 0.
    error_adjunto = 0.
    ds_arriba, ds_abajo = sigma/h**2-sigma/(2*h), sigma/h**2+sigma/(2*h)
    # R_k = A m_(k+1) - m_k; contribución = -lambda_k^T A_theta m_(k+1).
    for k in range(len(historia)-2,-1,-1):
        siguiente = resolver(dual,transpuesta=True)
        error_adjunto = max(error_adjunto,float(np.max(np.abs(aplicar(siguiente,True)-dual))))
        diferencias = np.diff(siguiente)
        m = historia[k+1]
        grad_sigma[:-1] += dt*m[:-1]*ds_arriba[:-1]*diferencias
        grad_sigma[1:] -= dt*m[1:]*ds_abajo[1:]*diferencias
        grad_mu += float(dt/(2*h)*np.dot(m[:-1]+m[1:],diferencias))
        dual = siguiente
    return grad_sigma, grad_mu, dual, error_adjunto


def resolver_europea(spot, strike, plazo, tasa, q, volatilidad, es_call=True,
                     nodos=801, pasos=800, semiancho=1.5):
    """Precio europeo, masas Q y adjunto; sigma fija en log-precio relativo.

    Plazo en años y q continuo. Con sigma espacial, la vega paralela corresponde
    a sumar sigma en todos los nodos. Comprobar dominio, malla y tiempo.
    """
    if not all(math.isfinite(x) and x > 0 for x in (spot,strike)):
        raise ValueError("spot y strike deben ser finitos y positivos")
    if not isinstance(es_call,(bool,np.bool_)):
        raise ValueError("es_call debe ser booleano")
    # Importación local: distribucion_pde comparte los helpers de este módulo.
    from .distribucion_pde import resolver_distribucion
    d = resolver_distribucion(spot,plazo,tasa,q,volatilidad,nodos,pasos,semiancho)
    v = d.valor_europeo(strike,es_call)
    error_estado = max(float(np.max(abs(d._aplicar(d._historia[k+1])-d._historia[k])))
                       for k in range(pasos))
    return ResultadoPDE(v.precio,v.delta,v.vega_paralela,v.rho,v.sensibilidad_q,
        d.y,d.pesos.copy(),v.sensibilidad_vol_nodos,d.masa_fronteras,v.error_dualidad,
        d.error_masa_pre_normalizacion,error_estado,v.error_residual_adjunto)
