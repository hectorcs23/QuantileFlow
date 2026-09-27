"""Adaptador de Alpaca sin red: cliente, crudo, manifiestos, normalización, replay y subyacente implícito.

Las respuestas tienen la forma de las reales (verificada el 26 de septiembre de
2026), pero sus precios salen del mercado **sintético**.
"""
import datetime as dt
import gzip
import http.client
import json
import os
import stat
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
from quantileflow import implicito as im
from quantileflow import piloto as pl
from quantileflow import sintetico as sn

RAIZ = Path(__file__).resolve().parents[1]
CLAVE, SECRETO = "PKPRUEBA0123456789", "secreto-que-no-debe-aparecer"
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


def test_dividendos_de_los_eventos_corporativos(tmp_path):
    d1 = dividendo_json("d1", "2025-11-18", 1.8)
    cuerpos = [{"corporate_actions": {}, "next_page_token": None},  # aún no anunciado
               {"corporate_actions": {"cash_dividends": [d1]}, "next_page_token": None},
               {"corporate_actions": {"cash_dividends": [dict(d1, rate=1.85)]}, "next_page_token": None},  # corregido
               {"corporate_actions": {"cash_dividends": [dict(d1, rate=1.85),
                                                         dividendo_json("d2", "2025-12-19", 0.5, especial=True)],
                                      "forward_splits": [{"id": "s1", "symbol": "SPY", "ex_date": "2025-06-02",
                                                          "process_date": "2025-06-02", "old_rate": 1,
                                                          "new_rate": 2}]},
                "next_page_token": None}]
    descargar_eventos(tmp_path, cuerpos)
    tabla, otros, usados = al.normalizar_eventos(tmp_path)
    assert ct.validar(tabla, ct.DIVIDENDOS) == [] and len(usados) == 4
    d = tabla.set_index("id_evento")
    assert d.loc["d1", "monto"] == 1.85 and d.loc["d1", "fecha_ex"] == dt.date(2025, 11, 18)
    assert d.loc["d1", "recibido_utc"] == pd.Timestamp("2025-11-16T21:00:00Z")  # primera consulta con ese monto
    assert (d["consultado_utc"] == pd.Timestamp("2025-11-17T21:00:00Z")).all()  # la consulta más reciente
    assert d["disponible_utc"].isna().all()  # Alpaca no da la hora del anuncio
    assert (d.loc["d1", "clase"], d.loc["d2", "clase"]) == ("ordinario", "especial")
    assert otros == [{"tipo": "forward_splits", "simbolo": "SPY", "fecha": "2025-06-02", "id": "s1"}]
    with pytest.raises(ValueError, match="forward_splits de SPY el 2025-06-02"):
        al.tablas_para_piloto(tmp_path, "2025-06-01", "2025-06-30")
    t = al.tablas_para_piloto(tmp_path, "2025-11-17", "2025-11-18")  # fuera del rango: se informa
    assert t.eventos_no_tratados == otros and len(t.dividendos) == 2


