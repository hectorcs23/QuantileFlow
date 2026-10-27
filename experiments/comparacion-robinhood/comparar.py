"""Compara las capturas de Alpaca con datos de Robinhood obtenidos por su conector.

Robinhood da tres cosas que Alpaca no da gratis:

* el índice SPX real, en barras de un minuto;
* el precio marca de cada opción (punto medio de su bid y ask), en barras de 15 segundos del mismo día;
* el bid y el ask de cada opción, solo en vivo.

El conector solo lo ve Claude: sus respuestas se guardan tal cual en ``<privado>/<fecha>/crudo/`` y este
script las importa, las valida y las compara. ``<privado>`` es la rama ``robinhood`` de QuantileFlow-datos;
al repositorio público solo llegan agregados. Los pasos están en el README.
"""
import argparse
import json
import math
from pathlib import Path
import re
import statistics
import sys

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from quantileflow import alpaca  # noqa: E402

CADENA_SPXW = "7a7fa2b1-b65e-4c75-a0b3-7f62749bee0a"  # Robinhood: SPXW, liquidación PM
INDICE_SPX = "432fbbb8-b82c-454a-852d-eb85382c7066"
LOTE_HISTORICOS = 10  # máximo de contratos por llamada de get_option_historicals
DESFASE_MAXIMO_S = 5.0  # foto en vivo: entre el updated_at más reciente de Robinhood y el envío a Alpaca
CAMPOS_COTIZACION = {"bid": "bid_price", "ask": "ask_price", "bid_size": "bid_size", "ask_size": "ask_size",
                     "marca": "mark_price", "iv": "implied_volatility", "delta": "delta", "vega": "vega"}


def _resumen(valores):
    if not valores:
        return {"n": 0}
    return {"n": len(valores), "media": statistics.fmean(valores), "mediana": statistics.median(valores),
            "desviacion": statistics.pstdev(valores), "max_abs": max(abs(v) for v in valores)}


def _rfc3339(instante) -> str:
    return pd.Timestamp(instante).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _hora_ny(instante) -> str:
    return pd.Timestamp(instante).tz_convert("America/New_York").strftime("%H:%M")


def _leer(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def _escribir(ruta: Path, contenido):
    """JSON con sangría, pero cada lista de números en una línea (las barras [o, h, l, c])."""
    texto = re.sub(r"\[\s+([^\[\]{}\"]*?)\s+\]",
                   lambda m: "[" + ", ".join(v.strip() for v in m.group(1).split(",")) + "]",
                   json.dumps(contenido, ensure_ascii=False, indent=1))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto + "\n", encoding="utf-8")


def simbolo_occ(raiz, vencimiento, tipo, strike) -> str:
    """Símbolo OCC sin espacios, como lo usa Alpaca: ``SPXW261120P07725000``."""
    return f"{raiz}{pd.Timestamp(vencimiento):%y%m%d}{tipo[0].upper()}{round(float(strike) * 1000):08d}"


def fuera_del_dinero(simbolo: str, nivel: float) -> bool:
    """Put con strike bajo el nivel o call con strike sobre él (símbolo OCC sin espacios)."""
    tipo, strike = simbolo[-9], int(simbolo[-8:]) / 1000
    return strike < nivel if tipo == "P" else strike > nivel


# ---------------------------------------------------------------------------
# Qué pedir a Robinhood
# ---------------------------------------------------------------------------


