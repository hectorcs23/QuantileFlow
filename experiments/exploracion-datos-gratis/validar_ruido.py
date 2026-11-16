"""Contraejemplo de identificación. Son datos simulados, nunca resultados de mercado."""
from pathlib import Path
import numpy as np
import pandas as pd
import skew_0dte_alpaca as s
from validacion_comun import guardar


def simular():
    rng = np.random.default_rng(1729)
    dias, slots, rho = 800, 75, .90
    errores = np.empty((dias, slots))
    errores[:, 0] = rng.normal(size=dias)
    for i in range(1, slots):
        errores[:, i] = rho * errores[:, i - 1] + np.sqrt(1 - rho**2) * rng.normal(size=dias)
    fechas = pd.bdate_range('2020-01-01', periods=dias)
    minutos = range(580, 955, 5)
    tabla = pd.DataFrame(4. + errores, index=fechas, columns=minutos)
    residuo, z, senales = s.senales_y_residuos(tabla, dict.fromkeys(fechas, 960))
    sesiones = [f for f in fechas if np.isfinite(z.loc[f]).any()]
    resultado = {'tipo': 'SIMULACIÓN: no datos de mercado', 'semilla': 1729, 'dias': dias,
                 'skew_economico_verdadero': 4., 'rho_error_medicion': rho,
                 'retrasada': s.convergencia(senales, sesiones, 'operable'),
                 'ingenua': s.convergencia(senales, sesiones, 'ingenua'),
                 'conclusion': 'Convergencia retrasada positiva puede originarse enteramente en ruido autocorrelacionado. No identifica reversión económica.'}
    # The identical observations also admit a latent AR skew with zero measurement error.
    resultado['modelos_observacionalmente_equivalentes'] = ['Skew fijo + error AR(.90)', 'Skew AR(.90) + error cero']
    return resultado


if __name__ == '__main__':
    output = Path(__file__).resolve().parent / 'resultados' / 'validacion_ruido.json'
    result = simular()
    guardar(output, result)
    print(result)
