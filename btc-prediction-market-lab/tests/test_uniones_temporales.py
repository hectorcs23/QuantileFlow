"""Uniones as-of hacia atras, velas cerradas, huecos y secuencias."""

import datetime as dt

import pytest

from btclab.tiempo import ErrorTiempo, Observacion, desde_iso, exigir_utc
from btclab.union import (
    ErrorUnion,
    detectar_huecos,
    detectar_saltos_secuencia,
    ultimo_disponible,
    unir_hacia_atras,
    vela_cerrada_en,
    velas_disponibles,
)


def obs(evento, recibido, valor=None, secuencia=None):
    return Observacion(
        event_time=desde_iso(evento),
        received_at=desde_iso(recibido),
        fuente="test",
        payload={"v": valor if valor is not None else evento},
        secuencia=secuencia,
    )


def test_un_datetime_ingenuo_se_rechaza():
    with pytest.raises(ErrorTiempo):
        exigir_utc(dt.datetime(2026, 10, 15, 12, 0))


def test_mensaje_con_marca_antigua_recibido_despues_no_esta_disponible():
    datos = [
        obs("2026-10-15T12:00:00Z", "2026-10-15T12:00:01Z", "viejo_pronto"),
        obs("2026-10-15T12:00:02Z", "2026-10-15T12:00:30Z", "nuevo_tarde"),
    ]
    r = ultimo_disponible(datos, desde_iso("2026-10-15T12:00:10Z"))
    assert r.observacion.payload["v"] == "viejo_pronto"


def test_union_usa_received_at_no_event_time():
    datos = [obs("2026-10-15T11:00:00Z", "2026-10-15T12:00:00Z", "a")]
    # El evento es de las 11:00 pero llego a las 12:00: a las 11:30 no existia.
    assert not ultimo_disponible(datos, desde_iso("2026-10-15T11:30:00Z")).disponible
    assert ultimo_disponible(datos, desde_iso("2026-10-15T12:00:00Z")).disponible


def test_igualdad_exacta_cuenta_como_disponible():
    datos = [obs("2026-10-15T12:00:00Z", "2026-10-15T12:00:00Z")]
    assert ultimo_disponible(datos, desde_iso("2026-10-15T12:00:00Z")).disponible


def test_cotizacion_caducada_se_descarta_con_motivo():
    datos = [obs("2026-10-15T12:00:00Z", "2026-10-15T12:00:00Z")]
    r = ultimo_disponible(datos, desde_iso("2026-10-15T12:00:09Z"), antiguedad_max_s=5.0)
    assert not r.disponible
    assert "caducada" in r.motivo
    assert r.antiguedad_s == 9.0


def test_sin_observaciones_previas_devuelve_motivo():
    r = ultimo_disponible([], desde_iso("2026-10-15T12:00:00Z"))
    assert not r.disponible
    assert r.observacion is None


def test_unir_hacia_atras_en_varios_momentos():
    datos = [
        obs("2026-10-15T12:00:00Z", "2026-10-15T12:00:00Z", "a"),
        obs("2026-10-15T12:00:05Z", "2026-10-15T12:00:05Z", "b"),
    ]
    momentos = [desde_iso(f"2026-10-15T12:00:{s:02d}Z") for s in (1, 6)]
    valores = [r.observacion.payload["v"] for r in unir_hacia_atras(momentos, datos)]
    assert valores == ["a", "b"]


def test_vela_en_curso_no_se_usa():
    momento = desde_iso("2026-10-15T12:00:10Z")
    assert vela_cerrada_en(desde_iso("2026-10-15T12:00:10Z"), momento) is True
    assert vela_cerrada_en(desde_iso("2026-10-15T12:00:11Z"), momento) is False


def test_margen_de_publicacion_de_velas():
    momento = desde_iso("2026-10-15T12:00:10Z")
    fin = desde_iso("2026-10-15T12:00:09Z")
    assert vela_cerrada_en(fin, momento, margen_s=0.0) is True
    assert vela_cerrada_en(fin, momento, margen_s=5.0) is False


def test_velas_disponibles_filtra_la_abierta():
    velas = [
        {"fin_periodo": desde_iso("2026-10-15T12:00:00Z"), "c": 1},
        {"fin_periodo": desde_iso("2026-10-15T12:01:00Z"), "c": 2},
    ]
    usables = velas_disponibles(velas, desde_iso("2026-10-15T12:00:30Z"))
    assert [v["c"] for v in usables] == [1]


def test_vela_sin_fin_de_periodo_falla():
    with pytest.raises(ErrorUnion):
        velas_disponibles([{"c": 1}], desde_iso("2026-10-15T12:00:00Z"))


def test_huecos_se_detectan_y_no_se_interpolan():
    datos = [
        obs("2026-10-15T12:00:00Z", "2026-10-15T12:00:00Z"),
        obs("2026-10-15T12:00:05Z", "2026-10-15T12:00:05Z"),
        obs("2026-10-15T12:01:00Z", "2026-10-15T12:01:00Z"),
    ]
    huecos = detectar_huecos(datos, intervalo_esperado_s=10.0)
    assert len(huecos) == 1
    assert huecos[0].duracion_s == 55.0


def test_intervalo_esperado_no_positivo_falla():
    with pytest.raises(ErrorUnion):
        detectar_huecos([], 0.0)


def test_salto_de_secuencia_invalida_la_reconstruccion():
    datos = [
        obs("2026-10-15T12:00:00Z", "2026-10-15T12:00:00Z", secuencia=1),
        obs("2026-10-15T12:00:01Z", "2026-10-15T12:00:01Z", secuencia=2),
        obs("2026-10-15T12:00:02Z", "2026-10-15T12:00:02Z", secuencia=7),
    ]
    assert detectar_saltos_secuencia(datos) == ((2, 7),)


def test_secuencia_consecutiva_no_reporta_saltos():
    datos = [
        obs("2026-10-15T12:00:00Z", "2026-10-15T12:00:00Z", secuencia=i)
        for i in (1, 2, 3)
    ]
    assert detectar_saltos_secuencia(datos) == ()


def test_latencia_negativa_se_reporta_tal_cual():
    # Reloj de la fuente adelantado: no se recorta, se deja como hallazgo.
    o = obs("2026-10-15T12:00:05Z", "2026-10-15T12:00:00Z")
    assert o.latencia_s == -5.0
