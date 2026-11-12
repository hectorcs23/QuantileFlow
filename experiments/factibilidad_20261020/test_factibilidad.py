import numpy as np
import pandas as pd
import pytest
from quantileflow.opciones import precio_black
from experiments.factibilidad_20261020.metodo import diagnosticar


def tabla(K, tipos, mids, spread=.2):
    return pd.DataFrame(dict(strike=K, tipo=tipos,
                            bid=np.asarray(mids) - spread / 2,
                            ask=np.asarray(mids) + spread / 2))


def test_precios_coherentes_no_requieren_relajacion():
    K = np.repeat([80., 95., 100., 110., 120.], 2)
    tipos = np.tile(["C", "P"], 5)
    mids = precio_black(102., K, .3**2 * .25, .99, tipos == "C")
    t = tabla(K, tipos, mids)
    for libre in (False, True):
        for objetivo in ("maximo", "media"):
            r = diagnosticar(t, 102., .99, forward_libre=libre, objetivo=objetivo)
            assert r["relajacion"] == pytest.approx(0., abs=1e-7)
            assert r["factible_sin_relajar"]


def test_paridad_un_par_solucion_analitica_y_forward_libre():
    t = tabla([100., 100.], ["C", "P"], [10., 1.], spread=2.)
    r = diagnosticar(t, 100., 1., nivel="paridad_cotas")
    assert r["relajacion"] == pytest.approx(1.75, abs=1e-7)
    libre = diagnosticar(t, 100., 1., nivel="paridad_cotas", forward_libre=True)
    assert libre["relajacion"] == pytest.approx(0., abs=1e-7)


def test_dos_pares_incompatibles_incluso_con_forward_libre():
    # Primas suficientemente positivas para que la cota cero no sea activa.
    t = tabla([100., 100., 110., 110.], ["C", "P", "C", "P"], [14., 5., 10., 6.])
    r = diagnosticar(t, 110., 1., nivel="paridad_cotas", forward_libre=True)
    assert r["relajacion"] == pytest.approx(5.75, abs=1e-6)
    assert not r["factible_sin_relajar"]


def test_convexidad_detecta_fallo_que_pasa_verticales():
    t = tabla([90., 100., 110.], ["C"] * 3, [12., 11., 2.])
    assert diagnosticar(t, 100., 1., nivel="verticales")["relajacion"] == pytest.approx(0.)
    r = diagnosticar(t, 100., 1.)
    assert r["relajacion"] == pytest.approx(9.5, abs=1e-6)
    assert r["violacion_primal"] < 1e-8
    assert r["brecha_primal_dual"] < 1e-6


@pytest.mark.parametrize("objetivo", ["media", "maximo"])
def test_unidades_y_orden_no_cambian_relajacion(objetivo):
    t = tabla([90., 100., 110.], ["C"] * 3, [12., 11., 2.])
    r = diagnosticar(t, 100., 1., objetivo=objetivo)
    otra = t.iloc[::-1].copy()
    otra[["strike", "bid", "ask"]] *= 50
    z = diagnosticar(otra, 5000., 1., objetivo=objetivo)
    assert z["relajacion"] == pytest.approx(r["relajacion"], abs=1e-6)
    assert r["media_distancia_spreads"] <= r["max_distancia_spreads"] + 1e-7


def test_las_restricciones_anidadas_no_disminuyen_el_error():
    t = tabla([90., 100., 110.], ["C"] * 3, [12., 11., 2.])
    valores = [diagnosticar(t, 100., 1., nivel=n)["relajacion"]
               for n in ("paridad_cotas", "verticales", "convexidad")]
    assert np.min(np.diff(valores)) >= -1e-7


def test_descuento_libre_recupera_un_mercado_sintetico_con_descuento_distinto():
    K = np.repeat([80., 95., 100., 110., 120.], 2)
    tipos = np.tile(["C", "P"], 5)
    mids = precio_black(102., K, .3**2 * .25, .95, tipos == "C")
    t = tabla(K, tipos, mids, spread=.02)
    fijo = diagnosticar(t, 100., 1., forward_libre=True)
    libre = diagnosticar(t, 100., 1., forward_libre=True, descuento_libre=True)
    assert fijo["relajacion"] > 1.
    assert libre["relajacion"] == pytest.approx(0., abs=1e-7)
    assert libre["descuento_ratio_diagnostico"] == pytest.approx(.95, abs=.002)


def test_paridad_imposible_aun_con_descuento_y_forward_libres():
    # C-P aumenta con K: no admite ninguna pendiente -D <= 0.
    t = tabla([100., 100., 110., 110.], ["C", "P", "C", "P"], [5., 5., 8., 4.])
    r = diagnosticar(t, 100., 1., forward_libre=True, descuento_libre=True,
                      nivel="paridad_cotas")
    # La paridad sola exige al menos 4.5 spreads; P<=D*K añade otra cota.
    assert r["relajacion"] >= 4.5 - 1e-6
    assert not r["factible_sin_relajar"]


@pytest.mark.parametrize("tipo_error", ["duplicado", "cruzado", "nan", "descuento"])
def test_entradas_invalidas_rechazadas(tipo_error):
    t = tabla([100., 110.], ["C", "C"], [10., 5.])
    if tipo_error == "duplicado":
        t.loc[1, "strike"] = 100.
    if tipo_error == "cruzado":
        t.loc[0, "ask"] = 0.
    if tipo_error == "nan":
        t.loc[0, "bid"] = np.nan
    with pytest.raises(ValueError):
        diagnosticar(t, 100., 0. if tipo_error == "descuento" else 1.)
