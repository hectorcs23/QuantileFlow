"""Reconstruccion de la serie del indice de liquidacion desde el propio exchange.

El contrato liquida con el BRTI de CF Benchmarks, y CF Benchmarks exige clave
para su API publica. Pero **cada mercado liquidado contiene dos observaciones
exactas del indice**:

* ``floor_strike`` = promedio de 60 s que cierra en ``open_time``
* ``expiration_value`` = promedio de 60 s que cierra en ``close_time``

Y la cadena esta encadenada: el ``expiration_value`` de un contrato es el
``floor_strike`` del siguiente (verificado en 49/49 pares). De modo que la serie
de mercados liquidados de ``KXBTC15M`` **es** una serie del indice de
liquidacion, muestreada cada 15 minutos, con los valores exactos que el exchange
uso para resolver.

Lo que esto da y lo que no:

* **Da** la serie real del objetivo (``V_T``) con sus etiquetas, sin depender de
  ningun sustituto. Es lo que la Fase C necesita.
* **No da** alta frecuencia: son dos puntos cada 15 minutos, no un tick. Para la
  volatilidad intra-horizonte sigue hace falta spot, con su base.

Cada punto se marca con el instante en que **cierra** su ventana de promedio, no
con el instante en que lo leimos: es un promedio de los 60 s anteriores a esa
marca.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Iterator

from .tiempo import desde_iso, exigir_utc


class ErrorIndice(ValueError):
    """Serie del indice no reconstruible."""


@dataclass(frozen=True)
class PuntoIndice:
    """Un valor del indice y la ventana que lo produjo.

    ``cierra_en`` es el final de la ventana de promedio. ``procedencia`` dice de
    que campo salio, porque los dos campos tienen fiabilidad distinta:
    ``expiration_value`` es el valor con el que el exchange liquido, mientras
    ``floor_strike`` es el umbral que publico al abrir.
    """

    cierra_en: dt.datetime
    valor: Decimal
    ventana_s: int
    contrato: str
    procedencia: str

    def __post_init__(self) -> None:
        exigir_utc(self.cierra_en, "cierra_en")
        if self.valor <= 0:
            raise ErrorIndice(f"valor no positivo: {self.valor}")
        if self.procedencia not in ("expiration_value", "floor_strike"):
            raise ErrorIndice(f"procedencia desconocida: {self.procedencia!r}")


def _decimal(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return None


def puntos_desde_mercados(
    mercados: Iterable[dict], ventana_s: int = 60
) -> Iterator[PuntoIndice]:
    """Extrae los puntos del indice de una coleccion de mercados.

    De cada mercado salen hasta dos puntos. Un mercado sin resultado aporta solo
    su ``floor_strike``: su ``expiration_value`` aun no existe y no se inventa.
    """
    for mercado in mercados:
        contrato = mercado.get("ticker") or ""
        apertura = mercado.get("open_time")
        cierre = mercado.get("close_time")

        umbral = _decimal(mercado.get("floor_strike"))
        if umbral is not None and apertura:
            try:
                yield PuntoIndice(
                    cierra_en=desde_iso(apertura, "open_time"),
                    valor=umbral,
                    ventana_s=ventana_s,
                    contrato=contrato,
                    procedencia="floor_strike",
                )
            except Exception:  # noqa: BLE001 - un mercado ilegible no corta la serie
                pass

        liquidacion = _decimal(mercado.get("expiration_value"))
        if liquidacion is not None and cierre:
            try:
                yield PuntoIndice(
                    cierra_en=desde_iso(cierre, "close_time"),
                    valor=liquidacion,
                    ventana_s=ventana_s,
                    contrato=contrato,
                    procedencia="expiration_value",
                )
            except Exception:  # noqa: BLE001
                pass


@dataclass(frozen=True)
class SerieIndice:
    """Serie del indice, deduplicada y ordenada, con su auditoria."""

    puntos: tuple[PuntoIndice, ...]
    conflictos: tuple[dict, ...]
    duplicados_coherentes: int

    @property
    def n(self) -> int:
        return len(self.puntos)

    @property
    def desde(self) -> dt.datetime | None:
        return self.puntos[0].cierra_en if self.puntos else None

    @property
    def hasta(self) -> dt.datetime | None:
        return self.puntos[-1].cierra_en if self.puntos else None

    def valor_en(self, momento: dt.datetime) -> PuntoIndice | None:
        """Ultimo punto cuya ventana ya habia cerrado en ``momento``.

        Union hacia atras: un promedio que cierra despues del momento de
        decision no estaba disponible.
        """
        instante = exigir_utc(momento)
        candidato = None
        for punto in self.puntos:
            if punto.cierra_en <= instante:
                candidato = punto
            else:
                break
        return candidato

    def huecos(self, separacion_esperada_s: float = 900.0) -> tuple[tuple[dt.datetime, dt.datetime], ...]:
        """Intervalos donde faltan mercados.

        La serie deberia tener un punto cada 15 minutos (y dos por contrato que
        coinciden en los bordes). Un hueco mayor significa mercados no
        capturados, no un mercado inexistente.
        """
        salida = []
        for previo, siguiente in zip(self.puntos, self.puntos[1:]):
            separacion = (siguiente.cierra_en - previo.cierra_en).total_seconds()
            if separacion > separacion_esperada_s:
                salida.append((previo.cierra_en, siguiente.cierra_en))
        return tuple(salida)

    def resumen(self) -> dict:
        from .tiempo import a_iso

        return {
            "puntos": self.n,
            "desde": a_iso(self.desde) if self.desde else None,
            "hasta": a_iso(self.hasta) if self.hasta else None,
            "duplicados_coherentes": self.duplicados_coherentes,
            "conflictos": len(self.conflictos),
            "huecos": len(self.huecos()),
            "nota": (
                "serie del indice de liquidacion reconstruida desde los mercados "
                "liquidados; dos puntos por contrato, muestreada cada 15 minutos"
            ),
        }


def construir_serie(
    mercados: Iterable[dict], ventana_s: int = 60
) -> SerieIndice:
    """Construye la serie deduplicando los bordes compartidos entre contratos.

    El ``expiration_value`` de un contrato y el ``floor_strike`` del siguiente
    describen **la misma ventana**, asi que coinciden en el mismo instante. Eso
    es una comprobacion gratuita: si los dos valores difieren, la cadena esta
    rota y se registra como conflicto en lugar de elegir uno.

    Cuando coinciden se conserva ``expiration_value``, que es el valor con el que
    el exchange liquido de verdad.
    """
    por_instante: dict[dt.datetime, PuntoIndice] = {}
    conflictos: list[dict] = []
    coherentes = 0

    for punto in puntos_desde_mercados(mercados, ventana_s):
        previo = por_instante.get(punto.cierra_en)
        if previo is None:
            por_instante[punto.cierra_en] = punto
            continue
        if previo.valor == punto.valor:
            coherentes += 1
            # Preferir el valor de liquidacion sobre el umbral publicado.
            if punto.procedencia == "expiration_value":
                por_instante[punto.cierra_en] = punto
            continue
        from .tiempo import a_iso

        conflictos.append(
            {
                "cierra_en": a_iso(punto.cierra_en),
                "valor_a": str(previo.valor),
                "procedencia_a": previo.procedencia,
                "contrato_a": previo.contrato,
                "valor_b": str(punto.valor),
                "procedencia_b": punto.procedencia,
                "contrato_b": punto.contrato,
            }
        )
        if punto.procedencia == "expiration_value":
            por_instante[punto.cierra_en] = punto

    ordenados = tuple(por_instante[k] for k in sorted(por_instante))
    return SerieIndice(
        puntos=ordenados,
        conflictos=tuple(conflictos),
        duplicados_coherentes=coherentes,
    )


def retornos_del_indice(serie: SerieIndice) -> list[tuple[dt.datetime, float]]:
    """Retornos logaritmicos entre puntos consecutivos del indice.

    Son retornos del **objetivo**, a paso de 15 minutos. Util para caracterizar
    el proceso que realmente decide la liquidacion, no un sustituto de el.
    """
    import math

    salida = []
    for previo, siguiente in zip(serie.puntos, serie.puntos[1:]):
        if previo.valor > 0 and siguiente.valor > 0:
            salida.append(
                (
                    siguiente.cierra_en,
                    math.log(float(siguiente.valor) / float(previo.valor)),
                )
            )
    return salida


def volatilidad_por_segundo(
    serie: SerieIndice,
    hasta: dt.datetime | None = None,
    ventana_dias: float | None = None,
    minimo_retornos: int = 100,
) -> tuple[float | None, dict]:
    """Volatilidad del **objetivo**, estimada sobre la serie del indice.

    Esta es la estimacion correcta para este problema, y sustituye a extrapolar
    desde una ventana corta de spot. Medido sobre 17 dias de serie, la ventana
    corta de spot subestimaba la volatilidad del horizonte unas 2.8 veces, lo que
    producia probabilidades extremas y una ventaja aparente que no existia.

    ``hasta`` recorta la serie a lo disponible en el momento de decision: la
    volatilidad se estima **solo con pasado**, nunca con la ventana que se esta
    prediciendo. Omitirlo usa toda la serie, lo que solo es admisible fuera de
    una evaluacion.

    Devuelve ``(sigma_por_segundo, detalle)``; ``None`` si no hay retornos
    suficientes, en lugar de un numero que el modelo tomaria por bueno.
    """
    import math
    import statistics

    puntos = serie.puntos
    if hasta is not None:
        limite = exigir_utc(hasta)
        puntos = tuple(p for p in puntos if p.cierra_en <= limite)
    if ventana_dias is not None and puntos:
        inicio = puntos[-1].cierra_en - dt.timedelta(days=ventana_dias)
        puntos = tuple(p for p in puntos if p.cierra_en >= inicio)

    detalle: dict = {
        "puntos_usados": len(puntos),
        "ventana_dias": ventana_dias,
        "solo_pasado_hasta": None if hasta is None else exigir_utc(hasta).isoformat(),
    }

    if len(puntos) < minimo_retornos + 1:
        detalle["motivo"] = (
            f"solo {max(0, len(puntos) - 1)} retornos (< {minimo_retornos})"
        )
        return None, detalle

    retornos: list[float] = []
    pasos_s: list[float] = []
    for previo, siguiente in zip(puntos, puntos[1:]):
        paso = (siguiente.cierra_en - previo.cierra_en).total_seconds()
        if paso <= 0 or previo.valor <= 0 or siguiente.valor <= 0:
            continue
        retornos.append(math.log(float(siguiente.valor) / float(previo.valor)))
        pasos_s.append(paso)

    if len(retornos) < minimo_retornos:
        detalle["motivo"] = f"solo {len(retornos)} retornos utiles"
        return None, detalle

    # Varianza por segundo: suma de retornos al cuadrado sobre el tiempo total
    # cubierto. Asi un paso irregular (por un hueco) no distorsiona la escala.
    total_s = sum(pasos_s)
    if total_s <= 0:
        detalle["motivo"] = "tiempo total no positivo"
        return None, detalle
    varianza_por_s = sum(r * r for r in retornos) / total_s
    sigma = math.sqrt(varianza_por_s)

    paso_tipico = statistics.median(pasos_s)
    detalle.update(
        {
            "retornos": len(retornos),
            "paso_tipico_s": paso_tipico,
            "sigma_por_segundo": sigma,
            "sigma_en_paso_tipico": sigma * math.sqrt(paso_tipico),
            "desviacion_muestral_del_paso": statistics.pstdev(retornos),
            "media_retornos": statistics.fmean(retornos),
            "nota": (
                "volatilidad del indice que liquida, no de un sustituto; "
                "estimada solo con puntos anteriores al momento indicado"
            ),
        }
    )
    return sigma, detalle


def cargar_serie(ruta) -> SerieIndice:
    """Carga una serie escrita por ``scripts/reconstruir_indice.py``."""
    import json
    from pathlib import Path

    archivo = Path(ruta)
    if not archivo.exists():
        raise ErrorIndice(f"no existe la serie: {archivo}")
    puntos = []
    for numero, linea in enumerate(
        archivo.read_text(encoding="utf-8").splitlines(), start=1
    ):
        linea = linea.strip()
        if not linea:
            continue
        try:
            crudo = json.loads(linea)
            puntos.append(
                PuntoIndice(
                    cierra_en=desde_iso(crudo["cierra_en"], "cierra_en"),
                    valor=Decimal(str(crudo["valor"])),
                    ventana_s=int(crudo.get("ventana_s", 60)),
                    contrato=crudo.get("contrato", ""),
                    procedencia=crudo.get("procedencia", "expiration_value"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise ErrorIndice(f"linea {numero} ilegible en {archivo}: {exc}") from exc
    return SerieIndice(
        puntos=tuple(sorted(puntos, key=lambda p: p.cierra_en)),
        conflictos=(),
        duplicados_coherentes=0,
    )
