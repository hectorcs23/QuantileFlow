"""Reglas de decisión: cuándo vender puts, cuándo comprarlos y cuándo no hacer nada.

El orden importa. Primero se comprueba si la pregunta tiene respuesta con los
datos disponibles (puertas globales); después se evalúan las candidatas; solo lo
que sobrevive a todos los filtros se ordena. La abstención es un resultado
legítimo y es el resultado por omisión: sin desacuerdo con ``Q`` no hay nada que
operar, por buena que parezca la estructura.

Las reglas son todas verificables y están en ``configs/estrategias.toml``:

* la ventaja debe superar el coste de ejecución **y** el residuo del ajuste de
  ``Q``, porque operar contra el propio error de modelo no es operar una
  ventaja (zona de no operación);
* debe sobrevivir con el mismo signo a las perturbaciones de ``robustez``;
* la ventaja no puede venir, en su mayor parte, de la zona sin cotizaciones;
* la vista no puede apartarse de ``Q`` más que un máximo de entropía relativa;
* el CVaR no puede pasar del presupuesto de riesgo sobre el capital inmovilizado.

Lo que **no** es un criterio: la probabilidad de ganar. Un put vendido muy fuera
del dinero gana casi siempre y eso ya está en su precio. Se reporta porque se
suele mirar, no porque decida.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass

import numpy as np

from .distribucion import Distribucion
from .evaluacion import Evaluacion, comparar, evaluar
from .precios import Mercado
from .robustez import escenarios_estandar, robustez

VENDER_PUTS, COMPRAR_PUTS, SIN_PUTS = "vender puts", "comprar puts", "sin puts"
OPERAR, ABSTENERSE = "operar", "abstenerse"


@dataclass(frozen=True)
class ConfigEstrategias:
    version: str
    alfa: float
    modo_ejecucion: str
    lambda_riesgo: float
    factor_sobre_coste: float
    ventaja_minima_sobre_capital: float
    kl_max: float
    cvar_max_sobre_capital: float
    fraccion_no_fiable_max: float
    exigir_signo_estable: bool
    permitir_perdida_no_acotada: bool
    distancias: tuple
    anchuras: tuple
    fuente: dict


def config_desde_dict(d: dict) -> ConfigEstrategias:
    r, c, e = d["reglas"], d["catalogo"], d["ejecucion"]
    return ConfigEstrategias(
        version=d["estrategias"]["version"], alfa=float(r["alfa"]),
        modo_ejecucion=str(e["modo"]), lambda_riesgo=float(r["lambda_riesgo"]),
        factor_sobre_coste=float(r["factor_sobre_coste"]),
        ventaja_minima_sobre_capital=float(r["ventaja_minima_sobre_capital"]),
        kl_max=float(r["kl_max"]), cvar_max_sobre_capital=float(r["cvar_max_sobre_capital"]),
        fraccion_no_fiable_max=float(r["fraccion_no_fiable_max"]),
        exigir_signo_estable=bool(r["exigir_signo_estable"]),
        permitir_perdida_no_acotada=bool(r["permitir_perdida_no_acotada"]),
        distancias=tuple(float(x) for x in c["distancias"]),
        anchuras=tuple(float(x) for x in c["anchuras"]), fuente=d)


def cargar_config(ruta) -> ConfigEstrategias:
    with open(ruta, "rb") as f:
        return config_desde_dict(tomllib.load(f))


def papel_en_puts(estructura, q: Distribucion, tol=1e-12):
    """¿La estructura cobra prima de puts, la paga, o no usa puts?

    Se clasifica por la **prima neta** de las patas de put valoradas en ``Q``,
    no por la suma de cantidades: un put spread alcista tiene cantidades que se
    cancelan y sin embargo cobra prima, que es lo que define la posición.
    """
    neta = sum(p.cantidad * q.precio_put(p.strike) for p in estructura.patas if p.tipo == "put")
    if neta < -tol:
        return VENDER_PUTS
    if neta > tol:
        return COMPRAR_PUTS
    return SIN_PUTS


def puertas_globales(diagnostico, mercado: Mercado, cfg: ConfigEstrategias):
    """Comprobaciones que, si fallan, invalidan toda recomendación."""
    motivos = []
    kl = diagnostico["kl_p_sobre_q"]
    if not np.isfinite(kl):
        motivos.append("la vista carga probabilidad donde Q no la tiene: entropía relativa infinita")
    elif kl > cfg.kl_max:
        motivos.append(f"la vista se aparta de Q más de lo admitido (KL {kl:.4f} > {cfg.kl_max:g}): "
                       "la recomendación la produciría la opinión, no el dato")
    if mercado.detalle.get("n_fiables", 2) < 2:
        motivos.append("menos de dos cotizaciones utilizables en el vencimiento")
    return motivos


def motivos_descarte(ev: Evaluacion, rob: dict, cfg: ConfigEstrategias, D=1.0):
    """Por qué una candidata no se recomienda. Lista vacía: es apta."""
    if not ev.identificada:
        return [f"no evaluable: {ev.motivo}"]
    motivos = []
    if not (ev.ventaja > 0.0):
        motivos.append(f"ventaja esperada no positiva ({ev.ventaja:+.4f})")
    umbral = cfg.factor_sobre_coste * (abs(ev.coste_ejecucion) + abs(ev.residuo_ajuste))
    if ev.ventaja <= umbral:
        motivos.append(f"zona de no operación: la ventaja ({ev.ventaja:+.4f}) no supera "
                       f"{cfg.factor_sobre_coste:g} veces el coste de ejecución más el residuo "
                       f"del ajuste ({umbral:.4f} = {abs(ev.coste_ejecucion):.4f} + "
                       f"{abs(ev.residuo_ajuste):.4f})")
    if not np.isfinite(rob["ventaja_peor_caso"]) or rob["ventaja_peor_caso"] <= 0.0:
        motivos.append(f"la ventaja desaparece en el escenario «{rob['escenario_peor']}» "
                       f"({rob['ventaja_peor_caso']:+.4f})")
    if cfg.exigir_signo_estable and not rob["signo_estable"]:
        motivos.append("el signo de la ventaja no es estable entre escenarios")
    fraccion = ev.fraccion_no_fiable
    if np.isfinite(fraccion) and fraccion > cfg.fraccion_no_fiable_max:
        motivos.append(f"el {fraccion:.0%} de la ventaja procede de la zona sin cotizaciones "
                       f"utilizables (máximo {cfg.fraccion_no_fiable_max:.0%})")
    if not cfg.permitir_perdida_no_acotada and ev.estructura.perdida_no_acotada:
        motivos.append("pérdida no acotada por arriba")
    if np.isfinite(ev.capital) and ev.capital > 0.0:
        if ev.rendimiento_sobre_capital < cfg.ventaja_minima_sobre_capital:
            motivos.append(f"rendimiento esperado sobre capital {ev.rendimiento_sobre_capital:.3%} "
                           f"por debajo de {cfg.ventaja_minima_sobre_capital:.3%}")
        if D * ev.cvar > cfg.cvar_max_sobre_capital * ev.capital:
            motivos.append(f"CVaR {D * ev.cvar:.4f} en valor presente, por encima del presupuesto "
                           f"({cfg.cvar_max_sobre_capital:g} del capital, {ev.capital:.2f})")
    else:
        motivos.append("capital inmovilizado no acotado: hace falta un margen declarado")
    return motivos


def puntuacion(ev: Evaluacion, rob: dict, D, cfg: ConfigEstrategias):
    """Ventaja de peor caso penalizada por CVaR, por unidad de capital.

    Misma forma que el objetivo de ``quantileflow.decision.optimizar_cvar``
    (``-mu + lambda * CVaR``), normalizada por el capital para comparar
    estructuras de tamaño distinto.
    """
    if not ev.identificada or not np.isfinite(ev.capital) or ev.capital <= 0.0:
        return float("-inf")
    return float((rob["ventaja_peor_caso"] - cfg.lambda_riesgo * D * rob["cvar_peor_caso"])
                 / ev.capital)


def recomendar(candidatas, p: Distribucion, q: Distribucion, mercado: Mercado,
               cfg: ConfigEstrategias, q_alternativa=None):
    """Evalúa el catálogo entero con la misma vara y devuelve el dictamen."""
    diagnostico = comparar(p, q, mercado.F, mercado.D)
    globales = puertas_globales(diagnostico, mercado, cfg)
    escenarios = escenarios_estandar(p, q, mercado.F, cfg.modo_ejecucion, q_alternativa)
    filas = []
    for estructura in candidatas:
        ev = evaluar(estructura, p, q, mercado, cfg.alfa, cfg.modo_ejecucion)
        rob = robustez(estructura, mercado, escenarios, cfg.alfa)
        motivos = motivos_descarte(ev, rob, cfg, mercado.D)
        filas.append({"estructura": estructura, "papel": papel_en_puts(estructura, q),
                      "evaluacion": ev, "robustez": rob, "motivos": motivos,
                      "apta": not motivos and not globales,
                      "puntuacion": puntuacion(ev, rob, mercado.D, cfg)})
    filas.sort(key=lambda f: (f["apta"], f["puntuacion"]), reverse=True)
    aptas = [f for f in filas if f["apta"]]
    return {"diagnostico": diagnostico, "motivos_globales": globales, "filas": filas,
            "aptas": aptas, "escenarios": [e.nombre for e in escenarios],
            "dictamen": dictamen(aptas, filas, globales), "config": cfg}


def _mejor(filas, papel):
    """La mejor candidata de ese papel, prefiriendo las aptas (mismo orden que la tabla)."""
    candidatas = [f for f in filas if f["papel"] == papel and f["evaluacion"].identificada]
    return max(candidatas, key=lambda f: (f["apta"], f["puntuacion"]), default=None)


def dictamen(aptas, filas, globales):
    """Respuesta de una línea, más la comparación entre vender y comprar puts."""
    mejor_venta, mejor_compra = _mejor(filas, VENDER_PUTS), _mejor(filas, COMPRAR_PUTS)
    mejor_sin = _mejor(filas, SIN_PUTS)
    base = {"mejor_venta_puts": mejor_venta, "mejor_compra_puts": mejor_compra,
            "mejor_sin_puts": mejor_sin}
    if globales:
        return {"accion": ABSTENERSE, "estructura": None,
                "texto": "Abstenerse: " + "; ".join(globales), **base}
    if not aptas:
        n = sum(1 for f in filas if f["evaluacion"].identificada)
        return {"accion": ABSTENERSE, "estructura": None,
                "texto": f"Abstenerse: ninguna de las {n} candidatas evaluables pasa los filtros.",
                **base}
    elegida = aptas[0]
    ev = elegida["evaluacion"]
    texto = (f"{elegida['papel'].capitalize()}: {elegida['estructura'].nombre}. "
             f"Ventaja esperada {ev.ventaja:+.4f} por unidad "
             f"({ev.rendimiento_sobre_capital:+.2%} sobre un capital de {ev.capital:.2f}); "
             f"en el peor escenario, {elegida['robustez']['ventaja_peor_caso']:+.4f}.")
    return {"accion": OPERAR, "estructura": elegida, "texto": texto, **base}
