"""Adaptador de Alpaca: captura en vivo, crudo inmutable y normalización al contrato.

Qué da Alpaca (comprobado el 26 de septiembre de 2026 con la cuenta *paper* del
entorno y la documentación oficial; detalle en ``docs/fuente_alpaca.md``):

* **Contratos** (Trading API, ``/v2/options/contracts``): símbolo OCC, raíz,
  subyacente, estilo (europeo o americano) y multiplicador. Con el subyacente
  ``SPX`` aparecen las raíces ``SPX`` (liquidación AM) y ``SPXW`` (PM).
* **Cotizaciones** (Market Data, ``/v1beta1/options/snapshots/{raíz}``): la
  última cotización de cada contrato, con bid, ask, tamaños, bolsas, condición y
  hora del evento en nanosegundos. La cadena se pide por **raíz** OSI (``SPXW``),
  no por el subyacente. No hay historia de cotizaciones de opciones (solo barras
  y operaciones desde febrero de 2024): la muestra se captura hacia adelante, a
  la hora de corte.
* **Feeds de opciones**: ``indicative`` (plan gratuito; según Alpaca, sus
  cotizaciones están *modificadas* y sus operaciones llegan con 15 minutos de
  retraso) u ``opra`` (BBO consolidado de OPRA; requiere suscripción). El feed
  queda en cada fila y no se mezcla en una serie sin declararlo.
* **Subyacente**: no hay nivel del índice SPX. SPY llega por IEX en tiempo real
  en el plan gratuito (``/v2/stocks/snapshots``). Para SPX se estima un
  subyacente implícito por paridad (``implicito.py``).
* **Histórico SIP** (``/v2/stocks/quotes``, ``feed=sip``): NBBO consolidado de
  todas las bolsas, con el bid y el ask de bolsas distintas y hora en
  nanosegundos. Sin suscripción solo se puede consultar una ventana que terminó
  hace al menos 15 minutos. Es el precio del **objetivo** (SPY) en cada corte:
  se descarga después y su disponibilidad fija la madurez de la etiqueta, sin
  entrar nunca en una medida del corte.
* **Eventos corporativos** (``/v1/corporate-actions``): dividendos en efectivo
  con fecha ex, registro y pago; el filtro de fechas es por ``process_date``
  (el pago) y un dividendo aparece desde que se anuncia. No trae la hora del
  anuncio.

Sellos de tiempo. ``sello_evento_utc`` es la hora de la cotización según
Alpaca, truncada a microsegundos. Una captura en vivo no trae hora de snapshot
del proveedor: ``sello_snapshot_utc``, ``disponible_utc`` y ``recibido_utc``
son la hora local de recepción de la respuesta, cota superior del instante del
snapshot. El reloj local se contrasta con el de Alpaca en cada corrida.

Crudo. El cuerpo de cada respuesta se guarda sin tocar, comprimido con gzip
(sin pérdida; los metadatos de contratos pesan varios MB al día) y direccionado
por el SHA-256 del archivo; el manifiesto de cada captura registra solicitud,
parámetros, estado, cabeceras, horas de envío y recepción y los hashes del
archivo y del contenido. Las credenciales viajan solo en
las cabeceras de la solicitud: nunca se escriben. La normalización lee
exclusivamente el crudo y sus manifiestos (y comprueba sus hashes), así que
reprocesarlos produce las mismas tablas.
"""
from __future__ import annotations

import datetime as dt
import gzip
import http.client
import json
import os
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import almacen, cadenas, contrato, implicito
from .calendario import CALENDARIO, _fecha, es_sesion, instante, instante_liquidacion, plazo_anios

PROVEEDOR = "alpaca"
VERSION_ADAPTADOR = "alpaca-0.1"
URL_DATOS = "https://data.alpaca.markets"
URL_TRADING = {True: "https://paper-api.alpaca.markets", False: "https://api.alpaca.markets"}
CABECERAS_GUARDADAS = ("date", "content-type", "x-ratelimit-limit", "x-ratelimit-remaining",
                       "x-ratelimit-reset", "x-request-id")
# Alpaca no publica la liquidación en el contrato. Índices: documentación de opciones sobre
# índices de Alpaca (SPX mensual AM; SPXW y XSP PM). Opciones sobre ETF: vencen al cierre de
# la sesión de vencimiento, que es el instante que usa el plazo.
LIQUIDACION = {"SPX": "AM", "SPXW": "PM", "XSP": "PM", "SPY": "PM"}
ESTILO = {"european": "europeo", "american": "americano"}
TIPO = {"call": "C", "put": "P"}
EXTRAS_COTIZACIONES = ["bolsa_bid", "bolsa_ask", "condicion", "captura"]
EXTRAS_SUBYACENTE = ["fuente_precio", "captura"]
EXTRAS_DIVIDENDOS = ["id_evento", "version", "origen", "fecha_registro", "fecha_proceso", "subtipo"]
# Anotaciones de la normalización de eventos que no son eventos por tratar: no detienen el piloto.
NO_BLOQUEAN = ("resolucion_sin_efecto", "omitido_tras_confirmar", "listado_tras_cancelar")
FEED_EVENTOS = "corporate_actions"
SUFIJO_DIARIO = ".diario.jsonl"
CODIGO_PLAZO_VENCIDO = 3
CODIGO_SIN_PREPARAR = 4
CODIGO_SIN_NORMALIZAR = 5  # las horas terminaron, pero falló la normalización del día (el crudo ya está)


class ErrorAlpaca(RuntimeError):
    """Respuesta no válida de Alpaca (estado distinto de 200 tras los reintentos)."""

    def __init__(self, estado, ruta, mensaje):
        super().__init__(f"{ruta}: HTTP {estado}: {mensaje}")
        self.estado = estado


@dataclass(frozen=True, repr=False)
class Credenciales:
    """Clave y secreto de la API. ``repr`` no los muestra: no deben llegar a registros ni manifiestos."""

    clave: str
    secreto: str
    paper: bool = True

    @classmethod
    def del_entorno(cls, entorno=None):
        entorno = os.environ if entorno is None else entorno
        clave, secreto = entorno.get("APCA_API_KEY_ID"), entorno.get("APCA_API_SECRET_KEY")
        if not clave or not secreto:
            raise RuntimeError("faltan APCA_API_KEY_ID o APCA_API_SECRET_KEY en el entorno")
        paper = entorno.get("ALPACA_PAPER", "true").strip().lower() not in ("false", "0", "no")
        return cls(clave, secreto, paper)

    def __repr__(self):
        return f"Credenciales(cuenta={'paper' if self.paper else 'live'})"


@dataclass(frozen=True, eq=False)
class Respuesta:
    """Una respuesta HTTP 200 tal como llegó, con sus horas de envío y recepción (UTC)."""

    servicio: str  # "datos" (Market Data) o "trading" (Trading API)
    ruta: str
    params: tuple  # pares (clave, valor) ordenados; sin credenciales
    estado: int
    cabeceras: dict
    cuerpo: bytes
    enviado_utc: pd.Timestamp
    recibido_utc: pd.Timestamp
    intentos: int = 1

    def json(self):
        return json.loads(self.cuerpo)


def _transporte_urllib(url, cabeceras, tiempo_max):
    """GET con urllib: respeta ``HTTPS_PROXY`` y el almacén de certificados del sistema."""
    solicitud = urllib.request.Request(url, headers=cabeceras, method="GET")
    try:
        with urllib.request.urlopen(solicitud, timeout=tiempo_max) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in (error.headers or {}).items()}, error.read()


def _ahora():
    return pd.Timestamp.now(tz="UTC")


def iso(instante) -> str | None:
    """Instante UTC en ISO 8601 con microsegundos y ``Z``."""
    if instante is None or pd.isna(instante):
        return None
    return pd.Timestamp(instante).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ClienteAlpaca:
    """Cliente mínimo de las APIs de Alpaca con reintentos ante 429, 5xx y errores de red.

    ``transporte(url, cabeceras, tiempo_max) -> (estado, cabeceras, cuerpo)``,
    ``reloj()`` y ``dormir(s)`` se pueden sustituir (pruebas sin red).
    """

    def __init__(self, credenciales: Credenciales, transporte=None, reloj=None, dormir=time.sleep,
                 reintentos=3, espera_base=0.5, espera_max=20.0, tiempo_max=30.0):
        self.credenciales = credenciales
        self.transporte = transporte or _transporte_urllib
        self.reloj = reloj or _ahora
        self.dormir = dormir
        self.reintentos = int(reintentos)
        self.espera_base = float(espera_base)
        self.espera_max = float(espera_max)
        self.tiempo_max = float(tiempo_max)

    @property
    def cuenta(self):
        return "paper" if self.credenciales.paper else "live"

    def _base(self, servicio):
        if servicio == "datos":
            return URL_DATOS
        if servicio == "trading":
            return URL_TRADING[self.credenciales.paper]
        raise ValueError(f"servicio desconocido: {servicio!r}")

    def _espera(self, intento, estado, cabeceras):
        espera = self.espera_base * 2 ** (intento - 1)
        if estado == 429 and "x-ratelimit-reset" in cabeceras:
            try:
                espera = max(float(cabeceras["x-ratelimit-reset"]) - time.time(), self.espera_base)
            except ValueError:
                pass
        return min(espera, self.espera_max)

    def get(self, servicio, ruta, params=()) -> Respuesta:
        pares = tuple(sorted((str(k), str(v)) for k, v in dict(params).items() if v is not None))
        url = self._base(servicio) + ruta + ("?" + urllib.parse.urlencode(pares) if pares else "")
        cabeceras = {"APCA-API-KEY-ID": self.credenciales.clave,
                     "APCA-API-SECRET-KEY": self.credenciales.secreto,
                     "Accept": "application/json", "User-Agent": f"quantileflow/{VERSION_ADAPTADOR}"}
        estado, ultimo = 0, ""
        for intento in range(1, self.reintentos + 2):
            enviado = self.reloj()
            cab = {}
            try:
                estado, cab, cuerpo = self.transporte(url, cabeceras, self.tiempo_max)
            except (OSError, http.client.HTTPException) as error:  # red, proxy, tiempo agotado o lectura cortada
                estado, ultimo = 0, f"error de red: {error!r}"
            else:
                recibido = self.reloj()
                if estado == 200:
                    guardadas = {k: cab[k] for k in CABECERAS_GUARDADAS if k in cab}
                    return Respuesta(servicio, ruta, pares, estado, guardadas, cuerpo, enviado, recibido, intento)
                ultimo = cuerpo[:300].decode("utf-8", "replace")
                if estado != 429 and estado < 500:
                    raise ErrorAlpaca(estado, ruta, ultimo)
            if intento <= self.reintentos:
                self.dormir(self._espera(intento, estado, cab))
        raise ErrorAlpaca(estado, ruta, f"sin respuesta válida tras {self.reintentos + 1} intentos: {ultimo}")

    def paginas(self, servicio, ruta, params=(), maximo=200, al_recibir=None, hasta=None) -> list[Respuesta]:
        """Todas las páginas de una consulta (``next_page_token``), cada una como respuesta propia.

        ``al_recibir(respuesta, numero)`` se llama en cuanto llega cada página:
        así una página ya recibida no se pierde si falla la siguiente. Con
        ``hasta``, se detiene tras esa cantidad de páginas aunque haya más.
        """
        respuestas, token = [], None
        while True:
            p = dict(params)
            if token:
                p["page_token"] = token
            respuesta = self.get(servicio, ruta, p)
            respuestas.append(respuesta)
            if al_recibir is not None:
                al_recibir(respuesta, len(respuestas))
            if hasta is not None and len(respuestas) >= hasta:
                return respuestas
            cuerpo = respuesta.json()
            token = cuerpo.get("next_page_token") if isinstance(cuerpo, dict) else None
            if not token:
                return respuestas
            if len(respuestas) >= maximo:
                raise ErrorAlpaca(200, ruta, f"más de {maximo} páginas")


