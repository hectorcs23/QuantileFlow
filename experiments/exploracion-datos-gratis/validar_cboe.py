"""Validación retrospectiva diaria: objetivos posteriores a la disponibilidad, etiquetas maduras y riesgo OOS."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
import skew_cboe as s
import skew_0dte_alpaca as intradia
from validacion_comun import guardar, procedencia
sys.path.insert(0, str(s.RAIZ))
from quantileflow.calendario import calendario


def preparar(spy, skew, vix):
    # Build labels on the underlying trading calendar BEFORE dropping missing index observations.
    df = spy.sort_index().copy()
    c, o = np.log(df.c), np.log(df.o)
    df['r'] = c.diff()
    df['abs_r'] = df.r.abs()
    df['rv5_pasada'] = np.sqrt(df.r.pow(2).rolling(5).sum())
    df['y1_ac'] = c.shift(-1) - o.shift(-1)
    # First overnight starts before the final SKEW is observable: exclude it.
    df['rv5_posterior'] = np.sqrt(df.y1_ac.pow(2) + sum(df.r.shift(-k).pow(2) for k in range(2, 6)))
    dates = pd.Series(df.index, index=df.index)
    df['fin_y1_ac'], df['fin_rv5_posterior'] = dates.shift(-1), dates.shift(-5)
    df = df.join(skew.rename('skew')).join(vix.rename('vix'))
    df['dskew'] = df['skew'].diff()
    df['dvix'] = df.vix.diff()
    df['zskew'] = (df['skew'] - df['skew'].rolling(252, min_periods=126).mean()) / df['skew'].rolling(252, min_periods=126).std()
    return df


def pronosticos(df, objetivo, base, extra, corte='2021-01-01', minimo=500):
    """Expanding daily fit. No label can mature on/after the forecast's date."""
    fin = 'fin_' + objetivo
    data = df[[objetivo, fin] + base + [extra]].dropna()
    records = []
    cols = base + [extra]
    for date in data.index[data.index >= corte]:
        train = data[(data.index < date) & (data[fin] < date)]
        if len(train) < minimo:
            continue
        def pred(features):
            X = np.column_stack([np.ones(len(train)), train[features].to_numpy()])
            beta = np.linalg.lstsq(X, train[objetivo].to_numpy(), rcond=None)[0]
            val = np.r_[1., data.loc[date, features].to_numpy(dtype=float)] @ beta
            return max(1e-6, float(val)) if objetivo.startswith('rv') else float(val)
        records.append({'fecha': date, 'realizado': data.at[date, objetivo],
                        'referencia': pred(base), 'con_skew': pred(cols),
                        'media_ajuste': train[objetivo].mean(), 'n_ajuste': len(train),
                        'ultima_etiqueta_ajuste': train[fin].max()})
    return pd.DataFrame(records, columns=['fecha', 'realizado', 'referencia', 'con_skew', 'media_ajuste',
                                         'n_ajuste', 'ultima_etiqueta_ajuste'])


