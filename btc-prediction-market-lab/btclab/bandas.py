"""Bandas de incertidumbre por remuestreo en bloques (Paso 5).

La banda ``[L, U]`` acota la **incertidumbre de estimacion** de ``p_yes``: cuanto
se movería nuestra estimacion si hubiéramos entrenado con otra muestra del mismo
proceso. Se obtiene remuestreando **bloques temporales** y reajustando modelo y
calibrador con datos anteriores a la decision en cada remuestreo. Reajustar es lo
que hace que la banda refleje la incertidumbre del procedimiento completo y no
solo la del ultimo paso.

Advertencias que el modulo hace explicitas:

* La longitud de bloque se elige segun la dependencia observada **en
  entrenamiento**, no ajustandola hasta que la banda guste.
* La dispersion entre modelos o entre simulaciones **no** es automaticamente un
  intervalo de confianza valido. Esa via existe como ``dispersion_entre_modelos``
  y devuelve ``defendible=False``.
* La "probabilidad verdadera" de un evento unico no es observable, asi que la
  cobertura de la banda solo puede comprobarse de forma agregada.
* La banda es aproximada y puede fallar ante cambios de regimen. No implica que
  una operacion individual gane con el nivel nominal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Sequence

import numpy as np

from .probabilidad import BandaProbabilidad


class ErrorBanda(ValueError):
    """Remuestreo mal planteado."""


def longitud_bloque_sugerida(
    serie: Sequence[float], maxima: int | None = None
) -> int:
    """Primer retardo con autocorrelacion por debajo de ``1/e``.

    Es una regla simple y declarada: el bloque debe durar al menos lo que dura la
    dependencia. Se usa sobre el tramo de entrenamiento y queda registrada.
    """
    datos = np.asarray(serie, dtype=float).ravel()
    n = datos.size
    if n < 8:
        return max(1, n // 2)
    tope = maxima if maxima is not None else max(2, n // 4)
    centrada = datos - datos.mean()
    varianza = float(np.dot(centrada, centrada))
    if varianza <= 0:
        return 1
    umbral = float(np.exp(-1.0))
    for retardo in range(1, tope + 1):
        acf = float(np.dot(centrada[:-retardo], centrada[retardo:]) / varianza)
        if abs(acf) < umbral:
            return retardo
    return tope


@dataclass
class BandaBootstrapBloques:
    """Banda por remuestreo de bloques con reajuste completo.

    ``ajustar_y_predecir`` recibe los indices del remuestreo de entrenamiento y
    devuelve la probabilidad para la observacion objetivo. El llamador es
    responsable de que esos indices solo contengan datos anteriores a la
    decision; ``evaluacion.py`` construye esos tramos con purga.
    """

    remuestreos: int = 200
    nivel: float = 0.90
    semilla: int = 20261015
    minimo_bloques: int = 8
    minimo_remuestreos_validos: int = 50

    def estimar(
        self,
        n_entrenamiento: int,
        longitud_bloque: int,
        ajustar_y_predecir: Callable[[np.ndarray], float | None],
        p_central: float,
    ) -> BandaProbabilidad:
        if n_entrenamiento <= 0:
            raise ErrorBanda("entrenamiento vacio")
        if longitud_bloque <= 0:
            raise ErrorBanda("longitud de bloque no positiva")
        if not 0 < self.nivel < 1:
            raise ErrorBanda(f"nivel fuera de (0,1): {self.nivel}")

        bloques_disponibles = n_entrenamiento // longitud_bloque
        generador = np.random.default_rng(self.semilla)
        muestras: list[float] = []

        if bloques_disponibles >= self.minimo_bloques:
            bloques_por_muestra = max(1, bloques_disponibles)
            inicios_posibles = n_entrenamiento - longitud_bloque + 1
            for _ in range(self.remuestreos):
                inicios = generador.integers(
                    0, inicios_posibles, size=bloques_por_muestra
                )
                indices = np.concatenate(
                    [np.arange(i, i + longitud_bloque) for i in inicios]
                )[:n_entrenamiento]
                try:
                    p = ajustar_y_predecir(indices)
                except Exception:  # noqa: BLE001 - un remuestreo degenerado no invalida el resto
                    p = None
                if p is not None and np.isfinite(p):
                    muestras.append(float(np.clip(p, 0.0, 1.0)))

        suficientes = len(muestras) >= self.minimo_remuestreos_validos
        defendible = suficientes and bloques_disponibles >= self.minimo_bloques

        cola = (1.0 - self.nivel) / 2.0
        if muestras:
            inferior = float(np.quantile(muestras, cola))
            superior = float(np.quantile(muestras, 1.0 - cola))
        else:
            inferior, superior = 0.0, 1.0

        # La banda debe contener el valor central; si el remuestreo no lo cubre,
        # se extiende en lugar de devolver una banda que lo excluya, y el hecho
        # queda en los supuestos.
        nota_extension = ""
        if not (inferior <= p_central <= superior):
            nota_extension = (
                "; banda extendida para contener la estimacion central, "
                "lo que indica sesgo del remuestreo"
            )
            inferior = min(inferior, p_central)
            superior = max(superior, p_central)

        supuestos = (
            f"bloques de {longitud_bloque} observaciones; "
            f"{bloques_disponibles} bloques disponibles; "
            f"{len(muestras)} de {self.remuestreos} remuestreos validos; "
            "modelo y calibrador reajustados en cada remuestreo con datos "
            "anteriores a la decision"
            + nota_extension
        )
        if not defendible:
            supuestos += (
                "; INSUFICIENTE: no se alcanzan los minimos de bloques o "
                "remuestreos, la banda no es defendible y el tamano monetario "
                "queda desactivado"
            )

        return BandaProbabilidad(
            inferior=Decimal(str(round(inferior, 6))),
            superior=Decimal(str(round(superior, 6))),
            metodo=f"bootstrap por bloques moviles, nivel nominal {self.nivel}",
            supuestos=supuestos,
            nivel_nominal=Decimal(str(self.nivel)),
            defendible=defendible,
        )


def dispersion_entre_modelos(
    probabilidades: Sequence[float], p_central: float
) -> BandaProbabilidad:
    """Rango entre candidatos, marcado como **no defendible**.

    Se ofrece para poder mirarlo, no para usarlo como banda: la dispersion entre
    modelos mide desacuerdo entre especificaciones, no incertidumbre de muestreo,
    y no tiene cobertura garantizada.
    """
    valores = np.asarray(probabilidades, dtype=float).ravel()
    if valores.size == 0:
        raise ErrorBanda("sin probabilidades")
    inferior = float(min(valores.min(), p_central))
    superior = float(max(valores.max(), p_central))
    return BandaProbabilidad(
        inferior=Decimal(str(round(inferior, 6))),
        superior=Decimal(str(round(superior, 6))),
        metodo="rango entre modelos candidatos",
        supuestos=(
            "NO DEFENDIBLE como intervalo de confianza: mide desacuerdo entre "
            "especificaciones, no incertidumbre de muestreo; sin cobertura "
            "garantizada"
        ),
        defendible=False,
    )


@dataclass(frozen=True)
class CoberturaBanda:
    """Comprobacion agregada de una familia de bandas.

    No comprueba si la banda cubrio la "probabilidad verdadera" de cada evento
    (no observable). Comprueba algo mas debil y si medible: que la frecuencia
    observada caiga dentro de la banda cuando se agrupan observaciones de banda
    parecida. Un desvio sistematico indica que la banda es demasiado estrecha.
    """

    nivel_nominal: float
    grupos: int
    cobertura: float
    ancho_medio: float
    n: int

    @property
    def desvio(self) -> float:
        return self.cobertura - self.nivel_nominal


def cobertura_agregada(
    inferiores: Sequence[float],
    superiores: Sequence[float],
    resultados: Sequence[int],
    nivel_nominal: float,
    grupos: int = 10,
) -> CoberturaBanda:
    """Agrupa por centro de banda y comprueba si la frecuencia cae dentro."""
    inf = np.asarray(inferiores, dtype=float).ravel()
    sup = np.asarray(superiores, dtype=float).ravel()
    y = np.asarray(resultados, dtype=float).ravel()
    if not (inf.size == sup.size == y.size):
        raise ErrorBanda("longitudes incompatibles")
    if inf.size == 0:
        raise ErrorBanda("sin observaciones")

    centros = (inf + sup) / 2.0
    bordes = np.quantile(centros, np.linspace(0.0, 1.0, grupos + 1))
    bordes = np.unique(bordes)
    dentro = 0
    usados = 0
    for inicio, fin in zip(bordes, bordes[1:]):
        if fin >= bordes[-1]:
            seleccion = (centros >= inicio) & (centros <= fin)
        else:
            seleccion = (centros >= inicio) & (centros < fin)
        n = int(seleccion.sum())
        if n == 0:
            continue
        usados += 1
        frecuencia = float(y[seleccion].mean())
        if float(inf[seleccion].mean()) <= frecuencia <= float(sup[seleccion].mean()):
            dentro += 1

    return CoberturaBanda(
        nivel_nominal=float(nivel_nominal),
        grupos=usados,
        cobertura=float(dentro / usados) if usados else 0.0,
        ancho_medio=float(np.mean(sup - inf)),
        n=int(inf.size),
    )
