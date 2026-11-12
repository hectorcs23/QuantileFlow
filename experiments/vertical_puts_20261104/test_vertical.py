import numpy as np
import pandas as pd
import pytest
from types import SimpleNamespace
from experiments.vertical_puts_20261104.metodo import banda,cambio,seleccionar,signo,resumen,sincronas
from experiments.vertical_puts_20261104.evaluar import analizar,instante


def test_extremos_put_call_y_descuento():
    assert banda('P',(1,2),(6,7),.5,20)==pytest.approx([.4,.6])
    assert banda('C',(15,16),(10,11),.5,20)==pytest.approx([.4,.6])


def test_vertical_es_promedio_cdf_con_atomos():
    estados=np.array([80.,100.,120.]);masa=np.array([.3,.4,.3]);kl,kh,D=90.,110.,.98
    low=D*(np.maximum(kl-estados,0)@masa);high=D*(np.maximum(kh-estados,0)@masa)
    assert (high-low)/(D*(kh-kl))==pytest.approx((.3*10+.7*10)/20)


def test_punto_medio_cambia_pero_no_supera_bid_ask():
    r=resumen([.2,.35],[.25,.4],1e-7)
    assert r['punto_medio']==pytest.approx(.05) and r['signo']=='incluye_cero'
    assert r['cambio']==pytest.approx([-.1,.2])


def test_signo_y_banda_fisica_incompatible():
    assert signo(cambio([.2,.3],[.4,.5]),1e-7)=='sube'
    assert signo(cambio([.4,.5],[.2,.3]),1e-7)=='baja'
    assert resumen([1.01,1.03],[.95,1.03],1e-7)['signo']=='incompatible'
    assert resumen([-.1,.12],[.15,.2],1e-7)['cambio']==pytest.approx([.03,.2])


def test_seleccion_cercania_empate_y_limite():
    assert seleccionar([99,101],100,1,.01)==99
    assert seleccionar([101.01],100,1,.01) is None
    assert seleccionar([],100,1,.005) is None


def test_freshness_limites_y_sello_futuro():
    t=pd.Timestamp('2026-10-20T13:45Z')
    def rows(ages):return [SimpleNamespace(sello_evento_utc=t-pd.Timedelta(seconds=x)) for x in ages]
    assert sincronas(rows([3,5]),t,5,2)
    assert not sincronas(rows([2.999,5]),t,5,2)
    assert not sincronas(rows([4,5.001]),t,5,2)
    assert not sincronas(rows([-.01,0]),t,5,2)


def test_no_reemplazar_strike_ausente_a_las_diez():
    def tab(ks):return pd.DataFrame([dict(strike=x,tipo='P',id_contrato=str(x)) for x in ks]).set_index(['strike','tipo'],drop=False)
    a=(tab([97.,103.]),dict(F=100,T=.1,D=1))
    b=(tab([97.,103.1]),dict(F=101,T=.1-15/(365*1440),D=1))
    r=analizar('2026-10-20','exp','central',[.97,1.03],(a,b),dict(distancia_max_F=.005,tolerancia=1e-7,horas=['09:45','10:00']))
    assert r['motivo']=='pata_put_no_elegible_1000' and r['strikes']==[97.,103.]


@pytest.mark.parametrize('args', [('P',(1,1),(2,3),1,2),('P',(1,2),(2,3),0,2),('C',(1,2),(2,3),1,-1)])
def test_intervalo_invalido(args):
    with pytest.raises(ValueError):banda(*args)
