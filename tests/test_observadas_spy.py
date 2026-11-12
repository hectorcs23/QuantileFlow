"""SPY en el comparador observado: ejercicio americano y dividendos conocidos al corte."""
import json
import math

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import brentq
from scipy.stats import multivariate_normal

from quantileflow.calendario import apertura, instante, instante_liquidacion
from quantileflow.observadas import (ConfiguracionObservada, call_americano, cargar_tablas,
                                    dividendos_al_corte, preparar_observadas, simular_observadas)
from quantileflow.opciones import binomial_crr
from tests.test_simulador import servidor, pedir

R = .04
CORTE = instante('2026-10-22', '09:45')
N = lambda x: (1+math.erf(x/math.sqrt(2)))/2


def bs(s, k, t, sigma):
    """Call europeo sin dividendos, con math.erf: independiente del motor."""
    d1 = (math.log(s/k)+(R+sigma*sigma/2)*t)/(sigma*math.sqrt(t))
    return s*N(d1)-k*math.exp(-R*t)*N(d1-sigma*math.sqrt(t))


def roll_geske_whaley(s, k, t, sigma, t1, d):
    """Call americano con un dividendo en efectivo: fórmula cerrada, sin árbol."""
    sx = s-d*math.exp(-R*t1)
    if d <= k*(1-math.exp(-R*(t-t1))):
        return bs(sx, k, t, sigma)
    critico = brentq(lambda x: bs(x, k, t-t1, sigma)-(x+d-k), 1e-6, 10*k)
    a1 = (math.log(sx/k)+(R+sigma*sigma/2)*t)/(sigma*math.sqrt(t))
    b1 = (math.log(sx/critico)+(R+sigma*sigma/2)*t1)/(sigma*math.sqrt(t1))
    a2, b2, rho = a1-sigma*math.sqrt(t), b1-sigma*math.sqrt(t1), -math.sqrt(t1/t)
    m = lambda a, b: multivariate_normal.cdf([a, b], mean=[0, 0], cov=[[1, rho], [rho, 1]])
    return (sx*N(b1)+sx*m(a1, -b1)-k*math.exp(-R*t)*m(a2, -b2)-(k-d)*math.exp(-R*t1)*N(b2))


def dias(vencimiento):
    return (instante_liquidacion(vencimiento, 'PM')-CORTE).total_seconds()/86400


def fila(i, strike, precio, vencimiento='2026-11-20', **cambios):
    base = dict(id_contrato=f'SPY-{i}', captura='2026-10-22T0945', raiz='SPY', subyacente='SPY',
                tipo='C', strike=strike, ejercicio='americano', liquidacion='PM', vencimiento=vencimiento,
                multiplicador=100., bid=precio-.01, ask=precio+.01, tam_bid=10., tam_ask=3.,
                proveedor='alpaca', feed='indicative', sello_evento_utc=CORTE-pd.Timedelta(seconds=1),
                sello_snapshot_utc=CORTE, disponible_utc=CORTE, recibido_utc=CORTE)
    return {**base, **cambios}


def referencia(precio=100.):
    return pd.DataFrame([dict(captura='2026-10-22T0945', subyacente='SPY', precio=precio,
                              tipo_precio='observado', feed='iex',
                              sello_evento_utc=CORTE-pd.Timedelta(seconds=1), sello_snapshot_utc=CORTE,
                              disponible_utc=CORTE, recibido_utc=CORTE)])


def dividendos(*extra):
    """Cuatro trimestres ya pagados, conocidos antes del corte, y los eventos adicionales."""
    visto = pd.Timestamp('2026-09-28T01:00:00Z')
    filas = [dict(simbolo='SPY', fecha_ex=f, monto=.25, clase='ordinario', id_evento=f'ev-{f}', version=1,
                  recibido_utc=visto, retirado_utc=pd.NaT)
             for f in ('2025-12-19', '2026-03-20', '2026-06-18', '2026-09-18')]
    base = dict(simbolo='SPY', clase='ordinario', version=1, recibido_utc=visto, retirado_utc=pd.NaT)
    return pd.DataFrame(filas+[{**base, **e} for e in extra])


