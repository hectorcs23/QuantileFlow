"""Comparación de posiciones con USD 300; ejemplos enteramente sintéticos."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from quantileflow.escenarios import ContratoEscenario, Escenario
from quantileflow.opciones import precio_bs
from quantileflow.posiciones import comparar_posiciones


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, default=Path(__file__).parent / "resultados")
    args = parser.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)
    presupuesto = 300
    cs = [ContratoEscenario("Call K108, prima USD 100", 108, 30, True, "europeo", .25, 1., 1.),
          ContratoEscenario("Call K105, prima USD 300", 105, 30, True, "europeo", .25, 3., 3.)]
    es = [Escenario("objetivo", 30, .10), Escenario("menor_subida", 30, .07)]
    sin_costos = comparar_posiciones(cs, 100, es, presupuesto, "objetivo",
        comision=0, semispread_salida=0, nodos=401, pasos=400,
        fuente_cotizaciones="primas inventadas para ilustrar contabilidad, no calibradas")
    con_costos = comparar_posiciones(cs, 100, es, presupuesto, "objetivo",
        comision=.65, semispread_salida=0, nodos=401, pasos=400,
        fuente_cotizaciones="mismo ejemplo con comisión USD 0.65 por contrato y lado")

    # Segundo ejemplo: entradas consistentes con un modelo sintético, salida
    # antes del vencimiento. Cada candidato mantiene su cantidad en los controles.
    contratos = []
    for dte in (14, 30, 60):
        for k in (100, 103, 105, 108):
            mid = float(precio_bs(100, k, dte / 365, .04, .013, .25, True))
            contratos.append(ContratoEscenario(f"C{k}-{dte}d", k, dte, True,
                "europeo", .25, max(0, mid - .04), mid + .04))
    escenarios = [Escenario("objetivo", 7, .03), Escenario("sin_subida", 7, 0),
                  Escenario("baja", 7, -.03), Escenario("cae_iv", 7, .03, -.05),
                  Escenario("llega_tarde", 14, .03)]
    kw = dict(comision=.65, semispread_salida=.04, tasa=.04, q=.013,
              fuente_cotizaciones="Black–Scholes sintético +/- 0.04; ninguna cotización real")
    modelado = comparar_posiciones(contratos, 100, escenarios, presupuesto, "objetivo",
                                  nodos=801, pasos=1200, **kw)
    control = comparar_posiciones(contratos, 100, escenarios, presupuesto, "objetivo",
                                 nodos=401, pasos=400, **kw)
    mapa = {f["contrato"]: f for f in control["posiciones"]}
    cambios = [abs(v["pnl_posicion"] - mapa[f["contrato"]]["escenarios"][nombre]["pnl_posicion"])
               for f in modelado["posiciones"] for nombre, v in f["escenarios"].items()]
    resultado = dict(presupuesto_operacion_ficticio=presupuesto, presupuesto_datos=0,
        ejemplo_contable_sin_costos=sin_costos, ejemplo_contable_con_costos=con_costos,
        escenario_antes_de_vencer=modelado,
        entrada=dict(spot=100, contratos=[asdict(c) for c in contratos],
                     escenarios=[asdict(e) for e in escenarios], **kw),
        refinamiento=dict(max_cambio_pnl=max(cambios),
            mismo_primero=modelado["rankings"]["ganancia_objetivo"][:1] == control["rankings"]["ganancia_objetivo"][:1],
            mismos_rankings=modelado["rankings"] == control["rankings"],
            mismos_candidatos=set(mapa) == {f["contrato"] for f in modelado["posiciones"]}))
    fuentes = [Path(__file__), RAIZ / "quantileflow/posiciones.py", RAIZ / "quantileflow/comparador.py",
               RAIZ / "quantileflow/escenarios.py", RAIZ / "quantileflow/distribucion_pde.py", RAIZ / "quantileflow/pde.py"]
    resultado["sha256_fuentes_lf"] = {p.relative_to(RAIZ).as_posix():
        hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in fuentes}
    (args.salida / "comparacion.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    ejemplos = sin_costos["posiciones"]
    for offset, nombre, etiqueta, color in [(-.18, "objetivo", "Sube 10% en 30 días", "#236a9f"),
                                           (.18, "menor_subida", "Sube solo 7%", "#c26643")]:
        values = [f["escenarios"][nombre]["pnl_posicion"] for f in ejemplos]
        bars = axes[0].bar(np.arange(len(ejemplos)) + offset, values, .36, label=etiqueta, color=color)
        axes[0].bar_label(bars, fmt="$%.0f", padding=4)
    axes[0].set_xticks(range(2), [f"{f['cantidad']} x USD {f['prima_por_contrato']:.0f}" for f in ejemplos])
    axes[0].set(title="3 baratos vs 1 caro: ejemplo sin comisiones", ylabel="Ganancia / pérdida de toda la posición (USD)", ylim=(-380, 410))
    axes[0].legend(fontsize=8)
    top = modelado["posiciones"][:4]
    x = np.arange(len(top))
    for offset, values, etiqueta, color in [(-.18, [f["escenarios"]["objetivo"]["pnl_posicion"] for f in top], "+3% en 7 días", "#236a9f"),
        (.18, [f["pnl_minimo_escenarios"] for f in top], "Peor de 5 escenarios", "#c26643")]:
        bars = axes[1].bar(x + offset, values, .36, label=etiqueta, color=color)
        axes[1].bar_label(bars, fmt="$%.0f", padding=4)
    axes[1].set_xticks(x, [f"{f['contrato']}\n{f['cantidad']} {'contrato' if f['cantidad'] == 1 else 'contratos'}\n${f['efectivo_libre']:.2f} libres" for f in top], fontsize=8)
    axes[1].set(title="Mismo presupuesto, distintos strikes y DTE", ylabel="PnL neto de comisiones y spread (USD)")
    axes[1].margins(y=.22)
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.axhline(0, color="#333333", lw=.8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("QuantileFlow | Presupuesto USD 300 | Resultados hipotéticos, no pronóstico", fontsize=13)
    fig.savefig(args.salida / "comparacion_presupuesto.png", dpi=160)
    plt.close(fig)
    print(json.dumps(dict(top=[dict(contrato=f["contrato"], cantidad=f["cantidad"],
        capital_reservado=f["capital_reservado"], efectivo_libre=f["efectivo_libre"],
        objetivo=f["escenarios"]["objetivo"], peor=f["pnl_minimo_escenarios"]) for f in top],
        refinamiento=resultado["refinamiento"], robustez=modelado["alternativa_robusta"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
