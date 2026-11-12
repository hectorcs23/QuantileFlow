"""SPY frente a SPXW con US$300 en una foto histórica. Nada individual se publica en Git."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from quantileflow.calendario import instante
from quantileflow.observadas import (ConfiguracionObservada, cargar_tablas, preparar_observadas,
                                    simular_observadas)
from quantileflow.opciones import binomial_crr
from experiments.cadena_comparador_20261010.evaluar_cadena import integridad

DIR = Path(__file__).resolve().parent
FECHA, HORA, TASA = '2026-10-22', '09:45', .04
PRESUPUESTOS = (100., 200., 300., 500.)
ESCENARIOS = ['+3%, 7 d', '+1.5%, 7 d', 'Flat, 7 d', '-3%, 7 d', '+3%, IV -5', '+3%, 14 d', '+1.5%, 14 d, IV -5']


def dump(ruta, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def bs(s, k, t, v):
    """Call europeo sin dividendos con math.erf: no comparte código con el motor."""
    d1 = (math.log(s/k)+(TASA+v*v/2)*t)/(v*math.sqrt(t))
    n = lambda x: (1+math.erf(x/math.sqrt(2)))/2
    return s*n(d1)-k*math.exp(-TASA*t)*n(d1-v*math.sqrt(t))


def verificar(foto, r):
    """Recalcula caja, inversiones de IV y todas las celdas de SPY con otra fórmula."""
    cfg, errores, celdas, ausentes, inversiones = r['configuracion'], [], 0, 0, 0
    registros = {c['contrato']: c for c in foto['registros']}
    capital = cfg['presupuesto']*cfg['riesgo_pct']/100
    for p in r['posiciones']:
        c, n = registros[p['contrato']], p['cantidad']
        assert c['dividendos'] == [], 'la fórmula sin dividendos no vale para este contrato'
        assert n == min(math.floor(capital/(100*c['ask']+2*cfg['comision'])), c['tam_ask'])
        assert p['capital_reservado'] <= capital and p['efectivo_libre'] >= 0
        for clave, precio in (('iv_bid', c['bid']), ('iv', (c['bid']+c['ask'])/2), ('iv_ask', c['ask'])):
            errores.append(abs(bs(foto['spot'], c['strike'], c['dte']/365, c[clave])-precio))
            inversiones += 1
        for mapa, choque in zip(p['mapas'], r['ejes']['choques_iv_pp']):
            for banda, iv, factor in (('nominal', c['iv'], 1), ('inferior', c['iv_bid'], 2), ('superior', c['iv_ask'], 1)):
                for i, d in enumerate(r['ejes']['plazos_dias']):
                    for j, m in enumerate(r['ejes']['movimientos_pct']):
                        visto, resta = mapa[banda][i][j], c['dte']-d
                        if resta < -1e-10 or (resta > 1e-10 and iv+choque/100 <= 0):
                            assert visto is None
                            ausentes += 1
                            continue
                        s = foto['spot']*(1+m/100)
                        valor = (max(0., s-c['strike']) if abs(resta) <= 1e-10 else
                                 max(0., bs(s, c['strike'], resta/365, iv+choque/100)-factor*(c['ask']-c['bid'])/2))
                        errores.append(abs(n*(100*(valor-c['ask'])-2*cfg['comision'])-visto))
                        celdas += 1
                        assert visto >= -p['capital_reservado']-1e-7
    assert max(errores) < 1e-6
    return dict(celdas_con_valor=celdas, celdas_ausentes_verificadas=ausentes, inversiones_comprobadas=inversiones,
                error_maximo_abs=max(errores), formula='Black–Scholes sin dividendos con math.erf')


def control_arbol(foto, r):
    """Árbol americano de cada candidato con su IV: no ejerce antes y converge al precio cerrado."""
    registros = {c['contrato']: c for c in foto['registros']}
    primas, errores = [], {400: [], 1600: []}
    for p in r['posiciones']:
        c = registros[p['contrato']]
        cerrado = bs(foto['spot'], c['strike'], c['dte']/365, c['iv'])
        for pasos in errores:
            args = (foto['spot'], c['strike'], c['dte']/365, TASA, c['iv'], True, 0., (), pasos)
            americano = binomial_crr(*args, americana=True)
            primas.append(abs(americano-binomial_crr(*args, americana=False)))
            errores[pasos].append(abs(americano-cerrado))
    assert max(primas) < 1e-9 and max(errores[1600]) < max(errores[400]) < .01
    return dict(contratos=len(r['posiciones']), prima_ejercicio_anticipado_max=max(primas),
                error_max_400_pasos=max(errores[400]), error_max_1600_pasos=max(errores[1600]),
                nota='Sin dividendos en la vida de ningún candidato: el árbol confirma que el call americano '
                     'vale lo que el europeo. Error en dólares por acción.')


def casos(posiciones, r):
    filas = []
    for k, caso in enumerate(posiciones[0]['controles']):
        nominal = [p['controles'][k]['nominal'] for p in posiciones]
        inferior = [p['controles'][k]['inferior'] for p in posiciones]
        filas.append(dict(nombre=caso['nombre'],
                          positivas_nominal=sum(x is not None and x > 0 for x in nominal),
                          positivas_banda_inferior=sum(x is not None and x > 0 for x in inferior),
                          faltantes=sum(x is None for x in nominal),
                          ganador_efectivo=r['mejores_nominales'][k] == ['efectivo'],
                          ganador_separado=bool(r['separados_banda'][k])))
    return filas


def describir(foto, r):
    """Agregados de una raíz: embudo propio, alcance de los candidatos y escenarios."""
    posiciones, spot = r['posiciones'], foto['spot']
    registros = {c['contrato']: c for c in foto['registros']}
    propios = [e for e in r['exclusiones'] if 'instrumento_no_admitido' not in e['motivos']]
    motivos = {}
    for e in propios:
        for m in e['motivos']:
            motivos[m] = motivos.get(m, 0)+1
    distancia = [100*(p['strike']/spot-1) for p in posiciones]
    spread = [100*(registros[p['contrato']]['ask']-registros[p['contrato']]['bid'])
              / ((registros[p['contrato']]['ask']+registros[p['contrato']]['bid'])/2) for p in posiciones]
    return dict(subyacente=r['subyacente'], referencia=r['referencia'], bloqueos=r['bloqueos'],
                embudo=dict(calls=r['embudo']['modelo'], calidad=r['embudo']['calidad'],
                            horizonte=r['embudo']['horizonte'], presupuesto=r['embudo']['presupuesto']),
                motivos=motivos, casos=casos(posiciones, r),
                dte_min=min(p['dte'] for p in posiciones), dte_max=max(p['dte'] for p in posiciones),
                strike_distancia_pct_min=min(distancia), strike_distancia_pct_mediana=statistics.median(distancia),
                strike_distancia_pct_max=max(distancia),
                candidatos_a_menos_de_5_pct=sum(x < 5 for x in distancia),
                spread_relativo_pct_mediana=statistics.median(spread),
                ganador_cambia_con_retraso=r['mejores_nominales'][0] != r['mejores_nominales'][5]), distancia


def union(grupos):
    """¿Alguna compra supera las bandas de todas las demás, de las dos raíces, y al efectivo?"""
    todas = [(nombre, p) for nombre, r in grupos for p in r['posiciones']]
    filas = []
    for k, caso in enumerate(todas[0][1]['controles']):
        nominal = [(p['controles'][k]['nominal'], nombre) for nombre, p in todas]
        mejor = max(nominal)
        separada = any(p['controles'][k]['inferior'] > .01+max([0.]+[q['controles'][k]['superior']
                       for j, (_, q) in enumerate(todas) if j != i]) for i, (_, p) in enumerate(todas))
        filas.append(dict(nombre=caso['nombre'], compras=len(todas),
                          mayor_nominal='efectivo' if mejor[0] <= 0 else mejor[1], ganador_separado=separada))
    return filas


def referencia_sip(subyacente, corte):
    """Auditoría posterior: el consolidado llegó después del corte y no entra en la decisión."""
    sip = subyacente[(subyacente.subyacente == 'SPY') & (subyacente.feed == 'sip')].copy()
    sip['evento'] = pd.to_datetime(sip.sello_evento_utc, utc=True)
    sip = sip[sip.evento <= corte].sort_values('evento')
    if sip.empty or (corte-sip.evento.iloc[-1]).total_seconds() > 5:
        return None
    return float(sip.precio.iloc[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for nombre in ('tablas', 'crudo', 'privado'):
        ap.add_argument('--'+nombre, type=Path, required=True)
    a = ap.parse_args()
    priv = a.privado.resolve()
    if priv.is_relative_to(ROOT) or any(priv.is_relative_to(x.resolve()) or x.resolve().is_relative_to(priv)
                                         for x in (a.tablas, a.crudo)):
        raise ValueError('La salida privada debe estar separada de código y entradas')
    priv.mkdir(parents=True, exist_ok=True)
    out = DIR/'resultados'
    out.mkdir(exist_ok=True)
    huellas = integridad(a.tablas, a.crudo)
    cot, sub, div = cargar_tablas(a.tablas, con_dividendos=True)
    cfg = ConfiguracionObservada()
    fotos = dict(SPXW=preparar_observadas(cot, sub, FECHA, HORA),
                 SPY=preparar_observadas(cot, sub, FECHA, HORA, 'SPY', div))
    resultados = {raiz: simular_observadas(foto, cfg) for raiz, foto in fotos.items()}
    dump(priv/'analisis_spy.json', resultados['SPY'])

    resumen = dict(fecha_analisis='2026-11-12', captura=resultados['SPY']['captura'], configuracion=asdict(cfg),
                   apto_compra=False, dividendos_spy=resultados['SPY']['dividendos'],
                   reglas_spy=resultados['SPY']['reglas'], raices={})
    distancias = {}
    for raiz, r in resultados.items():
        resumen['raices'][raiz], distancias[raiz] = describir(fotos[raiz], r)
    resumen['union'] = union(list(resultados.items()))

    resumen['sensibilidad_presupuesto'] = []
    for presupuesto in PRESUPUESTOS:
        fila = dict(presupuesto=presupuesto)
        for raiz, foto in fotos.items():
            ps = simular_observadas(foto, ConfiguracionObservada(presupuesto=presupuesto))['posiciones']
            fila[raiz] = dict(elegibles=len(ps), strike_distancia_pct_min=min(
                (100*(p['strike']/foto['spot']-1) for p in ps), default=None))
        resumen['sensibilidad_presupuesto'].append(fila)

    # La referencia de SPY es el punto medio de IEX. Se repite todo en su bid y en su ask.
    ref = sub[(sub.captura == fotos['SPY']['captura']) & (sub.subyacente == 'SPY')].iloc[0]
    sip = referencia_sip(sub, instante(FECHA, HORA))
    sensibilidad = []
    for nombre, precio in (('bid', float(ref.bid)), ('medio', float(ref.precio)), ('ask', float(ref.ask))):
        movida = sub.copy()
        movida.loc[(movida.captura == fotos['SPY']['captura']) & (movida.subyacente == 'SPY'), 'precio'] = precio
        r = simular_observadas(preparar_observadas(cot, movida, FECHA, HORA, 'SPY', div), cfg)
        sensibilidad.append(dict(referencia=nombre, distancia_al_medio_pct=100*(precio/float(ref.precio)-1),
                                 elegibles=len(r['posiciones']),
                                 positivas_nominal=[x['positivas_nominal'] for x in casos(r['posiciones'], r)]))
    resumen['referencia_spy'] = dict(
        iex_spread_pct=100*(float(ref.ask)-float(ref.bid))/float(ref.precio), sensibilidad=sensibilidad,
        sip_posterior_menos_iex_pct=None if sip is None else 100*(sip/float(ref.precio)-1),
        nota='El SIP se publicó después del corte: solo audita la referencia, no entra en ningún cálculo.')

    resumen.update(integridad=huellas, verificacion_numerica=verificar(fotos['SPY'], resultados['SPY']),
                   control_arbol=control_arbol(fotos['SPY'], resultados['SPY']),
                   analisis_privado_sha256=hashlib.sha256((priv/'analisis_spy.json').read_bytes()).hexdigest())
    dump(out/'resumen.json', resumen)

    plt.figure()
    for raiz in fotos:
        plt.plot(PRESUPUESTOS, [f[raiz]['elegibles'] for f in resumen['sensibilidad_presupuesto']], 'o-', label=raiz)
    plt.xlabel('Budget (USD)'); plt.ylabel('Comparable calls')
    plt.title('Calls that fit the budget, capture of 2026-10-22 09:45 ET')
    plt.legend()
    plt.savefig(out/'presupuesto.png')
    plt.close()

    plt.figure()
    plt.hist([distancias[raiz] for raiz in fotos], bins=range(0, 24, 2), label=list(fotos))
    plt.xlabel('Strike distance above the reference (%)'); plt.ylabel('Comparable calls')
    plt.title('How far out of the money the USD 300 candidates are')
    plt.legend()
    plt.savefig(out/'distancia.png')
    plt.close()

    plt.figure()
    for desplazamiento, raiz in ((-.2, 'SPXW'), (.2, 'SPY')):
        d = resumen['raices'][raiz]
        plt.bar([k+desplazamiento for k in range(7)],
                [100*c['positivas_nominal']/d['embudo']['presupuesto'] for c in d['casos']], width=.4, label=raiz)
    plt.xticks(range(7), ESCENARIOS, rotation=30, ha='right')
    plt.xlabel('Imposed exit scenario'); plt.ylabel('Candidates with a nominal gain (%)')
    plt.title('Share of USD 300 candidates that gain in each scenario')
    plt.legend()
    plt.subplots_adjust(bottom=.3)
    plt.savefig(out/'escenarios.png')
    plt.close()

    print(json.dumps({k: resumen[k] for k in ('raices', 'union', 'sensibilidad_presupuesto', 'referencia_spy',
                                              'verificacion_numerica', 'control_arbol')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
