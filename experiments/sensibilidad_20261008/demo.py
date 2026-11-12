"""Demostración sintética reproducible; precios inventados mediante un modelo."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quantileflow.escenarios import (ContratoEscenario, Escenario, comparar_contratos,
                                    sensibilidad_europea)
from quantileflow.opciones import precio_bs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--presupuesto', type=float, default=500)
    parser.add_argument('--movimiento', type=float, default=.05, help='retorno, .05 = +5%')
    parser.add_argument('--dias', type=float, default=14)
    parser.add_argument('--cambio-iv', type=float, default=0, help='absoluto: -.05 = -5 puntos de IV')
    parser.add_argument('--salida', type=Path, default=Path(__file__).with_name('ejemplo.json'))
    a = parser.parse_args()
    contratos = []
    for dte in (7, 14, 30, 60, 90):
        for K in (90, 95, 100, 105, 110, 115):
            mid = float(precio_bs(100, K, dte/365, .04, 0, .25, True))
            contratos.append(ContratoEscenario(f'C{K}_{dte}d_SINTETICO', K, dte, True, 'europeo',
                                              .25, max(0, mid-.04), mid+.04))
    escenarios = [Escenario('esperado', a.dias, a.movimiento, a.cambio_iv),
                  Escenario('adverso', a.dias+7, -.02, -.05)]
    result = comparar_contratos(contratos, 100, escenarios, a.presupuesto)
    result['contratos'].sort(key=lambda x:x['escenarios']['esperado']['pnl'], reverse=True)
    report = {'origen':'sintético, no cotizaciones de mercado', 'spot':100, 'iv':.25,
              'presupuesto':a.presupuesto, 'griegas_call_atm_30d':sensibilidad_europea(100, 100, 30, .25),
              'escenarios':[{**vars(e)} for e in escenarios], 'resultado':result}
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'griegas': report['griegas_call_atm_30d'], 'primeros': result['contratos'][:3]}, indent=2))


if __name__ == '__main__':
    main()
