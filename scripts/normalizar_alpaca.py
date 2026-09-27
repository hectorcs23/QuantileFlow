"""Reconstruye desde el crudo las tablas de Alpaca de un rango de sesiones, listas para el piloto.

Uso, desde la raíz del repositorio::

    python scripts/normalizar_alpaca.py --desde 2026-09-28 --hasta 2026-11-13
    python scripts/piloto.py --cotizaciones data/normalized/alpaca/cotizaciones.parquet \
        --subyacente data/normalized/alpaca/subyacente.parquet \
        --dividendos data/normalized/alpaca/dividendos.parquet \
        --cobertura-dividendos data/normalized/alpaca/cobertura_dividendos.parquet \
        --fuente-objetivo alpaca/sip --desde 2026-09-28 --hasta 2026-11-06

El rango de la normalización debe cubrir también las sesiones finales de las
etiquetas (cinco sesiones después de la última del piloto).

Lee solo el crudo y sus manifiestos (comprobando hashes): capturas en vivo,
histórico SIP del objetivo y eventos corporativos. Añade el nivel implícito de
SPX y escribe cotizaciones, subyacente, versiones de dividendos y cobertura de
cada consulta de eventos, con un manifiesto de los
manifiestos usados, la configuración, los fallos del nivel implícito, el
entorno y los hashes de salida. Reprocesar el mismo crudo da los mismos bytes.
Un evento corporativo distinto de un dividendo en efectivo dentro del rango
detiene la normalización.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow import alpaca, almacen  # noqa: E402
from quantileflow.piloto import cargar_config  # noqa: E402


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--desde", required=True)
    a.add_argument("--hasta", required=True)
    a.add_argument("--datos", default=str(RAIZ / "data"))
    a.add_argument("--config", default=str(RAIZ / "configs" / "captura_alpaca.toml"))
    a.add_argument("--config-piloto", default=str(RAIZ / "configs" / "piloto.toml"))
    a.add_argument("--salida", default=None, help="por omisión, data/normalized/alpaca")
    args = a.parse_args()
    entorno = almacen.huella_entorno(RAIZ)
    datos = Path(args.datos)
    salida = Path(args.salida) if args.salida else datos / "normalized" / "alpaca"
    with open(args.config, "rb") as f:
        bruto = tomllib.load(f)
    piloto = cargar_config(args.config_piloto)
    t = alpaca.tablas_para_piloto(datos, args.desde, args.hasta, bruto.get("implicito"), piloto.reglas)
    if not t.manifiestos:
        print(f"no hay capturas entre {args.desde} y {args.hasta} en {datos}", file=sys.stderr)
        return 1
    tablas = {"cotizaciones": t.cotizaciones, "subyacente": t.subyacente, "dividendos": t.dividendos,
              "cobertura_dividendos": t.cobertura_dividendos}
    salidas = {nombre: almacen.escribir_tabla(tabla, salida / f"{nombre}.parquet") for nombre, tabla in tablas.items()}

    def usados(manifiestos, *campos):
        return [{"manifiesto": m["_ruta"], "sha256": almacen.sha256_archivo(datos / m["_ruta"]),
                 **{c: m.get(c) for c in campos}} for m in manifiestos]

    almacen.escribir_json({
        "desde": args.desde, "hasta": args.hasta,
        "config": {"version": bruto["captura"]["version"], "huella": almacen.huella_datos(bruto),
                   "piloto": piloto.version, "huella_piloto": piloto.huella},
        "capturas": usados(t.manifiestos, "etiqueta", "modo", "feed_opciones"),
        "historico": usados(t.manifiestos_historico, "etiqueta", "feed", "disponible_utc"),
        "eventos": usados(t.manifiestos_eventos, "etiqueta", "simbolos"),
        "resumenes": t.resumenes, "resumenes_historico": t.resumenes_historico,
        "implicito_no_identificado": t.fallos_implicito, "eventos_no_tratados": t.eventos_no_tratados,
        "entorno": entorno, "salidas": salidas,
    }, salida / "manifiesto_normalizacion.json")
    print(f"{len(t.manifiestos)} capturas, {len(t.manifiestos_historico)} cortes del histórico SIP y "
          f"{len(t.manifiestos_eventos)} consultas de eventos -> {len(t.cotizaciones)} cotizaciones, "
          f"{len(t.subyacente)} filas de subyacente, {len(t.dividendos)} versiones de dividendos y "
          f"{len(t.cobertura_dividendos)} consultas de eventos en {salida}")
    for f in t.fallos_implicito:
        print(f"  nivel implícito no identificado en {f['captura']}: {f['motivo']}")
    cortes = {(r["fecha"], r["hora"]) for r in t.resumenes_historico}
    for m in t.manifiestos:
        if m.get("modo") == "programada" and (m["fecha"], m["hora"]) not in cortes:
            print(f"  sin histórico SIP del objetivo en {m['etiqueta']}: ejecute scripts/historico_alpaca.py")
    for e in t.eventos_no_tratados:
        print(f"  evento corporativo fuera del rango, no tratado: {e['tipo']} de {e['simbolo']} el {e['fecha']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
