"""Informe del piloto: tabla diaria exportable, gráficas y documento Markdown.

Lo que sale de aquí es la interfaz del piloto y va en inglés: nombres de
archivo, encabezados de las tablas, textos de las gráficas y el documento. Los
nombres internos de las columnas siguen en español y se traducen al exportar
(``ENCABEZADOS``), de modo que el CSV que abre quien lee el informe no depende
de cómo se llamen las cosas dentro del código.

Todo se genera desde el ``ResultadoPiloto``: los números del informe se
remontan a la tabla diaria y esta a los archivos de entrada del manifiesto. No
se edita a mano.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import vocabulario
from .piloto import ResultadoPiloto

COLUMNAS_TABLA = [
    "fecha", "hora", "estado_sesion", "motivo_sesion", "vencimiento_1", "dias_1", "vencimiento_2", "dias_2",
    "spot", "forward", "forward_error", "tasa_implicita", "forward_menos_contractual", "log_forward_spot",
    "rr25_estado", "rr25", "rr25_inferior", "rr25_superior", "rr25_motivo", "cambio_rr25",
    "cambio_rr25_inferior", "cambio_rr25_superior", "cambio_rr25_motivo", "asim_log_estado", "asim_log",
    "asim_log_inferior", "asim_log_superior", "asim_log_motivo", "cambio_asim_log", "paridad_pares",
    "paridad_fuera_de_banda", "paridad_interpretables", "paridad_mediana_multiplo", "filas", "filas_validas",
    "filas_solo_cota", "exclusiones", "ancho_ticks_mediano", "edad_mediana_s", "desfase_spot_s", "n_alertas",
    "alertas", "rr25_secundaria", "dif_rr25_secundaria", "dias_naturales_desde_anterior", "retorno_previo",
]


#: columna interna (español) -> encabezado exportado (inglés).
ENCABEZADOS = {
    "fecha": "session", "hora": "cutoff", "estado_sesion": "session_state",
    "motivo_sesion": "session_reason", "vencimiento_1": "expiry_1", "dias_1": "days_1",
    "vencimiento_2": "expiry_2", "dias_2": "days_2", "spot": "spot", "forward": "forward",
    "forward_error": "forward_error", "tasa_implicita": "implied_rate",
    "forward_menos_contractual": "forward_minus_contractual", "log_forward_spot": "log_forward_spot",
    "rr25_estado": "rr25_state", "rr25": "rr25", "rr25_inferior": "rr25_lower",
    "rr25_superior": "rr25_upper", "rr25_motivo": "rr25_reason", "cambio_rr25": "rr25_change",
    "cambio_rr25_inferior": "rr25_change_lower", "cambio_rr25_superior": "rr25_change_upper",
    "cambio_rr25_motivo": "rr25_change_reason", "asim_log_estado": "log_skew_state",
    "asim_log": "log_skew", "asim_log_inferior": "log_skew_lower",
    "asim_log_superior": "log_skew_upper", "asim_log_motivo": "log_skew_reason",
    "cambio_asim_log": "log_skew_change", "paridad_pares": "parity_pairs",
    "paridad_fuera_de_banda": "parity_out_of_band", "paridad_interpretables": "parity_interpretable",
    "paridad_mediana_multiplo": "parity_median_multiple", "filas": "rows",
    "filas_validas": "valid_rows", "filas_solo_cota": "bound_only_rows", "exclusiones": "exclusions",
    "ancho_ticks_mediano": "median_spread_ticks", "edad_mediana_s": "median_age_s",
    "desfase_spot_s": "spot_lag_s", "n_alertas": "n_alerts", "alertas": "alerts",
    "rr25_secundaria": "rr25_secondary", "dif_rr25_secundaria": "rr25_secondary_diff",
    "dias_naturales_desde_anterior": "calendar_days_since_previous",
    "retorno_previo": "previous_return",
    # columnas de etiquetas: decision_at, label_end_at, label_available_at y afines
    "decision_at": "decision_at", "label_end_at": "label_end_at",
    "label_available_at": "label_available_at",
}

#: nombres de los archivos que escribe el informe.
ARCHIVOS = {"tabla_diaria": "daily_table.csv", "tabla_completa": "all_cutoffs_table.csv",
            "etiquetas": "labels.csv", "informe": "report.md"}


def encabezado(columna: str) -> str:
    """Encabezado exportado de una columna interna (``ret_1`` -> ``return_1``)."""
    if columna in ENCABEZADOS:
        return ENCABEZADOS[columna]
    if columna.startswith("estado_ret_"):
        return f"return_{columna.removeprefix('estado_ret_')}_state"
    if columna.startswith("ret_"):
        return f"return_{columna.removeprefix('ret_')}"
    return columna


def _exclusiones(texto) -> dict:
    if not isinstance(texto, str) or not texto:
        return {}
    return {k: int(v) for k, v in (p.split("=") for p in texto.split("; "))}


def escribir_csv(tabla: pd.DataFrame, ruta) -> Path:
    """CSV con encabezados en inglés y formato numérico fijo (mismos bytes por entrada)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tabla = tabla.apply(lambda col: vocabulario.traducir_columna(col, col.name))
    tabla = tabla.rename(columns={c: encabezado(c) for c in tabla.columns})
    tabla.to_csv(ruta, index=False, float_format="%.10g", lineterminator="\n")
    return ruta


