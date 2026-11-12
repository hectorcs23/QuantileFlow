"""Pruebas de caja y valoración sin reutilizar el repricing del simulador como oráculo."""
from dataclasses import replace
from math import erf, exp, log, sqrt
import json
import pytest
from quantileflow.duelo import comparar_dos
from quantileflow.simulador import ConfiguracionSimulador
from tests.test_simulador import servidor, pedir

E=[dict(contrato='C103-14d',cantidad=3),dict(contrato='C103-60d',cantidad=1)]
CFG=ConfiguracionSimulador()

def call(s,k,t,iv):
    if t==0:return max(s-k,0.)
    v=iv*sqrt(t)
    d=(log(s/k)+(.04-.013+iv*iv/2)*t)/v
    cdf=lambda x:(1+erf(x/sqrt(2)))/2
    return s*exp(-.013*t)*cdf(d)-k*exp(-.04*t)*cdf(d-v)

def test_matriz_con_oraculo_independiente():
    r=comparar_dos(CFG,E)
    for j,(n,dte) in enumerate([(3,14),(1,60)]):
        a=r['alternativas'][j]
        ask=call(100,103,dte/365,.25)+.04
        coste=n*(100*ask+1.3)
        assert a['capital_reservado']==pytest.approx(coste)
        assert a['efectivo_libre']+coste==pytest.approx(300)
        for s in r['escenarios']:
            rem=(dte-s['dias'])/365
            valor=call(100*(1+s['movimiento_pct']/100),103,rem,s['iv_salida_pct']/100)
            venta=max(0.,valor-(.04 if rem else 0.))
            v=s['valores'][j]
            assert v['pnl']==pytest.approx(n*100*venta-coste,abs=2e-8)
            assert v['capital_final']==pytest.approx(300+v['pnl'])
        spot=a['equilibrio']['spot']
        assert call(spot,103,(dte-7)/365,.25)==pytest.approx(ask+.013+.04,abs=1e-10)
    filas={s['id']:s for s in r['escenarios']}
    assert [filas[k]['mejores'] for k in ('objetivo','mitad','sin_movimiento','tarde','combinado')]==[['A'],['B'],['Efectivo'],['B'],['Efectivo']]

def test_cantidad_explicita_y_empate():
    r=comparar_dos(CFG,[E[0],dict(E[0],cantidad=1)])
    assert r['alternativas'][1]['max_cantidad']==3
    for s in r['escenarios']: assert s['valores'][0]['pnl']==pytest.approx(3*s['valores'][1]['pnl'])
    assert comparar_dos(CFG,[E[0],E[0]])['escenarios'][0]['mejores']==['A','B']

def test_vencimiento_reserva_e_ausencia():
    r=comparar_dos(replace(CFG,dias=14),E);a=r['alternativas'][0]
    assert a['equilibrio']['spot']==pytest.approx(103+a['prima_por_contrato']/100+.013)
    assert r['escenarios'][0]['valores'][0]['pnl']==pytest.approx(-a['capital_reservado'])
    late=next(s for s in r['escenarios'] if s['id']=='tarde')
    assert late['valores'][0]['pnl'] is None and late['valores'][1]['pnl'] is not None
    assert late['mejores'] is None and late['diferencia_a_menos_b'] is None

@pytest.mark.parametrize('cfg,elecciones',[
    (CFG,[dict(E[0],cantidad=4),E[1]]),(replace(CFG,riesgo_pct=50),E),
    (replace(CFG,max_contratos=2),E),(replace(CFG,dias=15),E),
    (CFG,[dict(E[0],cantidad=True),E[1]]),(CFG,[dict(E[0],cantidad=1.2),E[1]]),
    (CFG,[dict(E[0],cantidad=0),E[1]]),(CFG,[dict(E[0],contrato='XXX'),E[1]]),(CFG,[]),
])
def test_rechaza_sin_reducir_en_silencio(cfg,elecciones):
    with pytest.raises(ValueError):comparar_dos(cfg,elecciones)

def test_api_duelo(servidor):
    path='/api/comparar-dos'
    payload=dict(configuracion={},alternativas=E)
    status,_,raw=pedir(servidor,path=path,body=json.dumps(payload))
    assert status==200 and json.loads(raw)==comparar_dos(CFG,E)
    assert pedir(servidor,path=path,body=json.dumps(dict(payload,alternativas=[E[0],dict(E[1],cantidad=2)])))[0]==400
    assert pedir(servidor,path=path,body='{}')[0]==400
