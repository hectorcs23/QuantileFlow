"""Revisión de la operación de la captura: estado de cada corte, puntualidad, respaldo y recuperaciones.

Lee solo lo que la captura y el histórico dejan en el repositorio de datos (los
registros de ``ejecuciones/`` y los manifiestos) y devuelve agregados, nunca
cotizaciones. Para cada sesión y hora de corte:

* el **estado final**, con la misma regla que usa la captura
  (``alpaca.planificar``): ``completa``, ``parcial``, ``fallida``, ``perdida``
  o, si el corte aún no pasó, ``pendiente``;
* las **ejecuciones** que lo planificaron, en orden de arranque, cuántas
  intentaron capturar y el ``cron`` de la que capturó (en la plantilla, el
  minuto 11 es el titular y el 26 el respaldo: si el titular no llegó a correr,
  la captura del respaldo se ve en su disparo);
* la **puntualidad**: el retraso con que arrancó el script respecto de su
  ``cron`` (incluye la preparación del workflow), el margen con que quedó lista
  la captura antes del corte y el de la ráfaga;
* los plazos que terminaron un proceso (preparación, absoluto), los errores y
  las recuperaciones;
* el estado del SIP histórico del objetivo en ese corte.

Además, el resumen de los dividendos (``alpaca.resumen_dividendos``): versiones,
discrepancias abiertas por tipo (ausentes, incompletos...), retiros y
contradicciones con las resoluciones.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import alpaca
from .calendario import CALENDARIO, _fecha, sesiones

ESTADOS_CORTE = ("completa", "parcial", "fallida", "perdida", "pendiente")


def programado_utc(disparo, inicio_utc):
    """Hora programada de un disparo ``cron`` (``"M H * * ..."``, en UTC) el día de ``inicio_utc``, o ``None``."""
    try:
        minuto, hora = (int(x) for x in str(disparo).split()[:2])
    except (TypeError, ValueError):
        return None
    inicio = pd.Timestamp(inicio_utc)
    return pd.Timestamp(inicio.date()).tz_localize("UTC") + pd.Timedelta(hours=hora, minutes=minuto)


def _segundos(a, b):
    """``a - b`` en segundos, o ``None`` si falta alguno."""
    if a is None or b is None:
        return None
    return round((pd.Timestamp(a) - pd.Timestamp(b)).total_seconds(), 3)


def leer_registros(raiz_datos, desde=None, hasta=None) -> list[dict]:
    """Registros de ``ejecuciones/`` entre dos fechas (incluidas), en orden de arranque."""
    base = alpaca.directorio_crudo(raiz_datos) / "ejecuciones"
    registros = []
    for ruta in sorted(base.glob("*/*.json")) if base.exists() else []:
        fecha = _fecha(ruta.parent.name)
        if (desde is not None and fecha < _fecha(desde)) or (hasta is not None and fecha > _fecha(hasta)):
            continue
        registro = json.loads(ruta.read_text(encoding="utf-8"))
        registro["_ruta"] = ruta.relative_to(Path(raiz_datos)).as_posix()
        registros.append(registro)
    return sorted(registros, key=lambda r: (r["inicio_utc"], r["_ruta"]))


def _ejecucion(registro, paso, corte):
    """Lo que interesa de una ejecución de captura para una hora de corte."""
    programado = programado_utc(registro.get("disparo"), registro["inicio_utc"])
    interrupcion = (registro.get("interrupcion") or {}).get("motivo")
    return {"registro": registro["_ruta"], "evento": registro.get("evento"), "disparo": registro.get("disparo"),
            "inicio_utc": registro["inicio_utc"], "retraso_s": _segundos(registro["inicio_utc"], programado),
            "accion": paso.get("accion"), "estado": paso.get("estado"), "motivo": paso.get("motivo", ""),
            "margen_listo_s": _segundos(corte, registro.get("listo_utc")) if paso.get("accion") == "capturar"
            else None,
            "margen_rafaga_s": paso.get("margen_s"), "duracion_s": paso.get("duracion_s"),
            "despues_del_corte": paso.get("despues_del_corte"), "errores": len(paso.get("errores") or []),
            "interrupcion": interrupcion or "", "error": (registro.get("error") or {}).get("error", "")}


def revisar(raiz_datos, desde, hasta, horas, adelanto_s, codigo=CALENDARIO, ahora_utc=None,
            resoluciones=None) -> dict:
    """Revisión de la operación entre dos sesiones (incluidas): cortes, ejecuciones, SIP y dividendos."""
    ahora = pd.Timestamp(ahora_utc) if ahora_utc is not None else pd.Timestamp.now(tz="UTC")
    registros = leer_registros(raiz_datos, desde, hasta)
    capturas = [r for r in registros if "tipo" not in r and r.get("modo") == "programada"]
    sip = {}
    for m in alpaca.leer_manifiestos(raiz_datos, desde, hasta, "historico"):
        sip.setdefault((m["fecha"], m["hora"]), []).append(m["estado"])
    cortes = []
    for fecha in sesiones(desde, hasta, codigo):
        for paso in alpaca.planificar(raiz_datos, fecha, horas, ahora, adelanto_s, codigo):
            corte = paso["corte_utc"]
            ejecuciones = [_ejecucion(r, h, corte) for r in capturas if r.get("fecha") == str(fecha)
                           for h in r.get("horas", []) if h.get("hora") == paso["hora"]]
            estados_sip = sip.get((str(fecha), paso["hora"]), [])
            intentos = [e for e in ejecuciones if e["accion"] == "capturar"]
            cortes.append({
                "fecha": str(fecha), "hora": paso["hora"], "corte_utc": alpaca.iso(corte), "estado": paso["estado"],
                "capturas": paso["capturas_previas"], "ejecuciones": ejecuciones, "intentos": len(intentos),
                # El último intento es el que dejó el estado: un fallo después del corte no se reintenta.
                "captura": intentos[-1] if intentos else None,
                "sip": "completa" if "completa" in estados_sip else (estados_sip[-1] if estados_sip
                                                                     else "sin descargar")})
    recuperaciones = [{"registro": r["_ruta"], **x} for r in registros if r.get("tipo") == "recuperacion"
                      for x in r.get("recuperadas", [])]
    recuperaciones += [{"registro": r["_ruta"], **x} for r in capturas for x in r.get("recuperadas", [])]
    eventos = [{"fecha": r.get("fecha"), "inicio_utc": r["inicio_utc"], **(r.get("eventos") or {})}
               for r in registros if r.get("tipo") == "historico" and r.get("eventos")]
    try:
        dividendos, _, otros, _ = alpaca.normalizar_eventos(raiz_datos, resoluciones)
        resumen_dividendos = alpaca.resumen_dividendos(dividendos, otros)
    except (ValueError, RuntimeError) as error:
        resumen_dividendos = {"error": str(error)}
    return {"desde": str(_fecha(desde)), "hasta": str(_fecha(hasta)), "revisado_utc": alpaca.iso(ahora),
            "resumen": resumir(cortes, recuperaciones), "cortes": cortes, "recuperaciones": recuperaciones,
            "eventos": eventos, "dividendos": resumen_dividendos}


def resumir(cortes, recuperaciones) -> dict:
    """Conteos y extremos: estados de los cortes, respaldos, plazos, errores y puntualidad."""
    ejecuciones = [e for c in cortes for e in c["ejecuciones"]]
    capturaron = [e for e in ejecuciones if e["accion"] == "capturar"]

    def extremo(valores, funcion):
        valores = [v for v in valores if v is not None]
        return funcion(valores) if valores else None

    return {"sesiones": len({c["fecha"] for c in cortes}), "cortes": len(cortes),
            "estados": {k: sum(c["estado"] == k for c in cortes) for k in ESTADOS_CORTE},
            "sip_completo": sum(c["sip"] == "completa" for c in cortes),
            "ejecuciones_de_captura": len(ejecuciones),
            "cortes_con_reintento": sum(c["intentos"] > 1 for c in cortes),
            "sin_preparar_a_tiempo": sum("sin preparar" in e["interrupcion"] for e in ejecuciones),
            "plazo_absoluto": sum("plazo absoluto" in e["interrupcion"] for e in ejecuciones),
            "errores": sum(bool(e["error"]) for e in ejecuciones),
            "recuperaciones": len(recuperaciones),
            "retraso_max_s": extremo([e["retraso_s"] for e in ejecuciones], max),
            "margen_listo_min_s": extremo([e["margen_listo_s"] for e in capturaron], min),
            "margen_rafaga_min_s": extremo([e["margen_rafaga_s"] for e in capturaron], min),
            "respuestas_despues_del_corte": sum(e["despues_del_corte"] or 0 for e in capturaron)}


def _texto(valor, formato="{:.0f}"):
    return "—" if valor is None else formato.format(valor)


def _conteos(d, vacio="ninguna"):
    return ", ".join(f"{k} {n}" for k, n in d.items()) if d else vacio


def _sin_repetir(partes):
    """Las partes no vacías, sin las que ya dice otra (p. ej., el motivo dentro de la interrupción)."""
    partes = [x for x in partes if x]
    return [x for i, x in enumerate(partes)
            if not any(x in y for j, y in enumerate(partes) if j != i and (x != y or j < i))]


def informe(revision: dict) -> str:
    """Informe Markdown de una revisión (solo agregados)."""
    r = revision["resumen"]
    estados = ", ".join(f"{n} {k}" for k, n in r["estados"].items() if n)
    lineas = [f"# Operación de la captura: {revision['desde']} a {revision['hasta']}", "",
              f"Revisado el {revision['revisado_utc']}, con los registros de `ejecuciones/` y los manifiestos del "
              "repositorio de datos. Solo agregados.", "",
              "## Resumen", "",
              f"- Sesiones: {r['sesiones']}; cortes: {r['cortes']} ({estados or 'ninguno'}).",
              f"- SIP del objetivo completo en {r['sip_completo']} de {r['cortes']} cortes.",
              f"- Ejecuciones de captura: {r['ejecuciones_de_captura']}; cortes con más de un intento de captura: "
              f"{r['cortes_con_reintento']}.",
              f"- Plazo de preparación vencido: {r['sin_preparar_a_tiempo']}; plazo absoluto: {r['plazo_absoluto']}; "
              f"errores: {r['errores']}; recuperaciones: {r['recuperaciones']}.",
              f"- Retraso máximo del arranque respecto del cron: {_texto(r['retraso_max_s'])} s. Margen mínimo "
              f"hasta el corte: al quedar lista, {_texto(r['margen_listo_min_s'])} s; al empezar la ráfaga, "
              f"{_texto(r['margen_rafaga_min_s'], '{:.1f}')} s. Respuestas después del corte: "
              f"{r['respuestas_despues_del_corte']}.", "",
              "## Cortes", "",
              "La captura es el último intento, el que dejó el estado; el retraso es el de su arranque respecto de "
              "su `cron`.", "",
              "| Sesión | Hora | Estado | SIP | Ejecuciones | Intentos | Disparo de la captura | Retraso (s) "
              "| Lista antes (s) | Ráfaga (s) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for c in revision["cortes"]:
        e = c["captura"] or {}
        lineas.append(
            f"| {c['fecha']} | {c['hora']} | {c['estado']} | {c['sip']} | {len(c['ejecuciones'])} | {c['intentos']} | "
            f"{e.get('disparo') or e.get('evento') or '—'} | {_texto(e.get('retraso_s'))} | "
            f"{_texto(e.get('margen_listo_s'))} | {_texto(e.get('margen_rafaga_s'), '{:.1f}')} |")
    incidencias = [(c, e) for c in revision["cortes"] for e in c["ejecuciones"]
                   if e["interrupcion"] or e["error"] or e["estado"] not in ("completa", None)]
    lineas += ["", "## Incidencias", ""]
    if not incidencias and not revision["recuperaciones"]:
        lineas.append("Ninguna.")
    for c, e in incidencias:
        detalle = "; ".join(_sin_repetir([e["interrupcion"], e["error"], e["motivo"]]))
        lineas.append(f"- {c['fecha']} {c['hora']}: {e['estado']} en la ejecución de {e['inicio_utc']}"
                      + (f" ({detalle})" if detalle else "") + f"; `{e['registro']}`.")
    for x in revision["recuperaciones"]:
        lineas.append(f"- Recuperada {x.get('etiqueta')}: {x.get('estado')}"
                      + (f" ({x['motivo']})" if x.get("motivo") else "") + f"; `{x['registro']}`.")
    d = revision["dividendos"]
    lineas += ["", "## Dividendos del objetivo", ""]
    if "error" in d:
        lineas.append(f"La normalización de eventos se detuvo: {d['error']}")
    else:
        lineas += [f"- Versiones: {d['versiones']} de {d['dividendos']} eventos; retiros: "
                   f"{_conteos(d['retiros_por_motivo'], 'ninguno')}.",
                   f"- Discrepancias abiertas: {_conteos(d['discrepancias_abiertas'])}; registradas en total "
                   f"(abiertas o resueltas): {_conteos(d['discrepancias'])}.",
                   f"- Confirmadas por resolución: {d['confirmadas_por_resolucion']}; contradicciones sin valores "
                   f"nuevos: {_conteos(d['contradicciones_sin_valores_nuevos'])}; resoluciones sin efecto: "
                   f"{d['resoluciones_sin_efecto']}."]
    fallidas = [e for e in revision["eventos"] if e.get("estado") != "completa"]
    lineas.append(f"- Consultas de eventos del histórico: {len(revision['eventos'])}; no completas: {len(fallidas)}.")
    return "\n".join(lineas) + "\n"
