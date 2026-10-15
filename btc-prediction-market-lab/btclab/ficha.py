"""Construccion de la ficha de contrato desde el mercado en vivo (Paso 1).

Traduce la respuesta del API a una ``FichaContrato`` validada y **declara lo que
no esta verificado**. En particular, la constante del modelo de comisiones no se
pudo confirmar contra fuente primaria desde el entorno auditado, asi que la
ficha sale con ``COSTS_UNVERIFIED`` y el tamano monetario queda en cero hasta
que se adjunte el calendario de comisiones vigente.

Los hechos documentales provienen de
``https://assets.kalshi.com/contract_terms/CRYPTO.pdf`` (consultado el
2026-10-15) y de las reglas del propio mercado (``rules_primary``). Los terminos
del contrato concreto prevalecen sobre la plantilla de clase.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from .contrato import (
    Comisiones,
    ErrorContrato,
    EstadoReglas,
    FichaContrato,
    Fuente,
    Operador,
    ReglaLiquidacion,
    operador_desde_strike_type,
)
from .dinero import PAGO_GANADOR, Rejilla
from .tiempo import desde_iso

#: Fuentes documentales consultadas para esta clase de contrato.
FUENTE_TERMINOS = Fuente(
    url="https://assets.kalshi.com/contract_terms/CRYPTO.pdf",
    consultada_en=dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc),
    nota=(
        "plantilla de clase CRYPTO: define 'at least X' como 'X o mayor', "
        "liquidacion a NO si no hay datos, tick minimo $0.001, valor de "
        "liquidacion $1.00, limite de posicion $25,000 por strike, y que las "
        "revisiones posteriores al vencimiento no se tienen en cuenta"
    ),
)

FUENTE_AYUDA = Fuente(
    url="https://help.kalshi.com/en/articles/13823838-crypto-markets",
    consultada_en=dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc),
    nota=(
        "los mercados de 15 minutos comparan el promedio del minuto previo al "
        "cierre con el promedio del minuto previo a la apertura"
    ),
)

#: Limite de posicion por strike y por miembro, de los terminos del contrato.
LIMITE_POSICION_POR_STRIKE = Decimal("25000")

#: Constante del modelo cuadratico de comisiones. **No verificada** contra
#: fuente primaria desde el entorno auditado (la pagina del calendario devolvio
#: 429 y la ruta de documentacion 404). Se mantiene configurable y la ficha
#: resultante bloquea el tamano monetario.
CONSTANTE_COMISION_SIN_VERIFICAR = Decimal("0.07")


def _decimal(valor, campo: str) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation as exc:
        raise ErrorContrato(f"{campo} ilegible: {valor!r}") from exc


def ficha_desde_mercado(
    mercado: dict,
    serie: dict,
    *,
    comisiones_verificadas: bool = False,
    constante_comision: Decimal | None = None,
    plataforma_visible: str = "Kalshi",
) -> FichaContrato:
    """Arma la ficha de un mercado concreto.

    ``plataforma_visible`` se deja explicito porque un contrato puede verse en
    una plataforma distinta del exchange que lo lista. No se asume que un
    contrato visto en otra plataforma sea este mismo contrato: la equivalencia
    exige verificar contrato, indice, ventana, umbral y reglas, y aun entonces la
    ejecucion y los costes de esa plataforma necesitan evidencia propia.
    """
    faltantes: list[str] = []

    ticker = mercado.get("ticker")
    if not ticker:
        raise ErrorContrato("mercado sin ticker")

    strike_type = mercado.get("strike_type")
    if not strike_type:
        raise ErrorContrato(f"{ticker}: sin strike_type; el empate quedaria indefinido")
    operador = operador_desde_strike_type(strike_type)

    umbral = _decimal(mercado.get("floor_strike"), "floor_strike")
    umbral_superior = _decimal(mercado.get("cap_strike"), "cap_strike")
    if umbral is None:
        faltantes.append("umbral (floor_strike)")

    reglas = (mercado.get("rules_primary") or "").strip()
    if not reglas:
        faltantes.append("texto oficial de reglas (rules_primary)")

    ventana = mercado.get("settlement_timer_seconds")
    # El temporizador de liquidacion no es la ventana de promedio. Para cripto la
    # ventana documentada es de 60 segundos; se usa esa y se deja constancia.
    ventana_promedio_s = 60
    if not reglas or "sixty seconds" not in reglas.lower():
        faltantes.append(
            "confirmacion textual de la ventana de 60s en las reglas del mercado"
        )

    # Un contrato cuyo umbral es el promedio de apertura se reconoce porque las
    # reglas comparan dos promedios.
    umbral_es_apertura = reglas.lower().count("simple average") >= 2

    indice = "CF Benchmarks BRTI" if "BRTI" in reglas else "indice no identificado"
    if indice == "indice no identificado":
        faltantes.append("identificacion del indice en las reglas")

    regla = ReglaLiquidacion(
        indice=indice,
        agencia_fuente="CF Benchmarks",
        ventana_promedio_s=ventana_promedio_s,
        operador=operador,
        umbral=umbral,
        umbral_superior=umbral_superior,
        umbral_es_promedio_apertura=umbral_es_apertura,
        revisiones_posteriores_cuentan=False,
        sin_datos_liquida="no",
        texto_oficial=reglas,
    )

    price_ranges = mercado.get("price_ranges")
    if not price_ranges:
        raise ErrorContrato(f"{ticker}: sin price_ranges; la rejilla seria un supuesto")
    rejilla = Rejilla.desde_price_ranges(
        price_ranges, mercado.get("price_level_structure", "desconocida")
    )

    tipo_comision = serie.get("fee_type") or "desconocida"
    multiplicador = _decimal(serie.get("fee_multiplier"), "fee_multiplier") or Decimal("1")
    if tipo_comision != "quadratic":
        faltantes.append(f"modelo de comisiones no soportado: {tipo_comision!r}")
    comisiones = Comisiones(
        tipo=tipo_comision if tipo_comision in ("quadratic", "plana") else "desconocida",
        multiplicador=multiplicador,
        constante=(
            constante_comision
            if constante_comision is not None
            else CONSTANTE_COMISION_SIN_VERIFICAR
        ),
        verificada=comisiones_verificadas,
        fuente=None,
        nota=(
            "estructura cuadratica verificada desde el API (fee_type, "
            "fee_multiplier); constante pendiente de fuente primaria"
            if not comisiones_verificadas
            else "verificada por el usuario contra el calendario vigente"
        ),
    )
    if not comisiones_verificadas:
        faltantes.append("constante del calendario de comisiones vigente")

    notional = _decimal(mercado.get("notional_value_dollars"), "notional_value_dollars")
    pago = notional if notional is not None else PAGO_GANADOR

    estado = (
        EstadoReglas.VERIFICADO
        if not faltantes
        else (
            EstadoReglas.COSTS_UNVERIFIED
            if faltantes == ["constante del calendario de comisiones vigente"]
            else EstadoReglas.RULES_UNVERIFIED
        )
    )

    return FichaContrato(
        plataforma_visible=plataforma_visible,
        exchange_subyacente="Kalshi",
        serie=serie.get("ticker") or mercado.get("series_ticker") or "",
        evento=mercado.get("event_ticker") or "",
        contrato=ticker,
        moneda="USD",
        apertura=desde_iso(mercado["open_time"], "open_time"),
        fin_negociacion=desde_iso(mercado["close_time"], "close_time"),
        vencimiento_esperado=desde_iso(
            mercado.get("expected_expiration_time") or mercado["close_time"],
            "expected_expiration_time",
        ),
        vencimiento_limite=desde_iso(
            mercado.get("latest_expiration_time")
            or mercado.get("expiration_time")
            or mercado["close_time"],
            "latest_expiration_time",
        ),
        pregunta=(mercado.get("title") or "") + " " + (mercado.get("yes_sub_title") or ""),
        regla=regla,
        rejilla=rejilla,
        pago_ganador=pago,
        cantidad_minima=1,
        fracciones_permitidas=True,
        comisiones=comisiones,
        limite_posicion_por_strike=LIMITE_POSICION_POR_STRIKE,
        estado_reglas=estado,
        version_reglas=(serie.get("last_updated_ts") or "sin_version"),
        fuentes=(FUENTE_TERMINOS, FUENTE_AYUDA),
        reglas_faltantes=tuple(faltantes),
    )
