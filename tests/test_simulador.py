"""Regresiones del producto: efectivo, cantidades fijas, vencimientos y API."""
import http.client
import json
import math
import threading

import pytest
from scipy.special import ndtr

from quantileflow.simulador import ConfiguracionSimulador, simular
from scripts.simulador_opciones import Handler, Servidor


@pytest.fixture(scope="module")
def ejemplo():
    return simular()


def test_oraculo_independiente_y_toda_la_posicion(ejemplo):
    # CDF normal y fórmula escritos aquí: no usar precio_bs como oráculo.
    p = ejemplo["posiciones"][0]
    assert (p["contrato"], p["cantidad"]) == ("C103-14d", 3)
    t, s, k, r, q, vol = 7/365, 103., 103., .04, .013, .25
    d1 = (math.log(s/k)+(r-q+vol**2/2)*t)/(vol*math.sqrt(t))
    precio = s*math.exp(-q*t)*ndtr(d1)-k*math.exp(-r*t)*ndtr(d1-vol*math.sqrt(t))
    venta = 3*(100*max(0, precio-.04)-.65)
    assert p["pnl_objetivo"] == pytest.approx(venta-p["desembolso"])
    assert p["capital_final"] == pytest.approx(300-p["desembolso"]+venta)
    assert p["capital_reservado"] + p["efectivo_libre"] == pytest.approx(300)
    assert p["pnl_objetivo"] == pytest.approx(148.346040393, abs=1e-8)


def test_superficie_no_redimensiona_ni_usa_el_spot_posterior(ejemplo):
    p = ejemplo["posiciones"][0]
    i_exp = ejemplo["ejes"]["plazos_dias"].index(14)
    j = ejemplo["ejes"]["movimientos_pct"].index(6)
    # Al vencer: max(106-103,0) * 100 * 3, menos primas y ambas comisiones.
    assert p["pnl_por_plazo_movimiento"][i_exp][j] == pytest.approx(
        3*(300-.65)-p["desembolso"])
    for i, d in enumerate(ejemplo["ejes"]["plazos_dias"]):
        if d > 14:
            assert all(v is None for v in p["pnl_por_plazo_movimiento"][i])
    i = ejemplo["ejes"]["plazos_dias"].index(7)
    j = ejemplo["ejes"]["movimientos_pct"].index(3)
    assert p["pnl_por_plazo_movimiento"][i][j] == p["pnl_objetivo"]


def test_control_tardio_no_expulsa_opcion_valida():
    r = simular(ConfiguracionSimulador(dias=10))
    p = next(p for p in r["posiciones"] if p["contrato"] == "C103-14d")
    tarde = p["controles"][-1]
    assert tarde["pnl"] is None and "venció" in tarde["motivo"]
    assert p["pnl_objetivo"] is not None


@pytest.mark.parametrize("cfg", [
    ConfiguracionSimulador(riesgo_pct=0), ConfiguracionSimulador(dias=90),
    ConfiguracionSimulador(presupuesto=1), ConfiguracionSimulador(movimiento_pct=-50),
])
def test_efectivo_y_exclusiones_no_fabrican_ganancias(cfg):
    r = simular(cfg)
    assert r["mejor_objetivo"] == {"contrato": "efectivo", "cantidad": 0, "pnl": 0.}
    assert r["efectivo"]["capital_final"] == cfg.presupuesto
    assert r["probabilidades"] == "no estimadas"
    assert not r["mezcla_series"]


def test_limite_de_riesgo_caja_y_comisiones():
    r = simular(ConfiguracionSimulador(riesgo_pct=50, max_contratos=2))
    for p in r["posiciones"]:
        assert 1 <= p["cantidad"] <= 2
        assert p["capital_reservado"] <= 150 + 1e-10
        assert p["efectivo_libre"] == pytest.approx(300-p["capital_reservado"])
        assert p["reserva_cierre"] == pytest.approx(.65*p["cantidad"])
        assert p["retorno_presupuesto"] == pytest.approx(p["pnl_objetivo"]/300)


def test_cambiar_salida_no_modifica_primas_ni_cantidades(ejemplo):
    r = simular(ConfiguracionSimulador(dias=9, movimiento_pct=4, cambio_iv_pp=-5))
    assert r["cadena"] == ejemplo["cadena"]
    previo = {p["contrato"]: p for p in ejemplo["posiciones"]}
    for p in r["posiciones"]:
        for campo in ("cantidad", "capital_reservado", "desembolso"):
            assert p[campo] == previo[p["contrato"]][campo]


