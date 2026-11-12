"""Interfaz local del simulador. Ejecutar: python scripts/simulador_opciones.py."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from pathlib import Path
import sys
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from quantileflow.simulador import ConfiguracionSimulador, simular
from quantileflow.duelo import comparar_dos
from quantileflow.observadas import (ConfiguracionObservada, cargar_tablas,
                                    preparar_observadas, simular_observadas)

ARCHIVOS = {"/": ("index.html", "text/html"),
            "/observadas": ("observadas.html", "text/html"),
            "/observadas.js": ("observadas.js", "text/javascript"),
            "/duelo.js": ("duelo.js", "text/javascript"),
            "/app.js": ("app.js", "text/javascript"),
            "/style.css": ("style.css", "text/css")}


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    foto_observada = None

    def server_bind(self):
        # Windows permite compartir un puerto con SO_REUSEADDR. Evitar servir
        # accidentalmente otra aplicación local cuando el puerto está ocupado.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):
        pass  # No se registran las entradas del usuario.

    def responder(self, status, cuerpo, tipo="application/json"):
        contenido = (json.dumps(cuerpo, ensure_ascii=False, allow_nan=False).encode("utf-8")
                     if tipo == "application/json" else cuerpo)
        self.send_response(status)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(contenido)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(contenido)

    def autoridad_valida(self):
        puerto = self.server.server_port
        return self.headers.get("Host") in (f"127.0.0.1:{puerto}", f"localhost:{puerto}")

    def do_GET(self):
        if not self.autoridad_valida():
            return self.responder(403, {"error": "Solo acceso local"})
        ruta = urlsplit(self.path).path
        if ruta not in ARCHIVOS:
            return self.responder(404, {"error": "Ruta no disponible"})
        nombre, tipo = ARCHIVOS[ruta]
        self.responder(200, (RAIZ / "apps" / "simulador" / nombre).read_bytes(), tipo)

    def do_POST(self):
        if not self.autoridad_valida():
            return self.responder(403, {"error": "Solo acceso local"})
        if self.path not in ("/api/simular", "/api/comparar-dos", "/api/observadas"):
            return self.responder(404, {"error": "Ruta no disponible"})
        origen = self.headers.get("Origin")
        if origen and origen != "http://" + self.headers["Host"]:
            return self.responder(403, {"error": "Origen no permitido"})
        if self.headers.get_content_type() != "application/json":
            return self.responder(415, {"error": "Se requiere application/json"})
        try:
            largo = int(self.headers.get("Content-Length", "0"))
            if not 0 < largo <= 8192:
                return self.responder(413, {"error": "Tamaño de petición inválido"})
            datos = json.loads(self.rfile.read(largo).decode("utf-8"))
            if self.path == "/api/observadas":
                if self.server.foto_observada is None:
                    return self.responder(409, {"error": "No hay captura cargada. Inicia el servidor con --tablas-observadas y --fecha-observada."})
                if not isinstance(datos, dict) or set(datos) - {"configuracion", "alternativas"} or "configuracion" not in datos:
                    raise ValueError("Indica configuración observada y, opcionalmente, dos alternativas")
                cfg = ConfiguracionObservada.desde_dict(datos["configuracion"])
            elif self.path == "/api/comparar-dos":
                if not isinstance(datos, dict) or set(datos) != {"configuracion", "alternativas"}:
                    raise ValueError("Indica configuración y dos alternativas")
                cfg = ConfiguracionSimulador.desde_dict(datos["configuracion"])
            else:
                cfg = ConfiguracionSimulador.desde_dict(datos)
        except (ValueError, TypeError, UnicodeError) as exc:
            return self.responder(400, {"error": str(exc)})
        try:
            if self.path == "/api/observadas":
                resultado = simular_observadas(self.server.foto_observada, cfg, datos.get("alternativas"))
            elif self.path == "/api/simular":
                resultado = simular(cfg)
            else:
                resultado = comparar_dos(cfg, datos["alternativas"])
        except ValueError as exc:
            return self.responder(400, {"error": str(exc)})
        except Exception:
            return self.responder(500, {"error": "No se pudo calcular; no se muestran resultados anteriores"})
        self.responder(200, resultado)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=8791)
    parser.add_argument("--tablas-observadas", type=Path)
    parser.add_argument("--fecha-observada", help="YYYY-MM-DD de la captura histórica")
    parser.add_argument("--hora-observada", default="09:45")
    parser.add_argument("--subyacente-observado", choices=("SPX", "SPY"), default="SPX",
                        help="SPX: calls SPXW europeos. SPY: calls americanos con los dividendos conocidos al corte")
    args = parser.parse_args()
    if not 1 <= args.puerto <= 65535:
        parser.error("puerto fuera de rango")
    if bool(args.tablas_observadas) != bool(args.fecha_observada):
        parser.error("Indica tanto tablas como fecha observada")
    foto = None
    if args.tablas_observadas:
        spy = args.subyacente_observado == "SPY"
        cotizaciones, referencias, *dividendos = cargar_tablas(args.tablas_observadas, con_dividendos=spy)
        foto = preparar_observadas(cotizaciones, referencias, args.fecha_observada, args.hora_observada,
                                   args.subyacente_observado, dividendos[0] if spy else None)
    servidor = Servidor(("127.0.0.1", args.puerto), Handler)
    servidor.foto_observada = foto
    print(f"QuantileFlow | http://127.0.0.1:{servidor.server_port} | sintético + histórico: {foto['captura'] + ' ' + foto['subyacente'] if foto else 'sin cargar'}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
