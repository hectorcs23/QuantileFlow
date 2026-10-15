"""Capturador prospectivo (Paso 2).

Captura lo que existia en cada momento, para los cuatro conjuntos que la
metodologia separa:

1. Indice que liquida -> no hay via verificada al BRTI en vivo. Se capturan sus
   dos observaciones indirectas: ``floor_strike`` (promedio de apertura) y, al
   liquidar, ``expiration_value`` (promedio de cierre).
2. BTC spot como variable explicativa -> Coinbase y Kraken.
3. Mercado de prediccion -> ficha del mercado y snapshot del libro, leidos como
   **par** y con marca temporal conjunta, porque a 15 minutos dos lecturas
   separadas por segundos ya discrepan.
4. Resultado oficial -> ``result`` y ``expiration_value`` del mercado liquidado.

El capturador respeta el limite de tasa, registra 429, huecos y latencias, y
nunca interpola. Si una lectura falla, se anota el fallo y se sigue: un hueco
registrado es un dato; un hueco rellenado es una fuga.
"""

from __future__ import annotations

import datetime as dt
import signal
from dataclasses import dataclass, field
from decimal import Decimal

from .almacen import Almacen
from .kalshi import ClienteKalshi, ErrorKalshi, ErrorTasa
from .libro import Libro
from .spot import Coinbase, ErrorSpot, Kraken
from .tiempo import Observacion, a_iso, ahora, desde_iso


@dataclass
class DiagnosticoCaptura:
    """Contadores de una sesion de captura, para el reporte de cobertura."""

    ciclos: int = 0
    pares_mercado_libro: int = 0
    fallos_kalshi: int = 0
    fallos_spot: int = 0
    discrepancias_libro: int = 0
    mercados_vistos: set[str] = field(default_factory=set)
    liquidaciones_capturadas: int = 0
    inicio: dt.datetime | None = None
    fin: dt.datetime | None = None

    def resumen(self) -> dict:
        return {
            "ciclos": self.ciclos,
            "pares_mercado_libro": self.pares_mercado_libro,
            "fallos_kalshi": self.fallos_kalshi,
            "fallos_spot": self.fallos_spot,
            "discrepancias_libro": self.discrepancias_libro,
            "mercados_distintos": len(self.mercados_vistos),
            "liquidaciones_capturadas": self.liquidaciones_capturadas,
            "inicio": a_iso(self.inicio) if self.inicio else None,
            "fin": a_iso(self.fin) if self.fin else None,
        }


