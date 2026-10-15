"""Costes ejecutables, valor esperado y ventaja (Paso 6).

Definiciones, con pago $1/$0 y sin cargos especiales:

    A(n) = coste de comprar n contratos barriendo el libro ejecutable
    F(n) = comisiones y cargos aplicables a esa orden
    C(n) = A(n) + F(n)
    EV(n) = n * p_robust - C(n)
    c(n) = C(n) / n
    edge(n) = p_robust - c(n)

Dos errores que este modulo evita por construccion:

* **No sumar el spread como coste aparte.** Se compra al lado de las ventas, que
  ya incorpora el spread. Anadirlo otra vez lo cuenta dos veces.
* **No duplicar el deslizamiento.** El coste sale de barrer la profundidad del
  libro que estaba disponible al llegar la orden. Si ademas se anadiera una
  penalizacion de deslizamiento, seria el mismo efecto contado dos veces.

Cuando existan cargos o pagos excepcionales, estas formulas no se fuerzan: se
usan los flujos de caja de cada resultado (ver ``flujos_por_resultado``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .contrato import Comisiones, FichaContrato
from .dinero import (
    PAGO_GANADOR,
    a_dolares,
    dolares,
    redondear_centavos_arriba,
)
from .libro import Barrido, Lado, Libro


class ErrorCostes(ValueError):
    """Parametros de coste incoherentes."""


@dataclass(frozen=True)
class ModeloComisionCuadratica:
    """Comision ponderada por probabilidad.

    Forma general, verificada contra el API (``fee_type='quadratic'``,
    ``fee_multiplier=1`` para la serie de 15 minutos):

        comision = redondeo_arriba( constante * multiplicador * C * P * (1 - P) )

    donde ``P`` es el precio en dolares y ``C`` la cantidad. El maximo esta en
    ``P = 0.5``, que es justo donde opera un mercado de 15 minutos. Por eso una
    tarifa plana subestima el coste en el tramo mas usado.

    ``constante`` es un parametro de configuracion, no una constante del codigo,
    y ``verificada`` controla si se permite exponer importes. Mientras sea
    ``False`` el proyecto no puede sugerir cantidades monetarias.
    """

    constante: Decimal
    multiplicador: Decimal = Decimal("1")
    verificada: bool = False
    redondeo_por_nivel: bool = True

    def __post_init__(self) -> None:
        if self.constante < 0:
            raise ErrorCostes("constante de comision negativa")
        if self.multiplicador <= 0:
            raise ErrorCostes("multiplicador no positivo")

    def _bruta(self, cantidad: Decimal, precio: Decimal) -> Decimal:
        return (
            self.constante
            * self.multiplicador
            * dolares(cantidad)
            * precio
            * (PAGO_GANADOR - precio)
        )

    def de_barrido(self, barrido: Barrido) -> Decimal:
        """Comision de una orden que consumio varios niveles.

        Con ``redondeo_por_nivel`` el redondeo al centavo superior se aplica a
        cada tramo ejecutado, lo que es la lectura conservadora (coste mayor o
        igual). La alternativa agrega primero y redondea una vez; se expone para
        poder medir la sensibilidad, no para elegir la mas favorable.
        """
        if not barrido.niveles_usados:
            return Decimal("0")
        if self.redondeo_por_nivel:
            return sum(
                (
                    redondear_centavos_arriba(
                        self._bruta(cantidad, a_dolares(precio_mils))
                    )
                    for precio_mils, cantidad in barrido.niveles_usados
                ),
                start=Decimal("0"),
            )
        bruta = sum(
            (
                self._bruta(cantidad, a_dolares(precio_mils))
                for precio_mils, cantidad in barrido.niveles_usados
            ),
            start=Decimal("0"),
        )
        return redondear_centavos_arriba(bruta)

    @classmethod
    def desde_ficha(cls, comisiones: Comisiones) -> "ModeloComisionCuadratica":
        if comisiones.tipo != "quadratic":
            raise ErrorCostes(
                f"la ficha declara comision {comisiones.tipo!r}, no cuadratica"
            )
        if comisiones.constante is None:
            raise ErrorCostes("ficha sin constante de comision")
        return cls(
            constante=comisiones.constante,
            multiplicador=comisiones.multiplicador,
            verificada=comisiones.verificada,
        )


@dataclass(frozen=True)
class EvaluacionCoste:
    """Coste y ventaja de comprar ``cantidad`` contratos de un lado.

    ``p_usada`` es la probabilidad con la que se calculo el valor esperado. Se
    guarda junto al resultado para que el registro no deje dudas de si era la
    central o la conservadora.
    """

    lado: Lado
    cantidad_pedida: Decimal
    cantidad_llenada: Decimal
    coste_libro: Decimal          # A(n)
    comisiones: Decimal           # F(n)
    p_usada: Decimal
    niveles_usados: tuple[tuple[int, Decimal], ...]
    comisiones_verificadas: bool

    @property
    def coste_total(self) -> Decimal:
        """C(n) = A(n) + F(n)."""
        return self.coste_libro + self.comisiones

    @property
    def completo(self) -> bool:
        return self.cantidad_llenada >= self.cantidad_pedida

    @property
    def coste_unitario(self) -> Decimal | None:
        """c(n) = C(n) / n, sobre lo efectivamente llenado."""
        if self.cantidad_llenada == 0:
            return None
        return self.coste_total / self.cantidad_llenada

    @property
    def valor_esperado(self) -> Decimal:
        """EV(n) = n * p - C(n), sobre lo llenado."""
        return self.cantidad_llenada * self.p_usada - self.coste_total

    @property
    def ventaja(self) -> Decimal | None:
        """edge(n) = p - c(n)."""
        unitario = self.coste_unitario
        if unitario is None:
            return None
        return self.p_usada - unitario

    @property
    def perdida_maxima(self) -> Decimal:
        """Perdida si el contrato pierde y se mantiene a vencimiento.

        Es el coste total comprometido. Un stop de P&L no la limita: no asegura
        salida en un mercado que puede quedarse sin compradores.
        """
        return self.coste_total

    def flujos_por_resultado(self) -> dict[str, Decimal]:
        """Flujo de caja neto en cada resultado, incluido el coste ya pagado."""
        return {
            "gana": self.cantidad_llenada * PAGO_GANADOR - self.coste_total,
            "pierde": -self.coste_total,
        }


def evaluar(
    libro: Libro,
    lado: Lado,
    cantidad: Decimal,
    probabilidad: Decimal,
    modelo: ModeloComisionCuadratica,
    limite_mils: int | None = None,
) -> EvaluacionCoste:
    """Coste y ventaja de una compra agresiva contra ``libro``.

    Se compra YES en las ventas de YES y NO en las ventas de NO; nunca en el
    punto medio ni en el ultimo operado.
    """
    probabilidad = dolares(probabilidad)
    if not 0 <= probabilidad <= 1:
        raise ErrorCostes(f"probabilidad fuera de [0,1]: {probabilidad}")

    barrido = libro.barrer(lado, cantidad, limite_mils=limite_mils)
    return EvaluacionCoste(
        lado=lado,
        cantidad_pedida=barrido.cantidad_pedida,
        cantidad_llenada=barrido.cantidad_llenada,
        coste_libro=barrido.coste_bruto,
        comisiones=modelo.de_barrido(barrido),
        p_usada=probabilidad,
        niveles_usados=barrido.niveles_usados,
        comisiones_verificadas=modelo.verificada,
    )


def elegible(
    evaluacion: EvaluacionCoste,
    margen_operativo: Decimal,
    ficha: FichaContrato,
    motivos_calidad: tuple[str, ...] = (),
) -> tuple[bool, tuple[str, ...]]:
    """Decide si la senal pasa el filtro, y por que no si falla.

    ``margen_operativo`` se fija **antes** de la prueba final (ver
    ``docs/protocolo.md``) y es un umbral sobre el EV conservador por contrato.
    La sensibilidad a ese margen se reporta, pero la variante no se elige a
    posteriori.
    """
    motivos: list[str] = list(motivos_calidad)

    motivos.extend(ficha.motivos_bloqueo)
    if not evaluacion.comisiones_verificadas:
        motivos.append("modelo de comisiones no verificado")
    if evaluacion.cantidad_llenada == 0:
        motivos.append("sin profundidad ejecutable")
    elif not evaluacion.completo:
        motivos.append(
            f"liquidez insuficiente: {evaluacion.cantidad_llenada} de "
            f"{evaluacion.cantidad_pedida}"
        )

    ventaja = evaluacion.ventaja
    if ventaja is None:
        motivos.append("ventaja no calculable")
    elif ventaja <= margen_operativo:
        motivos.append(
            f"ventaja {ventaja} no supera el margen operativo {margen_operativo}"
        )

    return (not motivos), tuple(dict.fromkeys(motivos))
