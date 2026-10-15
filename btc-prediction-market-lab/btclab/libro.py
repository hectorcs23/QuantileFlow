"""Libro ejecutable y coste de barrer profundidad.

Kalshi publica el libro como dos escaleras de ordenes de compra, una por lado:
``yes_dollars`` y ``no_dollars``. No existe escalera de ventas. La estructura
documentada de la plataforma es complementaria: una orden de compra de NO
descansando a ``q`` es ejecutable como una venta de YES a ``1 - q``, porque
ambos lados juntos aportan el dolar que paga al ganador.

De ahi:

* ventas de YES  = { (1 - q, tamano) : (q, tamano) en compras de NO }
* ventas de NO   = { (1 - p, tamano) : (p, tamano) en compras de YES }

Esto no es el supuesto prohibido ``ask_no = 1 - ask_yes`` (que relaciona dos
ventas entre si y es falso en presencia de spread). Es la relacion entre una
venta y la compra del lado opuesto, y se verifica en ejecucion contra el
``yes_ask``/``no_ask`` que el propio mercado reporta: ``verificar_contra_mercado``
falla si la derivacion y el API discrepan, en lugar de confiar en la formula.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .dinero import MILS_POR_DOLAR, ErrorDinero, a_dolares, dolares, mils
from .tiempo import exigir_utc


class Lado(str, Enum):
    YES = "yes"
    NO = "no"

    @property
    def opuesto(self) -> "Lado":
        return Lado.NO if self is Lado.YES else Lado.YES


class ErrorLibro(ValueError):
    """Libro incoherente, incompleto o no reconstruible."""


@dataclass(frozen=True)
class Nivel:
    """Un nivel de la escalera: precio en mils y cantidad de contratos."""

    precio_mils: int
    cantidad: Decimal

    def __post_init__(self) -> None:
        if not 0 <= self.precio_mils <= MILS_POR_DOLAR:
            raise ErrorLibro(f"precio fuera de rango: {self.precio_mils}")
        if self.cantidad < 0:
            raise ErrorLibro(f"cantidad negativa: {self.cantidad}")

    @property
    def precio(self) -> Decimal:
        return a_dolares(self.precio_mils)


@dataclass(frozen=True)
class Barrido:
    """Resultado de consumir profundidad contra la escalera de ventas."""

    cantidad_pedida: Decimal
    cantidad_llenada: Decimal
    coste_bruto: Decimal
    niveles_usados: tuple[tuple[int, Decimal], ...]

    @property
    def completo(self) -> bool:
        return self.cantidad_llenada >= self.cantidad_pedida

    @property
    def precio_medio(self) -> Decimal | None:
        """Coste medio por contrato, o ``None`` si no se lleno nada."""
        if self.cantidad_llenada == 0:
            return None
        return self.coste_bruto / self.cantidad_llenada

    @property
    def peor_precio_mils(self) -> int | None:
        if not self.niveles_usados:
            return None
        return max(precio for precio, _ in self.niveles_usados)


@dataclass(frozen=True)
class Libro:
    """Snapshot del libro con su doble marca temporal.

    ``secuencia`` permite detectar huecos. ``es_snapshot`` distingue un snapshot
    completo de un libro reconstruido a partir de deltas: tras una desconexion
    solo un snapshot nuevo vuelve a considerarse valido.
    """

    contrato: str
    event_time: dt.datetime
    received_at: dt.datetime
    compras_yes: tuple[Nivel, ...]
    compras_no: tuple[Nivel, ...]
    secuencia: int | None = None
    es_snapshot: bool = True
    fuente: str = "kalshi"

    def __post_init__(self) -> None:
        exigir_utc(self.event_time, "event_time")
        exigir_utc(self.received_at, "received_at")
        if not self.contrato:
            raise ErrorLibro("libro sin contrato")

    # -- construccion ---------------------------------------------------

    @classmethod
    def desde_payload(
        cls,
        contrato: str,
        payload: dict,
        received_at: dt.datetime,
        event_time: dt.datetime | None = None,
        secuencia: int | None = None,
    ) -> "Libro":
        """Traduce la respuesta de ``/orderbook`` sin alterar su contenido."""
        cuerpo = payload.get("orderbook_fp") or payload.get("orderbook") or {}
        if not isinstance(cuerpo, dict):
            raise ErrorLibro(f"orderbook no es un objeto: {cuerpo!r}")

        def escalera(clave: str) -> tuple[Nivel, ...]:
            crudo = cuerpo.get(clave) or []
            if crudo is None:
                return ()
            niveles = []
            for entrada in crudo:
                if not isinstance(entrada, (list, tuple)) or len(entrada) < 2:
                    raise ErrorLibro(f"nivel ilegible en {clave}: {entrada!r}")
                try:
                    niveles.append(
                        Nivel(
                            precio_mils=mils(str(entrada[0])),
                            cantidad=dolares(str(entrada[1])),
                        )
                    )
                except ErrorDinero as exc:
                    raise ErrorLibro(
                        f"nivel invalido en {clave}: {entrada!r} ({exc})"
                    ) from exc
            return tuple(sorted(niveles, key=lambda n: n.precio_mils))

        return cls(
            contrato=contrato,
            event_time=event_time or received_at,
            received_at=received_at,
            compras_yes=escalera("yes_dollars") or escalera("yes"),
            compras_no=escalera("no_dollars") or escalera("no"),
            secuencia=secuencia,
            es_snapshot=True,
        )

    # -- lectura --------------------------------------------------------

    def compras(self, lado: Lado) -> tuple[Nivel, ...]:
        return self.compras_yes if lado is Lado.YES else self.compras_no

    def mejor_compra_mils(self, lado: Lado) -> int | None:
        niveles = [n for n in self.compras(lado) if n.cantidad > 0]
        return max(n.precio_mils for n in niveles) if niveles else None

    def ventas(self, lado: Lado) -> tuple[Nivel, ...]:
        """Escalera de ventas del lado, derivada de las compras del opuesto.

        Se devuelve en orden ascendente de precio: el primer nivel es el mas
        barato y por tanto el primero que consume una compra agresiva.
        """
        derivadas = [
            Nivel(precio_mils=MILS_POR_DOLAR - n.precio_mils, cantidad=n.cantidad)
            for n in self.compras(lado.opuesto)
            if n.cantidad > 0
        ]
        return tuple(sorted(derivadas, key=lambda n: n.precio_mils))

    def mejor_venta_mils(self, lado: Lado) -> int | None:
        escalera = self.ventas(lado)
        return escalera[0].precio_mils if escalera else None

    def spread_mils(self, lado: Lado) -> int | None:
        compra = self.mejor_compra_mils(lado)
        venta = self.mejor_venta_mils(lado)
        if compra is None or venta is None:
            return None
        return venta - compra

    def punto_medio_mils(self, lado: Lado) -> Decimal | None:
        """Punto medio, solo como referencia de evaluacion.

        No es una probabilidad verdadera ni un precio al que se pueda ejecutar.
        """
        compra = self.mejor_compra_mils(lado)
        venta = self.mejor_venta_mils(lado)
        if compra is None or venta is None:
            return None
        return (Decimal(compra) + Decimal(venta)) / 2

    def profundidad(self, lado: Lado, hasta_mils: int) -> Decimal:
        """Contratos disponibles para comprar ``lado`` sin pasar de ``hasta_mils``."""
        return sum(
            (n.cantidad for n in self.ventas(lado) if n.precio_mils <= hasta_mils),
            start=Decimal("0"),
        )

    def imbalance(self) -> Decimal | None:
        """Desequilibrio entre el tamano de las mejores compras de cada lado.

        Devuelve un valor en ``[-1, 1]``: positivo cuando pesa mas la compra de
        YES. Es una variable de liquidez, no una senal validada.
        """
        yes = [n for n in self.compras_yes if n.cantidad > 0]
        no = [n for n in self.compras_no if n.cantidad > 0]
        if not yes or not no:
            return None
        mejor_yes = max(yes, key=lambda n: n.precio_mils).cantidad
        mejor_no = max(no, key=lambda n: n.precio_mils).cantidad
        total = mejor_yes + mejor_no
        if total == 0:
            return None
        return (mejor_yes - mejor_no) / total

    # -- ejecucion ------------------------------------------------------

    def barrer(
        self, lado: Lado, cantidad: Decimal, limite_mils: int | None = None
    ) -> Barrido:
        """Coste de comprar ``cantidad`` contratos de ``lado`` contra el libro.

        Consume profundidad nivel a nivel desde el mas barato. ``limite_mils``
        actua como precio limite: los niveles por encima no se ejecutan, de modo
        que una orden limitada puede quedar parcialmente llena o sin llenar.
        """
        pedida = dolares(cantidad)
        if pedida <= 0:
            return Barrido(pedida, Decimal("0"), Decimal("0"), ())

        restante = pedida
        coste = Decimal("0")
        usados: list[tuple[int, Decimal]] = []

        for nivel in self.ventas(lado):
            if restante <= 0:
                break
            if limite_mils is not None and nivel.precio_mils > limite_mils:
                break
            toma = min(restante, nivel.cantidad)
            if toma <= 0:
                continue
            coste += toma * a_dolares(nivel.precio_mils)
            usados.append((nivel.precio_mils, toma))
            restante -= toma

        return Barrido(
            cantidad_pedida=pedida,
            cantidad_llenada=pedida - restante,
            coste_bruto=coste,
            niveles_usados=tuple(usados),
        )

    # -- control --------------------------------------------------------

    def verificar_contra_mercado(self, mercado: dict) -> tuple[str, ...]:
        """Compara la derivacion con los mejores precios que reporta el API.

        Devuelve la lista de discrepancias. Una lista vacia significa que la
        estructura complementaria se sostiene en este snapshot. Cualquier
        discrepancia debe tratarse como motivo de no operar, no como ruido.
        """
        problemas: list[str] = []
        comparaciones = (
            ("yes_bid_dollars", self.mejor_compra_mils(Lado.YES)),
            ("no_bid_dollars", self.mejor_compra_mils(Lado.NO)),
            ("yes_ask_dollars", self.mejor_venta_mils(Lado.YES)),
            ("no_ask_dollars", self.mejor_venta_mils(Lado.NO)),
        )
        for clave, derivado in comparaciones:
            if clave not in mercado:
                continue
            crudo = mercado[clave]
            try:
                reportado = mils(str(crudo))
            except ErrorDinero:
                problemas.append(f"{clave} ilegible: {crudo!r}")
                continue
            # Un libro vacio por un lado hace que el API reporte el extremo
            # (0 para la compra, 1 para la venta); eso no es discrepancia.
            if derivado is None:
                if clave.endswith("bid_dollars") and reportado != 0:
                    problemas.append(f"{clave}: API {reportado}, libro vacio")
                if clave.endswith("ask_dollars") and reportado != MILS_POR_DOLAR:
                    problemas.append(f"{clave}: API {reportado}, libro vacio")
                continue
            if derivado != reportado:
                problemas.append(
                    f"{clave}: API {a_dolares(reportado)} != "
                    f"derivado {a_dolares(derivado)}"
                )
        return tuple(problemas)

    def calidad(self, momento: dt.datetime, antiguedad_max_s: float) -> tuple[str, ...]:
        """Motivos por los que este libro no deberia usarse para decidir."""
        motivos: list[str] = []
        if not self.es_snapshot:
            motivos.append("libro reconstruido sin snapshot valido")
        antiguedad = (exigir_utc(momento) - self.received_at).total_seconds()
        if antiguedad > antiguedad_max_s:
            motivos.append(
                f"cotizacion caducada: {antiguedad:.1f}s > {antiguedad_max_s:.1f}s"
            )
        if antiguedad < 0:
            motivos.append("libro recibido despues del momento de decision")
        if self.mejor_venta_mils(Lado.YES) is None:
            motivos.append("sin ventas de YES ejecutables")
        if self.mejor_venta_mils(Lado.NO) is None:
            motivos.append("sin ventas de NO ejecutables")
        for lado in (Lado.YES, Lado.NO):
            spread = self.spread_mils(lado)
            if spread is not None and spread < 0:
                motivos.append(f"spread negativo en {lado.value}: libro cruzado")
        return tuple(motivos)
