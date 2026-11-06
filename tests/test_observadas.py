import json
import math

import numpy as np
import pandas as pd
import pytest

from quantileflow.calendario import instante, instante_liquidacion
from quantileflow.observadas import (ConfiguracionObservada, cargar_tablas,
                                    preparar_observadas, simular_observadas)
from quantileflow.opciones import precio_bs
from tests.test_simulador import servidor, pedir


@pytest.fixture
def tablas():
    cut=instante('2026-10-22','09:45')
    dte=(instante_liquidacion('2026-11-20','PM')-cut).total_seconds()/86400
    filas=[]
    for i,k in enumerate((103.,108.)):
        mid=float(precio_bs(100,k,dte/365,.04,.013,.25))
        filas.append(dict(id_contrato=f'CALL-{i}',captura='2026-10-22T0945',raiz='SPXW',subyacente='SPX',
            tipo='C',strike=k,ejercicio='europeo',liquidacion='PM',vencimiento='2026-11-20',
            multiplicador=100.,bid=mid-.04,ask=mid+.04,tam_bid=10.,tam_ask=3.,
            proveedor='alpaca',feed='indicative',sello_evento_utc=cut-pd.Timedelta(seconds=1),
            sello_snapshot_utc=cut,disponible_utc=cut,recibido_utc=cut))
    ref=pd.DataFrame([dict(captura='2026-10-22T0945',subyacente='SPX',precio=100.,
        tipo_precio='implicito',feed='implicito_paridad_SPXW_indicative',
        sello_evento_utc=cut-pd.Timedelta(seconds=1),sello_snapshot_utc=cut,disponible_utc=cut,recibido_utc=cut)])
    return pd.DataFrame(filas),ref


@pytest.fixture
def foto(tablas):
    return preparar_observadas(*tablas,'2026-10-22')


def precio_independiente(s,k,t,sigma):
    d1=(math.log(s/k)+(.04-.013+sigma*sigma/2)*t)/(sigma*math.sqrt(t));d2=d1-sigma*math.sqrt(t)
    N=lambda x:(1+math.erf(x/math.sqrt(2)))/2
    return s*math.exp(-.013*t)*N(d1)-k*math.exp(-.04*t)*N(d2)


def test_iv_caja_y_mapa_con_formula_independiente(foto):
    r=simular_observadas(foto)
    assert r['embudo']['presupuesto']==2 and r['apto_compra'] is False
    for p in r['posiciones']:
        c=next(c for c in foto['registros'] if c['contrato']==p['contrato'])
        assert c['iv']==pytest.approx(.25,abs=1e-9)
        assert p['cantidad']<=3
        assert p['capital_reservado']+p['efectivo_libre']==pytest.approx(300)
        assert p['capital_reservado']<=300
        salida=max(0.,precio_independiente(103,c['strike'],(c['dte']-7)/365,.25)-.04)
        expected=p['cantidad']*(100*(salida-c['ask'])-1.30)
        assert p['controles'][0]['nominal']==pytest.approx(expected,abs=1e-8)
        i=r['ejes']['plazos_dias'].index(7);j=r['ejes']['movimientos_pct'].index(3)
        assert p['mapas'][1]['nominal'][i][j]==pytest.approx(expected,abs=1e-8)
        for a,b,z in zip(p['mapas'][1]['inferior'],p['mapas'][1]['nominal'],p['mapas'][1]['superior']):
            for lo,mid,hi in zip(a,b,z):
                if mid is not None: assert lo<=mid+1e-8<=hi+1e-8


def test_cantidades_fijas_y_limite_tamano(foto):
    a=simular_observadas(foto,ConfiguracionObservada(presupuesto=10000))
    b=simular_observadas(foto,ConfiguracionObservada(presupuesto=10000,movimiento_pct=9,dias=3,cambio_iv_pp=5))
    assert all(p['cantidad']==3 for p in a['posiciones'])
    assert [p['capital_reservado'] for p in a['posiciones']]==[p['capital_reservado'] for p in b['posiciones']]
    assert simular_observadas(foto,ConfiguracionObservada(riesgo_pct=0))['posiciones']==[]
    assert all(p['cantidad']==1 for p in simular_observadas(foto,ConfiguracionObservada(max_contratos=1))['posiciones'])


