"""Adaptador de Alpaca sin red: cliente, crudo, manifiestos, normalización, replay y subyacente implícito.

Las respuestas tienen la forma de las reales (verificada el 26 de septiembre de
2026), pero sus precios salen del mercado **sintético**.
"""
import dataclasses
import datetime as dt
import gzip
import http.client
import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
import tomllib
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantileflow import alpaca as al
from quantileflow import almacen
from quantileflow import calendario as cal
from quantileflow import contrato as ct
from quantileflow import diagnostico as dg
from quantileflow import etiquetas as et
from quantileflow import implicito as im
from quantileflow import operacion
from quantileflow import piloto as pl
from quantileflow import sintetico as sn

RAIZ = Path(__file__).resolve().parents[1]
CLAVE, SECRETO = "PKPRUEBA0123456789", "secreto-que-no-debe-aparecer"
CLIENTE_REAL, VIGILANTE_REAL = al.ClienteAlpaca, al.Vigilante  # antes de cualquier sustitución en una prueba
FECHAS = cal.sesiones("2025-11-17", "2025-11-18")


class Reloj:
    """Reloj falso: devuelve ``actual`` y avanza al dormir."""

    def __init__(self, inicio):
        self.actual = pd.Timestamp(inicio)
        self.siestas = []

    def __call__(self):
        return self.actual

    def dormir(self, segundos):
        self.siestas.append(segundos)
        self.actual += pd.Timedelta(seconds=segundos)


class API:
    """Transporte falso: responde según la ruta; ``fallos`` inyecta estados antes de responder bien."""

    def __init__(self, rutas, fallos=None):
        self.rutas = rutas  # ruta -> función(params) -> dict
        self.fallos = dict(fallos or {})
        self.vistas = []

    def __call__(self, url, cabeceras, tiempo_max):
        partes = urllib.parse.urlsplit(url)
        params = dict(urllib.parse.parse_qsl(partes.query))
        self.vistas.append((partes.path, params, dict(cabeceras)))
        pendientes = self.fallos.get(partes.path, [])
        if pendientes:
            estado = pendientes.pop(0)
            if estado == "red":
                raise OSError("conexión reiniciada")
            if estado == "cortada":
                raise http.client.IncompleteRead(b'{"par')
            return estado, {"x-ratelimit-reset": "0"}, b'{"message":"falla inyectada"}'
        cuerpo = json.dumps(self.rutas[partes.path](params)).encode()
        return 200, {"date": "Mon, 17 Nov 2025 14:44:55 GMT", "content-type": "application/json",
                     "x-ratelimit-limit": "200", "x-ratelimit-remaining": "199"}, cuerpo


def cliente(transporte, reloj=None, **kw):
    reloj = reloj or Reloj("2025-11-17T14:44:55Z")
    return al.ClienteAlpaca(al.Credenciales(CLAVE, SECRETO), transporte, reloj, reloj.dormir, **kw)


# --- Respuestas con la forma de Alpaca a partir del mercado sintético ------------------------------

def _t(instante):
    """Hora con nanosegundos, como la da Alpaca."""
    return pd.Timestamp(instante).strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z"


def contratos_json(cot):
    unicos = cot.drop_duplicates("id_contrato")
    return {"option_contracts": [
        {"symbol": f.id_contrato, "root_symbol": f.raiz, "underlying_symbol": f.subyacente,
         "expiration_date": str(f.vencimiento), "type": "call" if f.tipo == "C" else "put",
         "style": "european", "strike_price": f"{f.strike:g}", "multiplier": "100", "status": "active"}
        for f in unicos.itertuples()], "next_page_token": None}


def cadena_json(cot, vencimiento, corte, sin_cotizacion=()):
    filas = cot[(cot["vencimiento"].map(str) == vencimiento) & (cot["sello_snapshot_utc"] == corte)]
    snaps = {}
    for f in filas.itertuples():
        if f.id_contrato in sin_cotizacion:
            snaps[f.id_contrato] = {"dailyBar": {"c": 1.0}}
            continue
        snaps[f.id_contrato] = {"latestQuote": {
            "bp": f.bid, "ap": f.ask, "bs": int(f.tam_bid), "as": int(f.tam_ask), "bx": "C", "ax": "C", "c": "A",
            "t": _t(f.sello_evento_utc)}}
    return {"snapshots": snaps, "next_page_token": None}


def acciones_json(precio, instante):
    return {"SPY": {"latestQuote": {"bp": precio - 0.01, "ap": precio + 0.01, "bs": 100, "as": 200, "bx": "V",
                                    "ax": "V", "c": ["R"], "t": _t(instante)},
                    "latestTrade": {"p": precio, "s": 100, "t": _t(instante), "x": "V"}}}


def quotes_json(mids, params, atrasos=(0.2, 1.5, 4.0)):
    """Respuesta de ``/v2/stocks/quotes`` (SIP) con el SPY sintético: NBBO antes del corte, en orden descendente.

    ``mids`` da el mid de SPY en cada corte. La cotización más reciente es de un
    solo lado (sin bid); siempre hay ``next_page_token``, que no debe seguirse.
    """
    fin, inicio = pd.Timestamp(params["end"]), pd.Timestamp(params["start"])
    mid = mids[fin]
    cotizaciones = [{"t": _t(fin - pd.Timedelta(seconds=0.1)), "bp": 0, "bs": 0, "bx": " ", "ap": round(mid + 0.01, 2),
                     "as": 40, "ax": "P", "c": ["R"], "z": "B"}]
    for i, atraso in enumerate(atrasos):
        cotizaciones.append({"t": _t(fin - pd.Timedelta(seconds=atraso)), "bp": round(mid - 0.01 * (i + 1), 2),
                             "bs": 80, "bx": "T", "ap": round(mid + 0.01 * (i + 1), 2), "as": 120, "ax": "Z",
                             "c": ["R"], "z": "B"})
    dentro = [q for q in cotizaciones if inicio <= pd.Timestamp(q["t"]) <= fin][:int(params["limit"])]
    return {"quotes": {"SPY": dentro}, "next_page_token": "U1BZfHNpZ3VpZW50ZQ=="}


def dividendo_json(id_evento, ex, monto, especial=False):
    pago = str(pd.Timestamp(ex).date() + dt.timedelta(days=42))
    return {"id": id_evento, "symbol": "SPY", "cusip": "78462F103", "rate": monto, "special": especial,
            "foreign": False, "ex_date": str(ex), "record_date": str(ex), "payable_date": pago, "process_date": pago}


def descargar_historicos(mercado, directorio, horas=("09:45", "10:00")):
    """Descarga el histórico SIP de cada corte como el script, con el reloj pasado el retraso y el margen."""
    _, _, verdad = mercado
    mids = {cal.instante(f, h): mid for (f, h), mid in verdad["objetivo"].items()}
    reloj = Reloj("2025-11-17T15:00:00Z")
    api = API({"/v2/stocks/quotes": lambda p: quotes_json(mids, p)})
    c = cliente(api, reloj)
    for fecha in FECHAS:
        for hora in horas:
            reloj.actual = cal.instante(fecha, hora) + pd.Timedelta(seconds=965)
            paso = al.planificar_historico(directorio, fecha, [hora], reloj(), 900.0, 60.0)[0]
            assert paso["accion"] == "descargar"
            meta = al.meta_historico(fecha, paso, 900.0, ["SPY"], "sip", 120.0, 1000)
            m, _ = al.descargar_historico(c, al.pedir_historico(["SPY"], "sip", paso["corte_utc"], 120.0, 1000),
                                          directorio, meta)
            assert m["estado"] == "completa"
    return api


def descargar_eventos(directorio, cuerpos, desde="2025-11-14T21:00:00Z"):
    """Una consulta de eventos corporativos por cuerpo, un día después de la anterior."""
    for i, cuerpo in enumerate(cuerpos):
        reloj = Reloj(pd.Timestamp(desde) + pd.Timedelta(days=i))
        api = API({"/v1/corporate-actions": lambda p, cuerpo=cuerpo: cuerpo})
        fecha = reloj().tz_convert("America/New_York").date()
        al.descargar_eventos(cliente(api, reloj), al.pedir_eventos(["SPY"], fecha - dt.timedelta(days=400),
                                                                   fecha + dt.timedelta(days=120)),
                             directorio, {"fecha": str(fecha), "etiqueta": f"eventos-{i}", "simbolos": ["SPY"]})


@pytest.fixture(scope="module")
def mercado():
    # Viernes a 0-48 días: incluye un vencimiento cercano para el nivel implícito y los que encierran 30 días.
    return sn.mercado_sintetico(FECHAS, semilla=5, rango_k=(-0.08, 0.04), dias_vencimiento=(0, 48),
                                sesiones_extra=0)


def api_sintetica(mercado, reloj):
    """API falsa cuyas cadenas son las del mercado sintético a la hora que marca el reloj."""
    cot, _, _ = mercado

    def cadena(params, raiz):
        corte = reloj()
        return cadena_json(cot[cot["raiz"] == raiz], params["expiration_date"], corte)

    return API({
        "/v2/options/contracts": lambda p: contratos_json(cot),
        "/v1beta1/options/snapshots/SPXW": lambda p: cadena(p, "SPXW"),
        "/v2/stocks/snapshots": lambda p: acciones_json(580.0, reloj()),
        "/v2/clock": lambda p: {"timestamp": "2025-11-17T09:44:55.250000000-05:00", "is_open": True,
                                "next_open": "2025-11-18T09:30:00-05:00", "next_close": "2025-11-17T16:00:00-05:00"},
    })


def capturar_sesiones(mercado, directorio):
    """Captura cada sesión y hora del mercado sintético como lo haría el script, con reloj falso."""
    cot, _, _ = mercado
    reloj = Reloj("2025-11-17T14:40:00Z")
    c = cliente(api_sintetica(mercado, reloj), reloj)
    for fecha in FECHAS:
        pedidos = [al.pedir_contratos("SPX", fecha, fecha + dt.timedelta(days=60), "SPXW")]
        resultados, errores = al.ejecutar(c, pedidos)
        assert not errores
        previas = al.guardar_respuestas(resultados, {p.nombre: p.tipo for p in pedidos}, directorio)
        vencimientos = sorted({str(v) for v in cot["vencimiento"]})
        for hora in ("09:45", "10:00"):
            corte = cal.instante(fecha, hora)
            reloj.actual = corte  # la respuesta llega al corte: aún se conocía
            elegidos, _ = al.elegir_vencimientos(vencimientos, "PM", corte, 30.0, 2, True)
            solicitudes = [al.pedir_cadena("SPXW", v, "indicative") for v in elegidos]
            solicitudes.append(al.pedir_acciones(["SPY"], "iex"))
            meta = {"fecha": str(fecha), "hora": hora, "corte_utc": al.iso(corte),
                    "etiqueta": f"{fecha}T{hora.replace(':', '')}", "feed_opciones": "indicative"}
            al.capturar(c, solicitudes, directorio, meta, previas)
    return c


# --- Cliente -----------------------------------------------------------------------------------

def test_credenciales_no_se_muestran():
    cred = al.Credenciales.del_entorno({"APCA_API_KEY_ID": CLAVE, "APCA_API_SECRET_KEY": SECRETO,
                                        "ALPACA_PAPER": "true"})
    assert cred.paper and SECRETO not in repr(cred) and CLAVE not in repr(cred)
    assert not al.Credenciales.del_entorno({"APCA_API_KEY_ID": CLAVE, "APCA_API_SECRET_KEY": SECRETO,
                                            "ALPACA_PAPER": "false"}).paper
    with pytest.raises(RuntimeError):
        al.Credenciales.del_entorno({"APCA_API_KEY_ID": CLAVE})