def plan(resumen: dict, instrumentos=None, paso=100, lado=3, dias_objetivo=30) -> dict:
    """Contratos y ventanas que hay que pedir a Robinhood para un día de captura.

    ``resumen``: el ``resumen.json`` de ``scripts/verificar_alpaca.py``. Vencimiento: el del par de SPXW
    del plazo constante más cercano a ``dias_objetivo`` días (si empatan, el más lejano). Strikes: el
    múltiplo de 25 más cercano al primer nivel implícito, ± ``paso`` × 1..``lado``, call y put. Las
    ventanas salen de ``corte_utc``, así que siguen el horario de verano. Con ``instrumentos``
    ({símbolo: id}) agrega los ids en lotes para las llamadas.
    """
    capturas = [c for c in resumen["capturas"] if (c.get("spot_spx_implicito") or {}).get("estado") == "identificado"]
    if not capturas:
        return {"fecha": resumen["fecha"], "motivo": "sin nivel implícito identificado"}
    primera, fecha = capturas[0], pd.Timestamp(resumen["fecha"])
    par = ((primera["raices"].get("SPXW") or {}).get("plazo_constante_30d") or {}).get("vencimientos") or []
    if not par:
        return {"fecha": resumen["fecha"], "motivo": "sin vencimientos de SPXW a 30 días"}
    vencimiento = min(par, key=lambda v: (abs((pd.Timestamp(v) - fecha).days - dias_objetivo), -pd.Timestamp(v).value))
    centro = 25 * round(primera["spot_spx_implicito"]["spot"] / 25)
    strikes = [centro + paso * j for j in range(-lado, lado + 1)]
    cortes = {c["hora"]: pd.Timestamp(c["corte_utc"]) for c in resumen["capturas"]}
    salida = {"fecha": resumen["fecha"], "vencimiento": vencimiento, "nivel": primera["spot_spx_implicito"]["spot"],
              "strikes": strikes,
              "simbolos": [simbolo_occ("SPXW", vencimiento, t, k) for k in strikes for t in ("call", "put")],
              "instrumentos": [{"chain_id": CADENA_SPXW, "expiration_dates": vencimiento,
                                "strike_price": f"{k:.4f}"} for k in strikes],
              "spx": {"instrument_ids": [INDICE_SPX], "interval": "minute",
                      "start_time": _rfc3339(min(cortes.values()) - pd.Timedelta(minutes=5)),
                      "end_time": _rfc3339(max(cortes.values()) + pd.Timedelta(minutes=1))},
              "barras": {h: {"interval": "15second", "bounds": "regular",
                             "start_time": _rfc3339(t - pd.Timedelta(seconds=15)),
                             "end_time": _rfc3339(t + pd.Timedelta(seconds=15))} for h, t in cortes.items()}}
    if instrumentos:
        ids = [instrumentos[s] for s in salida["simbolos"] if s in instrumentos]
        salida["lotes"] = [ids[i:i + LOTE_HISTORICOS] for i in range(0, len(ids), LOTE_HISTORICOS)]
    return salida


# ---------------------------------------------------------------------------
# Importación de las respuestas del conector (``data`` de cada herramienta)
# ---------------------------------------------------------------------------


def _ohlc(apertura, alto, bajo, cierre, que) -> list[float]:
    o, h, l, c = (float(v) for v in (apertura, alto, bajo, cierre))
    if not l <= min(o, c) <= max(o, c) <= h:
        raise ValueError(f"{que}: barra incoherente {[o, h, l, c]}")
    return [o, h, l, c]


def importar_instrumentos(instrumentos: list, esperados=None) -> dict:
    """{símbolo OCC: id} de get_option_instruments (``data.instruments`` de una o varias llamadas)."""
    salida = {}
    for i in instrumentos:
        simbolo = simbolo_occ(i["chain_symbol"], i["expiration_date"], i["type"], i["strike_price"])
        if salida.setdefault(simbolo, i["id"]) != i["id"]:
            raise ValueError(f"{simbolo}: dos ids distintos")
    if esperados is not None:
        if faltan := sorted(set(esperados) - set(salida)):
            raise ValueError(f"faltan instrumentos: {faltan}")
        salida = {s: salida[s] for s in esperados}
    return dict(sorted(salida.items()))


