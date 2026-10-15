"""Calibracion y cobertura (Paso 5).

La calibracion se ajusta en un **tramo cronologico posterior al entrenamiento y
anterior a la validacion**. Nunca con resultados aun desconocidos y nunca con el
mismo tramo que entreno el modelo.

Se empieza con calibracion sigmoide (Platt): un solo parametro de pendiente y
uno de desplazamiento sobre el logit, que es lo bastante rigido para no
memorizar la muestra de calibracion.

Las comprobaciones se agrupan por probabilidad, volatilidad y tiempo restante, y
los tramos con pocas observaciones se agrupan en lugar de reportarse como si
fueran informativos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .modelos import ErrorModelo, _sigmoide, logit


class ErrorCalibracion(ValueError):
    """Calibracion mal planteada."""


@dataclass
class CalibradorSigmoide:
    """Platt scaling: ``p_cal = sigmoide(a * logit(p) + b)``."""

    a: float | None = None
    b: float | None = None
    iteraciones_max: int = 200
    tolerancia: float = 1e-10
    filas_ajuste: int = 0
    convergio: bool = False

    @property
    def ajustado(self) -> bool:
        return self.a is not None and self.b is not None

    def ajustar(
        self, p_crudo: Sequence[float], objetivo: Sequence[int]
    ) -> "CalibradorSigmoide":
        z = logit(np.asarray(p_crudo, dtype=float).ravel())
        y = np.asarray(objetivo, dtype=float).ravel()
        if z.size != y.size:
            raise ErrorCalibracion("longitudes incompatibles")
        if z.size == 0:
            raise ErrorCalibracion("sin observaciones de calibracion")
        if not np.all(np.isin(y, (0.0, 1.0))):
            raise ErrorCalibracion("objetivo no binario")

        diseno = np.column_stack([z, np.ones_like(z)])
        beta = np.array([1.0, 0.0])

        for _ in range(self.iteraciones_max):
            p = _sigmoide(diseno @ beta)
            gradiente = diseno.T @ (p - y)
            pesos = np.clip(p * (1.0 - p), 1e-12, None)
            hessiano = diseno.T @ (diseno * pesos[:, None])
            # Regularizacion minima para que un tramo degenerado no rompa el
            # ajuste; es numerica, no un hiperparametro de modelado.
            hessiano += np.eye(2) * 1e-10
            try:
                paso = np.linalg.solve(hessiano, gradiente)
            except np.linalg.LinAlgError:
                paso = np.linalg.lstsq(hessiano, gradiente, rcond=None)[0]
            beta_nuevo = beta - paso
            if np.max(np.abs(beta_nuevo - beta)) < self.tolerancia:
                beta = beta_nuevo
                self.convergio = True
                break
            beta = beta_nuevo

        self.a, self.b = float(beta[0]), float(beta[1])
        self.filas_ajuste = int(z.size)
        return self

    def calibrar(self, p_crudo: Sequence[float] | float) -> np.ndarray:
        if not self.ajustado:
            raise ErrorCalibracion("calibrador sin ajustar")
        z = logit(np.asarray(p_crudo, dtype=float))
        return _sigmoide(self.a * z + self.b)


# ---------------------------------------------------------------------------
# Metricas de prediccion
# ---------------------------------------------------------------------------


def brier(p: Sequence[float], y: Sequence[int]) -> float:
    pa = np.asarray(p, dtype=float).ravel()
    ya = np.asarray(y, dtype=float).ravel()
    if pa.size != ya.size or pa.size == 0:
        raise ErrorCalibracion("longitudes incompatibles o vacias")
    return float(np.mean((pa - ya) ** 2))


def log_loss(p: Sequence[float], y: Sequence[int], recorte: float = 1e-12) -> float:
    pa = np.clip(np.asarray(p, dtype=float).ravel(), recorte, 1.0 - recorte)
    ya = np.asarray(y, dtype=float).ravel()
    if pa.size != ya.size or pa.size == 0:
        raise ErrorCalibracion("longitudes incompatibles o vacias")
    return float(-np.mean(ya * np.log(pa) + (1.0 - ya) * np.log(1.0 - pa)))


@dataclass(frozen=True)
class TramoFiabilidad:
    """Un tramo de la curva de fiabilidad."""

    inferior: float
    superior: float
    n: int
    p_media: float
    frecuencia: float

    @property
    def desvio(self) -> float:
        return self.frecuencia - self.p_media


def fiabilidad(
    p: Sequence[float],
    y: Sequence[int],
    bordes: Sequence[float] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    minimo_por_tramo: int = 20,
) -> tuple[tuple[TramoFiabilidad, ...], tuple[str, ...]]:
    """Curva de fiabilidad y avisos de tramos con muestra insuficiente.

    Los tramos por debajo de ``minimo_por_tramo`` se reportan como aviso: su
    frecuencia observada no es informativa y no debe presentarse como evidencia
    de calibracion ni de su falta.
    """
    pa = np.asarray(p, dtype=float).ravel()
    ya = np.asarray(y, dtype=float).ravel()
    if pa.size != ya.size:
        raise ErrorCalibracion("longitudes incompatibles")

    tramos: list[TramoFiabilidad] = []
    avisos: list[str] = []
    for inferior, superior in zip(bordes, bordes[1:]):
        if superior >= 1.0:
            seleccion = (pa >= inferior) & (pa <= superior)
        else:
            seleccion = (pa >= inferior) & (pa < superior)
        n = int(seleccion.sum())
        if n == 0:
            continue
        tramo = TramoFiabilidad(
            inferior=float(inferior),
            superior=float(superior),
            n=n,
            p_media=float(pa[seleccion].mean()),
            frecuencia=float(ya[seleccion].mean()),
        )
        tramos.append(tramo)
        if n < minimo_por_tramo:
            avisos.append(
                f"tramo [{inferior:.2f},{superior:.2f}) con n={n} "
                f"(< {minimo_por_tramo}): no informativo"
            )
    return tuple(tramos), tuple(avisos)


def error_calibracion_esperado(
    p: Sequence[float], y: Sequence[int], **kwargs
) -> float:
    """ECE ponderado por tamano de tramo."""
    tramos, _ = fiabilidad(p, y, **kwargs)
    total = sum(t.n for t in tramos)
    if total == 0:
        raise ErrorCalibracion("sin observaciones")
    return float(
        sum(t.n * abs(t.desvio) for t in tramos) / total
    )


@dataclass(frozen=True)
class CoberturaIntervalo:
    """Cobertura empirica y ancho medio de un intervalo de prediccion."""

    nivel_nominal: float
    n: int
    cobertura: float
    ancho_medio: float

    @property
    def desvio(self) -> float:
        return self.cobertura - self.nivel_nominal


def cobertura_intervalos(
    inferiores: Sequence[float],
    superiores: Sequence[float],
    realizados: Sequence[float],
    nivel_nominal: float,
) -> CoberturaIntervalo:
    """Comprueba si los intervalos de ``V_T`` cubren lo que ocurrio."""
    inf = np.asarray(inferiores, dtype=float).ravel()
    sup = np.asarray(superiores, dtype=float).ravel()
    real = np.asarray(realizados, dtype=float).ravel()
    if not (inf.size == sup.size == real.size):
        raise ErrorCalibracion("longitudes incompatibles")
    if inf.size == 0:
        raise ErrorCalibracion("sin observaciones")
    dentro = (real >= inf) & (real <= sup)
    return CoberturaIntervalo(
        nivel_nominal=float(nivel_nominal),
        n=int(inf.size),
        cobertura=float(dentro.mean()),
        ancho_medio=float(np.mean(sup - inf)),
    )


def calibracion_por_grupo(
    p: Sequence[float],
    y: Sequence[int],
    grupo: Sequence,
    minimo_por_grupo: int = 30,
) -> tuple[dict, tuple[str, ...]]:
    """Brier y desvio medio por grupo (volatilidad, tiempo restante, hora...).

    Los grupos con muestra insuficiente se agrupan en ``"agrupado_escaso"`` en
    lugar de reportarse por separado.
    """
    pa = np.asarray(p, dtype=float).ravel()
    ya = np.asarray(y, dtype=float).ravel()
    claves = np.asarray(grupo)
    if not (pa.size == ya.size == claves.size):
        raise ErrorCalibracion("longitudes incompatibles")

    salida: dict[str, dict] = {}
    escasos_p: list[float] = []
    escasos_y: list[float] = []
    avisos: list[str] = []

    for clave in sorted(set(claves.tolist())):
        seleccion = claves == clave
        n = int(seleccion.sum())
        if n < minimo_por_grupo:
            escasos_p.extend(pa[seleccion].tolist())
            escasos_y.extend(ya[seleccion].tolist())
            avisos.append(f"grupo {clave!r} con n={n} agrupado por muestra escasa")
            continue
        salida[str(clave)] = {
            "n": n,
            "brier": brier(pa[seleccion], ya[seleccion]),
            "p_media": float(pa[seleccion].mean()),
            "frecuencia": float(ya[seleccion].mean()),
        }

    if escasos_p:
        salida["agrupado_escaso"] = {
            "n": len(escasos_p),
            "brier": brier(escasos_p, escasos_y),
            "p_media": float(np.mean(escasos_p)),
            "frecuencia": float(np.mean(escasos_y)),
        }
    return salida, tuple(avisos)
