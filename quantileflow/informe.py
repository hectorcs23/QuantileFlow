"""Informe del piloto: tabla diaria exportable, gráficas y documento Markdown.

Las gráficas usan matplotlib con su estilo por defecto, una por figura y con
textos en inglés; el documento las explica en español. Todo se genera desde el
``ResultadoPiloto``: los números del informe se remontan a la tabla diaria y
esta a los archivos de entrada del manifiesto. No se edita a mano.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .piloto import ResultadoPiloto

COLUMNAS_TABLA = [
    "fecha", "hora", "estado_sesion", "motivo_sesion", "fuente_opciones", "fuente_subyacente",
    "tipo_precio_subyacente", "segmento", "vencimiento_1", "dias_1", "vencimiento_2", "dias_2",
    "spot", "forward", "forward_error", "tasa_implicita", "forward_menos_contractual", "log_forward_spot",
    "rr25_estado", "rr25", "rr25_inferior", "rr25_superior", "rr25_motivo", "cambio_rr25",
    "cambio_rr25_inferior", "cambio_rr25_superior", "cambio_rr25_motivo", "asim_log_estado", "asim_log",
    "asim_log_inferior", "asim_log_superior", "asim_log_motivo", "cambio_asim_log", "paridad_pares",
    "paridad_fuera_de_banda", "paridad_interpretables", "paridad_mediana_multiplo", "filas", "filas_validas",
    "filas_solo_cota", "exclusiones", "ancho_ticks_mediano", "edad_mediana_s", "desfase_spot_s", "n_alertas",
    "alertas", "rr25_secundaria", "dif_rr25_secundaria", "dias_naturales_desde_anterior", "retorno_previo",
]


def _exclusiones(texto) -> dict:
    if not isinstance(texto, str) or not texto:
        return {}
    return {k: int(v) for k, v in (p.split("=") for p in texto.split("; "))}


def escribir_csv(tabla: pd.DataFrame, ruta) -> Path:
    """CSV con formato numérico fijo para que la misma entrada dé los mismos bytes."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(ruta, index=False, float_format="%.10g", lineterminator="\n")
    return ruta


def _guardar(ruta):
    plt.savefig(ruta)
    plt.close()
    return ruta


def objetivo_en_ingles(r: ResultadoPiloto) -> str:
    """Nombre del precio objetivo para las gráficas: nunca presenta un nivel implícito como el índice."""
    if r.dictamen.get("alcance", {}).get("tipo_precio_subyacente") == "implicito":
        return f"Implied {r.config.subyacente} level (option parity)"
    return r.config.subyacente