def test_perdida_acotada_y_expiracion_no_depende_de_iv(ejemplo):
    for p in ejemplo["posiciones"]:
        for fila in p["pnl_por_plazo_movimiento"]:
            for v in fila:
                if v is not None:
                    assert v >= -p["perdida_maxima_costos_asumidos"]-1e-9
    r = simular(ConfiguracionSimulador(dias=14))
    p = next(p for p in r["posiciones"] if p["contrato"] == "C103-14d")
    assert len(set(p["pnl_por_iv"])) == 1


def test_iv_imposible_en_control_es_ausente_no_cero():
    r = simular(ConfiguracionSimulador(iv_pct=3))
    p = r["posiciones"][0]
    assert p["controles"][3]["pnl"] is None
    assert p["pnl_por_iv"][0] is None


def test_primas_casi_cero_no_crean_compras_ilimitadas():
    r = simular(ConfiguracionSimulador(iv_pct=1, comision=0, semispread=0))
    assert any("piso" in e["motivo"] for e in r["excluidos"])
    assert all(c["ask"] >= .01 for c in r["cadena"])
    assert len(r["cadena"])+sum("piso" in e["motivo"] for e in r["excluidos"]) == 12
    assert all(p["cantidad"] <= 300 for p in r["posiciones"])


def test_vecindad_recalcula_todos_los_candidatos(ejemplo):
    v = ejemplo["vecindad"]
    assert v["mejores"][1][1] == ejemplo["mejor_objetivo"]
    assert v["mejores"][1][0]["contrato"] == "C100-14d"
    assert v["mejores"][2][0]["contrato"] == "C103-60d"


@pytest.mark.parametrize("datos", [
    {"presupuesto": True}, {"spot": float("nan")}, {"comision": -1},
    {"dias": 7.5}, {"max_contratos": 1.0}, {"riesgo_pct": 101},
    {"iv_pct": 25, "cambio_iv_pp": -25}, {"dias": 100000},
    {"desconocido": 1}, [], {"presupuesto": "300"},
])
def test_rechaza_entradas_ambiguas_o_fuera_de_dominio(datos):
    with pytest.raises(ValueError):
        ConfiguracionSimulador.desde_dict(datos)


@pytest.fixture(scope="module")
def servidor():
    server = Servidor(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=server.serve_forever, daemon=True)
    hilo.start()
    yield server
    server.shutdown()
    hilo.join(timeout=3)
    server.server_close()


def pedir(server, path="/api/simular", body="{}", headers=None, method="POST"):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {"Content-Type": "application/json"})
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        conn.close()


def test_api_devuelve_mismo_modelo_y_solo_archivos_publicos(servidor, ejemplo):
    status, _, contenido = pedir(servidor)
    assert status == 200
    assert json.loads(contenido) == ejemplo
    for path, expected in [("/", 200), ("/app.js", 200), ("/style.css", 200),
                           ("/../../.git/config", 404), ("/data/", 404)]:
        status, tipo, contenido = pedir(servidor, path=path, method="GET")
        assert status == expected
        if expected == 200:
            assert "charset=utf-8" in tipo


def test_no_compartir_puerto_de_otra_aplicacion(servidor):
    with pytest.raises(OSError):
        Servidor(("127.0.0.1", servidor.server_port), Handler)


@pytest.mark.parametrize("body,headers,expected", [
    ("{", {"Content-Type": "application/json"}, 400),
    ('{"presupuesto":true}', {"Content-Type": "application/json"}, 400),
    ("[]", {"Content-Type": "application/json"}, 400),
    ("{}", {"Content-Type": "text/plain"}, 415),
    ("{}", {"Content-Type": "application/json", "Origin": "https://externo.invalid"}, 403),
    ("{}", {"Content-Type": "application/json", "Host": "externo.invalid"}, 403),
    (" " * 8193, {"Content-Type": "application/json"}, 413),
])
def test_api_valida_cuerpo_y_origen(servidor, body, headers, expected):
    assert pedir(servidor, body=body, headers=headers)[0] == expected
