"""De la ventaja al presupuesto de perdida (Paso 7).

Con coste unitario constante ``0 < c < 1``, pago $1/$0 y probabilidad
conservadora ``p``, Kelly completo asigna como fraccion del capital comprometido:

    f_full = max(0, (p - c) / (1 - c))
    f_candidate = alpha * f_full

``alpha = 0.25`` es un punto de partida de **simulacion**, no una recomendacion.
Esa aproximacion deja de valer cuando el coste cambia con la cantidad, que es el
caso real: el libro tiene profundidad finita y la comision cuadratica depende del
precio de cada nivel. Para eso existe la busqueda discreta sobre cantidades, que
maximiza

    G(n) = p * log((B - C(n) + n) / B) + (1 - p) * log((B - C(n)) / B)

incluyendo ``n = 0``, exigiendo patrimonio positivo en ambos resultados y
recalculando los costes exactos en cada candidato.

La formula aislada supone que no hay exposicion previa relacionada. Si existen
posiciones correlacionadas, hace falta evaluacion conjunta por escenarios; el MVP
reduce el problema con una sola posicion abierta.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from .costes import EvaluacionCoste, ModeloComisionCuadratica, evaluar
from .libro import Lado, Libro
from .limites import EstadoRiesgo, LimitesRiesgo, Restriccion, restricciones_vigentes


class ErrorSizing(ValueError):
    """Parametros de dimensionamiento incoherentes."""


def kelly_completo(p: Decimal, c: Decimal) -> Decimal:
    """``max(0, (p - c) / (1 - c))`` para coste unitario constante."""
    if not 0 <= p <= 1:
        raise ErrorSizing(f"p fuera de [0,1]: {p}")
    if not 0 < c < 1:
        raise ErrorSizing(f"coste unitario fuera de (0,1): {c}")
    bruto = (p - c) / (1 - c)
    return bruto if bruto > 0 else Decimal("0")


def kelly_fraccionado(p: Decimal, c: Decimal, alpha: Decimal) -> Decimal:
    if not 0 < alpha <= 1:
        raise ErrorSizing(f"alpha fuera de (0,1]: {alpha}")
    return alpha * kelly_completo(p, c)


def crecimiento_log(
    cantidad: Decimal, coste_total: Decimal, p: Decimal, capital: Decimal
) -> float | None:
    """``G(n)`` para una cantidad concreta.

    Devuelve ``None`` si algun resultado deja patrimonio no positivo: ese
    candidato es inadmisible, no un valor muy negativo.
    """
    if capital <= 0:
        return None
    patrimonio_gana = capital - coste_total + cantidad
    patrimonio_pierde = capital - coste_total
    if patrimonio_gana <= 0 or patrimonio_pierde <= 0:
        return None
    pf = float(p)
    return pf * math.log(float(patrimonio_gana / capital)) + (1.0 - pf) * math.log(
        float(patrimonio_pierde / capital)
    )


@dataclass(frozen=True)
class CandidatoTamano:
    """Una cantidad evaluada con sus costes exactos."""

    cantidad: Decimal
    evaluacion: EvaluacionCoste | None
    crecimiento: float | None
    admisible: bool
    motivo: str = ""

    @property
    def coste_total(self) -> Decimal:
        return Decimal("0") if self.evaluacion is None else self.evaluacion.coste_total


@dataclass(frozen=True)
class PropuestaTamano:
    """Resultado del dimensionamiento.

    ``simulated_amount`` y ``suggested_live_amount`` estan separados a proposito:
    antes de la validacion el segundo es cero, y el registro debe poder
    distinguirlos sin interpretacion.
    """

    lado: Lado
    cantidad_simulada: Decimal
    simulated_amount: Decimal
    suggested_live_amount: Decimal
    perdida_maxima_simulada: Decimal
    p_usada: Decimal
    es_ficticio: bool
    cantidad_optima_sin_reduccion: Decimal
    crecimiento_en_propuesta: float | None
    restricciones_activas: tuple[str, ...]
    motivos_no_operar: tuple[str, ...]
    curva: tuple[CandidatoTamano, ...] = ()

    @property
    def opera(self) -> bool:
        return self.cantidad_simulada > 0 and not self.motivos_no_operar


def _tope_por_restricciones(
    restricciones: tuple[Restriccion, ...],
) -> tuple[Decimal | None, tuple[str, ...], tuple[str, ...]]:
    """Tope minimo entre restricciones y los nombres de las bloqueantes."""
    topes = [r.cantidad_maxima for r in restricciones if r.cantidad_maxima is not None]
    tope = min(topes) if topes else None
    activas = tuple(r.nombre for r in restricciones if r.activa)
    sin_traducir = tuple(
        r.nombre for r in restricciones if r.activa and r.cantidad_maxima is None
    )
    return tope, activas, sin_traducir


def dimensionar(
    libro: Libro,
    lado: Lado,
    p_robust: Decimal | None,
    modelo: ModeloComisionCuadratica,
    limites: LimitesRiesgo,
    estado: EstadoRiesgo,
    momento: dt.datetime,
    motivos_previos: tuple[str, ...] = (),
    cantidad_maxima_busqueda: Decimal | None = None,
    paso_busqueda: Decimal = Decimal("1"),
    cantidad_minima: Decimal = Decimal("1"),
) -> PropuestaTamano:
    """Busca la cantidad discreta que maximiza ``G(n)`` y le aplica los limites.

    El orden importa: primero se busca el optimo con costes exactos, luego se
    reduce por ``alpha``, y solo al final se recortan los limites y se recalcula
    el coste de la cantidad final. Reducir antes de recalcular dejaria un coste
    que no corresponde a la cantidad propuesta.
    """
    motivos: list[str] = list(motivos_previos)

    if p_robust is None:
        motivos.append(
            "sin banda de incertidumbre defendible: tamano monetario desactivado"
        )
    if not modelo.verificada:
        motivos.append("modelo de comisiones no verificado")

    capital = limites.capital_segregado
    if capital <= 0:
        motivos.append("capital segregado no positivo")

    # Coste unitario de referencia para traducir topes en dinero a contratos.
    sonda = evaluar(libro, lado, Decimal("1"), p_robust or Decimal("0"), modelo)
    coste_unitario = sonda.coste_unitario
    restricciones = restricciones_vigentes(limites, estado, momento, coste_unitario)
    tope, activas, sin_traducir = _tope_por_restricciones(restricciones)
    for nombre in sin_traducir:
        motivos.append(f"restriccion no traducible a cantidad: {nombre}")

    if p_robust is None or capital <= 0:
        return PropuestaTamano(
            lado=lado,
            cantidad_simulada=Decimal("0"),
            simulated_amount=Decimal("0"),
            suggested_live_amount=Decimal("0"),
            perdida_maxima_simulada=Decimal("0"),
            p_usada=p_robust or Decimal("0"),
            es_ficticio=limites.es_capital_ficticio,
            cantidad_optima_sin_reduccion=Decimal("0"),
            crecimiento_en_propuesta=None,
            restricciones_activas=activas,
            motivos_no_operar=tuple(dict.fromkeys(motivos)),
        )

    # Techo de la busqueda: la profundidad disponible, acotada por los limites.
    profundidad = sum(
        (n.cantidad for n in libro.ventas(lado)), start=Decimal("0")
    )
    techo = profundidad if cantidad_maxima_busqueda is None else min(
        profundidad, cantidad_maxima_busqueda
    )
    if tope is not None:
        techo = min(techo, tope)
    techo = max(Decimal("0"), techo)

    # Busqueda exhaustiva sobre la rejilla de cantidades, incluido n = 0.
    curva: list[CandidatoTamano] = [
        CandidatoTamano(Decimal("0"), None, crecimiento_log(
            Decimal("0"), Decimal("0"), p_robust, capital
        ), True, "no operar")
    ]
    mejor = curva[0]
    n = paso_busqueda
    while n <= techo:
        ev = evaluar(libro, lado, n, p_robust, modelo)
        if not ev.completo:
            curva.append(
                CandidatoTamano(n, ev, None, False, "profundidad insuficiente")
            )
            break
        g = crecimiento_log(ev.cantidad_llenada, ev.coste_total, p_robust, capital)
        admisible = g is not None
        candidato = CandidatoTamano(
            n, ev, g, admisible, "" if admisible else "patrimonio no positivo"
        )
        curva.append(candidato)
        if admisible and (mejor.crecimiento is None or g > mejor.crecimiento):
            mejor = candidato
        n += paso_busqueda

    optima = mejor.cantidad

    # Reduccion fraccionada sobre el optimo discreto.
    reducida = (limites.fraccion_kelly * optima).to_integral_value(
        rounding=ROUND_FLOOR
    )
    if tope is not None:
        reducida = min(reducida, tope.to_integral_value(rounding=ROUND_FLOOR))
    reducida = max(Decimal("0"), reducida)
    if 0 < reducida < cantidad_minima:
        # Por debajo de la cantidad minima negociable no hay orden posible:
        # se redondea a cero en lugar de proponer algo inejecutable.
        motivos.append(
            f"cantidad tras reduccion ({reducida}) por debajo del minimo "
            f"negociable ({cantidad_minima})"
        )
        reducida = Decimal("0")

    # Recalculo exacto del coste de la cantidad final.
    if reducida > 0:
        final = evaluar(libro, lado, reducida, p_robust, modelo)
        if not final.completo:
            motivos.append("la cantidad final no se llena con la profundidad actual")
            reducida = Decimal("0")
            final = None
    else:
        final = None

    if reducida == 0 and not motivos:
        motivos.append("la cantidad optima tras reduccion y limites es cero")

    perdida_maxima = final.perdida_maxima if final is not None else Decimal("0")
    simulado = final.coste_total if final is not None else Decimal("0")
    crecimiento = (
        crecimiento_log(reducida, simulado, p_robust, capital)
        if final is not None
        else None
    )

    return PropuestaTamano(
        lado=lado,
        cantidad_simulada=reducida,
        simulated_amount=simulado,
        # Cero hasta que exista validacion prospectiva; ver docs/protocolo.md.
        suggested_live_amount=Decimal("0"),
        perdida_maxima_simulada=perdida_maxima,
        p_usada=p_robust,
        es_ficticio=limites.es_capital_ficticio,
        cantidad_optima_sin_reduccion=optima,
        crecimiento_en_propuesta=crecimiento,
        restricciones_activas=activas,
        motivos_no_operar=tuple(dict.fromkeys(motivos)),
        curva=tuple(curva),
    )
