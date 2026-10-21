"""Reconstruccion de la serie del indice de liquidacion y su volatilidad.

El contrato liquida con el BRTI de CF Benchmarks, que exige clave. Pero cada
mercado liquidado trae dos observaciones exactas del indice, y la cadena
``expiration_value(n) == floor_strike(n+1)`` permite comprobarlas entre si.
"""

import datetime as dt
from decimal import Decimal

import pytest

from btclab.indice import (
    ErrorIndice,
    PuntoIndice,
    cargar_serie,
    construir_serie,
    puntos_desde_mercados,
    retornos_del_indice,
    volatilidad_por_segundo,
)

UTC = dt.timezone.utc


def mercado(indice, floor, valor=None, resultado="no"):
    """Mercado sintetico de 15 minutos, encadenado por indice."""
    base = dt.datetime(2026, 10, 15, 0, 0, tzinfo=UTC) + dt.timedelta(
        minutes=15 * indice
    )
    datos = {
        "ticker": f"KXBTC15M-TEST-{indice:04d}",
        "open_time": base.isoformat().replace("+00:00", "Z"),
        "close_time": (base + dt.timedelta(minutes=15))
        .isoformat()
        .replace("+00:00", "Z"),
        "floor_strike": floor,
        "result": resultado,
    }
    if valor is not None:
        datos["expiration_value"] = valor
    return datos


def cadena(valores, resultados=None):
    """Mercados encadenados: el valor de uno es el umbral del siguiente."""
    salida = []
    for i in range(len(valores) - 1):
        salida.append(
            mercado(
                i,
                floor=valores[i],
                valor=valores[i + 1],
                resultado=(resultados[i] if resultados else "no"),
            )
        )
    return salida


# -- extraccion -------------------------------------------------------------


def test_cada_mercado_aporta_dos_puntos():
    puntos = list(puntos_desde_mercados([mercado(0, "80000", "80100")]))
    assert len(puntos) == 2
    assert {p.procedencia for p in puntos} == {"floor_strike", "expiration_value"}


def test_un_mercado_sin_resultado_solo_aporta_el_umbral():
    puntos = list(puntos_desde_mercados([mercado(0, "80000", None)]))
    assert len(puntos) == 1
    assert puntos[0].procedencia == "floor_strike"


def test_el_punto_se_marca_al_cierre_de_su_ventana():
    puntos = {p.procedencia: p for p in puntos_desde_mercados([mercado(0, "80000", "80100")])}
    assert puntos["floor_strike"].cierra_en == dt.datetime(2026, 10, 15, 0, 0, tzinfo=UTC)
    assert puntos["expiration_value"].cierra_en == dt.datetime(
        2026, 10, 15, 0, 15, tzinfo=UTC
    )


def test_valor_no_positivo_se_rechaza():
    with pytest.raises(ErrorIndice):
        PuntoIndice(
            cierra_en=dt.datetime(2026, 10, 15, tzinfo=UTC),
            valor=Decimal("0"),
            ventana_s=60,
            contrato="C",
            procedencia="floor_strike",
        )


def test_procedencia_desconocida_se_rechaza():
    with pytest.raises(ErrorIndice):
        PuntoIndice(
            cierra_en=dt.datetime(2026, 10, 15, tzinfo=UTC),
            valor=Decimal("1"),
            ventana_s=60,
            contrato="C",
            procedencia="inventada",
        )


# -- cadena -----------------------------------------------------------------


def test_la_cadena_coherente_no_produce_conflictos():
    serie = construir_serie(cadena(["80000", "80100", "80200", "80300"]))
    assert serie.conflictos == ()
    assert serie.duplicados_coherentes > 0
    assert serie.n == 4


def test_una_cadena_rota_se_registra_como_conflicto():
    # El expiration_value del primero no coincide con el floor del segundo.
    mercados = [
        mercado(0, "80000", "80100"),
        mercado(1, "80999", "80200"),  # deberia abrir en 80100
    ]
    serie = construir_serie(mercados)
    assert len(serie.conflictos) == 1
    conflicto = serie.conflictos[0]
    assert {conflicto["procedencia_a"], conflicto["procedencia_b"]} == {
        "expiration_value",
        "floor_strike",
    }


def test_el_conflicto_prefiere_el_valor_de_liquidacion():
    mercados = [
        mercado(0, "80000", "80100"),
        mercado(1, "80999", "80200"),
    ]
    serie = construir_serie(mercados)
    punto = next(
        p for p in serie.puntos
        if p.cierra_en == dt.datetime(2026, 10, 15, 0, 15, tzinfo=UTC)
    )
    assert punto.valor == Decimal("80100")
    assert punto.procedencia == "expiration_value"


