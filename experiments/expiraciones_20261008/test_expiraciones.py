import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from comparar_expiraciones import cambios, configuraciones, medir_objetivo
from quantileflow import alpaca, piloto
from quantileflow.calendario import instante


def test_union_sin_duplicados_y_equivalencia_un_solo_objetivo():
    fechas = ["2026-10-08", "2026-10-09", "2026-10-15", "2026-10-22", "2026-11-05", "2026-11-09"]
    corte = instante("2026-10-08", "09:45")
    original = alpaca.elegir_vencimientos(fechas, "PM", corte, 30, 2, True)
    assert alpaca.elegir_vencimientos_multiples(iter(fechas), "PM", corte, [30], 2, True) == original
    union = alpaca.elegir_vencimientos_multiples(iter(fechas), "PM", corte, [7, 14, 30], 1, True)
    esperado = set()
    for d in (7, 14, 30):
        esperado.update(alpaca.elegir_vencimientos(fechas, "PM", corte, d, 1, True)[0])
    assert union[0] == sorted(esperado)


@pytest.mark.parametrize("objetivos", [[], [0], [-1], [float("nan")], [float("inf")], [7, 7], [True], ["7"]])
def test_rechaza_objetivos_invalidos(objetivos):
    with pytest.raises(ValueError):
        alpaca.elegir_vencimientos_multiples([], "PM", instante("2026-10-08", "09:45"), objetivos)


def test_no_interpola_desde_0dte_ni_extrapola_ni_acepta_hueco_grande():
    cfg = piloto.cargar_config(ROOT / "configs/piloto.toml")
    cfg = configuraciones(cfg, {"horizontes": [{"dias": 7, "separacion_maxima_dias": 7}]})[0]
    assert medir_objetivo({}, {"cero": .25, "mensual": 30}, cfg)["estado"] == "no identificada"
    assert medir_objetivo({}, {"semana": 6}, cfg)["estado"] == "no identificada"
    assert medir_objetivo({}, {"corto": 2, "largo": 14}, cfg)["estado"] == "no identificada"


def test_interpola_varianza_total_por_pata_no_rr_directamente():
    cfg = replace(piloto.cargar_config(ROOT / "configs/piloto.toml"), objetivo_dias=7,
                  minimo_dias=1, separacion_maxima_dias=7)
    def rr(c, p):
        return {"estado": "identificada", "iv_call": c, "iv_put": p,
                "iv_call_banda": [c-.01, c+.01], "iv_put_banda": [p-.01, p+.01]}
    result = medir_objetivo({"a": rr(.2, .3), "b": rr(.4, .35)}, {"a": 6, "b": 8}, cfg)
    c = ((.2**2*6 + .4**2*8)/2/7)**.5
    p = ((.3**2*6 + .35**2*8)/2/7)**.5
    assert result["valor"] == pytest.approx(c-p)
    assert result["valor"] != pytest.approx((-.1+.05)/2)
    assert result["vencimientos"] == ["a", "b"]


def test_banda_cambio_no_equivale_a_confianza_estadistica():
    a = {"estado": "identificada", "valor": .01, "inferior": 0, "superior": .02}
    b = {"estado": "identificada", "valor": .02, "inferior": .01, "superior": .03}
    d = cambios(a, b)
    assert d["inferior"] == pytest.approx(-.01)
    assert d["superior"] == pytest.approx(.03)
    assert not d["excluye_cero"]


def test_calendario_medio_dia_0dte_y_vencimientos_liquidados():
    elegidos, plazos = alpaca.elegir_vencimientos_multiples(
        ["2026-11-26", "2026-11-27", "2026-11-30"], "PM", instante("2026-11-27", "09:45"), [7], 1, True)
    assert "2026-11-26" not in {str(v) for v in plazos}  # Thanksgiving
    assert plazos[next(v for v in plazos if str(v) == "2026-11-27")] == pytest.approx(3.25/24)
    assert len(elegidos) == 2


def test_seleccion_cubre_60_y_90_y_config_consulta_hasta_120():
    import tomllib
    with Path(__file__).with_name("captura_propuesta.toml").open("rb") as f:
        cfg = tomllib.load(f)["captura"]
    assert cfg["ventana_contratos_dias"] >= 120
    assert all(o["objetivos_dias"] == [7, 14, 30, 60, 90] and "objetivo_dias" not in o
               for o in cfg["opciones"])
    fechas = ["2026-12-04", "2026-12-07", "2026-12-08", "2027-01-05", "2027-01-06", "2027-01-07"]
    elegidos, plazos = alpaca.elegir_vencimientos_multiples(
        fechas, "PM", instante("2026-10-08", "09:45"), [60, 90], 1)
    dias = [plazos[v] for v in elegidos]
    for objetivo in (60, 90):
        assert any(d < objetivo for d in dias) and any(d > objetivo for d in dias)