def figuras(r: ResultadoPiloto, salida: Path, aviso="") -> dict:
    """Cuatro gráficas del informe; ``aviso`` (en inglés) se añade al título."""
    p = r.principal
    x = np.arange(len(p))
    etiquetas_x = [str(f)[5:] for f in p["fecha"]]
    sufijo = f" ({aviso})" if aviso else ""
    rutas = {}

    plt.figure()
    excl = [_exclusiones(t) for t in p["exclusiones"]]
    motivos = [m for m, _ in Counter({k: v for e in excl for k, v in e.items()}).most_common(4)]
    plt.bar(x, p["filas_validas"], label="Valid rows")
    base = p["filas_validas"].to_numpy(float)
    for m in motivos:
        valores = np.array([e.get(m, 0) for e in excl], dtype=float)
        plt.bar(x, valores, bottom=base, label=f"Excluded: {m}")
        base = base + valores
    otros = p["filas"].to_numpy(float) - base
    if np.any(otros > 0):
        plt.bar(x, np.maximum(otros, 0), bottom=base, label="Excluded: other reasons")
    no_disp = np.flatnonzero(p["estado_sesion"] != "procesada")
    if len(no_disp):
        plt.plot(no_disp, np.zeros(len(no_disp)), "kx", markersize=10, label="Session not available")
    plt.ylim(0, max(float(p["filas"].max()), 1.0) * 1.5)  # espacio para la leyenda
    plt.xticks(x, etiquetas_x, rotation=90)
    plt.xlabel("Session (month-day)")
    plt.ylabel("Quote rows in the two expiries used")
    plt.title("Usable and excluded quotes by session" + sufijo)
    plt.legend()
    plt.tight_layout()
    rutas["disponibilidad"] = _guardar(salida / "disponibilidad_exclusiones.png")

    ok = p["rr25_estado"] == "identificada"
    plt.figure()
    plt.errorbar(x[ok], p.loc[ok, "rr25"] * 100,
                 yerr=[(p.loc[ok, "rr25"] - p.loc[ok, "rr25_inferior"]) * 100,
                       (p.loc[ok, "rr25_superior"] - p.loc[ok, "rr25"]) * 100],
                 fmt="o", capsize=3, label="RR25 at 30 days with bid-ask band")
    if (~ok).any():
        nivel = np.nanmedian(p.loc[ok, "rr25"]) * 100 if ok.any() else 0.0
        plt.plot(x[~ok], np.full((~ok).sum(), nivel), "rx", markersize=10, label="Not identified")
    plt.xticks(x, etiquetas_x, rotation=90)
    plt.xlabel("Session (month-day)")
    plt.ylabel("IV(call, delta 0.25) - IV(put, delta -0.25), vol points")
    plt.title("25-delta risk reversal at 09:45" + sufijo)
    plt.legend()
    plt.tight_layout()
    rutas["rr25"] = _guardar(salida / "rr25_30d.png")

    c = p["cambio_rr25"].notna() & p["retorno_previo"].notna()
    plt.figure()
    plt.errorbar(p.loc[c, "retorno_previo"] * 100, p.loc[c, "cambio_rr25"] * 100,
                 yerr=[(p.loc[c, "cambio_rr25"] - p.loc[c, "cambio_rr25_inferior"]) * 100,
                       (p.loc[c, "cambio_rr25_superior"] - p.loc[c, "cambio_rr25"]) * 100],
                 fmt="o", capsize=3, label="Sessions with both RR25 values identified")
    plt.axhline(0.0, color="k", linestyle="--", linewidth=1)
    plt.xlabel(f"{objetivo_en_ingles(r)}: move since the previous session at 09:45 (%)")
    plt.ylabel("Daily change in RR25 (vol points)")
    plt.title("RR25 change vs the move already observed" + sufijo)
    plt.legend()
    rutas["cambio"] = _guardar(salida / "cambio_rr25_vs_movimiento.png")

    s = p["rr25"].notna() & p["rr25_secundaria"].notna() if "rr25_secundaria" in p else pd.Series(False, index=p.index)
    plt.figure()
    if s.any():
        valores = pd.concat([p.loc[s, "rr25"], p.loc[s, "rr25_secundaria"]]) * 100
        extremos = [valores.min() - 0.2, valores.max() + 0.2]
        plt.plot(p.loc[s, "rr25"] * 100, p.loc[s, "rr25_secundaria"] * 100, "o", label="Session")
        plt.plot(extremos, extremos, "k--", label="Same value at both times")
    plt.xlabel("RR25 at 09:45 (vol points)")
    plt.ylabel("RR25 at 10:00 (vol points)")
    plt.title("Measurement stability between cut-off times" + sufijo)
    plt.legend()
    rutas["estabilidad"] = _guardar(salida / "estabilidad_0945_1000.png")
    return rutas


def _num(x, factor=1.0, decimales=2):
    return "" if x is None or not np.isfinite(x) else f"{x * factor:.{decimales}f}"


def _ejemplos(r: ResultadoPiloto):
    p = r.principal
    normales = p[(p["rr25_estado"] == "identificada") & (p["n_alertas"] == 0)]
    normal = normales.sort_values("filas_validas", ascending=False).iloc[0] if len(normales) else None
    problemas = p[(p["rr25_estado"] != "identificada") | (p["n_alertas"] > 0)]
    problema = problemas.iloc[0] if len(problemas) else None
    return normal, problema


def _detalle_sesion(r: ResultadoPiloto, fila) -> list[str]:
    lineas = [f"**{fila['fecha']}**: {fila['estado_sesion']}; RR25 {fila['rr25_estado']}"
              + (f" ({fila['rr25_motivo']})" if fila["rr25_motivo"] else "")
              + (f"; {fila['motivo_sesion']}" if fila["motivo_sesion"] else "") + "."]
    if fila["alertas"]:
        lineas.append(f"Alertas: {fila['alertas']}.")
    detalle = r.detalles.get((fila["fecha"], r.config.hora_principal), {})
    for venc, d in detalle.items():
        cap, res = d["captura"], d["resultado"]
        excluidas = res.controles.exclusiones(cap)
        F = res.volatilidades.forward
        excluidas.sort(key=lambda e: abs(np.log(e["strike"] / F)))
        lineas.append(f"Vencimiento {venc} ({d['info']['dias']:.1f} días): {d['calidad']['filas_validas']} de "
                      f"{d['calidad']['filas']} filas válidas; exclusiones: "
                      f"{', '.join(f'{k} {n}' for k, n in sorted(d['calidad']['exclusiones'].items())) or 'ninguna'}.")
        if excluidas:
            lineas.append("")
            lineas.append("| Strike | Tipo | k = ln(K/F) | Motivos |")
            lineas.append("|---:|---|---:|---|")
            for e in excluidas[:6]:
                lineas.append(f"| {e['strike']:.0f} | {e['tipo']} | {np.log(e['strike'] / F):+.4f} | "
                              f"{', '.join(e['motivos'])} |")
            lineas.append("")
    return lineas


