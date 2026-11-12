"""¿Se repite la ventaja de SPY en otras sesiones? Solo conteos por sesión; sin rendimientos."""
import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from quantileflow.observadas import cargar_tablas, preparar_observadas, simular_observadas
from experiments.cadena_comparador_20261010.evaluar_cadena import integridad

DIR = Path(__file__).resolve().parent
HORA, ULTIMA = '09:45', '2026-11-06'  # muestra de desarrollo del protocolo predictivo


def medir(foto):
    r = simular_observadas(foto)
    distancia = [100*(p['strike']/foto['spot']-1) for p in r['posiciones']]
    casos = {c['nombre']: sum(p['controles'][k]['nominal'] > 0 for p in r['posiciones'])
             for k, c in enumerate(r['posiciones'][0]['controles'])} if distancia else {}
    return dict(elegibles=len(distancia), strike_distancia_pct_min=min(distancia, default=None),
                a_menos_de_5_pct=sum(x < 5 for x in distancia),
                con_ganancia_mitad=casos.get('mitad'), con_ganancia_iv_menor=casos.get('iv_menor'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tablas', type=Path, required=True)
    ap.add_argument('--crudo', type=Path, required=True)
    a = ap.parse_args()
    huellas = integridad(a.tablas, a.crudo)
    cot, sub, div = cargar_tablas(a.tablas, con_dividendos=True)
    fechas = sorted(c[:10] for c in cot.captura.unique() if c.endswith('T0945') and c[:10] <= ULTIMA)
    filas = []
    for fecha in fechas:
        fila = dict(fecha=fecha)
        for raiz, extra in (('SPXW', ()), ('SPY', ('SPY', div))):
            try:
                fila[raiz] = medir(preparar_observadas(cot, sub, fecha, HORA, *extra))
            except ValueError as error:  # una foto sin referencia válida no se rellena
                fila[raiz] = dict(sin_foto=str(error))
        filas.append(fila)
    completas = [f for f in filas if 'elegibles' in f['SPXW'] and 'elegibles' in f['SPY']]
    resumen = dict(sesiones=len(filas), sesiones_con_las_dos_fotos=len(completas),
                   spy_con_mas_elegibles=sum(f['SPY']['elegibles'] > f['SPXW']['elegibles'] for f in completas),
                   spy_mas_cerca_del_dinero=sum(
                       f['SPY']['strike_distancia_pct_min'] < f['SPXW']['strike_distancia_pct_min'] for f in completas))
    for raiz in ('SPXW', 'SPY'):
        for clave in ('elegibles', 'strike_distancia_pct_min', 'a_menos_de_5_pct'):
            valores = [f[raiz][clave] for f in completas]
            resumen[f'{raiz}_{clave}'] = dict(min=min(valores), mediana=statistics.median(valores), max=max(valores))
    salida = dict(configuracion='US$300, +3% en 7 días, corte de las 09:45', resumen=resumen,
                  sesiones=filas, integridad=huellas)
    (DIR/'resultados'/'sesiones.json').write_text(
        json.dumps(salida, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')

    plt.figure()
    for raiz in ('SPXW', 'SPY'):
        plt.plot(range(len(completas)), [f[raiz]['strike_distancia_pct_min'] for f in completas], 'o-', label=raiz)
    plt.xlabel('Session number (2026-10-02 to 2026-11-06)'); plt.ylabel('Nearest strike above the reference (%)')
    plt.title('Closest call that fits USD 300, 09:45 ET captures')
    plt.legend()
    plt.savefig(DIR/'resultados'/'sesiones.png')
    plt.close()
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    for f in filas:
        print(f['fecha'], *(f[r].get('elegibles', f[r].get('sin_foto')) for r in ('SPXW', 'SPY')),
              *(None if f[r].get('strike_distancia_pct_min') is None else round(f[r]['strike_distancia_pct_min'], 2)
                for r in ('SPXW', 'SPY')), f['SPY'].get('con_ganancia_iv_menor'), f['SPXW'].get('con_ganancia_iv_menor'))


if __name__ == '__main__':
    main()