@pytest.fixture
def tablas():
    t = dias('2026-11-20')/365
    return pd.DataFrame([fila(i, k, bs(100, k, t, .25)) for i, k in enumerate((103., 108.))]), referencia()


def test_sin_dividendos_el_arbol_americano_no_ejerce_y_converge_a_black_scholes():
    for k in (95., 100., 108.):
        cerrado = bs(100, k, 30/365, .2)
        assert call_americano(100, k, 30/365, R, .2) == pytest.approx(cerrado, abs=1e-12)
        for n in (200, 800):  # el error del árbol oscila, pero su cota baja como 1/n
            americano = binomial_crr(100, k, 30/365, R, .2, True, 0., (), n, True)
            europeo = binomial_crr(100, k, 30/365, R, .2, True, 0., (), n, False)
            assert americano == pytest.approx(europeo, abs=1e-12)
            assert abs(americano-cerrado) < 1/n


@pytest.mark.parametrize('s,k,t,sigma,t1,d', [
    (100., 90., .25, .2, .2, 2.), (100., 103., 39/365, .14, 20/365, .25),
    (100., 96., 39/365, .16, 20/365, .25), (100., 91., 39/365, .25, 38.8/365, .25)])
def test_con_un_dividendo_el_arbol_reproduce_roll_geske_whaley(s, k, t, sigma, t1, d):
    exacto = roll_geske_whaley(s, k, t, sigma, t1, d)
    assert call_americano(s, k, t, R, sigma, [(t1, d)]) == pytest.approx(exacto, abs=.004)
    assert abs(call_americano(s, k, t, R, sigma, [(t1, d)], pasos=1600)-exacto) < .002
    # Nunca vale menos que el europeo sobre el precio sin el dividendo, ni que ejercer hoy.
    assert exacto >= bs(s-d*math.exp(-R*t1), k, t, sigma)-1e-9 and exacto >= s-k


def test_dividendos_fuera_de_la_vida_no_cuentan_y_los_imposibles_se_rechazan():
    assert call_americano(100, 100, .1, R, .2, [(.2, 5.), (0., 5.)]) == call_americano(100, 100, .1, R, .2)
    with pytest.raises(ValueError):
        call_americano(1., 100, .1, R, .2, [(.05, 2.)])
    with pytest.raises(ValueError):
        call_americano(100, 100, .1, -.01, .2)
    with pytest.raises(ValueError, match='baja'):
        call_americano(100, 100, .1, R, 1e-4, [(.05, 2.)])


def test_spy_iv_caja_y_mapa_con_formula_independiente(tablas):
    foto = preparar_observadas(*tablas, '2026-10-22', subyacente='SPY', dividendos=dividendos())
    r = simular_observadas(foto)
    assert r['subyacente'] == 'SPY' and r['apto_compra'] is False and r['embudo']['presupuesto'] == 2
    assert r['dividendos'] == dict(conocidos_al_corte=4, declarados_futuros=[],
                                   primera_fecha_ex_sin_declarar='2026-12-10')
    assert r['reglas']['dividendo_continuo'] == 0 and 'americano' in ' '.join(r['alcance'])
    assert any('iex' in b for b in r['bloqueos'])
    for p in r['posiciones']:
        c = next(c for c in foto['registros'] if c['contrato'] == p['contrato'])
        assert c['iv'] == pytest.approx(.25, abs=1e-8) and c['iv_bid'] < c['iv'] < c['iv_ask']
        salida = max(0., bs(103, c['strike'], (c['dte']-7)/365, .25)-.01)
        esperado = p['cantidad']*(100*(salida-c['ask'])-1.30)
        assert p['controles'][0]['nominal'] == pytest.approx(esperado, abs=1e-6)
        i, j = r['ejes']['plazos_dias'].index(7), r['ejes']['movimientos_pct'].index(3)
        assert p['mapas'][1]['nominal'][i][j] == pytest.approx(esperado, abs=1e-6)
        assert p['mapas'][1]['nominal'][-1] == [None]*len(r['ejes']['movimientos_pct'])