def escribir_informe(r: ResultadoPiloto, salida, titulo, aviso="", aviso_figuras="synthetic data",
                     manifiesto="manifiesto.json"):
    """Escribe tabla diaria, etiquetas, gráficas e ``informe.md`` en ``salida``.

    ``aviso`` (en español) encabeza el documento; si existe, ``aviso_figuras``
    (en inglés) marca también los títulos de las gráficas.
    """
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    p, cfg = r.principal, r.config
    columnas = COLUMNAS_TABLA + [c for c in p.columns if c.startswith(("ret_", "estado_ret_"))]
    rutas = {
        "tabla_diaria": escribir_csv(p[columnas], salida / "tabla_diaria.csv"),
        "tabla_completa": escribir_csv(r.completa, salida / "tabla_todas_las_horas.csv"),
        "etiquetas": escribir_csv(r.etiquetas, salida / "etiquetas.csv"),
    }
    rutas.update(figuras(r, salida, aviso_figuras if aviso else ""))
    d = r.dictamen
    al = d["alcance"]
    totales = Counter()
    for t in p["exclusiones"]:
        totales.update(_exclusiones(t))
    no_disp = p[p["estado_sesion"] != "procesada"]
    lineas = [f"# {titulo}", ""]
    if aviso:
        lineas += [f"> **{aviso.upper()}.** Datos generados por el código, no de mercado: este documento es la "
                   "plantilla del informe piloto. Sus cifras no dicen nada sobre SPX ni sobre ninguna señal.", ""]
    lineas += [
        f"- Configuración: `{cfg.version}` (huella `{cfg.huella[:12]}`); instrumento {cfg.raiz} "
        f"({cfg.ejercicio}, liquidación {cfg.liquidacion}), subyacente {cfg.subyacente}.",
        f"- Corte principal {cfg.hora_principal} y secundario {cfg.hora_secundaria} (America/New_York); "
        f"plazo constante de {cfg.objetivo_dias:g} días naturales; etiquetas a {', '.join(map(str, cfg.horizontes))} "
        "sesiones.",
        f"- Sesiones: {len(p)}, del {p['fecha'].min()} al {p['fecha'].max()}.",
        f"- Fuentes: opciones {', '.join(al['fuentes_opciones']) or 'ninguna'}; precio objetivo "
        f"{al['fuente_subyacente'] or 'ninguno'} ({al['precio_objetivo']}).",
        f"- Entradas y hashes: `{manifiesto}`.", "",
        "## Dictamen de datos", "", f"**{d['veredicto'].capitalize()}.**", "",
        "| Criterio | Valor | Umbral | Cumple | Crítico |", "|---|---:|---|---|---|",
    ]
    for c in d["criterios"]:
        valor = c["valor"]
        texto = f"{valor:.3f}" if isinstance(valor, float) and np.isfinite(valor) else str(valor)
        lineas.append(f"| {c['criterio']} | {texto} | {c['umbral']} | {'sí' if c['cumple'] else 'no'} | "
                      f"{'sí' if c['critico'] else ''} |")
    lineas += [
        "", "Un criterio crítico incumplido hace el dictamen «insuficiente»; uno no crítico, «apto con "
        "limitaciones». Los umbrales están en la configuración y son provisionales.", "",
        "**Alcance**, aparte de la aptitud de los datos:", "",
        f"- Medición: {al['medicion']}.",
        f"- Precio objetivo: {al['precio_objetivo']}.",
        f"- Evaluación con precios de mercado: {al['evaluacion_con_precios_de_mercado']}.", "",
        "## Calidad de los datos", "",
        f"- Sesiones procesadas: {int((p['estado_sesion'] == 'procesada').sum())} de {len(p)}.",
    ]
    for _, fila in no_disp.iterrows():
        lineas.append(f"- No disponible el {fila['fecha']}: {fila['motivo_sesion']}.")
    lineas += [
        "- Exclusiones acumuladas a la hora principal: "
        + (", ".join(f"{k} {n}" for k, n in totales.most_common()) or "ninguna") + ".",
        f"- Ancho mediano de spread: {_num(p['ancho_ticks_mediano'].median(), 1, 1)} ticks.",
        f"- Sesiones con alertas: {int((p['n_alertas'] > 0).sum())}.", "",
        "![Disponibilidad y exclusiones](disponibilidad_exclusiones.png)", "",
        "## Señales", "",
        "Convenciones: `RR25 = IV(call, delta +0.25) - IV(put, delta -0.25)` con delta forward sin descuento, "
        "`N(d1)` y `N(d1) - 1`; positivo significa mayor volatilidad en el call comparable. La asimetría a "
        "distancia logarítmica simétrica compara el call en `F * 1.03` con el put en `F / 1.03`. Ambas se "
        "interpolan a plazo constante en varianza total, pata por pata, y su banda sale de bid y ask. El "
        "cambio diario usa la sesión anterior del calendario, a la misma hora y plazo.", "",
        "![RR25](rr25_30d.png)", "",
        "![Cambio de RR25 frente al movimiento previo](cambio_rr25_vs_movimiento.png)", "",
        "La relación visual entre cambios de RR25 y movimientos es exploratoria: este piloto no evalúa "
        "capacidad predictiva.", "",
        "## Estabilidad entre 09:45 y 10:00", "",
        f"Mediana de |RR25(10:00) - RR25(09:45)|: {_num(p['dif_rr25_secundaria'].abs().median(), 100)} puntos; "
        f"mediana del ancho de banda a las 09:45: "
        f"{_num((p['rr25_superior'] - p['rr25_inferior']).median(), 100)} puntos.", "",
        "![Estabilidad](estabilidad_0945_1000.png)", "",
        "## Tabla diaria", "",
        "Completa en `tabla_diaria.csv` (hora principal) y `tabla_todas_las_horas.csv`. RR25 y cambios en "
        "puntos de volatilidad; rendimientos en porcentaje.", "",
        "| Sesión | RR25 | Banda | Cambio | Asim. log | Válidas/filas | Alertas | Rend. previo | Rend. 1 | Rend. 5 |",
        "|---|---:|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for _, f in p.iterrows():
        banda = (f"[{_num(f['rr25_inferior'], 100)}, {_num(f['rr25_superior'], 100)}]"
                 if np.isfinite(f["rr25"]) else "")
        rr = _num(f["rr25"], 100) or f["rr25_estado"]
        lineas.append(f"| {f['fecha']} | {rr} | {banda} | {_num(f['cambio_rr25'], 100)} | "
                      f"{_num(f['asim_log'], 100)} | {f['filas_validas']}/{f['filas']} | {f['n_alertas']} | "
                      f"{_num(f['retorno_previo'], 100)} | {_num(f.get('ret_1', np.nan), 100)} | "
                      f"{_num(f.get('ret_5', np.nan), 100)} |")
    normal, problema = _ejemplos(r)
    lineas += ["", "## Ejemplos", ""]
    for nombre, fila in (("Sesión normal", normal), ("Sesión problemática", problema)):
        lineas.append(f"### {nombre}")
        lineas.append("")
        lineas += _detalle_sesion(r, fila) if fila is not None else ["No hay ninguna en la muestra."]
        lineas.append("")
    if al["tipo_precio_subyacente"] == "implicito":
        objetivo = (f"- Las etiquetas son rendimientos del nivel de {cfg.subyacente} inferido por paridad de las "
                    "mismas opciones: comparten fuente y errores de medición con las señales y no sustituyen al "
                    "índice observado. Antes de evaluar predicción hay que compararlas con una referencia observada.")
    else:
        objetivo = (f"- Los rendimientos de {cfg.subyacente} son etiquetas de investigación: el índice no se compra "
                    "directamente, y una política sobre SPY o futuros necesitará sus propios precios, costos y "
                    "dividendos.")
    lineas += [
        "## Limitaciones", "",
        objetivo,
        "- Las etiquetas a 5 sesiones se solapan: no son observaciones independientes.",
        "- La referencia del forward usa una tasa y un rendimiento de dividendo fijos de la configuración, "
        "no una curva con fuente.",
        "- Los umbrales de calidad y del dictamen son provisionales hasta revisar este piloto.",
    ]
    if int((p["filas_validas"] > 0).sum()) and p["edad_mediana_s"].isna().any():
        lineas.append("- Hay sesiones sin hora de evento en las cotizaciones: en ellas la edad es desconocida y "
                      "el control de desfase no se aplicó.")
    lineas.append("")
    rutas["informe"] = salida / "informe.md"
    rutas["informe"].write_text("\n".join(lineas), encoding="utf-8")
    return rutas