def importar_barras(resultados: list, instrumentos: dict, corte_utc) -> dict:
    """Barras de 15 s de get_option_historicals (``data.results``) en el formato de comparar_opciones.

    Comprueba que cada id corresponda a su símbolo en ``instrumentos``, que las barras sean coherentes y
    que sean del día y del corte. Las barras interpoladas (relleno sin información nueva) se cuentan y se
    descartan.
    """
    corte = pd.Timestamp(corte_utc).tz_convert("UTC")
    simbolos = {v: k for k, v in instrumentos.items()}
    barras, interpoladas = {}, 0
    for r in resultados:
        simbolo = r["occ_symbol"].replace(" ", "")
        if simbolos.get(r["instrument_id"]) != simbolo:
            raise ValueError(f"{r['instrument_id']}: no es {simbolo} según instrumentos.json")
        if r.get("interval") != "15second":
            raise ValueError(f"{simbolo}: intervalo {r.get('interval')!r}, se esperaba 15second")
        interpoladas += sum(bool(b.get("interpolated")) for b in r["bars"])
        barras[simbolo] = {}
        for b in r["bars"]:
            t = pd.Timestamp(b["begins_at"]).tz_convert("UTC")
            if abs(t - corte) > pd.Timedelta(minutes=5):
                raise ValueError(f"{simbolo}: barra de {t}, lejos del corte {corte}")
            if not b.get("interpolated"):
                barras[simbolo][t.strftime("%H:%M:%S")] = _ohlc(
                    b["open_price"], b["high_price"], b["low_price"], b["close_price"], simbolo)
    return {"fuente": "Robinhood get_option_historicals, interval 15second, bounds regular; barras etiquetadas "
                      "por su inicio (UTC); [open, high, low, close]",
            "corte_utc": _rfc3339(corte_utc), "interpoladas": interpoladas, "barras": dict(sorted(barras.items()))}


def importar_spx(resultados: list) -> dict:
    """Barras de un minuto del SPX de get_index_historicals (``data.results``): {fecha: {"HH:MM": [o, h, l, c]}}."""
    salida = {}
    for r in resultados:
        if r.get("symbol") != "SPX" or r.get("interval") != "minute":
            raise ValueError(f"se esperaban barras de un minuto del SPX: {r.get('symbol')!r}, {r.get('interval')!r}")
        for b in r["bars"]:
            if b.get("interpolated"):
                continue
            t = pd.Timestamp(b["begins_at"]).tz_convert("UTC")
            salida.setdefault(t.strftime("%Y-%m-%d"), {})[t.strftime("%H:%M")] = _ohlc(
                b["open_value"], b["high_value"], b["low_value"], b["close_value"], f"SPX {t}")
    return salida


def importar_cotizaciones(resultados: list, instrumentos: dict) -> dict:
    """Cotizaciones en vivo de get_option_quotes (``data.results``): {símbolo OCC: bid, ask, marca...}.

    La marca de Robinhood es el punto medio: si no lo es, se supone un error al copiar la respuesta.
    """
    simbolos = {v: k for k, v in instrumentos.items()}
    salida = {}
    for r in resultados:
        q = r.get("quote") or r
        if (simbolo := simbolos.get(q["instrument_id"])) is None:
            raise ValueError(f"{q['instrument_id']}: no está en instrumentos.json")
        fila = {k: None if q.get(v) is None else float(q[v]) for k, v in CAMPOS_COTIZACION.items()}
        fila["actualizado_utc"] = q["updated_at"]
        if not 0 <= fila["bid"] <= fila["ask"]:
            raise ValueError(f"{simbolo}: bid {fila['bid']} y ask {fila['ask']} incoherentes")
        if fila["bid"] > 0 and abs(fila["marca"] - 0.5 * (fila["bid"] + fila["ask"])) > 0.0051:
            raise ValueError(f"{simbolo}: la marca {fila['marca']} no es el punto medio")
        salida[simbolo] = fila
    return dict(sorted(salida.items()))


