"""Medidas neutrales al riesgo admisibles bajo error acotado de cotización.

S/F_ref tiene soporte [0,L]. Los payoffs y rampas de CDF son lineales por
tramos. Al incluir todos sus quiebres como estados, reemplazar cualquier masa
interior por una mezcla de los extremos conserva payoffs, masa y media.
El LP es exacto para esas funciones continuas y ese soporte; no elige una
malla regular, una densidad suave ni una dinámica.

La CDF discontinua se encierra con rampas inferior/superior de ancho epsilon.
Sus extremos son cotas exteriores, no percentiles de confianza.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog


def resolver(c, G, h, E=None, b=None, bounds=None):
    c, G, h = np.asarray(c), np.asarray(G), np.asarray(h)
    bounds = [(0., None)]*len(c) if bounds is None else bounds
    sol = linprog(c, A_ub=G, b_ub=h, A_eq=E, b_eq=b, bounds=bounds,
                  method="highs", options={
                      "primal_feasibility_tolerance": 1e-9,
                      "dual_feasibility_tolerance": 1e-9, "time_limit": 30.})
    if not sol.success:
        raise RuntimeError(f"LP sin óptimo: {sol.message}")
    primal = max(0., float(np.max(G@sol.x-h)))
    dual = float(h@sol.ineqlin.marginals)
    station = c-G.T@sol.ineqlin.marginals-sol.lower.marginals-sol.upper.marginals
    if E is not None:
        primal = max(primal, float(np.max(np.abs(E@sol.x-b))))
        dual += float(b@sol.eqlin.marginals)
        station -= E.T@sol.eqlin.marginals
    for j, (a, z) in enumerate(bounds):
        if a is not None:
            primal = max(primal, a-sol.x[j])
            dual += a*sol.lower.marginals[j]
        if z is not None:
            primal = max(primal, sol.x[j]-z)
            dual += z*sol.upper.marginals[j]
    dual_error = max(0., float(np.max(sol.ineqlin.marginals)),
                     float(np.max(-sol.lower.marginals)), float(np.max(sol.upper.marginals)),
                     float(np.max(np.abs(station))))
    gap = abs(float(sol.fun)-dual)
    if primal > 1e-8 or dual_error > 1e-7 or gap > 1e-6*max(1, abs(sol.fun)):
        raise RuntimeError(f"Certificado numérico inválido: {primal=}, {dual_error=}, {gap=}")
    return sol.x, {"primal": float(primal), "dual": dual_error, "gap": gap}


class Mercado:
    def __init__(self, filas, forward, descuento, *, soporte=2., epsilon=.0025,
                 puntos=(.94,.97,1.,1.03,1.06), extras=()):
        if (not np.isfinite([forward, descuento, soporte, epsilon]).all()
                or min(forward, descuento, epsilon) <= 0 or soporte <= 1):
            raise ValueError("Referencias, soporte o epsilon inválidos")
        if len(filas) == 0 or filas.duplicated(["strike","tipo"]).any():
            raise ValueError("Filas vacías o duplicadas")
        K, bid, ask = [filas[c].to_numpy(float) for c in ("strike","bid","ask")]
        if (not np.isfinite(np.r_[K,bid,ask]).all() or np.any(K<=0)
                or np.any(bid<0) or np.any(ask<=bid) or not filas.tipo.isin(["C","P"]).all()):
            raise ValueError("Cotizaciones inválidas")
        puntos, extras = np.asarray(puntos, float), np.asarray(extras, float)
        if (not np.isfinite(np.r_[puntos, extras]).all() or len(puntos)==0
                or np.any(puntos-epsilon<=0) or np.any(puntos+epsilon>=soporte)
                or np.any(extras<=0) or np.any(extras>=soporte) or np.max(K/forward)>=soporte):
            raise ValueError("Quiebres fuera del soporte")
        self.F, self.D, self.L, self.eps = forward, descuento, soporte, epsilon
        self.puntos = puntos
        self.x = np.unique(np.r_[0., K/forward, puntos-epsilon, puntos,
                                 puntos+epsilon, extras, soporte])
        self.A = np.maximum(np.where(filas.tipo.to_numpy()[:,None]=="C",
            self.x[None,:]-K[:,None]/forward, K[:,None]/forward-self.x[None,:]), 0.)
        self.lo, self.hi = bid/(descuento*forward), ask/(descuento*forward)
        self.spread = self.hi-self.lo
        self.testigos = []

    def _referencias(self, fb, db):
        if (len(fb)!=2 or len(db)!=2 or not np.isfinite([*fb,*db]).all()
                or not 0<fb[0]<=fb[1]<self.L or not 0<db[0]<=db[1]):
            raise ValueError("Bandas de referencias inválidas")
        ones = np.ones(len(self.x))
        G = np.array([ones, -ones, self.x-fb[1]*ones, fb[0]*ones-self.x])
        h = np.array([db[1], -db[0], 0., 0.])
        return G, h

    def reparar(self, fb=(1.,1.), db=(1.,1.)):
        # w=(D/D_ref)*p; rho amplía cada bid/ask en spreads completos.
        G, h = self._referencias(fb, db)
        G = np.vstack([np.c_[G,np.zeros(len(h))], np.c_[self.A,-self.spread],
                       np.c_[-self.A,-self.spread]])
        h = np.r_[h,self.hi,-self.lo]
        c = np.r_[np.zeros(len(self.x)),1.]
        v, cert = resolver(c,G,h)
        rho = max(0., float(v[-1]))
        self._guardar("reparacion", v[:-1]/sum(v[:-1]), sum(v[:-1]),
                      rho, fb, db, rho, cert)
        return rho

    def _guardar(self, tipo, p, d, rho, fb, db, valor, cert, **extra):
        self.testigos.append(dict(tipo=tipo, p=np.asarray(p).tolist(), d=float(d),
            rho=float(rho), fb=list(fb), db=list(db), valor=float(valor),
            certificado=cert, **extra))

    def cdf(self, umbral, rho, fb=(1.,1.), db=(1.,1.), *, discreta=False):
        self._referencias(fb, db)
        if not np.isfinite(rho) or rho<0 or not np.any(self.puntos==umbral):
            raise ValueError("Rho o umbral no declarado")
        # Charnes-Cooper: p=w/sum(w), t=1/sum(w); las bandas se multiplican por t.
        lo, hi = self.lo-rho*self.spread, self.hi+rho*self.spread
        G = np.vstack([np.c_[self.A,-hi], np.c_[-self.A,lo],
                       np.r_[self.x,0.][None,:], np.r_[-self.x,0.][None,:]])
        h = np.r_[np.zeros(2*len(lo)),fb[1],-fb[0]]
        E = np.r_[np.ones(len(self.x)),0.][None,:]
        b = np.array([1.])
        bounds = [(0.,None)]*len(self.x)+[(1/db[1],1/db[0])]
        valores = []
        for lado in ("inferior","superior"):
            g = ((self.x<=umbral).astype(float) if discreta else
                 np.clip(((umbral if lado=="inferior" else umbral+self.eps)-self.x)/self.eps,0.,1.))
            signo = 1 if lado=="inferior" else -1
            v, cert = resolver(np.r_[signo*g,0.],G,h,E,b,bounds)
            valor = float(g@v[:-1])
            if not -1e-8<=valor<=1+1e-8:
                raise RuntimeError("Masa de CDF inválida")
            valor = float(np.clip(valor,0,1))
            self._guardar("cdf_discreta" if discreta else "cdf",v[:-1],1/v[-1],rho,fb,db,valor,cert,
                          umbral=float(umbral),lado=lado)
            valores.append(valor)
        if valores[0]>valores[1]+1e-8:
            raise RuntimeError("Intervalo invertido")
        return {"inferior": valores[0], "superior": valores[1],
                "ancho": valores[1]-valores[0]}

    def precio_call(self, strike_ratio, rho, fb=(1.,1.), db=(1.,1.)):
        if not np.isfinite(rho) or rho<0 or not np.any(np.isclose(self.x,strike_ratio,atol=1e-12,rtol=0)):
            raise ValueError("Rho o strike no declarado")
        G, h = self._referencias(fb,db)
        G = np.vstack([G,self.A,-self.A])
        h = np.r_[h,self.hi+rho*self.spread,-self.lo+rho*self.spread]
        payoff = np.maximum(self.x-strike_ratio,0.)
        values = []
        for lado,signo in (("inferior",1),("superior",-1)):
            v,cert = resolver(signo*payoff,G,h)
            valor = float(payoff@v)  # normalizado por D_ref*F_ref
            self._guardar("call",v/sum(v),sum(v),rho,fb,db,valor,cert,
                          strike_ratio=float(strike_ratio),lado=lado)
            values.append(valor)
        return {"inferior":values[0],"superior":values[1],"ancho":values[1]-values[0]}

    def evidencia(self):
        return {"x":self.x.tolist(),"F":float(self.F),"D":float(self.D),
                "soporte":self.L,"epsilon":self.eps,"testigos":self.testigos}
