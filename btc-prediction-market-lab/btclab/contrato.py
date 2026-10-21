"""Ficha de contrato versionada y reglas de liquidacion.

Este modulo es la puerta de entrada metodologica: si una regla esencial no esta
verificada, el estado es ``RULES_UNVERIFIED`` y el tamano monetario es cero. No
existe camino que produzca una cantidad sugerida sin una ficha completa.

El operador de comparacion se guarda explicito porque decide el empate. En los
terminos del contrato de Kalshi para cripto, "at least X" significa "X o mayor":
el empate liquida YES. En cambio "above X" es estrictamente mayor y el empate
liquida NO. Confundirlos invierte el resultado de los casos de borde, que son
precisamente los mas frecuentes en un mercado de 15 minutos.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from enum import Enum

from .dinero import ErrorDinero, Rejilla, dolares
from .tiempo import a_iso, exigir_utc


class Operador(str, Enum):
    """Comparacion entre el valor de liquidacion y el umbral."""

    MAYOR = "mayor"                  # > umbral ; empate -> NO
    MAYOR_O_IGUAL = "mayor_o_igual"  # >= umbral ; empate -> YES
    MENOR = "menor"                  # < umbral ; empate -> NO
    MENOR_O_IGUAL = "menor_o_igual"  # <= umbral ; empate -> YES
    RANGO_CERRADO = "rango_cerrado"  # umbral <= V <= umbral_superior

    @property
    def empate_liquida_yes(self) -> bool:
        """Que ocurre cuando el valor de liquidacion iguala el umbral."""
        return self in (
            Operador.MAYOR_O_IGUAL,
            Operador.MENOR_O_IGUAL,
            Operador.RANGO_CERRADO,
        )


#: Traduccion del campo ``strike_type`` del API de Kalshi a nuestro operador.
#: Se mantiene explicita para que un valor nuevo del exchange falle en lugar de
#: ser interpretado por omision.
STRIKE_TYPE_A_OPERADOR = {
    "greater": Operador.MAYOR,
    "greater_or_equal": Operador.MAYOR_O_IGUAL,
    "less": Operador.MENOR,
    "less_or_equal": Operador.MENOR_O_IGUAL,
    "between": Operador.RANGO_CERRADO,
}


class EstadoReglas(str, Enum):
    """Hasta donde esta verificada la ficha."""

    RULES_UNVERIFIED = "RULES_UNVERIFIED"
    COSTS_UNVERIFIED = "COSTS_UNVERIFIED"
    VERIFICADO = "VERIFICADO"

    @property
    def permite_tamano_monetario(self) -> bool:
        return self is EstadoReglas.VERIFICADO


class ErrorContrato(ValueError):
    """Ficha incompleta o incoherente."""


@dataclass(frozen=True)
class Fuente:
    """Procedencia documental de una regla."""

    url: str
    consultada_en: dt.datetime
    nota: str = ""

    def __post_init__(self) -> None:
        exigir_utc(self.consultada_en, "consultada_en")
        if not self.url:
            raise ErrorContrato("fuente sin url")


@dataclass(frozen=True)
class ReglaLiquidacion:
    """Como se determina el resultado.

    ``ventana_promedio_s`` es la longitud de la ventana que se promedia antes del
    instante de referencia. ``umbral_es_promedio_apertura`` marca los contratos
    que comparan el promedio de cierre contra el promedio de apertura: en ellos
    el umbral no es una constante del calendario sino un dato que se publica al
    abrir el mercado, y el momento de decision debe confirmar que ya se conoce.
    """

    indice: str
    agencia_fuente: str
    ventana_promedio_s: int
    operador: Operador
    umbral: Decimal | None
    umbral_superior: Decimal | None = None
    umbral_es_promedio_apertura: bool = False
    revisiones_posteriores_cuentan: bool = False
    sin_datos_liquida: str = "no"
    texto_oficial: str = ""

    def __post_init__(self) -> None:
        if self.ventana_promedio_s <= 0:
            raise ErrorContrato("ventana_promedio_s no positiva")
        if self.operador is Operador.RANGO_CERRADO and self.umbral_superior is None:
            raise ErrorContrato("rango sin umbral superior")
        if self.sin_datos_liquida not in ("yes", "no", "cancela"):
            raise ErrorContrato(
                f"sin_datos_liquida invalido: {self.sin_datos_liquida!r}"
            )

    def resuelve_yes(self, valor_liquidacion: Decimal | None) -> bool:
        """Aplica la regla al valor de liquidacion.

        ``None`` representa "sin dato o incompleto en el vencimiento", caso que
        los terminos resuelven explicitamente (para cripto en Kalshi, a NO).
        """
        if valor_liquidacion is None:
            if self.sin_datos_liquida == "cancela":
                raise ErrorContrato(
                    "sin dato: el contrato cancela; use el flujo de caja real"
                )
            return self.sin_datos_liquida == "yes"
        valor = dolares(valor_liquidacion)
        if self.umbral is None:
            raise ErrorContrato("umbral no fijado; ficha incompleta")
        umbral = dolares(self.umbral)
        if self.operador is Operador.MAYOR:
            return valor > umbral
        if self.operador is Operador.MAYOR_O_IGUAL:
            return valor >= umbral
        if self.operador is Operador.MENOR:
            return valor < umbral
        if self.operador is Operador.MENOR_O_IGUAL:
            return valor <= umbral
        if self.operador is Operador.RANGO_CERRADO:
            superior = dolares(self.umbral_superior)
            return umbral <= valor <= superior
        raise ErrorContrato(f"operador no implementado: {self.operador}")


@dataclass(frozen=True)
class Comisiones:
    """Modelo de costes del intermediario y del exchange.

    ``tipo`` se lee del propio exchange (para la serie de 15 minutos, el API
    devuelve ``fee_type='quadratic'`` y ``fee_multiplier=1``). La constante del
    modelo cuadratico se deja configurable y marcada como no verificada mientras
    no exista copia de la fuente primaria: una tarifa plana universal codificada
    a mano es precisamente lo que la metodologia prohibe.
    """

    tipo: str
    multiplicador: Decimal
    constante: Decimal | None
    verificada: bool
    vigente_desde: dt.datetime | None = None
    fuente: Fuente | None = None
    comision_intermediario: Decimal = Decimal("0")
    nota: str = ""

    def __post_init__(self) -> None:
        if self.tipo not in ("quadratic", "plana", "desconocida"):
            raise ErrorContrato(f"tipo de comision no soportado: {self.tipo!r}")
        if self.tipo != "desconocida" and self.constante is None:
            raise ErrorContrato("modelo de comision sin constante")


@dataclass(frozen=True)
class FichaContrato:
    """Ficha versionada de un contrato concreto.

    Guarda todo lo que la metodologia exige antes de permitir un tamano
    monetario, mas la huella de la propia ficha para poder citarla en cada
    decision registrada.
    """

    plataforma_visible: str
    exchange_subyacente: str
    serie: str
    evento: str
    contrato: str
    moneda: str
    apertura: dt.datetime
    fin_negociacion: dt.datetime
    vencimiento_esperado: dt.datetime
    vencimiento_limite: dt.datetime
    pregunta: str
    regla: ReglaLiquidacion
    rejilla: Rejilla
    pago_ganador: Decimal
    cantidad_minima: int
    fracciones_permitidas: bool
    comisiones: Comisiones
    limite_posicion_por_strike: Decimal | None
    estado_reglas: EstadoReglas
    version_reglas: str
    fuentes: tuple[Fuente, ...] = field(default_factory=tuple)
    reglas_faltantes: tuple[str, ...] = field(default_factory=tuple)
    zona_presentacion: str = "America/New_York"

    def __post_init__(self) -> None:
        for campo in (
            "apertura",
            "fin_negociacion",
            "vencimiento_esperado",
            "vencimiento_limite",
        ):
            exigir_utc(getattr(self, campo), campo)
        if self.fin_negociacion < self.apertura:
            raise ErrorContrato("fin de negociacion anterior a la apertura")
        if self.vencimiento_esperado < self.fin_negociacion:
            raise ErrorContrato("vencimiento esperado anterior al fin de negociacion")
        if self.vencimiento_limite < self.vencimiento_esperado:
            raise ErrorContrato("vencimiento limite anterior al esperado")
        if self.cantidad_minima < 1:
            raise ErrorContrato("cantidad minima menor que 1")
        if not self.fuentes:
            raise ErrorContrato("ficha sin fuentes documentales")
        if self.estado_reglas is EstadoReglas.VERIFICADO:
            if self.reglas_faltantes:
                raise ErrorContrato(
                    "ficha marcada VERIFICADO con reglas faltantes: "
                    f"{self.reglas_faltantes}"
                )
            if not self.comisiones.verificada:
                raise ErrorContrato(
                    "ficha marcada VERIFICADO con comisiones no verificadas"
                )

    @property
    def horizonte_s(self) -> float:
        """Segundos entre apertura y fin de negociacion."""
        return (self.fin_negociacion - self.apertura).total_seconds()

    @property
    def fin_ventana_liquidacion(self) -> dt.datetime:
        """Instante en que cierra la ventana que determina ``V_T``.

        **No es el vencimiento.** Para la serie de 15 minutos, las reglas fijan
        el promedio de los 60 s previos al **cierre de negociacion**, mientras
        ``expected_expiration_time`` llega unos cinco minutos despues (es cuando
        el exchange publica y liquida). Usar el vencimiento como horizonte
        anadiria difusion que el objetivo no tiene: en un contrato de 15 minutos
        son cinco minutos de mas, un tercio del horizonte real.

        Se verifico contra el texto oficial: para ``KXBTC15M`` el promedio de
        cierre es el de los 60 s anteriores a ``close_time``.
        """
        return self.fin_negociacion

    def tiempo_restante_s(self, momento: dt.datetime) -> float:
        """Segundos hasta que cierra la ventana que determina la liquidacion.

        El horizonte es el tiempo que falta para ese instante concreto, no una
        constante de 15 minutos ni de 24 horas, y no el vencimiento.
        """
        return (self.fin_ventana_liquidacion - exigir_utc(momento)).total_seconds()

    def tiempo_hasta_vencimiento_s(self, momento: dt.datetime) -> float:
        """Segundos hasta el vencimiento esperado.

        Es lo relevante para el capital inmovilizado, no para el modelo de
        precio: los fondos no se liberan en el cierre de negociacion.
        """
        return (self.vencimiento_esperado - exigir_utc(momento)).total_seconds()

    def negociable_en(self, momento: dt.datetime) -> bool:
        instante = exigir_utc(momento)
        return self.apertura <= instante < self.fin_negociacion

    @property
    def permite_tamano_monetario(self) -> bool:
        """Puerta unica para exponer importes distintos de cero."""
        return (
            self.estado_reglas.permite_tamano_monetario
            and self.comisiones.verificada
            and not self.reglas_faltantes
        )

    @property
    def motivos_bloqueo(self) -> tuple[str, ...]:
        """Por que no se permite un tamano monetario, si aplica."""
        motivos: list[str] = []
        if self.estado_reglas is not EstadoReglas.VERIFICADO:
            motivos.append(f"estado_reglas={self.estado_reglas.value}")
        if not self.comisiones.verificada:
            motivos.append("comisiones no verificadas contra fuente primaria")
        for falta in self.reglas_faltantes:
            motivos.append(f"regla faltante: {falta}")
        return tuple(motivos)

    def huella(self) -> str:
        """Hash estable de la ficha, para citarla desde el registro."""
        def normalizar(objeto):
            if isinstance(objeto, dt.datetime):
                return a_iso(objeto)
            if isinstance(objeto, Decimal):
                return str(objeto)
            if isinstance(objeto, Enum):
                return objeto.value
            if isinstance(objeto, Rejilla):
                return [
                    [t.inicio_mils, t.fin_mils, t.paso_mils] for t in objeto.tramos
                ]
            return str(objeto)

        crudo = json.dumps(
            asdict(self), default=normalizar, sort_keys=True, ensure_ascii=True
        )
        return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


def operador_desde_strike_type(strike_type: str) -> Operador:
    """Traduce ``strike_type`` del API; falla ante un valor desconocido."""
    try:
        return STRIKE_TYPE_A_OPERADOR[strike_type]
    except KeyError as exc:
        raise ErrorContrato(
            f"strike_type desconocido: {strike_type!r}; "
            "no se interpreta por omision porque decide el empate"
        ) from exc
