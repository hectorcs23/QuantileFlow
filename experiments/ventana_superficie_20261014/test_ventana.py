import pandas as pd
import pytest
from experiments.ventana_superficie_20261014.metodo import dividir_anidado, seleccionar


def ejemplo():
    return pd.DataFrame([
        dict(id_contrato=f'{strike}{side}', vencimiento='2030-01-01', strike=strike,
             tipo=side, k=k, holdout=strike == 100, entrenamiento=strike != 100)
        for strike, k in [(90, -.10), (95, -.05), (100, 0.), (105, .05), (110, .10)]
        for side in ['C', 'P']
    ])


def test_conserva_historico_pares_anidamiento_y_entradas():
    wide = ejemplo(); old = wide[wide.strike.eq(100)].copy()
    out = dividir_anidado(wide, old)
    assert out[out.historico].holdout.all()
    assert out.groupby(['vencimiento', 'strike']).holdout.nunique().max() == 1
    assert (~out.holdout).equals(out.entrenamiento)
    small = seleccionar(out, .06); big = seleccionar(out, .10)
    assert set(small.id_contrato).issubset(big.id_contrato)
    assert small.holdout.equals(big.loc[small.index, 'holdout'])
    assert wide.equals(ejemplo())


def test_split_invariante_al_orden():
    wide = ejemplo(); old = wide[wide.strike.eq(100)]
    a = dividir_anidado(wide, old).sort_index()
    b = dividir_anidado(wide.iloc[::-1], old.iloc[::-1]).sort_index()
    assert a.equals(b)


def test_rechaza_perdida_historica_y_par_dividido():
    wide = ejemplo(); old = wide[wide.strike.eq(100)].copy()
    with pytest.raises(ValueError): dividir_anidado(wide.iloc[1:], wide)
    old.loc[old.index[0], 'holdout'] = False
    with pytest.raises(ValueError): dividir_anidado(wide, old)
    with pytest.raises(ValueError): seleccionar(wide, 0)
