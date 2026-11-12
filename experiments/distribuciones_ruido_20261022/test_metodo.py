import numpy as np
import pandas as pd
import pytest
from experiments.distribuciones_ruido_20261022.metodo import Mercado
from experiments.distribuciones_ruido_20261022.evaluar import seleccionar_filtros


def tabla(K, tipos, mids, spread=.2):
    mid = np.array(mids,float)
    return pd.DataFrame({"strike":K,"tipo":tipos,"bid":mid-spread/2,"ask":mid+spread/2})


def mercado():
    return tabla([90,100,110],["C"]*3,[15,10,5],spread=.02)


def test_reparacion_de_paridad_con_respuesta_analitica():
    m=Mercado(tabla([100,100],["C","P"],[10,1],spread=2),100,1)
    assert m.reparar()==pytest.approx(1.75,abs=1e-7)
    assert m.reparar(fb=(1.09,1.09))==pytest.approx(0,abs=1e-7)


def test_distribucion_conocida_contenida_y_cdf_con_atomos():
    states,p=np.array([.8,1.,1.2]),np.array([.2,.6,.2])
    K=np.repeat([85.,95.,105.,115.],2)
    tipos=np.tile(["C","P"],4)
    payoff=np.maximum(np.where(tipos[:,None]=="C",100*states-K[:,None],K[:,None]-100*states),0)
    t=tabla(K,tipos,.98*(payoff@p),spread=.0001)
    m=Mercado(t,100,.98,puntos=(.9,1.,1.1))
    assert m.reparar()==pytest.approx(0,abs=1e-7)
    for k,real in zip([.9,1.,1.1],[.2,.8,.8]):
        v=m.cdf(k,.01)
        assert v["inferior"] <= real+1e-7 <= v["superior"]+2e-7


def test_mismos_precios_admiten_probabilidades_distintas():
    m=Mercado(tabla([100],["C"],[10],spread=.00001),100,1)
    # Q1: .5 en 80 y .5 en 120; Q2: .8 en 87.5 y .2 en 150.
    # Ambas E[S]=100 y E[(S-100)+]=10; sus CDF(100) son .5 y .8.
    c=m.cdf(1,0)
    assert c["inferior"]<=.5 and c["superior"]>=.8


def test_cotas_de_call_intermedio_son_las_analiticas():
    m=Mercado(tabla([100,110],["C","C"],[10,5],spread=.000001),
              100,1,extras=(1.05,))
    c=m.precio_call(1.05,0)
    # C(0)=100: pendiente media hasta K100=-.9. Por convexidad C105>=5.5.
    assert 100*c["inferior"]==pytest.approx(5.5,abs=.00001)
    assert 100*c["superior"]==pytest.approx(7.5,abs=.00001)


def test_mas_ruido_y_referencias_libres_no_estrechan():
    m=Mercado(mercado(),100,1)
    r=m.reparar()
    a=m.cdf(1,r+.1)
    b=m.cdf(1,r+1)
    c=m.cdf(1,r+1,fb=(.9975,1.0025),db=(.999,1.001))
    assert b["inferior"]<=a["inferior"]+1e-8 and b["superior"]>=a["superior"]-1e-8
    assert c["inferior"]<=b["inferior"]+1e-8 and c["superior"]>=b["superior"]-1e-8


def test_descontar_masa_no_es_tratarla_como_probabilidad():
    t=mercado()
    # D_ref=1, D_real=.9 frente a reformular D_ref=.9; mismo universo físico.
    a=Mercado(t,100,1); b=Mercado(t,100,.9)
    rho=max(a.reparar(db=(.9,.9)),b.reparar())+.5
    v=a.cdf(1,rho,db=(.9,.9)); w=b.cdf(1,rho)
    assert v==pytest.approx(w,abs=1e-7)
    assert a.testigos[-1]["d"]==pytest.approx(.9)
    assert sum(a.testigos[-1]["p"])==pytest.approx(1)


