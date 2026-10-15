"""Kelly a mano, busqueda exhaustiva, perdida maxima y limite diario."""

import datetime as dt
from decimal import Decimal

import pytest

from btclab.costes import ModeloComisionCuadratica, evaluar
from btclab.libro import Lado, Libro, Nivel
from btclab.limites import (
    ErrorLimites,
    EstadoRiesgo,
    LimitesRiesgo,
    restricciones_vigentes,
)
from btclab.sizing import (
    ErrorSizing,
    crecimiento_log,
    dimensionar,
    kelly_completo,
    kelly_fraccionado,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
INICIO_ZONA = dt.datetime(2026, 10, 15, 0, 0, tzinfo=UTC)


def modelo():
    return ModeloComisionCuadratica(constante=Decimal("0.07"), verificada=True)


def libro(precio_venta_yes_mils=500, cantidad=Decimal("10000")):
    return Libro(
        "C", T0, T0,
        compras_yes=(Nivel(1000 - precio_venta_yes_mils - 10, cantidad),),
        compras_no=(Nivel(1000 - precio_venta_yes_mils, cantidad),),
    )


# -- Kelly a mano -----------------------------------------------------------


def test_kelly_completo_a_mano():
    # (0.60 - 0.50) / (1 - 0.50) = 0.2
    assert kelly_completo(Decimal("0.60"), Decimal("0.50")) == Decimal("0.2")
    # (0.80 - 0.20) / (1 - 0.20) = 0.75
    assert kelly_completo(Decimal("0.80"), Decimal("0.20")) == Decimal("0.75")


def test_kelly_es_cero_sin_ventaja():
    assert kelly_completo(Decimal("0.50"), Decimal("0.50")) == Decimal("0")
    assert kelly_completo(Decimal("0.40"), Decimal("0.50")) == Decimal("0")


def test_kelly_fraccionado_escala_por_alpha():
    completo = kelly_completo(Decimal("0.60"), Decimal("0.50"))
    assert kelly_fraccionado(Decimal("0.60"), Decimal("0.50"), Decimal("0.25")) == (
        Decimal("0.25") * completo
    )


def test_kelly_rechaza_coste_degenerado():
    with pytest.raises(ErrorSizing):
        kelly_completo(Decimal("0.6"), Decimal("1"))
    with pytest.raises(ErrorSizing):
        kelly_completo(Decimal("0.6"), Decimal("0"))


def test_alpha_fuera_de_rango_falla():
    with pytest.raises(ErrorSizing):
        kelly_fraccionado(Decimal("0.6"), Decimal("0.5"), Decimal("0"))


# -- G(n) -------------------------------------------------------------------


def test_g_de_cero_es_cero():
    assert crecimiento_log(Decimal("0"), Decimal("0"), Decimal("0.6"), Decimal("1000")) == 0.0


def test_g_es_inadmisible_si_el_patrimonio_se_agota():
    # Coste mayor que el capital: no es un valor muy negativo, es inadmisible.
    assert crecimiento_log(
        Decimal("10"), Decimal("1000"), Decimal("0.6"), Decimal("1000")
    ) is None
    assert crecimiento_log(
        Decimal("10"), Decimal("1100"), Decimal("0.6"), Decimal("1000")
    ) is None


def test_g_positivo_con_ventaja_y_negativo_sin_ella():
    con = crecimiento_log(Decimal("100"), Decimal("50"), Decimal("0.70"), Decimal("1000"))
    sin = crecimiento_log(Decimal("100"), Decimal("50"), Decimal("0.30"), Decimal("1000"))
    assert con > 0
    assert sin < 0


# -- Busqueda exhaustiva ----------------------------------------------------


def limites(**kwargs):
    base = dict(
        capital_segregado=Decimal("1000"),
        presupuesto_configurado=True,
        es_capital_ficticio=True,
        fraccion_kelly=Decimal("1"),
    )
    base.update(kwargs)
    return LimitesRiesgo(**base)


def estado(**kwargs):
    return EstadoRiesgo(inicio_zona=INICIO_ZONA, **kwargs)


def test_sin_ventaja_la_cantidad_optima_es_cero():
    # Venta a 0.50 con p_robust 0.45: comprar destruye valor.
    p = dimensionar(
        libro(500), Lado.YES, Decimal("0.45"), modelo(), limites(), estado(), T0,
        cantidad_maxima_busqueda=Decimal("50"),
    )
    assert p.cantidad_optima_sin_reduccion == Decimal("0")
    assert p.cantidad_simulada == Decimal("0")
    assert not p.opera


def test_con_ventaja_la_busqueda_coincide_con_el_optimo_por_fuerza_bruta():
    lb = libro(400)
    lim = limites()
    est = estado()
    p_robust = Decimal("0.60")
    propuesta = dimensionar(
        lb, Lado.YES, p_robust, modelo(), lim, est, T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    # Fuerza bruta independiente sobre la misma rejilla.
    mejor_n, mejor_g = Decimal("0"), 0.0
    for n in range(1, 61):
        ev = evaluar(lb, Lado.YES, Decimal(n), p_robust, modelo())
        g = crecimiento_log(
            ev.cantidad_llenada, ev.coste_total, p_robust, lim.capital_segregado
        )
        if g is not None and g > mejor_g:
            mejor_n, mejor_g = Decimal(n), g
    assert propuesta.cantidad_optima_sin_reduccion == mejor_n
    assert mejor_n > 0


def test_la_curva_incluye_no_operar():
    p = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(), limites(), estado(), T0,
        cantidad_maxima_busqueda=Decimal("10"),
    )
    assert p.curva[0].cantidad == Decimal("0")
    assert p.curva[0].motivo == "no operar"


def test_fraccion_de_kelly_reduce_la_cantidad():
    completo = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(),
        limites(fraccion_kelly=Decimal("1")), estado(), T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    cuarto = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(),
        limites(fraccion_kelly=Decimal("0.25")), estado(), T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    assert cuarto.cantidad_simulada < completo.cantidad_simulada


def test_sin_banda_defendible_no_hay_tamano():
    p = dimensionar(
        libro(400), Lado.YES, None, modelo(), limites(), estado(), T0,
    )
    assert p.cantidad_simulada == Decimal("0")
    assert any("banda" in m for m in p.motivos_no_operar)


def test_comisiones_no_verificadas_bloquean_el_tamano():
    sin_verificar = ModeloComisionCuadratica(
        constante=Decimal("0.07"), verificada=False
    )
    p = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), sin_verificar, limites(), estado(), T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    assert any("comisiones no verificado" in m for m in p.motivos_no_operar)
    assert not p.opera


