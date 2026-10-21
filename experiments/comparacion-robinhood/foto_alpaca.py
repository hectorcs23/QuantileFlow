"""Foto en vivo de Alpaca para los contratos de ``instrumentos.json``.

Se corre a la vez que get_option_quotes de Robinhood, para comparar bid y ask. Las claves salen del
entorno (``APCA_API_KEY_ID``, ``APCA_API_SECRET_KEY``) y no se escriben en ningún lado. La salida tiene
cotizaciones: va a la rama privada ``robinhood``, nunca al repositorio público.

Uso::

    python experiments/comparacion-robinhood/foto_alpaca.py --instrumentos PRIVADO/<fecha>/instrumentos.json \
        --salida PRIVADO/<fecha>/crudo/alpaca_vivo.json
"""
import argparse
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from quantileflow import alpaca  # noqa: E402

RUTA = "/v1beta1/options/snapshots"


def cotizaciones(cuerpo: dict) -> dict:
    """{símbolo: bid, ask, tamaños, bolsas y hora de la cotización} de una respuesta de snapshots."""
    salida = {}
    for simbolo, s in sorted((cuerpo.get("snapshots") or {}).items()):
        q = s.get("latestQuote") or {}
        salida[simbolo] = {"bid": q.get("bp"), "ask": q.get("ap"), "bid_size": q.get("bs"), "ask_size": q.get("as"),
                           "bolsa_bid": q.get("bx"), "bolsa_ask": q.get("ax"), "t": q.get("t")}
    return salida


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--instrumentos", type=Path, required=True, help="instrumentos.json del día")
    p.add_argument("--feed", default="indicative", choices=("indicative", "opra"))
    p.add_argument("--salida", type=Path, required=True)
    a = p.parse_args()
    simbolos = sorted(json.loads(a.instrumentos.read_text(encoding="utf-8"))["instrumentos"])
    cliente = alpaca.ClienteAlpaca(alpaca.Credenciales.del_entorno())
    r = cliente.get("datos", RUTA, {"symbols": ",".join(simbolos), "feed": a.feed})
    foto = {"fuente": f"Alpaca {RUTA}, feed {a.feed}, cuenta {cliente.cuenta}",
            "enviado_utc": alpaca.iso(r.enviado_utc), "recibido_utc": alpaca.iso(r.recibido_utc),
            "cotizaciones": cotizaciones(r.json())}
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(foto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    faltan = sorted(set(simbolos) - set(foto["cotizaciones"]))
    print(f"{len(foto['cotizaciones'])} de {len(simbolos)} contratos; recibido {foto['recibido_utc']}"
          + (f"; faltan {faltan}" if faltan else ""))


if __name__ == "__main__":
    main()
