"""Robustez: la ventaja solo cuenta si sobrevive a lo que no sabemos.

Una ventaja calculada con una vista concreta, una ``Q`` concreta y el mid no es
un resultado: es el mejor caso. Aquí se recalcula la misma estructura bajo
perturbaciones deliberadas y se conserva **la peor**. Las perturbaciones por
omisión son las cuatro que más veces dan la vuelta al signo:

* ejecución adversa (comprar al ask, vender al bid) frente al mid;
* convicción a la mitad: la vista se mezcla con ``Q`` al 50 %, que es lo que
  queda si la opinión acierta solo la mitad de las veces;
* misma dirección pero con la dispersión que cotiza el mercado, **solo si la
  vista es materialmente direccional**: aísla cuánto de la ventaja venía de que
  la vista, al inclinarse, adelgaza por su cuenta la cola izquierda. Para una
  vista sin dirección este escenario degeneraría en la propia ``Q`` y mataría
  cualquier candidata por construcción, así que no se aplica;
* otra estimación de ``Q`` sobre las mismas cotizaciones, cuando se dispone de
  ella (por ejemplo el ajuste convexo frente al SSVI).

Si el signo de la ventaja cambia en alguna, la recomendación depende de un
supuesto y no del dato.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .distribucion import Distribucion
from .estructuras import Estructura
from .precios import ADVERSO, MEDIO, Mercado
from .evaluacion import evaluar
from .vista import mezcla, tilt_momentos


@dataclass(frozen=True)
class Escenario:
    nombre: str
    p: Distribucion
    q: Distribucion
    modo: str


def escenarios_estandar(p: Distribucion, q: Distribucion, F, modo=ADVERSO, q_alternativa=None,
                        direccion_minima=0.1):
    """Perturbaciones por omisión de la vista, de ``Q`` y de la ejecución.

    ``direccion_minima`` es el tamaño, en desviaciones típicas del horizonte,
    que debe tener el rendimiento esperado de la vista para que el escenario
    direccional tenga sentido.
    """
    lista = [Escenario("base", p, q, modo),
             Escenario("ejecución al mid", p, q, MEDIO),
             Escenario("convicción a la mitad", mezcla([p, q], [0.5, 0.5],
                                                       "vista mezclada al 50 % con Q"), q, modo)]
    retorno = p.media / float(F) - 1.0
    umbral = float(direccion_minima) * q.momentos_log(F)["sd_log"]
    if abs(retorno) > umbral:
        try:
            lista.append(Escenario("dirección con la dispersión de Q",
                                   tilt_momentos(q, F, retorno, 1.0), q, modo))
        except ValueError:
            pass
    if q_alternativa is not None:
        lista.append(Escenario("otra estimación de Q", p, q_alternativa, modo))
    return lista


def robustez(estructura: Estructura, mercado: Mercado, escenarios, alfa=0.95):
    """Evalúa la estructura en cada escenario y resume el peor caso."""
    resultados = {}
    for e in escenarios:
        ev = evaluar(estructura, e.p, e.q, mercado, alfa=alfa, modo=e.modo)
        resultados[e.nombre] = ev
    ventajas = {k: v.ventaja for k, v in resultados.items()}
    identificadas = [v for v in resultados.values() if v.identificada]
    if not identificadas:
        return {"evaluaciones": resultados, "ventajas": ventajas,
                "ventaja_peor_caso": float("nan"), "signo_estable": False,
                "escenario_peor": "", "cvar_peor_caso": float("nan")}
    base = resultados.get("base")
    signo = np.sign(base.ventaja) if base is not None and base.identificada else 0.0
    finitas = {k: v for k, v in ventajas.items() if np.isfinite(v)}
    peor = min(finitas, key=finitas.get)
    return {
        "evaluaciones": resultados,
        "ventajas": ventajas,
        "ventaja_peor_caso": float(finitas[peor]),
        "escenario_peor": peor,
        "signo_estable": bool(signo != 0.0 and all(np.sign(v) == signo for v in finitas.values())),
        "cvar_peor_caso": float(max(v.cvar for v in identificadas)),
        "n_escenarios": len(finitas),
    }