def _guardar(ruta):
    plt.savefig(ruta)
    plt.close()
    return ruta


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
        plt.bar(x, valores, bottom=base, label=f"Excluded: {vocabulario.motivo(m)}")
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
    rutas["disponibilidad"] = _guardar(salida / "availability_exclusions.png")

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
    plt.xlabel("Index move since the previous session at 09:45 (%)")
    plt.ylabel("Daily change in RR25 (vol points)")
    plt.title("RR25 change vs the move already observed" + sufijo)
    plt.legend()
    rutas["cambio"] = _guardar(salida / "rr25_change_vs_move.png")

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
    rutas["estabilidad"] = _guardar(salida / "stability_0945_1000.png")
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
    lineas = [f"**{fila['fecha']}**: {vocabulario.estado(fila['estado_sesion'])}; "
              f"RR25 {vocabulario.estado(fila['rr25_estado'])}"
              + (f" ({fila['rr25_motivo']})" if fila["rr25_motivo"] else "")
              + (f"; {fila['motivo_sesion']}" if fila["motivo_sesion"] else "") + "."]
    if fila["alertas"]:
        lineas.append(f"Alerts: {fila['alertas']}.")
    detalle = r.detalles.get((fila["fecha"], r.config.hora_principal), {})
    for venc, d in detalle.items():
        cap, res = d["captura"], d["resultado"]
        excluidas = res.controles.exclusiones(cap)
        F = res.volatilidades.forward
        excluidas.sort(key=lambda e: abs(np.log(e["strike"] / F)))
        lineas.append(f"Expiry {venc} ({d['info']['dias']:.1f} days): {d['calidad']['filas_validas']} of "
                      f"{d['calidad']['filas']} valid rows; exclusions: "
                      f"{', '.join(f'{vocabulario.motivo(k)} {n}' for k, n in sorted(d['calidad']['exclusiones'].items())) or 'none'}.")
        if excluidas:
            lineas.append("")
            lineas.append("| Strike | Type | k = ln(K/F) | Reasons |")
            lineas.append("|---:|---|---:|---|")
            for e in excluidas[:6]:
                lineas.append(f"| {e['strike']:.0f} | {e['tipo']} | {np.log(e['strike'] / F):+.4f} | "
                              f"{', '.join(vocabulario.motivo(m) for m in e['motivos'])} |")
            lineas.append("")
    return lineas