def test_la_serie_queda_ordenada_y_deduplicada():
    serie = construir_serie(cadena(["80000", "80100", "80200"]))
    marcas = [p.cierra_en for p in serie.puntos]
    assert marcas == sorted(marcas)
    assert len(set(marcas)) == len(marcas)


def test_huecos_se_detectan():
    mercados = [mercado(0, "80000", "80100"), mercado(8, "81000", "81100")]
    serie = construir_serie(mercados)
    assert len(serie.huecos(separacion_esperada_s=900.0)) >= 1


# -- union hacia atras ------------------------------------------------------


def test_valor_en_no_usa_una_ventana_que_no_habia_cerrado():
    serie = construir_serie(cadena(["80000", "80100", "80200"]))
    # A las 00:10 el promedio que cierra a las 00:15 aun no existia.
    punto = serie.valor_en(dt.datetime(2026, 10, 15, 0, 10, tzinfo=UTC))
    assert punto.cierra_en == dt.datetime(2026, 10, 15, 0, 0, tzinfo=UTC)
    assert punto.valor == Decimal("80000")


def test_valor_en_el_borde_exacto_si_esta_disponible():
    serie = construir_serie(cadena(["80000", "80100", "80200"]))
    punto = serie.valor_en(dt.datetime(2026, 10, 15, 0, 15, tzinfo=UTC))
    assert punto.valor == Decimal("80100")


def test_valor_en_antes_del_inicio_es_nulo():
    serie = construir_serie(cadena(["80000", "80100"]))
    assert serie.valor_en(dt.datetime(2026, 10, 14, tzinfo=UTC)) is None


# -- volatilidad ------------------------------------------------------------


def serie_larga(n=400, sigma=0.0017, semilla=11):
    import math
    import random

    generador = random.Random(semilla)
    valores = [80000.0]
    for _ in range(n):
        valores.append(valores[-1] * math.exp(generador.gauss(0.0, sigma)))
    textos = [f"{v:.2f}" for v in valores]
    return construir_serie(cadena(textos))


def test_la_volatilidad_recupera_la_escala_del_proceso():
    import math

    serie = serie_larga(n=600, sigma=0.0017)
    sigma, detalle = volatilidad_por_segundo(serie)
    assert sigma is not None
    # sigma por segundo escalada al paso de 900 s debe acercarse a 0.0017.
    en_paso = sigma * math.sqrt(900.0)
    assert 0.0013 < en_paso < 0.0022
    assert detalle["paso_tipico_s"] == 900.0


def test_muestra_insuficiente_devuelve_none_con_motivo():
    serie = serie_larga(n=20)
    sigma, detalle = volatilidad_por_segundo(serie, minimo_retornos=100)
    assert sigma is None
    assert "retornos" in detalle["motivo"]


def test_la_volatilidad_usa_solo_el_pasado_del_corte():
    serie = serie_larga(n=600)
    corte = serie.puntos[300].cierra_en
    sigma, detalle = volatilidad_por_segundo(serie, hasta=corte)
    assert sigma is not None
    assert detalle["puntos_usados"] == 301
    completa, _ = volatilidad_por_segundo(serie)
    # No tienen por que coincidir, pero la recortada no puede ver mas puntos.
    assert detalle["puntos_usados"] < serie.n
    assert completa is not None


def test_la_ventana_en_dias_recorta_la_muestra():
    serie = serie_larga(n=600)
    sigma_todo, detalle_todo = volatilidad_por_segundo(serie)
    sigma_corta, detalle_corta = volatilidad_por_segundo(
        serie, ventana_dias=1.0, minimo_retornos=50
    )
    assert sigma_corta is not None
    assert detalle_corta["retornos"] < detalle_todo["retornos"]


def test_una_volatilidad_mas_alta_da_sigma_mas_alta():
    import math

    baja, _ = volatilidad_por_segundo(serie_larga(n=600, sigma=0.0008, semilla=3))
    alta, _ = volatilidad_por_segundo(serie_larga(n=600, sigma=0.0032, semilla=3))
    assert baja is not None and alta is not None
    assert alta > baja * 2


def test_retornos_del_indice_son_consecutivos():
    serie = construir_serie(cadena(["80000", "80800", "80000"]))
    retornos = retornos_del_indice(serie)
    assert len(retornos) == serie.n - 1
    assert retornos[0][1] > 0
    assert retornos[1][1] < 0


