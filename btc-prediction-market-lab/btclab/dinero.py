"""Dinero exacto y rejilla de precios escalonada.

El dinero nunca se representa en coma flotante. Los precios de un contrato
binario viven en ``mils`` (milesimas de dolar, 1/1000 USD) porque el tick minimo
documentado del contrato es $0.001; los importes agregados usan ``Decimal``.

La rejilla de Kalshi para la serie de 15 minutos no es plana: el campo
``price_level_structure`` vale ``tapered_deci_cent`` y ``price_ranges`` declara
paso $0.001 por debajo de $0.10 y por encima de $0.90, y $0.01 en el tramo
central. Suponer un tick plano de un centavo produciria precios inexistentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

#: Un dolar expresado en mils.
MILS_POR_DOLAR = 1000

#: Valor de liquidacion de un contrato ganador, segun los terminos del contrato.
PAGO_GANADOR = Decimal("1.00")

CENTAVO = Decimal("0.01")
MIL = Decimal("0.001")


class ErrorDinero(ValueError):
    """Importe o precio fuera de dominio."""


def dolares(valor: str | int | Decimal) -> Decimal:
    """Construye un importe exacto. Rechaza ``float`` para evitar ruido binario."""
    if isinstance(valor, float):
        raise ErrorDinero(
            "no se aceptan float para dinero; use str, int o Decimal"
        )
    try:
        return Decimal(valor)
    except Exception as exc:  # noqa: BLE001 - Decimal lanza varios tipos
        raise ErrorDinero(f"importe invalido: {valor!r}") from exc


def mils(precio: str | int | Decimal) -> int:
    """Convierte un precio en dolares a mils enteros.

    Falla si el precio no cae exactamente en la rejilla de mils, en lugar de
    redondear en silencio.
    """
    if isinstance(precio, int):
        valor = Decimal(precio)
    else:
        valor = dolares(precio)
    escalado = valor * MILS_POR_DOLAR
    if escalado != escalado.to_integral_value():
        raise ErrorDinero(f"precio {valor} no es multiplo de $0.001")
    entero = int(escalado)
    if not 0 <= entero <= MILS_POR_DOLAR:
        raise ErrorDinero(f"precio {valor} fuera de [0, 1]")
    return entero


def a_dolares(precio_mils: int) -> Decimal:
    """Convierte mils a dolares con tres decimales."""
    if not isinstance(precio_mils, int):
        raise ErrorDinero(f"se esperaban mils enteros: {precio_mils!r}")
    if not 0 <= precio_mils <= MILS_POR_DOLAR:
        raise ErrorDinero(f"mils fuera de [0, 1000]: {precio_mils}")
    return (Decimal(precio_mils) / MILS_POR_DOLAR).quantize(MIL)


def redondear_centavos_arriba(importe: Decimal) -> Decimal:
    """Redondeo al centavo superior, usado por las comisiones del exchange."""
    return dolares(importe).quantize(CENTAVO, rounding=ROUND_CEILING)


def redondear_centavos(importe: Decimal) -> Decimal:
    """Redondeo al centavo mas cercano, para presentacion de importes."""
    return dolares(importe).quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TramoPrecio:
    """Un tramo de la rejilla: ``[inicio, fin)`` con paso constante."""

    inicio_mils: int
    fin_mils: int
    paso_mils: int

    def __post_init__(self) -> None:
        if self.paso_mils <= 0:
            raise ErrorDinero(f"paso no positivo: {self.paso_mils}")
        if self.fin_mils <= self.inicio_mils:
            raise ErrorDinero(
                f"tramo vacio: [{self.inicio_mils}, {self.fin_mils})"
            )

    def contiene(self, precio_mils: int) -> bool:
        return self.inicio_mils <= precio_mils < self.fin_mils


@dataclass(frozen=True)
class Rejilla:
    """Rejilla de precios declarada por el mercado.

    Se construye desde el campo ``price_ranges`` del propio mercado, no desde una
    constante del codigo, para que un cambio del exchange se detecte como dato y
    no como supuesto.
    """

    tramos: tuple[TramoPrecio, ...]
    estructura: str = "desconocida"

    def __post_init__(self) -> None:
        if not self.tramos:
            raise ErrorDinero("rejilla sin tramos")
        ordenados = sorted(self.tramos, key=lambda t: t.inicio_mils)
        if ordenados[0].inicio_mils != 0:
            raise ErrorDinero("la rejilla no empieza en 0")
        for previo, siguiente in zip(ordenados, ordenados[1:]):
            if previo.fin_mils != siguiente.inicio_mils:
                raise ErrorDinero(
                    "tramos no contiguos: "
                    f"{previo.fin_mils} != {siguiente.inicio_mils}"
                )
        if ordenados[-1].fin_mils != MILS_POR_DOLAR:
            raise ErrorDinero("la rejilla no termina en 1000 mils")
        object.__setattr__(self, "tramos", tuple(ordenados))

    @classmethod
    def desde_price_ranges(
        cls, price_ranges: list[dict], estructura: str = "desconocida"
    ) -> "Rejilla":
        """Traduce el ``price_ranges`` del API a una rejilla validada."""
        tramos = []
        for tramo in price_ranges:
            try:
                tramos.append(
                    TramoPrecio(
                        inicio_mils=mils(str(tramo["start"])),
                        fin_mils=mils(str(tramo["end"])),
                        paso_mils=mils(str(tramo["step"])),
                    )
                )
            except KeyError as exc:
                raise ErrorDinero(f"tramo sin campo {exc}: {tramo!r}") from exc
        return cls(tramos=tuple(tramos), estructura=estructura)

    def paso_en(self, precio_mils: int) -> int:
        """Paso vigente en ``precio_mils``.

        El extremo superior (1000 mils) pertenece al ultimo tramo.
        """
        if precio_mils == MILS_POR_DOLAR:
            return self.tramos[-1].paso_mils
        for tramo in self.tramos:
            if tramo.contiene(precio_mils):
                return tramo.paso_mils
        raise ErrorDinero(f"precio fuera de la rejilla: {precio_mils} mils")

    def es_valido(self, precio_mils: int) -> bool:
        """True si el precio cae en un multiplo del paso de su tramo."""
        if not 0 <= precio_mils <= MILS_POR_DOLAR:
            return False
        if precio_mils in (0, MILS_POR_DOLAR):
            return True
        for tramo in self.tramos:
            if tramo.contiene(precio_mils):
                desplazamiento = precio_mils - tramo.inicio_mils
                return desplazamiento % tramo.paso_mils == 0
        return False

    def exigir_valido(self, precio_mils: int) -> int:
        if not self.es_valido(precio_mils):
            raise ErrorDinero(
                f"{a_dolares(precio_mils)} no esta en la rejilla "
                f"({self.estructura})"
            )
        return precio_mils


#: Rejilla observada el 2026-10-15 en ``KXBTC15M`` (``tapered_deci_cent``).
#: Se conserva como referencia de prueba; el codigo de produccion debe leer
#: ``price_ranges`` del mercado concreto.
REJILLA_TAPERED_DECI_CENT = Rejilla(
    tramos=(
        TramoPrecio(0, 100, 1),
        TramoPrecio(100, 900, 10),
        TramoPrecio(900, 1000, 1),
    ),
    estructura="tapered_deci_cent",
)
