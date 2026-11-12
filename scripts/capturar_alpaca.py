"""Captura diaria de cadenas de opciones en Alpaca a horas fijas de Nueva York.

Uso, desde la raíz del repositorio, una vez por sesión y antes de la primera hora::

    python scripts/capturar_alpaca.py                # espera y captura a las horas de la configuración
    python scripts/capturar_alpaca.py --horas 09:45  # solo esa hora (un proceso por hora en el workflow)
    python scripts/capturar_alpaca.py --ahora        # captura inmediata de prueba (también fuera de sesión)
    python scripts/capturar_alpaca.py --recuperar    # solo convierte diarios sin manifiesto

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

Recuperación. Cada página queda en el diario de su captura
(``<etiqueta>.diario.jsonl``) en cuanto llega, y el manifiesto final se escribe
de forma atómica. Dos plazos terminan el proceso aunque una solicitud siga
colgada, y los dos dejan el registro de la ejecución:

* de **preparación** (código 4): si los contratos y los vencimientos no están
  listos ``preparacion_s`` antes del corte (o ``preparacion_minima_s`` después de
  arrancar, si se arrancó tarde), para que el respaldo de esa hora, en cola,
  arranque y llegue al corte;
* **absoluto** (código 3): ``plazo_s`` después del último corte.

Un error inesperado tampoco pierde el registro, que se abre antes de cualquier
llamada externa: queda en él, con la etapa. Al iniciar (credenciales, reloj del
servidor, recuperación o planificación), las horas pedidas quedan ``sin
iniciar`` y el código es 1; el registro no inventa lo que no llegó (``reloj``
queda nulo si el servidor no respondió). Al preparar o capturar, las horas en
curso quedan ``fallida`` (código 1). En la normalización del día, que es
posterior y no toca el crudo ni sus manifiestos, el código es 5 si las horas
habían terminado completas. Los instantes del registro son del reloj local.

Al empezar, y con ``--recuperar``, cada diario sin manifiesto se convierte en el
manifiesto de lo que llegó, ``parcial`` o ``fallida`` y marcado como interrumpido.

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
import traceback
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


def recuperar(datos) -> int:
    """Convierte cada diario sin manifiesto y deja constancia en un registro de ejecución (también si falla)."""
    ahora = pd.Timestamp.now(tz="UTC")
    registro = {"tipo": "recuperacion", "inicio_utc": alpaca.iso(ahora), "fuente_instantes": "reloj local",
                "fecha": str(ahora.tz_convert(NUEVA_YORK).date()),
                "evento": os.environ.get("GITHUB_EVENT_NAME", "manual"), "run_id": os.environ.get("GITHUB_RUN_ID"),
                "codigo": almacen.estado_git(RAIZ)}
    try:
        recuperadas = alpaca.recuperar(datos, ahora)
    except Exception as error:  # el diario sigue ahí: la próxima ejecución lo vuelve a intentar
        traceback.print_exc()
        alpaca.escribir_ejecucion({**registro, "recuperadas": [], "error": {
            "etapa": "recuperación", "error": f"{type(error).__name__}: {error}", "utc": alpaca.iso(ahora)}},
            datos, sufijo="_recuperacion")
        return 1
    for m in recuperadas:
        print(f"recuperada {m['etiqueta']}: {m['estado']} ({m['motivo_interrupcion']})")
    if recuperadas:
        alpaca.escribir_ejecucion({**registro, "recuperadas": [
            {"etiqueta": m["etiqueta"], "estado": m["estado"], "motivo": m["motivo_interrupcion"]}
            for m in recuperadas]}, datos, sufijo="_recuperacion")
    else:
        print("no hay capturas interrumpidas")
    return 0


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--config", default=str(RAIZ / "configs" / "captura_alpaca.toml"))
    a.add_argument("--config-piloto", default=str(RAIZ / "configs" / "piloto.toml"))
    a.add_argument("--datos", default=str(RAIZ / "data"))
    a.add_argument("--ahora", action="store_true", help="captura inmediata de prueba")
    a.add_argument("--horas", nargs="*", help="sustituye las horas de la configuración (HH:MM)")
    a.add_argument("--plazo-s", type=float, default=None,
                   help="plazo absoluto después del último corte (por omisión, plazo_s de la configuración)")
    a.add_argument("--recuperar", action="store_true", help="solo convierte los diarios sin manifiesto")
    args = a.parse_args()

    bruto = cargar(args.config)
    cfg = bruto["captura"]
    codigo = cfg["calendario"]
    datos = Path(args.datos)
    if args.recuperar:
        return recuperar(datos)
    info_config = {"ruta": Path(args.config).resolve().relative_to(RAIZ).as_posix()
                   if Path(args.config).resolve().is_relative_to(RAIZ) else args.config,
                   "version": cfg["version"], "huella": almacen.huella_datos(bruto)}
    # El registro se abre antes de cualquier llamada externa: un fallo al iniciar también deja constancia. Sus
    # instantes son del reloj local; «reloj» guarda el desfase con el del servidor, si respondió.
    ejecucion = {"modo": "inmediata" if args.ahora else "programada", "fuente_instantes": "reloj local",
                 "evento": os.environ.get("GITHUB_EVENT_NAME", "manual"), "disparo": os.environ.get("DISPARO") or None,
                 "run_id": os.environ.get("GITHUB_RUN_ID"), "intento": os.environ.get("GITHUB_RUN_ATTEMPT"),
                 "reloj": None, "codigo": almacen.estado_git(RAIZ), "config": info_config, "recuperadas": []}
    horas_pedidas = ["inmediata"] if args.ahora else list(args.horas or cfg["horas"])
    cliente, etapa = None, "credenciales"

    def sin_iniciar(etapa, error):
        """Registro de una ejecución que falló antes de planificar: sin datos del servidor que no llegaron."""
        traceback.print_exc()
        instante = cliente.reloj() if cliente is not None else pd.Timestamp.now(tz="UTC")
        ejecucion.setdefault("inicio_utc", alpaca.iso(instante))
        ejecucion.setdefault("fecha", str(instante.tz_convert(NUEVA_YORK).date()))
        ejecucion.update(fin_utc=alpaca.iso(instante),
                         error={"etapa": etapa, "error": f"{type(error).__name__}: {error}",
                                "utc": alpaca.iso(instante)},
                         horas=[{"hora": h, "accion": "ninguna", "estado": "sin iniciar",
                                 "motivo": f"error al iniciar ({etapa})"} for h in horas_pedidas])
        ruta = alpaca.escribir_ejecucion(ejecucion, datos)
        print(f"sin iniciar ({etapa}): {error} -> {ruta.relative_to(datos)}", file=sys.stderr)
        return 1

    try:
        cliente = alpaca.ClienteAlpaca(alpaca.Credenciales.del_entorno(), reintentos=cfg["reintentos"],
                                       espera_max=cfg["espera_max_s"])
        inicio = cliente.reloj()
        ejecucion.update(inicio_utc=alpaca.iso(inicio), fecha=str(inicio.tz_convert(NUEVA_YORK).date()))

        # Reloj del servidor, antes de nada: el horario depende del reloj local.
        etapa = "reloj del servidor"
        reloj, err = alpaca.ejecutar(cliente, [alpaca.pedir_reloj()], 1)
        if err:
            raise RuntimeError(f"no se pudo consultar el reloj de Alpaca: {err}")
        estado_reloj = alpaca.reloj_servidor(reloj["reloj"][0])
        ejecucion["reloj"] = estado_reloj
        print(f"cuenta {cliente.cuenta}; desfase del reloj local {estado_reloj['desfase_s']:+.3f} s "
              f"(± {estado_reloj['incertidumbre_s']:.3f}); mercado abierto: {estado_reloj['mercado_abierto']}")
        if abs(estado_reloj["desfase_s"]) > 1.0:
            print("AVISO: el reloj local difiere más de 1 s del de Alpaca; los sellos locales quedan desplazados",
                  file=sys.stderr)

        etapa = "recuperación"
        ahora = cliente.reloj()
        recuperadas = alpaca.recuperar(datos, ahora)  # capturas interrumpidas de ejecuciones anteriores
        for m in recuperadas:
            print(f"recuperada {m['etiqueta']}: {m['estado']} ({m['motivo_interrupcion']})", file=sys.stderr)
        ejecucion["recuperadas"] = [{"etiqueta": m["etiqueta"], "estado": m["estado"]} for m in recuperadas]

        etapa = "planificación"
        if args.ahora:
            fecha, corte_inmediato = sesion_de_referencia(ahora, codigo)
            plan = [{"hora": "inmediata", "corte_utc": corte_inmediato,
                     "etiqueta": f"{fecha}Tinmediata-{ahora:%H%M%S}", "capturas_previas": [], "estado": "pendiente",
                     "accion": "capturar"}]
        else:
            fecha = ahora.tz_convert(NUEVA_YORK).date()
            if not es_sesion(fecha, codigo):
                print(f"{fecha} no es sesión de {codigo}: no hay captura")
                return 0
            plan = alpaca.planificar(datos, fecha, horas_pedidas, ahora, cfg["adelanto_s"], codigo)
        ejecucion["fecha"] = str(fecha)
    except Exception as error:  # sin registro, una hora perdida no dice por qué
        return sin_iniciar(etapa, error)
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

    def al_interrumpir(estado):
        def registrar(motivo):  # corre en el hilo del plazo, justo antes de terminar el proceso
            for paso in pendientes:
                if paso["estado"] in ("pendiente", "en curso"):
                    paso.update(estado=estado, motivo=motivo)
            ejecucion["interrupcion"] = {"motivo": motivo, "utc": alpaca.iso(cliente.reloj())}
            terminar()
        return registrar

    # Plazo de preparación: si no está lista a tiempo, termina y deja que el respaldo de esa hora llegue al corte.
    listo_antes = alpaca.plazo_preparacion(min(p["corte_utc"] for p in pendientes), ahora, cfg["preparacion_s"],
                                           cfg["preparacion_minima_s"], cfg["adelanto_s"], programada=not args.ahora)
    preparacion = alpaca.Vigilante(listo_antes, cliente.reloj, codigo=alpaca.CODIGO_SIN_PREPARAR,
                                   motivo="sin preparar a tiempo", al_vencer=al_interrumpir("fallida"))
    # Plazo absoluto: pase lo que pase, el proceso termina poco después del último corte (y de la preparación).
    plazo = max([listo_antes] + [p["corte_utc"] for p in pendientes]) + pd.Timedelta(
        seconds=args.plazo_s if args.plazo_s is not None else float(cfg["plazo_s"]))
    vigilante = alpaca.Vigilante(plazo, cliente.reloj, al_vencer=al_interrumpir("interrumpida"))
    ejecucion.update(plazo_utc=alpaca.iso(plazo), listo_antes_utc=alpaca.iso(listo_antes))

    def registrar_error(etapa, error):
        traceback.print_exc()
        ejecucion["error"] = {"etapa": etapa, "error": f"{type(error).__name__}: {error}",
                             "utc": alpaca.iso(cliente.reloj())}

    try:
        # Contratos del día: metadatos para normalizar y para elegir vencimientos. Cada página se guarda al llegar.
        desde, hasta = fecha, fecha + dt.timedelta(days=int(cfg["ventana_contratos_dias"]))
        pedidos = [alpaca.pedir_contratos(o["subyacente"], desde, hasta, o["raiz"]) for o in cfg["opciones"]]
        registro = alpaca.Registro(datos)
        resultados, errores = alpaca.ejecutar(cliente, pedidos, cfg["hilos"], registro)
        if errores:
            # Sin manifiesto de captura: una ejecución posterior aún puede capturar si llega antes del corte.
            print(f"no se pudieron pedir los contratos: {errores}", file=sys.stderr)
            preparacion.cancelar()
            vigilante.cancelar()
            for paso in pendientes:
                paso.update(estado="fallida", motivo="sin contratos del día")
            return terminar()
        previas = {**registro.entradas, **alpaca.guardar_respuestas(reloj, {"reloj": "reloj"}, datos)}
        meta = alpaca.metadatos_contratos(r.json() for rs in resultados.values() for r in rs)
        seleccion, solicitudes = {}, []
        for o in cfg["opciones"]:
            vencimientos = {c["expiration_date"] for c in meta.values() if c["root_symbol"] == o["raiz"]}
            if "objetivos_dias" in o:
                if "objetivo_dias" in o:
                    raise ValueError("usar objetivo_dias u objetivos_dias, no ambos")
                elegidos, plazos = alpaca.elegir_vencimientos_multiples(
                    vencimientos, alpaca.LIQUIDACION[o["raiz"]], pendientes[0]["corte_utc"], o["objetivos_dias"],
                    o["vencimientos_por_lado"], o["cercano"], codigo=codigo)
            else:
                elegidos, plazos = alpaca.elegir_vencimientos(
                    vencimientos, alpaca.LIQUIDACION[o["raiz"]], pendientes[0]["corte_utc"], o["objetivo_dias"],
                    o["vencimientos_por_lado"], o["cercano"], codigo=codigo)
            seleccion[o["raiz"]] = {"vencimientos": [str(v) for v in elegidos],
                                    "dias": {str(v): round(plazos[v], 4) for v in elegidos}}
            print(f"{o['raiz']}: " + ", ".join(f"{v} ({plazos[v]:.1f} d)" for v in elegidos))
            solicitudes += [alpaca.pedir_cadena(o["raiz"], v, cfg["feed_opciones"]) for v in elegidos]
        solicitudes.append(alpaca.pedir_acciones(bruto["captura"]["acciones"]["simbolos"], cfg["feed_acciones"]))
        preparacion.cancelar()
        ejecucion["listo_utc"] = alpaca.iso(cliente.reloj())
        print(f"lista a las {cliente.reloj().tz_convert(NUEVA_YORK):%H:%M:%S} (Nueva York); "
              f"plazo de preparación {listo_antes.tz_convert(NUEVA_YORK):%H:%M:%S}")

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
            paso["estado"] = "en curso"
            try:
                manifiesto, ruta = alpaca.capturar(cliente, solicitudes, datos, m, previas, cfg["hilos"], vigilante)
            except FileExistsError as error:
                print(f"{hora}: {error}", file=sys.stderr)
                paso.update(estado="fallida", motivo=str(error))
                continue
            duracion = (pd.Timestamp(manifiesto["fin_utc"]) - pd.Timestamp(manifiesto["inicio_utc"])).total_seconds()
            n = sum(len(e["paginas"]) for e in manifiesto["solicitudes"].values())
            paso.update(estado=manifiesto["estado"], manifiesto=ruta.relative_to(datos).as_posix(), respuestas=n,
                        duracion_s=round(duracion, 3),
                        despues_del_corte=len(manifiesto["respuestas_despues_del_corte"]),
                        errores=sorted(manifiesto["errores"]),
                        margen_s=round((corte - pd.Timestamp(manifiesto["inicio_utc"])).total_seconds(), 3))
            print(f"{hora}: {manifiesto['estado']}; {n} respuestas en {duracion:.2f} s; después del corte: "
                  f"{paso['despues_del_corte']}; errores: {len(paso['errores'])} -> {paso['manifiesto']}")
    except Exception as error:  # un error inesperado no puede perder el registro de la ejecución
        preparacion.cancelar()
        vigilante.cancelar()
        registrar_error("preparación y captura", error)
        for paso in pendientes:
            if paso["estado"] in ("pendiente", "en curso"):
                paso.update(estado="fallida", motivo=f"error inesperado: {type(error).__name__}")
        return terminar()
    vigilante.cancelar()  # lo que sigue es local y no compite con ningún corte

    # Tablas normalizadas del día, reconstruidas desde el crudo (el histórico SIP llega después, con su script).
    # Un fallo aquí no toca la captura: el crudo y sus manifiestos ya están escritos.
    try:
        piloto = cargar_config(args.config_piloto)
        t = alpaca.tablas_para_piloto(datos, fecha, fecha, bruto.get("implicito"), piloto.reglas,
                                      eventos=False)
        salida = datos / "normalized" / "alpaca" / "diario" / str(fecha)
        hashes = {"cotizaciones.parquet": almacen.escribir_tabla(t.cotizaciones, salida / "cotizaciones.parquet"),
                  "subyacente.parquet": almacen.escribir_tabla(t.subyacente, salida / "subyacente.parquet")}
        almacen.escribir_json({"fecha": str(fecha), "capturas": t.resumenes, "implicito_no_identificado":
                               t.fallos_implicito, "salidas": hashes, "config": info_config,
                               "entorno": almacen.huella_entorno(RAIZ)}, salida / "resumen.json")
        for r in t.resumenes:
            print(f"{r['captura']}: {r.get('con_cotizacion', 0)} cotizaciones de {r.get('snapshots', 0)} snapshots; "
                  f"sin cotización {r.get('sin_cotizacion', 0)}; sin metadatos {r.get('sin_metadatos', 0)}")
        en_vivo = t.subyacente[t.subyacente["feed"] != "sip"]
        for _, fila in en_vivo.iterrows():
            print(f"  subyacente {fila['subyacente']} = {fila['precio']:.2f} ({fila['feed']}) en {fila['captura']}")
        for f in t.fallos_implicito:
            print(f"  subyacente implícito no identificado en {f['captura']}: {f['motivo']}")
    except Exception as error:
        registrar_error("normalización del día", error)
        return terminar() or alpaca.CODIGO_SIN_NORMALIZAR
    return terminar()


if __name__ == "__main__":
    sys.exit(main())
