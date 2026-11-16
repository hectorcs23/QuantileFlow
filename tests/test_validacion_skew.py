"""Regression tests for inference failures, chronology, missing labels, and paired populations."""
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pandas as pd

FOLDER = Path(__file__).resolve().parents[1] / 'experiments' / 'exploracion-datos-gratis'
sys.path.insert(0, str(FOLDER))
sys.path.insert(0, str(FOLDER.parents[1]))
import skew_0dte_alpaca as zero
import skew_cboe as cboe
from validar_0dte import comparaciones
from validar_cboe import preparar, pronosticos
from validacion_comun import guardar
from comparar_antiguedad import comparar


def test_delayed_estimator_cannot_exclude_correlated_measurement_noise():
    rng = np.random.default_rng(1729)
    n, slots, rho = 800, 75, .9
    error = np.empty((n, slots))
    error[:, 0] = rng.normal(size=n)
    for j in range(1, slots):
        error[:, j] = rho * error[:, j - 1] + np.sqrt(1 - rho**2) * rng.normal(size=n)
    dates = pd.bdate_range('2020-01-01', periods=n)
    table = pd.DataFrame(4 + error, index=dates, columns=range(580, 955, 5))
    _, z, signals = zero.senales_y_residuos(table, dict.fromkeys(dates, 960))
    days = [day for day in dates if np.isfinite(z.loc[day]).any()]
    result = zero.convergencia(signals, days, 'operable')
    # True skew is exactly 4; a positive interval here is entirely measurement error.
    assert result['ic95'][0] > .9
    assert result['media_puntos_vol'] > 1


def test_persistence_uses_common_origins_and_does_not_identify_noise():
    data = pd.DataFrame([[1, 2, 3, 4, 5, 6, 7], [2, np.nan, 4, 5, 6, 7, 8]],
                        columns=range(580, 615, 5))
    report = zero.persistencia(data)
    assert len({v['n'] for v in report['pendiente'].values()}) == 1
    assert report['pendiente']['5_min']['n'] == 1
    assert report['ruido_identificado'] is False
    assert report['vida_media_identificada'] is False
    assert 'parte_de_la_varianza_que_es_ruido' not in report


def test_paired_comparisons_and_horizon_attrition_are_explicit():
    dates = pd.bdate_range('2025-01-01', periods=30)
    signals = pd.DataFrame({'fecha': dates, 'minuto': 580, 'z': 2.5,
                           'ingenua': 3., 'operable': 1., 'operable_10': .4,
                           'operable_20': .7, 'operable_45': 1.2})
    signals.loc[0, 'operable'] = np.nan
    signals.loc[1, 'operable_45'] = np.nan
    r = comparaciones(signals, dates, dict.fromkeys(dates, 960))
    assert r['pares_ingenua_retrasada']['ingenua']['senales_validas'] == 29
    assert r['pares_ingenua_retrasada']['operable']['senales_validas'] == 29
    assert r['senales_con_todos_los_horizontes'] == 28
    assert all(v['senales_validas'] == 28 for v in r['horizontes_misma_cohorte'].values())


def test_targets_do_not_jump_over_missing_skew_day_and_exclude_first_overnight():
    days = pd.bdate_range('2025-01-01', periods=12)
    spy = pd.DataFrame({'o': np.exp(np.arange(12) * .1), 'c': np.exp(np.arange(12) * .1 + .01)}, index=days)
    skew = pd.Series(120., index=days.delete(1))
    vix = pd.Series(20., index=days)
    data = preparar(spy, skew, vix)
    assert np.isclose(data.loc[days[0], 'y1_ac'], .01)
    assert data.loc[days[0], 'fin_y1_ac'] == days[1]
    assert np.isclose(data.loc[days[0], 'rv5_posterior'], np.sqrt(.01**2 + 4 * .1**2))


