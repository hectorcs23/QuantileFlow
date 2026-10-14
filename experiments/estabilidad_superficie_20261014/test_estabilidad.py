import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm
from quantileflow.superficies import SuperficieSSVI
from experiments.estabilidad_superficie_20261014.metodo import perturbar,cdf_comun,cuantiles_modelo_diagnostico,cuantiles_discretos,distancia_cdf_discreta


def data():return pd.DataFrame(dict(bid=[.01,2,3,4],ask=[.21,2.4,3.4,4.4],tipo=['C','P','C','P'],strike=[99,99,100,100],dias=[30]*4,entrenamiento=[True,True,False,False]))


def test_shocks_preservan_spread_positividad_y_holdout():
    original=data()
    for case in ['paralelo_arriba','paralelo_abajo','paridad_arriba','paridad_abajo','jitter_17','jitter_29']:
        out,info=perturbar(original,case)
        assert np.allclose(out.ask-out.bid,original.ask-original.bid)
        assert out.bid.min()>=0
        assert out[~out.entrenamiento].equals(original[~original.entrenamiento])
        assert info['max_movimiento_en_semispread']<=.1+1e-12
    assert original.equals(data())


def test_jitter_no_depende_del_orden_de_filas():
    a=data();b=a.iloc[::-1]
    aa,_=perturbar(a,'jitter_17');bb,_=perturbar(b,'jitter_17')
    assert aa.sort_index().equals(bb.sort_index())


def test_cuantiles_contra_lognormal_y_forward_mecanico():
    t=.1;w=.04*t;s=SuperficieSSVI(np.array([t]),np.array([w]),0.,0.,.4)
    u=np.array([.05,.5,.95]);expected=np.exp(-w/2+np.sqrt(w)*norm.ppf(u))
    assert np.allclose(cuantiles_modelo_diagnostico(s,t,u),expected,atol=1e-11)
    q=cuantiles_modelo_diagnostico(s,t,u,1.01)
    assert np.allclose(q,expected*1.01)
    assert np.allclose(cdf_comun(s,t,q,1.01),u,atol=1e-11)


def test_discreta_usa_inversa_generalizada_sin_suavizar_atomos():
    assert np.array_equal(cuantiles_discretos([.8,1,1.2],[.2,.6,.2],[.19,.2,.21,.95]),[.8,.8,1,1.2])


def test_rechaza_niveles_o_entradas_invalidas():
    with pytest.raises(ValueError):perturbar(data(),'paralelo_arriba',-1)
    with pytest.raises(ValueError):perturbar(data(),'inventado')
    with pytest.raises(ValueError):cuantiles_discretos([1,2],[.5,.5],[0])
    with pytest.raises(ValueError):cuantiles_discretos([1,2],[-.1,1.1],[.5])


def test_distancia_no_pierde_saltos_entre_nodos_de_malla():
    assert distancia_cdf_discreta(lambda x:x,[.25,.75],[.5,.5],(0,1))==pytest.approx(.25)
