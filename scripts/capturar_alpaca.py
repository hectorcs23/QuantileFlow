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

Cada hora termina ``completa``, ``parcial`` (alguna solicitud falló o llegó
después del corte), ``fallida`` (ninguna cadena a tiempo) o ``perdida`` (sin
captura y con el corte pasado). Una hora ya capturada no se repite y un fallo
después del corte no se reemplaza con datos posteriores. El código de salida es
0 solo si todas las horas quedaron completas, y cada ejecución deja un registro
en ``data/raw/alpaca/ejecuciones/<fecha>/`` con el disparo, el margen hasta cada
corte y el estado de cada hora.

Fuera de sesión, ``--ahora`` toma como sesión de referencia la última que ya
abrió y como corte el menor entre ahora y su cierre: sirve para verificar el
adaptador con cotizaciones reales, no como sesión del piloto.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import tomllib
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow import alpaca, almacen  # noqa: E402
from quantileflow.calendario import NUEVA_YORK, apertura, calendario, cierre, es_sesion  # noqa: E402
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
    ejecucion = {"inicio_utc": alpaca.iso(ahora), "modo": "inmediata" if args.ahora else "programada",
                 "evento": os.environ.get("GITHUB_EVENT_NAME", "manual"), "disparo": os.environ.get("DISPARO") or None,
                 "run_id": os.environ.get("GITHUB_RUN_ID"), "intento": os.environ.get("GITHUB_RUN_ATTEMPT"),
                 "reloj": estado_reloj, "codigo": almacen.estado_git(RAIZ), "config": info_config}
    if args.ahora:
        fecha, corte_inmediato = sesion_de_referencia(ahora, codigo)
        plan = [{"hora": "inmediata", "corte_utc": corte_inmediato, "etiqueta": f"{fecha}Tinmediata-{ahora:%H%M%S}",
                 "capturas_previas": [], "estado": "pendiente", "accion": "capturar"}]
    else:
        fecha = ahora.tz_convert(NUEVA_YORK).date()
        if not es_sesion(fecha, codigo):
            print(f"{fecha} no es sesión de {codigo}: no hay captura")
            return 0
        plan = alpaca.planificar(datos, fecha, args.horas or cfg["horas"], ahora, cfg["adelanto_s"], codigo)
    ejecucion["fecha"] = str(fecha)
    for paso in plan:
        if paso["accion"] == "omitir":
            print(f"{paso['hora']}: {paso['estado']}; se omite", file=sys.stderr if paso["estado"] != "completa"
                  else sys.stdout)

    def terminar():
        ejecucion["fin_utc"] = alpaca.iso(cliente.reloj())
        ejecucion["horas"] = [{k: (alpaca.iso(v) if k == "corte_utc" else v) for k, v in paso.items()}
                              for paso in plan]
        ruta = alpaca.escribir_ejecucion(ejecucion, datos)
        print("horas: " + ", ".join(f"{p['hora']} {p['estado']}" for p in plan) + f" -> {ruta.relative_to(datos)}")
        return alpaca.codigo_salida(plan)

    pendientes = [p for p in plan if p["accion"] == "capturar"]
    if not pendientes:
        return terminar()

    # Contratos del día: metadatos para normalizar y para elegir vencimientos. Cada página se guarda al llegar.
    desde, hasta = fecha, fecha + dt.timedelta(days=int(cfg["ventana_contratos_dias"]))
    pedidos = [alpaca.pedir_contratos(o["subyacente"], desde, hasta, o["raiz"]) for o in cfg["opciones"]]
    registro = alpaca.Registro(datos)
    resultados, errores = alpaca.ejecutar(cliente, pedidos, cfg["hilos"], registro)
    if errores:
        # Sin manifiesto de captura: una ejecución posterior aún puede capturar si llega antes del corte.
        print(f"no se pudieron pedir los contratos: {errores}", file=sys.stderr)
        for paso in pendientes:
            paso.update(estado="fallida", motivo="sin contratos del día")
        return terminar()
    previas = {**registro.entradas, **alpaca.guardar_respuestas(reloj, {"reloj": "reloj"}, datos)}
    meta = alpaca.metadatos_contratos(r.json() for rs in resultados.values() for r in rs)
    seleccion, solicitudes = {}, []
    for o in cfg["opciones"]:
        vencimientos = {c["expiration_date"] for c in meta.values() if c["root_symbol"] == o["raiz"]}
        elegidos, plazos = alpaca.elegir_vencimientos(
            vencimientos, alpaca.LIQUIDACION[o["raiz"]], pendientes[0]["corte_utc"], o["objetivo_dias"],
            o["vencimientos_por_lado"], o["cercano"], codigo=codigo)
        seleccion[o["raiz"]] = {"vencimientos": [str(v) for v in elegidos],
                                "dias": {str(v): round(plazos[v], 4) for v in elegidos}}
        print(f"{o['raiz']}: " + ", ".join(f"{v} ({plazos[v]:.1f} d)" for v in elegidos))
        solicitudes += [alpaca.pedir_cadena(o["raiz"], v, cfg["feed_opciones"]) for v in elegidos]
    solicitudes.append(alpaca.pedir_acciones(bruto["captura"]["acciones"]["simbolos"], cfg["feed_acciones"]))

    for paso in pendientes:
        hora, corte = paso["hora"], paso["corte_utc"]
        if hora != "inmediata":
            inicio = corte - pd.Timedelta(seconds=cfg["adelanto_s"])
            print(f"{hora}: esperando hasta {inicio.tz_convert(NUEVA_YORK):%H:%M:%S} (Nueva York)")
            alpaca.esperar_hasta(inicio, cliente.reloj)
        m = {"fecha": str(fecha), "hora": hora, "corte_utc": alpaca.iso(corte), "etiqueta": paso["etiqueta"],
             "modo": "inmediata" if hora == "inmediata" else "programada", "feed_opciones": cfg["feed_opciones"],
             "feed_acciones": cfg["feed_acciones"], "adelanto_s": cfg["adelanto_s"], "config": info_config,
             "seleccion": seleccion, "reloj": estado_reloj, "codigo": ejecucion["codigo"]}
        try:
            manifiesto, ruta = alpaca.capturar(cliente, solicitudes, datos, m, previas, cfg["hilos"])
        except FileExistsError as error:
            print(f"{hora}: {error}", file=sys.stderr)
            paso.update(estado="fallida", motivo=str(error))
            continue
        duracion = (pd.Timestamp(manifiesto["fin_utc"]) - pd.Timestamp(manifiesto["inicio_utc"])).total_seconds()
        n = sum(len(e["paginas"]) for e in manifiesto["solicitudes"].values())
        paso.update(estado=manifiesto["estado"], manifiesto=ruta.relative_to(datos).as_posix(), respuestas=n,
                    duracion_s=round(duracion, 3), despues_del_corte=len(manifiesto["respuestas_despues_del_corte"]),
                    errores=sorted(manifiesto["errores"]),
                    margen_s=round((corte - pd.Timestamp(manifiesto["inicio_utc"])).total_seconds(), 3))
        print(f"{hora}: {manifiesto['estado']}; {n} respuestas en {duracion:.2f} s; después del corte: "
              f"{paso['despues_del_corte']}; errores: {len(paso['errores'])} -> {paso['manifiesto']}")

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
    return terminar()


if __name__ == "__main__":
    sys.exit(main())
