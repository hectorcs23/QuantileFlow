"""Descarga, pasado el retraso del SIP, el precio del objetivo en cada corte y los eventos corporativos.

Uso, desde la raíz del repositorio::

    python scripts/historico_alpaca.py              # completa lo que falte de la última semana y ya se pueda
    python scripts/historico_alpaca.py --esperar    # además espera a los cortes de hoy que aún no se pueden consultar
    python scripts/historico_alpaca.py --desde 2026-09-28 --hasta 2026-10-02

Para cada sesión y hora de corte de la configuración de captura pide a
``/v2/stocks/quotes`` (feed SIP, NBBO consolidado) las cotizaciones más
recientes del objetivo con evento en ``[corte - ventana, corte]``. Solo lo hace
pasados el retraso del SIP sin suscripción (15 minutos) y un margen: esa es la
disponibilidad documentada que la normalización registra y que fija la madurez
de las etiquetas, así que el dato nunca entra en una medida del corte. Un corte
ya descargado no se repite; un intento fallido sí, porque el dato histórico no
cambia. Después consulta los eventos corporativos del objetivo (dividendos).
Además, registra el estado de cada hora de captura de las sesiones del rango
(``completa``, ``parcial``, ``fallida`` o ``perdida``): un corte perdido queda
anotado aunque ninguna ejecución de captura haya llegado a correr.

Guarda el crudo como la captura en vivo, un manifiesto por corte en
``raw/alpaca/historico/<fecha>/``, uno por consulta de eventos en
``raw/alpaca/eventos/<fecha>/`` y un registro de la ejecución en
``raw/alpaca/ejecuciones/<fecha>/``. Lee las credenciales de
``APCA_API_KEY_ID`` y ``APCA_API_SECRET_KEY``; nunca las escribe. El código de
salida es 0 si todo lo que ya se podía descargar quedó completo; un corte que
aún no se puede consultar queda pendiente para la próxima ejecución.
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
from quantileflow.calendario import NUEVA_YORK, sesiones  # noqa: E402


def cargar(ruta):
    with open(ruta, "rb") as f:
        return tomllib.load(f)


def resumen_pagina(datos, manifiesto):
    """Número de cotizaciones y la más reciente de una descarga histórica, para el registro en pantalla."""
    for entrada in manifiesto["solicitudes"].values():
        for pagina in entrada["paginas"]:
            cotizaciones = [q for lista in (alpaca.leer_crudo(datos, pagina).get("quotes") or {}).values()
                            for q in lista or []]
            if cotizaciones:
                q = max(cotizaciones, key=lambda q: pd.Timestamp(q["t"]))
                return f"{len(cotizaciones)} cotizaciones; última {q['t']} {q['bp']}/{q['ap']}"
    return "sin cotizaciones en la ventana"


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--config", default=str(RAIZ / "configs" / "captura_alpaca.toml"))
    a.add_argument("--datos", default=str(RAIZ / "data"))
    a.add_argument("--desde", default=None, help="primera sesión (por omisión, hoy menos dias_atras)")
    a.add_argument("--hasta", default=None, help="última sesión (por omisión, hoy)")
    a.add_argument("--esperar", action="store_true", help="espera a los cortes de hoy que aún no se pueden consultar")
    a.add_argument("--sin-eventos", action="store_true", help="no consulta los eventos corporativos")
    args = a.parse_args()

    bruto = cargar(args.config)
    cfg, h, ev = bruto["captura"], bruto["historico"], bruto["eventos"]
    codigo = cfg["calendario"]
    datos = Path(args.datos)
    cliente = alpaca.ClienteAlpaca(alpaca.Credenciales.del_entorno())
    info_config = {"ruta": Path(args.config).resolve().relative_to(RAIZ).as_posix()
                   if Path(args.config).resolve().is_relative_to(RAIZ) else args.config,
                   "version": cfg["version"], "huella": almacen.huella_datos(bruto)}

    reloj, err = alpaca.ejecutar(cliente, [alpaca.pedir_reloj()], 1)
    if err:
        print(f"no se pudo consultar el reloj de Alpaca: {err}", file=sys.stderr)
        return 1
    estado_reloj = alpaca.reloj_servidor(reloj["reloj"][0])
    print(f"cuenta {cliente.cuenta}; desfase del reloj local {estado_reloj['desfase_s']:+.3f} s "
          f"(± {estado_reloj['incertidumbre_s']:.3f})")
    ahora = cliente.reloj()
    hoy = ahora.tz_convert(NUEVA_YORK).date()
    desde = pd.Timestamp(args.desde).date() if args.desde else hoy - dt.timedelta(days=int(h["dias_atras"]))
    hasta = min(pd.Timestamp(args.hasta).date() if args.hasta else hoy, hoy)
    ejecucion = {"tipo": "historico", "inicio_utc": alpaca.iso(ahora), "fecha": str(hoy),
                 "evento": os.environ.get("GITHUB_EVENT_NAME", "manual"), "disparo": os.environ.get("DISPARO") or None,
                 "run_id": os.environ.get("GITHUB_RUN_ID"), "intento": os.environ.get("GITHUB_RUN_ATTEMPT"),
                 "reloj": estado_reloj, "codigo": almacen.estado_git(RAIZ), "config": info_config,
                 "desde": str(desde), "hasta": str(hasta), "cortes": []}

    fallos = 0
    ejecucion["capturas"] = []
    for fecha in (sesiones(desde, hasta, codigo) if desde <= hasta else []):
        for paso in alpaca.planificar(datos, fecha, cfg["horas"], cliente.reloj(), cfg["adelanto_s"], codigo):
            if paso["estado"] != "pendiente":
                ejecucion["capturas"].append({"fecha": str(fecha), "hora": paso["hora"], "estado": paso["estado"],
                                              "capturas_previas": paso["capturas_previas"]})
                if paso["estado"] != "completa":
                    print(f"{fecha} {paso['hora']}: captura {paso['estado']}", file=sys.stderr)
        plan = alpaca.planificar_historico(datos, fecha, cfg["horas"], cliente.reloj(), h["retraso_s"],
                                           h["margen_s"], codigo)
        for paso in plan:
            corte = paso["corte_utc"]
            if paso["accion"] == "esperar" and args.esperar and fecha == hoy:
                print(f"{fecha} {paso['hora']}: esperando hasta "
                      f"{paso['consultable_utc'].tz_convert(NUEVA_YORK):%H:%M:%S} (Nueva York)")
                alpaca.esperar_hasta(paso["consultable_utc"], cliente.reloj)
                paso["accion"] = "descargar"
            if paso["accion"] == "descargar":
                meta = {**alpaca.meta_historico(fecha, paso, h["retraso_s"], h["simbolos"], h["feed"], h["ventana_s"],
                                                h["limite"]),
                        "config": info_config, "reloj": estado_reloj, "codigo": ejecucion["codigo"]}
                solicitud = alpaca.pedir_historico(h["simbolos"], h["feed"], corte, h["ventana_s"], h["limite"])
                manifiesto, ruta = alpaca.descargar_historico(cliente, solicitud, datos, meta)
                paso.update(estado=manifiesto["estado"], manifiesto=ruta.relative_to(datos).as_posix(),
                            errores=sorted(manifiesto["errores"]))
                detalle = (resumen_pagina(datos, manifiesto) if manifiesto["estado"] == "completa"
                           else "; ".join(manifiesto["errores"].values()))
                print(f"{fecha} {paso['hora']}: {manifiesto['estado']} ({detalle}) -> {paso['manifiesto']}")
                fallos += manifiesto["estado"] != "completa"
            elif paso["accion"] == "esperar":
                print(f"{fecha} {paso['hora']}: aún no se puede consultar (desde "
                      f"{paso['consultable_utc'].tz_convert(NUEVA_YORK):%H:%M} de Nueva York); queda pendiente")
            ejecucion["cortes"].append({"fecha": str(fecha), **{k: (alpaca.iso(v) if k.endswith("_utc") else v)
                                                                for k, v in paso.items()}})

    if not args.sin_eventos:
        inicio = cliente.reloj()
        solicitud = alpaca.pedir_eventos(ev["simbolos"], hoy - dt.timedelta(days=int(ev["dias_atras"])),
                                         hoy + dt.timedelta(days=int(ev["dias_adelante"])))
        meta = {"fecha": str(hoy), "etiqueta": f"eventos-{inicio:%Y%m%dT%H%M%S%f}", "simbolos": list(ev["simbolos"]),
                "config": info_config, "codigo": ejecucion["codigo"]}
        manifiesto, ruta = alpaca.descargar_eventos(cliente, solicitud, datos, meta)
        ejecucion["eventos"] = {"estado": manifiesto["estado"], "manifiesto": ruta.relative_to(datos).as_posix(),
                                "errores": sorted(manifiesto["errores"])}
        print(f"eventos corporativos: {manifiesto['estado']} -> {ejecucion['eventos']['manifiesto']}")
        fallos += manifiesto["estado"] != "completa"

    ejecucion["fin_utc"] = alpaca.iso(cliente.reloj())
    ruta = alpaca.escribir_ejecucion(ejecucion, datos, sufijo="_historico")
    print(f"registro -> {ruta.relative_to(datos)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
