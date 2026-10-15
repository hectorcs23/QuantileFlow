"""Fuentes de BTC spot, como variables explicativas.

Importante: **ninguna de estas fuentes es el indice que liquida.** El contrato
liquida con el BRTI de CF Benchmarks y no tenemos via verificada a el. Lo que se
obtiene aqui son sustitutos, y la diferencia spot-indice es una variable del
modelo, no un detalle despreciable: medida el 2026-10-15, Coinbase marcaba
80795.14 mientras el promedio real del indice era 80833.68, unos 39 USD.

Binance devuelve 451 desde este entorno (restriccion geografica), asi que no se
usa.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .tiempo import Observacion, ahora, desde_epoch, desde_iso


class ErrorSpot(RuntimeError):
    """Fuente spot no disponible o respuesta ilegible."""


def _pedir(url: str, tiempo_espera_s: float, agente: str) -> tuple[dict | list, object]:
    peticion = urllib.request.Request(
        url, headers={"User-Agent": agente, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=tiempo_espera_s) as respuesta:
            crudo = respuesta.read()
            recibido = ahora()
            return json.loads(crudo.decode("utf-8")), recibido
    except urllib.error.HTTPError as exc:
        cuerpo = exc.read().decode("utf-8", errors="replace")[:200]
        raise ErrorSpot(f"HTTP {exc.code} en {url}: {cuerpo}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ErrorSpot(f"fallo en {url}: {exc}") from exc


@dataclass
class Coinbase:
    """Ticker de Coinbase Exchange. Trae bid, ask, ultimo y ``time``."""

    producto: str = "BTC-USD"
    tiempo_espera_s: float = 15.0
    agente: str = "btc-prediction-market-lab/0.1 (investigacion)"

    @property
    def url(self) -> str:
        return (
            "https://api.exchange.coinbase.com/products/"
            f"{urllib.parse.quote(self.producto)}/ticker"
        )

    def leer(self) -> Observacion:
        cuerpo, recibido = _pedir(self.url, self.tiempo_espera_s, self.agente)
        if not isinstance(cuerpo, dict) or "price" not in cuerpo:
            raise ErrorSpot(f"respuesta sin precio: {str(cuerpo)[:200]}")
        try:
            # La fuente declara su propio instante; se conserva como event_time
            # para poder medir la latencia real de la fuente.
            evento = desde_iso(cuerpo["time"], "coinbase.time")
        except Exception:
            evento = recibido
        return Observacion(
            event_time=evento,
            received_at=recibido,
            fuente="coinbase:ticker",
            payload={"url": self.url, "cuerpo": cuerpo},
        )

    @staticmethod
    def precio(observacion: Observacion) -> Decimal:
        try:
            return Decimal(str(observacion.payload["cuerpo"]["price"]))
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise ErrorSpot(f"precio ilegible: {exc}") from exc


@dataclass
class Kraken:
    """OHLC de 1 minuto de Kraken, como segunda fuente."""

    par: str = "XBTUSD"
    intervalo_min: int = 1
    tiempo_espera_s: float = 15.0
    agente: str = "btc-prediction-market-lab/0.1 (investigacion)"

    @property
    def url(self) -> str:
        return (
            "https://api.kraken.com/0/public/OHLC?"
            + urllib.parse.urlencode({"pair": self.par, "interval": self.intervalo_min})
        )

    def leer(self) -> Observacion:
        cuerpo, recibido = _pedir(self.url, self.tiempo_espera_s, self.agente)
        if not isinstance(cuerpo, dict):
            raise ErrorSpot("respuesta de Kraken no es un objeto")
        if cuerpo.get("error"):
            raise ErrorSpot(f"Kraken devolvio error: {cuerpo['error']}")
        resultado = cuerpo.get("result") or {}
        series = [v for k, v in resultado.items() if k != "last"]
        if not series or not series[0]:
            raise ErrorSpot("Kraken sin series")
        ultima = series[0][-1]
        try:
            evento = desde_epoch(ultima[0], "kraken.ohlc_ts")
        except Exception:
            evento = recibido
        return Observacion(
            event_time=evento,
            received_at=recibido,
            fuente="kraken:ohlc",
            payload={"url": self.url, "cuerpo": cuerpo},
        )
