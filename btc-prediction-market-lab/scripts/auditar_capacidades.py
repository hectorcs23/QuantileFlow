#!/usr/bin/env python3
"""Reaudita en vivo las capacidades declaradas en capabilities.md (Paso 1).

Comprueba, llamando de verdad:

* qué endpoints públicos de Kalshi responden y con qué forma;
* si la estructura complementaria del libro se sostiene ahora mismo;
* la rejilla de precios y el modelo de comisiones que declara el exchange;
* qué fuentes de spot están accesibles y qué latencia traen;
* cuánto histórico de velas devuelve el endpoint de candlesticks.

No registra secretos y no usa credenciales. Escribe un JSON con el resultado
para poder comparar auditorías entre fechas: las capacidades son del entorno y
del momento, no garantías de la plataforma.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btclab.dinero import Rejilla
from btclab.ficha import ficha_desde_mercado
from btclab.kalshi import ClienteKalshi, CuboFichas, ErrorKalshi
from btclab.libro import Lado, Libro
from btclab.spot import Coinbase, ErrorSpot, Kraken
from btclab.tiempo import a_epoch, a_iso, ahora


def intentar(nombre: str, funcion):
    """Ejecuta una comprobación y devuelve su resultado o el fallo, sin abortar."""
    try:
        return {"estado": "ok", "detalle": funcion()}
    except Exception as exc:  # noqa: BLE001 - la auditoría debe completarse siempre
        return {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}"[:300]}


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--serie", default="KXBTC15M")
    analizador.add_argument("--salida", default="")
    analizador.add_argument("--fichas-por-segundo", type=float, default=8.0)
    argumentos = analizador.parse_args()

    cliente = ClienteKalshi(
        cubo=CuboFichas(fichas_por_segundo=argumentos.fichas_por_segundo)
    )
    reporte: dict = {
        "auditado_en": a_iso(ahora()),
        "serie": argumentos.serie,
        "base": cliente.base,
        "nota": (
            "capacidades del entorno y del momento de consulta; no son garantías "
            "de la plataforma. Reauditar ante cualquier cambio de entorno."
        ),
    }

    reporte["exchange_status"] = intentar(
        "status", lambda: cliente.estado_exchange().get("exchange_active")
    )

    def leer_serie():
        serie = cliente.serie(argumentos.serie)
        return {
            "ticker": serie.get("ticker"),
            "frecuencia": serie.get("frequency"),
            "fee_type": serie.get("fee_type"),
            "fee_multiplier": serie.get("fee_multiplier"),
            "contract_terms_url": serie.get("contract_terms_url"),
            "last_updated_ts": serie.get("last_updated_ts"),
        }

    reporte["serie_metadatos"] = intentar("serie", leer_serie)

    estado_serie = reporte["serie_metadatos"]
    if estado_serie["estado"] != "ok":
        reporte["conclusion"] = "sin metadatos de serie no se puede auditar el resto"
        _emitir(reporte, argumentos.salida)
        return 1

    serie_cruda = cliente.serie(argumentos.serie)

    def mercado_abierto():
        mercados, _ = cliente.mercados(
            serie=argumentos.serie, estado="open", limite=1
        )
        if not mercados:
            raise ErrorKalshi("no hay mercado abierto en este momento")
        mercado = mercados[0]
        return {
            "ticker": mercado.get("ticker"),
            "strike_type": mercado.get("strike_type"),
            "floor_strike": mercado.get("floor_strike"),
            "open_time": mercado.get("open_time"),
            "close_time": mercado.get("close_time"),
            "price_level_structure": mercado.get("price_level_structure"),
            "price_ranges": mercado.get("price_ranges"),
            "settlement_timer_seconds": mercado.get("settlement_timer_seconds"),
            "reglas_contienen_sixty_seconds": "sixty seconds"
            in (mercado.get("rules_primary") or "").lower(),
            "reglas_comparan_dos_promedios": (
                (mercado.get("rules_primary") or "").lower().count("simple average") >= 2
            ),
        }

    reporte["mercado_abierto"] = intentar("mercado", mercado_abierto)

    # Ficha y rejilla.
    def construir_ficha():
        mercados, _ = cliente.mercados(
            serie=argumentos.serie, estado="open", limite=1
        )
        if not mercados:
            raise ErrorKalshi("sin mercado abierto")
        ficha = ficha_desde_mercado(mercados[0], serie_cruda)
        rejilla: Rejilla = ficha.rejilla
        return {
            "contrato": ficha.contrato,
            "operador": ficha.regla.operador.value,
            "empate_liquida_yes": ficha.regla.operador.empate_liquida_yes,
            "sin_datos_liquida": ficha.regla.sin_datos_liquida,
            "umbral_es_promedio_apertura": ficha.regla.umbral_es_promedio_apertura,
            "estructura_rejilla": rejilla.estructura,
            "tramos_rejilla": [
                {"desde_mils": t.inicio_mils, "hasta_mils": t.fin_mils,
                 "paso_mils": t.paso_mils}
                for t in rejilla.tramos
            ],
            "estado_reglas": ficha.estado_reglas.value,
            "permite_tamano_monetario": ficha.permite_tamano_monetario,
            "motivos_bloqueo": list(ficha.motivos_bloqueo),
            "limite_posicion_por_strike": str(ficha.limite_posicion_por_strike),
            "huella": ficha.huella(),
        }

    reporte["ficha"] = intentar("ficha", construir_ficha)

    # Estructura del libro: control interno y contra la ficha del mercado.
    def auditar_libro():
        mercados, _ = cliente.mercados(
            serie=argumentos.serie, estado="open", limite=1
        )
        if not mercados:
            raise ErrorKalshi("sin mercado abierto")
        mercado = mercados[0]
        ticker = mercado["ticker"]
        observacion = cliente.libro(ticker)
        libro = Libro.desde_payload(
            ticker, observacion.payload["cuerpo"], observacion.received_at
        )
        coherencia = []
        for lado in (Lado.YES, Lado.NO):
            compra = libro.mejor_compra_mils(lado)
            venta = libro.mejor_venta_mils(lado.opuesto)
            coherencia.append(
                {
                    "lado_compra": lado.value,
                    "compra_mils": compra,
                    "venta_opuesta_mils": venta,
                    "suma": (compra + venta) if (compra is not None and venta is not None) else None,
                    "cuadra": (
                        compra + venta == 1000
                        if (compra is not None and venta is not None)
                        else None
                    ),
                }
            )
        barrido = libro.barrer(Lado.YES, Decimal("100"))
        return {
            "niveles_compra_yes": len(libro.compras_yes),
            "niveles_compra_no": len(libro.compras_no),
            "niveles_venta_yes_derivados": len(libro.ventas(Lado.YES)),
            "coherencia_complementaria": coherencia,
            "discrepancias_contra_mercado": list(
                libro.verificar_contra_mercado(mercado)
            ),
            "lectura_discrepancias": (
                "una discrepancia suele ser antigüedad entre dos lecturas HTTP; "
                "la coherencia complementaria la distingue de un error estructural"
            ),
            "barrido_100_yes": {
                "lleno": str(barrido.cantidad_llenada),
                "coste": str(barrido.coste_bruto),
                "niveles_usados": len(barrido.niveles_usados),
            },
            "motivos_calidad": list(libro.calidad(ahora(), antiguedad_max_s=3.0)),
        }

    reporte["libro"] = intentar("libro", auditar_libro)

    # Histórico de velas.
    def auditar_velas():
        mercados, _ = cliente.mercados(
            serie=argumentos.serie, estado="settled", limite=1
        )
        if not mercados:
            raise ErrorKalshi("sin mercados liquidados")
        mercado = mercados[0]
        fin = a_epoch(ahora())
        velas = cliente.velas(
            argumentos.serie, mercado["ticker"], fin - 3600, fin, intervalo_min=1
        )
        campos = sorted(velas[0].keys()) if velas else []
        return {
            "contrato": mercado["ticker"],
            "velas_devueltas": len(velas),
            "campos": campos,
            "tiene_profundidad": any("depth" in c or "size" in c for c in campos),
            "lectura": (
                "candlesticks da top-of-book a 1 minuto (OHLC de yes_bid y "
                "yes_ask) pero NO profundidad: el coste de barrer una cantidad "
                "no se puede reconstruir hacia atras"
            ),
        }

    reporte["historico_velas"] = intentar("velas", auditar_velas)

    # Etiquetas de mercados liquidados.
    def auditar_liquidados():
        mercados, cursor = cliente.mercados(
            serie=argumentos.serie, estado="settled", limite=200
        )
        resultados: dict[str, int] = {}
        for mercado in mercados:
            clave = mercado.get("result") or "sin_resultado"
            resultados[clave] = resultados.get(clave, 0) + 1
        cierres = sorted(m["close_time"] for m in mercados if m.get("close_time"))
        con_valor = sum(1 for m in mercados if m.get("expiration_value"))
        return {
            "devueltos": len(mercados),
            "hay_mas_paginas": bool(cursor),
            "resultados": resultados,
            "con_expiration_value": con_valor,
            "cierre_min": cierres[0] if cierres else None,
            "cierre_max": cierres[-1] if cierres else None,
        }

    reporte["mercados_liquidados"] = intentar("liquidados", auditar_liquidados)

    # Cadena de promedios: expiration_value(n) == floor_strike(n+1).
    def auditar_cadena():
        mercados, _ = cliente.mercados(
            serie=argumentos.serie, estado="settled", limite=50
        )
        ordenados = sorted(
            (m for m in mercados if m.get("close_time")),
            key=lambda m: m["close_time"],
        )
        comprobados = 0
        coinciden = 0
        ejemplos = []
        for previo, siguiente in zip(ordenados, ordenados[1:]):
            valor = previo.get("expiration_value")
            umbral = siguiente.get("floor_strike")
            if valor in (None, "") or umbral in (None, ""):
                continue
            comprobados += 1
            igual = Decimal(str(valor)) == Decimal(str(umbral))
            if igual:
                coinciden += 1
            elif len(ejemplos) < 3:
                ejemplos.append(
                    {
                        "previo": previo["ticker"],
                        "expiration_value": str(valor),
                        "siguiente": siguiente["ticker"],
                        "floor_strike": str(umbral),
                    }
                )
        return {
            "pares_comprobados": comprobados,
            "coinciden": coinciden,
            "fraccion": round(coinciden / comprobados, 4) if comprobados else None,
            "discrepancias_ejemplo": ejemplos,
            "lectura": (
                "el expiration_value de un contrato debe ser el floor_strike del "
                "siguiente: confirma que el umbral es el promedio de apertura"
            ),
        }

    reporte["cadena_de_promedios"] = intentar("cadena", auditar_cadena)

    # Fuentes de spot.
    def auditar_spot():
        salida = {}
        for nombre, fuente in (("coinbase", Coinbase()), ("kraken", Kraken())):
            try:
                observacion = fuente.leer()
                salida[nombre] = {
                    "estado": "ok",
                    "latencia_fuente_s": round(observacion.latencia_s, 3),
                    "event_time": a_iso(observacion.event_time),
                }
            except ErrorSpot as exc:
                salida[nombre] = {"estado": "fallo", "error": str(exc)[:200]}
        salida["indice_brti"] = {
            "estado": "no_verificado",
            "nota": (
                "el contrato liquida con el BRTI de CF Benchmarks y no hay via "
                "publica verificada desde este entorno; las fuentes spot son "
                "sustitutos y la diferencia spot-indice es una variable del modelo"
            ),
        }
        return salida

    reporte["spot"] = intentar("spot", auditar_spot)

    reporte["comisiones"] = {
        "estructura_verificada_desde_api": True,
        "constante_verificada": False,
        "nota": (
            "fee_type y fee_multiplier vienen del API; la constante del "
            "calendario de comisiones no se pudo obtener desde este entorno, "
            "asi que el tamano monetario esta desactivado"
        ),
    }
    reporte["conectores"] = {
        "robinhood": "no existe conector (verificado en conectores instalados y registro)",
        "consecuencia": (
            "ninguna afirmacion sobre coste o ejecucion en Robinhood tiene "
            "evidencia propia en este proyecto"
        ),
    }
    reporte["diagnostico_cliente"] = cliente.diagnostico

    _emitir(reporte, argumentos.salida)
    return 0


def _emitir(reporte: dict, salida: str) -> None:
    texto = json.dumps(reporte, indent=2, ensure_ascii=False)
    if salida:
        destino = Path(salida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + "\n", encoding="utf-8")
        print(f"escrito en {destino}")
    print(texto)


if __name__ == "__main__":
    raise SystemExit(main())