def test_sin_presupuesto_configurado_el_tamano_es_cero():
    p = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(),
        limites(presupuesto_configurado=False), estado(), T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    assert p.cantidad_simulada == Decimal("0")
    assert "presupuesto_no_configurado" in p.restricciones_activas


def test_importe_real_es_siempre_cero_antes_de_validar():
    p = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(), limites(), estado(), T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    assert p.suggested_live_amount == Decimal("0")
    assert p.es_ficticio is True


def test_perdida_maxima_igual_al_coste_comprometido():
    p = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(), limites(), estado(), T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    assert p.perdida_maxima_simulada == p.simulated_amount


def test_profundidad_insuficiente_limita_la_cantidad():
    lb = libro(400, cantidad=Decimal("5"))
    p = dimensionar(
        lb, Lado.YES, Decimal("0.60"), modelo(), limites(), estado(), T0,
        cantidad_maxima_busqueda=Decimal("100"),
    )
    assert p.cantidad_simulada <= Decimal("5")


def test_cantidad_bajo_el_minimo_negociable_redondea_a_cero():
    # Con alpha = 0.1 el optimo de 60 se reduce a 6, que esta por debajo del
    # minimo de 10: no hay orden posible y se propone cero con el motivo.
    p = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(),
        limites(fraccion_kelly=Decimal("0.1")), estado(), T0,
        cantidad_maxima_busqueda=Decimal("60"), cantidad_minima=Decimal("10"),
    )
    assert p.cantidad_simulada == Decimal("0")
    assert any("minimo negociable" in m for m in p.motivos_no_operar)


def test_reduccion_muy_agresiva_tambien_da_cero():
    p = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(),
        limites(fraccion_kelly=Decimal("0.01")), estado(), T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    assert p.cantidad_simulada == Decimal("0")
    assert not p.opera


# -- Limite diario ----------------------------------------------------------


def test_riesgo_diario_suma_realizadas_y_abierto():
    e = estado(perdidas_realizadas=Decimal("30"), riesgo_maximo_abierto=Decimal("15"))
    assert e.riesgo_diario_consumido == Decimal("45")