def test_objetivo_del_sip_historico_de_punta_a_punta(mercado, tmp_path):
    cot_sint, sub_sint, verdad = mercado
    capturar_sesiones(mercado, tmp_path)
    descargar_historicos(mercado, tmp_path)
    ex, monto = verdad["dividendos"].loc[0, "fecha_ex"], verdad["dividendos"].loc[0, "monto"]
    assert ex == FECHAS[1]
    anunciado = {"corporate_actions": {"cash_dividends": [dividendo_json("d1", ex, monto)]}, "next_page_token": None}
    descargar_eventos(tmp_path, [anunciado], desde="2025-11-18T21:00:00Z")  # conocido después del fin
    cfg = pl.cargar_config(RAIZ / "configs" / "piloto.toml")
    with open(RAIZ / "configs" / "captura_alpaca.toml", "rb") as f:
        implicito = tomllib.load(f)["implicito"]
    t = al.tablas_para_piloto(tmp_path, cfg_implicito=implicito, reglas=cfg.reglas)
    with pytest.raises(ValueError, match="objetivo SPY: hay varias fuentes"):  # SPY de IEX y del SIP
        pl.ejecutar(t.cotizaciones, t.subyacente, FECHAS, cfg)
    r = pl.ejecutar(t.cotizaciones, t.subyacente, FECHAS, cfg, fuente_objetivo="alpaca/sip", dividendos=t.dividendos)
    p = r.principal.set_index("fecha")
    spy = {f: verdad["objetivo"][(f, "09:45")] for f in FECHAS}
    # El mid de la última cotización con los dos lados (la más reciente no tiene bid).
    assert p.loc[FECHAS[0], "ret_1_objetivo"] == pytest.approx(np.log((spy[FECHAS[1]] + monto) / spy[FECHAS[0]]))
    assert p.loc[FECHAS[0], "ret_precio_1_objetivo"] == pytest.approx(np.log(spy[FECHAS[1]] / spy[FECHAS[0]]))
    e = r.etiquetas[(r.etiquetas["serie"] == "objetivo") & (r.etiquetas["estado"] == "ok")]
    # Madura cuando se supo del dividendo que suma: la consulta de las 21:00, después del fin.
    assert len(e) == 1 and e.iloc[0]["label_available_at"] == pd.Timestamp("2025-11-18T21:00:00Z")
    assert set(e["fuente"]) == {"alpaca/sip"}
    # Si ya se conocía antes (anunciado días antes, como hace SPY), madura con la publicación del SIP.
    descargar_eventos(tmp_path, [anunciado], desde="2025-11-14T21:00:00Z")
    t = al.tablas_para_piloto(tmp_path, cfg_implicito=implicito, reglas=cfg.reglas)
    r = pl.ejecutar(t.cotizaciones, t.subyacente, FECHAS, cfg, fuente_objetivo="alpaca/sip", dividendos=t.dividendos)
    e = r.etiquetas[(r.etiquetas["serie"] == "objetivo") & (r.etiquetas["estado"] == "ok")]
    assert e.iloc[0]["label_available_at"] == cal.instante(FECHAS[1]) + pd.Timedelta(minutes=15)
    assert r.principal.set_index("fecha").loc[FECHAS[0], "div_1_objetivo"] == monto
    a = r.dictamen["alcance"]
    assert a["fuente_objetivo"] == "alpaca/sip" and a["dividendos_objetivo"].startswith("consultados hasta")
    # Ninguna influencia sobre las señales: las medidas de SPXW no cambian sin el histórico.
    sin_sip = t.subyacente[t.subyacente["feed"] != "sip"]
    base = pl.ejecutar(t.cotizaciones, sin_sip, FECHAS, cfg, fuente_objetivo="alpaca/iex").principal
    medidas = [c for c in base.columns if not c.endswith("_objetivo")]
    pd.testing.assert_frame_equal(r.principal[medidas], base[medidas])
    pd.testing.assert_frame_equal(r.completa, pl.ejecutar(t.cotizaciones, sin_sip, FECHAS, cfg,
                                                          fuente_objetivo="alpaca/iex").completa)
    # Una consulta de dividendos anterior al fin de la etiqueta no la confirma.
    temprano = t.dividendos.assign(consultado_utc=cal.instante(FECHAS[1]) - pd.Timedelta(hours=1))
    e = pl.ejecutar(t.cotizaciones, t.subyacente, FECHAS, cfg, fuente_objetivo="alpaca/sip",
                    dividendos=temprano).etiquetas
    fila = e[(e["serie"] == "objetivo") & (e["horizonte"] == 1)].set_index("sesion").loc[FECHAS[0]]
    assert fila["estado"] == "sin dividendos confirmados" and np.isnan(fila["retorno_log"])
    assert np.isfinite(fila["retorno_precio_log"])
