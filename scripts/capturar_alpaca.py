"""Captura diaria de cadenas de opciones en Alpaca a horas fijas de Nueva York.

Uso, desde la raíz del repositorio, una vez por sesión y antes de la primera hora::

    python scripts/capturar_alpaca.py            # espera y captura a las horas de la configuración
    python scripts/capturar_alpaca.py --ahora    # captura inmediata de prueba (también fuera de sesión)

Cada captura es una ráfaga de solicitudes en paralelo que empieza ``adelanto_s``
antes del corte, para que las respuestas lleguen antes de él. Guarda el crudo en
``data/raw/alpaca`` (inmutable, direccionado por SHA-256), un manifiesto por
captura en ``data/raw/alpaca/capturas/<fecha>/`` y las tablas normalizadas del
día en ``data/normalized/alpaca/diario/<fecha>/``. Lee las credenciales de
``APCA_API_KEY_ID`` y ``APCA_API_SECRET_KEY``; nunca las escribe.

Fuera de sesión, ``--ahora`` toma como sesión de referencia la última que ya
abrió y como corte el menor entre ahora y su cierre: sirve para verificar el
adaptador con cotizaciones reales, no como sesión del piloto.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import tomllib
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow import alpaca, almacen  # noqa: E402
from quantileflow.calendario import (NUEVA_YORK, apertura, calendario, cierre, es_sesion,  # noqa: E402
                                     instante)
from quantileflow.piloto import cargar_config  # noqa: E402


def cargar(ruta):
    with open(ruta, "rb") as f:
        return tomllib.load(f)


def sesion_de_referencia(ahora_utc, codigo):
    """Última sesión que ya abrió y el corte inmediato: min(ahora, cierre de esa sesión)."""
    cal = calendario(codigo)
    dia = pd.Timestamp(ahora_utc.tz_convert(NUEVA_YORK).date())
    if not es_sesion(dia, codigo):
        dia = cal.date_to_session(dia, direction="previous")
    elif apertura(dia, codigo) > ahora_utc:
        dia = cal.previous_session(dia)
    fecha = dia.date()
    return fecha, min(ahora_utc, cierre(fecha, codigo))


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--config", default=str(RAIZ / "configs" / "captura_alpaca.toml"))
    a.add_argument("--config-piloto", default=str(RAIZ / "configs" / "piloto.toml"))
    a.add_argument("--datos", default=str(RAIZ / "data"))
    a.add_argument("--ahora", action="store_true", help="captura inmediata de prueba")
    a.add_argument("--horas", nargs="*", help="sustituye las horas de la configuración (HH:MM)")
    args = a.parse_args()

    bruto = cargar(args.config)
    cfg = bruto["captura"]
    codigo = cfg["calendario"]
    datos = Path(args.datos)
    cliente = alpaca.ClienteAlpaca(alpaca.Credenciales.del_entorno(), reintentos=cfg["reintentos"],
                                   espera_max=cfg["espera_max_s"])
    info_config = {"ruta": Path(args.config).resolve().relative_to(RAIZ).as_posix()
                   if Path(args.config).resolve().is_relative_to(RAIZ) else args.config,
                   "version": cfg["version"], "huella": almacen.huella_datos(bruto)}

    # Reloj del servidor, antes de nada: el horario depende del reloj local.
    reloj, err = alpaca.ejecutar(cliente, [alpaca.pedir_reloj()], 1)
    if err:
        print(f"no se pudo consultar el reloj de Alpaca: {err}", file=sys.stderr)
        return 1
    estado_reloj = alpaca.reloj_servidor(reloj["reloj"][0])
    print(f"cuenta {cliente.cuenta}; desfase del reloj local {estado_reloj['desfase_s']:+.3f} s "
          f"(± {estado_reloj['incertidumbre_s']:.3f}); mercado abierto: {estado_reloj['mercado_abierto']}")
    if abs(estado_reloj["desfase_s"]) > 1.0:
        print("AVISO: el reloj local difiere más de 1 s del de Alpaca; los sellos locales quedan desplazados",
              file=sys.stderr)

    ahora = cliente.reloj()
    if args.ahora:
        fecha, corte_inmediato = sesion_de_referencia(ahora, codigo)
        planes = [("inmediata", corte_inmediato, f"{fecha}Tinmediata-{ahora:%H%M%S}")]
    else:
        fecha = ahora.tz_convert(NUEVA_YORK).date()
        if not es_sesion(fecha, codigo):
            print(f"{fecha} no es sesión de {codigo}: no hay captura")
            return 0
        planes, perdidas = [], 0
        for hora in args.horas or cfg["horas"]:
            corte, etiqueta = instante(fecha, hora, codigo), f"{fecha}T{hora.replace(':', '')}"
            if alpaca.ruta_manifiesto(datos, fecha, etiqueta).exists():
                print(f"{hora}: ya capturada hoy; se omite")
            elif corte - pd.Timedelta(seconds=cfg["adelanto_s"]) < ahora:
                print(f"{hora}: el corte ya pasó o está demasiado cerca; se pierde", file=sys.stderr)
                perdidas += 1
            else:
                planes.append((hora, corte, etiqueta))
        if not planes:
            return 1 if perdidas else 0

    # Contratos del día: metadatos para normalizar y para elegir vencimientos.
    desde, hasta = fecha, fecha + dt.timedelta(days=int(cfg["ventana_contratos_dias"]))
    pedidos = [alpaca.pedir_contratos(o["subyacente"], desde, hasta, o["raiz"]) for o in cfg["opciones"]]
    resultados, errores = alpaca.ejecutar(cliente, pedidos, cfg["hilos"])
    if errores:
        print(f"no se pudieron pedir los contratos: {errores}", file=sys.stderr)
        return 1
    tipos = {p.nombre: p.tipo for p in pedidos}
    tipos["reloj"] = "reloj"
    previas = alpaca.guardar_respuestas({**resultados, **reloj}, tipos, datos)
    meta = alpaca.metadatos_contratos(r.json() for rs in resultados.values() for r in rs)
    seleccion, solicitudes = {}, []
    for o in cfg["opciones"]:
        vencimientos = {c["expiration_date"] for c in meta.values() if c["root_symbol"] == o["raiz"]}
        elegidos, plazos = alpaca.elegir_vencimientos(
            vencimientos, alpaca.LIQUIDACION[o["raiz"]], planes[0][1], o["objetivo_dias"],
            o["vencimientos_por_lado"], o["cercano"], codigo=codigo)
        seleccion[o["raiz"]] = {"vencimientos": [str(v) for v in elegidos],
                                "dias": {str(v): round(plazos[v], 4) for v in elegidos}}
        print(f"{o['raiz']}: " + ", ".join(f"{v} ({plazos[v]:.1f} d)" for v in elegidos))
        solicitudes += [alpaca.pedir_cadena(o["raiz"], v, cfg["feed_opciones"]) for v in elegidos]
    solicitudes.append(alpaca.pedir_acciones(bruto["captura"]["acciones"]["simbolos"], cfg["feed_acciones"]))

    fallidas = 0
    for hora, corte, etiqueta in planes:
        if hora != "inmediata":
            inicio = corte - pd.Timedelta(seconds=cfg["adelanto_s"])
            print(f"{hora}: esperando hasta {inicio.tz_convert(NUEVA_YORK):%H:%M:%S} (Nueva York)")
            alpaca.esperar_hasta(inicio, cliente.reloj)
        m = {"fecha": str(fecha), "hora": hora, "corte_utc": alpaca.iso(corte), "etiqueta": etiqueta,
             "modo": "inmediata" if hora == "inmediata" else "programada", "feed_opciones": cfg["feed_opciones"],
             "feed_acciones": cfg["feed_acciones"], "adelanto_s": cfg["adelanto_s"], "config": info_config,
             "seleccion": seleccion, "reloj": estado_reloj, "codigo": almacen.estado_git(RAIZ)}
        try:
            manifiesto, ruta = alpaca.capturar(cliente, solicitudes, datos, m, previas, cfg["hilos"])
        except FileExistsError as error:
            print(f"{hora}: {error}", file=sys.stderr)
            fallidas += 1
            continue
        duracion = (pd.Timestamp(manifiesto["fin_utc"]) - pd.Timestamp(manifiesto["inicio_utc"])).total_seconds()
        n = sum(len(e["paginas"]) for e in manifiesto["solicitudes"].values())
        print(f"{hora}: {n} respuestas en {duracion:.2f} s; después del corte: "
              f"{len(manifiesto['respuestas_despues_del_corte'])}; errores: {len(manifiesto['errores'])} -> "
              f"{ruta.relative_to(datos)}")
        if manifiesto["errores"] or (hora != "inmediata" and manifiesto["respuestas_despues_del_corte"]):
            fallidas += 1

    # Tablas normalizadas del día, reconstruidas desde el crudo.
    piloto = cargar_config(args.config_piloto)
    cot, sub, resumenes, fallos, _ = alpaca.tablas_para_piloto(datos, fecha, fecha, bruto.get("implicito"),
                                                               piloto.reglas)
    salida = datos / "normalized" / "alpaca" / "diario" / str(fecha)
    hashes = {"cotizaciones.parquet": almacen.escribir_tabla(cot, salida / "cotizaciones.parquet"),
              "subyacente.parquet": almacen.escribir_tabla(sub, salida / "subyacente.parquet")}
    almacen.escribir_json({"fecha": str(fecha), "capturas": resumenes, "implicito_no_identificado": fallos,
                           "salidas": hashes, "config": info_config, "entorno": almacen.huella_entorno(RAIZ)},
                          salida / "resumen.json")
    for r in resumenes:
        print(f"{r['captura']}: {r.get('con_cotizacion', 0)} cotizaciones de {r.get('snapshots', 0)} snapshots; "
              f"sin cotización {r.get('sin_cotizacion', 0)}; sin metadatos {r.get('sin_metadatos', 0)}")
    for _, fila in sub.iterrows():
        print(f"  subyacente {fila['subyacente']} = {fila['precio']:.2f} ({fila['feed']}) en {fila['captura']}")
    for f in fallos:
        print(f"  subyacente implícito no identificado en {f['captura']}: {f['motivo']}")
    return 1 if fallidas or (not args.ahora and perdidas) else 0


if __name__ == "__main__":
    sys.exit(main())
