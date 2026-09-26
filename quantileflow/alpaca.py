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

import gzip
import http.client
import json
import os
import stat
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
from .calendario import CALENDARIO, _fecha, es_sesion, instante_liquidacion, plazo_anios

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

    def paginas(self, servicio, ruta, params=(), maximo=200) -> list[Respuesta]:
        """Todas las páginas de una consulta (``next_page_token``), cada una como respuesta propia."""
        respuestas, token = [], None
        while True:
            p = dict(params)
            if token:
                p["page_token"] = token
            respuesta = self.get(servicio, ruta, p)
            respuestas.append(respuesta)
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
    tipo: str  # "reloj", "contratos", "cadena" o "acciones"
    servicio: str
    ruta: str
    params: tuple = ()


def _solicitud(nombre, tipo, servicio, ruta, **params):
    return Solicitud(nombre, tipo, servicio, ruta,
                     tuple(sorted((k, str(v)) for k, v in params.items() if v is not None)))


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


def ejecutar(cliente: ClienteAlpaca, solicitudes, hilos=8):
    """Ejecuta las solicitudes en paralelo. Devuelve respuestas por nombre y errores por nombre."""
    nombres = [s.nombre for s in solicitudes]
    if len(set(nombres)) != len(nombres):
        raise ValueError("nombres de solicitud repetidos")
    with ThreadPoolExecutor(max_workers=max(1, int(hilos))) as grupo:
        futuros = {s.nombre: grupo.submit(cliente.paginas, s.servicio, s.ruta, s.params) for s in solicitudes}
    resultados, errores = {}, {}
    for nombre, futuro in futuros.items():
        try:
            resultados[nombre] = futuro.result()
        except (ErrorAlpaca, OSError, ValueError) as error:
            errores[nombre] = str(error)
    return resultados, errores


# ---------------------------------------------------------------------------
# Crudo y manifiestos
# ---------------------------------------------------------------------------


def directorio_crudo(raiz_datos) -> Path:
    return Path(raiz_datos) / "raw" / "alpaca"


def guardar_respuestas(resultados, tipos, raiz_datos) -> dict:
    """Guarda cada página como crudo inmutable (gzip); devuelve las entradas del manifiesto por solicitud.

    ``sha256`` identifica el archivo guardado y ``sha256_contenido`` el cuerpo
    original: la lectura comprueba los dos.
    """
    raiz_datos = Path(raiz_datos)
    salida = {}
    for nombre in sorted(resultados):
        paginas = []
        for i, r in enumerate(resultados[nombre], start=1):
            comprimido = gzip.compress(r.cuerpo, compresslevel=9, mtime=0)
            info = almacen.guardar_crudo_bytes(comprimido, f"{nombre}_p{i}.json.gz", directorio_crudo(raiz_datos))
            paginas.append({
                "servicio": r.servicio, "ruta": r.ruta, "params": dict(r.params), "pagina": i,
                "estado": r.estado, "cabeceras": r.cabeceras, "enviado_utc": iso(r.enviado_utc),
                "recibido_utc": iso(r.recibido_utc), "intentos": r.intentos,
                "archivo": Path(info["ruta"]).relative_to(raiz_datos).as_posix(), "sha256": info["sha256"],
                "bytes": info["bytes"], "sha256_contenido": almacen.sha256_bytes(r.cuerpo),
                "bytes_contenido": len(r.cuerpo)})
        salida[nombre] = {"tipo": tipos[nombre], "paginas": paginas}
    return salida


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


def ruta_manifiesto(raiz_datos, fecha, etiqueta) -> Path:
    return directorio_crudo(raiz_datos) / "capturas" / str(fecha) / f"{etiqueta}.json"