def test_cada_subyacente_solo_admite_sus_contratos(tablas):
    q, s = tablas
    spx = pd.DataFrame([fila('X', 103., 2., raiz='SPXW', subyacente='SPX', ejercicio='europeo')])
    foto = preparar_observadas(pd.concat([q, spx]), s, '2026-10-22', subyacente='SPY', dividendos=dividendos())
    r = simular_observadas(foto)
    assert r['embudo']['calls'] == 3 and r['embudo']['modelo'] == 2
    assert next(e for e in r['exclusiones'] if e['contrato'] == 'SPY-X')['motivos'] == ['instrumento_no_admitido']
    with pytest.raises(ValueError, match='dividendos'):
        preparar_observadas(q, s, '2026-10-22', subyacente='SPY')
    with pytest.raises(ValueError, match='referencia SPX'):
        preparar_observadas(q, s, '2026-10-22')
    with pytest.raises(ValueError, match='no admitido'):
        preparar_observadas(q, s, '2026-10-22', subyacente='QQQ', dividendos=dividendos())


def test_dividendo_declarado_dentro_de_la_vida_usa_el_arbol():
    declarado = dict(fecha_ex='2026-11-13', monto=1.5, id_evento='ev-nuevo')
    t, t1 = dias('2026-11-20')/365, (apertura('2026-11-13')-CORTE).total_seconds()/86400/365
    precio = call_americano(100, 97., t, R, .25, [(t1, 1.5)])
    assert precio > bs(100-1.5*math.exp(-R*t1), 97., t, .25)+.05  # la prima de ejercicio existe
    q = pd.DataFrame([fila(0, 97., precio), fila(1, 97., precio, vencimiento='2026-11-06')])
    foto = preparar_observadas(q, referencia(), '2026-10-22', subyacente='SPY', dividendos=dividendos(declarado))
    assert foto['dividendos']['declarados_futuros'] == [dict(fecha_ex='2026-11-13', monto=1.5)]
    largo, corto = foto['registros']
    assert largo['iv'] == pytest.approx(.25, abs=1e-6) and len(largo['dividendos']) == 1
    assert corto['dividendos'] == []  # vence antes de la fecha ex: no lo cruza
    r = simular_observadas(foto, ConfiguracionObservada(presupuesto=2000, max_contratos=1))
    p = next(p for p in r['posiciones'] if p['contrato'] == 'SPY-0')
    antes = max(0., call_americano(103, 97., t-7/365, R, .25, [(t1-7/365, 1.5)])-.01)
    assert p['controles'][0]['nominal'] == pytest.approx(100*(antes-largo['ask'])-1.30, abs=1e-6)
    despues = max(0., bs(103, 97., t-28/365, .25)-.01)  # el día 28 ya pasó la fecha ex
    i, j = r['ejes']['plazos_dias'].index(28), r['ejes']['movimientos_pct'].index(3)
    assert p['mapas'][1]['nominal'][i][j] == pytest.approx(100*(despues-largo['ask'])-1.30, abs=1e-6)
    # Una IV casi nula queda fuera del dominio del árbol: la celda falta, no vale cero.
    r = simular_observadas(foto, ConfiguracionObservada(presupuesto=2000, max_contratos=1, cambio_iv_pp=-24.99))
    assert next(p for p in r['posiciones'] if p['contrato'] == 'SPY-0')['controles'][0]['nominal'] is None