def test_ab_misma_serie_dos_cantidades_no_se_colapsan(foto):
    ids=[dict(contrato='CALL-1',cantidad=i) for i in (1,2)]
    r=simular_observadas(foto,alternativas=ids)
    assert len(r['posiciones'])==2
    assert r['mejor_objetivo']==r['mejores_nominales'][0]
    for a,b in zip(*[p['controles'] for p in r['posiciones']]):
        assert b['nominal']==pytest.approx(2*a['nominal'])
    with pytest.raises(ValueError):simular_observadas(foto,alternativas=[ids[0],dict(contrato='CALL-1',cantidad=4)])


@pytest.mark.parametrize('col,valor,motivo',[
    ('bid',-1.,'precio_o_multiplicador_invalido'),('ask',float('nan'),'precio_o_multiplicador_invalido'),
    ('tam_ask',0.,'sin_tamano'),('bid',0.,'spread_amplio'),('multiplicador',99.,'precio_o_multiplicador_invalido'),
    ('ejercicio','americano','instrumento_no_admitido'),('feed','misterio','fuente_no_admitida'),
    ('sello_evento_utc',pd.Timestamp('2026-10-22T13:43:00Z'),'precio_antiguo'),
    ('disponible_utc',pd.Timestamp('2026-10-22T13:45:01Z'),'sello_ausente_o_futuro')])
def test_exclusiones_sin_rellenar_valores(tablas,col,valor,motivo):
    q,s=tablas;q.loc[0,col]=valor
    r=simular_observadas(preparar_observadas(q,s,'2026-10-22'))
    assert motivo in next(e for e in r['exclusiones'] if e['contrato']=='CALL-0')['motivos']
    assert all(p['contrato']!='CALL-0' for p in r['posiciones'])


def test_no_incidentalmente_sip_publicado_despues(tablas):
    q,s=tablas
    extra=s.copy();extra['subyacente']='SPY';extra['precio']=9999.;extra['disponible_utc']=pd.Timestamp('2026-10-22T14:00:00Z')
    assert preparar_observadas(q,pd.concat([s,extra]),'2026-10-22')['spot']==100
    s['disponible_utc']=pd.Timestamp('2026-10-22T14:00:00Z')
    with pytest.raises(ValueError,match='disponible'):preparar_observadas(q,s,'2026-10-22')


def test_vencido_o_iv_invalida_no_son_cero(foto):
    r=simular_observadas(foto,ConfiguracionObservada(dias=28,cambio_iv_pp=-30))
    assert r['mejores_nominales'][0] is None
    for p in r['posiciones']:
        assert p['controles'][0]['nominal'] is None
        assert p['controles'][5]['nominal'] is None
        assert all(v is None for v in p['mapas'][1]['nominal'][-1])


def test_expiracion_exacta_payoff_y_sin_spread(foto):
    from quantileflow.observadas import _valores
    c=next(c for c in foto['registros'] if not c['motivos'])
    z=_valores(c,100.,2,ConfiguracionObservada(),c['dte'],6.,-100.)
    expected=2*(100*(max(106-c['strike'],0)-c['ask'])-1.3)
    assert all(float(v)==pytest.approx(expected) for v in z.values())


def test_tablas_alteradas_se_rechazan(tmp_path):
    (tmp_path/'manifiesto_normalizacion.json').write_text(json.dumps({'salidas':{'cotizaciones':'no','subyacente':'no'}}),encoding='utf8')
    (tmp_path/'cotizaciones.parquet').write_bytes(b'changed')
    with pytest.raises(ValueError,match='Huella'):cargar_tablas(tmp_path)


def test_api_observada_no_inventa_captura_y_rechaza_rutas(servidor,foto):
    status,_,_=pedir(servidor,path='/api/observadas',body='{"configuracion":{}}')
    assert status==409
    servidor.foto_observada=foto
    try:
        status,_,b=pedir(servidor,path='/api/observadas',body='{"configuracion":{}}')
        assert status==200 and json.loads(b)['apto_compra'] is False
        assert pedir(servidor,path='/api/observadas',body='{"configuracion":{},"ruta":"secret"}')[0]==400
        assert pedir(servidor,path='/observadas',method='GET')[0]==200
        assert pedir(servidor,path='/cotizaciones.parquet',method='GET')[0]==404
        assert pedir(servidor,path='/api/observadas',body='{"configuracion":{}}',headers={'Content-Type':'application/json','Origin':'https://externo.invalid'})[0]==403
    finally:servidor.foto_observada=None


@pytest.mark.parametrize('cfg',[{'presupuesto':True},{'dias':1.5},{'cambio_iv_pp':float('nan')},{'spot':100}])
def test_configuracion_valida(cfg):
    with pytest.raises(ValueError):ConfiguracionObservada.desde_dict(cfg)
