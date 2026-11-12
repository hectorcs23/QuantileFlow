"""Bandas conservadoras del vertical; todas las primas están por unidad de índice."""
from math import isfinite
import pandas as pd


def seleccionar(strikes, forward, ratio, limite):
    if not all(isfinite(x) and x>0 for x in (forward,ratio,limite)):raise ValueError('Ancla inválida')
    valores=[float(x) for x in strikes]
    if any(not isfinite(x) or x<=0 for x in valores):raise ValueError('Strike inválido')
    if not valores:return None
    k=min(valores,key=lambda x:(abs(x-forward*ratio),x))
    return k if abs(k-forward*ratio)<=forward*limite+1e-12 else None


def banda(tipo,baja,alta,D,ancho):
    if not all(isfinite(x) for x in (*baja,*alta,D,ancho)) or D<=0 or ancho<=0:raise ValueError('Entradas inválidas')
    if any(b<0 or a<=b for b,a in (baja,alta)):raise ValueError('Cotización inválida')
    if tipo=='P': return [(alta[0]-baja[1])/(D*ancho),(alta[1]-baja[0])/(D*ancho)]
    if tipo=='C': return [1-(baja[1]-alta[0])/(D*ancho),1-(baja[0]-alta[1])/(D*ancho)]
    raise ValueError('Tipo desconocido')


def cambio(a,b):return [b[0]-a[1],b[1]-a[0]]
def signo(intervalo,tol):
    if intervalo is None:return 'incompatible'
    return 'sube' if intervalo[0]>tol else 'baja' if intervalo[1]<-tol else 'incluye_cero'
def fisica(intervalo):
    l,h=max(0.,intervalo[0]),min(1.,intervalo[1])
    return [l,h] if l<=h else None
def resumen(a,b,tol):
    raw=cambio(a,b); aa,bb=fisica(a),fisica(b)
    valid=None if aa is None or bb is None else cambio(aa,bb)
    return dict(cambio_raw=raw,cambio=valid,signo=signo(valid,tol),punto_medio=sum(raw)/2)
def compatible(a,b,tol):return max(0.,a[0],b[0])<=min(1.,a[1],b[1])+tol


def sincronas(filas,corte,edad,desfase):
    sellos=[f.sello_evento_utc for f in filas]
    if not sellos or any(pd.isna(t) for t in sellos):return False
    edades=[(corte-t).total_seconds() for t in sellos]
    return min(edades)>=0 and max(edades)<=edad and max(edades)-min(edades)<=desfase
