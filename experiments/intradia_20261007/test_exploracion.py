"""Controles independientes: paridad conocida, anomalia inyectada y emparejamiento."""
import os
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.environ.get("QF_CODE", str(Path(__file__).resolve().parents[2])))
from quantileflow import cadenas
from quantileflow.opciones import precio_black
from explorar_intradia import paired_changes, validar_fechas


def test_five_sessions_keep_explicit_order():
    dates = ["2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]
    assert validar_fechas(dates) == dates


@pytest.mark.parametrize("dates", [["2026-10-02", "2026-10-02"],
                                    ["2026-10-05", "2026-10-02"], ["2026-10-32"]])
def test_invalid_dates_are_rejected(dates):
    with pytest.raises(ValueError):
        validar_fechas(dates)


def synthetic(shock=0):
    k = np.arange(85., 116., 2.)
    K = np.repeat(k, 2)
    call = np.tile([True, False], len(k))
    t, f, d = 30/365, 100., np.exp(-.04*30/365)
    mid = precio_black(f, K, .25**2*t, d, call)
    target = 2*(len(k)//2)
    mid[target] += shock
    cap = cadenas.Captura(K, call, mid-.002, mid+.002, np.ones(len(K))*10,
                         np.ones(len(K))*10, np.full(len(K), 35099.), t, 100., 35099., .04,
                         corte=35100., disponible=np.full(len(K), 35099.))
    return cap, d, k[target//2]


@pytest.mark.parametrize("fixed", [False, True])
def test_exact_parity_does_not_invent_anomaly(fixed):
    cap, d, _ = synthetic()
    result = cadenas.residuos_paridad(cap, descuento=d if fixed else None)
    assert len(result.strike) == 16
    assert np.max(np.abs(result.residuo)) < 1e-10
    assert not result.fuera_de_banda.any()


def test_injected_call_error_is_identified_without_self_fitting():
    cap, d, k = synthetic(shock=.5)
    result = cadenas.residuos_paridad(cap, descuento=d)
    j = np.flatnonzero(result.strike == k)[0]
    assert result.fuera_de_banda[j]
    assert result.residuo[j] == pytest.approx(.5, abs=1e-9)
    assert not result.en_estimacion[j]
    assert np.max(np.abs(np.delete(result.residuo, j))) < 1e-10


def frame():
    rows = []
    # Same strike on distinct dates/expiries must not create spurious joins.
    for date in ["2026-10-02", "2026-10-05"]:
        for expiry in ["2026-11-02", "2026-11-03"]:
            for hour, residual in [("09:45", 2.), ("10:00", .2)]:
                rows.append(dict(fecha=date, vencimiento=expiry, strike=100., hora=hour,
                                 residuo=residual, ancho=1., fuera=residual>.5,
                                 edad_max=6., desfase_patas=.1, k=.01))
    return pd.DataFrame(rows)


def test_pairing_separates_date_and_expiry_and_uses_two_bands():
    m = paired_changes(frame())
    assert len(m) == 4
    assert np.allclose(m.delta_residuo, -1.8)
    assert np.allclose(m.banda_cambio, 1.)
    assert m.cambio_supera_bandas.all()
    assert not m.fuera_ambos_mismo_signo.any()


def test_duplicate_contract_cannot_multiply_panel():
    f = frame()
    with pytest.raises(pd.errors.MergeError):
        paired_changes(pd.concat([f, f.iloc[:1]], ignore_index=True))
