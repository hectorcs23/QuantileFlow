"""Datos sintéticos: recuperación fuera del ajuste, paridad y contabilidad común."""
import numpy as np
import pytest
from scipy.integrate import quad

from quantileflow.ajuste_bandas import (ajustar_bandas, precios_ajuste,
    incompatibilidades_paridad, valorador_bandas)
from quantileflow.escenarios import ContratoEscenario, Escenario, comparar_contratos
from quantileflow.opciones import precio_black
from quantileflow.superficies import Rebanada, SuperficieSSVI


@pytest.fixture(scope="module")
def recuperacion():
    verdad = SuperficieSSVI(np.array([.1,.15]), np.array([.004,.006]), -.65, .8, .4)
    trains, reservas = [], []
    for T in verdad.tiempos:
        K = np.repeat(100*np.exp(np.linspace(-.08,.08,25)),2)
        calls = np.tile([True,False],25)
        p = precio_black(100,K,verdad.w(np.log(K/100),T),.99,calls)
        mask = np.repeat(np.arange(25)%3 != 0,2)
        for grupo, m in ((trains,mask),(reservas,~mask)):
            grupo.append(Rebanada(T,100,.99,K[m],p[m]-.002,p[m]+.002,calls[m]))
    return ajustar_bandas(trains), reservas


def test_recupera_smile_en_strikes_no_ajustados(recuperacion):
    fit, reservas = recuperacion
    assert all(fit.superficie.condiciones().values())
    errores_ssvi, errores_plano = [], []
    for r in reservas:
        errores_ssvi.extend(np.abs(precios_ajuste(fit,r,"ssvi")-r.mid))
        errores_plano.extend(np.abs(precios_ajuste(fit,r,"plano")-r.mid))
    assert max(errores_ssvi) < .004
    assert np.median(errores_ssvi) < np.median(errores_plano)/20


def test_pdf_reproduce_precio_black_y_paridad(recuperacion):
    fit, _ = recuperacion
    T, F, D, K = .1, 100., .99, 102.
    surface = fit.superficie
    density = lambda x: float(surface.densidad(x,T))
    mass = quad(density,-3,3,epsabs=1e-9)[0]
    mean = quad(lambda x: np.exp(x)*density(x),-3,3,epsabs=1e-9)[0]
    assert mass == pytest.approx(1,abs=1e-6)
    assert mean == pytest.approx(1,abs=1e-6)
    integrado = D*quad(lambda x: max(F*np.exp(x)-K,0)*density(x),np.log(K/F),3,epsabs=1e-8)[0]
    w = surface.w(np.log(K/F),T)
    call, put = precio_black(F,K,w,D,True), precio_black(F,K,w,D,False)
    assert integrado == pytest.approx(call,abs=1e-6)
    assert call-put == pytest.approx(D*(F-K),abs=1e-12)


def test_incompatibilidad_demuestra_limite_independiente_del_modelo():
    r = Rebanada(.1,100.,1.,np.array([100.,100.,102.,102.]),
        np.array([4.,1.,2.,4.]),np.array([4.1,1.1,2.1,4.1]),np.array([True,False,True,False]))
    assert incompatibilidades_paridad(r) == dict(pares=2,incompatibles=1,minimo_cotizaciones_fuera=1)
    p = precio_black(r.F,r.K,.004,r.D,r.es_call)
    assert ((p < r.bid)|(p > r.ask)).sum() >= 1


def test_smile_plana_se_recupera_sin_mejora_artificial():
    K = np.linspace(95,105,15)
    p = precio_black(100,K,.004,1.,True)
    r = Rebanada(.1,100,1,K,p-.01,p+.01,np.ones(15,dtype=bool))
    fit = ajustar_bandas([r])
    assert fit.planas[.1] == pytest.approx(.2,abs=1e-7)
    assert max(np.abs(precios_ajuste(fit,r,"ssvi")-p)) < .011


def test_contabilidad_y_pago_final_del_valorador():
    c = ContratoEscenario("sintetico",100,10,True,"europeo",.2,2,2.1)
    es = [Escenario("objetivo",5,.02),Escenario("vencimiento",10,.03)]
    vistos = []
    def valorar(c,s,e,r,q):
        vistos.append(e.nombre)
        return 4.
    resultado = comparar_contratos([c],100,es,1000,comision=.65,semispread_salida=.1,
                                  limites_cantidad={"sintetico":2},valorador=valorar)
    f = resultado["contratos"][0]
    assert vistos == ["objetivo"]
    assert f["contratos"] == 2
    assert f["efectivo_libre"] == pytest.approx(1000-2*(210+1.3))
    assert f["escenarios"]["objetivo"]["pnl"] == pytest.approx(2*(390-.65)-2*(210+.65))
    assert f["escenarios"]["vencimiento"]["valor_teorico"] == pytest.approx(3)


@pytest.mark.parametrize("valor",[np.nan,np.inf,-1])
def test_callback_invalido_no_produce_ranking(valor):
    c = ContratoEscenario("sintetico",100,10,True,"europeo",.2,2,2.1)
    with pytest.raises(ValueError,match="precio inválido"):
        comparar_contratos([c],100,[Escenario("objetivo",5,.02)],1000,
                          valorador=lambda *args:valor)


@pytest.mark.parametrize("valor",[0.,200.])
def test_callback_no_puede_violar_cotas_de_no_arbitraje(valor):
    c = ContratoEscenario("sintetico",100,10,True,"europeo",.2,2,2.1)
    with pytest.raises(ValueError,match="cotas europeas"):
        comparar_contratos([c],100,[Escenario("objetivo",5,.02)],1000,
                          valorador=lambda *args:valor)


@pytest.mark.parametrize("modelo",["plano","ssvi"])
@pytest.mark.parametrize("dinamica",["tasa_congelada","plazo_restante"])
def test_escenario_cero_coincide_con_calibracion_y_respetan_paridad(recuperacion,modelo,dinamica):
    fit, reservas = recuperacion
    T, K = .1, 100.
    reb = Rebanada(T,100,1,np.array([K]),np.array([1.]),np.array([2.]),np.array([True]))
    c = ContratoEscenario("sintetico",K,T*365,True,"europeo",.2,1,2)
    val = valorador_bandas(fit,modelo,dinamica)
    assert val(c,100,Escenario("hoy",0,0),0,0) == pytest.approx(precios_ajuste(fit,reb,modelo)[0])
    e = Escenario("futuro",7,.02)
    from dataclasses import replace
    call, put = val(c,100,e,0,0), val(replace(c,es_call=False),100,e,0,0)
    assert call-put == pytest.approx(102-K,abs=1e-12)


def test_prohibir_iv_smile_como_diffusion_y_shift_no_definido(recuperacion):
    fit,_ = recuperacion
    c = ContratoEscenario("sintetico",100,36.5,True,"europeo",.2,1,2)
    with pytest.raises(ValueError,match="clásico"):
        comparar_contratos([c],100,[Escenario("objetivo",7,.01)],1000,motor="pde",
                          valorador=valorador_bandas(fit,"ssvi"))
    with pytest.raises(ValueError,match="shifts"):
        valorador_bandas(fit,"ssvi")(c,100,Escenario("objetivo",7,.01,-.03),0,0)


@pytest.mark.parametrize("pref",[-.1,1.1])
def test_preferencia_fuera_de_banda_rechazada(pref):
    with pytest.raises(ValueError):
        ajustar_bandas([],pref)