def test_reintentos_ante_429_5xx_y_red_pero_no_ante_403():
    api = API({"/v2/clock": lambda p: {"ok": True}}, fallos={"/v2/clock": [429, 503, "red", "cortada"]})
    reloj = Reloj("2025-11-17T14:00:00Z")
    r = cliente(api, reloj, reintentos=4).get("trading", "/v2/clock")
    assert r.estado == 200 and r.intentos == 5 and len(reloj.siestas) == 4
    assert api.vistas[0][2]["APCA-API-SECRET-KEY"] == SECRETO  # las credenciales van solo en cabeceras
    assert r.json() == {"ok": True} and "date" in r.cabeceras and SECRETO not in str(r.params)
    api = API({"/v2/clock": lambda p: {}}, fallos={"/v2/clock": [403]})
    with pytest.raises(al.ErrorAlpaca) as error:
        cliente(api).get("trading", "/v2/clock")
    assert error.value.estado == 403 and len(api.vistas) == 1
    api = API({"/v2/clock": lambda p: {}}, fallos={"/v2/clock": ["red"] * 3})
    with pytest.raises(al.ErrorAlpaca):
        cliente(api, reintentos=2).get("trading", "/v2/clock")


def test_paginacion_por_token():
    paginas = {None: {"option_contracts": [{"symbol": "A"}], "next_page_token": "p2"},
               "p2": {"option_contracts": [{"symbol": "B"}], "next_page_token": None}}
    api = API({"/v2/options/contracts": lambda p: paginas[p.get("page_token")]})
    respuestas = cliente(api).paginas("trading", "/v2/options/contracts", {"underlying_symbols": "SPX"})
    assert [r.json()["option_contracts"][0]["symbol"] for r in respuestas] == ["A", "B"]
    assert ("page_token", "p2") in respuestas[1].params
    assert api.vistas[0][0] == "/v2/options/contracts"


def test_reloj_del_servidor_y_espera():
    api = API({"/v2/clock": lambda p: {"timestamp": "2025-11-17T09:44:56.000000000-05:00", "is_open": True}})
    reloj = Reloj("2025-11-17T14:44:55Z")
    estado = al.reloj_servidor(cliente(api, reloj).get("trading", "/v2/clock"))
    assert estado["desfase_s"] == pytest.approx(1.0) and estado["mercado_abierto"]
    objetivo = pd.Timestamp("2025-11-17T14:46:10Z")
    al.esperar_hasta(objetivo, reloj, reloj.dormir, paso_max=30.0)
    assert reloj.actual == objetivo and max(reloj.siestas) <= 30.0


def test_eleccion_de_vencimientos():
    corte = cal.instante("2025-11-17", "09:45")
    fechas = ["2025-11-17", "2025-11-21", "2025-12-12", "2025-12-15", "2025-12-19", "2025-12-26",
              "2025-11-27", "2025-11-10"]  # Acción de Gracias no es sesión; el 10 ya liquidó
    elegidos, plazos = al.elegir_vencimientos(fechas, "PM", corte, 30.0, 2, True)
    assert [str(v) for v in elegidos] == ["2025-11-17", "2025-12-12", "2025-12-15", "2025-12-19", "2025-12-26"]
    assert "2025-11-27" not in map(str, plazos) and "2025-11-10" not in map(str, plazos)
    assert plazos[pd.Timestamp("2025-12-15").date()] > 28.0
    solo, _ = al.elegir_vencimientos(fechas, "PM", corte, 30.0, 1, False)
    assert [str(v) for v in solo] == ["2025-12-15", "2025-12-19"]


# --- Crudo, manifiesto y normalización ------------------------------------------------------------

def test_captura_crudo_inmutable_y_sin_secretos(mercado, tmp_path):
    capturar_sesiones(mercado, tmp_path)
    manifiestos = al.leer_manifiestos(tmp_path)
    assert len(manifiestos) == 4
    for m in manifiestos:
        texto = json.dumps(m)
        assert SECRETO not in texto and CLAVE not in texto
        assert m["respuestas_despues_del_corte"] == [] and m["errores"] == {}
        for e in m["solicitudes"].values():
            for p in e["paginas"]:
                ruta = tmp_path / p["archivo"]
                assert almacen.sha256_archivo(ruta) == p["sha256"]
                assert not os.stat(ruta).st_mode & stat.S_IWUSR
    primero = manifiestos[0]
    meta = {k: primero[k] for k in ("fecha", "hora", "corte_utc", "etiqueta")}
    with pytest.raises(FileExistsError):  # una captura no se sobrescribe
        al.escribir_manifiesto(meta, tmp_path)


def test_normalizacion_al_contrato(mercado, tmp_path):
    cot_sint, _, _ = mercado
    capturar_sesiones(mercado, tmp_path)
    cot, sub, resumenes, _ = al.normalizar(tmp_path)
    assert ct.validar(cot) == [] and ct.validar(sub, ct.SUBYACENTE) == []
    assert set(cot["raiz"]) == {"SPXW"} and set(cot["subyacente"]) == {"SPX"}
    assert set(cot["ejercicio"]) == {"europeo"} and set(cot["liquidacion"]) == {"PM"}
    assert set(cot["feed"]) == {"indicative"} and set(cot["proveedor"]) == {"alpaca"}
    assert all(r.get("sin_cotizacion", 0) == 0 and r.get("sin_metadatos", 0) == 0 for r in resumenes)
    # Mismo precio y misma hora de evento que el mercado de origen (nanosegundos truncados a microsegundos).
    fila = cot.iloc[0]
    origen = cot_sint[(cot_sint["id_contrato"] == fila["id_contrato"])
                      & (cot_sint["sello_snapshot_utc"] == fila["sello_snapshot_utc"])].iloc[0]
    assert (fila["bid"], fila["ask"], fila["tam_bid"]) == (origen["bid"], origen["ask"], origen["tam_bid"])
    assert fila["sello_evento_utc"] == origen["sello_evento_utc"]
    assert fila["sello_snapshot_utc"] == fila["recibido_utc"] == fila["disponible_utc"]
    assert str(cot["sello_evento_utc"].dtype) == "datetime64[us, UTC]"
    assert set(sub["subyacente"]) == {"SPY"} and np.allclose(sub["precio"], 580.0)


def test_cotizacion_ausente_metadatos_ausentes_y_raiz_desconocida(tmp_path):
    corte = pd.Timestamp("2025-11-17T14:45:00Z")
    snaps = {"SPXW251219C05800000": {"latestQuote": {"bp": 90.1, "ap": 90.9, "bs": 3, "as": 4, "t": _t(corte)}},
             "SPXW251219P05800000": {"dailyBar": {"c": 70.0}},  # sin cotización
             "SPXW251219P05700000": {"latestQuote": {"bp": 50.0, "ap": 51.0, "bs": 1, "as": 1, "t": _t(corte)}}}
    meta = {"SPXW251219C05800000": {"symbol": "SPXW251219C05800000", "root_symbol": "SPXW",
                                    "underlying_symbol": "SPX", "expiration_date": "2025-12-19", "type": "call",
                                    "style": "european", "strike_price": "5800", "multiplier": "100"}}
    cuentas = al.Counter()
    filas = al.filas_cadena(snaps, meta, al.iso(corte), "indicative", "x", cuentas)
    assert len(filas) == 1 and cuentas == {"con_cotizacion": 1, "sin_cotizacion": 1, "sin_metadatos": 1}
    mal = {"SPXW251219C05800000": dict(meta["SPXW251219C05800000"], strike_price="5900")}
    with pytest.raises(ValueError):
        al.filas_cadena(snaps, mal, al.iso(corte), "indicative", "x", al.Counter())
    otra = {"QQQ251219C00500000": {"latestQuote": {"bp": 1.0, "ap": 1.1, "bs": 1, "as": 1, "t": _t(corte)}}}
    meta_q = {"QQQ251219C00500000": {"symbol": "QQQ251219C00500000", "root_symbol": "QQQ", "underlying_symbol": "QQQ",
                                     "expiration_date": "2025-12-19", "type": "call", "style": "american",
                                     "strike_price": "500", "multiplier": "100"}}
    with pytest.raises(ValueError, match="liquidación desconocida"):
        al.filas_cadena(otra, meta_q, al.iso(corte), "indicative", "x", al.Counter())


def test_replay_da_los_mismos_bytes_y_detecta_crudo_alterado(mercado, tmp_path):
    capturar_sesiones(mercado, tmp_path)
    hashes = []
    for i in range(2):
        cot, sub, _, _ = al.normalizar(tmp_path)
        hashes.append((almacen.escribir_tabla(cot, tmp_path / f"c{i}.parquet"),
                       almacen.escribir_tabla(sub, tmp_path / f"s{i}.parquet")))
    assert hashes[0] == hashes[1]
    pagina = next(p for e in al.leer_manifiestos(tmp_path)[0]["solicitudes"].values() if e["tipo"] == "cadena"
                  for p in e["paginas"])
    ruta = tmp_path / pagina["archivo"]
    original = gzip.decompress(ruta.read_bytes())
    assert almacen.sha256_bytes(original) == pagina["sha256_contenido"]
    os.chmod(ruta, stat.S_IRUSR | stat.S_IWUSR)
    ruta.write_bytes(gzip.compress(original.replace(b'"bp": ', b'"bp": 1', 1)))
    with pytest.raises(RuntimeError, match="hash"):
        al.normalizar(tmp_path)


# --- Subyacente implícito y piloto de punta a punta ------------------------------------------------

def test_spot_implicito_recupera_el_nivel(mercado):
    cot, _, verdad = mercado
    fecha = FECHAS[0]
    corte = cal.instante(fecha, "09:45")
    filas = cot[(cot["sello_snapshot_utc"] == corte)]
    cercano = min(filas["vencimiento"])
    r = im.spot_implicito(filas[filas["vencimiento"] == cercano], fecha, corte, tasa=0.04,
                          rendimiento_dividendo=0.013)
    assert r["estado"] == "identificado" and r["pares"] >= 5
    assert abs(r["spot"] / verdad["spot"][(fecha, "09:45")] - 1) < 5e-5
    assert corte - pd.Timedelta(seconds=20) <= r["sello_evento_utc"] <= corte
    pocas = filas[filas["vencimiento"] == cercano].iloc[:6]
    assert im.spot_implicito(pocas, fecha, corte, 0.04, 0.013)["estado"] == "no identificado"