def test_expanding_forecast_purges_unmatured_training_labels():
    days = pd.bdate_range('2020-01-01', periods=40)
    data = pd.DataFrame({'rv5_posterior': .01 + np.arange(40) * .001,
                         'vix': np.sin(np.arange(40)), 'abs_r': np.cos(np.arange(40)),
                         'zskew': np.arange(40) / 40, 'fin_rv5_posterior': pd.Series(days, index=days).shift(-5)}, index=days)
    forecasts = pronosticos(data, 'rv5_posterior', ['vix', 'abs_r'], 'zskew', corte=str(days[20].date()), minimo=5)
    assert (forecasts.ultima_etiqueta_ajuste < forecasts.fecha).all()
    changed = data.copy()
    changed.loc[days[16]:, 'rv5_posterior'] = 1000
    other = pronosticos(changed, 'rv5_posterior', ['vix', 'abs_r'], 'zskew', corte=str(days[20].date()), minimo=5)
    # At day 20, labels of origins 15+ have not matured strictly before that date.
    assert np.isclose(forecasts.iloc[0].con_skew, other.iloc[0].con_skew)


def test_newey_west_covariance_matches_direct_bartlett_sum():
    rng = np.random.default_rng(14)
    X = np.column_stack([np.ones(40), rng.normal(size=40)])
    y = X @ np.array([.2, .4]) + rng.normal(size=40)
    b, t = cboe.newey_west(y, X, 3)
    u = y - X @ b
    meat = np.zeros((2, 2))
    for i in range(40):
        for j in range(40):
            lag = abs(i - j)
            if lag <= 3:
                meat += (1 - lag / 4) * u[i] * u[j] * np.outer(X[i], X[j])
    inverse = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(inverse @ meat @ inverse))
    assert np.allclose(t, b / se)


def test_strict_json_writes_missing_numbers_as_null(tmp_path):
    import json
    path = tmp_path / 'result.json'
    guardar(path, {'empty': float('nan'), 'infinite': float('inf'), 'n': np.int64(2)})
    assert json.loads(path.read_text(encoding='utf-8')) == {'empty': None, 'infinite': None, 'n': 2}


def test_one_minute_age_rejects_old_trades_and_other_expirations():
    t, close = pd.Timestamp('2025-01-02T14:35:00Z'), pd.Timestamp('2025-01-02T21:00:00Z')
    T = (close - t - pd.Timedelta(seconds=30)).total_seconds() / (365 * 86400)
    options = {}
    for call, strikes in [(False, range(594, 600)), (True, range(601, 607))]:
        for K in strikes:
            price = float(zero.precio_bs(600., K, T, .2, call))
            symbol = f'SPY250102{"C" if call else "P"}{K * 1000:08d}'
            options[symbol] = [{'t': t.isoformat(), 'vw': price, 'n': 10}]
    record = {'fecha': '2025-01-02', 'cierre_utc': close.isoformat(),
              'spy': [{'t': t.isoformat(), 'vw': 600.}], 'opciones': options}
    assert np.isfinite(zero.rr_de_la_sesion(record).get(580))
    assert zero.rr_de_la_sesion(record, antiguedad_maxima=1).empty
    record['opciones'] = {symbol.replace('250102', '250103'): bars for symbol, bars in options.items()}
    assert zero.rr_de_la_sesion(record).empty


def test_age_comparison_freezes_original_signal_direction_and_handles_missing_exit():
    date = pd.Timestamp('2025-01-02')
    r5 = pd.DataFrame([[5., 2.]], index=[date], columns=[585, 615])
    r1 = pd.DataFrame([[-5., -2.]], index=[date], columns=[585, 615])
    signal = pd.DataFrame([{'fecha': date, 'minuto': 580, 'z': 2.5}])
    pair = comparar(r5, r1, signal).iloc[0]
    assert pair.edad5 == 3
    assert pair.edad1 == -3  # Still original d=-1, no reselection using age1.
    r1.at[date, 615] = np.nan
    assert np.isnan(comparar(r5, r1, signal).iloc[0].edad1)