# ---------------------------------------------------------------------------
# Solicitudes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Solicitud:
    """Consulta declarada: su ``nombre`` identifica el crudo; ``tipo`` decide cómo se normaliza."""

    nombre: str
    tipo: str  # "reloj", "contratos", "cadena", "acciones", "historico" o "eventos"
    servicio: str
    ruta: str
    params: tuple = ()
    paginas_max: int | None = None  # None: todas las páginas


def _solicitud(nombre, tipo, servicio, ruta, paginas_max=None, **params):
    return Solicitud(nombre, tipo, servicio, ruta,
                     tuple(sorted((k, str(v)) for k, v in params.items() if v is not None)), paginas_max)


def pedir_reloj() -> Solicitud:
    """Hora del servidor (nanosegundos) y estado del mercado."""
    return _solicitud("reloj", "reloj", "trading", "/v2/clock")


def pedir_contratos(subyacente, desde, hasta, raiz=None) -> Solicitud:
    """Contratos activos de ``subyacente`` (``SPX`` incluye SPX y SPXW) que vencen entre dos fechas."""
    nombre = f"contratos_{subyacente}" + (f"_{raiz}" if raiz else "")
    return _solicitud(nombre, "contratos", "trading", "/v2/options/contracts", underlying_symbols=subyacente,
                      root_symbol=raiz, expiration_date_gte=str(_fecha(desde)),
                      expiration_date_lte=str(_fecha(hasta)), limit=10000)


def pedir_cadena(raiz, vencimiento, feed) -> Solicitud:
    """Última cotización de todos los contratos de una raíz y un vencimiento."""
    vencimiento = _fecha(vencimiento)
    return _solicitud(f"cadena_{raiz}_{vencimiento}", "cadena", "datos", f"/v1beta1/options/snapshots/{raiz}",
                      feed=feed, expiration_date=str(vencimiento), limit=1000)


def pedir_acciones(simbolos, feed) -> Solicitud:
    """Snapshot de acciones o ETF: última cotización, última operación y barras."""
    return _solicitud(f"acciones_{'-'.join(simbolos)}", "acciones", "datos", "/v2/stocks/snapshots",
                      symbols=",".join(simbolos), feed=feed)


def pedir_historico(simbolos, feed, corte_utc, ventana_s, limite) -> Solicitud:
    """Las ``limite`` cotizaciones más recientes con evento en ``[corte - ventana, corte]`` (extremos incluidos).

    Una sola página en orden descendente: basta para encontrar la última
    cotización válida y no descarga toda la ventana (SPY cotiza cientos de veces
    por segundo).
    """
    corte = pd.Timestamp(corte_utc)
    return _solicitud(f"historico_{'-'.join(simbolos)}", "historico", "datos", "/v2/stocks/quotes", paginas_max=1,
                      symbols=",".join(simbolos), feed=feed, start=iso(corte - pd.Timedelta(seconds=float(ventana_s))),
                      end=iso(corte), sort="desc", limit=int(limite))


def pedir_eventos(simbolos, desde, hasta) -> Solicitud:
    """Eventos corporativos de todos los tipos con ``process_date`` entre dos fechas (incluidas)."""
    return _solicitud(f"eventos_{'-'.join(simbolos)}", "eventos", "datos", "/v1/corporate-actions",
                      symbols=",".join(simbolos), start=str(_fecha(desde)), end=str(_fecha(hasta)), limit=1000)


def ejecutar(cliente: ClienteAlpaca, solicitudes, hilos=8, registro=None):
    """Ejecuta las solicitudes en paralelo; con ``registro``, guarda cada página en cuanto llega.

    Devuelve las respuestas recibidas por nombre (también las de una consulta
    interrumpida) y los errores por nombre.
    """
    nombres = [s.nombre for s in solicitudes]
    if len(set(nombres)) != len(nombres):
        raise ValueError("nombres de solicitud repetidos")

    def una(solicitud):
        recibidas = []

        def al_recibir(respuesta, numero):
            recibidas.append(respuesta)
            if registro is not None:
                registro.pagina(solicitud, respuesta, numero)

        if registro is not None:
            registro.iniciar(solicitud)
        try:
            cliente.paginas(solicitud.servicio, solicitud.ruta, solicitud.params, al_recibir=al_recibir,
                            hasta=solicitud.paginas_max)
        except (ErrorAlpaca, OSError, ValueError, http.client.HTTPException) as error:
            texto = (f"{error} ({len(recibidas)} páginas recibidas antes del fallo; el total es desconocido: "
                     "la paginación es por cursor)")
            if registro is not None:
                registro.terminar(solicitud, texto)
            return recibidas, texto
        if registro is not None:
            registro.terminar(solicitud)
        return recibidas, None

    with ThreadPoolExecutor(max_workers=max(1, int(hilos))) as grupo:
        futuros = {s.nombre: grupo.submit(una, s) for s in solicitudes}
    resultados, errores = {}, {}
    for nombre, futuro in futuros.items():
        recibidas, error = futuro.result()
        if recibidas:
            resultados[nombre] = recibidas
        if error:
            errores[nombre] = error
    return resultados, errores


# ---------------------------------------------------------------------------
# Crudo y manifiestos
# ---------------------------------------------------------------------------


def directorio_crudo(raiz_datos) -> Path:
    return Path(raiz_datos) / "raw" / "alpaca"


def guardar_pagina(respuesta: Respuesta, nombre, numero, raiz_datos) -> dict:
    """Guarda una página como crudo inmutable (gzip) y devuelve su entrada de manifiesto.

    ``sha256`` identifica el archivo guardado y ``sha256_contenido`` el cuerpo
    original: la lectura comprueba los dos.
    """
    raiz_datos = Path(raiz_datos)
    r = respuesta
    comprimido = gzip.compress(r.cuerpo, compresslevel=9, mtime=0)
    info = almacen.guardar_crudo_bytes(comprimido, f"{nombre}_p{numero}.json.gz", directorio_crudo(raiz_datos))
    return {"servicio": r.servicio, "ruta": r.ruta, "params": dict(r.params), "pagina": numero,
            "estado": r.estado, "cabeceras": r.cabeceras, "enviado_utc": iso(r.enviado_utc),
            "recibido_utc": iso(r.recibido_utc), "intentos": r.intentos,
            "archivo": Path(info["ruta"]).relative_to(raiz_datos).as_posix(), "sha256": info["sha256"],
            "bytes": info["bytes"], "sha256_contenido": almacen.sha256_bytes(r.cuerpo),
            "bytes_contenido": len(r.cuerpo)}


