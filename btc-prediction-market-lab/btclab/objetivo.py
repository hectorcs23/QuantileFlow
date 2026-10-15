"""Objetivo y momento de decision (Paso 3).

``Y = 1`` cuando YES liquida a $1 conforme a las reglas del contrato; ``Y = 0``
cuando liquida a $0. Las cancelaciones y los pagos especiales **no** se
convierten en perdidas ni se borran: se registran aparte con su flujo de caja
real, y el simulador los aplica tal cual.

``V_T`` es el valor de referencia que se usa en la liquidacion. Para la serie de
15 minutos de Kalshi hay **dos** promedios de 60 segundos en juego:

* el de apertura, que **es** el umbral (``floor_strike``), conocido al abrir;
* el de cierre, que es ``V_T`` (``expiration_value``).

Verificado empiricamente: el ``expiration_value`` de un contrato es exactamente
el ``floor_strike`` del siguiente. Por eso el objetivo de un modelo de precio no
es "el precio de BTC" sino ese promedio concreto, y el umbral debe confirmarse
como conocido antes de decidir.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .contrato import ErrorContrato, FichaContrato, ReglaLiquidacion
from .tiempo import exigir_utc


class ErrorObjetivo(ValueError):
    """Etiqueta no construible desde los datos."""


@dataclass(frozen=True)
class Etiqueta:
    """Resultado de un contrato, con su procedencia.

    ``y`` es ``None`` cuando el contrato no produjo un binario ordinario
    (cancelacion o pago especial). En ese caso ``flujo_caja_por_contrato`` lleva
    el flujo real y la evaluacion economica lo usa en lugar de la formula
    binaria.
    """

    contrato: str
    y: int | None
    valor_liquidacion: Decimal | None
    resultado_oficial: str
    version_reglas: str
    disponible_en: dt.datetime
    excepcional: bool = False
    flujo_caja_por_contrato: dict[str, Decimal] | None = None
    nota: str = ""

    def __post_init__(self) -> None:
        exigir_utc(self.disponible_en, "disponible_en")
        if self.y not in (0, 1, None):
            raise ErrorObjetivo(f"y invalido: {self.y!r}")
        if self.y is None and not self.excepcional:
            raise ErrorObjetivo("y nulo sin marcar como excepcional")


def etiqueta_desde_mercado(
    mercado: dict,
    ficha: FichaContrato,
    disponible_en: dt.datetime,
) -> Etiqueta:
    """Construye la etiqueta desde el mercado liquidado.

    Comprueba que el resultado oficial coincide con aplicar la regla al valor de
    liquidacion. Una discrepancia **no** se resuelve en favor de ninguno de los
    dos: se marca como excepcional, porque significa que nuestra lectura de las
    reglas o del operador es incorrecta y el contrato no esta verificado.
    """
    resultado = (mercado.get("result") or "").strip().lower()
    if not resultado:
        raise ErrorObjetivo(f"mercado sin resultado: {mercado.get('ticker')}")

    crudo = mercado.get("expiration_value")
    valor: Decimal | None = None
    if crudo not in (None, ""):
        try:
            valor = Decimal(str(crudo))
        except InvalidOperation as exc:
            raise ErrorObjetivo(f"expiration_value ilegible: {crudo!r}") from exc

    contrato = mercado.get("ticker", ficha.contrato)

    if resultado in ("void", "cancelled", "canceled"):
        return Etiqueta(
            contrato=contrato,
            y=None,
            valor_liquidacion=valor,
            resultado_oficial=resultado,
            version_reglas=ficha.version_reglas,
            disponible_en=disponible_en,
            excepcional=True,
            # Una cancelacion devuelve lo pagado: no es ganancia ni perdida.
            flujo_caja_por_contrato={"reembolso_coste": Decimal("1")},
            nota="cancelacion: se reembolsa el coste; no se fuerza una perdida",
        )

    if resultado not in ("yes", "no"):
        return Etiqueta(
            contrato=contrato,
            y=None,
            valor_liquidacion=valor,
            resultado_oficial=resultado,
            version_reglas=ficha.version_reglas,
            disponible_en=disponible_en,
            excepcional=True,
            nota=f"resultado no binario: {resultado!r}",
        )

    y_oficial = 1 if resultado == "yes" else 0

    # Control: aplicar la regla debe reproducir el resultado oficial.
    if valor is not None and ficha.regla.umbral is not None:
        try:
            y_regla = 1 if ficha.regla.resuelve_yes(valor) else 0
        except ErrorContrato:
            y_regla = None
        if y_regla is not None and y_regla != y_oficial:
            return Etiqueta(
                contrato=contrato,
                y=None,
                valor_liquidacion=valor,
                resultado_oficial=resultado,
                version_reglas=ficha.version_reglas,
                disponible_en=disponible_en,
                excepcional=True,
                nota=(
                    "la regla no reproduce el resultado oficial: "
                    f"oficial={resultado}, regla={'yes' if y_regla else 'no'}, "
                    f"V_T={valor}, umbral={ficha.regla.umbral}, "
                    f"operador={ficha.regla.operador.value}"
                ),
            )

    return Etiqueta(
        contrato=contrato,
        y=y_oficial,
        valor_liquidacion=valor,
        resultado_oficial=resultado,
        version_reglas=ficha.version_reglas,
        disponible_en=disponible_en,
    )


@dataclass(frozen=True)
class MomentoDecision:
    """Un unico momento de decision por contrato.

    Propuesta inicial del experimento: una observacion y una entrada maxima por
    contrato, ``retraso_s`` despues de abrir, mantenida hasta liquidacion. Es una
    eleccion para reducir grados de libertad, **no** una senal validada. Elegir a
    posteriori el mejor minuto seria seleccion sobre el resultado.
    """

    retraso_s: float = 60.0

    def instante(self, ficha: FichaContrato) -> dt.datetime:
        return ficha.apertura + dt.timedelta(seconds=self.retraso_s)

    def admisible(
        self,
        ficha: FichaContrato,
        umbral_conocido: bool,
        libro_valido: bool,
    ) -> tuple[bool, tuple[str, ...]]:
        """Comprueba las tres condiciones del Paso 3, y por que falla si falla."""
        motivos: list[str] = []
        instante = self.instante(ficha)
        if not umbral_conocido:
            motivos.append("el umbral aun no se conoce en el momento de decision")
        if not libro_valido:
            motivos.append("sin libro valido en el momento de decision")
        if not ficha.negociable_en(instante):
            motivos.append(
                f"el contrato no es negociable en {instante.isoformat()}"
            )
        if ficha.tiempo_restante_s(instante) <= 0:
            motivos.append("sin tiempo restante hasta el vencimiento")
        return (not motivos), tuple(motivos)
