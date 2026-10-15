"""Separacion cronologica, purga, agrupacion por contrato y dependencia."""

import datetime as dt

import numpy as np
import pytest

from btclab.evaluacion import (
    ErrorEvaluacion,
    Observable,
    SeparacionCronologica,
    agregar_por_dia,
    ajuste_por_seleccion,
    bootstrap_bloques_media,
    observaciones_efectivas,
    walk_forward,
)

UTC = dt.timezone.utc


def obs(contrato, hora_decision, hora_etiqueta, dia=1):
    return Observable(
        contrato,
        dt.datetime(2026, 10, dia, hora_decision, tzinfo=UTC),
        dt.datetime(2026, 10, dia, hora_etiqueta, tzinfo=UTC),
    )


def separacion(segundos=1800):
    return SeparacionCronologica(
        fin_entrenamiento=dt.datetime(2026, 10, 1, 10, tzinfo=UTC),
        fin_calibracion=dt.datetime(2026, 10, 1, 14, tzinfo=UTC),
        fin_validacion=dt.datetime(2026, 10, 1, 18, tzinfo=UTC),
        separacion_s=segundos,
    )


def test_tramos_por_orden_cronologico():
    s = separacion()
    assert s.tramo(obs("A", 8, 9)) == "entrenamiento"
    assert s.tramo(obs("B", 12, 13)) == "calibracion"
    assert s.tramo(obs("C", 16, 17)) == "validacion"
    assert s.tramo(obs("D", 20, 21)) == "final"


def test_etiqueta_que_invade_el_tramo_siguiente_se_purga():
    s = separacion()
    # Decision en entrenamiento pero etiqueta publicada en calibracion.
    assert s.tramo(obs("X", 9, 11)) == "purgada"


def test_la_separacion_temporal_purga_el_borde():
    s = separacion(segundos=1800)
    al_borde = Observable(
        "Y",
        dt.datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        dt.datetime(2026, 10, 1, 9, 35, tzinfo=UTC),
    )
    assert s.tramo(al_borde) == "purgada"
    sin_margen = separacion(segundos=0)
    assert sin_margen.tramo(al_borde) == "entrenamiento"


def test_cortes_no_crecientes_se_rechazan():
    with pytest.raises(ErrorEvaluacion):
        SeparacionCronologica(
            fin_entrenamiento=dt.datetime(2026, 10, 1, 14, tzinfo=UTC),
            fin_calibracion=dt.datetime(2026, 10, 1, 10, tzinfo=UTC),
            fin_validacion=dt.datetime(2026, 10, 1, 18, tzinfo=UTC),
            separacion_s=0,
        )


def test_etiqueta_anterior_a_la_decision_se_rechaza():
    with pytest.raises(ErrorEvaluacion):
        obs("Z", 12, 11)


def test_un_contrato_en_dos_tramos_es_un_hallazgo():
    s = separacion()
    problemas = s.comprobar_sin_solapamiento([obs("X", 8, 9), obs("X", 12, 13)])
    assert len(problemas) == 1
    assert "X" in problemas[0]


def test_un_contrato_en_un_solo_tramo_no_reporta_nada():
    s = separacion()
    assert s.comprobar_sin_solapamiento([obs("X", 8, 9), obs("X", 8, 9)]) == ()


def test_reparto_cubre_todas_las_observaciones():
    s = separacion()
    datos = [obs("A", 8, 9), obs("B", 12, 13), obs("C", 16, 17), obs("D", 20, 21),
             obs("E", 9, 11)]
    reparto = s.reparto(datos)
    assert sum(len(v) for v in reparto.values()) == len(datos)
    assert len(reparto["purgada"]) == 1


# -- walk-forward -----------------------------------------------------------


def serie_observables(n=600):
    base = dt.datetime(2026, 10, 1, tzinfo=UTC)
    return [
        Observable(
            f"c{i}",
            base + dt.timedelta(minutes=15 * i),
            base + dt.timedelta(minutes=15 * i + 15),
        )
        for i in range(n)
    ]