# -- persistencia -----------------------------------------------------------


def test_ida_y_vuelta_por_archivo(tmp_path):
    import json

    from btclab.tiempo import a_iso

    serie = construir_serie(cadena(["80000", "80100", "80200"]))
    ruta = tmp_path / "brti.jsonl"
    with ruta.open("w", encoding="utf-8") as archivo:
        for punto in serie.puntos:
            archivo.write(
                json.dumps(
                    {
                        "cierra_en": a_iso(punto.cierra_en),
                        "valor": str(punto.valor),
                        "ventana_s": punto.ventana_s,
                        "contrato": punto.contrato,
                        "procedencia": punto.procedencia,
                    }
                )
                + "\n"
            )
    vuelta = cargar_serie(ruta)
    assert vuelta.n == serie.n
    assert vuelta.puntos[0].valor == serie.puntos[0].valor
    assert vuelta.puntos[-1].cierra_en == serie.puntos[-1].cierra_en


def test_cargar_serie_inexistente_falla(tmp_path):
    with pytest.raises(ErrorIndice):
        cargar_serie(tmp_path / "no_existe.jsonl")


def test_cargar_serie_corrupta_falla(tmp_path):
    ruta = tmp_path / "mala.jsonl"
    ruta.write_text("{esto no es json\n", encoding="utf-8")
    with pytest.raises(ErrorIndice):
        cargar_serie(ruta)


# -- ancla antigua ----------------------------------------------------------


def test_un_ancla_antigua_aumenta_la_dispersion():
    """Desde un ancla vieja hay difusion no observada, y debe contar.

    Si el nivel conocido del indice tiene antiguedad, el tiempo efectivo de
    difusion es la antiguedad mas el tiempo restante. Tratar el ancla como si
    fuera de ahora mismo estrecha la distribucion de forma injustificada.
    """
    from decimal import Decimal as D

    from btclab.contrato import Operador, ReglaLiquidacion
    from btclab.modelos import ModeloSubyacente

    regla = ReglaLiquidacion(
        indice="BRTI",
        agencia_fuente="CF Benchmarks",
        ventana_promedio_s=60,
        operador=Operador.MAYOR_O_IGUAL,
        umbral=D("84000"),
    )
    modelo = ModeloSubyacente(trayectorias=8000)
    sin_antiguedad = modelo.simular(
        spot=84000.0, volatilidad_s=5.64e-5, tiempo_restante_s=450.0,
        ventana_promedio_s=60.0, regla=regla,
    )
    con_antiguedad = modelo.simular(
        spot=84000.0, volatilidad_s=5.64e-5, tiempo_restante_s=450.0 + 440.0,
        ventana_promedio_s=60.0, regla=regla,
    )
    ancho_sin = sin_antiguedad.intervalo(0.95)[1] - sin_antiguedad.intervalo(0.95)[0]
    ancho_con = con_antiguedad.intervalo(0.95)[1] - con_antiguedad.intervalo(0.95)[0]
    assert ancho_con > ancho_sin


def test_en_el_dinero_la_probabilidad_es_insensible_a_la_volatilidad():
    """Con umbral igual al nivel, p ~ 0.5 para cualquier volatilidad.

    Es la razon por la que una banda construida solo remuestreando la
    volatilidad sale degenerada en el dinero: no mide la incertidumbre que
    importa. Queda fijado como propiedad conocida del metodo, no como sorpresa.
    """
    from decimal import Decimal as D

    from btclab.contrato import Operador, ReglaLiquidacion
    from btclab.modelos import ModeloSubyacente

    regla = ReglaLiquidacion(
        indice="BRTI",
        agencia_fuente="CF Benchmarks",
        ventana_promedio_s=60,
        operador=Operador.MAYOR_O_IGUAL,
        umbral=D("84000"),
    )
    modelo = ModeloSubyacente(trayectorias=20000)
    baja = modelo.simular(
        spot=84000.0, volatilidad_s=2.0e-5, tiempo_restante_s=600.0,
        ventana_promedio_s=60.0, regla=regla,
    ).p_yes
    alta = modelo.simular(
        spot=84000.0, volatilidad_s=9.0e-5, tiempo_restante_s=600.0,
        ventana_promedio_s=60.0, regla=regla,
    ).p_yes
    assert abs(baja - alta) < 0.03
    assert 0.45 < baja < 0.55