def test_extension_de_soporte_y_rampa_mas_fina():
    a=Mercado(mercado(),100,1,soporte=2,epsilon=.0025)
    b=Mercado(mercado(),100,1,soporte=4,epsilon=.0025)
    c=Mercado(mercado(),100,1,soporte=2,epsilon=.00125)
    rho=a.reparar()+.5
    va,vb,vc=[m.cdf(1,rho) for m in (a,b,c)]
    assert vb["inferior"]<=va["inferior"]+1e-8 and vb["superior"]>=va["superior"]-1e-8
    assert vc["inferior"]>=va["inferior"]-1e-8 and vc["superior"]<=va["superior"]+1e-8


def test_quiebres_exactos_no_necesitan_malla_regular():
    a=Mercado(mercado(),100,1)
    b=Mercado(mercado(),100,1,extras=np.linspace(.01,1.99,150))
    assert a.reparar()==pytest.approx(b.reparar(),abs=1e-7)
    assert a.cdf(1,.5)==pytest.approx(b.cdf(1,.5),abs=1e-7)


def test_cdf_alcanzada_esta_entre_las_cotas_exteriores():
    m=Mercado(tabla([100],["C"],[10],spread=.00001),100,1)
    exterior=m.cdf(1,.5)
    interior=m.cdf(1,.5,discreta=True)
    assert exterior["inferior"]<=interior["inferior"]+1e-8
    assert exterior["superior"]>=interior["superior"]-1e-8
    assert interior["ancho"]>.25
    for t in m.testigos[-2:]:
        assert np.array(t["p"])[m.x<=1].sum()==pytest.approx(t["valor"])


def test_escalamiento_y_orden():
    t=mercado(); a=Mercado(t,100,1)
    s=t.iloc[::-1].copy(); s[["strike","bid","ask"]]*=50
    b=Mercado(s,5000,1)
    assert a.reparar()==pytest.approx(b.reparar(),abs=1e-7)
    assert a.cdf(1,.5)==pytest.approx(b.cdf(1,.5),abs=1e-7)


def test_filtro_usa_solo_selllos_disponibles_y_respeta_frontera_5s():
    recibido=pd.Timestamp("2026-10-02T13:45:00Z")
    edades=[5,5.001,-.001,None,1,1,0]
    t=pd.DataFrame({"recibido_utc":[recibido]*7,"disponible_utc":[recibido]*7,
        "sello_evento_utc":[recibido-pd.Timedelta(seconds=e) if e is not None else pd.NaT for e in edades],
        "strike":[110]*5+[90,100],"tipo":["C"]*7})
    t.loc[4,"disponible_utc"]=recibido+pd.Timedelta(milliseconds=1)
    f=seleccionar_filtros(t,100,5)
    assert f["frescas_5s"].index.tolist()==[0,5,6]
    assert f["otm"].index.tolist()==[0,1,2,3,4,6]
    assert f["otm_frescas_5s"].index.tolist()==[0,6]
    assert len(f["todos"])==7


@pytest.mark.parametrize("problema",["vacio","duplicado","spread","nan","referencia","soporte","epsilon"])
def test_entradas_invalidas(problema):
    t=mercado(); kw={}
    if problema=="vacio": t=t.iloc[:0]
    if problema=="duplicado": t=pd.concat([t,t.iloc[:1]])
    if problema=="spread": t.loc[0,"ask"]=0
    if problema=="nan": t.loc[0,"bid"]=np.nan
    if problema=="soporte": kw["soporte"]=1.05
    if problema=="epsilon": kw["epsilon"]=0
    with pytest.raises(ValueError):
        Mercado(t,0 if problema=="referencia" else 100,1,**kw)


@pytest.mark.parametrize("kw",[{"rho":-1},{"rho":np.nan},{"rho":.1,"fb":(1.1,.9)},
                              {"rho":.1,"db":(0,1)}])
def test_objetivos_invalidos(kw):
    with pytest.raises(ValueError):
        Mercado(mercado(),100,1).cdf(1,**kw)