def importar(privado: Path, resumen: dict) -> list[str]:
    """Importa lo que haya en ``<privado>/<fecha>/crudo/``; devuelve qué se escribió."""
    fecha = resumen["fecha"]
    carpeta, crudo, hecho = privado / fecha, privado / fecha / "crudo", []
    if (lista := _leer(crudo / "instrumentos.json")) is not None:
        p = plan(resumen)
        _escribir(carpeta / "instrumentos.json", {
            "fuente": f"Robinhood get_option_instruments, cadena SPXW {CADENA_SPXW}", "vencimiento": p["vencimiento"],
            "instrumentos": importar_instrumentos(lista, p["simbolos"])})
        hecho.append("instrumentos.json")
    instrumentos = (_leer(carpeta / "instrumentos.json") or {}).get("instrumentos", {})
    for c in resumen["capturas"]:
        nombre = f"barras_{c['hora'].replace(':', '')}.json"
        if (resultados := _leer(crudo / nombre)) is not None:
            _escribir(carpeta / nombre, importar_barras(resultados, instrumentos, c["corte_utc"]))
            hecho.append(nombre)
    if (resultados := _leer(crudo / "spx.json")) is not None:
        ruta = privado / "spx_minutos.json"
        spx = _leer(ruta) or {"fuente": f"Robinhood get_index_historicals, SPX {INDICE_SPX}, interval minute, barras "
                                        "etiquetadas por su inicio (UTC); [open, high, low, close]", "barras": {}}
        for dia, barras in importar_spx(resultados).items():
            spx["barras"].setdefault(dia, {}).update(barras)
        spx["barras"] = {d: dict(sorted(b.items())) for d, b in sorted(spx["barras"].items())}
        _escribir(ruta, spx)
        hecho.append("spx_minutos.json")
    rh, alp = _leer(crudo / "cotizaciones.json"), _leer(crudo / "alpaca_vivo.json")
    if rh is not None and alp is not None:
        cotizaciones = importar_cotizaciones(rh, instrumentos)
        ultima = max(pd.Timestamp(q["actualizado_utc"]) for q in cotizaciones.values())
        if abs(desfase := (pd.Timestamp(alp["enviado_utc"]) - ultima).total_seconds()) > DESFASE_MAXIMO_S:
            raise ValueError(f"la foto de Alpaca salió {desfase:+.1f} s después de la última cotización de "
                             "Robinhood: no están pareadas")
        _escribir(carpeta / "vivo.json", {
            "robinhood": {"fuente": "Robinhood get_option_quotes", "cotizaciones": cotizaciones},
            "alpaca": alp})
        hecho.append("vivo.json")
    return hecho


# ---------------------------------------------------------------------------
# Comparaciones
# ---------------------------------------------------------------------------


def minuto_del_sello(captura: dict) -> str:
    """Minuto UTC ("HH:MM") de la barra del SPX que contiene el sello del nivel implícito.

    Sin sello, el minuto anterior al corte. Sale de los instantes UTC de los datos, así que vale
    con y sin horario de verano.
    """
    sello = (captura.get("spot_spx_implicito") or {}).get("sello_evento_utc")
    instante = pd.Timestamp(sello) if sello else pd.Timestamp(captura["corte_utc"]) - pd.Timedelta(minutes=1)
    return instante.tz_convert("UTC").floor("min").strftime("%H:%M")


def comparar_spx(barras: dict, resumenes: list[dict]) -> dict:
    """Nivel implícito de cada corte frente a la barra de un minuto del SPX que contiene su sello.

    ``barras``: {fecha: {"HH:MM": [open, high, low, close]}}. ``resumenes``: los
    ``resumen.json`` de ``scripts/verificar_alpaca.py``. La diferencia es implícito
    menos el cierre del minuto; ``dentro`` dice si el implícito cae en [low, high].
    """
    filas = []
    for r in resumenes:
        for c in r["capturas"]:
            nivel = c.get("spot_spx_implicito") or {}
            if nivel.get("estado") != "identificado":
                continue
            b = (barras.get(r["fecha"]) or {}).get(minuto_del_sello(c))
            if not b:
                continue
            _, alto, bajo, cierre = b
            filas.append({"fecha": r["fecha"], "hora": c["hora"], "diferencia": nivel["spot"] - cierre,
                          "dentro": bajo <= nivel["spot"] <= alto, "rango_minuto": alto - bajo,
                          "error_forward": nivel.get("forward_error")})
    return {"cortes": filas, "diferencia": _resumen([f["diferencia"] for f in filas]),
            "dentro_del_minuto": sum(f["dentro"] for f in filas)}


