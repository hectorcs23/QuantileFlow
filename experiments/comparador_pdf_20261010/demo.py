"""Comparador y sensibilidad reproducibles; datos y cotizaciones sintéticos, US$0."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from quantileflow.comparador import comparar_con_pdf
from quantileflow.distribucion_pde import resolver_distribucion
from quantileflow.escenarios import ContratoEscenario, Escenario
from quantileflow.opciones import precio_bs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--presupuesto", type=float, default=500, help="capital de operación ficticio, no gasto en datos")
    p.add_argument("--movimiento", type=float, default=.03)
    p.add_argument("--dias", type=float, default=7)
    p.add_argument("--salida", type=Path, default=Path(__file__).parent/"resultados")
    args = p.parse_args()
    out = args.salida
    out.mkdir(parents=True, exist_ok=True)
    spot, sigma, tasa, q = 100., .25, .04, .013
    cs = []
    for dte in (7., 14., 30., 60.):
        for k in (95., 100., 105.):
            for call in (True, False):
                mid = float(precio_bs(spot, k, dte/365, tasa, q, sigma, call))
                cs.append(ContratoEscenario(f"{'C' if call else 'P'}{k:g}-{dte:g}d", k, dte,
                    call, "europeo", sigma, max(0, mid-.04), mid+.04))
    es = [Escenario("objetivo", args.dias, args.movimiento),
          Escenario("sin_movimiento", args.dias, 0),
          Escenario("contrario", args.dias, -.03),
          Escenario("sube_pero_cae_iv", args.dias, args.movimiento, -.05),
          Escenario("llega_tarde", args.dias+7, args.movimiento),
          Escenario("sube_iv", args.dias, args.movimiento, .05)]
    def comparar(escenarios, presupuesto=args.presupuesto, spread=.04, nodos=401, pasos=400):
        return comparar_con_pdf(cs, spot, escenarios, presupuesto, escenarios[0].nombre,
            tasa=tasa, q=q, comision=.65, semispread_salida=spread, nodos=nodos, pasos=pasos,
            fuente_cotizaciones="sintéticas: Black–Scholes ±0.04 por unidad")
    base = comparar(es)
    fino = comparar(es, nodos=801, pasos=1200)
    (out/"entrada.json").write_text(json.dumps(dict(spot=spot, tasa=tasa, q=q,
        presupuesto_operacion_ficticio=args.presupuesto, presupuesto_datos=0,
        contratos=[asdict(c) for c in cs], escenarios=[asdict(e) for e in es]), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (out/"comparacion.json").write_text(json.dumps(base, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    filas = []
    for f in base["contratos"]:
        for nombre, v in f["escenarios"].items():
            filas.append(dict(contrato=f["contrato"], strike=f["strike"], dte=f["dte"],
                cantidad=f["contratos"], capital_reservado=f["capital_reservado"], escenario=nombre,
                **{k:v[k] for k in ("valor_teorico", "precio_salida_asumido", "pnl", "retorno_capital_reservado")}))
    pd.DataFrame(filas).to_csv(out/"pnl_escenarios.csv", index=False)
    elegido = base["rankings"]["ganancia_objetivo"][0] if base["contratos"] else None
    movimientos, shocks = np.array([-.03, 0, .02, .03, .06]), np.array([-.05, -.025, 0, .025, .05])
    malla = []
    for iv in shocks:
        for retorno in movimientos:
            r = comparar([Escenario("objetivo", args.dias, float(retorno), float(iv))])
            orden = r["rankings"]["ganancia_objetivo"]
            mejor = next((f for f in r["contratos"] if orden and f["contrato"] == orden[0]), None)
            fijo = next((f for f in r["contratos"] if f["contrato"] == elegido), None)
            malla.append(dict(retorno=float(retorno), cambio_iv=float(iv),
                mejor_condicional=mejor["contrato"] if mejor and mejor["pnl_objetivo"] > 0 else "efectivo",
                pnl_mejor_incluyendo_caja=max(0, mejor["pnl_objetivo"] if mejor else 0),
                pnl_elegido=fijo["pnl_objetivo"] if fijo else None))
    pd.DataFrame(malla).to_csv(out/"sensibilidad_spot_iv.csv", index=False)
    variaciones = []
    for nombre, valores in (("dias", [1, 3, 7, 14, 21, 30]), ("presupuesto", [100, 250, 500, 750, 1000]),
                           ("semispread_salida", [0, .04, .10, .20, .40])):
        for valor in valores:
            escenarios = es if nombre != "dias" else [Escenario("objetivo", valor, args.movimiento),
                Escenario("sin_movimiento", valor, 0), Escenario("contrario", valor, -.03),
                Escenario("sube_pero_cae_iv", valor, args.movimiento, -.05),
                Escenario("llega_tarde", valor+7, args.movimiento), Escenario("sube_iv", valor, args.movimiento, .05)]
            r = comparar(escenarios, presupuesto=valor if nombre == "presupuesto" else args.presupuesto,
                         spread=valor if nombre == "semispread_salida" else .04)
            orden = r["rankings"]["ganancia_objetivo"]
            variaciones.append(dict(parametro=nombre, valor=valor, candidatos=len(r["contratos"]),
                primero_ganancia=orden[0] if orden else None,
                primero_retorno=r["rankings"]["retorno_objetivo"][0] if orden else None,
                alternativa_robusta=r["alternativa_robusta"]))
    pd.DataFrame(variaciones).to_csv(out/"sensibilidad_plazo_costos_presupuesto.csv", index=False)
    mapa_fino = {f["contrato"]: f for f in fino["contratos"]}
    diferencias = [abs(v["pnl"]-mapa_fino[f["contrato"]]["escenarios"][nombre]["pnl"])
                   for f in base["contratos"] if f["contrato"] in mapa_fino
                   for nombre, v in f["escenarios"].items()]
    fuentes = [Path(__file__), RAIZ/"quantileflow/comparador.py", RAIZ/"quantileflow/escenarios.py",
               RAIZ/"quantileflow/distribucion_pde.py", RAIZ/"quantileflow/pde.py"]
    resumen = dict(cotizaciones="sintéticas, no contratos reales", presupuesto_datos=0,
        candidatos=len(cs), evaluables=len(base["contratos"]), excluidos=base["excluidos"],
        primero_ganancia=elegido, primero_retorno=base["rankings"]["retorno_objetivo"][:1],
        alternativa_robusta=base["alternativa_robusta"],
        sensibilidad_celdas=len(malla), sensibilidad_variaciones=len(variaciones),
        cambios_contrato_mejor=len({f["mejor_condicional"] for f in malla}),
        refinamiento=dict(nodos=801, pasos=1200, max_cambio_pnl=max(diferencias, default=0),
                         mismos_candidatos=set(mapa_fino) == {f["contrato"] for f in base["contratos"]},
                         rankings_iguales=base["rankings"] == fino["rankings"],
                         misma_alternativa_robusta=base["alternativa_robusta"] == fino["alternativa_robusta"]),
        entorno=dict(python=platform.python_version(), numpy=np.__version__),
        sha256_fuentes_lf={f.relative_to(RAIZ).as_posix():hashlib.sha256(f.read_text(encoding="utf-8").encode()).hexdigest() for f in fuentes})
    (out/"verificacion.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    fig, axs = plt.subplots(2, 2, figsize=(12, 9), layout="constrained")
    top = sorted(base["contratos"], key=lambda f: -f["pnl_objetivo"])[:5]
    x = np.arange(len(top))
    axs[0, 0].bar(x-.18, [f["pnl_objetivo"] for f in top], .36, label="Escenario objetivo")
    axs[0, 0].bar(x+.18, [f["pnl_minimo_escenarios"] for f in top], .36, label="Peor escenario de la lista")
    axs[0, 0].axhline(0, color="black", linewidth=.7)
    axs[0, 0].set_xticks(x, [f["contrato"] for f in top], rotation=25)
    axs[0, 0].set(title="Ganancia condicional y fragilidad", ylabel="PnL total, US$ ficticios")
    axs[0, 0].legend(fontsize=8)
    z = np.array([f["pnl_elegido"] if f["pnl_elegido"] is not None else np.nan for f in malla]).reshape(5, 5)
    vmax = max(float(np.nanmax(np.abs(z))), 1) if np.any(np.isfinite(z)) else 1
    im = axs[0, 1].imshow(z, origin="lower", aspect="auto", cmap="RdBu", vmin=-vmax, vmax=vmax)
    axs[0, 1].set_xticks(range(5), [f"{v*100:g}%" for v in movimientos])
    axs[0, 1].set_yticks(range(5), [f"{v*100:+g}" for v in shocks])
    axs[0, 1].set(title=f"PnL manteniendo {elegido}", xlabel="Movimiento del stock", ylabel="Cambio de IV, puntos porcentuales")
    fig.colorbar(im, ax=axs[0, 1], label="US$ ficticios")
    for i in range(5):
        for j in range(5):
            axs[0, 1].text(j, i, f"{z[i, j]:.0f}", ha="center", va="center", fontsize=8,
                          color="white" if abs(z[i, j]) > vmax*.6 else "black")
    xs = np.linspace(70, 135, 400)
    d0 = resolver_distribucion(spot, 30/365, tasa, q, sigma, nodos=801, pasos=800)
    for label, s, t, vol in [("Entrada: S=100, 30d, IV25%", 100, 30, .25),
        ("Solo spot: S=103, 30d, IV25%", 103, 30, .25),
        ("Spot + reloj: S=103, 23d, IV25%", 103, 23, .25),
        ("Spot + reloj + IV: S=103, 23d, IV20%", 103, 23, .20)]:
        d = d0 if s == 100 else resolver_distribucion(s, t/365, tasa, q, vol, nodos=801, pasos=800)
        axs[1, 0].plot(xs, d.evaluar(xs).pdf, label=label)
    axs[1, 0].set(title="Misma fecha final al avanzar 7 días", xlabel="Precio terminal", ylabel="Densidad Q")
    axs[1, 0].legend(fontsize=7)
    axs[1, 1].axis("off")
    texto = ["Mejor contrato por celda (incluye efectivo)", "Filas: cambio IV −5, −2.5, 0, +2.5, +5 puntos", "Columnas: spot −3%, 0%, +2%, +3%, +6%", ""]
    texto += [" | ".join(f["mejor_condicional"] for f in malla[i:i+5]) for i in range(0, 25, 5)]
    texto += ["", f"Robustez con seis escenarios: {base['alternativa_robusta']}",
              "Estos escenarios no tienen probabilidades estimadas.", "IV plana; calls/puts europeos; sin compras ni órdenes."]
    axs[1, 1].text(0, .98, "\n".join(texto), va="top", fontsize=9, linespacing=1.7)
    fig.suptitle(f"QuantileFlow · comparador PDF · capital ficticio USD {args.presupuesto:g} · datos USD 0")
    fig.savefig(out/"comparador_sensibilidad.png", dpi=160)
    plt.close(fig)
    print(json.dumps({k:resumen[k] for k in ("candidatos", "evaluables", "primero_ganancia", "alternativa_robusta", "refinamiento")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
