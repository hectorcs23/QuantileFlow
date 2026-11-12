import numpy as np
import pytest
from experiments.skew_bandas_20261010.control_forward import maximo_solapamiento


def test_limite_con_intervalos_cerrados_y_solapamiento_parcial():
    assert maximo_solapamiento([[1,2],[2,3],[4,5]]) == 2
    assert maximo_solapamiento([[1,4],[2,3],[3,5],[6,7]]) == 3
    assert maximo_solapamiento([[1,2],[3,4],[5,6]]) == 1


def test_error_de_ancla_puede_desaparecer_con_forward_libre():
    intervalos = [[103,104],[103.5,104.5],[103.8,104.1]]
    assert all(not a <= 100 <= b for a,b in intervalos)
    assert maximo_solapamiento(intervalos) == 3


@pytest.mark.parametrize("intervalos",[[[2,1]],[[np.nan,2]],[[1,2,3]]])
def test_intervalos_invalidos_no_producen_certificado(intervalos):
    with pytest.raises(ValueError):
        maximo_solapamiento(intervalos)
