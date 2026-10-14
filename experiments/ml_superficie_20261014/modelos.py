"""Red pequeña de corrección SSVI y distribución convexa con restricciones exactas.

La red puede fallar la condición g; una penalización no es un certificado.
El convexo tiene átomos, no una PDF ordinaria. No se usa IV como difusión local.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import least_squares, brentq
from scipy.special import softmax
from scipy import sparse
import clarabel
from quantileflow.opciones import precio_black
from quantileflow.superficies import funcion_g, densidad_logmoneyness
from quantileflow.ajuste_bandas import _validar


@dataclass
class CorreccionRed:
    base: object
    pesos: np.ndarray

    def delta(self,k):
        p=self.pesos;a,b,c,d=p[:4],p[4:8],p[8:12],p[12]
        h=np.tanh(np.asarray(k)[...,None]/.03*a+b)
        h1=(1-h*h)*a/.03
        h2=-2*h*(1-h*h)*(a/.03)**2
        u=h@c+d;u1=h1@c;u2=h2@c;t=np.tanh(u)
        return .25*t,.25*(1-t*t)*u1,.25*(1-t*t)*(u2-2*t*u1*u1)

    def derivadas(self,k,T):
        w,w1,w2=self.base.derivadas(k,T);d,d1,d2=self.delta(k);e=np.exp(d)
        return e*w,e*(w1+w*d1),e*(w2+2*w1*d1+w*(d2+d1*d1))

    def w(self,k,T):return self.derivadas(k,T)[0]

    def densidad(self,k,T):return densidad_logmoneyness(k,*self.derivadas(k,T))

    def precios(self,r):return precio_black(r.F,r.K,self.w(np.log(r.K/r.F),r.T),r.D,r.es_call)

    def control(self):
        k=np.unique(np.r_[np.linspace(-2,2,801),np.linspace(-.15,.15,601)])
        ts=np.unique(np.r_[self.base.tiempos,np.linspace(self.base.tiempos[0],self.base.tiempos[-1],17)])
        gmin=min(float(funcion_g(*self.derivadas(k,t),k).min()) for t in ts)
        # Limiting wing slopes of SSVI, multiplied by limiting NN correction.
        th=self.base.thetas
        a,b,c,d=self.pesos[:4],self.pesos[4:8],self.pesos[8:12],self.pesos[12]
        dp=np.array([.25*np.tanh(np.where(a==0,np.tanh(b),direction*np.sign(a))@c+d) for direction in (-1,1)])
        phi=self.base.phi(th)
        slopes=np.r_[th*phi*(1-self.base.rho)/2*np.exp(dp[0]),th*phi*(1+self.base.rho)/2*np.exp(dp[1])]
        return dict(g_min_malla=gmin,ala_max=float(slopes.max()),
            pasa_malla_y_alas=bool(gmin>=-1e-8 and slopes.max()<2),certificado_global=False,
            calendario_preservado_por_factor_independiente_T=True)


def ajustar_red(rs,base,proto):
    _validar(rs,.5,proto['peso_mid'])
    n=sum(len(r.K) for r in rs)
    kgrid=np.unique(np.r_[np.linspace(-.15,.15,241),np.linspace(-2,2,81)])
    candidatos=[]
    referencia=np.r_[[-1.5,-.5,.5,1.5],np.zeros(9)]
    for seed in proto['semillas']:
        rng=np.random.default_rng(seed)
        z=np.r_[[-1.5,-.5,.5,1.5],rng.normal(0,.15,4),rng.normal(0,.03,4),0.]
        def fun(p):
            red=CorreccionRed(base,p);partes=[]
            for r in rs:
                price=red.precios(r);s=r.medio_spread
                band=price-np.clip(price,r.bid,r.ask)
                partes.extend([band/s/np.sqrt(n),np.sqrt(proto['peso_mid']/n)*(price-r.mid)/s])
            gs=np.concatenate([funcion_g(*red.derivadas(kgrid,r.T),kgrid) for r in rs])
            partes.append(np.sqrt(proto['penalizacion_g']/len(gs))*np.minimum(gs,0))
            # Same regularization reference for all starts; zero output is the base SSVI.
            partes.append(np.sqrt(proto['regularizacion_red'])*(p-referencia))
            return np.concatenate(partes)
        sol=least_squares(fun,z,bounds=(-3*np.ones(13),3*np.ones(13)),max_nfev=proto['max_nfev_red'],ftol=1e-8,xtol=1e-8,gtol=1e-8)
        red=CorreccionRed(base,sol.x);check=red.control()
        candidatos.append((red,dict(semilla=seed,costo=float(2*sol.cost),convergencia=bool(sol.success),nfev=sol.nfev,**check)))
    # Select only on training loss, then report (do not hide) failed coherence.
    convergentes=[x for x in candidatos if x[1]['convergencia']]
    elegido=min(convergentes or candidatos,key=lambda x:x[1]['costo'])
    return elegido[0],dict(elegido=elegido[1],inicios=[x[1] for x in candidatos])


@dataclass
class DistribucionConvexa:
    tiempos: np.ndarray
    soporte: np.ndarray
    masas: np.ndarray

    def precios(self,r):
        idx=np.flatnonzero(np.isclose(self.tiempos,r.T,rtol=0,atol=1e-12))
        if len(idx)!=1:raise ValueError('solo vencimientos observados')
        x=r.K/r.F
        pay=np.where(r.es_call[:,None],np.maximum(self.soporte-x[:,None],0),np.maximum(x[:,None]-self.soporte,0))
        return r.D*r.F*(pay@self.masas[idx[0]])

    def control(self):
        calls=np.maximum(self.soporte[None,:]-self.soporte[:,None],0)@self.masas.T
        cal=float(np.diff(calls,axis=1).min()) if len(self.tiempos)>1 else 0.
        mass=float(abs(self.masas.sum(axis=1)-1).max())
        mean=float(abs(self.masas@self.soporte-1).max())
        pmin=float(self.masas.min())
        return dict(error_masa=mass,error_media=mean,masa_minima=pmin,calendario_minimo=cal,
            pasa_restricciones=bool(max(mass,mean)<1e-8 and pmin>=-1e-10 and cal>=-1e-8),
            naturaleza='distribución discreta con átomos; calendario global en strike normalizado sobre soporte común')


def ajustar_convexo(rs,proto):
    rs=sorted(rs,key=lambda r:r.T);nt=len(rs)
    _validar(rs,.5,proto['peso_mid'])
    k=np.r_[np.linspace(-.30,-.06,11)[:-1],np.linspace(-.06,.06,61),np.linspace(.06,.30,11)[1:]]
    x=np.exp(k);m=len(x)
    # Positive normalized prior, exponentially tilted to impose mean exactly one.
    logp=-.5*((k+.035**2/2)/.035)**2+np.log(np.gradient(k))
    lam=brentq(lambda z:softmax(logp+z*(x-1))@x-1,-100,100)
    prior=softmax(logp+lam*(x-1));z0=np.tile(prior,nt)
    matrices=[];lows=[];highs=[];mids=[];scales=[]
    for j,r in enumerate(rs):
        ratio=r.K/r.F
        pay=np.where(r.es_call[:,None],np.maximum(x-ratio[:,None],0),np.maximum(ratio[:,None]-x,0))*r.D*r.F
        block=np.zeros((len(r.K),m*nt));block[:,j*m:(j+1)*m]=pay
        matrices.append(block);lows.extend(r.bid);highs.extend(r.ask);mids.extend(r.mid);scales.extend(r.medio_spread)
    A=np.vstack(matrices);lo=np.array(lows);hi=np.array(highs);mid=np.array(mids);s=np.array(scales);n=len(lo)
    def objective(z):
        p=A@z;out=p-np.clip(p,lo,hi);res=p-mid
        val=np.mean((out/s)**2+proto['peso_mid']*(res/s)**2)+proto['regularizacion_convexo']*np.sum((z-z0)**2)
        grad=2*A.T@((out+proto['peso_mid']*res)/s**2)/n+2*proto['regularizacion_convexo']*(z-z0)
        return val*1e-4,grad*1e-4
    E=np.zeros((2*nt,m*nt))
    for j in range(nt):E[2*j,j*m:(j+1)*m]=1;E[2*j+1,j*m:(j+1)*m]=x
    B=np.maximum(x[None,:]-x[1:-1,None],0)
    G=np.zeros(((nt-1)*len(B),m*nt))
    for j in range(nt-1):
        G[j*len(B):(j+1)*len(B),j*m:(j+1)*m]=-B
        G[j*len(B):(j+1)*len(B),(j+1)*m:(j+2)*m]=B
    # Exact same convex objective, with an auxiliary standardized projection e in [-1,1].
    # Eliminating e gives the squared distance to the bid/ask interval.
    nq=len(z0);M=sparse.csc_matrix(A/s[:,None]/np.sqrt(n));v=mid/s/np.sqrt(n)
    U=sparse.hstack([M,-sparse.eye(n)/np.sqrt(n)],format='csc')
    V=sparse.hstack([M,sparse.csc_matrix((n,n))],format='csc')
    R=sparse.diags(np.r_[np.full(nq,proto['regularizacion_convexo']),np.zeros(n)],format='csc')
    P=2*(U.T@U+proto['peso_mid']*(V.T@V)+R)
    q=-2*np.asarray(U.T@v+proto['peso_mid']*(V.T@v)+R@np.r_[z0,np.zeros(n)]).ravel()
    EE=sparse.hstack([sparse.csc_matrix(E),sparse.csc_matrix((len(E),n))],format='csc')
    GG=sparse.hstack([sparse.csc_matrix(G),sparse.csc_matrix((len(G),n))],format='csc')
    I=sparse.eye(nq+n,format='csc')
    C=sparse.vstack([EE,-GG,-I,I],format='csc')
    b=np.r_[np.ones(len(E)),np.zeros(len(G)),np.zeros(nq),np.ones(n),np.ones(nq+n)]
    cones=[clarabel.ZeroConeT(len(E)),clarabel.NonnegativeConeT(len(G)+2*(nq+n))]
    settings=clarabel.DefaultSettings();settings.verbose=False
    settings.max_iter=proto['maxiter_convexo'];settings.tol_gap_abs=1e-10;settings.tol_gap_rel=1e-10;settings.tol_feas=1e-10
    solver=clarabel.DefaultSolver(sparse.triu(P*1e-4,format='csc'),q*1e-4,C,b,cones,settings)
    sol=solver.solve()
    if sol.x is None or not np.isfinite(sol.x).all():raise ValueError('sin iterado convexo finito')
    weights=np.array(sol.x[:nq])
    model=DistribucionConvexa(np.array([r.T for r in rs]),x,weights.reshape(nt,m))
    return model,dict(convergencia=bool(str(sol.status)=='Solved'),mensaje=str(sol.status),iteraciones=int(sol.iterations),
        residual_primal=float(sol.r_prim),residual_dual=float(sol.r_dual),
        brecha_dual_objetivo=float(abs(sol.obj_val-sol.obj_val_dual)/1e-4),
        costo=float(objective(weights)[0]/1e-4),**model.control())
