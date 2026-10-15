"""Evaluacion sin informacion futura (Paso 8).

Separacion cronologica en cuatro tramos: entrenamiento, calibracion, validacion
para seleccion y un tramo final **intacto**. Las fechas se fijan antes de ajustar
candidatos y las filas **no** se reparten al azar.

Durante el desarrollo se usa walk-forward: entrenar con pasado, calibrar con el
pasado mas reciente y evaluar el bloque siguiente, **purgando** las observaciones
cuyo periodo de resultado o de disponibilidad invada el tramo siguiente.

Dos reglas de agrupacion que cambian las conclusiones:

* Todas las observaciones de un contrato van al **mismo** grupo.
* Los contratos de un mismo dia estan correlacionados, asi que la incertidumbre
  se estima por dias o bloques mas largos. Miles de ticks no son miles de
  apuestas independientes, y el numero **efectivo** de observaciones se reporta.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Callable, Iterator, Sequence

import numpy as np

from .tiempo import exigir_utc


class ErrorEvaluacion(ValueError):
    """Separacion o evaluacion mal planteada."""


@dataclass(frozen=True)
class Observable:
    """Una observacion evaluable, con sus instantes relevantes.

    ``disponible_en`` es cuando la etiqueta se conocio. Es lo que decide la purga:
    una observacion cuya etiqueta se publica dentro del tramo siguiente no puede
    usarse para entrenar el modelo que se evalua en ese tramo.
    """

    contrato: str
    decision_en: dt.datetime
    disponible_en: dt.datetime
    dia: str = ""

    def __post_init__(self) -> None:
        exigir_utc(self.decision_en, "decision_en")
        exigir_utc(self.disponible_en, "disponible_en")
        if self.disponible_en < self.decision_en:
            raise ErrorEvaluacion(
                f"{self.contrato}: etiqueta disponible antes de la decision"
            )
        if not self.dia:
            object.__setattr__(self, "dia", self.decision_en.date().isoformat())


@dataclass(frozen=True)
class SeparacionCronologica:
    """Cortes fechados de los cuatro tramos.

    ``congelada`` marca que la separacion ya se fijo. El tramo final solo se
    abre una vez; si el resultado falla y la estrategia cambia, hace falta
    evidencia futura nueva y el test anterior pasa a desarrollo.
    """

    fin_entrenamiento: dt.datetime
    fin_calibracion: dt.datetime
    fin_validacion: dt.datetime
    separacion_s: float
    congelada: bool = False
    nota: str = ""

    def __post_init__(self) -> None:
        for campo in ("fin_entrenamiento", "fin_calibracion", "fin_validacion"):
            exigir_utc(getattr(self, campo), campo)
        if not (
            self.fin_entrenamiento < self.fin_calibracion < self.fin_validacion
        ):
            raise ErrorEvaluacion("los cortes no son crecientes")
        if self.separacion_s < 0:
            raise ErrorEvaluacion("separacion negativa")

    def tramo(self, observable: Observable) -> str:
        """Tramo al que pertenece, aplicando la separacion temporal.

        Una observacion cuya etiqueta se publica despues del corte queda
        ``purgada``: pertenece al pasado por su decision pero contamina el futuro
        por su resultado.
        """
        decision = observable.decision_en
        disponible = observable.disponible_en
        margen = dt.timedelta(seconds=self.separacion_s)

        if decision < self.fin_entrenamiento:
            if disponible >= self.fin_entrenamiento - margen:
                return "purgada"
            return "entrenamiento"
        if decision < self.fin_calibracion:
            if disponible >= self.fin_calibracion - margen:
                return "purgada"
            return "calibracion"
        if decision < self.fin_validacion:
            if disponible >= self.fin_validacion - margen:
                return "purgada"
            return "validacion"
        return "final"

    def reparto(self, observables: Sequence[Observable]) -> dict[str, list[Observable]]:
        salida: dict[str, list[Observable]] = {
            "entrenamiento": [],
            "calibracion": [],
            "validacion": [],
            "final": [],
            "purgada": [],
        }
        for observable in observables:
            salida[self.tramo(observable)].append(observable)
        return salida

    def comprobar_sin_solapamiento(
        self, observables: Sequence[Observable]
    ) -> tuple[str, ...]:
        """Comprueba que ningun contrato aparece en dos tramos.

        Si un contrato se parte entre tramos, la evaluacion mide memorizacion de
        ese contrato y no capacidad de prediccion.
        """
        por_contrato: dict[str, set[str]] = {}
        for observable in observables:
            tramo = self.tramo(observable)
            if tramo == "purgada":
                continue
            por_contrato.setdefault(observable.contrato, set()).add(tramo)
        return tuple(
            f"contrato {contrato} aparece en {sorted(tramos)}"
            for contrato, tramos in sorted(por_contrato.items())
            if len(tramos) > 1
        )


@dataclass(frozen=True)
class BloqueWalkForward:
    """Un paso del walk-forward con sus indices."""

    paso: int
    entrenamiento: tuple[int, ...]
    calibracion: tuple[int, ...]
    evaluacion: tuple[int, ...]
    purgados: tuple[int, ...]
    inicio_evaluacion: dt.datetime
    fin_evaluacion: dt.datetime


def walk_forward(
    observables: Sequence[Observable],
    bloque: dt.timedelta,
    separacion_s: float,
    minimo_entrenamiento: int = 200,
    fraccion_calibracion: float = 0.3,
) -> Iterator[BloqueWalkForward]:
    """Genera pasos: entrenar con pasado, calibrar con pasado reciente, evaluar el siguiente bloque.

    La purga se aplica por ``disponible_en``: se descartan del entrenamiento y de
    la calibracion las observaciones cuya etiqueta cae dentro del bloque de
    evaluacion (o a menos de ``separacion_s`` de su inicio).
    """
    if not observables:
        return
    if bloque.total_seconds() <= 0:
        raise ErrorEvaluacion("bloque no positivo")
    if not 0 < fraccion_calibracion < 1:
        raise ErrorEvaluacion("fraccion de calibracion fuera de (0,1)")

    indexados = sorted(enumerate(observables), key=lambda par: par[1].decision_en)
    inicio = indexados[0][1].decision_en
    fin_total = indexados[-1][1].decision_en
    margen = dt.timedelta(seconds=separacion_s)

    paso = 0
    corte = inicio + bloque
    while corte < fin_total:
        fin_bloque = corte + bloque
        pasado = [par for par in indexados if par[1].decision_en < corte]
        if len(pasado) < minimo_entrenamiento:
            corte = fin_bloque
            paso += 1
            continue

        # Purga: la etiqueta no puede invadir el bloque de evaluacion.
        limite_etiqueta = corte - margen
        admisibles = [
            par for par in pasado if par[1].disponible_en < limite_etiqueta
        ]
        purgados = [
            par[0] for par in pasado if par[1].disponible_en >= limite_etiqueta
        ]

        if len(admisibles) < minimo_entrenamiento:
            corte = fin_bloque
            paso += 1
            continue

        n_calibracion = max(1, int(len(admisibles) * fraccion_calibracion))
        entrenamiento = admisibles[:-n_calibracion]
        calibracion = admisibles[-n_calibracion:]
        if not entrenamiento:
            corte = fin_bloque
            paso += 1
            continue

        evaluacion = [
            par[0]
            for par in indexados
            if corte <= par[1].decision_en < fin_bloque
        ]
        if evaluacion:
            yield BloqueWalkForward(
                paso=paso,
                entrenamiento=tuple(par[0] for par in entrenamiento),
                calibracion=tuple(par[0] for par in calibracion),
                evaluacion=tuple(evaluacion),
                purgados=tuple(purgados),
                inicio_evaluacion=corte,
                fin_evaluacion=fin_bloque,
            )
        corte = fin_bloque
        paso += 1


# ---------------------------------------------------------------------------
# Incertidumbre por bloques
# ---------------------------------------------------------------------------


def agregar_por_dia(
    valores: Sequence[float], dias: Sequence[str]
) -> tuple[list[str], np.ndarray]:
    """Suma por dia. Es la unidad de analisis economico del Paso 10."""
    if len(valores) != len(dias):
        raise ErrorEvaluacion("longitudes incompatibles")
    acumulado: dict[str, float] = {}
    for valor, dia in zip(valores, dias):
        acumulado[dia] = acumulado.get(dia, 0.0) + float(valor)
    claves = sorted(acumulado)
    return claves, np.array([acumulado[k] for k in claves], dtype=float)


def observaciones_efectivas(valores: Sequence[float], grupos: Sequence[str]) -> float:
    """Numero efectivo de observaciones dado el agrupamiento.

    Con ``n`` observaciones en ``g`` grupos y correlacion intragrupo ``rho``, el
    tamano efectivo es ``n / (1 + (m - 1) * rho)`` con ``m`` el tamano medio de
    grupo. Es la cifra que hay que reportar en lugar del conteo bruto.
    """
    if len(valores) != len(grupos):
        raise ErrorEvaluacion("longitudes incompatibles")
    n = len(valores)
    if n == 0:
        return 0.0
    datos = np.asarray(valores, dtype=float)
    etiquetas = np.asarray(grupos)
    unicos = np.unique(etiquetas)
    g = unicos.size
    if g <= 1 or g == n:
        return float(n) if g == n else 1.0

    media_global = datos.mean()
    varianza_total = datos.var(ddof=1) if n > 1 else 0.0
    if varianza_total <= 0:
        return 1.0

    medias = np.array([datos[etiquetas == u].mean() for u in unicos])
    tamanos = np.array([int((etiquetas == u).sum()) for u in unicos])
    m = float(tamanos.mean())
    varianza_entre = float(
        np.sum(tamanos * (medias - media_global) ** 2) / max(1, n - 1)
    )
    rho = float(np.clip((varianza_entre / varianza_total - 1.0 / m) / (1.0 - 1.0 / m)
                        if m > 1 else 0.0, 0.0, 1.0))
    return float(n / (1.0 + (m - 1.0) * rho))


def bootstrap_bloques_media(
    valores: Sequence[float],
    longitud_bloque: int = 1,
    remuestreos: int = 2000,
    nivel: float = 0.95,
    semilla: int = 20261015,
) -> dict:
    """Cota inferior unilateral de la media por bootstrap de bloques.

    El Paso 10 exige, para afirmar evidencia de ventaja, que una cota inferior
    unilateral predefinida del beneficio medio neto por dia sea positiva. Esta
    funcion la calcula sobre la serie **diaria**, no sobre operaciones
    individuales.
    """
    datos = np.asarray(valores, dtype=float).ravel()
    n = datos.size
    if n == 0:
        raise ErrorEvaluacion("sin observaciones")
    if longitud_bloque < 1:
        raise ErrorEvaluacion("longitud de bloque menor que 1")
    bloque = min(longitud_bloque, n)
    generador = np.random.default_rng(semilla)
    bloques_por_muestra = int(math.ceil(n / bloque))
    inicios_posibles = n - bloque + 1

    medias = np.empty(remuestreos, dtype=float)
    for i in range(remuestreos):
        inicios = generador.integers(0, inicios_posibles, size=bloques_por_muestra)
        indices = np.concatenate(
            [np.arange(s, s + bloque) for s in inicios]
        )[:n]
        medias[i] = datos[indices].mean()

    return {
        "media": float(datos.mean()),
        "n": int(n),
        "longitud_bloque": int(bloque),
        "remuestreos": int(remuestreos),
        "nivel_unilateral": float(nivel),
        "cota_inferior": float(np.quantile(medias, 1.0 - nivel)),
        "positiva": bool(float(np.quantile(medias, 1.0 - nivel)) > 0.0),
    }


def ajuste_por_seleccion(cota: float, ensayos: int, nivel: float = 0.95) -> dict:
    """Penalizacion simple por numero de candidatos probados (Bonferroni).

    Si se probaron varios candidatos, el nivel efectivo de la cota no es el
    nominal. Esta funcion declara el nivel ajustado para que la seleccion
    multiple no se ignore.
    """
    if ensayos < 1:
        raise ErrorEvaluacion("ensayos menor que 1")
    alfa = 1.0 - nivel
    return {
        "ensayos": int(ensayos),
        "nivel_nominal": float(nivel),
        "alfa_nominal": float(alfa),
        "alfa_ajustado": float(alfa / ensayos),
        "nivel_ajustado": float(1.0 - alfa / ensayos),
        "cota_sin_ajuste": float(cota),
        "nota": (
            "la cota debe recalcularse al nivel ajustado; este objeto solo "
            "declara el ajuste, no lo aplica a la cota ya calculada"
        ),
    }


@dataclass
class MetricasEconomicas:
    """Metricas del Paso 8, incluidos los dias sin operaciones."""

    neto_por_dia: dict[str, float] = field(default_factory=dict)
    operaciones: int = 0
    descartadas: int = 0
    dias_totales: int = 0
    costes: float = 0.0
    contratos: int = 0

    def resumen(self, longitud_bloque: int = 1) -> dict:
        dias = sorted(self.neto_por_dia)
        serie = np.array([self.neto_por_dia[d] for d in dias], dtype=float)
        dias_sin = sum(1 for v in serie if v == 0.0)
        acumulado = np.cumsum(serie) if serie.size else np.array([0.0])
        maximo = np.maximum.accumulate(acumulado)
        drawdown = float((acumulado - maximo).min()) if serie.size else 0.0
        datos = {
            "dias_con_datos": len(dias),
            "dias_sin_operaciones": dias_sin,
            "dias_totales_declarados": self.dias_totales,
            "contratos": self.contratos,
            "operaciones": self.operaciones,
            "descartadas": self.descartadas,
            "cobertura_senales": (
                round(self.operaciones / (self.operaciones + self.descartadas), 4)
                if (self.operaciones + self.descartadas)
                else None
            ),
            "neto_total": float(serie.sum()) if serie.size else 0.0,
            "neto_medio_por_dia": float(serie.mean()) if serie.size else 0.0,
            "peor_dia": float(serie.min()) if serie.size else 0.0,
            "drawdown": drawdown,
            "costes": self.costes,
            "beneficio_medio_por_contrato": (
                round(float(serie.sum()) / self.contratos, 6)
                if self.contratos
                else None
            ),
        }
        if serie.size > 1:
            datos["cota_inferior_diaria"] = bootstrap_bloques_media(
                serie, longitud_bloque=longitud_bloque
            )
        return datos
