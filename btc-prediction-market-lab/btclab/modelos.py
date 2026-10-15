"""Referencias simples y modelos candidatos (Paso 4).

Candidatos, en el orden que la metodologia impone:

1. **Referencia de mercado**: punto medio de YES cuando es coherente, con su
   spread. Es referencia de evaluacion, no una probabilidad verdadera ni un
   precio de ejecucion. La referencia economica incluye **no operar**.
2. **Modelo del subyacente**: simulacion de trayectorias desde la volatilidad
   reciente y retornos historicos condicionados por regimen. Empieza **sin
   drift**; cualquier tendencia exige validacion.
3. **Modelo supervisado simple**: regresion logistica regularizada.

Extension posible: corregir la probabilidad de mercado con
``logit(p) = logit(p_market) + g(features)``, comparandola con usar el mercado
sin corregir.

Detalle que distingue este problema de un binario ordinario: ``V_T`` no es el
precio terminal, es el **promedio de los ultimos 60 segundos**. La simulacion
promedia esa ventana al final de la trayectoria en lugar de tomar el ultimo
punto; tomar el ultimo punto sobreestima la varianza del objetivo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

import numpy as np

from .contrato import Operador, ReglaLiquidacion
from .dinero import MILS_POR_DOLAR
from .libro import Lado, Libro


class ErrorModelo(ValueError):
    """Modelo mal especificado o usado sin ajustar."""


# ---------------------------------------------------------------------------
# 1. Referencia de mercado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferenciaMercado:
    """Punto medio de YES como referencia de evaluacion.

    ``spread_maximo_mils`` define cuando el punto medio deja de ser coherente:
    con un spread ancho el medio no informa de nada y se devuelve ``None`` en
    lugar de un numero que parecera una probabilidad.
    """

    spread_maximo_mils: int = 100

    def probabilidad(self, libro: Libro) -> tuple[float | None, dict]:
        medio = libro.punto_medio_mils(Lado.YES)
        spread = libro.spread_mils(Lado.YES)
        detalle = {
            "punto_medio_mils": None if medio is None else float(medio),
            "spread_mils": spread,
            "es_precio_ejecutable": False,
            "nota": "referencia de evaluacion, no probabilidad verdadera",
        }
        if medio is None or spread is None:
            detalle["motivo"] = "libro incompleto"
            return None, detalle
        if spread > self.spread_maximo_mils:
            detalle["motivo"] = (
                f"spread {spread} mils supera el maximo {self.spread_maximo_mils}"
            )
            return None, detalle
        return float(medio) / MILS_POR_DOLAR, detalle


# ---------------------------------------------------------------------------
# 2. Modelo del subyacente
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoSimulacion:
    """Distribucion simulada de ``V_T``."""

    valores: np.ndarray
    p_yes: float
    trayectorias: int
    con_drift: bool
    fuente_retornos: str

    def cuantiles(self, niveles: Sequence[float] = (0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975)) -> dict[str, float]:
        return {
            f"q{int(round(nivel * 1000)):04d}": float(np.quantile(self.valores, nivel))
            for nivel in niveles
        }

    def intervalo(self, nivel: float) -> tuple[float, float]:
        if not 0 < nivel < 1:
            raise ErrorModelo(f"nivel fuera de (0,1): {nivel}")
        cola = (1.0 - nivel) / 2.0
        return (
            float(np.quantile(self.valores, cola)),
            float(np.quantile(self.valores, 1.0 - cola)),
        )


@dataclass
class ModeloSubyacente:
    """Simulacion de trayectorias y aplicacion de la regla de liquidacion.

    ``retornos_historicos`` son retornos logaritmicos por paso de la **misma**
    duracion que ``paso_s``, tomados solo de datos anteriores a la decision. Si
    se proporcionan, se remuestrean por bloques para conservar colas, saltos y
    agrupamiento de volatilidad; el modelo normal se mantiene como referencia
    comparativa, no como supuesto por omision.
    """

    trayectorias: int = 20000
    paso_s: float = 1.0
    con_drift: bool = False
    bloque_remuestreo: int = 30
    semilla: int = 20261015

    def simular(
        self,
        *,
        spot: float,
        volatilidad_s: float,
        tiempo_restante_s: float,
        ventana_promedio_s: float,
        regla: ReglaLiquidacion,
        retornos_historicos: Sequence[float] | None = None,
    ) -> ResultadoSimulacion:
        if spot <= 0:
            raise ErrorModelo(f"spot no positivo: {spot}")
        if volatilidad_s <= 0:
            raise ErrorModelo(f"volatilidad no positiva: {volatilidad_s}")
        if tiempo_restante_s <= 0:
            raise ErrorModelo(f"tiempo restante no positivo: {tiempo_restante_s}")
        if ventana_promedio_s <= 0:
            raise ErrorModelo("ventana de promedio no positiva")

        pasos = max(1, int(round(tiempo_restante_s / self.paso_s)))
        pasos_promedio = max(1, int(round(ventana_promedio_s / self.paso_s)))
        pasos_promedio = min(pasos_promedio, pasos)

        generador = np.random.default_rng(self.semilla)

        if retornos_historicos is not None and len(retornos_historicos) >= self.bloque_remuestreo:
            incrementos = self._remuestrear_bloques(
                np.asarray(retornos_historicos, dtype=float), pasos, generador
            )
            fuente = f"bloques historicos (bloque={self.bloque_remuestreo})"
        else:
            sigma_paso = volatilidad_s * math.sqrt(self.paso_s)
            incrementos = generador.normal(
                0.0, sigma_paso, size=(self.trayectorias, pasos)
            )
            fuente = "normal (referencia)"

        if not self.con_drift:
            # Sin drift: se centra cada paso para que el remuestreo historico no
            # introduzca una tendencia por la via de la muestra elegida.
            incrementos = incrementos - incrementos.mean(axis=1, keepdims=True)

        log_trayectorias = math.log(spot) + np.cumsum(incrementos, axis=1)
        precios = np.exp(log_trayectorias)

        # V_T es el promedio de la ventana final, no el ultimo punto.
        valores = precios[:, -pasos_promedio:].mean(axis=1)

        p_yes = self._probabilidad(valores, regla)
        return ResultadoSimulacion(
            valores=valores,
            p_yes=p_yes,
            trayectorias=int(self.trayectorias),
            con_drift=self.con_drift,
            fuente_retornos=fuente,
        )

    def _remuestrear_bloques(
        self, retornos: np.ndarray, pasos: int, generador: np.random.Generator
    ) -> np.ndarray:
        """Remuestreo por bloques solapados, conservando dependencia local."""
        bloque = min(self.bloque_remuestreo, len(retornos))
        inicios_posibles = len(retornos) - bloque + 1
        bloques_por_trayectoria = int(math.ceil(pasos / bloque))
        inicios = generador.integers(
            0, inicios_posibles, size=(self.trayectorias, bloques_por_trayectoria)
        )
        indices = inicios[:, :, None] + np.arange(bloque)[None, None, :]
        muestra = retornos[indices].reshape(self.trayectorias, -1)
        return muestra[:, :pasos]

    @staticmethod
    def _probabilidad(valores: np.ndarray, regla: ReglaLiquidacion) -> float:
        if regla.umbral is None:
            raise ErrorModelo("regla sin umbral")
        umbral = float(regla.umbral)
        if regla.operador is Operador.MAYOR:
            aciertos = valores > umbral
        elif regla.operador is Operador.MAYOR_O_IGUAL:
            aciertos = valores >= umbral
        elif regla.operador is Operador.MENOR:
            aciertos = valores < umbral
        elif regla.operador is Operador.MENOR_O_IGUAL:
            aciertos = valores <= umbral
        elif regla.operador is Operador.RANGO_CERRADO:
            if regla.umbral_superior is None:
                raise ErrorModelo("rango sin umbral superior")
            superior = float(regla.umbral_superior)
            aciertos = (valores >= umbral) & (valores <= superior)
        else:
            raise ErrorModelo(f"operador no implementado: {regla.operador}")
        return float(aciertos.mean())


# ---------------------------------------------------------------------------
# 3. Regresion logistica regularizada
# ---------------------------------------------------------------------------


def _sigmoide(z: np.ndarray) -> np.ndarray:
    """Sigmoide estable en los extremos."""
    salida = np.empty_like(z, dtype=float)
    positivos = z >= 0
    salida[positivos] = 1.0 / (1.0 + np.exp(-z[positivos]))
    exponencial = np.exp(z[~positivos])
    salida[~positivos] = exponencial / (1.0 + exponencial)
    return salida


def logit(p: np.ndarray | float, recorte: float = 1e-9) -> np.ndarray:
    """``log(p / (1 - p))`` con recorte para evitar infinitos."""
    valores = np.clip(np.asarray(p, dtype=float), recorte, 1.0 - recorte)
    return np.log(valores / (1.0 - valores))


@dataclass
class LogisticaRegularizada:
    """Logistica con penalizacion L2, ajustada por Newton amortiguado.

    Implementada sobre ``numpy`` porque el entorno auditado no tiene ``scipy`` ni
    ``sklearn``. El termino constante no se penaliza.
    """

    regularizacion: float = 1.0
    iteraciones_max: int = 100
    tolerancia: float = 1e-8
    coeficientes: np.ndarray | None = None
    nombres: tuple[str, ...] = ()
    filas_ajuste: int = 0
    convergio: bool = False

    @property
    def ajustado(self) -> bool:
        return self.coeficientes is not None

    def ajustar(
        self, matriz: np.ndarray, objetivo: np.ndarray,
        nombres: Sequence[str] | None = None,
    ) -> "LogisticaRegularizada":
        X = np.asarray(matriz, dtype=float)
        y = np.asarray(objetivo, dtype=float).ravel()
        if X.ndim != 2:
            raise ErrorModelo("se esperaba una matriz 2-D")
        if X.shape[0] != y.size:
            raise ErrorModelo("filas y etiquetas de distinta longitud")
        if np.isnan(X).any():
            raise ErrorModelo(
                "hay variables faltantes: no se imputan, se excluye la observacion"
            )
        if not np.all(np.isin(y, (0.0, 1.0))):
            raise ErrorModelo("el objetivo debe ser binario 0/1")

        n, k = X.shape
        diseno = np.hstack([np.ones((n, 1)), X])
        beta = np.zeros(k + 1)
        penalizacion = np.full(k + 1, self.regularizacion)
        penalizacion[0] = 0.0

        for _ in range(self.iteraciones_max):
            p = _sigmoide(diseno @ beta)
            gradiente = diseno.T @ (p - y) + penalizacion * beta
            pesos = np.clip(p * (1.0 - p), 1e-12, None)
            hessiano = diseno.T @ (diseno * pesos[:, None]) + np.diag(penalizacion)
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

        self.coeficientes = beta
        self.filas_ajuste = int(n)
        self.nombres = tuple(nombres) if nombres is not None else ()
        return self

    def probabilidad(self, matriz: np.ndarray) -> np.ndarray:
        if not self.ajustado:
            raise ErrorModelo("logistica sin ajustar")
        X = np.asarray(matriz, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if X.shape[1] + 1 != self.coeficientes.size:
            raise ErrorModelo(
                f"se esperaban {self.coeficientes.size - 1} variables, "
                f"hay {X.shape[1]}"
            )
        diseno = np.hstack([np.ones((X.shape[0], 1)), X])
        return _sigmoide(diseno @ self.coeficientes)


# ---------------------------------------------------------------------------
# 4. Correccion del mercado
# ---------------------------------------------------------------------------


@dataclass
class CorreccionLogit:
    """``logit(p) = logit(p_market) + g(features)``.

    ``g`` es lineal y regularizada. El ajuste parte del mercado como base, de
    modo que ``g = 0`` reproduce el mercado exactamente; eso permite comparar
    "corregir" contra "usar el mercado sin corregir" sobre las mismas
    observaciones, que es lo que la metodologia pide.
    """

    regularizacion: float = 1.0
    iteraciones_max: int = 100
    tolerancia: float = 1e-8
    coeficientes: np.ndarray | None = None
    filas_ajuste: int = 0

    @property
    def ajustado(self) -> bool:
        return self.coeficientes is not None

    def ajustar(
        self, matriz: np.ndarray, p_mercado: np.ndarray, objetivo: np.ndarray
    ) -> "CorreccionLogit":
        X = np.asarray(matriz, dtype=float)
        base = logit(np.asarray(p_mercado, dtype=float).ravel())
        y = np.asarray(objetivo, dtype=float).ravel()
        if X.shape[0] != y.size or base.size != y.size:
            raise ErrorModelo("longitudes incompatibles")
        if np.isnan(X).any():
            raise ErrorModelo("variables faltantes en la correccion")

        n, k = X.shape
        diseno = np.hstack([np.ones((n, 1)), X])
        beta = np.zeros(k + 1)
        penalizacion = np.full(k + 1, self.regularizacion)
        penalizacion[0] = 0.0

        for _ in range(self.iteraciones_max):
            p = _sigmoide(base + diseno @ beta)
            gradiente = diseno.T @ (p - y) + penalizacion * beta
            pesos = np.clip(p * (1.0 - p), 1e-12, None)
            hessiano = diseno.T @ (diseno * pesos[:, None]) + np.diag(penalizacion)
            try:
                paso = np.linalg.solve(hessiano, gradiente)
            except np.linalg.LinAlgError:
                paso = np.linalg.lstsq(hessiano, gradiente, rcond=None)[0]
            beta_nuevo = beta - paso
            if np.max(np.abs(beta_nuevo - beta)) < self.tolerancia:
                beta = beta_nuevo
                break
            beta = beta_nuevo

        self.coeficientes = beta
        self.filas_ajuste = int(n)
        return self

    def probabilidad(self, matriz: np.ndarray, p_mercado: np.ndarray) -> np.ndarray:
        if not self.ajustado:
            raise ErrorModelo("correccion sin ajustar")
        X = np.asarray(matriz, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        base = logit(np.asarray(p_mercado, dtype=float).ravel())
        diseno = np.hstack([np.ones((X.shape[0], 1)), X])
        return _sigmoide(base + diseno @ self.coeficientes)