class Diario:
    """Diario de una captura: una línea JSON por evento, sincronizada en disco al escribirla.

    Se crea de forma atómica con su línea de inicio, que trae lo necesario para
    rehacer el manifiesto; después registra cada solicitud, cada página ya
    guardada en el crudo y cada fin. Si el proceso muere, ``recuperar`` lo
    convierte en el manifiesto de lo que llegó. Nunca continúa un diario
    existente.
    """

    def __init__(self, ruta, inicio: dict):
        self.ruta = Path(ruta)
        almacen.crear_nuevo(self.ruta, _linea(inicio), solo_lectura=False)
        self._archivo = open(self.ruta, "ab")

    def escribir(self, evento: dict):
        self._archivo.write(_linea(evento))
        self._archivo.flush()
        os.fsync(self._archivo.fileno())

    def cerrar(self):
        if not self._archivo.closed:
            self._archivo.close()
            os.chmod(self.ruta, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def _linea(evento: dict) -> bytes:
    return (json.dumps(evento, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def leer_diario(ruta):
    """Eventos de un diario y si su última línea quedó truncada (se descarta; en otra línea es un error)."""
    lineas = Path(ruta).read_bytes().split(b"\n")
    if lineas and lineas[-1] == b"":
        lineas.pop()
    eventos, truncada = [], False
    for i, linea in enumerate(lineas):
        try:
            eventos.append(json.loads(linea.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if i != len(lineas) - 1:
                raise ValueError(f"{ruta}: línea {i + 1} ilegible en medio del diario") from None
            truncada = True
    return eventos, truncada


class Registro:
    """Entradas de manifiesto que se escriben a medida que llegan las páginas (seguro entre hilos).

    Cada solicitud termina ``completa``, ``parcial`` (algunas páginas y un
    fallo) o ``fallida`` (ninguna página), con la causa del fallo. Con
    ``diario``, cada paso queda además en disco en cuanto ocurre; tras
    ``interrumpir`` ya no se anota nada.
    """

    def __init__(self, raiz_datos, diario: Diario | None = None):
        self.raiz_datos = Path(raiz_datos)
        self.entradas = {}
        self.diario = diario
        self.interrumpido = False
        self._candado = threading.Lock()

    def _anotar(self, evento):
        if self.diario is not None and not self.interrumpido:
            self.diario.escribir(evento)

    def iniciar(self, solicitud):
        with self._candado:
            self.entradas[solicitud.nombre] = {"tipo": solicitud.tipo, "ruta": solicitud.ruta,
                                               "params": dict(solicitud.params), "estado": "en curso",
                                               "paginas": [], "error": None}
            self._anotar({"evento": "solicitud", "nombre": solicitud.nombre, "tipo": solicitud.tipo,
                          "ruta": solicitud.ruta, "params": dict(solicitud.params)})

    def pagina(self, solicitud, respuesta, numero):
        entrada = guardar_pagina(respuesta, solicitud.nombre, numero, self.raiz_datos)
        with self._candado:
            self.entradas[solicitud.nombre]["paginas"].append(entrada)
            self._anotar({"evento": "pagina", "nombre": solicitud.nombre, "entrada": entrada})

    def terminar(self, solicitud, error=None):
        with self._candado:
            e = self.entradas[solicitud.nombre]
            if error is None:
                e["estado"] = "completa"
            else:
                e["estado"], e["error"] = ("parcial" if e["paginas"] else "fallida"), str(error)
            self._anotar({"evento": "fin", "nombre": solicitud.nombre, "estado": e["estado"], "error": e["error"]})

    def interrumpir(self, motivo, instante=None):
        """Anota la interrupción (p. ej., plazo vencido) y deja de anotar: el proceso va a terminar."""
        with self._candado:
            self._anotar({"evento": "interrumpida", "motivo": motivo, "utc": iso(instante)})
            self.interrumpido = True


def guardar_respuestas(resultados, tipos, raiz_datos) -> dict:
    """Guarda respuestas completas ya recibidas; devuelve las entradas del manifiesto por solicitud."""
    return {nombre: {"tipo": tipos[nombre], "estado": "completa", "error": None,
                     "paginas": [guardar_pagina(r, nombre, i, raiz_datos)
                                 for i, r in enumerate(resultados[nombre], start=1)]}
            for nombre in sorted(resultados)}


def reloj_servidor(respuesta: Respuesta) -> dict:
    """Desfase del reloj local frente al de Alpaca (positivo: el servidor va adelantado)."""
    d = respuesta.json()
    servidor = pd.Timestamp(d["timestamp"]).tz_convert("UTC")
    medio = respuesta.enviado_utc + (respuesta.recibido_utc - respuesta.enviado_utc) / 2
    return {"servidor_utc": iso(servidor), "local_medio_utc": iso(medio),
            "desfase_s": round((servidor - medio).total_seconds(), 6),
            "incertidumbre_s": round((respuesta.recibido_utc - respuesta.enviado_utc).total_seconds() / 2, 6),
            "mercado_abierto": bool(d.get("is_open")), "proxima_apertura": d.get("next_open"),
            "proximo_cierre": d.get("next_close")}


def ruta_manifiesto(raiz_datos, fecha, etiqueta, carpeta="capturas") -> Path:
    """``capturas`` (en vivo), ``historico`` (SIP de cada corte) o ``eventos`` (eventos corporativos)."""
    return directorio_crudo(raiz_datos) / carpeta / str(fecha) / f"{etiqueta}.json"


def escribir_manifiesto(manifiesto: dict, raiz_datos, carpeta="capturas") -> Path:
    """Escribe un manifiesto en solo lectura; nunca sobrescribe uno existente."""
    ruta = ruta_manifiesto(raiz_datos, manifiesto["fecha"], manifiesto["etiqueta"], carpeta)
    if ruta.exists():
        raise FileExistsError(f"{ruta} ya existe: un manifiesto no se sobrescribe")
    almacen.escribir_json_nuevo(manifiesto, ruta)  # atómico: completo o ausente, en solo lectura
    return ruta


def ruta_diario(raiz_datos, fecha, etiqueta) -> Path:
    return directorio_crudo(raiz_datos) / "capturas" / str(fecha) / f"{etiqueta}{SUFIJO_DIARIO}"


def etiqueta_libre(raiz_datos, fecha, base, carpeta="capturas") -> str:
    """``base``, ``base-2``, ``base-3``... la primera sin manifiesto ni diario."""
    n = 1
    while True:
        etiqueta = base if n == 1 else f"{base}-{n}"
        if (not ruta_manifiesto(raiz_datos, fecha, etiqueta, carpeta).exists()
                and not ruta_diario(raiz_datos, fecha, etiqueta).exists()):
            return etiqueta
        n += 1


def estado_captura(entradas: dict, tardias, modo=None) -> str:
    """``completa``, ``parcial`` o ``fallida`` según las solicitudes propias de la captura.

    Es completa si todas sus solicitudes terminaron completas y, salvo en una
    captura inmediata, ninguna respuesta llegó después del corte. Es fallida si
    ninguna cadena tiene una página recibida a tiempo.
    """
    propias = {n: e for n, e in entradas.items() if e["tipo"] in ("cadena", "acciones")}
    tardias = set(tardias) if modo != "inmediata" else set()
    utiles = [e for e in propias.values() if e["tipo"] == "cadena"] or list(propias.values())
    if not any(p["archivo"] not in tardias for e in utiles for p in e["paginas"]):
        return "fallida"
    if not tardias and all(e.get("estado", "completa") == "completa" for e in propias.values()):
        return "completa"
    return "parcial"


def estado_manifiesto(manifiesto: dict) -> str:
    """Estado de una captura guardada; los manifiestos sin estado (versión 0.1) se evalúan de nuevo."""
    if "estado" in manifiesto:
        return manifiesto["estado"]
    estado = estado_captura(manifiesto["solicitudes"], manifiesto.get("respuestas_despues_del_corte", []),
                            manifiesto.get("modo"))
    return "parcial" if estado == "completa" and manifiesto.get("errores") else estado


def _manifiesto_captura(base: dict, entradas: dict, errores: dict, fin_utc) -> dict:
    corte = pd.Timestamp(base["corte_utc"])
    tardias = [p["archivo"] for e in entradas.values() if e["tipo"] in ("cadena", "acciones")
               for p in e["paginas"] if pd.Timestamp(p["recibido_utc"]) > corte]
    return {**base, "fin_utc": iso(fin_utc), "solicitudes": entradas, "errores": errores,
            "respuestas_despues_del_corte": tardias, "estado": estado_captura(entradas, tardias, base.get("modo"))}


def capturar(cliente: ClienteAlpaca, solicitudes, raiz_datos, meta: dict, previas=None, hilos=8, vigilante=None):
    """Ejecuta una captura, guarda crudo, diario y manifiesto y devuelve ``(manifiesto, ruta)``.

    ``meta`` trae al menos ``fecha`` (sesión), ``hora``, ``corte_utc`` y
    ``etiqueta``; ``previas`` son entradas ya guardadas (p. ej., los contratos
    del día) que se incluyen para que el manifiesto se normalice por sí solo.
    Cada página se guarda en cuanto llega y queda en el diario
    (``<etiqueta>.diario.jsonl``); el manifiesto final, atómico, registra el
    estado de cada solicitud y el de la captura. ``vigilante`` (``Vigilante``)
    anota en el diario la interrupción si vence el plazo absoluto.
    """
    if ruta_manifiesto(raiz_datos, meta["fecha"], meta["etiqueta"]).exists():
        raise FileExistsError(f"{meta['etiqueta']}: ya hay un manifiesto; una captura no se sobrescribe")
    inicio = cliente.reloj()
    base = {"proveedor": PROVEEDOR, "version_adaptador": VERSION_ADAPTADOR, "cuenta": cliente.cuenta, **meta,
            "inicio_utc": iso(inicio)}
    diario = Diario(ruta_diario(raiz_datos, meta["fecha"], meta["etiqueta"]),
                    {"evento": "inicio", "manifiesto": base, "previas": previas or {}})
    registro = Registro(raiz_datos, diario)
    if vigilante is not None:
        vigilante.vigilar(registro)
    try:
        _, errores = ejecutar(cliente, solicitudes, hilos, registro)
    finally:
        if vigilante is not None:
            vigilante.vigilar(None)
    entradas = dict(previas or {})
    entradas.update(registro.entradas)
    manifiesto = _manifiesto_captura(base, entradas, errores, cliente.reloj())
    ruta = escribir_manifiesto(manifiesto, raiz_datos)
    diario.escribir({"evento": "manifiesto", "estado": manifiesto["estado"]})
    diario.cerrar()
    return manifiesto, ruta


def recuperar(raiz_datos, ahora_utc=None, fecha=None) -> list[dict]:
    """Convierte cada diario sin manifiesto en el manifiesto de lo que llegó, marcado como interrumpido.

    Una solicitud sin fin en el diario queda ``parcial`` (con páginas) o
    ``fallida``, y la captura toma el estado de ``estado_captura``: la que se
    cortó a mitad nunca queda ``completa``. Comprueba el hash de cada página y
    registra el hash del diario. Devuelve los manifiestos escritos.
    """
    base_capturas = directorio_crudo(raiz_datos) / "capturas"
    escritos = []
    for ruta in sorted(base_capturas.glob(f"{fecha or '*'}/*{SUFIJO_DIARIO}")):
        etiqueta = ruta.name[:-len(SUFIJO_DIARIO)]
        if (ruta.parent / f"{etiqueta}.json").exists():
            continue
        eventos, truncada = leer_diario(ruta)
        if not eventos or eventos[0].get("evento") != "inicio":
            raise ValueError(f"{ruta}: diario sin línea de inicio")
        base, previas = eventos[0]["manifiesto"], eventos[0].get("previas") or {}
        entradas, motivo = {}, None
        for ev in eventos[1:]:
            if ev["evento"] == "solicitud":
                entradas[ev["nombre"]] = {"tipo": ev["tipo"], "ruta": ev.get("ruta"), "params": ev.get("params", {}),
                                          "estado": "en curso", "paginas": [], "error": None}
            elif ev["evento"] == "pagina":
                entradas[ev["nombre"]]["paginas"].append(ev["entrada"])
            elif ev["evento"] == "fin":
                entradas[ev["nombre"]].update(estado=ev["estado"], error=ev["error"])
            elif ev["evento"] == "interrumpida":
                motivo = ev["motivo"]
        for e in entradas.values():
            if e["estado"] == "en curso":
                e.update(estado="parcial" if e["paginas"] else "fallida",
                         error="interrumpida: el diario no registra el fin de la solicitud")
            for p in e["paginas"]:
                archivo = Path(raiz_datos) / p["archivo"]
                if not archivo.exists() or almacen.sha256_archivo(archivo) != p["sha256"]:
                    raise RuntimeError(f"{ruta}: la página {p['archivo']} falta o no coincide con su hash")
        errores = {n: e["error"] for n, e in entradas.items() if e["estado"] != "completa"}
        manifiesto = _manifiesto_captura(base, {**previas, **entradas}, errores, None)
        if manifiesto["estado"] == "completa":  # todo llegó, pero la ejecución no terminó: no se da por buena
            manifiesto["estado"] = "parcial"
        manifiesto.update(interrumpida=True, recuperada_utc=iso(ahora_utc or _ahora()),
                          motivo_interrupcion=motivo or "el proceso terminó sin escribir el manifiesto",
                          diario={"archivo": ruta.relative_to(Path(raiz_datos)).as_posix(),
                                  "sha256": almacen.sha256_archivo(ruta), "ultima_linea_truncada": truncada})
        escribir_manifiesto(manifiesto, raiz_datos)
        if os.access(ruta, os.W_OK):
            os.chmod(ruta, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        escritos.append(manifiesto)
    return escritos


class Vigilante:
    """Plazo de una ejecución: al vencer, deja constancia y termina el proceso.

    Anota la interrupción en el diario de la captura en curso, llama a
    ``al_vencer(motivo)`` (p. ej., para escribir el registro de la ejecución) y
    termina de inmediato (``os._exit`` con ``codigo``), aunque una solicitud
    siga colgada. Lo que llegó ya está en el crudo y en el diario; ``recuperar``
    lo convierte después en su manifiesto. Hay dos usos: el plazo absoluto
    después del corte (``CODIGO_PLAZO_VENCIDO``) y el de preparación antes del
    corte (``CODIGO_SIN_PREPARAR``), que libera a tiempo al respaldo de esa hora.
    """

    def __init__(self, plazo_utc, reloj=None, salir=None, codigo=CODIGO_PLAZO_VENCIDO,
                 motivo="plazo absoluto vencido", al_vencer=None):
        self.plazo_utc = pd.Timestamp(plazo_utc)
        self.codigo, self.motivo = codigo, motivo
        self._salir = salir or os._exit
        self._al_vencer = al_vencer
        self._registro = None
        self._cancelado = False
        self._candado = threading.Lock()
        segundos = max((self.plazo_utc - (reloj or _ahora)()).total_seconds(), 0.0)
        self._temporizador = threading.Timer(segundos, self._vencer)
        self._temporizador.daemon = True
        self._temporizador.start()

    def vigilar(self, registro):
        with self._candado:
            self._registro = registro

    def cancelar(self):
        with self._candado:
            self._cancelado = True
            self._temporizador.cancel()

    def _vencer(self):
        with self._candado:
            if self._cancelado:
                return
            texto = f"{self.motivo} ({iso(self.plazo_utc)})"
            if self._registro is not None:
                self._registro.interrumpir(texto, _ahora())
            if self._al_vencer is not None:
                try:
                    self._al_vencer(texto)
                except Exception as error:  # registrar es lo secundario: el proceso termina igual
                    print(f"no se pudo registrar la interrupción: {error!r}", file=sys.stderr, flush=True)
            print(f"{texto}: se termina el proceso", file=sys.stderr, flush=True)
            self._salir(self.codigo)


def plazo_preparacion(primer_corte_utc, ahora_utc, preparacion_s, minima_s, adelanto_s, programada=True):
    """Hasta cuándo debe quedar lista (contratos y vencimientos) una captura antes de esperar el corte.

    Por omisión, ``preparacion_s`` antes del primer corte, para que un titular
    colgado termine a tiempo de que el respaldo de esa hora arranque y llegue.
    Una ejecución que arranca tarde (el respaldo) tiene al menos ``minima_s``,
    pero nunca más allá del inicio de la ráfaga (``adelanto_s`` antes del
    corte). Una captura inmediata tiene ``minima_s`` desde ahora.
    """
    ahora = pd.Timestamp(ahora_utc)
    minima = ahora + pd.Timedelta(seconds=float(minima_s))
    if not programada:
        return minima
    corte = pd.Timestamp(primer_corte_utc)
    return min(max(corte - pd.Timedelta(seconds=float(preparacion_s)), minima),
               corte - pd.Timedelta(seconds=float(adelanto_s)))


def planificar(raiz_datos, fecha, horas, ahora_utc, adelanto_s, codigo=CALENDARIO) -> list[dict]:
    """Qué hacer con cada hora de una sesión según las capturas guardadas y la hora actual.

    ``completa``: ya hay una captura completa y se omite. ``parcial`` o
    ``fallida``: la captura de esa hora tuvo problemas y el corte ya pasó; el
    fallo se conserva y no se reemplaza con datos posteriores. ``perdida``: sin
    captura y con el corte pasado. ``pendiente``: se capturará.
    """
    previas = {}
    for m in leer_manifiestos(raiz_datos, fecha, fecha):
        previas.setdefault(m["hora"], []).append(estado_manifiesto(m))
    plan = []
    for hora in horas:
        corte = instante(fecha, hora, codigo)
        estados = previas.get(hora, [])
        paso = {"hora": hora, "corte_utc": corte, "capturas_previas": estados,
                "etiqueta": etiqueta_libre(raiz_datos, _fecha(fecha), f"{_fecha(fecha)}T{hora.replace(':', '')}")}
        if "completa" in estados:
            paso.update(estado="completa", accion="omitir")
        elif corte - pd.Timedelta(seconds=float(adelanto_s)) < pd.Timestamp(ahora_utc):
            paso.update(estado="parcial" if "parcial" in estados else ("fallida" if estados else "perdida"),
                        accion="omitir")
        else:
            paso.update(estado="pendiente", accion="capturar")
        plan.append(paso)
    return plan


def codigo_salida(plan) -> int:
    """0 solo si todas las horas quedaron completas: la existencia de un archivo no es un éxito."""
    return 0 if plan and all(p["estado"] == "completa" for p in plan) else 1


def escribir_ejecucion(registro: dict, raiz_datos, sufijo="") -> Path:
    """Registro de una ejecución de un script (disparo, horas planificadas y su estado), en solo lectura."""
    ruta = (directorio_crudo(raiz_datos) / "ejecuciones" / registro["fecha"]
            / f"{pd.Timestamp(registro['inicio_utc']):%Y%m%dT%H%M%S%fZ}{sufijo}.json")
    almacen.escribir_json_nuevo(registro, ruta)
    return ruta


# ---------------------------------------------------------------------------
# Histórico SIP del objetivo y eventos corporativos
# ---------------------------------------------------------------------------


def planificar_historico(raiz_datos, fecha, horas, ahora_utc, retraso_s, margen_s, codigo=CALENDARIO) -> list[dict]:
    """Qué descargar del histórico de una sesión según lo ya descargado y la hora actual.

    ``completa``: ya hay una descarga completa y se omite. Si no, la ventana del
    corte se puede consultar desde ``corte + retraso_s`` (SIP sin suscripción:
    900 s); con ``margen_s`` más, la acción es ``descargar`` y antes,
    ``esperar``. A diferencia de la captura en vivo, un intento fallido se
    repite: el dato histórico no cambia.
    """
    previas = {}
    for m in leer_manifiestos(raiz_datos, fecha, fecha, "historico"):
        previas.setdefault(m["hora"], []).append(m["estado"])
    plan = []
    for hora in horas:
        corte = instante(fecha, hora, codigo)
        estados = previas.get(hora, [])
        consultable = corte + pd.Timedelta(seconds=float(retraso_s) + float(margen_s))
        paso = {"hora": hora, "corte_utc": corte, "consultable_utc": consultable, "intentos_previos": estados,
                "etiqueta": etiqueta_libre(raiz_datos, _fecha(fecha), f"{_fecha(fecha)}T{hora.replace(':', '')}",
                                           "historico")}
        if "completa" in estados:
            paso.update(estado="completa", accion="omitir")
        else:
            paso.update(estado="pendiente", accion="esperar" if pd.Timestamp(ahora_utc) < consultable else "descargar")
        plan.append(paso)
    return plan


def meta_historico(fecha, paso: dict, retraso_s, simbolos, feed, ventana_s, limite) -> dict:
    """Metadatos de la descarga histórica de un paso de ``planificar_historico``.

    ``disponible_utc`` es el corte más ``retraso_s``: la disponibilidad
    documentada del dato, que fija la madurez de las etiquetas.
    """
    corte = pd.Timestamp(paso["corte_utc"])
    return {"fecha": str(_fecha(fecha)), "hora": paso["hora"], "corte_utc": iso(corte), "etiqueta": paso["etiqueta"],
            "retraso_s": float(retraso_s), "disponible_utc": iso(corte + pd.Timedelta(seconds=float(retraso_s))),
            "simbolos": list(simbolos), "feed": feed, "ventana_s": float(ventana_s), "limite": int(limite)}


def _descargar(cliente, solicitud, raiz_datos, meta, carpeta):
    registro = Registro(raiz_datos)
    inicio = cliente.reloj()
    _, errores = ejecutar(cliente, [solicitud], 1, registro)
    manifiesto = {"proveedor": PROVEEDOR, "version_adaptador": VERSION_ADAPTADOR, "cuenta": cliente.cuenta,
                  **meta, "inicio_utc": iso(inicio), "fin_utc": iso(cliente.reloj()),
                  "solicitudes": registro.entradas, "errores": errores,
                  "estado": registro.entradas[solicitud.nombre]["estado"]}
    return manifiesto, escribir_manifiesto(manifiesto, raiz_datos, carpeta)


def descargar_historico(cliente: ClienteAlpaca, solicitud: Solicitud, raiz_datos, meta: dict):
    """Descarga las cotizaciones históricas de un corte y escribe su manifiesto en ``historico/``.

    ``meta`` trae ``fecha``, ``hora``, ``corte_utc``, ``etiqueta`` y
    ``disponible_utc``: desde cuándo se puede consultar la ventana (el corte más
    el retraso del SIP sin suscripción), que la normalización registra como
    disponibilidad documentada. Consultar antes es un error: Alpaca respondería
    403 y, con suscripción, el dato no mediría lo que se podía saber en vivo.
    """
    if pd.Timestamp(cliente.reloj()) < pd.Timestamp(meta["disponible_utc"]):
        raise ValueError(f"{meta['etiqueta']}: la ventana del corte solo se puede consultar desde "
                         f"{meta['disponible_utc']}")
    return _descargar(cliente, solicitud, raiz_datos, meta, "historico")


def descargar_eventos(cliente: ClienteAlpaca, solicitud: Solicitud, raiz_datos, meta: dict):
    """Descarga los eventos corporativos y escribe su manifiesto en ``eventos/`` (``fecha`` es la de la consulta)."""
    return _descargar(cliente, solicitud, raiz_datos, meta, "eventos")


def leer_manifiestos(raiz_datos, desde=None, hasta=None, carpeta="capturas") -> list[dict]:
    """Manifiestos de ``carpeta`` entre dos fechas (incluidas), en orden de ruta."""
    base = directorio_crudo(raiz_datos) / carpeta
    if not base.exists():
        return []
    salida = []
    for ruta in sorted(base.glob("*/*.json")):
        fecha = _fecha(ruta.parent.name)
        if (desde is not None and fecha < _fecha(desde)) or (hasta is not None and fecha > _fecha(hasta)):
            continue
        manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
        manifiesto["_ruta"] = ruta.relative_to(Path(raiz_datos)).as_posix()
        salida.append(manifiesto)
    return salida


def leer_crudo(raiz_datos, pagina: dict):
    """JSON de una página del crudo, tras comprobar los hashes del archivo y del contenido."""
    datos = (Path(raiz_datos) / pagina["archivo"]).read_bytes()
    if almacen.sha256_bytes(datos) != pagina["sha256"]:
        raise RuntimeError(f"{pagina['archivo']}: el hash del archivo no coincide con el manifiesto")
    if pagina["archivo"].endswith(".gz"):
        datos = gzip.decompress(datos)
        if almacen.sha256_bytes(datos) != pagina["sha256_contenido"]:
            raise RuntimeError(f"{pagina['archivo']}: el hash del contenido no coincide con el manifiesto")
    return json.loads(datos)


# ---------------------------------------------------------------------------
# Selección de vencimientos
# ---------------------------------------------------------------------------


def metadatos_contratos(paginas_json) -> dict:
    """Metadatos por símbolo OCC a partir de las páginas de ``/v2/options/contracts``."""
    meta = {}
    for d in paginas_json:
        for c in d.get("option_contracts") or []:
            meta[c["symbol"]] = c
    return meta


def elegir_vencimientos(vencimientos, liquidacion, corte_utc, objetivo_dias=30.0, por_lado=2, cercano=False,
                        base_dias=365.0, codigo=CALENDARIO):
    """Vencimientos a capturar: ``por_lado`` a cada lado del objetivo y, si se pide, el más cercano.

    El plazo son días naturales desde el corte hasta el instante contractual
    de liquidación (la misma medida que usa el piloto). Devuelve la lista y los
    plazos de todos los vencimientos que aún no liquidaron.
    """
    plazos = {}
    for v in sorted({_fecha(v) for v in vencimientos}):
        if not es_sesion(v, codigo):
            continue
        dias = plazo_anios(corte_utc, instante_liquidacion(v, liquidacion, codigo), base_dias) * base_dias
        if dias > 0:
            plazos[v] = dias
    antes = [v for v in plazos if plazos[v] <= objetivo_dias][-por_lado:] if por_lado else []
    despues = [v for v in plazos if plazos[v] > objetivo_dias][:por_lado] if por_lado else []
    elegidos = set(antes) | set(despues)
    if cercano and plazos:
        elegidos.add(min(plazos, key=plazos.get))
    return sorted(elegidos), plazos


# ---------------------------------------------------------------------------
# Normalización al contrato de datos
# ---------------------------------------------------------------------------


def _tabla(filas, esquema, extras) -> pd.DataFrame:
    tabla = pd.DataFrame(filas, columns=list(esquema) + list(extras))
    for columna, (tipo, _, _) in esquema.items():
        if tipo == "instante":
            tabla[columna] = pd.to_datetime(tabla[columna], utc=True, format="ISO8601").dt.as_unit("us")
        elif tipo == "real":
            tabla[columna] = pd.to_numeric(tabla[columna]).astype(float)
    return tabla


def filas_cadena(snapshots: dict, meta: dict, recibido_utc, feed, captura, cuentas: Counter) -> list[dict]:
    """Filas ``COTIZACIONES`` de una página de snapshots (sin cotización o sin metadatos: se cuentan)."""
    filas = []
    for simbolo in sorted(snapshots):
        q = snapshots[simbolo].get("latestQuote")
        if not q or q.get("bp") is None or q.get("ap") is None:
            cuentas["sin_cotizacion"] += 1
            continue
        m = meta.get(simbolo)
        if m is None:
            cuentas["sin_metadatos"] += 1
            continue
        occ = contrato.parsear_occ(simbolo)
        if (occ["raiz"] != m["root_symbol"] or str(occ["vencimiento"]) != m["expiration_date"]
                or occ["tipo"] != TIPO.get(m["type"]) or abs(occ["strike"] - float(m["strike_price"])) > 1e-9):
            raise ValueError(f"{simbolo}: el símbolo no coincide con los metadatos del contrato")
        if m["style"] not in ESTILO:
            raise ValueError(f"{simbolo}: estilo de ejercicio desconocido {m['style']!r}")
        if occ["raiz"] not in LIQUIDACION:
            raise ValueError(f"{simbolo}: liquidación desconocida para la raíz {occ['raiz']}")
        cuentas["con_cotizacion"] += 1
        filas.append({
            "id_contrato": simbolo, "raiz": occ["raiz"], "subyacente": m["underlying_symbol"],
            "strike": occ["strike"], "tipo": occ["tipo"], "ejercicio": ESTILO[m["style"]],
            "liquidacion": LIQUIDACION[occ["raiz"]], "vencimiento": occ["vencimiento"],
            "multiplicador": float(m["multiplier"]), "bid": q["bp"], "ask": q["ap"],
            "tam_bid": q.get("bs", 0), "tam_ask": q.get("as", 0), "sello_evento_utc": q.get("t"),
            "sello_snapshot_utc": recibido_utc, "disponible_utc": recibido_utc, "recibido_utc": recibido_utc,
            "proveedor": PROVEEDOR, "feed": feed, "bolsa_bid": q.get("bx"), "bolsa_ask": q.get("ax"),
            "condicion": q.get("c"), "captura": captura})
    return filas


def filas_acciones(snapshots: dict, recibido_utc, feed, captura) -> list[dict]:
    """Filas ``SUBYACENTE`` de un snapshot de acciones: mid de la cotización o, si falta, la última operación."""
    filas = []
    for simbolo in sorted(snapshots):
        q = snapshots[simbolo].get("latestQuote") or {}
        t = snapshots[simbolo].get("latestTrade") or {}
        bid, ask = q.get("bp") or 0.0, q.get("ap") or 0.0
        if 0.0 < bid <= ask:
            precio, sello, fuente = 0.5 * (bid + ask), q.get("t"), "mid"
        elif t.get("p"):
            precio, sello, fuente = t["p"], t.get("t"), "operacion"
        else:
            continue
        filas.append({"subyacente": simbolo, "precio": precio, "bid": bid if bid > 0 else None,
                      "ask": ask if ask > 0 else None, "sello_evento_utc": sello, "sello_snapshot_utc": recibido_utc,
                      "disponible_utc": recibido_utc, "recibido_utc": recibido_utc, "proveedor": PROVEEDOR,
                      "feed": feed, "tipo_precio": "observado", "fuente_precio": fuente, "captura": captura})
    return filas


def normalizar_manifiesto(manifiesto: dict, raiz_datos):
    """Tablas ``COTIZACIONES`` y ``SUBYACENTE`` de una captura, y su resumen de cobertura."""
    solicitudes = manifiesto["solicitudes"]
    captura = manifiesto["etiqueta"]
    meta = metadatos_contratos(leer_crudo(raiz_datos, p) for e in solicitudes.values() if e["tipo"] == "contratos"
                               for p in e["paginas"])
    cotizaciones, subyacente, cuentas = [], [], Counter()
    for nombre in sorted(solicitudes):
        e = solicitudes[nombre]
        for p in e["paginas"]:
            if e["tipo"] == "cadena":
                d = leer_crudo(raiz_datos, p)
                cuentas["snapshots"] += len(d.get("snapshots") or {})
                cotizaciones += filas_cadena(d.get("snapshots") or {}, meta, p["recibido_utc"],
                                             p["params"].get("feed"), captura, cuentas)
            elif e["tipo"] == "acciones":
                subyacente += filas_acciones(leer_crudo(raiz_datos, p), p["recibido_utc"], p["params"].get("feed"),
                                             captura)
    cot = _tabla(cotizaciones, contrato.COTIZACIONES, EXTRAS_COTIZACIONES)
    sub = _tabla(subyacente, contrato.SUBYACENTE, EXTRAS_SUBYACENTE)
    for tabla, esquema in ((cot, contrato.COTIZACIONES), (sub, contrato.SUBYACENTE)):
        problemas = contrato.validar(tabla, esquema) if len(tabla) else []
        if problemas:
            raise ValueError(f"{manifiesto['_ruta'] if '_ruta' in manifiesto else captura}: " + "; ".join(problemas))
    resumen = {"captura": captura, "fecha": manifiesto["fecha"], "hora": manifiesto["hora"],
               "estado": estado_manifiesto(manifiesto),
               "solicitudes_no_completas": sorted(n for n, e in solicitudes.items()
                                                  if e.get("estado", "completa") != "completa"),
               "corte_utc": manifiesto["corte_utc"], "contratos_en_metadatos": len(meta),
               **dict(sorted(cuentas.items())),
               "errores": len(manifiesto.get("errores", {})),
               "respuestas_despues_del_corte": len(manifiesto.get("respuestas_despues_del_corte", []))}
    return cot, sub, resumen


def normalizar(raiz_datos, desde=None, hasta=None):
    """Normaliza todas las capturas entre dos fechas; tablas ordenadas y listas para Parquet."""
    manifiestos = leer_manifiestos(raiz_datos, desde, hasta)
    partes_cot, partes_sub, resumenes = [], [], []
    for m in manifiestos:
        cot, sub, resumen = normalizar_manifiesto(m, raiz_datos)
        partes_cot.append(cot)
        partes_sub.append(sub)
        resumenes.append(resumen)
    cot = (pd.concat(partes_cot, ignore_index=True) if partes_cot
           else _tabla([], contrato.COTIZACIONES, EXTRAS_COTIZACIONES))
    sub = (pd.concat(partes_sub, ignore_index=True) if partes_sub
           else _tabla([], contrato.SUBYACENTE, EXTRAS_SUBYACENTE))
    cot = cot.sort_values(["sello_snapshot_utc", "id_contrato"], kind="stable").reset_index(drop=True)
    sub = sub.sort_values(["sello_snapshot_utc", "subyacente"], kind="stable").reset_index(drop=True)
    return cot, sub, resumenes, manifiestos


def filas_historico(cuerpo: dict, corte_utc, disponible_utc, recibido_utc, feed, captura,
                    cuentas: Counter) -> list[dict]:
    """Filas ``SUBYACENTE`` de una página de ``/v2/stocks/quotes``: una por cotización con los dos lados.

    ``sello_snapshot_utc`` es el corte (la consulta pide el estado hasta él) y
    ``disponible_utc``, desde cuándo el proveedor deja consultarlo. Las filas
    van en orden de la hora del evento en nanosegundos. Una cotización sin bid
    o sin ask no tiene mid: se cuenta y no se normaliza. Una cruzada sí, y la
    regla histórica (``contrato.precio_para_etiqueta``) la descarta después.
    """
    filas = []
    for simbolo in sorted(cuerpo.get("quotes") or {}):
        for q in sorted(cuerpo["quotes"][simbolo] or [], key=lambda q: pd.Timestamp(q["t"])):
            bid, ask = float(q.get("bp") or 0.0), float(q.get("ap") or 0.0)
            if bid <= 0.0 or ask <= 0.0:
                cuentas["de_un_lado"] += 1
                continue
            if pd.Timestamp(q["t"]) > pd.Timestamp(corte_utc):
                raise ValueError(f"{captura}: cotización de {simbolo} posterior al corte ({q['t']})")
            cuentas["cotizaciones"] += 1
            filas.append({"subyacente": simbolo, "precio": 0.5 * (bid + ask), "bid": bid, "ask": ask,
                          "sello_evento_utc": q["t"], "sello_snapshot_utc": corte_utc,
                          "disponible_utc": disponible_utc, "recibido_utc": recibido_utc, "proveedor": PROVEEDOR,
                          "feed": feed, "tipo_precio": "observado", "fuente_precio": "mid", "captura": captura})
    return filas


def normalizar_historico(raiz_datos, desde=None, hasta=None):
    """Filas ``SUBYACENTE`` de la primera descarga histórica completa de cada corte y sus resúmenes.

    Comprueba que cada página se descargó después de la disponibilidad
    documentada del corte: el dato no pudo influir en nada anterior.
    Devuelve ``(subyacente, resumenes, manifiestos_usados)``.
    """
    elegidos = {}
    for m in leer_manifiestos(raiz_datos, desde, hasta, "historico"):
        if m["estado"] == "completa":
            elegidos.setdefault((m["fecha"], m["hora"]), m)
    partes, resumenes, usados = [], [], []
    for clave in sorted(elegidos):
        m = elegidos[clave]
        filas, cuentas, recibidos = [], Counter(), []
        for nombre in sorted(m["solicitudes"]):
            for p in m["solicitudes"][nombre]["paginas"]:
                if pd.Timestamp(p["recibido_utc"]) < pd.Timestamp(m["disponible_utc"]):
                    raise ValueError(f"{m['etiqueta']}: página recibida antes de la disponibilidad documentada")
                recibidos.append(p["recibido_utc"])
                filas += filas_historico(leer_crudo(raiz_datos, p), m["corte_utc"], m["disponible_utc"],
                                         p["recibido_utc"], p["params"].get("feed"), m["etiqueta"], cuentas)
        tabla = _tabla(filas, contrato.SUBYACENTE, EXTRAS_SUBYACENTE)
        problemas = contrato.validar(tabla, contrato.SUBYACENTE) if len(tabla) else []
        if problemas:
            raise ValueError(f"{m['_ruta']}: " + "; ".join(problemas))
        partes.append(tabla)
        usados.append(m)
        resumenes.append({"captura": m["etiqueta"], "fecha": m["fecha"], "hora": m["hora"],
                          "corte_utc": m["corte_utc"], "disponible_utc": m["disponible_utc"],
                          "recibido_utc": min(recibidos) if recibidos else None, **dict(sorted(cuentas.items())),
                          "primer_evento_utc": iso(tabla["sello_evento_utc"].min()) if len(tabla) else None,
                          "ultimo_evento_utc": iso(tabla["sello_evento_utc"].max()) if len(tabla) else None})
    sub = (pd.concat(partes, ignore_index=True) if partes else _tabla([], contrato.SUBYACENTE, EXTRAS_SUBYACENTE))
    return sub, resumenes, usados


def _valores_dividendo(x):
    """Los valores que definen una versión; ``None`` donde el proveedor no dio el campo."""
    return (x["symbol"], x.get("ex_date") or None, None if x.get("rate") is None else float(x["rate"]),
            bool(x.get("special")), x.get("payable_date") or None, x.get("process_date") or None)


def _novedad(listado, datos) -> bool:
    """Si un listado del proveedor trae algo nuevo sobre ``datos``: un campo que faltaba o un valor distinto.

    Un campo que el listado no trae no es novedad: repetir con menos datos no
    corrige lo que ya se sabía.
    """
    return any(n is not None and n != v for n, v in zip(_valores_dividendo(listado), _valores_dividendo(datos)))


def _incompleto(x) -> bool:
    return not x.get("ex_date") or x.get("rate") is None


def _identificar(x, simbolos):
    """Un dividendo con identificador y símbolo, o ``None`` si no se puede atribuir.

    Sin símbolo, vale el de la consulta si pidió uno solo. Sin identificador, se
    deriva uno estable de su contenido.
    """
    simbolo = x.get("symbol") or (simbolos[0] if len(simbolos) == 1 else None)
    if not simbolo:
        return None
    contenido = json.dumps(x, sort_keys=True, default=str).encode()
    return dict(x, symbol=simbolo, id=x.get("id") or f"sin-id-{almacen.sha256_bytes(contenido)[:16]}")


def _completar(id_evento, datos, resolucion):
    """Los valores de un dividendo con la evidencia de una resolución «vigente»: completa, no corrige."""
    x = dict(datos)
    evidencia = {"ex_date": None if pd.isna(resolucion.fecha_ex) else str(_fecha(resolucion.fecha_ex)),
                 "rate": None if pd.isna(resolucion.monto) else float(resolucion.monto)}
    for campo, valor in evidencia.items():
        if valor is None:
            continue
        conocido = x.get(campo)
        if conocido is not None and (_fecha(conocido) != _fecha(valor) if campo == "ex_date"
                                     else abs(float(conocido) - valor) > 1e-12):
            raise ValueError(f"resolución de {id_evento}: {campo} {valor} contradice el valor conocido {conocido} "
                             "(una resolución completa lo que falta; no corrige)")
        x[campo] = valor
    if _incompleto(x):
        raise ValueError(f"resolución vigente de {id_evento}: el dividendo llegó sin fecha ex o sin monto; la "
                         "resolución debe darlos (fecha_ex, monto)")
    return x


def _con_opcionales(resoluciones):
    """Las resoluciones con las columnas opcionales del contrato que falten, vacías."""
    faltan = {c: None for c, (_, obligatoria, _) in contrato.RESOLUCIONES_DIVIDENDOS.items()
              if not obligatoria and c not in resoluciones}
    return resoluciones.assign(**faltan) if faltan else resoluciones


def _consultas_eventos(raiz_datos):
    """Cada consulta de eventos guardada: parámetros, estado, recepción y eventos devueltos."""
    consultas = []
    for m in leer_manifiestos(raiz_datos, None, None, "eventos"):
        for nombre in sorted(m["solicitudes"]):
            e = m["solicitudes"][nombre]
            params = e["paginas"][0]["params"] if e["paginas"] else dict(e.get("params") or {})
            if not params.get("symbols"):
                raise ValueError(f"{m['_ruta']}: consulta de eventos sin parámetros registrados")
            eventos = [(tipo, x) for p in e["paginas"]
                       for tipo, lista in sorted((leer_crudo(raiz_datos, p).get("corporate_actions") or {}).items())
                       for x in lista or []]
            recibido = (max(p["recibido_utc"] for p in e["paginas"]) if e["paginas"]
                        else m.get("fin_utc") or m["inicio_utc"])
            consultas.append({"consulta": m["etiqueta"], "estado": e.get("estado", "completa"),
                              "recibido": pd.Timestamp(recibido), "simbolos": params["symbols"].split(","),
                              "desde": _fecha(params["start"]), "hasta": _fecha(params["end"]),
                              "calidad": params.get("data_quality", "complete"), "tipos": params.get("types", "todos"),
                              "eventos": eventos, "manifiesto": m})
    return sorted(consultas, key=lambda q: (q["recibido"], q["consulta"]))


def _comparable(consulta, version) -> bool:
    """Si la ausencia de ``version`` en ``consulta`` dice algo: completa, mismos filtros y su proceso dentro."""
    x = version["datos"]
    fecha = x.get("process_date") or x.get("payable_date") or x.get("ex_date")
    if not fecha:
        return False
    fecha, tipos = _fecha(fecha), consulta["tipos"]
    return (consulta["estado"] == "completa" and consulta["calidad"] == version["calidad"]
            and (tipos == "todos" or "cash_dividend" in tipos.split(",")) and x["symbol"] in consulta["simbolos"]
            and consulta["desde"] <= fecha <= consulta["hasta"])


def normalizar_eventos(raiz_datos, resoluciones=None):
    """Versiones de dividendos, cobertura de cada consulta y demás eventos corporativos.

    **Cobertura** (``contrato.COBERTURA_DIVIDENDOS``): una fila por consulta y
    símbolo pedido, con su intervalo (por ``process_date``), filtros, estado y
    recepción, aunque haya venido vacía o haya fallado.

    **Versiones** (``contrato.DIVIDENDOS``). Se recorren en orden de
    conocimiento las consultas completas y las ``resoluciones``
    (``contrato.RESOLUCIONES_DIVIDENDOS``, evidencia registrada a mano):

    * un id nuevo abre una versión conocida desde esa consulta; con otros
      valores, la anterior se retira («corregido») y se abre otra;
    * un id vigente que falta en una consulta **comparable** (completa, con el
      mismo filtro de calidad, tipos que incluyen dividendos y un intervalo que
      contiene su fecha de proceso) **no** se retira: abre una discrepancia
      («ausente»). Repetir la ausencia no la resuelve;
    * la resuelve evidencia fechada: que el id reaparezca igual (la versión se
      cierra, «reaparecido», y sigue otra idéntica), que reaparezca con otros
      valores («corregido») o una resolución;
    * una resolución actúa sobre el dividendo en su fecha de conocimiento,
      haya o no una discrepancia abierta. «vigente» cierra la versión
      («confirmado») y abre otra idéntica, de origen ``resolucion``, que ya no
      abre discrepancias por ausencia; también devuelve un dividendo cancelado.
      «cancelado» la cierra («cancelado»). La evidencia fija el estado con esos
      valores: una omisión posterior de un dividendo confirmado, o un cancelado
      que el proveedor vuelve a traer igual, no aporta nada nuevo (se cuenta en
      ``otros_eventos``). Si el proveedor trae un cancelado con **otros**
      valores, se abre una versión con la discrepancia «reaparece_cancelado»,
      que solo resuelve otra resolución;
    * un dividendo que llega **sin fecha ex o sin monto** también es una
      versión, con la discrepancia «incompleto» y, sin fecha ex, el intervalo
      de su fecha de proceso (el del proveedor o el de la consulta que lo
      trajo). La resuelve el registro completo del proveedor (una versión
      nueva) o una resolución «vigente» con la fecha ex y el monto que falten.
      Un listado posterior con menos datos no es novedad.

    Nada se borra. ``disponible_utc`` queda nulo: Alpaca no da la hora del
    anuncio. Los demás tipos (splits, fusiones, cambios de nombre, etc.) y los
    dividendos sin identificador o sin símbolo se devuelven aparte: el piloto no
    los trata. Devuelve ``(dividendos, cobertura, otros_eventos, manifiestos)``;
    en ``otros_eventos`` quedan también, con su tipo, las resoluciones sin
    dividendo sobre el que actuar (``resolucion_sin_efecto``) y las consultas
    que contradicen una resolución sin valores nuevos
    (``omitido_tras_confirmar`` y ``listado_tras_cancelar``, con cuántas veces).
    """
    consultas = _consultas_eventos(raiz_datos)
    pasos = [(q["recibido"], 0, q["consulta"], q) for q in consultas]
    if resoluciones is not None and len(resoluciones):
        resoluciones = _con_opcionales(resoluciones)
        problemas = contrato.validar(resoluciones, contrato.RESOLUCIONES_DIVIDENDOS)
        if problemas:
            raise ValueError("resoluciones de dividendos: " + "; ".join(problemas))
        pasos += [(r.conocido_utc, 1, str(r.id_evento), r) for r in resoluciones.itertuples()]
    cobertura, versiones, vigentes, cancelados, otros = [], [], {}, {}, {}

    def abrir(id_evento, x, desde, calidad, ventana, origen="consulta", discrepancia=None):
        if discrepancia is None and _incompleto(x):
            discrepancia = ("incompleto", desde)
        vigentes[id_evento] = len(versiones)
        versiones.append({"id": id_evento, "datos": x, "recibido": desde, "retirado": None, "motivo": "",
                          "discrepancia": discrepancia, "calidad": calidad, "origen": origen, "ventana": ventana})

    def cerrar(id_evento, cuando, motivo):
        v = versiones[vigentes.pop(id_evento)]
        v.update(retirado=cuando, motivo=motivo)
        return v

    def anotar(tipo, id_evento, simbolo, cuando):
        e = otros.setdefault(f"{tipo}-{id_evento}", {"tipo": tipo, "simbolo": simbolo, "fecha": str(cuando.date()),
                                                     "id": id_evento, "veces": 0})
        e.update(veces=e["veces"] + 1, ultima=str(cuando.date()))

    for cuando, clase, id_paso, paso in sorted(pasos, key=lambda t: t[:3]):
        if clase == 1:  # resolución registrada
            previa = versiones[vigentes[id_paso]] if id_paso in vigentes else cancelados.get(id_paso)
            if previa is not None and previa["datos"]["symbol"] != paso.simbolo:
                raise ValueError(f"resolución de {id_paso}: el evento es de {previa['datos']['symbol']}, "
                                 f"no de {paso.simbolo}")
            # La evidencia de una «vigente» completa lo que falta; nunca contradice lo conocido.
            datos = (_completar(id_paso, previa["datos"], paso)
                     if previa is not None and paso.resolucion == "vigente" else None)
            if id_paso in vigentes and not (paso.resolucion == "vigente" and previa["origen"] == "resolucion"):
                cerrar(id_paso, cuando, "confirmado" if paso.resolucion == "vigente" else "cancelado")
                if paso.resolucion == "vigente":
                    abrir(id_paso, datos, cuando, previa["calidad"], previa["ventana"], "resolucion")
                else:
                    cancelados[id_paso] = previa
            elif id_paso in cancelados and paso.resolucion == "vigente":
                del cancelados[id_paso]
                abrir(id_paso, datos, cuando, previa["calidad"], previa["ventana"], "resolucion")
            else:  # evento desconocido, ya cancelado o ya confirmado
                otros[f"resolucion-{id_paso}-{iso(cuando)}"] = {
                    "tipo": "resolucion_sin_efecto", "simbolo": paso.simbolo, "fecha": str(cuando.date()),
                    "id": id_paso}
            continue
        q = paso
        atribuidos = [_identificar(x, q["simbolos"]) for t, x in q["eventos"] if t == "cash_dividends"]
        for simbolo in q["simbolos"]:
            cobertura.append({
                "simbolo": simbolo, "desde": q["desde"], "hasta": q["hasta"], "campo_fecha": "process_date",
                "recibido_utc": iso(q["recibido"]), "estado": q["estado"],
                "eventos": float(sum(x is not None and x["symbol"] == simbolo for x in atribuidos)),
                "calidad": q["calidad"], "tipos": q["tipos"], "consulta": q["consulta"], "proveedor": PROVEEDOR,
                "feed": FEED_EVENTOS})
        if q["estado"] != "completa":
            continue
        presentes = {}
        for tipo, x in q["eventos"]:
            dividendo = _identificar(x, q["simbolos"]) if tipo == "cash_dividends" else None
            if dividendo is not None:  # también sin fecha ex o sin monto: la versión lleva la discrepancia
                presentes[dividendo["id"]] = dividendo
                continue
            otros[x.get("id")] = {"tipo": tipo if tipo != "cash_dividends" else "cash_dividends_incompleto",
                                  "simbolo": x.get("symbol") or x.get("old_symbol") or x.get("target_symbol"),
                                  "fecha": x.get("ex_date") or x.get("effective_date") or x.get("process_date"),
                                  "id": x.get("id")}
        recibido, ventana = q["recibido"], (q["desde"], q["hasta"])
        for id_evento in sorted(presentes):
            x = presentes[id_evento]
            if id_evento in vigentes:
                v = versiones[vigentes[id_evento]]
                tipo = v["discrepancia"][0] if v["discrepancia"] else None
                if _novedad(x, v["datos"]):
                    cerrar(id_evento, recibido, "corregido")
                    # Una corrección responde a una ausencia, no a la resolución que lo canceló.
                    sigue = ("reaparece_cancelado", recibido) if tipo == "reaparece_cancelado" else None
                    abrir(id_evento, x, recibido, q["calidad"], ventana, discrepancia=sigue)
                elif tipo == "ausente":  # reaparece sin nada nuevo: sigue con lo que ya se sabía
                    cerrar(id_evento, recibido, "reaparecido")
                    abrir(id_evento, v["datos"], recibido, q["calidad"], v["ventana"])
            elif id_evento in cancelados:
                if not _novedad(x, cancelados[id_evento]["datos"]):
                    anotar("listado_tras_cancelar", id_evento, x["symbol"], recibido)
                else:
                    del cancelados[id_evento]
                    abrir(id_evento, x, recibido, q["calidad"], ventana,
                          discrepancia=("reaparece_cancelado", recibido))
            else:
                abrir(id_evento, x, recibido, q["calidad"], ventana)
        for id_evento, i in sorted(vigentes.items()):
            v = versiones[i]
            if id_evento in presentes or v["discrepancia"] is not None or not _comparable(q, v):
                continue
            if v["origen"] == "resolucion":
                anotar("omitido_tras_confirmar", id_evento, v["datos"]["symbol"], recibido)
            else:
                v["discrepancia"] = ("ausente", recibido)
    numero, filas = {}, []
    for v in versiones:
        x, (tipo, desde) = v["datos"], v["discrepancia"] or ("", None)
        numero[v["id"]] = numero.get(v["id"], 0) + 1
        # Sin fecha ex, el intervalo de su fecha de proceso: la del proveedor o, si falta, el de la consulta.
        proceso = ((None, None) if x.get("ex_date") else (_fecha(x["process_date"]),) * 2 if x.get("process_date")
                   else v["ventana"])
        filas.append({"simbolo": x["symbol"], "fecha_ex": _fecha(x["ex_date"]) if x.get("ex_date") else None,
                      "monto": float(x["rate"]) if x.get("rate") is not None else None,
                      "fecha_pago": _fecha(x["payable_date"]) if x.get("payable_date") else None,
                      "clase": "especial" if x.get("special") else "ordinario",
                      "proceso_desde": proceso[0], "proceso_hasta": proceso[1], "disponible_utc": None,
                      "recibido_utc": iso(v["recibido"]),
                      "retirado_utc": iso(v["retirado"]) if v["retirado"] is not None else None,
                      "motivo_retiro": v["motivo"], "discrepancia": tipo,
                      "discrepancia_desde_utc": iso(desde) if desde is not None else None,
                      "proveedor": PROVEEDOR, "feed": FEED_EVENTOS, "id_evento": v["id"], "version": numero[v["id"]],
                      "origen": v["origen"], "fecha_registro": x.get("record_date"),
                      "fecha_proceso": x.get("process_date"), "subtipo": x.get("sub_type")})
    # Las versiones de un evento, juntas; los eventos, por su primera fecha ex conocida (sin ella, al final).
    primera = {}
    for f in filas:
        if f["fecha_ex"] is not None:
            primera[f["id_evento"]] = min(primera.get(f["id_evento"], f["fecha_ex"]), f["fecha_ex"])
    filas.sort(key=lambda f: (f["simbolo"], primera.get(f["id_evento"]) is None,
                              primera.get(f["id_evento"]) or dt.date.min, f["id_evento"], f["version"]))
    tabla = _tabla(filas, contrato.DIVIDENDOS, EXTRAS_DIVIDENDOS)
    cob = _tabla(cobertura, contrato.COBERTURA_DIVIDENDOS, [])
    for t, esquema, nombre in ((tabla, contrato.DIVIDENDOS, "dividendos"),
                               (cob, contrato.COBERTURA_DIVIDENDOS, "cobertura")):
        problemas = contrato.validar(t, esquema) if len(t) else []
        if problemas:
            raise ValueError(f"{nombre} de Alpaca: " + "; ".join(problemas))
    return (tabla, cob, sorted(otros.values(), key=lambda e: (str(e["fecha"]), str(e["id"]), e["tipo"])),
            [q["manifiesto"] for q in consultas])


def cargar_resoluciones(ruta) -> pd.DataFrame:
    """Resoluciones de dividendos registradas a mano (CSV con el esquema ``contrato.RESOLUCIONES_DIVIDENDOS``).

    ``conocido_utc`` se lee como instante UTC (con zona explícita en el
    archivo); ``fecha_ex`` y ``monto`` son opcionales (una «vigente» los da
    cuando el proveedor no los dio). Lanza ``ValueError`` si la tabla no cumple
    el contrato.
    """
    tabla = _con_opcionales(pd.read_csv(ruta, dtype=str, keep_default_na=False))
    if "conocido_utc" in tabla:
        if not tabla["conocido_utc"].str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).all():
            raise ValueError(f"{ruta}: conocido_utc debe llevar la zona explícita (p. ej., 2026-11-20T15:00:00Z)")
        tabla["conocido_utc"] = pd.to_datetime(tabla["conocido_utc"], utc=True, format="ISO8601").dt.as_unit("us")
    vacias = {c: tabla[c].fillna("").astype(str).str.strip() == "" for c in ("fecha_ex", "monto")}
    tabla["fecha_ex"] = [None if vacia else _fecha(v) for v, vacia in zip(tabla["fecha_ex"], vacias["fecha_ex"])]
    tabla["monto"] = pd.to_numeric(tabla["monto"].where(~vacias["monto"]), errors="raise").astype(float)
    for columna, (tipo, obligatoria, _) in contrato.RESOLUCIONES_DIVIDENDOS.items():
        if columna in tabla and tipo == "texto" and obligatoria:  # una celda vacía es un valor que falta
            tabla[columna] = tabla[columna].mask(tabla[columna].str.strip() == "")
    problemas = contrato.validar(tabla, contrato.RESOLUCIONES_DIVIDENDOS)
    if problemas:
        raise ValueError(f"{ruta}: " + "; ".join(problemas))
    return tabla.sort_values(["conocido_utc", "id_evento"], kind="stable").reset_index(drop=True)


def resumen_dividendos(dividendos: pd.DataFrame, otros=()) -> dict:
    """Cuánto revisa el proveedor lo que ya había publicado: versiones, retiros, discrepancias y contradicciones.

    ``otros`` son los demás eventos de ``normalizar_eventos``: de ellos se
    cuentan las consultas que contradicen una resolución sin valores nuevos.
    """
    d = dividendos
    con = d["discrepancia_desde_utc"].notna() if len(d) else pd.Series(dtype=bool)
    abiertas = con & d["retirado_utc"].isna() if len(d) else con
    return {"versiones": int(len(d)),
            "dividendos": int(d["id_evento"].nunique()) if "id_evento" in d and len(d) else int(len(d)),
            "retiros_por_motivo": {k: int(n) for k, n in sorted(d.loc[d["retirado_utc"].notna(), "motivo_retiro"]
                                                                .value_counts().items())} if len(d) else {},
            "confirmadas_por_resolucion": int((d["origen"] == "resolucion").sum()) if "origen" in d else 0,
            "discrepancias": {k: int(n) for k, n in sorted(d.loc[con, "discrepancia"].value_counts().items())}
            if len(d) else {},
            "discrepancias_abiertas": {k: int(n) for k, n in sorted(d.loc[abiertas, "discrepancia"]
                                                                    .value_counts().items())} if len(d) else {},
            "contradicciones_sin_valores_nuevos": {
                t: int(sum(e.get("veces", 0) for e in otros if e["tipo"] == t))
                for t in ("omitido_tras_confirmar", "listado_tras_cancelar")},
            "resoluciones_sin_efecto": int(sum(e["tipo"] == "resolucion_sin_efecto" for e in otros))}


@dataclass(frozen=True, eq=False)
class TablasAlpaca:
    """Tablas normalizadas de Alpaca para el piloto y lo que las explica."""

    cotizaciones: pd.DataFrame
    subyacente: pd.DataFrame  # IEX, nivel implícito y SIP histórico
    dividendos: pd.DataFrame  # versiones
    cobertura_dividendos: pd.DataFrame  # una fila por consulta y símbolo
    resumenes: list  # capturas en vivo
    resumenes_historico: list
    fallos_implicito: list
    manifiestos: list  # capturas en vivo
    manifiestos_historico: list
    manifiestos_eventos: list
    eventos_no_tratados: list


def tablas_para_piloto(raiz_datos, desde=None, hasta=None, cfg_implicito=None, reglas=None,
                       resoluciones=None, eventos=True) -> TablasAlpaca:
    """Cotizaciones, subyacente y dividendos normalizados, con el subyacente implícito si se configura.

    ``cfg_implicito`` es la sección ``[implicito]`` de la configuración de
    captura; ``reglas`` son las reglas de calidad del piloto. El subyacente
    reúne las cotizaciones en vivo (IEX), el nivel implícito y el histórico SIP
    del objetivo. Un evento corporativo distinto de un dividendo en efectivo
    con fecha dentro del rango detiene la normalización: cambiaría los precios
    sin que las etiquetas lo traten. Un dividendo que no se puede atribuir a un
    símbolo la detiene siempre. Con ``eventos=False`` (el resumen del día que
    escribe la captura) no se leen los eventos: las tablas de dividendos quedan
    vacías y no se comprueba nada de ellos.
    """
    cot, sub, resumenes, manifiestos = normalizar(raiz_datos, desde, hasta)
    fallos, partes = [], [sub]
    if cfg_implicito and len(cot):
        c = cfg_implicito
        capturas = [(m["etiqueta"], m["fecha"], m["corte_utc"]) for m in manifiestos]
        imp, fallos = implicito.subyacente_implicito(
            cot, capturas, c["raiz"], c["subyacente"], float(c["tasa"]), float(c["rendimiento_dividendo"]),
            reglas or cadenas.ReglasCalidad(), int(c["minimo_pares"]), float(c["dias_max"]))
        partes.append(imp)
    historico, resumenes_hist, manifiestos_hist = normalizar_historico(raiz_datos, desde, hasta)
    partes.append(historico)
    partes = [t for t in partes if len(t)]
    if len(partes) > 1:
        sub = pd.concat(partes, ignore_index=True)
    elif partes:
        sub = partes[0]
    sub = sub.sort_values(["sello_snapshot_utc", "subyacente"], kind="stable").reset_index(drop=True)
    if not eventos:
        return TablasAlpaca(cot, sub, _tabla([], contrato.DIVIDENDOS, EXTRAS_DIVIDENDOS),
                            _tabla([], contrato.COBERTURA_DIVIDENDOS, []), resumenes, resumenes_hist, fallos,
                            manifiestos, manifiestos_hist, [], [])
    dividendos, cobertura, otros, manifiestos_ev = normalizar_eventos(raiz_datos, resoluciones)
    def en_rango(e):
        if e["tipo"] in NO_BLOQUEAN:
            return False
        if e["tipo"] == "cash_dividends_incompleto":  # sin símbolo atribuible: no se sabe a qué etiquetas toca
            return True
        return bool(e["fecha"]) and ((desde is None or _fecha(e["fecha"]) >= _fecha(desde))
                                     and (hasta is None or _fecha(e["fecha"]) <= _fecha(hasta)))

    en_rango = [e for e in otros if en_rango(e)]
    if en_rango:
        raise ValueError("eventos corporativos no tratados en el rango: "
                         + "; ".join(f"{e['tipo']} de {e['simbolo']} el {e['fecha']}" for e in en_rango))
    return TablasAlpaca(cot, sub, dividendos, cobertura, resumenes, resumenes_hist, fallos, manifiestos,
                        manifiestos_hist, manifiestos_ev, otros)


def esperar_hasta(objetivo_utc, reloj=None, dormir=time.sleep, paso_max=30.0):
    """Duerme hasta ``objetivo_utc`` en pasos cortos (tolera ajustes del reloj)."""
    reloj = reloj or _ahora
    objetivo_utc = pd.Timestamp(objetivo_utc)
    while True:
        faltan = (objetivo_utc - reloj()).total_seconds()
        if faltan <= 0:
            return
        dormir(min(faltan, paso_max))
