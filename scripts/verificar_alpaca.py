"""Diagnóstico de las capturas de Alpaca de una fecha: elegibilidad, calidad del feed y medidas.

Uso, desde la raíz del repositorio::

    python scripts/verificar_alpaca.py --fecha 2026-09-28
    python scripts/verificar_alpaca.py --fecha 2026-09-25 --cierre-descriptivo

Lee el crudo y los manifiestos (comprobando hashes), procesa cada vencimiento con
los controles y medidas del piloto y escribe en
``reports/verificacion_alpaca/<fecha>/`` un resumen en JSON, un informe
Markdown y dos gráficas. Solo publica **agregados y medidas derivadas**
(conteos, anchos, volatilidades implícitas, residuos relativos): nunca
cotizaciones individuales, que no se pueden redistribuir.

La elegibilidad al corte usa siempre los controles estrictos. Con
``--cierre-descriptivo``, una captura inmediata recibida con la sesión cerrada se
describe además sin horas de snapshot ni de disponibilidad, y el informe la marca
como no elegible para el piloto (``quantileflow/diagnostico.py``).
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from quantileflow import almacen, diagnostico  # noqa: E402
from quantileflow.calendario import _fecha  # noqa: E402
from quantileflow.piloto import cargar_config  # noqa: E402

K_MIN_GRAFICA, K_MAX_GRAFICA = -0.25, 0.12  # región central de la sonrisa en la gráfica


def graficas(resultados, salida, titulo):
    """Sonrisa con bandas bid/ask y residuos de paridad del vencimiento más cercano a 30 días."""
    rutas = {}
    venc, dias, res = resultados
    v, p = res.volatilidades, res.paridad
    plt.figure()
    for es_call, nombre in ((False, "OTM puts"), (True, "OTM calls")):
        m = (v.es_call == es_call) & np.isfinite(v.iv) & (v.k >= K_MIN_GRAFICA) & (v.k <= K_MAX_GRAFICA)
        plt.errorbar(v.k[m], v.iv[m] * 100, yerr=[(v.iv[m] - v.iv_bid[m]) * 100, (v.iv_ask[m] - v.iv[m]) * 100],
                     fmt="o", markersize=3, capsize=2, label=nombre)
    plt.xlabel("Log-moneyness k = ln(K/F), central region")
    plt.ylabel("Implied volatility (%), mid with bid-ask band")
    plt.title(f"{titulo}: {venc} ({dias:.1f} days)")
    plt.legend()
    rutas["sonrisa"] = salida / "sonrisa_30d.png"
    plt.savefig(rutas["sonrisa"])
    plt.close()

    plt.figure()
    k = np.log(p.strike / v.forward)
    dentro = ~p.fuera_de_banda
    plt.plot(k[dentro], p.multiplo_ancho[dentro], "o", markersize=3, label="Inside the bid-ask band")
    plt.plot(k[~dentro], p.multiplo_ancho[~dentro], "x", label="Outside the band")
    plt.axhline(0.5, color="k", linestyle="--", linewidth=1)
    plt.axhline(-0.5, color="k", linestyle="--", linewidth=1)
    plt.xlabel("Log-moneyness k = ln(K/F)")
    plt.ylabel("Parity residual / bid-ask width of the pair")
    plt.title(f"Put-call parity residuals: {venc}")
    plt.legend()
    rutas["paridad"] = salida / "paridad_30d.png"
    plt.savefig(rutas["paridad"])
    plt.close()
    return rutas


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--fecha", required=True)
    a.add_argument("--datos", default=str(RAIZ / "data"))
    a.add_argument("--config", default=str(RAIZ / "configs" / "captura_alpaca.toml"))
    a.add_argument("--config-piloto", default=str(RAIZ / "configs" / "piloto.toml"))
    a.add_argument("--salida", default=None)
    a.add_argument("--cierre-descriptivo", action="store_true",
                   help="describe capturas inmediatas recibidas con la sesión cerrada (no elegibles para el piloto)")
    args = a.parse_args()
    fecha = _fecha(args.fecha)
    with open(args.config, "rb") as f:
        cfg_imp = tomllib.load(f)["implicito"]
    salida = Path(args.salida) if args.salida else RAIZ / "reports" / "verificacion_alpaca" / str(fecha)
    informe, figura = diagnostico.diagnosticar(Path(args.datos), fecha, cfg_imp, cargar_config(args.config_piloto),
                                               args.cierre_descriptivo)
    if not informe["capturas"]:
        print(f"no hay capturas de {fecha} en {args.datos}", file=sys.stderr)
        return 1
    salida.mkdir(parents=True, exist_ok=True)
    rutas = graficas(figura, salida, f"SPXW {fecha}") if figura else {}
    almacen.escribir_json(informe, salida / "resumen.json")
    escribir_markdown(informe, salida, rutas)
    for c in informe["capturas"]:
        e = c["elegibilidad"]
        print(f"{c['etiqueta']}: {c['estado']}; filas válidas al corte {e['filas_validas_al_corte']} de {e['filas']}"
              + ("; descriptivo del cierre" if c["descriptivo_cierre"] else ""))
    print(f"{salida.relative_to(RAIZ) if salida.is_relative_to(RAIZ) else salida}: "
          f"{len(informe['capturas'])} capturas")
    return 0


def _n(x, factor=1.0, dec=2):
    try:
        return "" if x is None or not np.isfinite(float(x)) else f"{float(x) * factor:.{dec}f}"
    except (TypeError, ValueError):
        return str(x)


def escribir_markdown(informe, salida, rutas):
    lineas = [f"# Verificación de capturas de Alpaca: {informe['fecha']}", "",
              "Generado por `scripts/verificar_alpaca.py` desde el crudo. Solo agregados y medidas derivadas.", ""]
    for c in informe["capturas"]:
        e = c["elegibilidad"]
        lineas += [f"## Captura `{c['etiqueta']}`", ""]
        if c["descriptivo_cierre"]:
            motivo = c["motivo_modo"][:1].upper() + c["motivo_modo"][1:]
            lineas += [f"> **Descriptivo del cierre, no elegible para el piloto.** {motivo}. Las tablas "
                       "siguientes omiten las horas de snapshot y de disponibilidad para describir el feed; con los "
                       f"controles estrictos quedan {e['filas_validas_al_corte']} filas válidas al corte.", ""]
        lineas += [f"- Estado {c['estado']}; modo {c['modo']}, corte {c['corte_utc']}, feed de opciones "
                   f"`{c['feed_opciones']}`, cuenta {c['cuenta']}; desfase del reloj local "
                   f"{_n(c['desfase_reloj_s'], 1, 3)} s.",
                   f"- Elegibilidad al corte (controles estrictos): {e['filas_validas_al_corte']} filas válidas de "
                   f"{e['filas']}; nivel implícito {e['nivel_implicito']}. Modo: {c['motivo_modo']}.",
                   f"- {c['respuestas']} respuestas ({c['bytes'] / 1e6:.1f} MB sin comprimir) "
                   f"en {c['duracion_s']:.2f} s; "
                   f"errores {c['errores']}; respuestas después del corte {c['respuestas_despues_del_corte']}.",
                   f"- Cobertura: {c['cobertura'].get('con_cotizacion', 0)} contratos con cotización de "
                   f"{c['cobertura'].get('snapshots', 0)}; sin cotización {c['cobertura'].get('sin_cotizacion', 0)}; "
                   f"sin metadatos {c['cobertura'].get('sin_metadatos', 0)}."]
        s = c["spot_spx_implicito"]
        lineas.append(f"- SPX implícito: {s.get('estado')}"
                      + (f", {_n(s.get('spot'))} con {s.get('pares')} pares del {s.get('vencimiento')} "
                         f"(error del forward {_n(s.get('forward_error'), 1, 3)})" if s.get("estado") == "identificado"
                         else f" ({s.get('motivo', '')})")
                      + f"; SPY (IEX) {_n(c['spot_spy_iex'])}"
                      + (f"; razón SPX/SPY {_n(c.get('razon_spx_spy'), 1, 4)}." if "razon_spx_spy" in c else "."))
        lineas.append("")
        for raiz, r in c["raices"].items():
            lineas += [f"### {raiz}", "",
                       "| Vencimiento | Días | Válidas/filas | Bid en grilla | Ancho cerca (ticks) "
                       "| Edad mediana (s) | Pares | Fuera de banda | Mediana abs(res)/ancho | Tasa implícita "
                       "| RR25 (pts) |",
                       "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for venc, x in r["vencimientos"].items():
                if "diagnostico" not in x:
                    lineas.append(f"| {venc} | | {x['estado']} | | | | | | | | |")
                    continue
                d = x["diagnostico"]
                rr = _n(x["rr25"]["obs_rr25"], 100) or x["rr25"]["obs_rr25_estado"]
                # A pocos días la pendiente de C - P no identifica el descuento: no se muestra la tasa.
                tasa = f"{_n(d['tasa_implicita'], 100, 2)} %" if x["dias"] >= 7 else "—"
                lineas.append(f"| {venc} | {x['dias']:.1f} | {x['filas_validas']}/{x['filas']} | "
                              f"{_n(d['bid_en_grilla'], 100, 0)} % | {_n(d['ancho_ticks_mediano_cerca'], 1, 1)} | "
                              f"{_n(d['edad_mediana_s'], 1, 0)} | {d['paridad_pares']} | "
                              f"{_n(d['paridad_fuera_de_banda'], 100, 0)} % | "
                              f"{_n(d['paridad_mediana_abs_multiplo'], 1, 2)} | {tasa} | "
                              f"{rr} |")
            ex = r["exclusiones_totales"]
            lineas += ["", "Exclusiones: " + (", ".join(f"{k} {n}" for k, n in sorted(ex.items(), key=lambda t: -t[1]))
                                              or "ninguna") + "."]
            pc = r["plazo_constante_30d"]
            if "rr25" in pc:
                rr, al = pc["rr25"], pc["asim_log"]
                lineas.append(f"A 30 días ({', '.join(pc['vencimientos'])}): RR25 {rr['estado']}"
                              + (f" = {_n(rr['valor'], 100)} puntos, banda [{_n(rr['inferior'], 100)}, "
                                 f"{_n(rr['superior'], 100)}]" if rr["estado"] == "identificada"
                                 else f" ({rr['motivo']})")
                              + f"; asimetría logarítmica {al['estado']}"
                              + (f" = {_n(al['valor'], 100)} puntos." if al["estado"] == "identificada"
                                 else f" ({al['motivo']})."))
            else:
                lineas.append(f"A 30 días: no disponible ({pc['motivo']}).")
            lineas.append("")
    for nombre, ruta in rutas.items():
        lineas += [f"![{nombre}]({Path(ruta).name})", ""]
    (salida / "informe.md").write_text("\n".join(lineas), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