def test_piloto_de_punta_a_punta_con_respuestas_de_alpaca(mercado, tmp_path):
    _, _, verdad = mercado
    capturar_sesiones(mercado, tmp_path)
    cfg = pl.cargar_config(RAIZ / "configs" / "piloto.toml")
    with open(RAIZ / "configs" / "captura_alpaca.toml", "rb") as f:
        implicito = tomllib.load(f)["implicito"]
    t = al.tablas_para_piloto(tmp_path, cfg_implicito=implicito, reglas=cfg.reglas)
    cot, sub = t.cotizaciones, t.subyacente
    assert t.fallos_implicito == [] and ct.validar(sub, ct.SUBYACENTE) == []
    spx = sub[sub["subyacente"] == "SPX"]
    assert len(spx) == 4 and set(spx["feed"]) == {"implicito_paridad_SPXW_indicative"}
    for fila in spx.itertuples():
        hora = fila.captura[-4:-2] + ":" + fila.captura[-2:]
        fecha = pd.Timestamp(fila.captura[:10]).date()
        assert abs(fila.precio / verdad["spot"][(fecha, hora)] - 1) < 5e-5
    resultado = pl.ejecutar(cot, sub, FECHAS, cfg)
    p = resultado.principal
    assert (p["estado_sesion"] == "procesada").all() and (p["rr25_estado"] == "identificada").all()
    assert p["cambio_rr25"].notna().iloc[1:].all()
    assert (p["spot"] / [verdad["spot"][(f, "09:45")] for f in p["fecha"]] - 1).abs().max() < 5e-5
    assert (p["tipo_precio_referencia"] == "implicito").all()
    assert set(p["fuente_referencia"]) == {"alpaca/implicito_paridad_SPXW_indicative"}
    assert set(p["fuente_opciones"]) == {"alpaca/indicative"}
    assert resultado.dictamen["alcance"]["evaluacion_con_precios_de_mercado"].startswith("no permitida")


# --- Regresiones de la revisión del commit e2b92f0 ------------------------------------

def test_pagina_recibida_se_guarda_aunque_falle_la_siguiente(tmp_path):
    # H5: página 1 con 200 y token; página 2 con 503 sin reintentos.
    corte = pd.Timestamp("2025-11-17T14:45:00Z")
    paginas = {None: {"snapshots": {}, "next_page_token": "p2"}}

    class APIFalla(API):
        def __call__(self, url, cabeceras, tiempo_max):
            if "page_token=p2" in url:
                return 503, {}, b'{"message":"no disponible"}'
            return super().__call__(url, cabeceras, tiempo_max)

    api = APIFalla({"/v1beta1/options/snapshots/SPXW": lambda p: paginas[p.get("page_token")]})
    c = cliente(api, Reloj(corte - pd.Timedelta(seconds=5)), reintentos=0)
    meta = {"fecha": "2025-11-17", "hora": "09:45", "corte_utc": al.iso(corte), "etiqueta": "x", "modo": "programada"}
    m, _ = al.capturar(c, [al.pedir_cadena("SPXW", "2025-12-19", "indicative")], tmp_path, meta)
    e = m["solicitudes"]["cadena_SPXW_2025-12-19"]
    assert e["estado"] == "parcial" and len(e["paginas"]) == 1 and "503" in e["error"]
    assert (tmp_path / e["paginas"][0]["archivo"]).exists()
    assert m["estado"] == "parcial" and "cadena_SPXW_2025-12-19" in m["errores"]


def test_estados_de_cada_hora_y_codigo_de_salida(mercado, tmp_path):
    # H8: un manifiesto con error no cuenta como captura hecha.
    fecha = FECHAS[0]
    for hora in ("09:45", "10:00"):
        corte = cal.instante(fecha, hora)
        api = API({}, fallos={"/v1beta1/options/snapshots/SPXW": [503] * 5})
        c = cliente(api, Reloj(corte - pd.Timedelta(seconds=5)), reintentos=0)
        m, _ = al.capturar(c, [al.pedir_cadena("SPXW", "2025-12-19", "indicative")], tmp_path,
                           {"fecha": str(fecha), "hora": hora, "corte_utc": al.iso(corte),
                            "etiqueta": f"{fecha}T{hora.replace(':', '')}", "modo": "programada"})
        assert m["estado"] == "fallida" and m["solicitudes"]["cadena_SPXW_2025-12-19"]["paginas"] == []
    despues = cal.instante(fecha, "10:30")
    plan = al.planificar(tmp_path, fecha, ["09:45", "10:00"], despues, 5.0)
    assert [(h["hora"], h["estado"], h["accion"]) for h in plan] == [("09:45", "fallida", "omitir"),
                                                                      ("10:00", "fallida", "omitir")]
    assert al.codigo_salida(plan) == 1
    # Sin manifiesto y con el corte pasado: perdida. Antes del corte: pendiente.
    otra = tmp_path / "otra"
    plan = al.planificar(otra, fecha, ["09:45", "10:00"], cal.instante(fecha, "09:50"), 5.0)
    assert [(h["estado"], h["accion"]) for h in plan] == [("perdida", "omitir"), ("pendiente", "capturar")]
    # Una hora completa se omite y cuenta como hecha.
    capturar_sesiones(mercado, otra)
    plan = al.planificar(otra, fecha, ["09:45", "10:00"], despues, 5.0)
    assert [h["estado"] for h in plan] == ["completa", "completa"] and al.codigo_salida(plan) == 0


def _captura_unica(cot, directorio, fecha, corte, recibido, modo):
    """Una captura de las cadenas de ``cot`` cuyo snapshot es ``corte``, recibida en ``recibido``."""
    reloj = Reloj(recibido)
    api = API({"/v2/options/contracts": lambda p: contratos_json(cot),
               "/v1beta1/options/snapshots/SPXW": lambda p: cadena_json(cot, p["expiration_date"], corte),
               "/v2/stocks/snapshots": lambda p: acciones_json(580.0, corte)})
    c = cliente(api, reloj)
    pedidos = [al.pedir_contratos("SPX", fecha, fecha + dt.timedelta(days=60), "SPXW")]
    resultados, _ = al.ejecutar(c, pedidos)
    previas = al.guardar_respuestas(resultados, {p.nombre: p.tipo for p in pedidos}, directorio)
    elegidos, _ = al.elegir_vencimientos(sorted({str(v) for v in cot["vencimiento"]}), "PM", corte, 30.0, 2, True)
    solicitudes = [al.pedir_cadena("SPXW", v, "indicative") for v in elegidos] + [al.pedir_acciones(["SPY"], "iex")]
    meta = {"fecha": str(fecha), "hora": "09:45" if modo == "programada" else "inmediata", "corte_utc": al.iso(corte),
            "etiqueta": f"{fecha}T{modo}", "modo": modo, "feed_opciones": "indicative"}
    return al.capturar(c, solicitudes, directorio, meta, previas)[0]


def test_diagnostico_no_relaja_sellos_de_una_captura_programada_tardia(mercado, tmp_path):
    # H1: captura programada de las 09:45 recibida a las 09:45:01, con eventos anteriores al corte.
    cot, _, _ = mercado
    fecha = FECHAS[0]
    corte = cal.instante(fecha, "09:45")
    cfg = pl.cargar_config(RAIZ / "configs" / "piloto.toml")
    with open(RAIZ / "configs" / "captura_alpaca.toml", "rb") as f:
        imp = tomllib.load(f)["implicito"]
    m = _captura_unica(cot, tmp_path / "tarde", fecha, corte, corte + pd.Timedelta(seconds=1), "programada")
    assert m["estado"] == "fallida"  # todo llegó después del corte
    for pedido in (False, True):  # ni pidiéndolo se relaja una captura programada
        c0 = dg.diagnosticar(tmp_path / "tarde", fecha, imp, cfg, cierre_descriptivo=pedido)[0]["capturas"][0]
        assert not c0["descriptivo_cierre"]
        assert "programada" in c0["motivo_modo"] if pedido else "no pedido" in c0["motivo_modo"]
        assert c0["elegibilidad"]["filas"] > 0 and c0["elegibilidad"]["filas_validas_al_corte"] == 0
        assert sum(r["filas_validas"] for r in c0["raices"].values()) == 0
    # Control: la misma captura recibida un segundo antes del corte sí aporta filas.
    _captura_unica(cot, tmp_path / "a_tiempo", fecha, corte, corte - pd.Timedelta(seconds=1), "programada")
    c0 = dg.diagnosticar(tmp_path / "a_tiempo", fecha, imp, cfg)[0]["capturas"][0]
    assert c0["estado"] == "completa" and c0["elegibilidad"]["filas_validas_al_corte"] > 0
    assert c0["elegibilidad"]["nivel_implicito"] == "identificado"


def test_modo_descriptivo_del_cierre_solo_si_se_pide_y_corresponde(mercado, tmp_path):
    cot, _, _ = mercado
    fecha = FECHAS[0]
    fin = cal.cierre(fecha)
    desplazamiento = fin - cal.instante(fecha, "09:45")
    al_cierre = cot.assign(sello_evento_utc=cot["sello_evento_utc"] + desplazamiento,
                           sello_snapshot_utc=cot["sello_snapshot_utc"] + desplazamiento)
    _captura_unica(al_cierre, tmp_path, fecha, fin, fin + pd.Timedelta(hours=3), "inmediata")
    cfg = pl.cargar_config(RAIZ / "configs" / "piloto.toml")
    with open(RAIZ / "configs" / "captura_alpaca.toml", "rb") as f:
        imp = tomllib.load(f)["implicito"]
    estricto = dg.diagnosticar(tmp_path, fecha, imp, cfg)[0]["capturas"][0]
    assert not estricto["descriptivo_cierre"] and estricto["elegibilidad"]["filas_validas_al_corte"] == 0
    descriptivo = dg.diagnosticar(tmp_path, fecha, imp, cfg, cierre_descriptivo=True)[0]["capturas"][0]
    assert descriptivo["descriptivo_cierre"] and descriptivo["elegibilidad"]["filas_validas_al_corte"] == 0
    assert sum(r["filas_validas"] for r in descriptivo["raices"].values()) > 0


# --- Revalidación de d815bdd: histórico SIP del objetivo y dividendos ---------------------------

def test_historico_sip_una_pagina_despues_del_retraso(mercado, tmp_path):
    api = descargar_historicos(mercado, tmp_path)
    pedidos = [params for ruta, params, _ in api.vistas if ruta == "/v2/stocks/quotes"]
    assert len(pedidos) == 4 and all("page_token" not in p for p in pedidos)  # una página, aunque haya más
    corte = cal.instante(FECHAS[0], "09:45")
    p0 = pedidos[0]
    assert (p0["symbols"], p0["feed"], p0["sort"], p0["limit"]) == ("SPY", "sip", "desc", "1000")
    assert pd.Timestamp(p0["end"]) == corte and pd.Timestamp(p0["start"]) == corte - pd.Timedelta(seconds=120)
    for m in al.leer_manifiestos(tmp_path, carpeta="historico"):
        assert SECRETO not in json.dumps(m) and m["estado"] == "completa"
    sub, resumenes, usados = al.normalizar_historico(tmp_path)
    assert ct.validar(sub, ct.SUBYACENTE) == [] and len(usados) == 4
    assert set(sub["feed"]) == {"sip"} and set(sub["tipo_precio"]) == {"observado"}
    assert all(r["cotizaciones"] == 3 and r["de_un_lado"] == 1 for r in resumenes)
    filas = sub[sub["sello_snapshot_utc"] == corte]
    assert (filas["disponible_utc"] == corte + pd.Timedelta(minutes=15)).all()
    assert (filas["recibido_utc"] == corte + pd.Timedelta(seconds=965)).all()
    assert filas["sello_evento_utc"].is_monotonic_increasing and (filas["sello_evento_utc"] <= corte).all()
    # Reprocesar da los mismos bytes.
    otra, _, _ = al.normalizar_historico(tmp_path)
    assert (almacen.escribir_tabla(sub, tmp_path / "a.parquet") == almacen.escribir_tabla(otra, tmp_path / "b.parquet"))


