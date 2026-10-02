"""Descarga el historial gratuito de Alpaca para la exploración del skew 0DTE de SPY.

Para cada sesión desde febrero de 2024 guarda, en ``data/exploracion/0dte/<fecha>.json.gz``:

- las barras de 1 minuto de SPY (feed SIP, sin ajustar);
- las barras de 1 minuto de las opciones de SPY que vencen ese día, calls y puts, en todos los strikes
  enteros entre el mínimo del día −1.5 % y el máximo +1.5 %.

Son **operaciones**, no cotizaciones: Alpaca no guarda compra/venta histórica de opciones. Sirven para
explorar si el skew intradía revierte, no para medir una ganancia después de costos. Los datos quedan
fuera de Git (``data/``) y no se redistribuyen.

Uso, desde la raíz del repositorio::

    python experiments/exploracion-datos-gratis/descargar_0dte_alpaca.py --desde 2024-02-01 --hasta 2026-10-01
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from quantileflow.calendario import calendario  # noqa: E402

DATOS = "https://data.alpaca.markets"
MARGEN = 0.015
TROZO = 25  # contratos por solicitud
_ultima = [0.0]


def pedir(ruta, parametros):
    """GET con pausa mínima entre solicitudes (~3 por segundo) y reintentos ante 429, 5xx y errores de red."""
    cabeceras = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
                 "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
    url = f"{DATOS}{ruta}?{urllib.parse.urlencode(parametros)}"
    for intento in range(6):
        espera = 0.34 - (time.monotonic() - _ultima[0])
        if espera > 0:
            time.sleep(espera)
        _ultima[0] = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=cabeceras), timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2 ** intento)
    raise RuntimeError(f"sin respuesta tras 6 intentos: {ruta}")


def barras(ruta, simbolos, inicio, fin, **extra):
    """Todas las barras de 1 minuto de los símbolos, siguiendo la paginación."""
    salida, token = {}, None
    while True:
        p = {"symbols": ",".join(simbolos), "timeframe": "1Min", "start": inicio, "end": fin, "limit": 10000, **extra}
        if token:
            p["page_token"] = token
        d = pedir(ruta, p)
        for simbolo, filas in (d.get("bars") or {}).items():
            salida.setdefault(simbolo, []).extend(filas)
        token = d.get("next_page_token")
        if not token:
            return salida


def occ(fecha, derecho, strike):
    return f"SPY{fecha:%y%m%d}{derecho}{int(round(strike * 1000)):08d}"


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--desde", default="2024-02-01")
    a.add_argument("--hasta", required=True)
    a.add_argument("--salida", default=str(RAIZ / "data" / "exploracion" / "0dte"))
    args = a.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cal = calendario("XNYS")
    sesiones = cal.sessions_in_range(args.desde, args.hasta)
    diarias = barras("/v2/stocks/bars", ["SPY"], f"{args.desde}T00:00:00Z", f"{args.hasta}T23:59:59Z",
                     feed="sip", adjustment="raw", timeframe="1Day")["SPY"]
    rango = {b["t"][:10]: (b["l"], b["h"]) for b in diarias}
    hechas = 0
    for sesion in sesiones:
        fecha = sesion.date()
        destino = salida / f"{fecha}.json.gz"
        if destino.exists() or str(fecha) not in rango:
            continue
        apertura, cierre = cal.session_open(sesion), cal.session_close(sesion)
        inicio, fin = apertura.strftime("%Y-%m-%dT%H:%M:%SZ"), cierre.strftime("%Y-%m-%dT%H:%M:%SZ")
        bajo, alto = rango[str(fecha)]
        strikes = range(math.floor(bajo * (1 - MARGEN)), math.ceil(alto * (1 + MARGEN)) + 1)
        contratos = [occ(fecha, d, k) for k in strikes for d in ("P", "C")]
        spy = barras("/v2/stocks/bars", ["SPY"], inicio, fin, feed="sip", adjustment="raw").get("SPY", [])
        opciones = {}
        for i in range(0, len(contratos), TROZO):
            opciones.update(barras("/v1beta1/options/bars", contratos[i:i + TROZO], inicio, fin))
        registro = {"fecha": str(fecha), "apertura_utc": inicio, "cierre_utc": fin, "strikes": [strikes.start, strikes.stop - 1],
                    "spy": spy, "opciones": opciones}
        temporal = destino.with_suffix(".tmp")
        with gzip.open(temporal, "wt", encoding="utf-8") as f:
            json.dump(registro, f)
        temporal.replace(destino)
        hechas += 1
        if hechas % 20 == 0:
            print(f"{fecha}: {hechas} sesiones descargadas", flush=True)
    print(f"listo: {hechas} sesiones nuevas en {salida}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