def cotizaciones_alpaca(datos, fecha, hora, simbolos) -> dict:
    """Última cotización indicative de cada símbolo en la captura de ``fecha`` y ``hora``."""
    simbolos = set(simbolos)
    for m in alpaca.leer_manifiestos(datos, fecha, fecha):
        if m.get("hora") != hora or m.get("modo") == "inmediata":
            continue
        corte = pd.Timestamp(m["corte_utc"])
        salida = {}
        for e in m["solicitudes"].values():
            if e["tipo"] != "cadena":
                continue
            for p in e["paginas"]:
                for simbolo, s in (alpaca.leer_crudo(datos, p).get("snapshots") or {}).items():
                    q = s.get("latestQuote") or {}
                    if simbolo in simbolos and q.get("bp") is not None and q.get("ap") is not None:
                        salida[simbolo] = {"bid": float(q["bp"]), "ask": float(q["ap"]),
                                           "edad_s": (corte - pd.Timestamp(q["t"])).total_seconds()}
        return salida
    return {}


def comparar_opciones(barras_rh: dict, alpaca_q: dict, nivel=None, edad_maxima_s=60.0) -> dict:
    """Mid de Alpaca frente a la marca de Robinhood al cierre de la barra de 15 s anterior al corte.

    ``barras_rh``: el JSON de barras de un corte. La diferencia en medios spreads
    usa el spread de Alpaca; ``dentro_del_spread`` dice si la marca cae en
    [bid, ask] de Alpaca. Con ``nivel`` (el SPX implícito del corte) se separan
    las opciones fuera del dinero, que son las que usa el piloto.
    """
    corte = pd.Timestamp(barras_rh["corte_utc"])
    previa = (corte - pd.Timedelta(seconds=15)).strftime("%H:%M:%S")
    filas = []
    for simbolo, bs in sorted(barras_rh["barras"].items()):
        q, b = alpaca_q.get(simbolo), bs.get(previa)
        if q is None or b is None or not 0 < q["bid"] <= q["ask"]:
            continue
        marca = b[3]
        mid, medio = 0.5 * (q["bid"] + q["ask"]), 0.5 * (q["ask"] - q["bid"])
        filas.append({"simbolo": simbolo, "diferencia": mid - marca,
                      "diferencia_relativa": (mid - marca) / marca,
                      "en_medios_spreads": (mid - marca) / medio if medio > 0 else None,
                      "dentro_del_spread": q["bid"] <= marca <= q["ask"], "spread_alpaca": q["ask"] - q["bid"],
                      "edad_s": q["edad_s"], "fresca": q["edad_s"] <= edad_maxima_s,
                      "fuera_del_dinero": None if nivel is None else fuera_del_dinero(simbolo, nivel)})
    otm = [f for f in filas if f["fuera_del_dinero"]]
    return {"corte_utc": barras_rh["corte_utc"], "nivel": nivel, "contratos": filas,
            "diferencia": _resumen([f["diferencia"] for f in filas]),
            "diferencia_relativa": _resumen([f["diferencia_relativa"] for f in filas]),
            "en_medios_spreads": _resumen([f["en_medios_spreads"] for f in filas
                                           if f["en_medios_spreads"] is not None]),
            "dentro_del_spread": sum(f["dentro_del_spread"] for f in filas),
            "frescas": sum(f["fresca"] for f in filas),
            "fuera_del_dinero": {"n": len(otm), "diferencia": _resumen([f["diferencia"] for f in otm]),
                                 "diferencia_relativa": _resumen([f["diferencia_relativa"] for f in otm]),
                                 "dentro_del_spread": sum(f["dentro_del_spread"] for f in otm)}}


