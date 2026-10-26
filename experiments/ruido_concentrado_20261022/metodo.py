"""Error medio acotado y cap por cotizacion; no selecciona outliers a eliminar."""
import numpy as np
from experiments.distribuciones_ruido_20261022.metodo import Mercado, resolver


class MercadoL1(Mercado):
    def _validar(self, cap, presupuesto=None):
        if not np.isfinite(cap) or cap < 0:
            raise ValueError("Cap invalido")
        if presupuesto is not None and (not np.isfinite(presupuesto) or presupuesto < 0):
            raise ValueError("Presupuesto invalido")

    def _sistema(self, cap, presupuesto, fb, db, cdf=False):
        self._validar(cap, presupuesto)
        ref, rhs = self._referencias(fb, db)
        m, n = self.A.shape
        if cdf:
            # p=w/d, t=1/d, z=e/d. La media z <= presupuesto*t.
            G = np.vstack([
                np.c_[self.A, -np.diag(self.spread), -self.hi],
                np.c_[-self.A, -np.diag(self.spread), self.lo],
                np.c_[np.zeros((m,n)), np.eye(m), -cap*np.ones(m)],
                np.r_[self.x,np.zeros(m+1)][None,:],
                np.r_[-self.x,np.zeros(m+1)][None,:],
                np.r_[np.zeros(n),np.ones(m)/m,-presupuesto][None,:]])
            h = np.r_[np.zeros(3*m),fb[1],-fb[0],0.]
            E = np.r_[np.ones(n),np.zeros(m+1)][None,:]
            b = np.array([1.])
            bounds = [(0.,None)]*(n+m)+[(1/db[1],1/db[0])]
        else:
            G = np.vstack([np.c_[ref,np.zeros((len(rhs),m))],
                           np.c_[self.A,-np.diag(self.spread)],
                           np.c_[-self.A,-np.diag(self.spread)]])
            h = np.r_[rhs,self.hi,-self.lo]
            if presupuesto is not None:
                G = np.vstack([G,np.r_[np.zeros(n),np.ones(m)/m]])
                h = np.r_[h,presupuesto]
            E = b = None
            bounds = [(0.,None)]*n+[(0.,cap)]*m
        return G,h,E,b,bounds

    def desviaciones(self, p, d=1.):
        precios=d*(self.A@p)
        return np.maximum(np.maximum(self.lo-precios,precios-self.hi),0)/self.spread

    def _save(self, tipo, p, d, cap, presupuesto, fb, db, valor, cert, **extra):
        self.testigos.append(dict(tipo=tipo,p=np.asarray(p).tolist(),d=float(d),
            cap=float(cap),presupuesto=None if presupuesto is None else float(presupuesto),
            fb=list(fb),db=list(db),valor=float(valor),certificado=cert,**extra))

    def reparar_l1(self, cap, fb=(1.,1.), db=(1.,1.)):
        n,m=len(self.x),len(self.lo)
        v,cert=resolver(np.r_[np.zeros(n),np.ones(m)/m],
                        *self._sistema(cap,None,fb,db))
        d=sum(v[:n]); p=v[:n]/d
        valor=float(np.mean(v[n:])); actual=float(np.mean(self.desviaciones(p,d)))
        if abs(actual-valor)>1e-6:
            raise RuntimeError("Desviacion real y objetivo L1 discrepan")
        self._save("reparacion_l1",p,d,cap,None,fb,db,valor,cert)
        return valor

    def cdf_l1(self, umbral, cap, presupuesto, fb=(1.,1.), db=(1.,1.), *, discreta=False):
        if not np.any(self.puntos==umbral):
            raise ValueError("Umbral no declarado")
        n,m=len(self.x),len(self.lo)
        sistema=self._sistema(cap,presupuesto,fb,db,cdf=True)
        valores=[]
        for lado,signo in (("inferior",1),("superior",-1)):
            g=((self.x<=umbral).astype(float) if discreta else
               np.clip(((umbral if lado=="inferior" else umbral+self.eps)-self.x)/self.eps,0,1))
            v,cert=resolver(np.r_[signo*g,np.zeros(m+1)],*sistema)
            valor=float(g@v[:n])
            self._save("cdf_discreta_l1" if discreta else "cdf_l1",v[:n],1/v[-1],
                       cap,presupuesto,fb,db,valor,cert,umbral=float(umbral),lado=lado)
            valores.append(valor)
        return dict(inferior=valores[0],superior=valores[1],ancho=valores[1]-valores[0])

    def precio_call_l1(self, strike_ratio, cap, presupuesto, fb=(1.,1.), db=(1.,1.)):
        if not np.any(np.isclose(self.x,strike_ratio,atol=1e-12,rtol=0)):
            raise ValueError("Strike no declarado")
        n,m=len(self.x),len(self.lo)
        sistema=self._sistema(cap,presupuesto,fb,db)
        g=np.maximum(self.x-strike_ratio,0.); valores=[]
        for lado,signo in (("inferior",1),("superior",-1)):
            v,cert=resolver(np.r_[signo*g,np.zeros(m)],*sistema)
            d=sum(v[:n]); valor=float(g@v[:n])
            self._save("call_l1",v[:n]/d,d,cap,presupuesto,fb,db,valor,cert,
                       strike_ratio=float(strike_ratio),lado=lado)
            valores.append(valor)
        return dict(inferior=valores[0],superior=valores[1],ancho=valores[1]-valores[0])


def conflictos_paridad(filas,F,D,cap):
    """Cotas necesarias al F/D fijo, usando pares de strikes distintos."""
    pares=malos=filas_min=0; suma_min=0.
    for K,g in filas.groupby("strike"):
        if set(g.tipo)!={"C","P"}: continue
        if len(g)!=2: raise ValueError("Par duplicado")
        c=g[g.tipo=="C"].iloc[0]; p=g[g.tipo=="P"].iloc[0]
        target=D*(F-K)
        gap=max(0.,float(c.bid-p.ask-target),float(target-c.ask+p.bid))
        pares+=1
        if gap<=1e-7: continue
        malos+=1
        smax,smin=sorted([c.ask-c.bid,p.ask-p.bid],reverse=True)
        first=min(cap,gap/smax); rem=max(0.,gap-first*smax)
        if rem>cap*smin+1e-6: raise ValueError("Cap no cubre paridad")
        suma_min+=first+rem/smin
        filas_min+=1+int(rem>1e-7)
    return dict(pares=pares,incompatibles=malos,filas_modificadas_min=filas_min,
                fraccion_filas_min=filas_min/len(filas),media_error_min=suma_min/len(filas))
