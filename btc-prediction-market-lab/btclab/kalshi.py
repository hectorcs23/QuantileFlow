"""Cliente REST publico de Kalshi con control de tasa y reintentos.

Solo endpoints publicos de lectura. El cliente no acepta ni almacena
credenciales: si en el futuro se necesita autenticacion, debe anadirse en un
modulo aparte para que quede explicito en el diff.

Comportamiento observado el 2026-10-15 desde este entorno (ver capabilities.md):
las lecturas sin autenticar devuelven ``429 too_many_requests`` con mucha
facilidad y sin cabecera ``Retry-After``, asi que el cliente aplica un cubo de
fichas conservador y retroceso exponencial con jitter.

Cada respuesta se devuelve envuelta con ``received_at`` y el payload original
intacto: el analisis posterior necesita saber cuando entro el dato, no solo lo
que decia.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator

from .tiempo import Observacion, ahora

BASE_PUBLICA = "https://api.elections.kalshi.com/trade-api/v2"

#: Coste en fichas de una lectura, segun la documentacion de limites de Kalshi
#: ("most requests cost the default of 10 tokens").
COSTE_LECTURA_FICHAS = 10

#: Presupuesto por segundo. La documentacion cita 200 fichas/s de lectura para
#: el nivel Basic autenticado; sin autenticar observamos 429 muy por debajo de
#: eso, asi que el valor por omision es deliberadamente bajo.
FICHAS_POR_SEGUNDO = 20.0


class ErrorKalshi(RuntimeError):
    """Fallo de transporte o respuesta no utilizable."""


class ErrorTasa(ErrorKalshi):
    """El exchange devolvio 429 tras agotar los reintentos."""


@dataclass
class CuboFichas:
    """Limitador de tasa por cubo de fichas.

    Mantiene el ritmo medio por debajo de ``fichas_por_segundo`` y permite una
    rafaga acotada por ``capacidad``.
    """

    fichas_por_segundo: float = FICHAS_POR_SEGUNDO
    capacidad: float = 40.0
    _disponibles: float = 0.0
    _ultimo: float = 0.0

    def __post_init__(self) -> None:
        if self.fichas_por_segundo <= 0:
            raise ValueError("fichas_por_segundo no positivo")
        self._disponibles = self.capacidad
        self._ultimo = time.monotonic()

    def consumir(self, fichas: int) -> float:
        """Espera lo necesario y consume. Devuelve los segundos esperados."""
        esperado = 0.0
        while True:
            instante = time.monotonic()
            self._disponibles = min(
                self.capacidad,
                self._disponibles + (instante - self._ultimo) * self.fichas_por_segundo,
            )
            self._ultimo = instante
            if self._disponibles >= fichas:
                self._disponibles -= fichas
                return esperado
            falta = (fichas - self._disponibles) / self.fichas_por_segundo
            time.sleep(falta)
            esperado += falta


@dataclass
class ClienteKalshi:
    """Lector de los endpoints publicos.

    ``reintentos`` cuenta los intentos adicionales tras el primero. El retroceso
    es exponencial con jitter porque el exchange no envia ``Retry-After``.
    """

    base: str = BASE_PUBLICA
    tiempo_espera_s: float = 20.0
    reintentos: int = 4
    espera_inicial_s: float = 1.0
    cubo: CuboFichas | None = None
    agente: str = "btc-prediction-market-lab/0.1 (investigacion)"

    def __post_init__(self) -> None:
        if self.cubo is None:
            self.cubo = CuboFichas()
        self.peticiones = 0
        self.respuestas_429 = 0
        self.segundos_esperando = 0.0

    # -- transporte -----------------------------------------------------

    def _url(self, ruta: str, parametros: dict[str, Any] | None) -> str:
        limpio = ruta.lstrip("/")
        if parametros:
            utiles = {k: v for k, v in parametros.items() if v is not None}
            if utiles:
                return f"{self.base}/{limpio}?{urllib.parse.urlencode(utiles)}"
        return f"{self.base}/{limpio}"

    def obtener(
        self, ruta: str, parametros: dict[str, Any] | None = None
    ) -> Observacion:
        """GET con control de tasa. Devuelve el payload con ``received_at``."""
        url = self._url(ruta, parametros)
        espera = self.espera_inicial_s
        ultimo_error: Exception | None = None

        for intento in range(self.reintentos + 1):
            self.segundos_esperando += self.cubo.consumir(COSTE_LECTURA_FICHAS)
            peticion = urllib.request.Request(
                url, headers={"User-Agent": self.agente, "Accept": "application/json"}
            )
            self.peticiones += 1
            try:
                with urllib.request.urlopen(
                    peticion, timeout=self.tiempo_espera_s
                ) as respuesta:
                    crudo = respuesta.read()
                    recibido = ahora()
                    payload = json.loads(crudo.decode("utf-8"))
                    return Observacion(
                        event_time=recibido,
                        received_at=recibido,
                        fuente=f"kalshi:{ruta}",
                        payload={"url": url, "cuerpo": payload},
                    )
            except urllib.error.HTTPError as exc:
                cuerpo = exc.read().decode("utf-8", errors="replace")[:300]
                ultimo_error = ErrorKalshi(f"HTTP {exc.code} en {url}: {cuerpo}")
                if exc.code == 429:
                    self.respuestas_429 += 1
                elif exc.code < 500:
                    # 4xx distinto de 429 no mejora reintentando.
                    raise ultimo_error from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                ultimo_error = ErrorKalshi(f"fallo en {url}: {exc}")

            if intento < self.reintentos:
                pausa = espera * (1.0 + random.random())
                time.sleep(pausa)
                self.segundos_esperando += pausa
                espera *= 2.0

        if self.respuestas_429:
            raise ErrorTasa(str(ultimo_error))
        raise ErrorKalshi(str(ultimo_error))

    def _cuerpo(self, ruta: str, parametros: dict[str, Any] | None = None) -> dict:
        return self.obtener(ruta, parametros).payload["cuerpo"]

    # -- endpoints ------------------------------------------------------

    def estado_exchange(self) -> dict:
        return self._cuerpo("exchange/status")

    def serie(self, serie: str) -> dict:
        """Metadatos de la serie, incluido ``fee_type`` y ``fee_multiplier``."""
        return self._cuerpo(f"series/{serie}")["series"]

    def mercados(
        self,
        serie: str | None = None,
        estado: str | None = None,
        limite: int = 100,
        cursor: str | None = None,
        evento: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """Una pagina de mercados y el cursor siguiente."""
        cuerpo = self._cuerpo(
            "markets",
            {
                "series_ticker": serie,
                "event_ticker": evento,
                "status": estado,
                "limit": limite,
                "cursor": cursor,
            },
        )
        return cuerpo.get("markets", []), (cuerpo.get("cursor") or None)

    def mercados_todos(
        self,
        serie: str | None = None,
        estado: str | None = None,
        limite: int = 200,
        paginas_max: int = 50,
    ) -> Iterator[dict]:
        """Recorre paginas hasta agotar el cursor o ``paginas_max``.

        El tope de paginas es deliberado: una serie de 15 minutos genera 96
        mercados al dia y un recorrido sin limite agota el presupuesto de tasa.
        """
        cursor = None
        for _ in range(paginas_max):
            pagina, cursor = self.mercados(
                serie=serie, estado=estado, limite=limite, cursor=cursor
            )
            yield from pagina
            if not cursor or not pagina:
                return

    def mercado(self, ticker: str) -> dict:
        return self._cuerpo(f"markets/{urllib.parse.quote(ticker)}")["market"]

    def libro(self, ticker: str) -> Observacion:
        """Snapshot del libro. Se devuelve envuelto por su ``received_at``.

        Kalshi publica el libro como dos listas de ordenes de compra, una por
        lado (``yes_dollars`` y ``no_dollars``). No hay lista de ventas: la mejor
        venta de un lado es el complemento de la mejor compra del otro. Esa
        traduccion vive en ``libro.py`` y no aqui, para que el payload crudo se
        conserve tal como llego.
        """
        return self.obtener(f"markets/{urllib.parse.quote(ticker)}/orderbook")

    def operaciones(
        self, ticker: str, limite: int = 100, cursor: str | None = None
    ) -> tuple[list[dict], str | None]:
        cuerpo = self._cuerpo(
            "markets/trades", {"ticker": ticker, "limit": limite, "cursor": cursor}
        )
        return cuerpo.get("trades", []), (cuerpo.get("cursor") or None)

    def velas(
        self, serie: str, ticker: str, desde_epoch: int, hasta_epoch: int,
        intervalo_min: int = 1,
    ) -> list[dict]:
        """Velas de 1 minuto con OHLC de ``yes_bid`` y ``yes_ask``.

        El endpoint acepta como maximo 5000 velas por peticion, de modo que el
        rango debe trocearse. Importante: una vela es un agregado del minuto, y
        usar el cierre de la vela en curso como si ya estuviera cerrada es una
        fuga temporal. ``union.py`` solo admite velas cerradas.
        """
        if hasta_epoch <= desde_epoch:
            raise ErrorKalshi("rango de velas vacio")
        cuerpo = self._cuerpo(
            f"series/{serie}/markets/{urllib.parse.quote(ticker)}/candlesticks",
            {
                "start_ts": desde_epoch,
                "end_ts": hasta_epoch,
                "period_interval": intervalo_min,
            },
        )
        return cuerpo.get("candlesticks", [])

    @property
    def diagnostico(self) -> dict:
        """Resumen de uso, para el reporte de cobertura."""
        return {
            "peticiones": self.peticiones,
            "respuestas_429": self.respuestas_429,
            "segundos_esperando": round(self.segundos_esperando, 3),
        }