def test_historico_no_se_consulta_antes_y_un_fallo_se_reintenta(mercado, tmp_path):
    _, _, verdad = mercado
    fecha = FECHAS[0]
    corte = cal.instante(fecha, "09:45")
    reloj = Reloj(corte + pd.Timedelta(minutes=10))
    plan = al.planificar_historico(tmp_path, fecha, ["09:45", "10:00"], reloj(), 900.0, 60.0)
    assert [p["accion"] for p in plan] == ["esperar", "esperar"]
    mids = {cal.instante(f, h): mid for (f, h), mid in verdad["objetivo"].items()}
    api = API({"/v2/stocks/quotes": lambda p: quotes_json(mids, p)}, fallos={"/v2/stocks/quotes": [403]})
    c = cliente(api, reloj)
    solicitud = al.pedir_historico(["SPY"], "sip", corte, 120.0, 1000)
    with pytest.raises(ValueError, match="solo se puede consultar"):
        al.descargar_historico(c, solicitud, tmp_path, al.meta_historico(fecha, plan[0], 900.0, ["SPY"], "sip",
                                                                        120.0, 1000))
    reloj.actual = corte + pd.Timedelta(seconds=961)
    plan = al.planificar_historico(tmp_path, fecha, ["09:45", "10:00"], reloj(), 900.0, 60.0)
    assert [p["accion"] for p in plan] == ["descargar", "esperar"]
    m, _ = al.descargar_historico(c, solicitud, tmp_path, al.meta_historico(fecha, plan[0], 900.0, ["SPY"], "sip",
                                                                           120.0, 1000))
    assert m["estado"] == "fallida" and "403" in m["errores"][solicitud.nombre]  # un 403 no se reintenta en el acto
    paso = al.planificar_historico(tmp_path, fecha, ["09:45"], reloj(), 900.0, 60.0)[0]
    assert (paso["accion"], paso["etiqueta"], paso["intentos_previos"]) == ("descargar", f"{fecha}T0945-2",
                                                                            ["fallida"])
    m, _ = al.descargar_historico(c, solicitud, tmp_path, al.meta_historico(fecha, paso, 900.0, ["SPY"], "sip",
                                                                           120.0, 1000))
    assert m["estado"] == "completa"
    assert al.planificar_historico(tmp_path, fecha, ["09:45"], reloj(), 900.0, 60.0)[0]["accion"] == "omitir"
    _, _, usados = al.normalizar_historico(tmp_path)
    assert [u["etiqueta"] for u in usados] == [f"{fecha}T0945-2"]  # la fallida se conserva y no se usa


def test_versiones_y_cobertura_de_los_eventos_corporativos(tmp_path):
    # Revisión de 8c97b2b, P2: versiones con fecha de conocimiento, retirada y consultas vacías o fallidas.
    d1, d2 = dividendo_json("d1", "2025-11-18", 1.8), dividendo_json("d2", "2025-12-19", 0.5, especial=True)
    split = {"id": "s1", "symbol": "SPY", "ex_date": "2025-06-02", "process_date": "2025-06-02", "old_rate": 1,
             "new_rate": 2}
    cuerpos = [{"corporate_actions": {}},                                      # 14: vacía, aún no publicado
               {"corporate_actions": {"cash_dividends": [d1]}},                # 15: aparece
               {"corporate_actions": {"cash_dividends": [dict(d1, rate=1.85)]}},  # 16: corregido
               {"corporate_actions": {"cash_dividends": [dict(d1, rate=1.85), d2], "forward_splits": [split]}},  # 17
               {"corporate_actions": {"cash_dividends": [d2]}}]                # 18: d1 ya no aparece
    descargar_eventos(tmp_path, [dict(c, next_page_token=None) for c in cuerpos])
    # 19: una consulta que falla; 20: una completa y vacía cuyo intervalo no llega a la fecha de proceso de d2.
    reloj = Reloj("2025-11-19T21:00:00Z")
    falla = API({"/v1/corporate-actions": lambda p: {}}, fallos={"/v1/corporate-actions": [403]})
    al.descargar_eventos(cliente(falla, reloj), al.pedir_eventos(["SPY"], "2024-10-15", "2026-03-18"), tmp_path,
                         {"fecha": "2025-11-19", "etiqueta": "eventos-falla", "simbolos": ["SPY"]})
    reloj.actual = pd.Timestamp("2025-11-20T21:00:00Z")
    corta = API({"/v1/corporate-actions": lambda p: {"corporate_actions": {}, "next_page_token": None}})
    al.descargar_eventos(cliente(corta, reloj), al.pedir_eventos(["SPY"], "2024-10-15", "2026-01-15"), tmp_path,
                         {"fecha": "2025-11-20", "etiqueta": "eventos-corta", "simbolos": ["SPY"]})
    tabla, cobertura, otros, usados = al.normalizar_eventos(tmp_path)
    assert ct.validar(tabla, ct.DIVIDENDOS) == [] and ct.validar(cobertura, ct.COBERTURA_DIVIDENDOS) == []
    assert len(usados) == 7
    d = tabla.set_index(["id_evento", "version"])
    dia = {n: pd.Timestamp(f"2025-11-{n}T21:00:00Z") for n in range(14, 21)}
    assert list(tabla[["id_evento", "version"]].itertuples(index=False, name=None)) == [
        ("d1", 1), ("d1", 2), ("d2", 1)]
    assert (d.loc[("d1", 1), "monto"], d.loc[("d1", 1), "recibido_utc"], d.loc[("d1", 1), "retirado_utc"],
            d.loc[("d1", 1), "motivo_retiro"]) == (1.8, dia[15], dia[16], "corregido")
    # Revalidación de a5e2748, P1: la ausencia del 18 no retira la versión; abre una discrepancia sin resolver,
    # y la consulta del 20, que tampoco la trae, no la resuelve.
    assert (d.loc[("d1", 2), "monto"], d.loc[("d1", 2), "recibido_utc"], d.loc[("d1", 2), "motivo_retiro"],
            d.loc[("d1", 2), "discrepancia"], d.loc[("d1", 2), "discrepancia_desde_utc"]) == (
        1.85, dia[16], "", "ausente", dia[18])
    assert pd.isna(d.loc[("d1", 2), "retirado_utc"])
    # La consulta del 20 no llega al 30 de enero (proceso de d2): su ausencia allí no dice nada.
    assert pd.isna(d.loc[("d2", 1), "retirado_utc"]) and d.loc[("d2", 1), "clase"] == "especial"
    assert pd.isna(d.loc[("d2", 1), "discrepancia_desde_utc"]) and set(tabla["origen"]) == {"consulta"}
    assert d["disponible_utc"].isna().all()  # Alpaca no da la hora del anuncio
    assert list(cobertura["estado"]) == ["completa"] * 5 + ["fallida", "completa"]
    assert list(cobertura["eventos"]) == [0.0, 1.0, 1.0, 2.0, 1.0, 0.0, 0.0]
    assert cobertura.iloc[5]["desde"] == dt.date(2024, 10, 15) and cobertura.iloc[5]["recibido_utc"] == dia[19]
    assert otros == [{"tipo": "forward_splits", "simbolo": "SPY", "fecha": "2025-06-02", "id": "s1"}]
    with pytest.raises(ValueError, match="forward_splits de SPY el 2025-06-02"):
        al.tablas_para_piloto(tmp_path, "2025-06-01", "2025-06-30")
    t = al.tablas_para_piloto(tmp_path, "2025-11-17", "2025-11-18")  # fuera del rango: se informa
    assert t.eventos_no_tratados == otros and len(t.dividendos) == 3 and len(t.cobertura_dividendos) == 7


def consulta_eventos(directorio, cuerpo, recibido, tipos=None, etiqueta=None):
    """Una consulta de eventos recibida en ``recibido``; con ``tipos``, filtrada como en la API."""
    reloj = Reloj(recibido)
    fecha = reloj().tz_convert("America/New_York").date()
    solicitud = al.pedir_eventos(["SPY"], fecha - dt.timedelta(days=400), fecha + dt.timedelta(days=120))
    if tipos:
        solicitud = dataclasses.replace(solicitud, params=tuple(sorted(solicitud.params + (("types", tipos),))))
    api = API({"/v1/corporate-actions": lambda p: dict(cuerpo, next_page_token=None)})
    etiqueta = etiqueta or f"eventos-{reloj():%Y%m%dT%H%M%S}"
    m, _ = al.descargar_eventos(cliente(api, reloj), solicitud, directorio,
                                {"fecha": str(fecha), "etiqueta": etiqueta, "simbolos": ["SPY"]})
    assert m["estado"] == "completa"


def test_una_ausencia_sin_resolver_deja_pendiente_la_etiqueta_despues_de_60_dias(tmp_path):
    # Revalidación de a5e2748, P1 de punta a punta: del crudo a la vista de la política aceptada.
    d1 = {"corporate_actions": {"cash_dividends": [dividendo_json("d1", "2025-11-18", 1.8)]}}
    vacia = {"corporate_actions": {}}
    consulta_eventos(tmp_path, d1, "2025-11-18T21:00:00Z")  # después del fin: habilita
    ausencias = [pd.Timestamp(t) for t in ("2025-11-25T21:00:00Z", "2026-01-27T21:00:00Z", "2026-02-27T21:00:00Z")]
    for t in ausencias:  # la primera abre la discrepancia; repetirla, también pasados 60 días, no la resuelve
        consulta_eventos(tmp_path, vacia, t)
    # P2: una consulta que solo pidió splits no dice nada de los dividendos, ni ausencia ni presencia.
    consulta_eventos(tmp_path, vacia, "2026-03-02T21:00:00Z", tipos="forward_split")
    tabla, cobertura, otros, _ = al.normalizar_eventos(tmp_path)
    assert len(tabla) == 1 and pd.isna(tabla.loc[0, "retirado_utc"]) and otros == []
    assert (tabla.loc[0, "discrepancia"], tabla.loc[0, "discrepancia_desde_utc"]) == ("ausente", ausencias[0])
    assert list(cobertura["tipos"]) == ["todos"] * 4 + ["forward_split"]
    precios = pd.Series([100.0, 100.0], index=FECHAS)

    def etiqueta(hasta=None):
        e = et.etiquetas_retorno(precios, horizontes=(1,), dividendos=tabla, cobertura=cobertura,
                                 margen_proceso_dias=60, conocido_hasta=hasta)
        return e[e["sesion"] == FECHAS[0]]

    e = etiqueta()
    assert list(e["estado_dividendos"]) == ["provisional", "pendiente"] and list(e["dividendos"]) == [1.8, 1.8]
    for t in ausencias[1:] + [pd.Timestamp("2026-06-01T00:00:00Z")]:
        assert et.etiquetas_maduras(e, t, politica="aceptada").empty
        assert et.etiquetas_maduras(e, t).iloc[0]["estado_dividendos"] == "pendiente"
    antes = etiqueta(ausencias[0] - pd.Timedelta(seconds=1))  # la versión previa se reconstruye intacta
    assert list(antes["estado_dividendos"]) == ["provisional"] and list(antes["dividendos"]) == [1.8]
    # Con solo la consulta de splits después del fin, el rendimiento total no se confirma.
    solo_splits = et.etiquetas_retorno(precios, horizontes=(1,), dividendos=tabla.iloc[:0],
                                       cobertura=cobertura.iloc[[4]], margen_proceso_dias=60)
    assert solo_splits.iloc[0]["estado"] == "sin dividendos confirmados"
    assert "sin dividendos en los tipos pedidos" in solo_splits.iloc[0]["motivo"]


