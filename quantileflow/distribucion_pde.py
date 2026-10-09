"""Distribución Q europea: reconstrucción positiva, tangentes y adjuntos.

Sigma estática en y=log(S/S0); spot cambia la escala, sin recalibrar sigma.
Plazo en años, q continuo y número de pasos fijo al derivar el plazo.
No estima probabilidades físicas ni implementa ejercicio americano.
"""
from dataclasses import dataclass
import math

import numpy as np

from .pde import _adjunto_log, _operador_log


@dataclass(frozen=True)
class MedidasDistribucion:
    precios: np.ndarray
    pdf: np.ndarray
    cdf: np.ndarray
    pdf_spot: np.ndarray
    pdf_sigma: np.ndarray
    pdf_plazo: np.ndarray
    cdf_spot: np.ndarray
    cdf_sigma: np.ndarray
    cdf_plazo: np.ndarray
    pdf_spot_diferenciable: np.ndarray


@dataclass(frozen=True)
class CuantilPDE:
    probabilidad: float
    precio: float
    sensibilidad_spot: float
    sensibilidad_sigma: float
    sensibilidad_plazo: float
    densidad_y: float
    condicion_inversa_cdf: float  # d precio / d probabilidad = 1 / pdf(precio)


@dataclass(frozen=True)
class ColaPDE:
    probabilidad: float
    sensibilidad_spot: float
    sensibilidad_sigma: float
    sensibilidad_plazo: float


def _generador(m, arriba, abajo):
    flujo = arriba[:-1]*m[:-1]-abajo[1:]*m[1:]
    out = np.zeros_like(m)
    out[:-1] -= flujo
    out[1:] += flujo
    return out


class DistribucionPDE:
    """Bases triangulares en log-precio: integral exacta uno, PDF no negativa.

    Cada peso m_j multiplica max(1-|y-y_j|/h,0)/h. La CDF es cuadrática
    por tramos; su inversión y las derivadas usan esa misma reconstrucción.
    La derivada spot de la PDF no existe en los vértices: devuelve NaN y
    un indicador. Las de CDF y cuantiles siguen bien definidas si pdf>0.
    """

    def __init__(self, spot, historia, tangentes, operador, plazo):
        self.spot, self.plazo = float(spot), float(plazo)
        self.y, self.h, self.dt, self.sigma, _, _, self._aplicar, self._resolver = operador
        self._historia = historia
        self._normalizacion = float(historia[-1].sum())
        if self._normalizacion <= 0 or not np.isfinite(self._normalizacion):
            raise RuntimeError("masa terminal inválida")
        self.pesos = historia[-1]/self._normalizacion
        self._tangentes = (tangentes-self.pesos[:,None]*tangentes.sum(axis=0))/self._normalizacion
        self.masa_fronteras = float(self.pesos[0]+self.pesos[-1])
        self.error_masa_pre_normalizacion = float(np.max(np.abs(historia.sum(axis=1)-1)))
        self.error_masa_tangentes = float(np.max(np.abs(self._tangentes.sum(axis=0))))
        self._nudos = np.r_[self.y[0]-self.h,self.y,self.y[-1]+self.h]
        self._pdf_y = np.r_[0.,self.pesos/self.h,0.]
        areas = .5*self.h*(self._pdf_y[:-1]+self._pdf_y[1:])
        self._cdf_nudos = np.r_[0.,np.cumsum(areas)]
        for a in (self.y,self.sigma,self.pesos,self._historia,self._tangentes,
                  self._nudos,self._pdf_y,self._cdf_nudos):
            a.setflags(write=False)

    def _pesos_cdf(self, log_precio):
        u = np.clip((log_precio-self.y)/self.h,-1.,1.)
        return np.where(u < 0,.5*(u+1)**2,1-.5*(1-u)**2)

    def evaluar(self, precios):
        """Arrays de PDF/CDF y derivadas a precios fijos, incluso fuera del soporte.

        sigma significa desplazamiento paralelo de sigma(y). pdf_plazo y
        cdf_plazo son por año de plazo restante; por día transcurrido, -valor/365.
        """
        xs = np.atleast_1d(np.asarray(precios,dtype=float))
        if xs.ndim != 1 or len(xs) == 0 or not np.all(np.isfinite(xs)):
            raise ValueError("precios debe ser un vector finito no vacío")
        valores = np.zeros((8,len(xs)))
        diferenciable = np.ones(len(xs),dtype=bool)
        for i,x in enumerate(xs):
            if x <= 0:
                continue
            z = math.log(x)-math.log(self.spot)
            diferenciable[i] = not np.any(np.isclose(z,self._nudos,rtol=0,atol=1e-11))
            if z <= self._nudos[0] or z >= self._nudos[-1]:
                valores[1,i] = float(z >= self._nudos[-1])
                if not diferenciable[i]:
                    valores[2,i] = np.nan
                continue
            pesos_cdf = self._pesos_cdf(z)
            py = float(np.interp(z,self._nudos,self._pdf_y))
            s = np.searchsorted(self._nudos,z,side="right")-1
            pendiente = (self._pdf_y[s+1]-self._pdf_y[s])/self.h
            dy = [float(np.interp(z,self.y,self._tangentes[:,k]/self.h,left=0,right=0)) for k in (0,1)]
            # En las dos celdas exteriores, la base triangular decrece linealmente a cero.
            if z < self.y[0]:
                dy = [float(self._tangentes[0,k]/self.h*(z-self._nudos[0])/self.h) for k in (0,1)]
            elif z > self.y[-1]:
                dy = [float(self._tangentes[-1,k]/self.h*(self._nudos[-1]-z)/self.h) for k in (0,1)]
            ds_cdf, dt_cdf = pesos_cdf@self._tangentes
            valores[:,i] = (py/x,pesos_cdf@self.pesos,-pendiente/(x*self.spot),
                             dy[0]/x,dy[1]/x,-py/self.spot,ds_cdf,dt_cdf)
            if not diferenciable[i]:
                valores[2,i] = np.nan
        return MedidasDistribucion(xs.copy(),*valores,diferenciable)

    def cuantil(self, probabilidad, densidad_minima=1e-8):
        """Inversión de CDF y derivada implícita; rechaza colas mal condicionadas."""
        if not (math.isfinite(probabilidad) and 0 < probabilidad < 1
                and math.isfinite(densidad_minima) and densidad_minima > 0):
            raise ValueError("probabilidad debe estar en (0,1) y densidad mínima ser positiva")
        i = int(np.searchsorted(self._cdf_nudos,probabilidad,side="left")-1)
        i = max(0,min(i,len(self._nudos)-2))
        area = float(probabilidad-self._cdf_nudos[i])
        a = self._pdf_y[i]
        b = (self._pdf_y[i+1]-a)/self.h
        raiz = math.sqrt(max(0.,a*a+2*b*area))
        avance = 0. if area == 0 else 2*area/(a+raiz)
        z = float(self._nudos[i]+np.clip(avance,0,self.h))
        py = float(np.interp(z,self._nudos,self._pdf_y))
        if py < densidad_minima:
            raise ValueError("cuantil mal condicionado: densidad demasiado pequeña; ampliar/verificar dominio")
        precio = self.spot*math.exp(z)
        fs, ft = self._pesos_cdf(z)@self._tangentes
        return CuantilPDE(float(probabilidad),precio,precio/self.spot,-precio*fs/py,-precio*ft/py,py,precio/py)

    def probabilidad_cola(self, precio, superior=True):
        """P_Q(S_T>precio) o P_Q(S_T<=precio), con umbral monetario fijo."""
        if not isinstance(superior,(bool,np.bool_)):
            raise ValueError("superior debe ser booleano")
        m = self.evaluar([precio])
        signo = -1 if superior else 1
        return ColaPDE(float(1-m.cdf[0] if superior else m.cdf[0]),
            float(signo*m.cdf_spot[0]),float(signo*m.cdf_sigma[0]),float(signo*m.cdf_plazo[0]))

    def probabilidad_retorno(self, retorno, superior=True):
        """Umbral S0*(1+retorno): la derivada spot total es cero en este modelo.

        Se mueve el umbral junto al spot; no confundir con un strike monetario fijo.
        """
        if not math.isfinite(retorno) or retorno <= -1:
            raise ValueError("retorno debe ser finito y mayor que -1")
        c = self.probabilidad_cola(self.spot*(1+retorno),superior)
        return ColaPDE(c.probabilidad,0.,c.sensibilidad_sigma,c.sensibilidad_plazo)

    def gradiente_vol_cdf(self, precio):
        """Un adjunto para d P_Q(S_T<=precio) / d sigma_j, todos los nodos."""
        if not math.isfinite(precio):
            raise ValueError("precio debe ser finito")
        if precio <= 0:
            return np.zeros_like(self.pesos)
        z = math.log(precio)-math.log(self.spot)
        if z <= self._nudos[0] or z >= self._nudos[-1]:
            return np.zeros_like(self.pesos)
        w = self._pesos_cdf(z)
        # Derivar también la normalización terminal, no solo la proyección.
        terminal = (w-float(w@self.pesos))/self._normalizacion
        grad,_,_,_ = _adjunto_log(self._historia,terminal,self.sigma,self.h,self.dt,
                                 self._aplicar,self._resolver)
        return grad

    def gradiente_vol_cuantil(self, probabilidad, densidad_minima=1e-8):
        c = self.cuantil(probabilidad,densidad_minima)
        return -c.precio/c.densidad_y*self.gradiente_vol_cdf(c.precio)