def test_walk_forward_solo_entrena_con_pasado():
    datos = serie_observables()
    pasos = list(
        walk_forward(datos, dt.timedelta(days=1), separacion_s=0, minimo_entrenamiento=50)
    )
    assert pasos
    for paso in pasos:
        for indice in paso.entrenamiento + paso.calibracion:
            assert datos[indice].decision_en < paso.inicio_evaluacion
        for indice in paso.evaluacion:
            assert paso.inicio_evaluacion <= datos[indice].decision_en < paso.fin_evaluacion


def test_walk_forward_calibra_con_el_pasado_mas_reciente():
    datos = serie_observables()
    pasos = list(
        walk_forward(datos, dt.timedelta(days=1), separacion_s=0, minimo_entrenamiento=50)
    )
    paso = pasos[0]
    ultimo_entrenamiento = max(datos[i].decision_en for i in paso.entrenamiento)
    primer_calibracion = min(datos[i].decision_en for i in paso.calibracion)
    assert primer_calibracion >= ultimo_entrenamiento


def test_walk_forward_purga_por_disponibilidad():
    datos = serie_observables()
    pasos = list(
        walk_forward(
            datos, dt.timedelta(days=1), separacion_s=3600, minimo_entrenamiento=50
        )
    )
    for paso in pasos:
        for indice in paso.entrenamiento + paso.calibracion:
            assert datos[indice].disponible_en < paso.inicio_evaluacion
        assert len(paso.purgados) > 0


def test_walk_forward_sin_datos_no_produce_pasos():
    assert list(walk_forward([], dt.timedelta(days=1), 0)) == []


def test_bloque_no_positivo_se_rechaza():
    with pytest.raises(ErrorEvaluacion):
        list(walk_forward(serie_observables(10), dt.timedelta(0), 0))


# -- dependencia ------------------------------------------------------------


def test_miles_de_ticks_correlacionados_no_son_miles_de_apuestas():
    rng = np.random.default_rng(1)
    dias = [f"d{i // 100}" for i in range(1000)]
    efecto = {f"d{i}": rng.normal() * 5 for i in range(10)}
    valores = [efecto[d] + rng.normal() * 0.05 for d in dias]
    efectivas = observaciones_efectivas(valores, dias)
    assert efectivas < 20
    assert efectivas >= 1


def test_observaciones_independientes_cuentan_casi_todas():
    rng = np.random.default_rng(2)
    dias = [f"d{i // 100}" for i in range(1000)]
    valores = rng.normal(size=1000).tolist()
    assert observaciones_efectivas(valores, dias) > 500


def test_agregar_por_dia():
    dias, serie = agregar_por_dia([1.0, 2.0, 3.0], ["a", "a", "b"])
    assert dias == ["a", "b"]
    assert list(serie) == [3.0, 3.0]


def test_cota_inferior_positiva_solo_con_serie_consistente():
    buena = bootstrap_bloques_media([1.0, 1.2, 0.9, 1.1, 1.3, 0.8, 1.0, 1.2, 1.1, 0.9])
    assert buena["positiva"] is True
    mala = bootstrap_bloques_media([1.0, -2.0, 1.5, -0.5, 1.2, -0.8, 1.1, -1.4, 0.9, -1.3])
    assert mala["positiva"] is False


def test_la_cota_es_menor_que_la_media():
    r = bootstrap_bloques_media([1.0, 1.2, 0.9, 1.1, 1.3, 0.8, 1.0, 1.2, 1.1, 0.9])
    assert r["cota_inferior"] < r["media"]


def test_bloques_mas_largos_dan_cota_mas_conservadora_con_dependencia():
    rng = np.random.default_rng(5)
    serie = [0.0]
    for _ in range(200):
        serie.append(0.9 * serie[-1] + rng.normal() + 0.5)
    corto = bootstrap_bloques_media(serie, longitud_bloque=1)
    largo = bootstrap_bloques_media(serie, longitud_bloque=20)
    assert largo["cota_inferior"] <= corto["cota_inferior"]


def test_ajuste_por_seleccion_endurece_el_nivel():
    uno = ajuste_por_seleccion(0.1, 1)
    ocho = ajuste_por_seleccion(0.1, 8)
    assert ocho["alfa_ajustado"] < uno["alfa_ajustado"]
    assert ocho["nivel_ajustado"] > uno["nivel_ajustado"]


def test_serie_vacia_se_rechaza():
    with pytest.raises(ErrorEvaluacion):
        bootstrap_bloques_media([])
