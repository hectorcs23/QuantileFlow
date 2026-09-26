"""Calendario bursátil real, instantes contractuales y etiquetas de 1 y 5 sesiones."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quantileflow import calendario as cal
from quantileflow import etiquetas as et


def test_horario_de_verano_y_zona_horaria():
    assert cal.instante("2025-10-31") == pd.Timestamp("2025-10-31 13:45", tz="UTC")  # EDT
    assert cal.instante("2025-11-03") == pd.Timestamp("2025-11-03 14:45", tz="UTC")  # EST
    assert cal.segundos_locales(cal.instante("2025-11-03"), "2025-11-03") == 9.75 * 3600
    with pytest.raises(ValueError):
        cal.instante("2025-11-27")  # Acción de Gracias: no hay sesión
    with pytest.raises(ValueError):
        cal.instante("2025-11-28", "13:30")  # cierre anticipado a las 13:00


def test_feriados_cierres_anticipados_y_extraordinarios():
    assert not cal.es_sesion("2025-01-09")  # cierre extraordinario (duelo nacional)
    assert cal.sesion_desplazada("2025-01-08", 1) == dt.date(2025, 1, 10)
    assert cal.sesiones("2025-11-24", "2025-12-02") == [
        dt.date(2025, 11, d) for d in (24, 25, 26, 28)] + [dt.date(2025, 12, 1), dt.date(2025, 12, 2)]
    assert cal.cierre("2025-11-28") == pd.Timestamp("2025-11-28 18:00", tz="UTC")  # 13:00 en Nueva York
    assert cal.sesiones_entre("2025-11-26", "2025-12-04") == 5


def test_instante_de_liquidacion_y_plazo():
    assert cal.instante_liquidacion("2025-11-28", "PM") == pd.Timestamp("2025-11-28 18:00", tz="UTC")
    assert cal.instante_liquidacion("2025-11-21", "AM") == pd.Timestamp("2025-11-21 14:30", tz="UTC")
    plazo = cal.plazo_anios(cal.instante("2026-09-21"), cal.instante_liquidacion("2026-09-25", "PM"))
    assert plazo * 365 == pytest.approx(4 + 6.25 / 24)
    with pytest.raises(ValueError):
        cal.instante_liquidacion("2025-11-27", "PM")


def _precios(fechas, valores):
    return pd.Series(valores, index=pd.to_datetime(fechas))


def test_etiquetas_siguen_el_calendario_y_no_los_dias():
    fechas = cal.sesiones("2025-11-20", "2025-12-05")
    precios = _precios(fechas, 100.0 * np.exp(0.01 * np.arange(len(fechas))))
    e = et.etiquetas_retorno(precios, horizontes=(1, 5))
    miercoles = e[(e["sesion"] == dt.date(2025, 11, 26))].set_index("horizonte")
    assert miercoles.loc[1, "sesion_fin"] == dt.date(2025, 11, 28)  # salta el feriado
    assert miercoles.loc[5, "sesion_fin"] == dt.date(2025, 12, 4)
    assert miercoles.loc[1, "label_end_at"] == pd.Timestamp("2025-11-28 14:45", tz="UTC")
    assert miercoles.loc[1, "retorno_log"] == pytest.approx(0.01)
    assert miercoles.loc[5, "retorno_log"] == pytest.approx(0.05)
    viernes = e[(e["sesion"] == dt.date(2025, 11, 21)) & (e["horizonte"] == 1)].iloc[0]
    assert viernes["sesion_fin"] == dt.date(2025, 11, 24)


def test_ausencias_latencia_y_madurez():
    fechas = cal.sesiones("2025-11-03", "2025-11-14")
    valores = np.linspace(100.0, 110.0, len(fechas))
    valores[3] = np.nan  # falta un precio
    precios = _precios(fechas, valores)
    e = et.etiquetas_retorno(precios, horizontes=(1,), latencia_s=60, retraso_publicacion_s=900)
    uno = e.set_index("sesion")
    assert uno.loc[fechas[2], "estado"] == "sin precio final"
    assert uno.loc[fechas[3], "estado"] == "sin precio inicial"
    assert uno.loc[fechas[-1], "estado"] == "sin precio final"  # la siguiente sesión no está en la serie
    assert np.isnan(uno.loc[fechas[2], "retorno_log"])
    fila = uno.loc[fechas[0]]
    assert fila["decision_at"] - fila["inicio_at"] == pd.Timedelta(seconds=60)
    assert fila["label_available_at"] - fila["label_end_at"] == pd.Timedelta(seconds=900)
    # A las 09:55 de la tercera sesión la etiqueta de la segunda termina pero aún no se publica.
    antes = et.etiquetas_maduras(e, cal.instante(fechas[2]) + pd.Timedelta(minutes=10))
    assert list(antes["sesion"]) == [fechas[0]]
    despues = et.etiquetas_maduras(e, cal.instante(fechas[2]) + pd.Timedelta(minutes=15))
    assert list(despues["sesion"]) == [fechas[0], fechas[1]]
    previo = et.movimiento_previo(precios)
    assert np.isnan(previo[fechas[0]]) and np.isnan(previo[fechas[4]])
    assert previo[fechas[1]] == pytest.approx(np.log(valores[1] / valores[0]))


def test_fechas_invalidas_se_rechazan():
    with pytest.raises(ValueError):
        et.etiquetas_retorno(_precios(["2025-11-27"], [1.0]))
    with pytest.raises(ValueError):
        et.etiquetas_retorno(_precios(["2025-11-26", "2025-11-26"], [1.0, 2.0]))