@dataclass
class Capturador:
    """Bucle de captura para una serie.

    ``periodo_s`` es el intervalo objetivo entre ciclos. El limite de tasa del
    cliente puede alargarlo; eso se refleja en los huecos registrados en lugar de
    ocultarse.
    """

    almacen: Almacen
    cliente: ClienteKalshi
    serie: str = "KXBTC15M"
    periodo_s: float = 5.0
    capturar_spot: bool = True
    diagnostico: DiagnosticoCaptura = field(default_factory=DiagnosticoCaptura)
    _parar: bool = False

    def __post_init__(self) -> None:
        self.coinbase = Coinbase()
        self.kraken = Kraken()
        self._pendientes_liquidacion: set[str] = set()

    def instalar_senales(self) -> None:
        """Permite detener el bucle con Ctrl-C sin perder el manifiesto."""
        def manejar(_sig, _marco):
            self._parar = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, manejar)
            except (ValueError, OSError):
                pass

    # -- un ciclo -------------------------------------------------------

    def ciclo(self) -> None:
        """Una pasada: mercado abierto + libro + spot, y liquidaciones pendientes."""
        self.diagnostico.ciclos += 1

        try:
            mercados, _ = self.cliente.mercados(
                serie=self.serie, estado="open", limite=5
            )
        except ErrorTasa:
            self.diagnostico.fallos_kalshi += 1
            return
        except ErrorKalshi:
            self.diagnostico.fallos_kalshi += 1
            return

        for mercado in mercados:
            ticker = mercado.get("ticker")
            if not ticker:
                continue
            self.diagnostico.mercados_vistos.add(ticker)
            recibido = ahora()
            self.almacen.anadir(
                "mercado",
                Observacion(
                    event_time=self._event_time_mercado(mercado, recibido),
                    received_at=recibido,
                    fuente=f"kalshi:markets:{self.serie}",
                    payload=mercado,
                ),
                contrato=ticker,
                unidad="dolares",
            )

            try:
                observacion_libro = self.cliente.libro(ticker)
            except ErrorKalshi:
                self.diagnostico.fallos_kalshi += 1
                continue

            self.almacen.anadir(
                "libro",
                observacion_libro,
                contrato=ticker,
                unidad="dolares",
            )
            self.diagnostico.pares_mercado_libro += 1

            # Control de estructura: la derivacion complementaria debe cuadrar.
            # Una discrepancia aqui suele ser antiguedad entre las dos lecturas,
            # pero se cuenta siempre, porque tambien seria el sintoma de un
            # cambio de la plataforma.
            try:
                libro = Libro.desde_payload(
                    ticker,
                    observacion_libro.payload["cuerpo"],
                    observacion_libro.received_at,
                )
                if libro.verificar_contra_mercado(mercado):
                    self.diagnostico.discrepancias_libro += 1
            except Exception:  # noqa: BLE001 - el control no debe tumbar la captura
                self.diagnostico.discrepancias_libro += 1

        # Los mercados que dejaron de estar abiertos pasan a esperar su resultado.
        abiertos = {m.get("ticker") for m in mercados}
        nuevos_cerrados = {
            t for t in self.diagnostico.mercados_vistos if t not in abiertos
        }
        self._pendientes_liquidacion |= nuevos_cerrados

        if self.capturar_spot:
            self._capturar_spot()

        self._capturar_liquidaciones()

    def _event_time_mercado(self, mercado: dict, recibido: dt.datetime) -> dt.datetime:
        """``updated_time`` del mercado si existe; si no, el momento de recepcion."""
        crudo = mercado.get("updated_time")
        if crudo:
            try:
                return desde_iso(crudo, "updated_time")
            except Exception:  # noqa: BLE001
                return recibido
        return recibido

    def _capturar_spot(self) -> None:
        for fuente, nombre in ((self.coinbase, "coinbase"), (self.kraken, "kraken")):
            try:
                observacion = fuente.leer()
            except ErrorSpot:
                self.diagnostico.fallos_spot += 1
                continue
            self.almacen.anadir("spot", observacion, contrato="BTC-USD", unidad="usd")

    def _capturar_liquidaciones(self) -> None:
        """Busca el resultado oficial de los mercados ya cerrados.

        ``expiration_value`` es una observacion real del indice (el promedio de
        60 s), asi que cada liquidacion aporta un punto del BRTI que de otro modo
        no tendriamos.
        """
        if not self._pendientes_liquidacion:
            return
        for ticker in sorted(self._pendientes_liquidacion):
            try:
                mercado = self.cliente.mercado(ticker)
            except ErrorKalshi:
                self.diagnostico.fallos_kalshi += 1
                continue
            resultado = (mercado.get("result") or "").strip()
            if not resultado:
                continue  # aun sin liquidar; se vuelve a intentar en otro ciclo
            recibido = ahora()
            self.almacen.anadir(
                "resultado",
                Observacion(
                    event_time=self._event_time_mercado(mercado, recibido),
                    received_at=recibido,
                    fuente="kalshi:settlement",
                    payload=mercado,
                ),
                contrato=ticker,
                unidad="dolares",
            )
            self.diagnostico.liquidaciones_capturadas += 1
            self._pendientes_liquidacion.discard(ticker)

    # -- bucle ----------------------------------------------------------

    def correr(self, duracion_s: float | None = None, ciclos_max: int | None = None) -> dict:
        """Corre hasta agotar duracion o ciclos, o hasta recibir una senal."""
        import time

        self.instalar_senales()
        self.diagnostico.inicio = ahora()
        comienzo = time.monotonic()

        while not self._parar:
            if ciclos_max is not None and self.diagnostico.ciclos >= ciclos_max:
                break
            if duracion_s is not None and (time.monotonic() - comienzo) >= duracion_s:
                break
            inicio_ciclo = time.monotonic()
            self.ciclo()
            resto = self.periodo_s - (time.monotonic() - inicio_ciclo)
            if resto > 0 and not self._parar:
                time.sleep(resto)

        self.diagnostico.fin = ahora()
        extra = {
            "captura": self.diagnostico.resumen(),
            "cliente": self.cliente.diagnostico,
            "serie": self.serie,
            "periodo_s": self.periodo_s,
        }
        self.almacen.escribir_manifiesto(extra)
        return extra
