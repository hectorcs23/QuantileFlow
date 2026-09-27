"""Calendario bursátil real, instantes contractuales y etiquetas de 1 y 5 sesiones."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quantileflow import calendario as cal
from quantileflow import contrato as ct
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


def test_etiqueta_madura_cuando_el_precio_final_esta_disponible():
    # H3: si el precio final se publica tarde, la etiqueta madura con él, no con el reloj.
    fechas = cal.sesiones("2025-11-03", "2025-11-07")
    precios = _precios(fechas, np.linspace(100.0, 104.0, len(fechas)))
    disponibles = pd.Series({f: cal.instante(f) for f in fechas})
    disponibles[fechas[1]] = cal.instante(fechas[1]) + pd.Timedelta(hours=3)
    e = et.etiquetas_retorno(precios, horizontes=(1,), retraso_publicacion_s=60, disponibles=disponibles)
    uno = e.set_index("sesion")
    assert uno.loc[fechas[0], "label_available_at"] == cal.instante(fechas[1]) + pd.Timedelta(hours=3)
    assert uno.loc[fechas[1], "label_available_at"] == cal.instante(fechas[2]) + pd.Timedelta(seconds=60)


NY = "America/New_York"


def _ny(texto):
    return pd.Timestamp(texto, tz=NY).tz_convert("UTC")


def _dividendos(*versiones):
    """Versiones ``(fecha_ex, monto, conocida_desde, retirada_en[, motivo[, discrepancia_desde[, tipo]]])``.

    Con el esquema ``contrato.DIVIDENDOS``; la discrepancia es «ausente» si no se dice otra cosa.
    """
    filas = []
    for ex, monto, desde, hasta, *resto in versiones:
        motivo = resto[0] if resto else ("corregido" if hasta is not None else "")
        discrepancia = resto[1] if len(resto) > 1 else None
        filas.append({"simbolo": "SPY", "fecha_ex": pd.Timestamp(ex).date(), "monto": monto, "fecha_pago": None,
                      "clase": "ordinario", "disponible_utc": pd.NaT, "recibido_utc": desde, "retirado_utc": hasta,
                      "motivo_retiro": motivo,
                      "discrepancia": (resto[2] if len(resto) > 2 else "ausente") if discrepancia is not None else "",
                      "discrepancia_desde_utc": discrepancia, "proveedor": "prueba", "feed": "eventos"})
    tabla = pd.DataFrame(filas, columns=list(ct.DIVIDENDOS)).astype({"monto": float})
    for columna in ("disponible_utc", "recibido_utc", "retirado_utc", "discrepancia_desde_utc"):
        tabla[columna] = pd.to_datetime(tabla[columna], utc=True)
    assert ct.validar(tabla, ct.DIVIDENDOS) == []
    return tabla


def _consultas(*recepciones, estado="completa", desde="2025-01-01", hasta="2026-12-31", tipos="todos",
               calidad="complete"):
    """Consultas de eventos de SPY con el esquema de ``contrato.COBERTURA_DIVIDENDOS``."""
    filas = [{"simbolo": "SPY", "desde": pd.Timestamp(desde).date(), "hasta": pd.Timestamp(hasta).date(),
              "campo_fecha": "process_date", "recibido_utc": r, "estado": estado, "eventos": 0.0,
              "calidad": calidad, "tipos": tipos, "consulta": f"q{i}", "proveedor": "prueba", "feed": "eventos"}
             for i, r in enumerate(recepciones)]
    tabla = pd.DataFrame(filas, columns=list(ct.COBERTURA_DIVIDENDOS)).astype({"eventos": float})
    tabla["recibido_utc"] = pd.to_datetime(tabla["recibido_utc"], utc=True)
    assert ct.validar(tabla, ct.COBERTURA_DIVIDENDOS) == []
    return tabla


def test_dividendo_en_el_rendimiento_total_y_en_la_madurez():
    fechas = cal.sesiones("2025-11-17", "2025-11-21")
    precios = _precios(fechas, [100.0, 101.0, 99.5, 100.0, 100.5])
    dividendo = _dividendos((fechas[2], 1.5, _ny("2025-11-10 10:21"), None))  # ex el miércoles, conocido antes
    diarias = _consultas(*[cal.instante(f, "10:21") for f in fechas])  # como el workflow del histórico
    e = et.etiquetas_retorno(precios, horizontes=(1, 2), dividendos=dividendo, cobertura=diarias)
    e = e.set_index(["sesion", "horizonte"])
    cruza = e.loc[(fechas[1], 1)]  # de 09:45 del día anterior a 09:45 del día ex: incluye la apertura ex
    assert cruza["dividendos"] == 1.5 and cruza["estado_dividendos"] == "provisional"
    assert cruza["retorno_log"] == pytest.approx(np.log((99.5 + 1.5) / 101.0))
    assert cruza["retorno_precio_log"] == pytest.approx(np.log(99.5 / 101.0))
    # Madura con la consulta habilitante: la primera completa que cubre el periodo, recibida después del fin.
    assert cruza["label_available_at"] == cruza["consulta_habilitante_utc"] == cal.instante(fechas[2], "10:21")
    assert e.loc[(fechas[2], 1), "dividendos"] == 0.0  # empieza a las 09:45 del día ex: ya no lo cobra
    assert e.loc[(fechas[0], 1), "dividendos"] == 0.0 and e.loc[(fechas[0], 2), "dividendos"] == 1.5
    assert e.loc[(fechas[2], 1), "retorno_log"] == e.loc[(fechas[2], 1), "retorno_precio_log"]
    sin_tabla = et.etiquetas_retorno(precios, horizontes=(1,)).set_index("sesion")  # índice de precio
    assert sin_tabla.loc[fechas[1], "retorno_log"] == sin_tabla.loc[fechas[1], "retorno_precio_log"]
    assert sin_tabla.loc[fechas[1], "estado_dividendos"] == "no aplica"
    with pytest.raises(ValueError, match="no es una sesión"):
        et.etiquetas_retorno(precios, dividendos=_dividendos((dt.date(2025, 11, 22), 1.5, _ny("2025-11-10"), None)),
                             cobertura=diarias)


def test_una_consulta_futura_no_habilita_etiquetas_en_el_pasado():
    # Revisión de 8c97b2b, P1: periodo del 17 al 18 de noviembre de 2025, de 09:45 a 09:45 de Nueva York.
    fechas = cal.sesiones("2025-11-17", "2025-11-18")
    precios = _precios(fechas, [100.0, 100.0])
    disponibles = pd.Series({f: cal.instante(f) + pd.Timedelta(minutes=15) for f in fechas})
    kw = dict(horizontes=(1,), retraso_publicacion_s=900, disponibles=disponibles, dividendos=_dividendos())
    solo_antes = et.etiquetas_retorno(precios, cobertura=_consultas(_ny("2025-11-17 16:00")), **kw).iloc[0]
    assert solo_antes["estado"] == "sin dividendos confirmados" and "anterior al fin" in solo_antes["motivo"]
    ambas = et.etiquetas_retorno(precios, cobertura=_consultas(_ny("2025-11-17 16:00"), _ny("2025-11-20 16:00")),
                                 **kw)
    assert ambas.iloc[0]["estado"] == "ok" and ambas.iloc[0]["label_available_at"] == _ny("2025-11-20 16:00")
    assert et.etiquetas_maduras(ambas, _ny("2025-11-18 10:00")).empty  # sigue ausente el 18 a las 10:00
    assert len(et.etiquetas_maduras(ambas, _ny("2025-11-20 16:00"))) == 1
    # Añadir consultas posteriores a un instante no cambia lo que era utilizable en él.
    recepciones = [_ny("2025-11-17 16:00"), _ny("2025-11-18 09:50"), _ny("2025-11-18 16:00"), _ny("2025-11-20 16:00")]
    todas = et.etiquetas_retorno(precios, cobertura=_consultas(*recepciones), **kw)
    for k, recibida in enumerate(recepciones):
        t = recibida + pd.Timedelta(minutes=1)
        hasta_t = et.etiquetas_retorno(precios, cobertura=_consultas(*recepciones[:k + 1]), **kw)
        reconstruida = et.etiquetas_retorno(precios, cobertura=_consultas(*recepciones), conocido_hasta=t, **kw)
        columnas = ["sesion", "horizonte", "retorno_log", "label_available_at"]
        for tabla in (hasta_t, reconstruida):
            pd.testing.assert_frame_equal(et.etiquetas_maduras(tabla, t)[columnas].reset_index(drop=True),
                                          et.etiquetas_maduras(todas, t)[columnas].reset_index(drop=True))


def test_versiones_de_un_dividendo_revisan_la_etiqueta():
    # Revisión de 8c97b2b, P2: cancelación, corrección de importe y cambio de fecha ex, antes y después de
    # conocerlos.
    fechas = cal.sesiones("2025-11-17", "2025-11-21")
    precios = _precios(fechas, [100.0] * len(fechas))
    diarias = _consultas(*[cal.instante(f, "10:21") for f in cal.sesiones("2025-11-17", "2025-11-26")])
    conocido, revision = _ny("2025-11-17 10:21"), _ny("2025-11-24 10:21")

    def por_sesion(dividendos, t=None):
        e = et.etiquetas_retorno(precios, horizontes=(1,), dividendos=dividendos, cobertura=diarias)
        vigentes = e if t is None else et.etiquetas_maduras(e, t)
        return e, vigentes.set_index("sesion")["retorno_log"]

    # Cancelación registrada el 24: el dividendo del martes 18 deja de sumarse desde entonces.
    retirado = _dividendos((fechas[1], 1.8, conocido, revision, "cancelado"))
    e, antes = por_sesion(retirado, revision - pd.Timedelta(minutes=1))
    _, despues = por_sesion(retirado, revision)
    lunes = e[e["sesion"] == fechas[0]]
    assert list(lunes["version"]) == [1, 2] and list(lunes["estado_dividendos"]) == ["provisional", "provisional"]
    assert lunes.iloc[0]["vigente_hasta_utc"] == lunes.iloc[1]["vigente_desde_utc"] == revision
    assert antes[fechas[0]] == pytest.approx(np.log(101.8 / 100.0)) and despues[fechas[0]] == 0.0
    reconstruida = et.etiquetas_retorno(precios, horizontes=(1,), dividendos=retirado, cobertura=diarias,
                                        conocido_hasta=revision - pd.Timedelta(minutes=1))
    assert list(reconstruida.loc[reconstruida["sesion"] == fechas[0], "dividendos"]) == [1.8]  # aún no se sabía
    # Corrección de importe: 1.80 -> 1.85 el 24.
    corregido = _dividendos((fechas[1], 1.8, conocido, revision), (fechas[1], 1.85, revision, None))
    _, antes = por_sesion(corregido, revision - pd.Timedelta(minutes=1))
    _, despues = por_sesion(corregido, revision)
    assert antes[fechas[0]] == pytest.approx(np.log(101.8 / 100.0))
    assert despues[fechas[0]] == pytest.approx(np.log(101.85 / 100.0))
    # Cambio de fecha ex: del martes 18 al jueves 20, el 24; el dividendo cambia de etiqueta.
    movido = _dividendos((fechas[1], 1.8, conocido, revision), (fechas[3], 1.8, revision, None))
    _, antes = por_sesion(movido, revision - pd.Timedelta(minutes=1))
    _, despues = por_sesion(movido, revision)
    assert antes[fechas[0]] == pytest.approx(np.log(1.018)) and antes[fechas[2]] == 0.0
    assert despues[fechas[0]] == 0.0 and despues[fechas[2]] == pytest.approx(np.log(1.018))


def test_consulta_vacia_distinta_de_fallida_o_inexistente():
    # Revisión de 8c97b2b, P2: una respuesta vacía conserva su consulta.
    fechas = cal.sesiones("2025-11-17", "2025-11-18")
    precios = _precios(fechas, [100.0, 100.5])
    despues = _ny("2025-11-18 16:00")

    def unica(cobertura):
        return et.etiquetas_retorno(precios, horizontes=(1,), dividendos=_dividendos(), cobertura=cobertura).iloc[0]

    vacia = unica(_consultas(despues))
    assert vacia["estado"] == "ok" and vacia["dividendos"] == 0.0 and vacia["label_available_at"] == despues
    fallida = unica(_consultas(despues, estado="fallida"))
    assert fallida["estado"] == "sin dividendos confirmados"
    assert fallida["motivo"] == "sin consulta completa de dividendos; 1 consultas parciales o fallidas no cuentan"
    assert unica(None)["motivo"] == "sin consulta completa de dividendos"
    corta = unica(_consultas(despues, hasta="2025-12-01"))  # no llega a fin + 60 días de procesamiento
    assert corta["motivo"] == "ninguna consulta completa de dividendos cubre el periodo"


def test_aceptada_despues_del_margen_de_proceso():
    fechas = cal.sesiones("2025-11-17", "2025-11-18")
    precios = _precios(fechas, [100.0, 100.5])
    consultas = _consultas(_ny("2025-11-18 16:00"), _ny("2026-01-20 16:00"))
    e = et.etiquetas_retorno(precios, horizontes=(1,), dividendos=_dividendos(), cobertura=consultas,
                             margen_proceso_dias=60)
    e = e[e["sesion"] == fechas[0]]  # la del 18 no tiene precio final
    assert list(e["estado_dividendos"]) == ["provisional", "aceptada"] and list(e["version"]) == [1, 1]
    assert e.iloc[1]["vigente_desde_utc"] == _ny("2026-01-20 16:00")
    assert len(et.etiquetas_maduras(e, _ny("2025-12-01"))) == 1  # provisional ya utilizable
    assert et.etiquetas_maduras(e, _ny("2025-12-01"), politica="aceptada").empty
    assert len(et.etiquetas_maduras(e, _ny("2026-01-21"), politica="aceptada")) == 1
    with pytest.raises(ValueError, match="politica"):
        et.etiquetas_maduras(e, _ny("2026-01-21"), politica="cualquiera")


def test_ausencia_sin_resolver_queda_pendiente_y_fuera_de_la_politica_aceptada():
    # Revalidación de a5e2748, P1: el dividendo del 18 de noviembre falta en la consulta comparable del 20 de enero.
    fechas = cal.sesiones("2025-11-17", "2025-11-18")
    precios = _precios(fechas, [100.0, 100.0])
    conocido, ausente = _ny("2025-11-17 16:00"), _ny("2026-01-20 16:00")
    diarias = [_ny("2025-11-18 16:00"), ausente, _ny("2026-01-21 16:00"), _ny("2026-03-20 16:00")]

    def etiquetas(dividendos, consultas=diarias, hasta=None):
        e = et.etiquetas_retorno(precios, horizontes=(1,), dividendos=dividendos, cobertura=_consultas(*consultas),
                                 conocido_hasta=hasta)
        return e[e["sesion"] == fechas[0]]  # la del 18 no tiene precio final

    sin_resolver = _dividendos((fechas[1], 1.8, conocido, None, "", ausente))
    e = etiquetas(sin_resolver)
    assert list(e["estado_dividendos"]) == ["provisional", "pendiente"] and list(e["dividendos"]) == [1.8, 1.8]
    assert "ausente en una consulta comparable" in e.iloc[1]["motivo"] and "sin resolver" in e.iloc[1]["motivo"]
    for t in (ausente, _ny("2026-01-21 17:00"), _ny("2026-03-21")):  # ni pasados 60 días, ni repitiendo la ausencia
        assert et.etiquetas_maduras(e, t, politica="aceptada").empty
        assert et.etiquetas_maduras(e, t).iloc[0]["estado_dividendos"] == "pendiente"  # valor de diagnóstico, marcado
    antes = etiquetas(sin_resolver, hasta=ausente - pd.Timedelta(minutes=1))  # antes de la ausencia
    assert list(antes["estado_dividendos"]) == ["provisional"] and list(antes["dividendos"]) == [1.8]
    # Reaparece igual el 25 de enero: la discrepancia se resuelve y esa consulta la acepta.
    resuelta = _ny("2026-01-25 16:00")
    reaparecido = _dividendos((fechas[1], 1.8, conocido, resuelta, "reaparecido", ausente),
                              (fechas[1], 1.8, resuelta, None))
    e = etiquetas(reaparecido, diarias + [resuelta])
    assert list(e["estado_dividendos"]) == ["provisional", "pendiente", "aceptada"]
    assert e.iloc[2]["vigente_desde_utc"] == resuelta and e.iloc[2]["dividendos"] == 1.8
    # Una cancelación registrada el 25 revisa el valor y solo la consulta siguiente lo acepta.
    cancelado = _dividendos((fechas[1], 1.8, conocido, resuelta, "cancelado", ausente))
    e = etiquetas(cancelado, diarias + [_ny("2026-01-26 16:00")])
    assert list(e["estado_dividendos"]) == ["provisional", "pendiente", "provisional", "aceptada"]
    assert list(e["version"]) == [1, 1, 2, 2] and list(e["dividendos"]) == [1.8, 1.8, 0.0, 0.0]
    # El 2 de febrero el proveedor lo trae con otro monto: otra discrepancia, que solo resuelve otra resolución.
    vuelve, confirmado = _ny("2026-02-02 16:00"), _ny("2026-02-05 16:00")
    conflicto = (fechas[1], 1.9, vuelve, None, "", vuelve, "reaparece_cancelado")
    e = etiquetas(_dividendos((fechas[1], 1.8, conocido, resuelta, "cancelado", ausente), conflicto),
                  diarias + [_ny("2026-01-26 16:00"), vuelve])
    assert list(e["estado_dividendos"]) == ["provisional", "pendiente", "provisional", "aceptada", "pendiente"]
    assert "cancelado por una resolución y de nuevo en el proveedor" in e.iloc[-1]["motivo"]
    assert e.iloc[-1]["dividendos"] == 1.9 and e.iloc[-1]["version"] == 3
    assert et.etiquetas_maduras(e, _ny("2026-03-21"), politica="aceptada").empty
    confirmada = _dividendos((fechas[1], 1.8, conocido, resuelta, "cancelado", ausente),
                             conflicto[:3] + (confirmado, "confirmado") + conflicto[5:],
                             (fechas[1], 1.9, confirmado, None))
    e = etiquetas(confirmada, diarias + [_ny("2026-01-26 16:00"), vuelve])
    assert list(e["estado_dividendos"])[-3:] == ["pendiente", "provisional", "aceptada"]
    assert e.iloc[-1]["vigente_desde_utc"] == _ny("2026-03-20 16:00")  # la primera consulta tras la resolución


def test_una_consulta_sin_dividendos_en_sus_tipos_no_confirma_ni_acepta():
    # Revalidación de a5e2748, P2: una consulta que solo pidió splits no dice nada de los dividendos.
    fechas = cal.sesiones("2025-11-17", "2025-11-18")
    precios = _precios(fechas, [100.0, 100.5])
    tarde = _ny("2026-01-20 16:00")

    def unica(**kw):
        e = et.etiquetas_retorno(precios, horizontes=(1,), dividendos=_dividendos(), cobertura=_consultas(tarde, **kw))
        return e[e["sesion"] == fechas[0]].iloc[-1]

    splits = unica(tipos="forward_split")
    assert splits["estado"] == "sin dividendos confirmados"
    assert "1 consultas sin dividendos en los tipos pedidos no cuentan" in splits["motivo"]
    assert "con calidad distinta de complete" in unica(calidad="all")["motivo"]
    for tipos in ("todos", "cash_dividend", "forward_split,cash_dividend"):
        assert unica(tipos=tipos)["estado_dividendos"] == "aceptada"


def test_la_vista_de_un_instante_coincide_con_la_reconstruccion_truncada():
    # Revalidación de a5e2748, P3: mismos retornos, madurez y estados; nada posterior al instante.
    fechas = cal.sesiones("2025-11-17", "2025-11-21")
    precios = _precios(fechas, [100.0, 101.0, 99.5, 100.0, 100.5])
    conocido, correccion, ausente, reaparece = (_ny("2025-11-10 16:00"), _ny("2025-11-25 16:00"),
                                                _ny("2026-01-22 16:00"), _ny("2026-01-27 16:00"))
    dividendos = _dividendos((fechas[2], 1.5, conocido, correccion),
                             (fechas[2], 1.55, correccion, reaparece, "reaparecido", ausente),
                             (fechas[2], 1.55, reaparece, None))
    recepciones = [cal.instante(f, "16:00") for f in fechas] + [correccion, ausente, reaparece,
                                                               _ny("2026-01-20 16:00"), _ny("2026-01-28 16:00")]
    cobertura = _consultas(*sorted(recepciones))
    kw = dict(horizontes=(1, 2), dividendos=dividendos, cobertura=cobertura)
    historia = et.etiquetas_retorno(precios, **kw)
    assert {"provisional", "pendiente", "aceptada"} <= set(historia["estado_dividendos"])
    columnas = ["sesion", "horizonte", "retorno_log", "label_available_at", "estado_dividendos", "version",
                "tramo", "vigente_desde_utc", "vigente_hasta_utc", "motivo"]
    instantes = sorted(set(recepciones)) + [_ny("2025-12-01 12:00"), _ny("2026-01-19 12:00"), _ny("2026-03-01")]
    for t in instantes:
        truncada = et.etiquetas_retorno(precios, conocido_hasta=t, **kw)
        for politica in et.POLITICAS:
            a = et.etiquetas_maduras(historia, t, politica)[columnas].reset_index(drop=True)
            b = et.etiquetas_maduras(truncada, t, politica)[columnas].reset_index(drop=True)
            pd.testing.assert_frame_equal(a, b)
            assert a["vigente_hasta_utc"].isna().all()  # el fin del tramo es futuro: no se expone
    # El caso de la revisión: el 1 de diciembre, la historia completa ya no dice «aceptada».
    vista = et.etiquetas_maduras(historia, _ny("2025-12-01 12:00"))
    assert "aceptada" not in set(vista["estado_dividendos"])
