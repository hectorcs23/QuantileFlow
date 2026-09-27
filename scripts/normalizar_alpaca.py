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

Las **resoluciones** de dividendos (``--resoluciones``; por omisión,
``<datos>/resoluciones_dividendos.csv`` si existe) son evidencia registrada a
mano, con su fecha de conocimiento, que resuelve una discrepancia con el
proveedor (esquema ``contrato.RESOLUCIONES_DIVIDENDOS``). Son una entrada más:
el manifiesto registra el archivo y su hash, y el resumen de los dividendos
cuenta versiones, retiros, discrepancias y contradicciones con cada
normalización, para medir cuánto revisa el proveedor lo ya publicado.
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
    a.add_argument("--resoluciones", default=None,
                   help="resoluciones de dividendos (CSV); por omisión, <datos>/resoluciones_dividendos.csv si existe")
    args = a.parse_args()
    entorno = almacen.huella_entorno(RAIZ)
    datos = Path(args.datos)
    salida = Path(args.salida) if args.salida else datos / "normalized" / "alpaca"
    with open(args.config, "rb") as f:
        bruto = tomllib.load(f)
    piloto = cargar_config(args.config_piloto)
    ruta_res = Path(args.resoluciones) if args.resoluciones else datos / "resoluciones_dividendos.csv"
    if args.resoluciones and not ruta_res.is_file():
        print(f"no existe el archivo de resoluciones {ruta_res}", file=sys.stderr)
        return 1
    resoluciones = alpaca.cargar_resoluciones(ruta_res) if ruta_res.is_file() else None
    t = alpaca.tablas_para_piloto(datos, args.desde, args.hasta, bruto.get("implicito"), piloto.reglas,
                                  resoluciones=resoluciones)
    if not t.manifiestos:
        print(f"no hay capturas entre {args.desde} y {args.hasta} en {datos}", file=sys.stderr)
        return 1
    tablas = {"cotizaciones": t.cotizaciones, "subyacente": t.subyacente, "dividendos": t.dividendos,
              "cobertura_dividendos": t.cobertura_dividendos}
    salidas = {nombre: almacen.escribir_tabla(tabla, salida / f"{nombre}.parquet") for nombre, tabla in tablas.items()}

    resumen = alpaca.resumen_dividendos(t.dividendos, t.eventos_no_tratados)

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
        "resoluciones": ({"archivo": ruta_res.resolve().relative_to(datos.resolve()).as_posix()
                          if ruta_res.resolve().is_relative_to(datos.resolve()) else str(ruta_res),
                          "sha256": almacen.sha256_archivo(ruta_res), "filas": int(len(resoluciones))}
                         if resoluciones is not None else None),
        "resumenes": t.resumenes, "resumenes_historico": t.resumenes_historico,
        "dividendos": resumen,
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
    print(f"  dividendos: {resumen['versiones']} versiones de {resumen['dividendos']} eventos; retiros "
          f"{resumen['retiros_por_motivo'] or 'ninguno'}; discrepancias abiertas "
          f"{resumen['discrepancias_abiertas'] or 'ninguna'}"
          + (f" ({len(resoluciones)} resoluciones de {ruta_res})" if resoluciones is not None else ""))
    for e in t.eventos_no_tratados:
        if e["tipo"] in alpaca.NO_BLOQUEAN:
            veces = f", {e['veces']} veces hasta {e['ultima']}" if "veces" in e else ""
            print(f"  anotación: {e['tipo']} de {e['simbolo']} ({e['id']}) el {e['fecha']}{veces}")
        else:
            print(f"  evento corporativo fuera del rango, no tratado: {e['tipo']} de {e['simbolo']} el {e['fecha']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
