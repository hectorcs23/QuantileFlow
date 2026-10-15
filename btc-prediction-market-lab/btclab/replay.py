"""Replay de ejecucion realista (Paso 9).

Se reproduce en **orden de disponibilidad**: mensaje recibido, decision,
calculo, retraso, orden simulada, fill, liquidacion. Cada etapa tiene su propio
retraso, medido por separado, porque mezclarlos oculta donde esta el problema.

Lo que este modulo **no** hace, por prohibicion explicita de la metodologia:

* No rellena al punto medio, ni al ultimo operado, ni al mejor precio de la vela.
* No simula ordenes pasivas con supuestos optimistas de cola. Una orden limitada
  no garantiza ejecucion; aqui una limitada solo se llena contra profundidad que
  ya estaba disponible a su precio o mejor.
* No usa el libro del momento de la decision para el fill: usa el libro que
  habria estado disponible **a la llegada de la orden**.
* No duplica el deslizamiento: el coste sale de barrer ese libro, y no se suma
  ninguna penalizacion adicional.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from .costes import EvaluacionCoste, ModeloComisionCuadratica, evaluar
from .libro import Lado, Libro
from .objetivo import Etiqueta
from .tiempo import exigir_utc


class ErrorReplay(ValueError):
    """Replay mal planteado."""


@dataclass(frozen=True)
class PerfilRetrasos:
    """Retrasos de cada etapa, en segundos.

    Se declaran por separado porque tienen causas distintas: la latencia de datos
    depende de la red y del proveedor, el calculo de nuestro codigo, y la accion
    humana del flujo manual. **No son intercambiables:** las latencias de una API
    no sirven para estimar el retraso de un humano operando a mano, y usarlas asi
    produce una conclusion que no se sostiene.
    """

    datos_s: float = 0.0
    calculo_s: float = 0.0
    accion_humana_s: float = 0.0
    etiqueta: str = "sin medir"
    medido: bool = False

    def __post_init__(self) -> None:
        for nombre in ("datos_s", "calculo_s", "accion_humana_s"):
            if getattr(self, nombre) < 0:
                raise ErrorReplay(f"{nombre} negativo")

    @property
    def total_s(self) -> float:
        return self.datos_s + self.calculo_s + self.accion_humana_s

    def llegada(self, decision_en: dt.datetime) -> dt.datetime:
        return exigir_utc(decision_en) + dt.timedelta(seconds=self.total_s)


#: Escenarios explicitos para cuando aun no hay mediciones del flujo real. La
#: conclusion obtenida con ellos es **provisional** y debe etiquetarse asi.
ESCENARIOS_RETRASO = {
    "optimista": PerfilRetrasos(0.3, 0.2, 2.0, "escenario optimista", False),
    "central": PerfilRetrasos(1.0, 0.5, 8.0, "escenario central", False),
    "pesimista": PerfilRetrasos(3.0, 1.0, 25.0, "escenario pesimista", False),
}


@dataclass(frozen=True)
class Orden:
    """Orden simulada. Solo agresiva: el MVP no modela ordenes pasivas."""

    lado: Lado
    cantidad: Decimal
    limite_mils: int | None
    decision_en: dt.datetime
    contrato: str

    def __post_init__(self) -> None:
        exigir_utc(self.decision_en, "decision_en")
        if self.cantidad <= 0:
            raise ErrorReplay("cantidad no positiva")


@dataclass(frozen=True)
class Fill:
    """Resultado de la orden simulada."""

    orden: Orden
    llegada_en: dt.datetime
    libro_usado_en: dt.datetime | None
    evaluacion: EvaluacionCoste | None
    estado: str
    motivo: str = ""

    @property
    def ejecutada(self) -> bool:
        return self.estado in ("completa", "parcial")

    @property
    def cantidad_llenada(self) -> Decimal:
        return (
            Decimal("0") if self.evaluacion is None else self.evaluacion.cantidad_llenada
        )

    @property
    def coste_total(self) -> Decimal:
        return Decimal("0") if self.evaluacion is None else self.evaluacion.coste_total


@dataclass(frozen=True)
class EstresMercado:
    """Deterioro aplicado al libro para el estres predefinido.

    ``factor_profundidad`` < 1 reduce la liquidez disponible;
    ``recargo_mils`` encarece cada nivel. Los escenarios se fijan **antes** de la
    prueba, y los dias malos no se excluyen a posteriori.
    """

    factor_profundidad: Decimal = Decimal("1")
    recargo_mils: int = 0
    etiqueta: str = "sin estres"

    def aplicar(self, libro: Libro) -> Libro:
        if self.factor_profundidad == 1 and self.recargo_mils == 0:
            return libro

        def deteriorar(niveles):
            from .libro import Nivel

            salida = []
            for nivel in niveles:
                cantidad = nivel.cantidad * self.factor_profundidad
                # Encarecer la compra de un lado equivale a bajar la compra en
                # reposo del lado opuesto, que es como se representa el libro.
                precio = max(0, min(1000, nivel.precio_mils - self.recargo_mils))
                if cantidad > 0:
                    salida.append(Nivel(precio_mils=precio, cantidad=cantidad))
            return tuple(salida)

        return Libro(
            contrato=libro.contrato,
            event_time=libro.event_time,
            received_at=libro.received_at,
            compras_yes=deteriorar(libro.compras_yes),
            compras_no=deteriorar(libro.compras_no),
            secuencia=libro.secuencia,
            es_snapshot=libro.es_snapshot,
            fuente=f"{libro.fuente}+estres:{self.etiqueta}",
        )


def libro_a_la_llegada(
    libros: Sequence[Libro], llegada: dt.datetime, antiguedad_max_s: float | None = None
) -> Libro | None:
    """Ultimo libro recibido en o antes de la llegada de la orden.

    Es el unico libro legitimo para simular el fill: usar el de la decision
    regalaria a la estrategia el movimiento ocurrido durante el retraso.
    """
    instante = exigir_utc(llegada)
    candidato: Libro | None = None
    for libro in libros:
        if libro.received_at <= instante:
            if candidato is None or libro.received_at > candidato.received_at:
                candidato = libro
    if candidato is None:
        return None
    if antiguedad_max_s is not None:
        antiguedad = (instante - candidato.received_at).total_seconds()
        if antiguedad > antiguedad_max_s:
            return None
    return candidato


def ejecutar(
    orden: Orden,
    libros: Sequence[Libro],
    perfil: PerfilRetrasos,
    modelo: ModeloComisionCuadratica,
    probabilidad: Decimal,
    estres: EstresMercado | None = None,
    antiguedad_max_s: float | None = None,
) -> Fill:
    """Simula la orden con el libro disponible a su llegada."""
    llegada = perfil.llegada(orden.decision_en)
    libro = libro_a_la_llegada(libros, llegada, antiguedad_max_s)

    if libro is None:
        return Fill(
            orden=orden,
            llegada_en=llegada,
            libro_usado_en=None,
            evaluacion=None,
            estado="rechazada",
            motivo="sin libro valido a la llegada de la orden",
        )

    if estres is not None:
        libro = estres.aplicar(libro)

    mejor = libro.mejor_venta_mils(orden.lado)
    if mejor is None:
        return Fill(
            orden=orden,
            llegada_en=llegada,
            libro_usado_en=libro.received_at,
            evaluacion=None,
            estado="rechazada",
            motivo="sin ventas ejecutables a la llegada",
        )

    # Orden limitada cuyo precio ya fue superado: no se ejecuta. Una limitada no
    # garantiza ejecucion, y suponerlo es el error que infla los backtests.
    if orden.limite_mils is not None and mejor > orden.limite_mils:
        return Fill(
            orden=orden,
            llegada_en=llegada,
            libro_usado_en=libro.received_at,
            evaluacion=None,
            estado="no_ejecutada",
            motivo=(
                f"mejor venta {mejor} mils por encima del limite "
                f"{orden.limite_mils} mils a la llegada"
            ),
        )

    evaluacion = evaluar(
        libro, orden.lado, orden.cantidad, probabilidad, modelo,
        limite_mils=orden.limite_mils,
    )

    if evaluacion.cantidad_llenada == 0:
        estado, motivo = "no_ejecutada", "profundidad nula al precio limite"
    elif evaluacion.completo:
        estado, motivo = "completa", ""
    else:
        estado, motivo = (
            "parcial",
            f"llenado {evaluacion.cantidad_llenada} de {orden.cantidad}",
        )

    return Fill(
        orden=orden,
        llegada_en=llegada,
        libro_usado_en=libro.received_at,
        evaluacion=evaluacion,
        estado=estado,
        motivo=motivo,
    )


@dataclass(frozen=True)
class FlujoCaja:
    """Flujos de una posicion simulada, con fondos inmovilizados.

    ``liberado_en`` es cuando el capital vuelve a ser utilizable, que no es el
    vencimiento sino la liquidacion. Tratarlo como disponible antes sobreestima
    cuantas operaciones caben en un dia.
    """

    contrato: str
    pagado: Decimal
    cobrado: Decimal
    inmovilizado_desde: dt.datetime
    liberado_en: dt.datetime
    resultado: str
    excepcional: bool = False

    @property
    def neto(self) -> Decimal:
        return self.cobrado - self.pagado


def liquidar(
    fill: Fill,
    etiqueta: Etiqueta,
    liberacion_en: dt.datetime | None = None,
) -> FlujoCaja:
    """Aplica la liquidacion al fill, respetando resultados excepcionales.

    Para una cancelacion o un pago especial se usa el flujo de caja real que
    trae la etiqueta, en lugar de forzar la formula binaria.
    """
    if not fill.ejecutada or fill.evaluacion is None:
        return FlujoCaja(
            contrato=fill.orden.contrato,
            pagado=Decimal("0"),
            cobrado=Decimal("0"),
            inmovilizado_desde=fill.llegada_en,
            liberado_en=liberacion_en or fill.llegada_en,
            resultado="sin_posicion",
        )

    pagado = fill.coste_total
    cantidad = fill.cantidad_llenada
    liberado = liberacion_en or etiqueta.disponible_en

    if etiqueta.excepcional:
        # Claves con significado declarado, para que un reembolso no se confunda
        # con un pago. ``reembolso_coste`` devuelve lo pagado (una cancelacion no
        # es una ganancia); ``pago_por_contrato`` paga ese importe por contrato.
        flujos = etiqueta.flujo_caja_por_contrato or {}
        cobrado = Decimal("0")
        desconocidas = []
        for clave, valor in flujos.items():
            if clave == "reembolso_coste":
                cobrado += pagado * valor
            elif clave == "pago_por_contrato":
                cobrado += cantidad * valor
            else:
                desconocidas.append(clave)
        if desconocidas:
            raise ErrorReplay(
                "flujo excepcional con claves no reconocidas: "
                f"{desconocidas}; use reembolso_coste o pago_por_contrato"
            )
        return FlujoCaja(
            contrato=fill.orden.contrato,
            pagado=pagado,
            cobrado=cobrado,
            inmovilizado_desde=fill.llegada_en,
            liberado_en=liberado,
            resultado=etiqueta.resultado_oficial or "excepcional",
            excepcional=True,
        )

    gana_yes = etiqueta.y == 1
    gana = gana_yes if fill.orden.lado is Lado.YES else not gana_yes
    cobrado = cantidad if gana else Decimal("0")
    return FlujoCaja(
        contrato=fill.orden.contrato,
        pagado=pagado,
        cobrado=cobrado,
        inmovilizado_desde=fill.llegada_en,
        liberado_en=liberado,
        resultado="gana" if gana else "pierde",
    )
