"""Precio, probabilidad e incertidumbre como tres objetos distintos (Paso 5).

El modulo publica por separado:

1. Cuantiles de ``V_T`` e intervalos centrales de prediccion (50/80/95 %).
2. Probabilidad calibrada ``p_yes``, con ``p_no = 1 - p_yes``.
3. Banda aproximada ``[L, U]`` sobre la *estimacion* de ``p_yes``.

El punto que mas facilmente se implementa mal es la probabilidad conservadora
del lado NO. La banda ``[L, U]`` acota ``p_yes``. Como ``p_no = 1 - p_yes``, la
banda de ``p_no`` es ``[1 - U, 1 - L]``, y la cota **inferior** de ``p_no`` es
``1 - U``. Usar ``1 - L`` tomaria la cota superior de ``p_no`` y seria
anticonservador justo en la direccion que infla el valor esperado. La clase
``Prediccion`` solo expone ``p_robust`` por lado para que no exista la
oportunidad de escribir ``1 - L`` por descuido.

La banda es aproximada y condicionada a supuestos; puede fallar ante cambios de
regimen. No significa que una operacion individual gane con 95 % de confianza, y
la "probabilidad verdadera" de un evento unico no es observable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .dinero import dolares
from .libro import Lado


class ErrorProbabilidad(ValueError):
    """Probabilidad o banda incoherente."""


@dataclass(frozen=True)
class IntervaloPrediccion:
    """Intervalo central de ``V_T`` a un nivel nominal dado."""

    nivel: Decimal
    inferior: Decimal
    superior: Decimal

    def __post_init__(self) -> None:
        if not 0 < self.nivel < 1:
            raise ErrorProbabilidad(f"nivel fuera de (0,1): {self.nivel}")
        if self.superior < self.inferior:
            raise ErrorProbabilidad(
                f"intervalo invertido: [{self.inferior}, {self.superior}]"
            )

    def cubre(self, valor: Decimal) -> bool:
        return self.inferior <= dolares(valor) <= self.superior


@dataclass(frozen=True)
class BandaProbabilidad:
    """Banda aproximada sobre la estimacion de ``p_yes``.

    ``metodo`` y ``supuestos`` son obligatorios: la metodologia exige que el
    metodo y sus supuestos sean visibles, y que la dispersion entre modelos no se
    presente como si fuera un intervalo de confianza valido.
    """

    inferior: Decimal
    superior: Decimal
    metodo: str
    supuestos: str
    nivel_nominal: Decimal | None = None
    cobertura_empirica: Decimal | None = None
    defendible: bool = True

    def __post_init__(self) -> None:
        for nombre in ("inferior", "superior"):
            valor = getattr(self, nombre)
            if not 0 <= valor <= 1:
                raise ErrorProbabilidad(f"{nombre} fuera de [0,1]: {valor}")
        if self.superior < self.inferior:
            raise ErrorProbabilidad(
                f"banda invertida: [{self.inferior}, {self.superior}]"
            )
        if not self.metodo:
            raise ErrorProbabilidad("banda sin metodo declarado")
        if not self.supuestos:
            raise ErrorProbabilidad("banda sin supuestos declarados")

    @property
    def ancho(self) -> Decimal:
        return self.superior - self.inferior


@dataclass(frozen=True)
class Prediccion:
    """Salida completa del modelo para un contrato y un momento.

    ``p_yes`` es la probabilidad calibrada central. ``banda`` acota su
    estimacion. ``cuantiles`` describe ``V_T`` y es lo unico que puede dar rangos
    de precio: un clasificador por si solo no produce intervalos de precio.
    """

    p_yes: Decimal
    banda: BandaProbabilidad | None
    cuantiles: dict[str, Decimal] = field(default_factory=dict)
    intervalos: tuple[IntervaloPrediccion, ...] = ()
    version_modelo: str = "sin_version"
    version_calibrador: str = "sin_version"

    def __post_init__(self) -> None:
        if not 0 <= self.p_yes <= 1:
            raise ErrorProbabilidad(f"p_yes fuera de [0,1]: {self.p_yes}")
        if self.banda is not None:
            # La banda acota la estimacion, asi que debe contener el valor
            # central; si no, el calibrador y el remuestreo no son coherentes.
            if not self.banda.inferior <= self.p_yes <= self.banda.superior:
                raise ErrorProbabilidad(
                    f"p_yes {self.p_yes} fuera de su banda "
                    f"[{self.banda.inferior}, {self.banda.superior}]"
                )

    @property
    def p_no(self) -> Decimal:
        """Complemento exacto. Para resultados binarios ordinarios."""
        return Decimal(1) - self.p_yes

    def p_central(self, lado: Lado) -> Decimal:
        return self.p_yes if lado is Lado.YES else self.p_no

    def p_robust(self, lado: Lado) -> Decimal | None:
        """Probabilidad conservadora del lado pedido.

        * YES: ``L`` (cota inferior de ``p_yes``).
        * NO:  ``1 - U``, **no** ``1 - L``.

        Devuelve ``None`` si no hay banda defendible: en ese caso el tamano
        monetario queda desactivado en lugar de inventar una cota.
        """
        if self.banda is None or not self.banda.defendible:
            return None
        if lado is Lado.YES:
            return self.banda.inferior
        return Decimal(1) - self.banda.superior

    @property
    def degenerada(self) -> bool:
        """True si la prediccion afirma certeza, lo que nunca es defendible.

        Una probabilidad de exactamente 0 o 1 para un evento futuro de mercado
        no es una estimacion, es un sintoma: casi siempre significa que la
        volatilidad esta subestimada o que el horizonte esta fuera del dominio
        en el que el modelo se valido. Lo mismo vale para una banda de ancho
        cero.
        """
        if self.p_yes in (Decimal(0), Decimal(1)):
            return True
        return self.banda is not None and self.banda.ancho == 0

    @property
    def banda_p_no(self) -> tuple[Decimal, Decimal] | None:
        """Banda de ``p_no``, que es ``[1 - U, 1 - L]``."""
        if self.banda is None:
            return None
        return (Decimal(1) - self.banda.superior, Decimal(1) - self.banda.inferior)

    def motivos_no_usable(
        self, p_maxima: Decimal = Decimal("0.995")
    ) -> tuple[str, ...]:
        """Motivos para no usar esta prediccion al decidir.

        ``p_maxima`` acota cuanta certeza se admite. Por encima de ese valor la
        prediccion se trata como fuera de dominio en lugar de como una
        oportunidad: un mercado liquido que cotiza por debajo de nuestra
        probabilidad extrema es, casi siempre, senal de que el modelo esta mal.
        """
        motivos: list[str] = []
        if self.degenerada:
            motivos.append(
                f"prediccion degenerada (p_yes={self.p_yes}, "
                f"ancho de banda={self.banda.ancho if self.banda else 'sin banda'})"
            )
        extremo = max(self.p_yes, self.p_no)
        if not self.degenerada and extremo > p_maxima:
            motivos.append(
                f"certeza excesiva: max(p_yes, p_no)={extremo} > {p_maxima}"
            )
        if self.banda is None:
            motivos.append("sin banda de incertidumbre")
        elif not self.banda.defendible:
            motivos.append("banda no defendible")
        return tuple(motivos)

    def resumen(self) -> dict:
        """Objeto plano para el registro de la decision."""
        datos = {
            "p_yes": str(self.p_yes),
            "p_no": str(self.p_no),
            "version_modelo": self.version_modelo,
            "version_calibrador": self.version_calibrador,
            "cuantiles": {k: str(v) for k, v in self.cuantiles.items()},
            "intervalos": [
                {
                    "nivel": str(i.nivel),
                    "inferior": str(i.inferior),
                    "superior": str(i.superior),
                }
                for i in self.intervalos
            ],
        }
        if self.banda is None:
            datos["banda"] = None
            datos["p_robust_yes"] = None
            datos["p_robust_no"] = None
        else:
            datos["banda"] = {
                "inferior": str(self.banda.inferior),
                "superior": str(self.banda.superior),
                "metodo": self.banda.metodo,
                "supuestos": self.banda.supuestos,
                "defendible": self.banda.defendible,
                "cobertura_empirica": (
                    str(self.banda.cobertura_empirica)
                    if self.banda.cobertura_empirica is not None
                    else None
                ),
            }
            robust_yes = self.p_robust(Lado.YES)
            robust_no = self.p_robust(Lado.NO)
            datos["p_robust_yes"] = None if robust_yes is None else str(robust_yes)
            datos["p_robust_no"] = None if robust_no is None else str(robust_no)
        return datos
