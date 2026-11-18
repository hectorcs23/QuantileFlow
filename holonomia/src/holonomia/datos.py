"""Descarga de cotizaciones cripto de Alpaca y crudo inmutable.

Qué da Alpaca (comprobado el 18 de noviembre de 2026 contra la API con la
cuenta del entorno):

* ``GET /v2/assets?asset_class=crypto`` (Trading API) — inventario de pares.
  El 18 de noviembre de 2026 había 73 pares activos sobre 37 monedas.
* ``GET /v1beta3/crypto/us/quotes`` (Market Data) — **histórico de
  cotizaciones de dos lados**, con ``bp``, ``ap``, ``bs``, ``as`` y sello del
  exchange en nanosegundos. Acepta varios símbolos por petición y pagina con
  ``next_page_token``. No pide suscripción: el plan gratuito lo sirve.
  Profundidad comprobada: hay datos en 2023-06, 2024-06 y 2025-06; no los hay
  en 2021-06 ni 2022-06.
* Límite de peticiones observado en las cabeceras: ``X-Ratelimit-Limit: 200``
  por minuto.

Esto es lo que vuelve innecesaria la captura en vivo de §2.2: el histórico
tiene el bid/ask tick a tick, así que no hace falta cron ni websocket.

Crudo inmutable (regla 2 del proyecto). Cada página de respuesta se guarda tal
como llega, comprimida con gzip, y el manifiesto anota la petición, los
parámetros, el estado, las horas de envío y recepción y el SHA-256 del
contenido. La normalización lee sólo el crudo, así que reprocesar da siempre
las mismas tablas. Las credenciales viajan únicamente en las cabeceras: nunca
se escriben en disco.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

URL_DATOS = "https://data.alpaca.markets"
URL_TRADING_PAPER = "https://paper-api.alpaca.markets"
RUTA_QUOTES = "/v1beta3/crypto/us/quotes"
RUTA_BARRAS = "/v1beta3/crypto/us/bars"
RUTA_ACTIVOS = "/v2/assets"
LIMITE_PAGINA = 10_000
COLUMNAS = ("par", "bid", "ask", "bid_size", "ask_size", "ts_exchange", "ts_captura")


class ErrorAlpaca(RuntimeError):
    def __init__(self, estado, ruta, mensaje):
        super().__init__(f"{ruta}: HTTP {estado}: {mensaje}")
        self.estado = estado


@dataclass(frozen=True, repr=False)
class Credenciales:
    """Clave y secreto. ``repr`` no los muestra: no deben llegar a registros."""

    clave: str
    secreto: str

    def __repr__(self) -> str:
        return "Credenciales(clave=<oculta>, secreto=<oculto>)"

    @classmethod
    def del_entorno(cls, entorno=None) -> "Credenciales":
        entorno = os.environ if entorno is None else entorno
        clave = entorno.get("APCA_API_KEY_ID")
        secreto = entorno.get("APCA_API_SECRET_KEY")
        if not clave or not secreto:
            raise RuntimeError("faltan APCA_API_KEY_ID o APCA_API_SECRET_KEY en el entorno")
        return cls(clave, secreto)

    def cabeceras(self) -> dict[str, str]:
        return {"APCA-API-KEY-ID": self.clave, "APCA-API-SECRET-KEY": self.secreto,
                "Accept": "application/json"}


def _pedir(url: str, ruta: str, params: dict, cred: Credenciales,
           reintentos: int = 4) -> tuple[bytes, dict]:
    """Una petición GET con reintentos. Devuelve el cuerpo crudo y su recibo."""
    consulta = urllib.parse.urlencode(params)
    completa = f"{url}{ruta}?{consulta}"
    ultimo = None
    for intento in range(reintentos):
        enviado = dt.datetime.now(dt.timezone.utc)
        pedido = urllib.request.Request(completa, headers=cred.cabeceras())
        try:
            with urllib.request.urlopen(pedido, timeout=60) as resp:
                cuerpo = resp.read()
                recibido = dt.datetime.now(dt.timezone.utc)
                recibo = {
                    "ruta": ruta,
                    "parametros": {k: v for k, v in params.items()},
                    "estado": resp.status,
                    "enviado_utc": enviado.isoformat(),
                    "recibido_utc": recibido.isoformat(),
                    "sha256_contenido": hashlib.sha256(cuerpo).hexdigest(),
                    "bytes": len(cuerpo),
                    "limite_restante": resp.headers.get("x-ratelimit-remaining"),
                }
                return cuerpo, recibo
        except urllib.error.HTTPError as e:
            ultimo = ErrorAlpaca(e.code, ruta, e.read()[:400].decode("utf-8", "replace"))
            if e.code not in (429, 500, 502, 503, 504):
                raise ultimo
        except urllib.error.URLError as e:
            ultimo = ErrorAlpaca(0, ruta, str(e.reason))
        time.sleep(2.0 * (intento + 1))
    raise ultimo


def inventario_pares(cred: Credenciales | None = None) -> pd.DataFrame:
    """Pares cripto activos en Alpaca, con sus mínimos de operación."""
    cred = cred or Credenciales.del_entorno()
    cuerpo, _ = _pedir(URL_TRADING_PAPER, RUTA_ACTIVOS,
                       {"asset_class": "crypto", "status": "active"}, cred)
    activos = json.loads(cuerpo)
    filas = [{"simbolo": a["symbol"], "nombre": a["name"], "operable": a["tradable"],
              "min_orden": float(a.get("min_order_size") or "nan"),
              "incremento": float(a.get("min_trade_increment") or "nan")}
             for a in activos if "/" in a["symbol"]]
    return pd.DataFrame(filas).sort_values("simbolo").reset_index(drop=True)


def descargar_quotes(simbolos, inicio, fin, destino, cred: Credenciales | None = None,
                     limite: int = LIMITE_PAGINA) -> Path:
    """Baja el histórico de cotizaciones y lo guarda crudo, página por página.

    ``inicio`` y ``fin`` son RFC-3339 en UTC. Devuelve el directorio de la
    captura, que contiene ``pagina-000.json.gz`` ... y ``manifiesto.json``.
    """
    cred = cred or Credenciales.del_entorno()
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    base = {"symbols": ",".join(simbolos), "start": inicio, "end": fin, "limit": limite}
    recibos, token, n = [], None, 0
    while True:
        params = dict(base)
        if token:
            params["page_token"] = token
        cuerpo, recibo = _pedir(URL_DATOS, RUTA_QUOTES, params, cred)
        archivo = destino / f"pagina-{n:03d}.json.gz"
        archivo.write_bytes(gzip.compress(cuerpo))
        recibo["archivo"] = archivo.name
        recibo["sha256_archivo"] = hashlib.sha256(archivo.read_bytes()).hexdigest()
        recibos.append(recibo)
        token = json.loads(cuerpo).get("next_page_token")
        n += 1
        if not token:
            break

    manifiesto = {
        "proveedor": "alpaca",
        "endpoint": RUTA_QUOTES,
        "simbolos": list(simbolos),
        "inicio": inicio,
        "fin": fin,
        "paginas": recibos,
        "capturado_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    (destino / "manifiesto.json").write_text(json.dumps(manifiesto, indent=2))
    return destino


def _comprobar_hashes(destino: Path, manifiesto: dict) -> None:
    for pagina in manifiesto["paginas"]:
        ruta = destino / pagina["archivo"]
        visto = hashlib.sha256(ruta.read_bytes()).hexdigest()
        if visto != pagina["sha256_archivo"]:
            raise ValueError(f"el crudo cambió desde la captura: {ruta}")


def cargar_quotes(destino) -> pd.DataFrame:
    """Lee el crudo de una captura y lo normaliza al esquema de §2.2.

    Columnas: ``par, bid, ask, bid_size, ask_size, ts_exchange, ts_captura``.
    ``ts_exchange`` es la hora del evento según Alpaca; ``ts_captura`` es la
    hora en que llegó la página que lo trajo, cota superior del instante en
    que el dato estuvo disponible.
    """
    destino = Path(destino)
    manifiesto = json.loads((destino / "manifiesto.json").read_text())
    _comprobar_hashes(destino, manifiesto)

    filas = []
    for pagina in manifiesto["paginas"]:
        cuerpo = gzip.decompress((destino / pagina["archivo"]).read_bytes())
        recibido = pagina["recibido_utc"]
        for par, quotes in (json.loads(cuerpo).get("quotes") or {}).items():
            for q in quotes:
                filas.append((par, q["bp"], q["ap"], q["bs"], q["as"], q["t"], recibido))

    df = pd.DataFrame(filas, columns=list(COLUMNAS))
    if df.empty:
        return df.astype({"bid": float, "ask": float, "bid_size": float, "ask_size": float})
    df["ts_exchange"] = pd.to_datetime(df["ts_exchange"], format="ISO8601", utc=True)
    df["ts_captura"] = pd.to_datetime(df["ts_captura"], format="ISO8601", utc=True)
    for c in ("bid", "ask", "bid_size", "ask_size"):
        df[c] = df[c].astype(float)
    return (df.sort_values(["ts_exchange", "par"], kind="stable")
              .drop_duplicates()
              .reset_index(drop=True))