@pytest.mark.parametrize('evento,futuros', [
    (dict(fecha_ex='2026-11-13', monto=1.5, id_evento='a', recibido_utc=CORTE+pd.Timedelta(seconds=1)), 0),
    (dict(fecha_ex='2026-11-13', monto=1.5, id_evento='a', retirado_utc=CORTE-pd.Timedelta(hours=1)), 0),
    (dict(fecha_ex='2026-11-13', monto=1.5, id_evento='a', retirado_utc=CORTE+pd.Timedelta(hours=1)), 1),
    (dict(fecha_ex='2026-10-22', monto=1.5, id_evento='a'), 0)])
def test_solo_cuenta_lo_conocido_al_corte(evento, futuros):
    assert len(dividendos_al_corte(dividendos(evento), 'SPY', CORTE)['futuros']) == futuros


def test_de_cada_evento_vale_la_ultima_version_conocida():
    v1 = dict(fecha_ex='2026-11-13', monto=1.5, id_evento='a', retirado_utc=CORTE-pd.Timedelta(hours=1))
    v2 = dict(fecha_ex='2026-11-13', monto=1.6, id_evento='a', version=2, recibido_utc=CORTE-pd.Timedelta(hours=1))
    v3 = dict(fecha_ex='2026-11-13', monto=9., id_evento='a', version=3, recibido_utc=CORTE+pd.Timedelta(hours=1))
    assert [m for _, m in dividendos_al_corte(dividendos(v1, v2, v3), 'SPY', CORTE)['futuros']] == [1.6]


def test_no_se_valora_lo_que_cruza_un_dividendo_sin_declarar():
    t = dias('2026-12-11')/365
    q = pd.DataFrame([fila(0, 103., bs(100, 103., t, .25), vencimiento='2026-12-11'),
                      fila(1, 103., bs(100, 103., dias('2026-12-09')/365, .25), vencimiento='2026-12-09')])
    r = simular_observadas(preparar_observadas(q, referencia(), '2026-10-22', subyacente='SPY', dividendos=dividendos()))
    assert [p['contrato'] for p in r['posiciones']] == ['SPY-1']
    assert next(e for e in r['exclusiones'] if e['contrato'] == 'SPY-0')['motivos'] == ['dividendo_esperado_sin_declarar']
    # Sin cadencia conocida no se supone que no habrá dividendo.
    poco = dividendos().iloc[:1]
    r = simular_observadas(preparar_observadas(q, referencia(), '2026-10-22', subyacente='SPY', dividendos=poco))
    assert r['posiciones'] == [] and r['motivos'] == {'historial_de_dividendos_insuficiente': 2}


def test_precio_por_debajo_del_valor_de_ejercicio_no_tiene_iv(tablas):
    q, s = tablas
    q.loc[0, ['strike', 'bid', 'ask']] = [90., 9.90, 9.95]
    r = simular_observadas(preparar_observadas(q, s, '2026-10-22', subyacente='SPY', dividendos=dividendos()))
    assert next(e for e in r['exclusiones'] if e['contrato'] == 'SPY-0')['motivos'] == ['iv_no_identificada']


def test_tablas_con_dividendos_verifican_huellas(tmp_path):
    (tmp_path/'manifiesto_normalizacion.json').write_text(
        json.dumps({'salidas': {'cotizaciones': 'no', 'subyacente': 'no'}}), encoding='utf8')
    (tmp_path/'cotizaciones.parquet').write_bytes(b'x')
    with pytest.raises(ValueError, match='Huella'):
        cargar_tablas(tmp_path, con_dividendos=True)


def test_api_sirve_la_foto_de_spy(servidor, tablas):
    servidor.foto_observada = preparar_observadas(*tablas, '2026-10-22', subyacente='SPY', dividendos=dividendos())
    try:
        status, _, cuerpo = pedir(servidor, path='/api/observadas', body='{"configuracion":{}}')
        r = json.loads(cuerpo)
        assert status == 200 and r['subyacente'] == 'SPY' and r['apto_compra'] is False
        assert np.isfinite([p['controles'][0]['nominal'] for p in r['posiciones']]).all()
    finally:
        servidor.foto_observada = None
