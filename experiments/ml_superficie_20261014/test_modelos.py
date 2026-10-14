import numpy as np
from quantileflow.superficies import SuperficieSSVI, Rebanada
from quantileflow.opciones import precio_black
from experiments.ml_superficie_20261014.modelos import CorreccionRed, DistribucionConvexa, ajustar_convexo


def base():return SuperficieSSVI(np.array([.08,.10]),np.array([.003,.004]),-.4,.8,.35)


def test_red_cero_reproduce_base_y_calendario():
    s=base();red=CorreccionRed(s,np.zeros(13));k=np.linspace(-.2,.2,301)
    assert np.allclose(red.w(k,.09),s.w(k,.09))
    assert red.control()['pasa_malla_y_alas']
    assert not red.control()['certificado_global']


def test_derivadas_red_contra_diferencias_finitas():
    p=np.r_[[-1.2,-.5,.5,1.3],[.1,-.1,.2,-.2],[.08,-.02,.01,.03],.03]
    red=CorreccionRed(base(),p);k=np.array([-.021,-.003,.012]);h=1e-6
    w,w1,w2=red.derivadas(k,.09)
    assert np.allclose(w1,(red.w(k+h,.09)-red.w(k-h,.09))/(2*h),rtol=1e-7,atol=1e-8)
    assert np.allclose(w2,(red.w(k+h,.09)-2*w+red.w(k-h,.09))/h**2,rtol=2e-5,atol=2e-6)


def test_factor_positivo_conserva_calendario():
    red=CorreccionRed(base(),np.linspace(-.4,.4,13));k=np.linspace(-1,1,101)
    assert np.all(red.w(k,.1)>=red.w(k,.08))


def test_discreta_paridad_convexidad_y_calendario_global():
    d=DistribucionConvexa(np.array([.08,.1]),np.array([.8,1,1.2]),np.array([[.1,.8,.1],[.25,.5,.25]]))
    assert d.control()['pasa_restricciones']
    K=np.linspace(50,150,401);F=100.;D=.99
    c=Rebanada(.1,F,D,K,np.zeros(len(K)),np.ones(len(K)),np.ones(len(K),dtype=bool))
    put=Rebanada(.1,F,D,K,c.bid,c.ask,~c.es_call)
    assert np.allclose(d.precios(c)-d.precios(put),D*(F-K),atol=1e-12)
    assert np.diff(d.precios(c)).max()<1e-12
    assert np.diff(d.precios(c),n=2).min()>-1e-12


def test_control_detecta_calendario_y_media_incorrectos():
    d=DistribucionConvexa(np.array([.08,.1]),np.array([.8,1,1.2]),np.array([[.3,.4,.3],[0,1,0]]))
    assert not d.control()['pasa_restricciones']
    d.masas[0,0]=.1
    assert d.control()['error_masa']>.1


def test_ajuste_convexo_impone_igualdades_sin_penalizaciones():
    rs=[]
    for T in (.08,.1):
        K=np.repeat(np.linspace(96,104,5),2);types=np.tile([True,False],5)
        p=precio_black(100,K,.2**2*T,.99,types)
        rs.append(Rebanada(T,100,.99,K,p-.1,p+.1,types))
    model,info=ajustar_convexo(rs,{'peso_mid':.02,'regularizacion_convexo':.1,'maxiter_convexo':300})
    assert info['convergencia'],info
    assert info['pasa_restricciones'],info
    assert info['error_masa']<1e-9
    assert info['error_media']<1e-9