def evaluar(forecasts):
    if forecasts.empty:
        return {'n': 0, 'estado': 'sin pronósticos'}
    y = forecasts.realizado.to_numpy()
    a, b = (y - forecasts.referencia.to_numpy()) ** 2, (y - forecasts.con_skew.to_numpy()) ** 2
    diff = a - b  # Positive = incremental improvement, same dates/targets.
    denominator = np.mean((y - forecasts.media_ajuste.to_numpy()) ** 2)
    return {'n': len(forecasts), 'periodo': [str(forecasts.fecha.min().date()), str(forecasts.fecha.max().date())],
            'mse_referencia': float(a.mean()), 'mse_con_skew': float(b.mean()),
            'reduccion_mse_pct': float(100 * (1 - b.mean() / a.mean())),
            'diferencia_perdida_media': float(diff.mean()),
            'ic95_diferencia_bloques_10_sesiones': intradia.bootstrap(diff),
            'r2_oos_referencia': float(1 - a.mean() / denominator),
            'r2_oos_con_skew': float(1 - b.mean() / denominator)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desde', default='2016-01-01')
    parser.add_argument('--hasta', default='2026-10-01')
    parser.add_argument('--datos', type=Path, default=s.CACHE)
    parser.add_argument('--salida', type=Path, default=s.SALIDA / 'validacion_cboe.json')
    args = parser.parse_args()
    archivos = [args.datos / f for f in ('SKEW.csv', 'VIX.csv', 'spy_diario.json')]
    if not all(p.exists() for p in archivos):
        raise SystemExit('Faltan datos originales. Descárgalos con skew_cboe.py o copia la caché privada.')
    spy = pd.DataFrame(json.loads(archivos[2].read_text(encoding='utf-8')))
    spy.index = pd.to_datetime(spy.t.str[:10])
    spy = spy.loc[args.desde:args.hasta, ['o', 'c']]
    esperadas = calendario('XNYS').sessions_in_range(args.desde, args.hasta).tz_localize(None)
    if spy.index.has_duplicates or len(spy.index.difference(esperadas)):
        raise ValueError('SPY contiene fechas duplicadas o ajenas al calendario XNYS')
    faltantes_spy = esperadas.difference(spy.index)
    spy = spy.reindex(esperadas)
    def indice(path, column):
        d = pd.read_csv(path)
        return pd.Series(d[column].to_numpy(), index=pd.to_datetime(d.DATE, format='%m/%d/%Y'))
    df = preparar(spy, indice(archivos[0], 'SKEW'), indice(archivos[1], 'CLOSE'))
    riesgo = pronosticos(df, 'rv5_posterior', ['vix', 'abs_r'], 'zskew')
    direccion = pronosticos(df, 'y1_ac', ['r', 'dvix'], 'dskew')
    riesgo_control = pronosticos(df, 'rv5_posterior', ['vix', 'abs_r', 'rv5_pasada'], 'zskew')
    regression = s.ajustar(df, 'rv5_posterior', ['zskew', 'vix', 'abs_r'], 5)
    t = regression['zskew']['t']
    p = float(2 * norm.sf(abs(t)))
    config = {'desde': args.desde, 'hasta': args.hasta, 'corte_oos': '2021-01-01',
              'ajuste': 'OLS expansivo; etiquetas maduras antes de la fecha de pronóstico',
              'primario': 'reducción MSE rv5_posterior al añadir zskew a vix+abs_r',
              'riesgo_objetivo': 'raíz de (retorno próxima apertura-cierre)^2 + siguientes 4 retornos cierre-cierre^2',
              'prediccion_riesgo_minimo': 1e-6, 'bootstrap': {'bloque': 10, 'repeticiones': 3000, 'semilla': 1729}}
    config['ajuste_minimo'] = 500
    config['calendario'] = 'XNYS; preservar sesiones ausentes, sin comprimir objetivos'
    result = {'procedencia': procedencia(s.RAIZ, archivos, config), 'sesiones_spy': len(df),
              'fechas_spy_ausentes': [str(f.date()) for f in faltantes_spy],
              'fechas_skew_ausentes': [str(f.date()) for f in df.index[df['skew'].isna()]],
              'riesgo_oos_primario': evaluar(riesgo), 'direccion_oos_secundaria': evaluar(direccion),
              'riesgo_oos_control_vol_pasada_secundario': evaluar(riesgo_control),
              'asociacion_riesgo_posterior': regression,
              'sensibilidad_multiplicidad_asociacion': {'p_asintotico': p, 'bonferroni_8': min(1, 8 * p),
                                                       'bonferroni_14': min(1, 14 * p),
                                                       'nota': 'Sensibilidades al tamaño de familia; no familia elegida después del resultado.'},
              'sensibilidad_hac': {str(k): s.ajustar(df, 'rv5_posterior', ['zskew', 'vix', 'abs_r'], k) for k in (5, 10, 20)},
              'limitaciones': ['Diseño retrospectivo: 2021–2026 ya fue examinado; requiere confirmación prospectiva.',
                               'No incluye precios de opciones ni utilidad económica después de costos.',
                               'SKEW diario no es el RR25 0DTE.',
                               'Objetivo posterior excluye el primer overnight; distinto al rv5 original.']}
    result['riesgo_por_periodo'] = {name: evaluar(riesgo[(riesgo.fecha >= start) & (riesgo.fecha <= end)])
                                   for name, start, end in [('2021-2023', '2021-01-01', '2023-12-31'),
                                                            ('2024-2026', '2024-01-01', args.hasta)]}
    args.datos.mkdir(parents=True, exist_ok=True)
    riesgo.to_csv(args.datos / 'pronosticos_riesgo_validacion.csv', index=False)
    direccion.to_csv(args.datos / 'pronosticos_direccion_validacion.csv', index=False)
    guardar(args.salida, result)
    print(json.dumps({k: v for k, v in result.items() if k.endswith('primario') or k.endswith('secundaria')}, indent=2))


if __name__ == '__main__':
    main()
