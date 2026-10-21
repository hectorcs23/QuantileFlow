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

ARCHIVOS = {"/": ("index.html", "text/html"),
            "/app.js": ("app.js", "text/javascript"),
            "/style.css": ("style.css", "text/css")}


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

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
        if self.path != "/api/simular":
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
            cfg = ConfiguracionSimulador.desde_dict(datos)
        except (ValueError, TypeError, UnicodeError) as exc:
            return self.responder(400, {"error": str(exc)})
        try:
            resultado = simular(cfg)
        except Exception:
            return self.responder(500, {"error": "No se pudo calcular; no se muestran resultados anteriores"})
        self.responder(200, resultado)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=8791)
    args = parser.parse_args()
    if not 1 <= args.puerto <= 65535:
        parser.error("puerto fuera de rango")
    servidor = Servidor(("127.0.0.1", args.puerto), Handler)
    print(f"QuantileFlow | http://127.0.0.1:{servidor.server_port} | datos sintéticos", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
