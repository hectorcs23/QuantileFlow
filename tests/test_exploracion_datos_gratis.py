"""Pruebas de las piezas de cálculo de la exploración con datos gratis (sin red)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

RUTA = Path(__file__).resolve().parents[1] / "experiments" / "exploracion-datos-gratis"


def cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, RUTA / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


cero = cargar("skew_0dte_alpaca")
skew = cargar("skew_cboe")


def test_la_iv_se_recupera_del_precio_de_black_scholes():
    S, T = 600.0, 3 / (365 * 24)
    K = np.array([597.0, 598.0, 602.0, 603.0])
    call = np.array([False, False, True, True])
    sigma = np.array([0.22, 0.20, 0.15, 0.14])
    precio = cero.precio_bs(S, K, T, sigma, call)
    iv, delta = cero.iv_y_delta(precio, np.full(4, S), K, np.full(4, T), call)
    assert np.allclose(iv, sigma, atol=1e-6)
    assert np.all(delta[:2] < 0) and np.all(delta[2:] > 0)


def test_precio_imposible_da_nan():
    iv, delta = cero.iv_y_delta(np.array([0.0, 1e6]), np.full(2, 600.0), np.array([590.0, 610.0]),
                                np.full(2, 0.001), np.array([False, True]))
    assert np.isnan(iv).all() and np.isnan(delta).all()


def test_interpolacion_a_25_delta_sin_extrapolar():
    assert np.isclose(cero.interpolar([-0.30, -0.20], [0.20, 0.18]), 0.19)
    assert np.isclose(cero.interpolar([0.25, 0.10], [0.15, 0.13]), 0.15)
    assert np.isnan(cero.interpolar([-0.40, -0.35], [0.2, 0.2]))      # no la rodean
    assert np.isnan(cero.interpolar([-0.45, -0.05], [0.2, 0.1]))      # hueco mayor que 0.15


def test_la_base_horaria_solo_usa_sesiones_anteriores():
    fechas = pd.bdate_range("2025-01-01", periods=30)
    tabla = pd.DataFrame({580: np.arange(30, dtype=float)}, index=fechas)
    media, desv = cero.base_horaria(tabla)
    assert np.isnan(media.iloc[19, 0])                                 # menos de 20 previas
    assert media.iloc[20, 0] == np.mean(np.arange(20))                 # 20 previas, sin la del día
    tabla.iloc[25, 0] = 1e9                                            # un valor extremo del día 25
    media2, _ = cero.base_horaria(tabla)
    assert media2.iloc[25, 0] == media.iloc[25, 0]                     # no entra en su propia base


def test_la_convergencia_operable_no_usa_el_residuo_de_la_senal():
    fechas = pd.bdate_range("2025-01-01", periods=25)
    minutos = list(range(580, 700, 5))
    rng = np.random.default_rng(0)
    tabla = pd.DataFrame(rng.normal(0, 1, (25, len(minutos))), index=fechas, columns=minutos)
    tabla.iloc[24, 0] = 50.0                                           # solo un salto aislado en la señal
    cierres = {f: 16 * 60 for f in fechas}
    _, z, senales = cero.senales_y_residuos(tabla, cierres)
    s = senales[(senales["fecha"] == fechas[24]) & (senales["minuto"] == 580)].iloc[0]
    assert s["ingenua"] > 40                                           # la ingenua «revierte» por construcción
    assert abs(s["operable"]) < 10                                     # la operable no ve ese salto


def test_newey_west_coincide_con_mco_sin_rezagos():
    rng = np.random.default_rng(1)
    x = rng.normal(size=500)
    y = 0.5 * x + rng.normal(size=500)
    X = np.column_stack([np.ones(500), x])
    b, t = skew.newey_west(y, X, 0)
    assert np.isclose(b[1], np.polyfit(x, y, 1)[0])
    assert t[1] > 5
