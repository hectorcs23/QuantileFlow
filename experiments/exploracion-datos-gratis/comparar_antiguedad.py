"""Compara ventanas de precios sobre las señales originales, sin reseleccionar por el filtro nuevo."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import skew_0dte_alpaca as s
from validacion_comun import guardar, procedencia


def comparar(res5, res1, senales):
    filas = []
    for signal in senales.itertuples(index=False):
        fecha, t, d = pd.Timestamp(signal.fecha), int(signal.minuto), -np.sign(signal.z)
        row = {'fecha': fecha, 'minuto': t}
        for nombre, residuo in [('edad5', res5), ('edad1', res1)]:
            entrada, salida = t + s.ESPERA, t + s.ESPERA + s.HORIZONTE
            row[nombre] = d * (residuo.at[fecha, salida] - residuo.at[fecha, entrada]) if (
                fecha in residuo.index and entrada in residuo.columns and salida in residuo.columns) else np.nan
        filas.append(row)
    return pd.DataFrame(filas, columns=['fecha', 'minuto', 'edad5', 'edad1'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos', type=Path, default=s.DATOS)
    parser.add_argument('--salida', type=Path, default=s.SALIDA / 'validacion_antiguedad_pareada.json')
    args = parser.parse_args()
    archivos = [args.datos / f'rr_validacion_edad{edad}.csv' for edad in (5, 1)]
    archivos.append(args.datos / 'senales_validacion_edad5.csv')
    tables = []
    for path in archivos[:2]:
        table = pd.read_csv(path, index_col=0, parse_dates=True)
        table.columns = table.columns.astype(int)
        tables.append(table)
    if not tables[0].index.equals(tables[1].index) or not tables[0].columns.equals(tables[1].columns):
        raise ValueError('Las matrices de RR deben compartir calendario y cuadrícula')
    media5, sd5 = s.base_horaria(tables[0])
    media1, _ = s.base_horaria(tables[1])
    z5 = (tables[0] - media5) / sd5
    sesiones = [f for f in tables[0].index if np.isfinite(z5.loc[f]).any()]
    signals = pd.read_csv(archivos[2], parse_dates=['fecha'])
    all_rows = comparar(tables[0] - media5, tables[1] - media1, signals)
    paired = all_rows.dropna(subset=['edad5', 'edad1']).copy()
    paired['diferencia_5_menos_1'] = paired.edad5 - paired.edad1
    result = {'procedencia': procedencia(s.RAIZ, archivos, {'seleccion': 'señales y dirección de edad5 congeladas; base horaria propia para cada ventana'}),
              'senales_originales': len(signals), 'senales_observables_ambas': len(paired),
              'comparacion': {col: s.convergencia(paired, sesiones, col) for col in ('edad5', 'edad1', 'diferencia_5_menos_1')},
              'limitacion': 'Controla reselección de señales; no identifica ruido correlacionado ni resuelve selección por disponibilidad de ambas salidas.'}
    guardar(args.salida, result)
    print(result['comparacion'])


if __name__ == '__main__':
    main()