def escribir_informe(r: ResultadoPiloto, salida, titulo, aviso="", manifiesto="manifest.json"):
    """Escribe las tablas, las gráficas y ``report.md`` en ``salida``.

    ``aviso``, si existe, encabeza el documento y marca los títulos de las
    gráficas. Todo el texto que sale de aquí va en inglés.
    """
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    p, cfg = r.principal, r.config
    columnas = COLUMNAS_TABLA + [c for c in p.columns if c.startswith(("ret_", "estado_ret_"))]
    rutas = {
        "tabla_diaria": escribir_csv(p[columnas], salida / ARCHIVOS["tabla_diaria"]),
        "tabla_completa": escribir_csv(r.completa, salida / ARCHIVOS["tabla_completa"]),
        "etiquetas": escribir_csv(r.etiquetas, salida / ARCHIVOS["etiquetas"]),
    }
    rutas.update(figuras(r, salida, aviso))
    d = r.dictamen
    totales = Counter()
    for t in p["exclusiones"]:
        totales.update(_exclusiones(t))
    no_disp = p[p["estado_sesion"] != "procesada"]
    lineas = [f"# {titulo}", ""]
    if aviso:
        lineas += [f"> **{aviso.upper()}.** Generated by the code, not from the market: this document is "
                   "the pilot report template. Its figures say nothing about SPX or about any signal.", ""]
    lineas += [
        f"- Configuration: `{cfg.version}` (fingerprint `{cfg.huella[:12]}`); instrument {cfg.raiz} "
        f"({vocabulario.ejercicio(cfg.ejercicio)}, {cfg.liquidacion} settlement), "
        f"underlying {cfg.subyacente}.",
        f"- Primary cut-off {cfg.hora_principal}, secondary {cfg.hora_secundaria} "
        f"(America/New_York); constant maturity of {cfg.objetivo_dias:g} calendar days; labels at "
        f"{', '.join(map(str, cfg.horizontes))} sessions.",
        f"- Sessions: {len(p)}, from {p['fecha'].min()} to {p['fecha'].max()}.",
        f"- Inputs and hashes: `{manifiesto}`.", "",
        "## Data verdict", "", f"**{d['veredicto'].capitalize()}.**", "",
        "| Criterion | Value | Threshold | Met | Critical |", "|---|---:|---|---|---|",
    ]
    for c in d["criterios"]:
        valor = c["valor"]
        texto = f"{valor:.3f}" if isinstance(valor, float) and np.isfinite(valor) else str(valor)
        lineas.append(f"| {c['criterio']} | {texto} | {c['umbral']} | {'yes' if c['cumple'] else 'no'} | "
                      f"{'yes' if c['critico'] else ''} |")
    lineas += [
        "", "One unmet critical criterion makes the verdict “insufficient”; a non-critical one, "
        "“usable with limitations”. The thresholds live in the configuration and are provisional.", "",
        "## Data quality", "",
        f"- Sessions processed: {int((p['estado_sesion'] == 'procesada').sum())} of {len(p)}.",
    ]
    for _, fila in no_disp.iterrows():
        lineas.append(f"- Not available on {fila['fecha']}: {fila['motivo_sesion']}.")
    lineas += [
        "- Exclusions accumulated at the primary cut-off: "
        + (", ".join(f"{vocabulario.motivo(k)} {n}" for k, n in totales.most_common()) or "none") + ".",
        f"- Median spread width: {_num(p['ancho_ticks_mediano'].median(), 1, 1)} ticks.",
        f"- Sessions with alerts: {int((p['n_alertas'] > 0).sum())}.", "",
        "![Availability and exclusions](availability_exclusions.png)", "",
        "## Signals", "",
        "Conventions: `RR25 = IV(call, delta +0.25) - IV(put, delta -0.25)` with undiscounted forward "
        "delta, `N(d1)` and `N(d1) - 1`; positive means more volatility in the comparable call. The "
        "symmetric log-distance skew compares the call at `F * 1.03` with the put at `F / 1.03`. Both are "
        "interpolated to constant maturity in total variance, leg by leg, and their band comes from bid "
        "and ask. The daily change uses the previous calendar session, at the same cut-off and maturity.",
        "",
        "![RR25](rr25_30d.png)", "",
        "![RR25 change against the move already observed](rr25_change_vs_move.png)", "",
        "The visual relationship between RR25 changes and moves is exploratory: this pilot does not "
        "evaluate predictive ability.", "",
        "## Stability between 09:45 and 10:00", "",
        f"Median |RR25(10:00) - RR25(09:45)|: {_num(p['dif_rr25_secundaria'].abs().median(), 100)} points; "
        f"median band width at 09:45: "
        f"{_num((p['rr25_superior'] - p['rr25_inferior']).median(), 100)} points.", "",
        "![Stability](stability_0945_1000.png)", "",
        "## Daily table", "",
        f"Complete in `{ARCHIVOS['tabla_diaria']}` (primary cut-off) and "
        f"`{ARCHIVOS['tabla_completa']}`. RR25 and changes in volatility points; returns in percent.", "",
        "| Session | RR25 | Band | Change | Log skew | Valid/rows | Alerts | Prev. return | Ret. 1 | "
        "Ret. 5 |",
        "|---|---:|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for _, f in p.iterrows():
        banda = (f"[{_num(f['rr25_inferior'], 100)}, {_num(f['rr25_superior'], 100)}]"
                 if np.isfinite(f["rr25"]) else "")
        rr = _num(f["rr25"], 100) or vocabulario.estado(f["rr25_estado"])
        lineas.append(f"| {f['fecha']} | {rr} | {banda} | {_num(f['cambio_rr25'], 100)} | "
                      f"{_num(f['asim_log'], 100)} | {f['filas_validas']}/{f['filas']} | {f['n_alertas']} | "
                      f"{_num(f['retorno_previo'], 100)} | {_num(f.get('ret_1', np.nan), 100)} | "
                      f"{_num(f.get('ret_5', np.nan), 100)} |")
    normal, problema = _ejemplos(r)
    lineas += ["", "## Examples", ""]
    for nombre, fila in (("Normal session", normal), ("Problematic session", problema)):
        lineas.append(f"### {nombre}")
        lineas.append("")
        lineas += _detalle_sesion(r, fila) if fila is not None else ["There is none in the sample."]
        lineas.append("")
    lineas += [
        "## Limitations", "",
        "- SPX returns are research labels: the index is not bought directly, and a policy on SPY or "
        "futures will need its own prices, costs and dividends.",
        "- The 5-session labels overlap: they are not independent observations.",
        "- The forward reference uses a fixed rate and dividend yield from the configuration, not a "
        "sourced curve.",
        "- The quality and verdict thresholds are provisional until this pilot is reviewed.",
    ]
    if int((p["filas_validas"] > 0).sum()) and p["edad_mediana_s"].isna().any():
        lineas.append("- Some sessions have no event timestamp on the quotes: there the age is unknown "
                      "and the staleness control was not applied.")
    lineas.append("")
    rutas["informe"] = salida / ARCHIVOS["informe"]
    rutas["informe"].write_text("\n".join(lineas), encoding="utf-8")
    return rutas
