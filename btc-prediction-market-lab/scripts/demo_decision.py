#!/usr/bin/env python3
"""Cadena completa sobre un mercado en vivo, hasta la pantalla de decision.

Demuestra el recorrido del Paso 1 al Paso 12 con datos reales y **sin emitir
ordenes**. La probabilidad proviene del modelo del subyacente alimentado con
spot reciente; la banda es un remuestreo por bloques sobre esa misma ventana.

Lo que esta demostracion NO es: evidencia de ventaja. El estado del proyecto es
DATA_ONLY y el importe sugerido real es cero por construccion.

Uso:
    python3 scripts/demo_decision.py [--serie KXBTC15M] [--lado yes|no]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btclab import ESTADO_ACTUAL
from btclab.bandas import BandaBootstrapBloques, longitud_bloque_sugerida
from btclab.calibracion import CalibradorSigmoide  # noqa: F401 (documenta la etapa)
from btclab.costes import ModeloComisionCuadratica, elegible, evaluar
from btclab.decision import (
    CalidadDatos,
    ClaseImporte,
    Decision,
    caducidad,
    nuevo_decision_id,
)
from btclab.ficha import ficha_desde_mercado
from btclab.kalshi import ClienteKalshi, CuboFichas
from btclab.libro import Lado, Libro
from btclab.limites import EstadoRiesgo, LimitesRiesgo
from btclab.modelos import ModeloSubyacente, ReferenciaMercado
from btclab.probabilidad import IntervaloPrediccion, Prediccion
from btclab.sizing import dimensionar
from btclab.spot import Coinbase
from btclab.tiempo import ahora
from btclab.variables import motivos_fuera_de_dominio, volatilidad_realizada


def leer_spot(lecturas: int, periodo_s: float) -> tuple[list[float], list[float]]:
    """Serie corta de spot para estimar volatilidad reciente."""
    fuente = Coinbase()
    precios: list[float] = []
    marcas: list[float] = []
    for i in range(lecturas):
        if i:
            time.sleep(periodo_s)
        observacion = fuente.leer()
        precios.append(float(Coinbase.precio(observacion)))
        marcas.append(observacion.received_at.timestamp())
    return precios, marcas


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--serie", default="KXBTC15M")
    analizador.add_argument("--lado", choices=("yes", "no"), default="yes")
    analizador.add_argument("--lecturas-spot", type=int, default=12)
    analizador.add_argument("--periodo-spot", type=float, default=2.0)
    analizador.add_argument("--trayectorias", type=int, default=20000)
    analizador.add_argument("--registro", default="")
    argumentos = analizador.parse_args()

    lado = Lado.YES if argumentos.lado == "yes" else Lado.NO
    cliente = ClienteKalshi(cubo=CuboFichas(fichas_por_segundo=8.0))

    print(f"estado del proyecto: {ESTADO_ACTUAL}")
    print(f"serie: {argumentos.serie}\n")

    # Paso 1: ficha del contrato.
    serie = cliente.serie(argumentos.serie)
    mercados, _ = cliente.mercados(serie=argumentos.serie, estado="open", limite=1)
    if not mercados:
        print("no hay mercado abierto en este momento")
        return 1
    ficha = ficha_desde_mercado(mercados[0], serie)

    # Paso 2: libro y spot, con sus marcas temporales.
    observacion_libro = cliente.libro(ficha.contrato)
    libro = Libro.desde_payload(
        ficha.contrato, observacion_libro.payload["cuerpo"], observacion_libro.received_at
    )
    print("leyendo spot para estimar volatilidad reciente ...", flush=True)
    precios, marcas = leer_spot(argumentos.lecturas_spot, argumentos.periodo_spot)

    decidido_en = ahora()
    tiempo_restante = ficha.tiempo_restante_s(decidido_en)
    if tiempo_restante <= 0:
        print("el contrato ya vencio mientras leiamos datos; reintente")
        return 1

    # Paso 4/5: volatilidad, simulacion y cuantiles de V_T.
    volatilidad = volatilidad_realizada(precios, marcas, 600.0, minimo=5)
    if volatilidad is None or volatilidad <= 0:
        print("sin volatilidad estimable con las lecturas disponibles")
        return 1

    modelo_subyacente = ModeloSubyacente(trayectorias=argumentos.trayectorias)
    simulacion = modelo_subyacente.simular(
        spot=precios[-1],
        volatilidad_s=volatilidad,
        tiempo_restante_s=tiempo_restante,
        ventana_promedio_s=float(ficha.regla.ventana_promedio_s),
        regla=ficha.regla,
    )

    referencia, detalle_mercado = ReferenciaMercado(
        spread_maximo_mils=60
    ).probabilidad(libro)

    # Paso 5: banda por remuestreo de bloques sobre los retornos recientes.
    retornos = [
        math.log(precios[i] / precios[i - 1]) for i in range(1, len(precios))
    ]
    bloque = longitud_bloque_sugerida(retornos) if len(retornos) >= 8 else 1

    def reajustar(indices) -> float | None:
        muestra = [retornos[i] for i in indices if 0 <= i < len(retornos)]
        if len(muestra) < 3:
            return None
        import numpy as np

        sigma = float(np.std(muestra))
        if sigma <= 0:
            return None
        # El paso de los retornos es el periodo de muestreo del spot.
        sigma_s = sigma / math.sqrt(argumentos.periodo_spot)
        return modelo_subyacente.simular(
            spot=precios[-1],
            volatilidad_s=sigma_s,
            tiempo_restante_s=tiempo_restante,
            ventana_promedio_s=float(ficha.regla.ventana_promedio_s),
            regla=ficha.regla,
        ).p_yes

    banda = BandaBootstrapBloques(remuestreos=60, nivel=0.90).estimar(
        n_entrenamiento=len(retornos),
        longitud_bloque=max(1, bloque),
        ajustar_y_predecir=reajustar,
        p_central=simulacion.p_yes,
    )

    prediccion = Prediccion(
        p_yes=Decimal(str(round(simulacion.p_yes, 6))),
        banda=banda,
        cuantiles={
            k: Decimal(str(round(v, 2))) for k, v in simulacion.cuantiles().items()
        },
        intervalos=tuple(
            IntervaloPrediccion(
                nivel=Decimal(str(nivel)),
                inferior=Decimal(str(round(simulacion.intervalo(nivel)[0], 2))),
                superior=Decimal(str(round(simulacion.intervalo(nivel)[1], 2))),
            )
            for nivel in (0.5, 0.8, 0.95)
        ),
        version_modelo=f"subyacente-mc-{argumentos.trayectorias}",
        version_calibrador="sin_calibrar(demo)",
    )

    # Paso 6/7: costes y tamano. Las comisiones NO estan verificadas, asi que la
    # ficha bloquea el importe monetario.
    modelo_comision = ModeloComisionCuadratica(
        constante=ficha.comisiones.constante,
        multiplicador=ficha.comisiones.multiplicador,
        verificada=ficha.comisiones.verificada,
    )
    limites = LimitesRiesgo(
        capital_segregado=Decimal("1000.00"),
        es_capital_ficticio=True,
        presupuesto_configurado=False,
        perdida_maxima_por_operacion=Decimal("25.00"),
        perdida_diaria_maxima=Decimal("50.00"),
        fraccion_kelly=Decimal("0.25"),
        limite_posicion_exchange=ficha.limite_posicion_por_strike,
    )
    estado_riesgo = EstadoRiesgo(
        inicio_zona=decidido_en.replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # La ventana de spot observada es el tramo entre la primera y la ultima
    # lectura. Si el horizonte la excede con holgura, la observacion queda fuera
    # del dominio validado y la decision es no operar.
    ventana_observada_s = marcas[-1] - marcas[0]
    motivos_calidad = (
        libro.calidad(decidido_en, antiguedad_max_s=3.0)
        + motivos_fuera_de_dominio(
            ventana_observada_s=ventana_observada_s,
            tiempo_restante_s=tiempo_restante,
            observaciones=len(precios),
        )
        + prediccion.motivos_no_usable()
    )
    p_robust = prediccion.p_robust(lado)

    propuesta = dimensionar(
        libro, lado, p_robust, modelo_comision, limites, estado_riesgo, decidido_en,
        motivos_previos=motivos_calidad,
        cantidad_maxima_busqueda=Decimal("200"),
        cantidad_minima=Decimal(ficha.cantidad_minima),
    )

    cantidad_muestra = max(propuesta.cantidad_simulada, Decimal("10"))
    evaluacion = evaluar(
        libro, lado, cantidad_muestra, p_robust or prediccion.p_central(lado),
        modelo_comision,
    )
    margen = Decimal("0.02")
    pasa, motivos_senal = elegible(evaluacion, margen, ficha, motivos_calidad)

    valid_until, condiciones = caducidad(decidido_en, 3.0)
    decision = Decision(
        decision_id=nuevo_decision_id(ficha.contrato, decidido_en, "demo-0.1"),
        decidido_en=decidido_en,
        ficha=ficha,
        libro=libro,
        prediccion=prediccion,
        propuesta=propuesta,
        calidad=CalidadDatos(
            antiguedad_libro_s=round(
                (decidido_en - libro.received_at).total_seconds(), 3
            ),
            antiguedad_spot_s=round(decidido_en.timestamp() - marcas[-1], 3),
            huecos_detectados=0,
            secuencias_rotas=0,
            motivos=motivos_calidad,
        ),
        clase_importe=ClaseImporte.FICTICIO,
        valid_until=valid_until,
        version_configuracion="demo-0.1",
        margen_operativo=margen,
        condiciones_invalidez=condiciones,
        coste_evaluado={
            "cantidad_evaluada": cantidad_muestra,
            "A(n)": evaluacion.coste_libro,
            "F(n)": evaluacion.comisiones,
            "C(n)": evaluacion.coste_total,
            "c(n)": evaluacion.coste_unitario,
            "EV(n)": evaluacion.valor_esperado,
            "edge(n)": evaluacion.ventaja,
        },
    )

    print("=" * 78)
    print(decision.pantalla())
    print("=" * 78)
    print(f"\nreferencia de mercado (punto medio YES): {referencia}")
    print(f"  {json.dumps(detalle_mercado, ensure_ascii=False)}")
    print(f"simulacion: {simulacion.fuente_retornos}, drift={simulacion.con_drift}")
    print(f"senal elegible por el filtro economico: {pasa}")
    if motivos_senal:
        for motivo in motivos_senal:
            print(f"  - {motivo}")
    print(f"diagnostico del cliente: {cliente.diagnostico}")

    if argumentos.registro:
        destino = Path(argumentos.registro)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("a", encoding="utf-8") as archivo:
            archivo.write(
                json.dumps(decision.registro(), ensure_ascii=False, sort_keys=True) + "\n"
            )
        print(f"\ndecision registrada en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