def resolver_distribucion(spot, plazo, tasa, q, volatilidad,
                          nodos=801, pasos=800, semiancho=1.5):
    """Forward y dos tangentes exactas del sistema discreto: sigma paralela y T.

    A m[k+1]=m[k]; A dm[k+1]=dm[k]+dt G_sigma m[k+1] para sigma.
    Para T el término fuente es G m[k+1]/pasos, con G independiente de T.
    La derivada spot se obtiene del cambio de coordenadas en la reconstrucción.
    """
    if not math.isfinite(spot) or spot <= 0:
        raise ValueError("spot debe ser finito y positivo")
    op = _operador_log(plazo,tasa,q,volatilidad,nodos,pasos,semiancho)
    _,h,dt,sigma,arriba,abajo,_,resolver = op
    ds_arriba,ds_abajo = sigma/h**2-sigma/(2*h),sigma/h**2+sigma/(2*h)
    historia = np.zeros((pasos+1,nodos))
    historia[0,nodos//2] = 1.
    tangentes = np.zeros((nodos,2))
    for k in range(pasos):
        m = resolver(historia[k])
        historia[k+1] = m
        fuentes = np.column_stack((dt*_generador(m,ds_arriba,ds_abajo),
                                   _generador(m,arriba,abajo)/pasos))
        tangentes = resolver(tangentes+fuentes)
    if not np.all(np.isfinite(historia)) or not np.all(np.isfinite(tangentes)):
        raise RuntimeError("estado o sensibilidades no finitos")
    if float(historia.min()) < -1e-12:
        raise RuntimeError("distribución perdió positividad")
    return DistribucionPDE(spot,historia,tangentes,op,plazo)