def test_resoluciones_registradas_resuelven_y_fijan_el_estado_del_dividendo(tmp_path):
    # Revalidación de a5e2748, P1: la resolución exige evidencia registrada con su fecha de conocimiento.
    def cuerpo(*montos):
        return {"corporate_actions": {"cash_dividends": [dividendo_json("d1", "2025-11-18", m) for m in montos]}}

    dia = {n: pd.Timestamp(f"2025-11-{n}T21:00:00Z") for n in range(14, 25)}
    for n, c in ((14, cuerpo(1.8)), (15, cuerpo()), (16, cuerpo()), (17, cuerpo(1.8)), (18, cuerpo()),
                 (19, cuerpo()), (20, cuerpo()), (21, cuerpo(1.8)), (22, cuerpo(1.9)), (23, cuerpo()),
                 (24, cuerpo(1.9))):
        consulta_eventos(tmp_path, c, dia[n])
    hora = {n: pd.Timestamp(f"2025-11-{n}T12:00:00Z") for n in (19, 21, 25, 26)}
    ruta = tmp_path / "resoluciones_dividendos.csv"
    ruta.write_text("id_evento,simbolo,resolucion,conocido_utc,fuente,nota\n"
                    "d1,SPY,vigente,2025-11-19T12:00:00Z,aviso del emisor,\n"
                    "d1,SPY,cancelado,2025-11-21T12:00:00Z,aviso del emisor,prueba\n"
                    "d1,SPY,vigente,2025-11-25T12:00:00Z,aviso del emisor,\n"
                    "d9,SPY,vigente,2025-11-25T12:00:00Z,aviso del emisor,sin evento\n"
                    "d1,SPY,vigente,2025-11-26T12:00:00Z,aviso del emisor,ya confirmado\n", encoding="utf-8")
    resoluciones = al.cargar_resoluciones(ruta)
    assert ct.validar(resoluciones, ct.RESOLUCIONES_DIVIDENDOS) == []
    tabla, _, otros, _ = al.normalizar_eventos(tmp_path, resoluciones)
    assert ct.validar(tabla, ct.DIVIDENDOS) == []
    columnas = ["monto", "recibido_utc", "retirado_utc", "motivo_retiro", "discrepancia", "discrepancia_desde_utc",
                "origen"]
    filas = [tuple(None if pd.isna(x) else x for x in fila) for fila in tabla[columnas].itertuples(index=False)]
    assert filas == [
        (1.8, dia[14], dia[17], "reaparecido", "ausente", dia[15], "consulta"),  # el 16 repite la ausencia
        (1.8, dia[17], hora[19], "confirmado", "ausente", dia[18], "consulta"),
        # Confirmado: las omisiones del 19 y el 20 ya no abren discrepancias.
        (1.8, hora[19], hora[21], "cancelado", "", None, "resolucion"),
        # Cancelado: el 21 lo trae igual (nada nuevo); el 22, con otro monto: discrepancia hasta otra resolución,
        # que ni la ausencia del 23 ni la reaparición del 24 resuelven.
        (1.9, dia[22], hora[25], "confirmado", "reaparece_cancelado", dia[22], "consulta"),
        (1.9, hora[25], None, "", "", None, "resolucion")]
    anotados = {(e["tipo"], e["id"]): e for e in otros}
    assert set(anotados) == {("omitido_tras_confirmar", "d1"), ("listado_tras_cancelar", "d1"),
                             ("resolucion_sin_efecto", "d9"), ("resolucion_sin_efecto", "d1")}
    assert anotados[("omitido_tras_confirmar", "d1")]["veces"] == 2
    assert anotados[("listado_tras_cancelar", "d1")]["veces"] == 1
    # Las anotaciones no detienen el piloto aunque caigan en su rango.
    t = al.tablas_para_piloto(tmp_path, "2025-11-17", "2025-11-30", resoluciones=resoluciones)
    assert len(t.dividendos) == 5 and len(t.eventos_no_tratados) == 4
    assert al.resumen_dividendos(tabla, otros) == {
        "versiones": 5, "dividendos": 1,
        "retiros_por_motivo": {"cancelado": 1, "confirmado": 2, "reaparecido": 1},
        "confirmadas_por_resolucion": 2, "discrepancias": {"ausente": 2, "reaparece_cancelado": 1},
        "discrepancias_abiertas": {}, "contradicciones_sin_valores_nuevos": {
            "omitido_tras_confirmar": 2, "listado_tras_cancelar": 1}, "resoluciones_sin_efecto": 2}
    # Sin las resoluciones decide solo el proveedor: cada reaparición resuelve una ausencia y el 22 corrige.
    sin, _, _, _ = al.normalizar_eventos(tmp_path)
    r = al.resumen_dividendos(sin)
    assert (r["retiros_por_motivo"], r["discrepancias"], r["discrepancias_abiertas"]) == (
        {"corregido": 1, "reaparecido": 3}, {"ausente": 3}, {})
    # Una resolución de otro símbolo, sin zona o repetida no se acepta.
    for linea, error in (("d1,QQQ,vigente,2025-11-19T12:00:00Z,x,", "el evento es de SPY"),
                         ("d1,SPY,vigente,2025-11-19 12:00,x,", "zona explícita"),
                         ("d1,SPY,quizas,2025-11-19T12:00:00Z,x,", "resolucion: solo se admite")):
        ruta.write_text("id_evento,simbolo,resolucion,conocido_utc,fuente,nota\n" + linea + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=error):
            al.normalizar_eventos(tmp_path, al.cargar_resoluciones(ruta))
    ruta.write_text("id_evento,simbolo,resolucion,conocido_utc,fuente,nota\n"
                    + "d1,SPY,vigente,2025-11-19T12:00:00Z,x,\n" * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="repetidas"):
        al.cargar_resoluciones(ruta)


def dividendo_incompleto(id_evento="d1", monto=1.8, proceso="2025-12-30", **cambios):
    """Un dividendo de SPY sin fecha ex (ni de registro), con fecha de proceso y de pago."""
    x = {k: v for k, v in dividendo_json(id_evento, "2025-11-18", monto).items() if k not in ("ex_date", "record_date")}
    return dict(x, process_date=proceso, payable_date=proceso, **cambios)


def test_un_dividendo_incompleto_deja_pendientes_las_etiquetas_que_podria_afectar(tmp_path):
    # Revalidación de 5c15028, P2: un dividendo recibido sin fecha ex no puede terminar como cero aceptado.
    vacia = {"corporate_actions": {}}
    completo = {"corporate_actions": {"cash_dividends": [dividendo_json("d1", "2025-11-18", 1.8)]}}
    incompleto = {"corporate_actions": {"cash_dividends": [dividendo_incompleto()]}}
    t = {n: pd.Timestamp(x) for n, x in (("habilita", "2025-11-18T21:00:00Z"), ("acepta", "2026-01-19T21:00:00Z"),
                                         ("incompleto", "2026-01-20T21:00:00Z"), ("completo", "2026-02-20T21:00:00Z"))}
    precios = pd.Series([100.0, 100.0], index=FECHAS)

    def etiqueta(directorio, resoluciones=None, hasta=None):
        tabla, cobertura, otros, _ = al.normalizar_eventos(directorio, resoluciones)
        e = et.etiquetas_retorno(precios, horizontes=(1,), dividendos=tabla, cobertura=cobertura,
                                 margen_proceso_dias=60, conocido_hasta=hasta)
        return tabla, otros, e[e["sesion"] == FECHAS[0]]

    for nombre, cuerpo in (("habilita", vacia), ("acepta", vacia), ("incompleto", incompleto), ("completo", completo)):
        consulta_eventos(tmp_path, cuerpo, t[nombre])
    tabla, otros, e = etiqueta(tmp_path)
    assert ct.validar(tabla, ct.DIVIDENDOS) == [] and otros == []
    # Una versión con la discrepancia «incompleto» y el intervalo de su fecha de proceso; el registro completo la
    # corrige.
    v1, v2 = tabla.iloc[0], tabla.iloc[1]
    assert (pd.isna(v1["fecha_ex"]), v1["monto"], v1["proceso_desde"], v1["proceso_hasta"], v1["discrepancia"],
            v1["discrepancia_desde_utc"], v1["retirado_utc"], v1["motivo_retiro"]) == (
        True, 1.8, dt.date(2025, 12, 30), dt.date(2025, 12, 30), "incompleto", t["incompleto"], t["completo"],
        "corregido")
    assert (v2["fecha_ex"], v2["monto"], v2["discrepancia"]) == (dt.date(2025, 11, 18), 1.8, "")
    assert list(e["estado_dividendos"]) == ["provisional", "aceptada", "pendiente", "aceptada"]
    assert list(e["dividendos"]) == [0.0, 0.0, 0.0, 1.8] and list(e["version"]) == [1, 1, 1, 2]
    assert "sin fecha ex (1.8) recibido incompleto" in e.iloc[2]["motivo"]
    assert "entre 2025-10-31 y 2025-12-30" in e.iloc[2]["motivo"]
    # 1. No pasa la política aceptada mientras siga incompleto.
    entre = pd.Timestamp("2026-02-01T00:00:00Z")
    assert et.etiquetas_maduras(e, entre, politica="aceptada").empty
    assert et.etiquetas_maduras(e, entre).iloc[0]["estado_dividendos"] == "pendiente"
    # 2. Lo conocido antes de recibirlo no cambia: aceptada con cero, igual en la reconstrucción truncada.
    antes = t["incompleto"] - pd.Timedelta(seconds=1)
    assert et.etiquetas_maduras(e, antes, politica="aceptada")["dividendos"].tolist() == [0.0]
    _, _, truncada = etiqueta(tmp_path, hasta=antes)
    assert list(truncada["estado_dividendos"]) == ["provisional", "aceptada"]
    # 3. El registro completo actualiza la etiqueta desde que llega.
    assert et.etiquetas_maduras(e, t["completo"], politica="aceptada")["dividendos"].tolist() == [1.8]

    # 3'. O una resolución con la fecha ex: desde su fecha de conocimiento, y la acepta la consulta siguiente.
    otro = tmp_path / "con_resolucion"
    for nombre, cuerpo in (("habilita", vacia), ("acepta", vacia), ("incompleto", incompleto),
                           ("completo", incompleto)):  # el proveedor lo sigue trayendo incompleto: nada nuevo
        consulta_eventos(otro, cuerpo, t[nombre])
    ruta = otro / "resoluciones_dividendos.csv"
    encabezado = "id_evento,simbolo,resolucion,conocido_utc,fuente,nota,fecha_ex,monto\n"
    ruta.write_text(encabezado + "d1,SPY,vigente,2026-02-01T15:00:00Z,aviso del emisor,,2025-11-18,\n",
                    encoding="utf-8")
    tabla, otros, e = etiqueta(otro, al.cargar_resoluciones(ruta))
    assert otros == [] and list(tabla["origen"]) == ["consulta", "resolucion"]
    assert (tabla.iloc[1]["fecha_ex"], tabla.iloc[1]["monto"]) == (dt.date(2025, 11, 18), 1.8)
    assert list(e["estado_dividendos"]) == ["provisional", "aceptada", "pendiente", "provisional", "aceptada"]
    assert e.iloc[3]["vigente_desde_utc"] == pd.Timestamp("2026-02-01T15:00:00Z") and e.iloc[3]["dividendos"] == 1.8
    for evidencia, error in ((",", "debe darlos"), ("2025-11-18,1.9", "contradice")):
        ruta.write_text(encabezado + "d1,SPY,vigente,2026-02-01T15:00:00Z,aviso,," + evidencia + "\n",
                        encoding="utf-8")
        with pytest.raises(ValueError, match=error):
            al.normalizar_eventos(otro, al.cargar_resoluciones(ruta))

    # 5. Una fecha ex conocida fuera del periodo, o un proceso que no la deja caer en él, no afecta a la etiqueta.
    for cuerpo in ({"cash_dividends": [dividendo_json("d1", "2025-12-19", 1.8)]},
                   {"cash_dividends": [dict(dividendo_json("d1", "2025-12-19", 1.8), rate=None)]},
                   {"cash_dividends": [dividendo_incompleto(proceso="2026-06-30")]}):
        aparte = tmp_path / f"aparte-{len(list(tmp_path.glob('aparte-*')))}"
        for nombre, c in (("habilita", vacia), ("acepta", vacia), ("incompleto", {"corporate_actions": cuerpo})):
            consulta_eventos(aparte, c, t[nombre])
        tabla, _, e = etiqueta(aparte)
        assert tabla.iloc[0]["discrepancia"] == ("incompleto" if _incompleto_json(cuerpo) else "")
        assert list(e["estado_dividendos"]) == ["provisional", "aceptada"] and (e["dividendos"] == 0.0).all()
    # 4. Una respuesta de verdad vacía se sigue aceptando con cero.
    solo_vacias = tmp_path / "vacias"
    for nombre in ("habilita", "acepta", "incompleto"):
        consulta_eventos(solo_vacias, vacia, t[nombre])
    tabla, _, e = etiqueta(solo_vacias)
    assert tabla.empty and e.iloc[-1]["estado_dividendos"] == "aceptada" and e.iloc[-1]["dividendos"] == 0.0


