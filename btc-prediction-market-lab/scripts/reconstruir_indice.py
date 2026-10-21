#!/usr/bin/env python3
"""Reconstruye la serie del indice de liquidacion (BRTI) desde Kalshi.

CF Benchmarks exige clave para su API, pero cada mercado liquidado contiene dos
observaciones exactas del indice: ``floor_strike`` (promedio de 60 s que cierra
al abrir) y ``expiration_value`` (el valor con el que el exchange liquido).
Recorriendo los mercados liquidados hacia atras se obtiene la serie real del
objetivo, muestreada cada 15 minutos, con sus etiquetas.

Uso:
    python3 scripts/reconstruir_indice.py --paginas 10 --salida datos/indice/brti.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btclab.indice import construir_serie, retornos_del_indice
from btclab.kalshi import ClienteKalshi, CuboFichas
from btclab.tiempo import a_iso


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--serie", default="KXBTC15M")
    analizador.add_argument("--paginas", type=int, default=10,
                            help="paginas de 200 mercados (96 mercados = 1 dia)")
    analizador.add_argument("--salida", default="datos/indice/brti.jsonl")
    analizador.add_argument("--fichas-por-segundo", type=float, default=8.0)
    argumentos = analizador.parse_args()

    cliente = ClienteKalshi(
        cubo=CuboFichas(fichas_por_segundo=argumentos.fichas_por_segundo)
    )

    print(f"recorriendo mercados liquidados de {argumentos.serie} ...", flush=True)
    mercados = []
    etiquetas = {"yes": 0, "no": 0, "otro": 0}
    for mercado in cliente.mercados_todos(
        serie=argumentos.serie, estado="settled", limite=200,
        paginas_max=argumentos.paginas,
    ):
        mercados.append(mercado)
        resultado = (mercado.get("result") or "").lower()
        etiquetas[resultado if resultado in ("yes", "no") else "otro"] += 1
        if len(mercados) % 400 == 0:
            print(f"  {len(mercados)} mercados ...", flush=True)

    serie = construir_serie(mercados)
    retornos = retornos_del_indice(serie)

    destino = Path(argumentos.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as archivo:
        for punto in serie.puntos:
            archivo.write(
                json.dumps(
                    {
                        "cierra_en": a_iso(punto.cierra_en),
                        "valor": str(punto.valor),
                        "ventana_s": punto.ventana_s,
                        "contrato": punto.contrato,
                        "procedencia": punto.procedencia,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    import statistics

    resumen = serie.resumen()
    resumen["mercados_recorridos"] = len(mercados)
    resumen["etiquetas"] = etiquetas
    resumen["escrito_en"] = str(destino)
    if retornos:
        valores = [r for _, r in retornos]
        resumen["retornos_15min"] = {
            "n": len(valores),
            "desviacion": round(statistics.pstdev(valores), 8),
            "media": round(statistics.fmean(valores), 8),
            "min": round(min(valores), 8),
            "max": round(max(valores), 8),
        }
    resumen["diagnostico_cliente"] = cliente.diagnostico

    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    if serie.conflictos:
        print("\nCONFLICTOS EN LA CADENA (los dos campos describen la misma ventana):")
        for conflicto in serie.conflictos[:5]:
            print(f"  {conflicto}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
