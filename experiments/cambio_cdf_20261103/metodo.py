"""Cambio de CDF en un mismo precio absoluto, con dos conjuntos marginales."""
import numpy as np
from scipy.linalg import block_diag
from experiments.distribuciones_ruido_20261022.metodo import resolver


def coordenadas(ratios, F0, Ft, epsilon):
    ratios = np.asarray(ratios, dtype=float)
    if (ratios.ndim != 1 or not ratios.size or not np.isfinite(ratios).all()
            or min(ratios) <= 0 or np.any(np.diff(ratios) <= 0)
            or not np.isfinite([F0,Ft,epsilon]).all() or min(F0,Ft,epsilon) <= 0):
        raise ValueError("Coordenadas inválidas")
    return (ratios*F0)/Ft, epsilon*F0/Ft


def cambio(a, b, tol):
    """a y b: [cota exterior inferior, interior inferior, interior superior, exterior superior]."""
    a,b=np.asarray(a,float),np.asarray(b,float)
    if not np.isfinite(tol) or tol <= 0: raise ValueError("Tolerancia inválida")
    for x in (a,b):
        if (x.shape!=(4,) or not np.isfinite(x).all() or min(x)<-tol or max(x)>1+tol
                or np.any(np.diff(x)<-tol)): raise ValueError("Banda marginal inválida")
    lo,li,ui,hi = b-a[::-1]
    if lo>tol: estado="aumento"
    elif hi<-tol: estado="descenso"
    elif li<=0<=ui: estado="cero_alcanzable"
    else: estado="indeterminado"
    return dict(inferior=float(lo),interior_inferior=float(li),interior_superior=float(ui),
                superior=float(hi),estado=estado)


def conjunto(ms,caps,budgets):
    """Testigos en los que se minimiza la mayor diferencia en los cinco umbrales.

    La malla da un certificado de existencia (si se encuentra). Un óptimo positivo
    no certifica imposibilidad en soporte continuo.
    """
    a,b=ms
    if len(a.puntos)!=len(b.puntos) or not np.allclose(a.puntos*a.F,b.puntos*b.F,atol=1e-9,rtol=1e-13):
        raise ValueError("Los umbrales absolutos no coinciden")
    parts=[m._sistema(cap,budget,(1.,1.),(1.,1.)) for m,cap,budget in zip(ms,caps,budgets,strict=True)]
    G=block_diag(parts[0][0],parts[1][0])
    H=[np.c_[(m.x[None,:]<=m.puntos[:,None]).astype(float),np.zeros((len(m.puntos),len(m.lo)))] for m in ms]
    diff=np.c_[-H[0],H[1]]
    M=np.vstack([np.c_[G,np.zeros(len(G))],np.c_[diff,-np.ones(len(diff))],
                 np.c_[-diff,-np.ones(len(diff))]])
    n0=H[0].shape[1]
    v,cert=resolver(np.r_[np.zeros(G.shape[1]),1.],M,
        np.r_[parts[0][1],parts[1][1],np.zeros(2*len(diff))],
        bounds=parts[0][4]+parts[1][4]+[(0.,1.)])
    ps=[v[:len(a.x)],v[n0:n0+len(b.x)]]
    cdfs=[(m.x[None,:]<=m.puntos[:,None])@p for m,p in zip(ms,ps)]
    achieved=float(max(abs(cdfs[1]-cdfs[0])))
    if abs(achieved-v[-1])>1e-7: raise RuntimeError("Objetivo conjunto no reconstruido")
    return dict(gamma=float(v[-1]),diferencia_max=achieved,certificado=cert,
                masas=[p.tolist() for p in ps],cdf=[c.tolist() for c in cdfs])
