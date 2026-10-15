"""Variables explicativas y escalado (Paso 4).

Las ventanas y periodos son **hiperparametros documentados**, no numeros
elegidos despues de ver el resultado. Estan reunidos en ``VentanasVariables``
para que el diff los muestre cuando cambien.

Todos los escaladores se ajustan **exclusivamente con entrenamiento**. El
``Escalador`` falla si se usa sin ajustar y recuerda con cuantas filas se ajusto,
de modo que aplicar el escalador del conjunto completo sea un error visible y no
una fuga silenciosa.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


class ErrorVariables(ValueError):
    """Variables no calculables con la informacion disponible."""


@dataclass(frozen=True)
class VentanasVariables:
    """Hiperparametros de las ventanas, en segundos."""

    volatilidad_s: tuple[int, ...] = (60, 300, 900)
    retornos_s: tuple[int, ...] = (10, 30, 60, 300)
    #: Anualizacion no se aplica: la volatilidad se deja por segundo para que la
    #: normalizacion por raiz del tiempo restante sea directa.
    minimo_observaciones: int = 5


#: Orden canonico de las variables. El modelo exige este orden exacto para que
#: una columna no se desplace silenciosamente entre entrenamiento y evaluacion.
NOMBRES_VARIABLES: tuple[str, ...] = (
    "distancia_normalizada",
    "log_distancia",
    "tiempo_restante_s",
    "raiz_tiempo_restante",
    "vol_60",
    "vol_300",
    "vol_900",
    "ret_10",
    "ret_30",
    "ret_60",
    "ret_300",
    "spread_yes_mils",
    "profundidad_yes",
    "profundidad_no",
    "imbalance",
    "brecha_spot_indice",
    "hora_sin",
    "hora_cos",
    "dia_semana",
)


def volatilidad_realizada(
    precios: Sequence[float], marcas_s: Sequence[float], ventana_s: float,
    minimo: int = 5,
) -> float | None:
    """Desviacion de los retornos logaritmicos por segundo en la ventana.

    Devuelve ``None`` si no hay observaciones suficientes, en lugar de un cero
    que el modelo interpretaria como "mercado en calma".
    """
    if len(precios) != len(marcas_s):
        raise ErrorVariables("precios y marcas de distinta longitud")
    if len(precios) < 2:
        return None
    fin = marcas_s[-1]
    seleccion = [
        (t, p) for t, p in zip(marcas_s, precios) if fin - t <= ventana_s and p > 0
    ]
    if len(seleccion) < minimo:
        return None
    valores = np.array([p for _, p in seleccion], dtype=float)
    tiempos = np.array([t for t, _ in seleccion], dtype=float)
    retornos = np.diff(np.log(valores))
    deltas = np.diff(tiempos)
    validos = deltas > 0
    if validos.sum() < minimo - 1:
        return None
    # Varianza por segundo: suma de retornos al cuadrado sobre tiempo total.
    total = float(deltas[validos].sum())
    if total <= 0:
        return None
    return float(np.sqrt(np.square(retornos[validos]).sum() / total))


def retorno(precios: Sequence[float], marcas_s: Sequence[float], ventana_s: float) -> float | None:
    """Retorno logaritmico sobre la ventana, o ``None`` si no hay base."""
    if not precios:
        return None
    fin = marcas_s[-1]
    base = None
    for t, p in zip(marcas_s, precios):
        if fin - t <= ventana_s and p > 0:
            base = p
            break
    if base is None or precios[-1] <= 0:
        return None
    return float(math.log(precios[-1] / base))


def distancia_normalizada(
    spot: float, umbral: float, volatilidad_s: float | None, tiempo_restante_s: float
) -> float | None:
    """``log(S/K) / (sigma * sqrt(tau))``.

    Es la variable central: mide a cuantas desviaciones esta el umbral dado el
    tiempo que queda. Sin volatilidad o sin tiempo no es calculable y se devuelve
    ``None``; forzar un cero afirmaria que el umbral esta justo en el dinero.
    """
    if spot <= 0 or umbral <= 0:
        return None
    if volatilidad_s is None or volatilidad_s <= 0:
        return None
    if tiempo_restante_s <= 0:
        return None
    return float(math.log(spot / umbral) / (volatilidad_s * math.sqrt(tiempo_restante_s)))


def motivos_fuera_de_dominio(
    *,
    ventana_observada_s: float,
    tiempo_restante_s: float,
    factor_maximo: float = 3.0,
    observaciones: int = 0,
    observaciones_minimas: int = 30,
) -> tuple[str, ...]:
    """Comprueba que el horizonte no exija extrapolar mas alla de lo observado.

    Estimar la volatilidad con una ventana mucho mas corta que el horizonte es
    el error que produce probabilidades extremas: la raiz del tiempo escala la
    desviacion, pero no captura los saltos ni los cambios de regimen que ocurren
    en el horizonte y no en la ventana. Si el horizonte supera
    ``factor_maximo`` veces la ventana observada, la observacion esta fuera del
    dominio validado y la decision es no operar.
    """
    motivos: list[str] = []
    if ventana_observada_s <= 0:
        motivos.append("sin ventana de observacion")
    elif tiempo_restante_s > factor_maximo * ventana_observada_s:
        motivos.append(
            f"horizonte {tiempo_restante_s:.0f}s excede {factor_maximo:g}x la "
            f"ventana observada ({ventana_observada_s:.0f}s): extrapolacion "
            "fuera del dominio validado"
        )
    if observaciones < observaciones_minimas:
        motivos.append(
            f"solo {observaciones} observaciones de subyacente "
            f"(< {observaciones_minimas})"
        )
    return tuple(motivos)


@dataclass
class Escalador:
    """Normalizacion ajustada solo con entrenamiento.

    Guarda media y desviacion por columna y rechaza transformar antes de
    ajustar. ``filas_ajuste`` queda registrado para poder citarlo en el informe.
    """

    medias: np.ndarray | None = None
    desviaciones: np.ndarray | None = None
    filas_ajuste: int = 0
    nombres: tuple[str, ...] = NOMBRES_VARIABLES

    @property
    def ajustado(self) -> bool:
        return self.medias is not None and self.desviaciones is not None

    def ajustar(self, matriz: np.ndarray) -> "Escalador":
        datos = np.asarray(matriz, dtype=float)
        if datos.ndim != 2:
            raise ErrorVariables("se esperaba una matriz 2-D")
        if datos.shape[1] != len(self.nombres):
            raise ErrorVariables(
                f"se esperaban {len(self.nombres)} columnas, hay {datos.shape[1]}"
            )
        self.medias = np.nanmean(datos, axis=0)
        desviaciones = np.nanstd(datos, axis=0)
        # Una columna constante en entrenamiento se deja sin escalar en lugar de
        # dividir por cero.
        desviaciones[desviaciones <= 0] = 1.0
        self.desviaciones = desviaciones
        self.filas_ajuste = int(datos.shape[0])
        return self

    def transformar(self, matriz: np.ndarray) -> np.ndarray:
        if not self.ajustado:
            raise ErrorVariables(
                "escalador sin ajustar: ajustelo solo con el tramo de entrenamiento"
            )
        datos = np.asarray(matriz, dtype=float)
        if datos.shape[1] != len(self.nombres):
            raise ErrorVariables(
                f"se esperaban {len(self.nombres)} columnas, hay {datos.shape[1]}"
            )
        return (datos - self.medias) / self.desviaciones


@dataclass(frozen=True)
class VectorVariables:
    """Un vector de variables, con constancia de lo que no se pudo calcular.

    ``faltantes`` no se rellena con ceros. Si una variable exigida por el modelo
    falta, la observacion queda fuera del dominio validado y la decision es no
    operar; eso es preferible a imputar un valor que el modelo leera como
    informacion.
    """

    valores: dict[str, float]
    faltantes: tuple[str, ...]
    momento: dt.datetime
    contrato: str

    def como_fila(self, nombres: Sequence[str] = NOMBRES_VARIABLES) -> np.ndarray:
        return np.array(
            [self.valores.get(nombre, np.nan) for nombre in nombres], dtype=float
        )

    @property
    def completo(self) -> bool:
        return not self.faltantes


@dataclass
class ConstructorVariables:
    """Arma el vector de variables desde el estado disponible en un momento.

    Recibe solo informacion ya recibida (la union as-of la garantiza). No accede
    al almacen por si mismo, para que no exista forma de que mire hacia adelante.
    """

    ventanas: VentanasVariables = field(default_factory=VentanasVariables)
    #: Variables sin las que no se decide. El resto puede faltar y se anota.
    exigidas: tuple[str, ...] = (
        "distancia_normalizada",
        "tiempo_restante_s",
        "spread_yes_mils",
    )

    def construir(
        self,
        *,
        contrato: str,
        momento: dt.datetime,
        umbral: float,
        tiempo_restante_s: float,
        precios_spot: Sequence[float],
        marcas_spot_s: Sequence[float],
        spread_yes_mils: int | None,
        profundidad_yes: float | None,
        profundidad_no: float | None,
        imbalance: float | None,
        indice_referencia: float | None = None,
    ) -> VectorVariables:
        valores: dict[str, float] = {}
        faltantes: list[str] = []

        spot = precios_spot[-1] if precios_spot else None

        vols: dict[int, float | None] = {}
        for ventana in self.ventanas.volatilidad_s:
            vols[ventana] = volatilidad_realizada(
                precios_spot, marcas_spot_s, float(ventana),
                self.ventanas.minimo_observaciones,
            )
            clave = f"vol_{ventana}"
            if vols[ventana] is None:
                faltantes.append(clave)
            else:
                valores[clave] = vols[ventana]

        for ventana in self.ventanas.retornos_s:
            valor = retorno(precios_spot, marcas_spot_s, float(ventana))
            clave = f"ret_{ventana}"
            if valor is None:
                faltantes.append(clave)
            else:
                valores[clave] = valor

        # La volatilidad de referencia para normalizar es la ventana mas corta
        # disponible: es la que mejor describe el regimen del horizonte corto.
        vol_referencia = next(
            (vols[v] for v in self.ventanas.volatilidad_s if vols.get(v)), None
        )

        if spot is not None and umbral > 0 and spot > 0:
            valores["log_distancia"] = float(math.log(spot / umbral))
        else:
            faltantes.append("log_distancia")

        normalizada = (
            distancia_normalizada(spot, umbral, vol_referencia, tiempo_restante_s)
            if spot is not None
            else None
        )
        if normalizada is None:
            faltantes.append("distancia_normalizada")
        else:
            valores["distancia_normalizada"] = normalizada

        if tiempo_restante_s > 0:
            valores["tiempo_restante_s"] = float(tiempo_restante_s)
            valores["raiz_tiempo_restante"] = float(math.sqrt(tiempo_restante_s))
        else:
            faltantes.extend(["tiempo_restante_s", "raiz_tiempo_restante"])

        if spread_yes_mils is None:
            faltantes.append("spread_yes_mils")
        else:
            valores["spread_yes_mils"] = float(spread_yes_mils)

        for clave, valor in (
            ("profundidad_yes", profundidad_yes),
            ("profundidad_no", profundidad_no),
            ("imbalance", imbalance),
        ):
            if valor is None:
                faltantes.append(clave)
            else:
                valores[clave] = float(valor)

        # Brecha spot-indice: solo si tenemos una lectura del indice. Es la
        # variable que mide el riesgo de usar un sustituto del BRTI.
        if indice_referencia is not None and spot is not None and indice_referencia > 0:
            valores["brecha_spot_indice"] = float(
                math.log(spot / indice_referencia)
            )
        else:
            faltantes.append("brecha_spot_indice")

        instante = momento.astimezone(dt.timezone.utc)
        segundos_dia = (
            instante.hour * 3600 + instante.minute * 60 + instante.second
        )
        angulo = 2.0 * math.pi * segundos_dia / 86400.0
        valores["hora_sin"] = math.sin(angulo)
        valores["hora_cos"] = math.cos(angulo)
        valores["dia_semana"] = float(instante.weekday())

        exigidas_faltantes = tuple(
            nombre for nombre in self.exigidas if nombre not in valores
        )

        return VectorVariables(
            valores=valores,
            faltantes=exigidas_faltantes,
            momento=instante,
            contrato=contrato,
        )