def _bloque_vivo(filas):
    return {"n": len(filas), "diferencia": _resumen([f["diferencia"] for f in filas]),
            "diferencia_relativa": _resumen([f["diferencia_relativa"] for f in filas]),
            "razon_spread": _resumen([f["razon_spread"] for f in filas if f["razon_spread"] is not None]),
            "igual": sum(f["igual"] for f in filas), "alpaca_contiene": sum(f["alpaca_contiene"] for f in filas),
            "marca_dentro": sum(f["marca_dentro"] for f in filas)}


def comparar_vivo(rh: dict, alp: dict) -> dict:
    """Bid y ask en vivo: Alpaca (indicative) frente a Robinhood, contrato por contrato.

    ``rh`` sale de importar_cotizaciones y ``alp`` de foto_alpaca.py. La diferencia es mid de Alpaca menos
    marca de Robinhood; ``razon_spread`` es el spread de Alpaca entre el de Robinhood; ``alpaca_contiene``
    dice si el bid y el ask de Alpaca encierran los de Robinhood. Fuera del dinero: |delta| < 0.5.
    """
    filas = []
    for simbolo, r in sorted(rh.items()):
        q = alp.get(simbolo) or {}
        if q.get("bid") is None or q.get("ask") is None or not 0 < q["bid"] <= q["ask"] or not 0 < r["bid"] <= r["ask"]:
            continue
        mid, spread_rh, spread_alp = 0.5 * (q["bid"] + q["ask"]), r["ask"] - r["bid"], q["ask"] - q["bid"]
        filas.append({"simbolo": simbolo, "diferencia": mid - r["marca"],
                      "diferencia_relativa": (mid - r["marca"]) / r["marca"],
                      "spread_robinhood": spread_rh, "spread_alpaca": spread_alp,
                      "razon_spread": spread_alp / spread_rh if spread_rh > 0 else None,
                      "igual": math.isclose(q["bid"], r["bid"], abs_tol=1e-6)
                      and math.isclose(q["ask"], r["ask"], abs_tol=1e-6),
                      "alpaca_contiene": q["bid"] <= r["bid"] + 1e-9 and r["ask"] <= q["ask"] + 1e-9,
                      "marca_dentro": q["bid"] <= r["marca"] <= q["ask"],
                      "desfase_s": (pd.Timestamp(q["t"]) - pd.Timestamp(r["actualizado_utc"])).total_seconds()
                      if q.get("t") else None,
                      "fuera_del_dinero": None if r.get("delta") is None else abs(r["delta"]) < 0.5})
    return {"contratos": filas, **_bloque_vivo(filas),
            "fuera_del_dinero": _bloque_vivo([f for f in filas if f["fuera_del_dinero"]])}


def resultados_dia(privado: Path, resumen: dict, datos=None) -> dict:
    """Las tres comparaciones de un día, con lo que haya importado en ``<privado>/<fecha>/``."""
    fecha = resumen["fecha"]
    carpeta, salida = privado / fecha, {"fecha": fecha}
    if spx := _leer(privado / "spx_minutos.json"):
        salida["spx"] = comparar_spx(spx["barras"], [resumen])
    niveles = {c["hora"]: (c.get("spot_spx_implicito") or {}).get("spot") for c in resumen["capturas"]}
    for ruta in sorted(carpeta.glob("barras_*.json")):
        if datos is None:
            raise ValueError("hay barras de opciones: hace falta --datos con las capturas de Alpaca")
        barras = _leer(ruta)
        hora = _hora_ny(barras["corte_utc"])
        q = cotizaciones_alpaca(datos, fecha, hora, barras["barras"])
        salida.setdefault("opciones", []).append({"hora": hora, **comparar_opciones(barras, q, niveles.get(hora))})
    if vivo := _leer(carpeta / "vivo.json"):
        salida["vivo"] = {"alpaca_recibido_utc": vivo["alpaca"]["recibido_utc"],
                          **comparar_vivo(vivo["robinhood"]["cotizaciones"], vivo["alpaca"]["cotizaciones"])}
    return salida


