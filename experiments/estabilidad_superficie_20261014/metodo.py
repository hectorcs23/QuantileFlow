"""Sensibilidad de entradas y diagnósticos Q en un eje de precio común.

Los cuantiles de modelo extrapolados son diagnósticos separados, no rellenan
los cuantiles identificados del contrato ni se convierten en señales.
"""
import numpy as np
from scipy.optimize import brentq


def perturbar(filas,caso,amplitud=.1):
    if not np.isfinite(amplitud) or not 0<=amplitud<=1:
        raise ValueError('amplitud inválida')
    if not {'bid','ask','tipo','strike','dias','entrenamiento'}.issubset(filas.columns):
        raise ValueError('faltan campos')
    out=filas.copy(deep=True);mask=out.entrenamiento.astype(bool)
    if not mask.any() or not np.isfinite(out[['bid','ask']].to_numpy()).all() or (out.bid<0).any() or (out.ask<=out.bid).any():
        raise ValueError('bandas/training inválidos')
    h=(out.ask-out.bid)/2
    if caso.startswith('paralelo_'):
        signs=np.full(len(out),1. if caso=='paralelo_arriba' else -1.)
        if caso not in ('paralelo_arriba','paralelo_abajo'):raise ValueError('caso desconocido')
    elif caso.startswith('paridad_'):
        signs=np.where(out.tipo.eq('C'),1.,-1.)
        if caso=='paridad_abajo':signs=-signs
        elif caso!='paridad_arriba':raise ValueError('caso desconocido')
    elif caso in ('jitter_17','jitter_29'):
        ordered=out[mask].sort_values(['dias','strike','tipo'])
        rng=np.random.default_rng(int(caso.split('_')[1]))
        from pandas import Series
        signs=Series(rng.uniform(-1,1,len(ordered)),index=ordered.index).reindex(out.index).fillna(0).to_numpy()
    else:raise ValueError('caso desconocido')
    shift=amplitud*np.minimum(h.to_numpy(),out.bid.to_numpy())*signs*mask.to_numpy()
    out['bid']=out.bid+shift;out['ask']=out.ask+shift
    return out,dict(filas_training=int(mask.sum()),filas_capadas=int(((h>filas.bid)&mask).sum()),
        max_movimiento_en_semispread=float(np.max(abs(shift)/h)))


def cdf_comun(superficie,T,x,factor_forward=1.):
    x=np.asarray(x,float)
    if (x<=0).any() or not np.isfinite(x).all() or not np.isfinite(factor_forward) or factor_forward<=0:
        raise ValueError('eje/forward inválido')
    return superficie.cdf(np.log(x/factor_forward),T)


def cuantiles_modelo_diagnostico(superficie,T,niveles,factor_forward=1.):
    """Inversa analítica-numérica del modelo completo, incluida su extrapolación."""
    u=np.asarray(niveles,float)
    if not np.isfinite(u).all() or ((u<=0)|(u>=1)).any():raise ValueError('niveles interiores requeridos')
    if not np.isfinite(factor_forward) or factor_forward<=0:raise ValueError('forward inválido')
    return factor_forward*np.exp([brentq(lambda k:float(superficie.cdf(k,T))-a,-4,4,xtol=1e-12) for a in u])


def cuantiles_discretos(soporte,masas,niveles):
    x=np.asarray(soporte,float);p=np.asarray(masas,float);u=np.asarray(niveles,float)
    if len(x)!=len(p) or np.any(np.diff(x)<=0) or not np.isfinite(p).all() or p.min()<-1e-10 or abs(p.sum()-1)>1e-8:
        raise ValueError('distribución discreta inválida')
    if not np.isfinite(u).all() or ((u<=0)|(u>=1)).any():raise ValueError('niveles interiores requeridos')
    c=np.maximum.accumulate(np.cumsum(p))
    return x[np.searchsorted(c,u,side='left').clip(0,len(x)-1)]


def distancia_cdf_discreta(cdf_continua,soporte,masas,rango):
    """Supremo exacto contra una CDF continua monótona, evaluando ambos lados de átomos.

    Entre átomos la CDF discreta es constante: los extremos están al borde del
    intervalo. Una malla uniforme puede perder completamente esos saltos.
    """
    x=np.asarray(soporte,float);p=np.asarray(masas,float);lo,hi=rango
    if lo>=hi:raise ValueError('rango inválido')
    pts=np.unique(np.r_[lo,hi,x[(x>=lo)&(x<=hi)]])
    f=np.asarray(cdf_continua(pts))
    right=(pts[:,None]>=x)@p;left=(pts[:,None]>x)@p
    left=np.where(pts>lo,left,right)
    return float(max(np.max(abs(right-f)),np.max(abs(left-f))))
