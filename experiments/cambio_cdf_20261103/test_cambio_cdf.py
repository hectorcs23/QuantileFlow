import numpy as np
import pandas as pd
import pytest
from experiments.cambio_cdf_20261103.metodo import cambio,coordenadas,conjunto
from experiments.ruido_concentrado_20261022.metodo import MercadoL1


def fijo(F, absoluto):
    t=pd.DataFrame(dict(strike=[F,F],tipo=['C','P'],bid=[0.,0.],ask=[.00001,.00001]))
    return MercadoL1(t,F,1.,puntos=np.asarray(absoluto)/F)


def test_mismo_precio_fisico_y_ancho_en_ambos_cortes():
    a,ea=coordenadas([.97,1,1.03],100,100,.0025)
    b,eb=coordenadas([.97,1,1.03],100,102,.0025)
    assert a*100==pytest.approx(b*102) and ea*100==pytest.approx(eb*102)
    assert b[1]!=1.


@pytest.mark.parametrize('a,b,estado',[
    ([.15,.16,.22,.23],[.34,.35,.36,.37],'aumento'),
    ([.34,.35,.36,.37],[.15,.16,.22,.23],'descenso'),
    ([.10,.12,.2,.25],[.15,.17,.3,.32],'cero_alcanzable'),
    ([.10,.12,.17,.25],[.20,.22,.3,.32],'indeterminado')])
def test_rango_cambio_y_certificacion(a,b,estado):
    c=cambio(a,b,1e-7)
    assert c['inferior']==pytest.approx(b[0]-a[3]) and c['superior']==pytest.approx(b[3]-a[0])
    assert c['estado']==estado


def test_igualdad_conjunta_y_separacion_forzada():
    k=np.array([95.,100.,105.])
    a,b=fijo(80.,k),fijo(120.,k)
    assert conjunto([a,a],[0.,0.],[0.,0.])['diferencia_max']<1e-7
    j=conjunto([a,b],[0.,0.],[0.,0.])
    assert j['diferencia_max']>.999 and sum(j['masas'][0])==pytest.approx(1)
    f=lambda m:m.cdf_l1(m.puntos[1],0.,0.)
    assert f(b)['superior']<f(a)['inferior']-.99


def test_no_mezclar_umbrales_y_no_aceptar_bandas_invertidas():
    with pytest.raises(ValueError): conjunto([fijo(100,[100]),fijo(100,[101])],[0,0],[0,0])
    with pytest.raises(ValueError): cambio([.1,.4,.3,.5],[.1,.2,.3,.4],1e-7)


def test_tolerancia_no_transforma_holgura_numerica_en_direccion():
    assert cambio([.1,.1,.2,.2],[.2+1e-9,.21,.3,.3],1e-7)['estado']=='indeterminado'


def test_relajacion_conjunta_acota_separacion_y_testigo_en_malla():
    from experiments.cambio_cdf_20261103.control_malla import resolver_conjunto
    a,b=fijo(80.,[95.,100.,105.]),fijo(120.,[95.,100.,105.]);refs=[((1.,1.),(1.,1.))]*2
    lo=resolver_conjunto([a,b],[0,0],[0,0],refs,True)['gamma']
    hi=resolver_conjunto([a,b],[0,0],[0,0],refs,False)['gamma']
    assert .99<lo<=hi+1e-7
    assert resolver_conjunto([a,a],[0,0],[0,0],refs,False)['gamma']<1e-7
