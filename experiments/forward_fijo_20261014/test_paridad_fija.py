import numpy as np
import pandas as pd
import pytest
from experiments.forward_fijo_20261014.metodo import bandas_paridad,diagnostico


def filas():
    return pd.DataFrame(dict(strike=[100,100,101,101,102],tipo=['C','P','C','P','C'],
        bid=[2,2,4,1,2],ask=[3,3,5,2,3]))


def test_bandas_pares_completos_y_minimo_imposible():
    a=bandas_paridad(filas(),1)
    assert np.array_equal(a,[[99,101],[103,105]])
    assert diagnostico(filas(),1,100)==dict(pares=2,incompatibles=1,minimo_incompatibles_F_libre=1)
    assert diagnostico(filas(),1,102)['incompatibles']==2


def test_extremos_cerrados_y_descuento():
    f=filas().iloc[:2]
    assert np.array_equal(bandas_paridad(f,.5),[[98,102]])
    assert diagnostico(f,.5,98)['incompatibles']==0
    assert diagnostico(f,.5,102)['incompatibles']==0


def test_orden_no_altera_y_no_inventa_pares():
    assert np.array_equal(bandas_paridad(filas(),1),bandas_paridad(filas().iloc[::-1],1))
    assert diagnostico(filas().iloc[-1:],1,100)['pares']==0


def test_rechaza_datos_inconsistentes():
    with pytest.raises(ValueError):bandas_paridad(filas(),0)
    with pytest.raises(ValueError):bandas_paridad(pd.concat([filas(),filas().iloc[:1]]),1)
    f=filas();f.loc[0,'ask']=f.loc[0,'bid']
    with pytest.raises(ValueError):bandas_paridad(f,1)