def test_limite_diario_se_agota_en_la_igualdad():
    lim = limites(perdida_diaria_maxima=Decimal("50"))
    assert estado(perdidas_realizadas=Decimal("49")).limite_diario_agotado(lim) is False
    assert estado(perdidas_realizadas=Decimal("50")).limite_diario_agotado(lim) is True
    assert estado(perdidas_realizadas=Decimal("51")).limite_diario_agotado(lim) is True


def test_el_riesgo_abierto_cuenta_contra_el_limite_diario():
    # Una posicion abierta puede perder todo lo comprometido, asi que consume
    # presupuesto aunque todavia no haya perdida realizada.
    lim = limites(perdida_diaria_maxima=Decimal("50"))
    e = estado(riesgo_maximo_abierto=Decimal("50"))
    assert e.limite_diario_agotado(lim) is True


def test_limite_diario_agotado_bloquea_nuevas_entradas():
    lim = limites(perdida_diaria_maxima=Decimal("50"))
    e = estado(perdidas_realizadas=Decimal("50"))
    p = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(), lim, e, T0,
        cantidad_maxima_busqueda=Decimal("60"),
    )
    assert p.cantidad_simulada == Decimal("0")
    assert "perdida_diaria_restante" in p.restricciones_activas


def test_no_se_aumenta_el_tamano_para_recuperar_perdidas():
    lim = limites(perdida_diaria_maxima=Decimal("100"))
    sin_perdidas = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(), lim, estado(), T0,
        cantidad_maxima_busqueda=Decimal("200"),
    )
    con_perdidas = dimensionar(
        libro(400), Lado.YES, Decimal("0.60"), modelo(), lim,
        estado(perdidas_realizadas=Decimal("60")), T0,
        cantidad_maxima_busqueda=Decimal("200"),
    )
    assert con_perdidas.cantidad_simulada <= sin_perdidas.cantidad_simulada


def test_zona_de_reinicio_por_hora_configurada():
    lim = limites(hora_reinicio_utc=12)
    e = EstadoRiesgo(inicio_zona=dt.datetime(2026, 10, 15, 13, 0, tzinfo=UTC))
    assert e.zona_vigente(dt.datetime(2026, 10, 15, 20, 0, tzinfo=UTC), lim) is True
    assert e.zona_vigente(dt.datetime(2026, 10, 16, 13, 0, tzinfo=UTC), lim) is False


def test_posiciones_abiertas_maximas_bloquean():
    lim = limites(posiciones_abiertas_maximas=1)
    e = estado(posiciones_abiertas=1)
    restr = restricciones_vigentes(lim, e, T0, Decimal("0.5"))
    assert any(r.nombre == "posiciones_abiertas" and r.activa for r in restr)


def test_capital_segregado_negativo_se_rechaza():
    with pytest.raises(ErrorLimites):
        LimitesRiesgo(capital_segregado=Decimal("-1"))


def test_fraccion_kelly_fuera_de_rango_se_rechaza():
    with pytest.raises(ErrorLimites):
        LimitesRiesgo(capital_segregado=Decimal("1"), fraccion_kelly=Decimal("1.5"))


# -- dominio de validez ----------------------------------------------------


def test_horizonte_mucho_mayor_que_la_ventana_esta_fuera_de_dominio():
    from btclab.variables import motivos_fuera_de_dominio

    motivos = motivos_fuera_de_dominio(
        ventana_observada_s=15.0, tiempo_restante_s=795.0, observaciones=100
    )
    assert any("fuera del dominio" in m for m in motivos)


def test_ventana_suficiente_esta_dentro_de_dominio():
    from btclab.variables import motivos_fuera_de_dominio

    assert motivos_fuera_de_dominio(
        ventana_observada_s=900.0, tiempo_restante_s=795.0, observaciones=180
    ) == ()


def test_pocas_observaciones_quedan_fuera_de_dominio():
    from btclab.variables import motivos_fuera_de_dominio

    motivos = motivos_fuera_de_dominio(
        ventana_observada_s=900.0, tiempo_restante_s=100.0, observaciones=5
    )
    assert any("observaciones de subyacente" in m for m in motivos)


def test_sin_ventana_observada_queda_fuera_de_dominio():
    from btclab.variables import motivos_fuera_de_dominio

    motivos = motivos_fuera_de_dominio(
        ventana_observada_s=0.0, tiempo_restante_s=100.0, observaciones=100
    )
    assert any("sin ventana" in m for m in motivos)
