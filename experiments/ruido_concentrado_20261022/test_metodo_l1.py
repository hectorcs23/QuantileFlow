import numpy as np
import pytest
from experiments.distribuciones_ruido_20261022.test_metodo import tabla,mercado
from experiments.ruido_concentrado_20261022.metodo import MercadoL1,conflictos_paridad


def test_minimo_l1_paridad_analitico_y_cap():
    # C-P debe ser cero; distancia entre bandas = 7, ambos spreads = 2.
    t=tabla([100,100],["C","P"],[10,1],spread=2)
    m=MercadoL1(t,100,1)
    assert m.reparar_l1(2)==pytest.approx(1.75,abs=1e-7)
    d=conflictos_paridad(t,100,1,2)
    assert d["filas_modificadas_min"]==2
    assert d["media_error_min"]==pytest.approx(1.75)
    with pytest.raises(RuntimeError): m.reparar_l1(1.7)


def test_presupuesto_cap_es_igual_al_modelo_uniforme():
    m=MercadoL1(mercado(),100,1,extras=(1.05,))
    for refs in ({},{"fb":(.9975,1.0025),"db":(.99,1.01)}):
        for discrete in (False,True):
            assert m.cdf_l1(1,.5,.5,**refs,discreta=discrete)==pytest.approx(
                m.cdf(1,.5,**refs,discreta=discrete),abs=1e-7)
        assert m.precio_call_l1(1.05,.5,.5,**refs)==pytest.approx(
            m.precio_call(1.05,.5,**refs),abs=1e-7)


def test_mayor_presupuesto_amplia_y_cdf_alcanzable_contenida():
    m=MercadoL1(mercado(),100,1)
    b=m.reparar_l1(.5)
    a=m.cdf_l1(1,.5,b+.01); c=m.cdf_l1(1,.5,b+.1)
    assert a["inferior"]>=c["inferior"]-1e-7
    assert a["superior"]<=c["superior"]+1e-7
    d=m.cdf_l1(1,.5,b+.1,discreta=True)
    assert c["inferior"]<=d["inferior"]+1e-7
    assert c["superior"]>=d["superior"]-1e-7


def test_masas_reconstruyen_presupuesto_y_cap():
    m=MercadoL1(mercado(),100,1)
    m.cdf_l1(1,.5,.1,db=(.99,1.01),fb=(.9975,1.0025))
    for t in m.testigos:
        p=np.array(t["p"]); e=m.desviaciones(p,t["d"])
        assert sum(p)==pytest.approx(1)
        assert min(p)>=-1e-8 and max(e)<=.5+1e-7
        assert np.mean(e)<=.1+1e-7


def test_descuento_variable_charnes_cooper():
    a=MercadoL1(mercado(),100,1); b=MercadoL1(mercado(),100,.9)
    cap=max(a.reparar(db=(.9,.9)),b.reparar())+.5
    budget=max(a.reparar_l1(cap,db=(.9,.9)),b.reparar_l1(cap))+.1
    assert a.cdf_l1(1,cap,budget,db=(.9,.9))==pytest.approx(b.cdf_l1(1,cap,budget),abs=1e-7)


def test_escala_orden_y_estados_adicionales():
    t=mercado(); a=MercadoL1(t,100,1)
    t=t.iloc[::-1].copy(); t[["strike","bid","ask"]]*=50
    b=MercadoL1(t,5000,1,extras=np.linspace(.01,1.99,150))
    assert a.reparar_l1(.5)==pytest.approx(b.reparar_l1(.5),abs=1e-7)
    assert a.cdf_l1(1,.5,.1)==pytest.approx(b.cdf_l1(1,.5,.1),abs=1e-7)


def test_outlier_grande_no_es_necesariamente_pocos_errores():
    t=tabla([90,90,100,100,110,110],["C","P"]*3,[16,1,10,3,5,13],spread=1)
    m=MercadoL1(t,100,1); cap=m.reparar()+.5
    bound=conflictos_paridad(t,100,1,cap)
    assert bound["incompatibles"]==3
    assert bound["filas_modificadas_min"]>=3
    assert bound["media_error_min"]<=m.reparar_l1(cap)+1e-7


@pytest.mark.parametrize("cap,budget",[(-1,.1),(np.nan,.1),(.5,-1),(.5,np.inf)])
def test_entradas_invalidas(cap,budget):
    with pytest.raises(ValueError): MercadoL1(mercado(),100,1).cdf_l1(1,cap,budget)