def _incompleto_json(cuerpo):
    x = cuerpo["cash_dividends"][0]
    return not x.get("ex_date") or x.get("rate") is None


def test_un_dividendo_sin_simbolo_atribuible_detiene_la_normalizacion(tmp_path):
    # Sin identificador, se deriva uno estable; sin símbolo, vale el de la consulta si pidió uno solo.
    sin_id = {k: v for k, v in dividendo_json("d1", "2025-11-18", 1.8).items() if k != "id"}
    sin_simbolo = {k: v for k, v in dividendo_json("d2", "2025-12-19", 0.5).items() if k != "symbol"}
    consulta_eventos(tmp_path, {"corporate_actions": {"cash_dividends": [sin_id, sin_simbolo]}},
                     "2025-11-18T21:00:00Z")
    tabla, cobertura, otros, _ = al.normalizar_eventos(tmp_path)
    assert otros == [] and list(tabla["simbolo"]) == ["SPY", "SPY"] and list(cobertura["eventos"]) == [2.0]
    assert tabla.iloc[0]["id_evento"].startswith("sin-id-") and tabla.iloc[1]["id_evento"] == "d2"
    assert al.normalizar_eventos(tmp_path)[0]["id_evento"].tolist() == tabla["id_evento"].tolist()  # estable
    # Con dos símbolos pedidos, uno sin símbolo no se puede atribuir: detiene la normalización, con cualquier fecha.
    reloj = Reloj("2025-11-19T21:00:00Z")
    api = API({"/v1/corporate-actions": lambda p: {"corporate_actions": {"cash_dividends": [sin_simbolo]},
                                                   "next_page_token": None}})
    al.descargar_eventos(cliente(api, reloj), al.pedir_eventos(["SPY", "QQQ"], "2024-10-15", "2026-03-18"), tmp_path,
                         {"fecha": "2025-11-19", "etiqueta": "eventos-dos", "simbolos": ["SPY", "QQQ"]})
    with pytest.raises(ValueError, match="cash_dividends_incompleto"):
        al.tablas_para_piloto(tmp_path, "2020-01-01", "2020-01-31")


def borrar(ruta):
    """Borra un archivo del almacén, que lo deja de solo lectura (en Windows no se puede borrar así)."""
    os.chmod(ruta, stat.S_IREAD | stat.S_IWRITE)
    ruta.unlink()