def escribir_manifiesto(manifiesto: dict, raiz_datos) -> Path:
    """Escribe el manifiesto de una captura en solo lectura; nunca sobrescribe uno existente."""
    ruta = ruta_manifiesto(raiz_datos, manifiesto["fecha"], manifiesto["etiqueta"])
    if ruta.exists():
        raise FileExistsError(f"{ruta} ya existe: una captura no se sobrescribe")
    almacen.escribir_json(manifiesto, ruta)
    os.chmod(ruta, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return ruta


def capturar(cliente: ClienteAlpaca, solicitudes, raiz_datos, meta: dict, previas=None, hilos=8):
    """Ejecuta una captura, guarda crudo y manifiesto y devuelve ``(manifiesto, ruta)``.

    ``meta`` trae al menos ``fecha`` (sesión), ``hora``, ``corte_utc`` y
    ``etiqueta``; ``previas`` son entradas ya guardadas (p. ej., los contratos
    del día) que se incluyen para que el manifiesto se normalice por sí solo.
    """
    inicio = cliente.reloj()
    resultados, errores = ejecutar(cliente, solicitudes, hilos)
    fin = cliente.reloj()
    entradas = dict(previas or {})
    entradas.update(guardar_respuestas(resultados, {s.nombre: s.tipo for s in solicitudes}, raiz_datos))
    corte = pd.Timestamp(meta["corte_utc"])
    tardias = [p["archivo"] for e in entradas.values() if e["tipo"] in ("cadena", "acciones")
               for p in e["paginas"] if pd.Timestamp(p["recibido_utc"]) > corte]
    manifiesto = {"proveedor": PROVEEDOR, "version_adaptador": VERSION_ADAPTADOR, "cuenta": cliente.cuenta,
                  **meta, "inicio_utc": iso(inicio), "fin_utc": iso(fin), "solicitudes": entradas,
                  "errores": errores, "respuestas_despues_del_corte": tardias}
    return manifiesto, escribir_manifiesto(manifiesto, raiz_datos)


def leer_manifiestos(raiz_datos, desde=None, hasta=None) -> list[dict]:
    """Manifiestos de captura entre dos fechas de sesión (incluidas), en orden de ruta."""
    base = directorio_crudo(raiz_datos) / "capturas"
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
                      "feed": feed, "fuente_precio": fuente, "captura": captura})
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


def tablas_para_piloto(raiz_datos, desde=None, hasta=None, cfg_implicito=None, reglas=None):
    """Cotizaciones y subyacente normalizados, con el subyacente implícito si se configura.

    ``cfg_implicito`` es la sección ``[implicito]`` de la configuración de
    captura; ``reglas`` son las reglas de calidad del piloto. Devuelve
    ``(cotizaciones, subyacente, resumenes, fallos_implicito, manifiestos)``.
    """
    cot, sub, resumenes, manifiestos = normalizar(raiz_datos, desde, hasta)
    fallos = []
    if cfg_implicito and len(cot):
        c = cfg_implicito
        capturas = [(m["etiqueta"], m["fecha"], m["corte_utc"]) for m in manifiestos]
        imp, fallos = implicito.subyacente_implicito(
            cot, capturas, c["raiz"], c["subyacente"], float(c["tasa"]), float(c["rendimiento_dividendo"]),
            reglas or cadenas.ReglasCalidad(), int(c["minimo_pares"]), float(c["dias_max"]))
        partes = [t for t in (sub, imp) if len(t)]
        if partes:
            sub = pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]
            sub = sub.sort_values(["sello_snapshot_utc", "subyacente"], kind="stable").reset_index(drop=True)
    return cot, sub, resumenes, fallos, manifiestos


def esperar_hasta(objetivo_utc, reloj=None, dormir=time.sleep, paso_max=30.0):
    """Duerme hasta ``objetivo_utc`` en pasos cortos (tolera ajustes del reloj)."""
    reloj = reloj or _ahora
    objetivo_utc = pd.Timestamp(objetivo_utc)
    while True:
        faltan = (objetivo_utc - reloj()).total_seconds()
        if faltan <= 0:
            return
        dormir(min(faltan, paso_max))
