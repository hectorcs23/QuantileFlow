"""Reanaliza una ventana explícita sin convertir convergencia VWAP en beneficio ejecutable."""
from __future__ import annotations
import argparse
import gzip
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import skew_0dte_alpaca as s
from validacion_comun import guardar, procedencia
sys.path.insert(0, str(s.RAIZ))
from quantileflow.calendario import calendario


def comparaciones(senales, sesiones, cierres):
    """Paired cohort, horizon coverage, and an observable missing-exit sensitivity."""
    pares = senales.dropna(subset=['ingenua', 'operable']).copy()
    pares['diferencia'] = pares['ingenua'] - pares['operable']
    cols = ['operable_10', 'operable_20', 'operable', 'operable_45']
    # Eligibility is fixed by the exchange close, before conditioning on observed exits.
    elegibles = senales[senales.apply(lambda r: r['minuto'] + s.ESPERA + 45 <= cierres[r['fecha']] - 10, axis=1)] if len(senales) else senales
    comunes = elegibles.dropna(subset=cols)
    sensibilidad = senales.copy()
    sensibilidad['retrasada_cero_si_falta'] = sensibilidad['operable'].fillna(0)
    return {'pares_ingenua_retrasada': {col: s.convergencia(pares, sesiones, col)
                                      for col in ('ingenua', 'operable', 'diferencia')},
            'horizontes_misma_cohorte': {col: s.convergencia(comunes, sesiones, col) for col in cols},
            'senales_elegibles_hasta_45': len(elegibles),
            'senales_con_todos_los_horizontes': len(comunes),
            'faltantes_por_horizonte': {col: int(elegibles[col].isna().sum()) for col in cols},
            'sensibilidad_cero_si_falta': s.convergencia(sensibilidad, sesiones, 'retrasada_cero_si_falta'),
            'nota_sensibilidad': 'Escenario, no imputación de datos ni límite inferior: las salidas ausentes podrían ser negativas.',
            'faltantes_30_por_z': {nombre: {'total': len(g), 'sin_salida': int(g.operable.isna().sum())}
                                 for nombre, g in [('2<=|z|<3', senales[senales.z.abs() < 3]),
                                                   ('|z|>=3', senales[senales.z.abs() >= 3])]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desde', default='2024-02-01')
    parser.add_argument('--hasta', default='2026-10-01')
    parser.add_argument('--datos', type=Path, default=s.DATOS)
    parser.add_argument('--antiguedad-maxima', type=int, choices=(1, 5), default=5)
    parser.add_argument('--salida', type=Path)
    args = parser.parse_args()
    if args.salida is None:
        args.salida = s.SALIDA / ('validacion_0dte.json' if args.antiguedad_maxima == 5 else 'validacion_0dte_edad1.json')
    cal = calendario('XNYS')
    fechas = cal.sessions_in_range(args.desde, args.hasta).tz_localize(None)
    cierres, filas, inventario, archivos = {}, {}, [], []
    for i, fecha in enumerate(fechas):
        cierre = cal.session_close(fecha).tz_convert(s.NY)
        cierres[fecha] = cierre.hour * 60 + cierre.minute
        path = args.datos / f'{fecha.date()}.json.gz'
        if not path.exists():
            inventario.append({'fecha': str(fecha.date()), 'estado': 'ausente'})
            continue
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            registro = json.load(f)
        if pd.Timestamp(registro['fecha']) != fecha or pd.Timestamp(registro['cierre_utc']) != cierre:
            raise ValueError(f'Fecha o cierre incompatible con XNYS: {path.name}')
        archivos.append(path)
        filas[fecha] = s.rr_de_la_sesion(registro, antiguedad_maxima=args.antiguedad_maxima)
        inventario.append({'fecha': str(fecha.date()), 'estado': 'rr_disponible' if len(filas[fecha]) else 'sin_rr'})
        if (i + 1) % 50 == 0:
            print(f'{i + 1}/{len(fechas)} sesiones examinadas', flush=True)
    if not archivos:
        raise SystemExit('Sin archivos originales en la ventana solicitada; no hay resultado de mercado.')
    tabla = pd.DataFrame(filas).T.reindex(index=fechas, columns=range(s.PRIMER_MINUTO, 951, s.PASO))
    for fecha in fechas:
        tabla.loc[fecha, tabla.columns > cierres[fecha] - 10] = np.nan
    residuo, z, senales = s.senales_y_residuos(tabla, cierres)
    sesiones = [f for f in fechas if np.isfinite(z.loc[f]).any()]
    config = {'desde': args.desde, 'hasta': args.hasta, 'antiguedad_maxima': args.antiguedad_maxima,
              'paso': s.PASO, 'primer_minuto': s.PRIMER_MINUTO, 'ultima_senal_antes_cierre': s.ULTIMA_SENAL_ANTES,
              'base_sesiones': s.BASE_SESIONES, 'base_minimo': s.BASE_MINIMO, 'umbral_z': s.UMBRAL_Z,
              'espera': s.ESPERA, 'horizonte': s.HORIZONTE, 'horizontes_secundarios': s.HORIZONTES_SECUNDARIOS,
              'delta': s.DELTA, 'hueco_delta': s.HUECO_DELTA, 'tasa': s.TASA, 'precio_minimo': s.PRECIO_MINIMO,
              'modelo': 'Black-Scholes europeo, sin dividendos, ACT/365 hasta cierre XNYS',
              'bootstrap': {'bloque': 10, 'repeticiones': 3000, 'semilla': 1729}}
    resultado = {'procedencia': procedencia(s.RAIZ, archivos, config),
                 'periodo': [args.desde, args.hasta], 'sesiones_esperadas': len(fechas),
                 'archivos_presentes': len(archivos), 'calendario': inventario,
                 'todo': s.resumir(tabla, z, senales), 'comparaciones': comparaciones(senales, sesiones, cierres),
                 'persistencia_descriptiva': s.persistencia(residuo),
                 'limitaciones': ['VWAP de operaciones; patas asincrónicas; ruido autocorrelacionado no identificado.',
                                  'Contratos interpolados cambian entre tiempos; no es P&L de contratos fijos.',
                                  'Ausencias pueden depender del resultado; comparar cohortes no elimina ese sesgo.',
                                  'No se identifica reversión económica, vida media latente ni rentabilidad neta.']}
    resultado['por_anio'] = {str(y): s.resumir(tabla, z, senales, lambda f, y=y: f.year == y) for y in sorted(set(fechas.year))}
    def cobertura(calendario_sesiones):
        posibles = sum(sum(m <= cierres[f] - 10 for m in tabla.columns) for f in calendario_sesiones)
        observados = int(tabla.loc[calendario_sesiones].notna().sum().sum())
        return {'puntos_observados': observados, 'puntos_calendario': posibles,
                'fraccion': observados / posibles if posibles else None}
    resultado['cobertura_calendario'] = cobertura(list(fechas))
    resultado['cobertura_con_base'] = cobertura(sesiones)
    resultado['nota_cobertura'] = 'Denominador excluye puntos posteriores al cierre temprano; la clave histórica cobertura_rr usa una tabla rectangular.'
    # Raw-derived artifacts stay beside the input data, outside public Git.
    tabla.to_csv(args.datos / f'rr_validacion_edad{args.antiguedad_maxima}.csv')
    senales.to_csv(args.datos / f'senales_validacion_edad{args.antiguedad_maxima}.csv', index=False)
    guardar(args.salida, resultado)
    print(json.dumps({'salida': str(args.salida), 'todo': resultado['todo']}, default=str, indent=2))


if __name__ == '__main__':
    main()
