"""Bandas de forward implícitas en pares call/put europeos completos."""
import numpy as np
from experiments.skew_bandas_20261010.control_forward import maximo_solapamiento


def bandas_paridad(filas, descuento):
    if not np.isfinite(descuento) or descuento <= 0:
        raise ValueError('descuento positivo requerido')
    if filas.duplicated(['strike','tipo']).any():
        raise ValueError('lado duplicado por strike')
    if not filas.tipo.isin(['C','P']).all(): raise ValueError('lado desconocido')
    if not np.isfinite(filas[['strike','bid','ask']]).all().all():
        raise ValueError('datos no finitos')
    if (filas.strike<=0).any() or (filas.bid<0).any() or (filas.ask<=filas.bid).any():
        raise ValueError('bandas inválidas')
    bands=[]
    for strike,g in filas.groupby('strike',sort=True):
        if len(g)!=2:continue
        call=g[g.tipo.eq('C')].iloc[0];put=g[g.tipo.eq('P')].iloc[0]
        bands.append([strike+(call.bid-put.ask)/descuento,strike+(call.ask-put.bid)/descuento])
    return np.asarray(bands,float).reshape(-1,2)


def diagnostico(filas, descuento, forward):
    if not np.isfinite(forward) or forward<=0:raise ValueError('forward positivo requerido')
    a=bandas_paridad(filas,descuento)
    bad=int(((forward<a[:,0]-1e-9)|(forward>a[:,1]+1e-9)).sum())
    return dict(pares=len(a),incompatibles=bad,minimo_incompatibles_F_libre=len(a)-maximo_solapamiento(a))
