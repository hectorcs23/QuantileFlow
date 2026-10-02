"""Informe del recomendador: tabla de candidatas, gráficas y documento Markdown.

Las gráficas usan matplotlib con su estilo por defecto, una por figura y con
textos en inglés; el documento las explica en español. Todo sale del resultado
de ``recomendacion.recomendar``: ningún número del informe se escribe a mano.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .evaluacion import ventaja_put_por_strike  # noqa: E402

COLUMNAS = ["estructura", "papel", "direccion", "apta", "precio", "ventaja", "ventaja_sin_costos",
            "coste_ejecucion", "residuo_ajuste", "ventaja_peor_caso", "escenario_peor",
            "signo_estable", "capital",
            "rendimiento_sobre_capital", "cvar", "var", "prob_ganancia", "perdida_maxima",
            "ganancia_maxima", "equilibrio", "ventaja_no_fiable", "fraccion_no_fiable",
            "cota_extrapolacion", "motivos"]


def tabla(resultado) -> pd.DataFrame:
    filas = []
    for f in resultado["filas"]:
        ev, rob = f["evaluacion"], f["robustez"]
        filas.append({
            "estructura": f["estructura"].nombre, "papel": f["papel"],
            "direccion": f["estructura"].direccion, "apta": f["apta"],
            "precio": ev.precio, "ventaja": ev.ventaja,
            "ventaja_sin_costos": ev.ventaja_sin_costos, "coste_ejecucion": ev.coste_ejecucion,
            "residuo_ajuste": ev.residuo_ajuste,
            "ventaja_peor_caso": rob["ventaja_peor_caso"], "escenario_peor": rob["escenario_peor"],
            "signo_estable": rob["signo_estable"], "capital": ev.capital,
            "rendimiento_sobre_capital": ev.rendimiento_sobre_capital,
            "cvar": ev.cvar, "var": ev.var, "prob_ganancia": ev.prob_ganancia,
            "perdida_maxima": ev.perdida_maxima, "ganancia_maxima": ev.ganancia_maxima,
            "equilibrio": "; ".join(f"{x:.2f}" for x in ev.equilibrio),
            "ventaja_no_fiable": ev.ventaja_no_fiable,
            "fraccion_no_fiable": ev.fraccion_no_fiable,
            "cota_extrapolacion": ev.cota_extrapolacion,
            "motivos": " | ".join(f["motivos"]),
        })
    return pd.DataFrame(filas, columns=COLUMNAS)


def escribir_csv(t: pd.DataFrame, ruta) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(ruta, index=False, float_format="%.10g", lineterminator="\n")
    return ruta


def _guardar(ruta):
    plt.savefig(ruta)
    plt.close()
    return ruta


def figuras(resultado, p, q, mercado, salida: Path, aviso="") -> dict:
    """Cuatro gráficas: distribuciones, ventaja por strike, perfiles y riesgo."""
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    sufijo = f" ({aviso})" if aviso else ""
    F, D = mercado.F, mercado.D
    lo, hi = q.rango_fiable
    rutas = {}

    plt.figure()
    plt.plot(q.s / F, q.p, label="Q (implied)")
    plt.plot(p.s / F, p.p, label="P (view)")
    plt.axvspan(lo / F, hi / F, alpha=0.12, label="quoted strike range")
    plt.xlim(0.80, 1.20)
    plt.xlabel("$S_T / F$")
    plt.ylabel("probability per grid point")
    plt.title("Implied vs view distribution" + sufijo)
    plt.legend()
    rutas["distribuciones"] = _guardar(salida / "distribuciones.png")

    plt.figure()
    K = np.linspace(0.74 * F, 1.16 * F, 240)
    plt.plot(K / F, ventaja_put_por_strike(p, q, D, K))
    plt.axhline(0.0, linewidth=0.8)
    plt.axvspan(lo / F, hi / F, alpha=0.12, label="quoted strike range")
    plt.xlabel("$K / F$")
    plt.ylabel("edge of selling one put (PV)")
    plt.title(r"Edge of a short put: $D\int_0^K (F_Q - F_P)\,ds$" + sufijo)
    plt.legend()
    rutas["ventaja_por_strike"] = _guardar(salida / "ventaja_por_strike.png")

    plt.figure()
    s = np.linspace(0.80 * F, 1.20 * F, 400)
    mostradas = (resultado["aptas"] or resultado["filas"])[:3]
    for f in mostradas:
        ev = f["evaluacion"]
        if not ev.identificada:
            continue
        coste = (ev.precio + ev.comisiones) / D
        plt.plot(s / F, f["estructura"].pago(s) - coste, label=f["estructura"].nombre)
    plt.axhline(0.0, linewidth=0.8)
    plt.axvline(1.0, linewidth=0.8, linestyle=":")
    plt.xlabel("$S_T / F$")
    plt.ylabel("payoff at expiry, net of premium")
    plt.title("Result profiles of the leading candidates" + sufijo)
    plt.legend(fontsize="small")
    rutas["perfiles"] = _guardar(salida / "perfiles.png")

    plt.figure()
    for apta, marca in ((True, "o"), (False, "x")):
        xs = [f["evaluacion"].cvar * D for f in resultado["filas"]
              if f["apta"] is apta and f["evaluacion"].identificada
              and np.isfinite(f["evaluacion"].capital)]
        ys = [f["evaluacion"].ventaja for f in resultado["filas"]
              if f["apta"] is apta and f["evaluacion"].identificada
              and np.isfinite(f["evaluacion"].capital)]
        if xs:
            plt.scatter(xs, ys, marker=marca, label="passes the filters" if apta else "discarded")
    plt.axhline(0.0, linewidth=0.8)
    plt.xscale("log")
    plt.xlabel("CVaR of the loss, present value (log scale)")
    plt.ylabel("expected edge (PV)")
    plt.title("Edge against tail risk, all candidates" + sufijo)
    plt.legend()
    rutas["ventaja_riesgo"] = _guardar(salida / "ventaja_riesgo.png")
    return rutas


def _fila_md(f):
    ev, rob = f["evaluacion"], f["robustez"]
    if not ev.identificada:
        return (f"| {f['estructura'].nombre} | {f['papel']} | — | — | — | — | — | "
                f"no evaluable |")
    roc = (f"{ev.rendimiento_sobre_capital:+.3%}"
           if np.isfinite(ev.rendimiento_sobre_capital) else "—")
    frac = f"{ev.fraccion_no_fiable:+.0%}" if np.isfinite(ev.fraccion_no_fiable) else "—"
    cap = f"{ev.capital:.2f}" if np.isfinite(ev.capital) else "no acotado"
    return (f"| {f['estructura'].nombre} | {f['papel']} | {ev.ventaja:+.4f} | "
            f"{rob['ventaja_peor_caso']:+.4f} | {cap} | {roc} | {ev.cvar:.2f} | {frac} |")


def escribir_informe(resultado, p, q, mercado, salida, titulo, aviso="",
                     aviso_figuras="synthetic data", contexto=None):
    """Escribe ``candidatas.csv``, las gráficas e ``informe.md`` en ``salida``."""
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    cfg, d, dic = resultado["config"], resultado["diagnostico"], resultado["dictamen"]
    rutas = {"candidatas": escribir_csv(tabla(resultado), salida / "candidatas.csv")}
    rutas.update(figuras(resultado, p, q, mercado, salida, aviso_figuras if aviso else ""))
    F, D = mercado.F, mercado.D
    ctx = contexto or {}

    L = [f"# {titulo}", ""]
    if aviso:
        L += [f"> **{aviso.upper()}.** Las cotizaciones las genera el propio código. Este documento "
              "es la plantilla del informe: sus cifras no dicen nada sobre ningún activo real, y "
              "en ningún caso son una recomendación de inversión.", ""]
    L += [
        f"- Configuración: `{cfg.version}`; ejecución **{cfg.modo_ejecucion}**, comisión "
        f"{mercado.comision:g} por pata y unidad.",
        f"- Vencimiento: {ctx.get('dias', mercado.T * 365.0):.1f} días; forward {F:.4f}; "
        f"descuento {D:.6f}; {mercado.detalle.get('n_fiables', '?')} de "
        f"{mercado.detalle.get('n_cotizaciones', '?')} cotizaciones utilizables.",
        f"- Rango de strikes respaldado por cotizaciones: [{q.rango_fiable[0]:.2f}, "
        f"{q.rango_fiable[1]:.2f}], es decir [{q.rango_fiable[0] / F:.3f}, "
        f"{q.rango_fiable[1] / F:.3f}] en unidades del forward.",
        f"- `Q`: {q.origen}. `P`: {p.origen}.", "",
        "## Dictamen", "",
        f"**{dic['accion'].upper()}.** {dic['texto']}", "",
    ]
    if resultado["motivos_globales"]:
        L += ["Puertas globales que fallan:", ""]
        L += [f"- {m}" for m in resultado["motivos_globales"]] + [""]

    L += ["## En qué discrepa la vista del mercado", "",
          f"- Rendimiento esperado sobre el forward: **{d['retorno_vista']:+.2%}**.",
          f"- Desviación típica de `ln(S_T/F)`: vista {d['sd_log_p']:.4f} frente a implícita "
          f"{d['sd_log_q']:.4f} (factor {d['factor_vol']:.3f}).",
          f"- Asimetría: vista {d['asimetria_p']:+.3f} frente a implícita {d['asimetria_q']:+.3f}.",
          f"- Probabilidad de caer un 5 %: vista {d['prob_caida_5_p']:.2%} frente a implícita "
          f"{d['prob_caida_5_q']:.2%}. De caer un 10 %: {d['prob_caida_10_p']:.2%} frente a "
          f"{d['prob_caida_10_q']:.2%}.",
          f"- Entropía relativa `KL(P||Q)`: **{d['kl_p_sobre_q']:.5f}** nats "
          f"(máximo admitido {cfg.kl_max:g}).", "",
          "Toda la ventaja de cualquier estructura sale de estas diferencias. Si la vista fuera "
          "`P = Q`, la columna de ventaja sería exactamente cero antes de costos y negativa "
          "después.", "",
          "### Ventaja de vender exposición a la caída, por tramo de precio", "",
          "Cada fila es `D * int (F_Q - F_P) ds` sobre el tramo: positivo significa que el mercado "
          "asigna más probabilidad acumulada que la vista a esa zona, de modo que **vender** la "
          "caída dentro de ese tramo tiene ventaja. Es la descomposición que decide qué strike "
          "expresa la opinión.", "",
          "| Desde | Hasta | Prob. Q | Prob. P | Ventaja |", "|---|---|---|---|---|"]
    for t in d["tramos"]:
        L.append(f"| {t['desde']:.2f} | {t['hasta']:.2f} | {t['prob_q']:.4f} | "
                 f"{t['prob_p']:.4f} | {t['ventaja']:+.5f} |")

    L += ["", "![Distribuciones](distribuciones.png)", "",
          "La vista frente a la implícita. La banda marca el rango de strikes con cotizaciones "
          "utilizables: fuera de ella la forma de ambas distribuciones es extrapolación.", "",
          "![Ventaja por strike](ventaja_por_strike.png)", "",
          "Ventaja de vender un put de cada strike. Su máximo señala dónde la discrepancia pesa "
          "más en prima; fuera de la banda, la curva depende de lo que nadie cotiza.", "",
          "## Candidatas", "",
          f"Escenarios de robustez: {', '.join(resultado['escenarios'])}. La columna «peor» es la "
          "ventaja mínima entre ellos. «No fiable» es la parte de la ventaja que procede de la "
          "zona sin cotizaciones utilizables.", "",
          "| Estructura | Papel | Ventaja | Peor | Capital | Sobre capital | CVaR | No fiable |",
          "|---|---|---|---|---|---|---|---|"]
    L += [_fila_md(f) for f in resultado["filas"]]

    L += ["", "![Perfiles](perfiles.png)", "",
          "Resultado al vencimiento de las candidatas principales, neto de la prima capitalizada.",
          "", "![Ventaja y riesgo](ventaja_riesgo.png)", "",
          "Ventaja esperada frente al CVaR de la pérdida. Las estructuras con más ventaja suelen "
          "ser también las de más cola: la puntuación penaliza el CVaR para no confundirlas.", "",
          "## Vender o comprar puts", ""]
    for etiqueta, clave in (("Mejor forma de **vender** puts", "mejor_venta_puts"),
                            ("Mejor forma de **comprar** puts", "mejor_compra_puts"),
                            ("Mejor alternativa **sin** puts", "mejor_sin_puts")):
        f = dic[clave]
        if f is None:
            L.append(f"- {etiqueta}: ninguna candidata evaluable.")
            continue
        ev = f["evaluacion"]
        estado = "pasa los filtros" if f["apta"] else f"descartada ({f['motivos'][0]})"
        L.append(f"- {etiqueta}: `{f['estructura'].nombre}` ({f['estructura'].direccion}), "
                 f"ventaja {ev.ventaja:+.4f}; {estado}.")
    L += ["", "## Descartes", ""]
    descartadas = [f for f in resultado["filas"] if not f["apta"]]
    if not descartadas:
        L.append("Ninguna: todas las candidatas pasan los filtros.")
    for f in descartadas:
        L.append(f"- `{f['estructura'].nombre}`: " + "; ".join(f["motivos"]) + ".")

    L += ["", "## Lo que este informe no dice", "",
          "- **No hay evidencia de que la vista acierte.** La ventaja es una resta entre lo que "
          "dice la vista y lo que dice el precio; si la vista está mal, el signo se invierte.",
          "- **El CVaR y la pérdida máxima se calculan bajo la vista**, que es justamente la parte "
          "optimista del cálculo. La pérdida real de un put vendido llega cuando la vista falla.",
          "- **El capital es una regla propia** (peor caso en valor presente), no el margen que "
          "exigiría un intermediario, que depende de su propio modelo y puede cambiar intradía.",
          "- **La probabilidad de ganar no es un criterio.** Un put muy fuera del dinero gana casi "
          "siempre y eso ya está en su precio; se reporta porque se suele mirar.",
          "- No hay ejecución, ni gestión de la posición antes del vencimiento, ni asignación "
          "anticipada, ni dividendos, ni impuestos, ni límite de concentración entre vencimientos.",
          ""]
    ruta = salida / "informe.md"
    ruta.write_text("\n".join(L), encoding="utf-8")
    rutas["informe"] = ruta
    return rutas