def correr_captura(mercado, datos, monkeypatch, argumentos=("--ahora",), fallos_api=None, **fallos):
    """``scripts/capturar_alpaca.py`` (por omisión, ``--ahora``) de punta a punta, con la API sintética y solo SPXW.

    ``fallos_api`` inyecta estados HTTP por ruta; ``fallos`` sustituye funciones
    de ``alpaca`` por otras que lanzan un error. Devuelve el código de salida y
    el registro de la ejecución (o ``None``).
    """
    spec = importlib.util.spec_from_file_location("capturar_alpaca", RAIZ / "scripts" / "capturar_alpaca.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    texto = (RAIZ / "configs" / "captura_alpaca.toml").read_text(encoding="utf-8")
    texto = texto[:texto.index('[[captura.opciones]]\nsubyacente = "SPY"')] + texto[texto.index("[captura.acciones]"):]
    config = datos / "captura.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(texto, encoding="utf-8")
    reloj = Reloj("2025-11-17T14:45:00Z")  # el corte inmediato: la cadena sintética tiene cotizaciones
    api, vigilantes = api_sintetica(mercado, reloj), []
    api.fallos = dict(fallos_api or {})

    class Vigilante(VIGILANTE_REAL):  # para cancelarlos siempre, pase lo que pase
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            vigilantes.append(self)

    monkeypatch.setattr(al.Credenciales, "del_entorno", classmethod(lambda cls, entorno=None: al.Credenciales(
        CLAVE, SECRETO)))
    monkeypatch.setattr(al, "ClienteAlpaca", lambda cred, **kw: CLIENTE_REAL(cred, api, reloj, reloj.dormir, **kw))
    monkeypatch.setattr(al, "Vigilante", Vigilante)
    for nombre, error in fallos.items():
        monkeypatch.setattr(al, nombre, lambda *a, error=error, **k: (_ for _ in ()).throw(error))
    monkeypatch.setattr(sys, "argv", ["capturar_alpaca.py", "--datos", str(datos), "--config", str(config),
                                      *argumentos])
    try:
        codigo = script.main()
    finally:
        for v in vigilantes:
            v.cancelar()
    registros = sorted((datos / "raw" / "alpaca" / "ejecuciones").rglob("*.json"))
    return codigo, (json.loads(registros[0].read_text(encoding="utf-8")) if registros else None)


def test_captura_multiplazo_de_punta_a_punta(mercado, tmp_path, monkeypatch):
    texto = (RAIZ / "configs" / "captura_alpaca.toml").read_text(encoding="utf-8")
    texto = texto[:texto.index('[[captura.opciones]]\nsubyacente = "SPY"')] + texto[texto.index("[captura.acciones]"):]
    texto = texto.replace("objetivo_dias = 30.0", "objetivos_dias = [7.0, 14.0, 30.0]")
    ruta = tmp_path / "multi.toml"
    ruta.write_text(texto, encoding="utf-8")
    datos = tmp_path / "datos"
    codigo, registro = correr_captura(mercado, datos, monkeypatch, argumentos=("--ahora", "--config", str(ruta)))
    assert codigo == 0
    assert registro["horas"][0]["estado"] == "completa"
    ms = sorted((datos / "raw" / "alpaca" / "capturas").rglob("*.json"))
    m = json.loads(ms[0].read_text(encoding="utf-8"))
    seleccion = m["seleccion"]["SPXW"]["vencimientos"]
    assert len(seleccion) == len(set(seleccion))
    cot = mercado[0]
    corte = pd.Timestamp("2025-11-17T14:45:00Z")
    fecha = corte.date()
    fechas = sorted({str(v) for v in cot["vencimiento"] if fecha <= v <= fecha + dt.timedelta(days=50)})
    esperado = set()
    for objetivo in (7, 14, 30):
        elegido, _ = al.elegir_vencimientos(fechas, "PM", corte, objetivo, 2, True)
        esperado.update(str(v) for v in elegido)
    assert set(seleccion) == esperado
    assert len([s for s in m["solicitudes"].values() if s["tipo"] == "cadena"]) == len(esperado)


def test_cada_ejecucion_de_la_captura_deja_su_registro(mercado, tmp_path, monkeypatch):
    # Cierre de b240dc2 (operación): el registro de la ejecución mide la puntualidad; un error no puede perderlo.
    # 1. Un evento que la normalización del piloto rechaza no toca el resumen del día: no lee los eventos.
    datos = tmp_path / "evento_raro"
    sin_simbolo = {k: v for k, v in dividendo_json("d2", "2025-12-19", 0.5).items() if k != "symbol"}
    api = API({"/v1/corporate-actions": lambda p: {"corporate_actions": {"cash_dividends": [sin_simbolo]},
                                                   "next_page_token": None}})
    al.descargar_eventos(cliente(api, Reloj("2025-11-16T21:00:00Z")), al.pedir_eventos(["SPY", "QQQ"], "2024-10-15",
                         "2026-03-18"), datos, {"fecha": "2025-11-16", "etiqueta": "eventos-dos",
                                                "simbolos": ["SPY", "QQQ"]})
    codigo, registro = correr_captura(mercado, datos, monkeypatch)
    assert codigo == 0 and registro["horas"][0]["estado"] == "completa" and "error" not in registro
    assert (datos / "normalized" / "alpaca" / "diario" / "2025-11-17" / "resumen.json").exists()
    with pytest.raises(ValueError, match="cash_dividends_incompleto"):  # la del piloto sí se detiene
        al.tablas_para_piloto(datos, "2025-11-17", "2025-11-17")
    # 2. Si falla la normalización del día, la captura ya está: registro con el error y código 5.
    codigo, registro = correr_captura(mercado, tmp_path / "normalizacion", monkeypatch,
                                      tablas_para_piloto=RuntimeError("fallo simulado"))
    assert codigo == al.CODIGO_SIN_NORMALIZAR and registro["horas"][0]["estado"] == "completa"
    assert registro["error"]["etapa"] == "normalización del día" and "fallo simulado" in registro["error"]["error"]
    assert list((tmp_path / "normalizacion" / "raw" / "alpaca" / "capturas").rglob("*T*.json"))
    # 3. Si falla la preparación, la hora queda fallida con el motivo, y el registro existe.
    codigo, registro = correr_captura(mercado, tmp_path / "preparacion", monkeypatch,
                                      elegir_vencimientos=ValueError("sin vencimientos"))
    assert codigo == 1 and registro["horas"][0]["estado"] == "fallida"
    assert registro["horas"][0]["motivo"] == "error inesperado: ValueError"
    assert registro["error"]["etapa"] == "preparación y captura" and "listo_utc" not in registro
    # 4. Revisión de los cambios operativos, P2: el reloj del servidor falla (403) antes de planificar. El registro
    # se abrió antes, con el reloj local; no inventa el del servidor y marca la hora pedida «sin iniciar».
    codigo, registro = correr_captura(mercado, tmp_path / "reloj", monkeypatch, fallos_api={"/v2/clock": [403]})
    assert codigo == 1 and registro["error"]["etapa"] == "reloj del servidor"
    assert "HTTP 403" in registro["error"]["error"]
    assert registro["reloj"] is None and registro["fuente_instantes"] == "reloj local"
    assert registro["inicio_utc"] == "2025-11-17T14:45:00.000000Z" and registro["fecha"] == "2025-11-17"
    assert registro["horas"] == [{"hora": "inmediata", "accion": "ninguna", "estado": "sin iniciar",
                                  "motivo": "error al iniciar (reloj del servidor)"}]
    # 5. Falla la recuperación de diarios anteriores, también antes del bloque protegido.
    codigo, registro = correr_captura(mercado, tmp_path / "recuperacion", monkeypatch,
                                      recuperar=OSError("diario ilegible"))
    assert codigo == 1 and registro["error"] == {"etapa": "recuperación", "error": "OSError: diario ilegible",
                                                 "utc": "2025-11-17T14:45:00.000000Z"}
    assert registro["reloj"] is not None and registro["horas"][0]["estado"] == "sin iniciar"
    # 6. La recuperación aparte (paso «Recuperar» del workflow) también deja el suyo si falla.
    codigo, registro = correr_captura(mercado, tmp_path / "recuperar", monkeypatch, argumentos=("--recuperar",),
                                      recuperar=OSError("diario ilegible"))
    assert codigo == 1 and registro["tipo"] == "recuperacion" and registro["recuperadas"] == []
    assert registro["error"]["etapa"] == "recuperación" and registro["fuente_instantes"] == "reloj local"


def test_revision_de_la_operacion_de_las_sesiones(mercado, tmp_path):
    # Cierre de b240dc2, pasos 4 y 5: estado de cada corte, puntualidad, respaldo, recuperaciones, SIP y dividendos.
    capturar_sesiones(mercado, tmp_path)
    descargar_historicos(mercado, tmp_path, horas=("09:45",))  # el SIP de las 10:00 aún no se descargó
    borrar(tmp_path / "raw" / "alpaca" / "capturas" / str(FECHAS[1]) / f"{FECHAS[1]}T1000.json")  # perdida
    consulta_eventos(tmp_path, {"corporate_actions": {"cash_dividends": [dividendo_incompleto()]}},
                     "2025-11-18T20:21:00Z")

    def registro(inicio, fecha, **campos):
        al.escribir_ejecucion({"inicio_utc": inicio, "fecha": str(fecha), **campos}, tmp_path,
                              sufijo="_" + campos["tipo"] if "tipo" in campos else "")

    def hora(h, accion="capturar", estado="completa", **campos):
        return {"hora": h, "accion": accion, "estado": estado, **campos}

    ok = {"margen_s": 5.0, "duracion_s": 1.2, "despues_del_corte": 0, "errores": []}
    # Primera sesión: sin incidencias; el respaldo encuentra la hora completa y la omite.
    registro("2025-11-17T14:13:30Z", FECHAS[0], modo="programada", evento="schedule", disparo="11 14 * * 1-5",
             listo_utc="2025-11-17T14:14:10Z", horas=[hora("09:45", **ok)])
    registro("2025-11-17T14:28:05Z", FECHAS[0], modo="programada", evento="schedule", disparo="26 14 * * 1-5",
             horas=[hora("09:45", accion="omitir")])
    registro("2025-11-17T14:28:40Z", FECHAS[0], modo="programada", evento="schedule", disparo="26 14 * * 1-5",
             listo_utc="2025-11-17T14:29:30Z", horas=[hora("10:00", **ok)])
    # Segunda sesión: el titular no está listo a tiempo, se recupera su diario y el respaldo captura; las 10:00
    # no corrieron.
    registro("2025-11-18T14:15:00Z", FECHAS[1], modo="programada", evento="schedule", disparo="11 14 * * 1-5",
             interrupcion={"motivo": "sin preparar a tiempo (2025-11-18T14:39:00+00:00)"},
             horas=[hora("09:45", estado="fallida", motivo="sin preparar a tiempo")])
    registro("2025-11-18T14:39:30Z", FECHAS[1], tipo="recuperacion",
             recuperadas=[{"etiqueta": f"{FECHAS[1]}T0945", "estado": "fallida", "motivo": "sin preparar"}])
    registro("2025-11-18T14:40:10Z", FECHAS[1], modo="programada", evento="schedule", disparo="26 14 * * 1-5",
             listo_utc="2025-11-18T14:42:00Z", horas=[hora("09:45", **ok)])
    registro("2025-11-18T15:21:00Z", FECHAS[1], tipo="historico", eventos={"estado": "completa", "errores": []})
    # Las 10:00 de la segunda sesión: un intento que falló al iniciar (sin reloj del servidor), no una ausencia.
    registro("2025-11-18T14:43:10Z", FECHAS[1], modo="programada", evento="schedule", disparo="41 14 * * 1-5",
             fuente_instantes="reloj local", reloj=None,
             error={"etapa": "reloj del servidor", "error": "RuntimeError: HTTP 403", "utc": "2025-11-18T14:43:10Z"},
             horas=[hora("10:00", accion="ninguna", estado="sin iniciar",
                         motivo="error al iniciar (reloj del servidor)")])
    registro("2025-11-18T15:05:00Z", FECHAS[1], tipo="recuperacion", recuperadas=[],
             error={"etapa": "recuperación", "error": "OSError: diario ilegible", "utc": "2025-11-18T15:05:00Z"})
    registro("2025-11-18T14:00:00Z", FECHAS[1], modo="inmediata", horas=[hora("inmediata", **ok)])  # no cuenta

    revision = operacion.revisar(tmp_path, FECHAS[0], FECHAS[1], ["09:45", "10:00"], 5.0,
                                 ahora_utc="2025-11-19T00:00:00Z")
    cortes = {(c["fecha"], c["hora"]): c for c in revision["cortes"]}
    uno, dos, perdido = (cortes[(str(FECHAS[0]), "09:45")], cortes[(str(FECHAS[1]), "09:45")],
                         cortes[(str(FECHAS[1]), "10:00")])
    assert (uno["estado"], len(uno["ejecuciones"]), uno["intentos"], uno["sip"]) == ("completa", 2, 1, "completa")
    assert (uno["captura"]["retraso_s"], uno["captura"]["margen_listo_s"], uno["captura"]["margen_rafaga_s"]) == (
        150.0, 1850.0, 5.0)
    assert (dos["intentos"], dos["captura"]["disparo"], dos["captura"]["retraso_s"],
            dos["captura"]["margen_listo_s"]) == (2, "26 14 * * 1-5", 850.0, 180.0)
    assert (perdido["estado"], perdido["intentos"], perdido["sip"]) == ("perdida", 0, "sin descargar")
    assert [(e["estado"], e["error"]) for e in perdido["ejecuciones"]] == [("sin iniciar", "RuntimeError: HTTP 403")]
    r = revision["resumen"]
    assert r["estados"] == {"completa": 3, "parcial": 0, "fallida": 0, "perdida": 1, "pendiente": 0}
    assert (r["cortes_con_reintento"], r["sin_preparar_a_tiempo"], r["plazo_absoluto"], r["recuperaciones"],
            r["retraso_max_s"], r["margen_listo_min_s"], r["sip_completo"]) == (1, 1, 0, 1, 850.0, 180.0, 2)
    assert (r["errores"], r["sin_iniciar"], r["errores_de_recuperacion"]) == (1, 1, 1)
    assert revision["dividendos"]["discrepancias_abiertas"] == {"incompleto": 1}
    assert revision["eventos"] == [{"fecha": str(FECHAS[1]), "inicio_utc": "2025-11-18T15:21:00Z",
                                    "estado": "completa", "errores": []}]
    texto = operacion.informe(revision)
    assert f"| {FECHAS[1]} | 10:00 | perdida | sin descargar | 1 | 0 | — |" in texto
    assert (f"- {FECHAS[1]} 10:00: sin iniciar en la ejecución de 2025-11-18T14:43:10Z "
            "(RuntimeError: HTTP 403;") in texto
    assert "La recuperación de 2025-11-18T15:05:00Z falló (OSError: diario ilegible)" in texto
    assert "sin preparar a tiempo" in texto and f"Recuperada {FECHAS[1]}T0945: fallida" in texto
    assert "Discrepancias abiertas: incompleto 1;" in texto
    assert "(sin preparar a tiempo (2025-11-18T14:39:00+00:00));" in texto  # el motivo, una sola vez
    assert not any(x in texto.lower() for x in ("bid", "ask", "precio", "580"))  # solo agregados, sin precios
    # Sin ninguna ejecución registrada, los cortes pasados quedan perdidos y sin actividad inventada.
    vacia = operacion.revisar(tmp_path / "vacia", FECHAS[0], FECHAS[1], ["09:45", "10:00"], 5.0,
                              ahora_utc="2025-11-19T00:00:00Z")
    assert [(c["estado"], c["ejecuciones"]) for c in vacia["cortes"]] == [("perdida", [])] * 4


def test_revisar_operacion_valida_la_ruta_de_resoluciones(tmp_path, monkeypatch):
    # Revisión de los cambios operativos, P2: una ruta explícita que no existe no se ignora en silencio.
    spec = importlib.util.spec_from_file_location("revisar_operacion", RAIZ / "scripts" / "revisar_operacion.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    datos = tmp_path / "datos"
    consulta_eventos(datos, {"corporate_actions": {"cash_dividends": [dividendo_json("d1", "2025-11-18", 1.8)]}},
                     "2025-11-18T21:00:00Z")
    texto = ("id_evento,simbolo,resolucion,conocido_utc,fuente,nota,fecha_ex,monto\n"
             "d1,SPY,vigente,2025-11-19T15:00:00Z,aviso del emisor,,,\n")

    def correr(nombre, *extra):
        salida = tmp_path / nombre
        monkeypatch.setattr(sys, "argv", ["revisar_operacion.py", "--datos", str(datos), "--desde", "2025-11-17",
                                          "--hasta", "2025-11-17", "--salida", str(salida), *extra])
        codigo = script.main()
        return codigo, json.loads((salida / "resumen.json").read_text(encoding="utf-8"))

    codigo, resumen = correr("sin_archivo")  # sin el argumento ni el archivo por omisión: opcional
    assert codigo == 1 and resumen["dividendos"]["confirmadas_por_resolucion"] == 0  # 1: sin capturas
    with pytest.raises(SystemExit) as salida:
        correr("inexistente", "--resoluciones", str(tmp_path / "no_existe.csv"))
    assert salida.value.code == 2 and not (tmp_path / "inexistente").exists()
    (datos / "resoluciones_dividendos.csv").write_text(texto, encoding="utf-8")  # el archivo por omisión se aplica
    assert correr("por_omision")[1]["dividendos"]["confirmadas_por_resolucion"] == 1
    explicito = tmp_path / "resoluciones.csv"
    explicito.write_text(texto, encoding="utf-8")
    borrar_por_omision = datos / "resoluciones_dividendos.csv"
    borrar_por_omision.unlink()
    assert correr("explicito", "--resoluciones", str(explicito))[1]["dividendos"]["confirmadas_por_resolucion"] == 1


def test_objetivo_del_sip_historico_de_punta_a_punta(mercado, tmp_path):
    cot_sint, sub_sint, verdad = mercado
    capturar_sesiones(mercado, tmp_path)
    descargar_historicos(mercado, tmp_path)
    ex, monto = verdad["dividendos"].loc[0, "fecha_ex"], verdad["dividendos"].loc[0, "monto"]
    assert ex == FECHAS[1]
    anunciado = {"corporate_actions": {"cash_dividends": [dividendo_json("d1", ex, monto)]}, "next_page_token": None}
    descargar_eventos(tmp_path, [anunciado], desde="2025-11-14T21:00:00Z")  # anunciado días antes, como SPY
    cfg = pl.cargar_config(RAIZ / "configs" / "piloto.toml")
    with open(RAIZ / "configs" / "captura_alpaca.toml", "rb") as f:
        implicito = tomllib.load(f)["implicito"]

    def piloto():
        t = al.tablas_para_piloto(tmp_path, cfg_implicito=implicito, reglas=cfg.reglas)
        r = pl.ejecutar(t.cotizaciones, t.subyacente, FECHAS, cfg, fuente_objetivo="alpaca/sip",
                        dividendos=t.dividendos, cobertura=t.cobertura_dividendos)
        e = et.etiquetas_vigentes(r.etiquetas)
        return t, r, e[(e["serie"] == "objetivo") & (e["horizonte"] == 1)].set_index("sesion")

    t, r, e = piloto()
    with pytest.raises(ValueError, match="objetivo SPY: hay varias fuentes"):  # SPY de IEX y del SIP
        pl.ejecutar(t.cotizaciones, t.subyacente, FECHAS, cfg)
    # Solo con la consulta anterior al fin, el rendimiento total no se confirma; el de precio, sí.
    assert e.loc[FECHAS[0], "estado"] == "sin dividendos confirmados"
    assert "anterior al fin" in e.loc[FECHAS[0], "motivo"]
    assert np.isfinite(e.loc[FECHAS[0], "retorno_precio_log"])
    # La consulta del workflow del histórico, a las 10:21, habilita la etiqueta y fija su madurez.
    descargar_eventos(tmp_path, [anunciado], desde="2025-11-18T15:21:00Z")
    t, r, e = piloto()
    p = r.principal.set_index("fecha")
    spy = {f: verdad["objetivo"][(f, "09:45")] for f in FECHAS}
    # El mid de la última cotización con los dos lados (la más reciente no tiene bid).
    assert p.loc[FECHAS[0], "ret_1_objetivo"] == pytest.approx(np.log((spy[FECHAS[1]] + monto) / spy[FECHAS[0]]))
    assert p.loc[FECHAS[0], "ret_precio_1_objetivo"] == pytest.approx(np.log(spy[FECHAS[1]] / spy[FECHAS[0]]))
    assert p.loc[FECHAS[0], "div_1_objetivo"] == monto and p.loc[FECHAS[0], "estado_div_1_objetivo"] == "provisional"
    ok = e[e["estado"] == "ok"]
    assert len(ok) == 1 and ok.iloc[0]["label_available_at"] == pd.Timestamp("2025-11-18T15:21:00Z")
    assert set(ok["fuente"]) == {"alpaca/sip"}
    a = r.dictamen["alcance"]
    assert a["fuente_objetivo"] == "alpaca/sip" and a["dividendos_objetivo"].startswith("2 consultas completas")
    # Ninguna influencia sobre las señales: las medidas de SPXW no cambian sin el histórico.
    sin_sip = t.subyacente[t.subyacente["feed"] != "sip"]
    base = pl.ejecutar(t.cotizaciones, sin_sip, FECHAS, cfg, fuente_objetivo="alpaca/iex").principal
    medidas = [c for c in base.columns if not c.endswith("_objetivo")]
    pd.testing.assert_frame_equal(r.principal[medidas], base[medidas])
    pd.testing.assert_frame_equal(r.completa, pl.ejecutar(t.cotizaciones, sin_sip, FECHAS, cfg,
                                                          fuente_objetivo="alpaca/iex").completa)


# --- Revalidación de d815bdd: recuperación operativa ----------------------------------------

HIJO = """
import json, sys, time
sys.path.insert(0, {raiz!r})
import pandas as pd
from quantileflow import alpaca as al

datos, config = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))


def transporte(url, cabeceras, tiempo_max):
    if "page_token=p2" in url:
        time.sleep(600)  # la segunda página no llega nunca
    return 200, {{}}, json.dumps(config["pagina1"]).encode()


cliente = al.ClienteAlpaca(al.Credenciales("clave", "secreto"), transporte, reintentos=0)
vigilante = None
if config["plazo_s"]:
    vigilante = al.Vigilante(pd.Timestamp.now(tz="UTC") + pd.Timedelta(seconds=config["plazo_s"]))
al.capturar(cliente, [al.pedir_cadena("SPXW", config["vencimiento"], "indicative")], datos, config["meta"],
            config["previas"], vigilante=vigilante)
print("terminó sin interrupción")
"""


def lanzar_captura(mercado, tmp_path, plazo_s=None):
    """Una captura real en otro proceso: la primera página llega y la segunda se cuelga."""
    cot, _, _ = mercado
    corte_sintetico = cal.instante(FECHAS[0], "09:45")
    vencimiento = str(cot.loc[cot["sello_snapshot_utc"] == corte_sintetico, "vencimiento"].iloc[0])
    datos = tmp_path / "datos"
    pedidos = [al.pedir_contratos("SPX", FECHAS[0], FECHAS[0] + dt.timedelta(days=60), "SPXW")]
    resultados, _ = al.ejecutar(cliente(API({"/v2/options/contracts": lambda p: contratos_json(cot)})), pedidos)
    previas = al.guardar_respuestas(resultados, {p.nombre: p.tipo for p in pedidos}, datos)
    ahora = pd.Timestamp.now(tz="UTC")
    fecha = next(f for f in cal.sesiones(ahora.date(), ahora.date() + dt.timedelta(days=15))
                 if cal.instante(f, "09:45") > ahora + pd.Timedelta(minutes=10))  # todo llega antes del corte
    corte = cal.instante(fecha, "09:45")
    meta = {"fecha": str(fecha), "hora": "09:45", "corte_utc": al.iso(corte), "etiqueta": f"{fecha}T0945",
            "modo": "programada"}
    config = {"pagina1": dict(cadena_json(cot, vencimiento, corte_sintetico), next_page_token="p2"),
              "vencimiento": vencimiento, "meta": meta, "previas": previas, "plazo_s": plazo_s}
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "hijo.py").write_text(HIJO.format(raiz=str(RAIZ)), encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(tmp_path / "hijo.py"), str(datos), str(tmp_path / "config.json")],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc, datos, meta, f"cadena_SPXW_{vencimiento}"


def test_corte_brusco_tras_una_pagina_se_recupera_como_parcial(mercado, tmp_path):
    proc, datos, meta, nombre = lanzar_captura(mercado, tmp_path)
    diario = al.ruta_diario(datos, meta["fecha"], meta["etiqueta"])
    try:
        limite = time.monotonic() + 60
        while not (diario.exists() and b'"evento": "pagina"' in diario.read_bytes()):
            assert time.monotonic() < limite and proc.poll() is None, "la primera página no llegó al diario"
            time.sleep(0.05)
        proc.kill()  # sin limpieza de ningún tipo
    finally:
        proc.communicate(timeout=60)
    assert not al.ruta_manifiesto(datos, meta["fecha"], meta["etiqueta"]).exists()
    recuperados = al.recuperar(datos)
    assert len(recuperados) == 1 and al.recuperar(datos) == []  # una sola vez
    m = recuperados[0]
    e = m["solicitudes"][nombre]
    assert (m["estado"], e["estado"], len(e["paginas"])) == ("parcial", "parcial", 1)
    assert m["interrumpida"] and "sin escribir el manifiesto" in m["motivo_interrupcion"]
    assert "interrumpida" in e["error"] and m["diario"]["sha256"] == almacen.sha256_archivo(diario)
    assert (datos / e["paginas"][0]["archivo"]).exists()
    despues = pd.Timestamp(meta["corte_utc"]) + pd.Timedelta(minutes=1)
    assert al.planificar(datos, meta["fecha"], ["09:45"], despues, 5.0)[0]["estado"] == "parcial"
    cot, _, resumenes, _ = al.normalizar(datos)  # el manifiesto recuperado se normaliza como cualquier otro
    assert len(cot) > 0 and resumenes[0]["estado"] == "parcial"
    antes = pd.Timestamp(meta["corte_utc"]) - pd.Timedelta(minutes=5)
    paso = al.planificar(datos, meta["fecha"], ["09:45"], antes, 5.0)[0]  # aún antes del corte: se repite
    assert (paso["accion"], paso["etiqueta"]) == ("capturar", f"{meta['fecha']}T0945-2")


def test_plazo_absoluto_termina_una_solicitud_colgada(mercado, tmp_path):
    proc, datos, meta, _ = lanzar_captura(mercado, tmp_path, plazo_s=3)
    salida, errores = proc.communicate(timeout=120)
    assert proc.returncode == al.CODIGO_PLAZO_VENCIDO, errores.decode()
    assert b"plazo absoluto vencido" in errores and b"sin interrupci" not in salida
    eventos, truncada = al.leer_diario(al.ruta_diario(datos, meta["fecha"], meta["etiqueta"]))
    assert [e["evento"] for e in eventos] == ["inicio", "solicitud", "pagina", "interrumpida"] and not truncada
    m = al.recuperar(datos)[0]
    assert m["estado"] == "parcial" and m["motivo_interrupcion"].startswith("plazo absoluto vencido")


def test_diario_con_la_ultima_linea_truncada_o_roto_en_medio(tmp_path):
    ruta = tmp_path / "x.diario.jsonl"
    lineas = [json.dumps({"evento": "inicio"}), json.dumps({"evento": "solicitud"})]
    for cola in ('{"evento": "pag', '{"motivo": "sesión'.encode()[:-1].decode("utf-8", "ignore")):
        ruta.write_bytes(("\n".join(lineas) + "\n").encode() + cola.encode())
        eventos, truncada = al.leer_diario(ruta)
        assert [e["evento"] for e in eventos] == ["inicio", "solicitud"] and truncada
    ruta.write_bytes(("\n".join(lineas) + "\n").encode() + "sesió".encode()[:-1])  # carácter partido
    assert al.leer_diario(ruta)[1]
    ruta.write_bytes(b'{"evento": "inicio"}\n{roto\n{"evento": "fin"}\n')
    with pytest.raises(ValueError, match="línea 2"):
        al.leer_diario(ruta)
    with pytest.raises(FileExistsError):  # un diario existente nunca se continúa
        al.Diario(ruta, {"evento": "inicio"})


# --- Revisión de 8c97b2b: el respaldo de la misma hora llega al corte ------------------------------

def test_plazo_de_preparacion_deja_llegar_al_respaldo():
    corte = cal.instante(FECHAS[0], "09:45")

    def antes(minutos):
        return corte - pd.Timedelta(minutes=minutos)

    def plazo(ahora, programada=True):
        return al.plazo_preparacion(corte, ahora, 360.0, 120.0, 5.0, programada)

    assert plazo(antes(32)) == antes(6)  # el titular de las 09:13 debe estar listo a las 09:39
    assert plazo(antes(4.5)) == antes(2.5)  # el respaldo que arranca a las 09:40:30 tiene dos minutos
    assert plazo(antes(1.5)) == corte - pd.Timedelta(seconds=5)  # nunca después del inicio de la ráfaga
    assert plazo(antes(600), programada=False) == antes(598)  # captura inmediata: dos minutos desde ahora


def test_vigilante_de_preparacion_registra_y_termina():
    import threading
    fin, salidas, motivos = threading.Event(), [], []

    def salir(codigo):
        salidas.append(codigo)
        fin.set()

    plazo = pd.Timestamp.now(tz="UTC") + pd.Timedelta(seconds=0.2)
    al.Vigilante(plazo, salir=salir, codigo=al.CODIGO_SIN_PREPARAR, motivo="sin preparar a tiempo",
                 al_vencer=motivos.append)
    assert fin.wait(10) and salidas == [al.CODIGO_SIN_PREPARAR]
    assert motivos == [f"sin preparar a tiempo ({al.iso(plazo)})"]
    cancelado = al.Vigilante(pd.Timestamp.now(tz="UTC") + pd.Timedelta(seconds=0.2), salir=salir)
    cancelado.cancelar()  # lista a tiempo: no termina nada
    time.sleep(0.4)
    assert salidas == [al.CODIGO_SIN_PREPARAR]