def _bloque_opciones(filas):
    return {"n": len(filas), "diferencia": _resumen([f["diferencia"] for f in filas]),
            "diferencia_relativa": _resumen([f["diferencia_relativa"] for f in filas]),
            "dentro_del_spread": sum(f["dentro_del_spread"] for f in filas)}


def acumulado(privado: Path) -> dict:
    """Agregados de todos los ``<fecha>/resultados.json``: lo que se publica."""
    dias = [_leer(p) for p in sorted(privado.glob("*/resultados.json"))]
    spx = [f for d in dias for f in (d.get("spx") or {}).get("cortes", [])]
    opciones = [f for d in dias for c in d.get("opciones", []) for f in c["contratos"]]
    vivo = [f for d in dias for f in (d.get("vivo") or {}).get("contratos", [])]
    return {"dias": len(dias),
            "spx": {"diferencia": _resumen([f["diferencia"] for f in spx]),
                    "dentro_del_minuto": sum(f["dentro"] for f in spx)},
            "opciones": {"dias": sum(bool(d.get("opciones")) for d in dias), "todas": _bloque_opciones(opciones),
                         "fuera_del_dinero": _bloque_opciones([f for f in opciones if f["fuera_del_dinero"]])},
            "vivo": {"dias": sum(bool(d.get("vivo")) for d in dias), "todas": _bloque_vivo(vivo),
                     "fuera_del_dinero": _bloque_vivo([f for f in vivo if f["fuera_del_dinero"]])}}


def _sin_contratos(informe):
    """El informe sin las filas por contrato (para la consola)."""
    if isinstance(informe, dict):
        return {k: _sin_contratos(v) for k, v in informe.items() if k != "contratos"}
    if isinstance(informe, list):
        return [_sin_contratos(v) for v in informe]
    return informe


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="orden", required=True)
    for nombre, ayuda in (("plan", "contratos y ventanas que hay que pedir a Robinhood"),
                          ("importar", "valida e importa las respuestas guardadas en <privado>/<fecha>/crudo/"),
                          ("dia", "compara un día y escribe <privado>/<fecha>/resultados.json")):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument("--verificacion", type=Path, required=True,
                       help="carpeta de scripts/verificar_alpaca.py del día (con resumen.json)")
        s.add_argument("--privado", type=Path, required=nombre != "plan", help="clon de la rama robinhood")
        if nombre == "dia":
            s.add_argument("--datos", type=Path, help="datos de Alpaca (hace falta si hay barras de opciones)")
    s = sub.add_parser("acumulado", help="agregados de todos los días")
    s.add_argument("--privado", type=Path, required=True)
    a = p.parse_args()
    if a.orden == "acumulado":
        print(json.dumps(acumulado(a.privado), ensure_ascii=False, indent=1))
        return
    resumen = json.loads((a.verificacion / "resumen.json").read_text(encoding="utf-8"))
    if a.orden == "plan":
        privado = a.privado / resumen["fecha"] / "instrumentos.json" if a.privado else None
        print(json.dumps(plan(resumen, ((_leer(privado) or {}).get("instrumentos") if privado else None)),
                         ensure_ascii=False, indent=1))
    elif a.orden == "importar":
        print("importado:", ", ".join(importar(a.privado, resumen)) or "nada")
    else:
        informe = resultados_dia(a.privado, resumen, a.datos)
        _escribir(a.privado / resumen["fecha"] / "resultados.json", informe)
        print(json.dumps(_sin_contratos(informe), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
