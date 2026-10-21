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
from btclab.indice import cargar_serie, retornos_del_indice, volatilidad_por_segundo
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
    analizador.add_argument(
        "--serie-indice", default="datos/indice/brti.jsonl",
        help="serie del indice de liquidacion (scripts/reconstruir_indice.py)",
    )
    analizador.add_argument(
        "--brti", default="",
        help=(
            "valor del BRTI en vivo, si se dispone de el. El conector que lo "
            "expone no es accesible desde este script, asi que se pasa a mano "
            "y queda registrado como tal."
        ),
    )
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

    # Paso 4/5: volatilidad del OBJETIVO, no de un sustituto.
    #
    # La volatilidad se estima sobre la serie del indice que liquida, recortada a
    # lo disponible en el momento de decision. Medido sobre 17 dias de serie, una
    # ventana corta de spot subestimaba esta volatilidad unas 2.8 veces, lo que
    # producia probabilidades extremas y una ventaja aparente inexistente.
    volatilidad = None
    fuente_volatilidad = "sin estimar"
    detalle_volatilidad: dict = {}
    ventana_volatilidad_s = 0.0
    serie_indice = None

    ruta_serie = Path(argumentos.serie_indice)
    if ruta_serie.exists():
        try:
            serie_indice = cargar_serie(ruta_serie)
            volatilidad, detalle_volatilidad = volatilidad_por_segundo(
                serie_indice, hasta=decidido_en
            )
            if volatilidad:
                fuente_volatilidad = (
                    f"serie del indice ({detalle_volatilidad['retornos']} retornos "
                    f"a paso de {detalle_volatilidad['paso_tipico_s']:.0f}s)"
                )
                primero = serie_indice.puntos[0].cierra_en
                ultimo = (serie_indice.valor_en(decidido_en) or serie_indice.puntos[-1])
                ventana_volatilidad_s = (ultimo.cierra_en - primero).total_seconds()
        except Exception as exc:  # noqa: BLE001
            print(f"aviso: no se pudo usar la serie del indice: {exc}")

    if volatilidad is None:
        # Repliegue: ventana corta de spot. Queda marcado, porque es la via que
        # fabrica ventajas y el control de dominio debe rechazarla.
        volatilidad = volatilidad_realizada(precios, marcas, 600.0, minimo=5)
        fuente_volatilidad = "ventana corta de spot (REPLIEGUE, subestima)"
        ventana_volatilidad_s = marcas[-1] - marcas[0]
        if volatilidad is None or volatilidad <= 0:
            print(
                "sin volatilidad estimable: reconstruya la serie del indice con "
                "scripts/reconstruir_indice.py"
            )
            return 1

    # Nivel actual del indice. El indice solo publica un valor cada 15 minutos,
    # asi que hay tres opciones, en orden de preferencia declarado:
    #   1. una lectura en vivo del BRTI, si se proporciona;
    #   2. el ultimo punto de la serie, con su antiguedad declarada;
    #   3. spot, que arrastra una base de orden 20-40 USD frente al indice.
    nivel_indice = None
    fuente_nivel = ""
    antiguedad_nivel_s = None
    if argumentos.brti:
        nivel_indice = float(argumentos.brti)
        fuente_nivel = "BRTI en vivo (pasado a mano desde el conector)"
        antiguedad_nivel_s = 0.0
    elif serie_indice is not None:
        punto = serie_indice.valor_en(decidido_en)
        if punto is not None:
            nivel_indice = float(punto.valor)
            antiguedad_nivel_s = (decidido_en - punto.cierra_en).total_seconds()
            fuente_nivel = (
                f"ultimo punto del indice ({antiguedad_nivel_s:.0f}s de antiguedad)"
            )
    if nivel_indice is None:
        nivel_indice = precios[-1]
        fuente_nivel = "spot (sustituto, con base frente al indice)"
        antiguedad_nivel_s = decidido_en.timestamp() - marcas[-1]

    # El nivel conocido del indice puede ser antiguo (el indice publica cada 15
    # minutos). Desde ese ancla hasta el cierre de la ventana de liquidacion hay
    # dos tramos de difusion: el ya ocurrido pero no observado, y el que falta.
    # El tiempo efectivo es la suma; tratar el ancla como si fuera de ahora
    # mismo subestima la dispersion justo cuando el ancla esta mas vieja.
    tiempo_efectivo = tiempo_restante + max(0.0, antiguedad_nivel_s or 0.0)

    modelo_subyacente = ModeloSubyacente(trayectorias=argumentos.trayectorias)
    simulacion = modelo_subyacente.simular(
        spot=nivel_indice,
        volatilidad_s=volatilidad,
        tiempo_restante_s=tiempo_efectivo,
        ventana_promedio_s=float(ficha.regla.ventana_promedio_s),
        regla=ficha.regla,
    )

    referencia, detalle_mercado = ReferenciaMercado(
        spread_maximo_mils=60
    ).probabilidad(libro)

    # Paso 5: banda por remuestreo de bloques.
    #
    # Se remuestrean los retornos del **indice**, que es el proceso que decide la
    # liquidacion, y solo los anteriores al momento de decision. Remuestrear en
    # su lugar un punado de retornos de spot daba una banda degenerada [0, 1],
    # que el control de defendibilidad rechazaba con razon.
    retornos: list[float] = []
    paso_retornos_s = float(argumentos.periodo_spot)
    if serie_indice is not None:
        from dataclasses import replace as _replace

        pasados = tuple(
            p for p in serie_indice.puntos if p.cierra_en <= decidido_en
        )
        recortada = _replace(serie_indice, puntos=pasados)
        pares = retornos_del_indice(recortada)
        if len(pares) >= 50:
            retornos = [r for _, r in pares]
            paso_retornos_s = detalle_volatilidad.get("paso_tipico_s") or 900.0

    if not retornos:
        # Repliegue explicito: spot. Queda marcado por el control de dominio.
        retornos = [
            math.log(precios[i] / precios[i - 1]) for i in range(1, len(precios))
        ]
        paso_retornos_s = float(argumentos.periodo_spot)

    bloque = longitud_bloque_sugerida(retornos) if len(retornos) >= 8 else 1

    def reajustar(indices) -> float | None:
        muestra = [retornos[i] for i in indices if 0 <= i < len(retornos)]
        if len(muestra) < 3:
            return None
        import numpy as np

        # Varianza por segundo desde la muestra remuestreada, usando el paso
        # real de esos retornos.
        sigma_paso = float(np.sqrt(np.mean(np.square(muestra))))
        if sigma_paso <= 0:
            return None
        sigma_s = sigma_paso / math.sqrt(paso_retornos_s)
        return modelo_subyacente.simular(
            spot=nivel_indice,
            volatilidad_s=sigma_s,
            tiempo_restante_s=tiempo_efectivo,
            ventana_promedio_s=float(ficha.regla.ventana_promedio_s),
            regla=ficha.regla,
        ).p_yes

    banda = BandaBootstrapBloques(remuestreos=60, nivel=0.90).estimar(
        n_entrenamiento=len(retornos),
        longitud_bloque=max(1, bloque),
        ajustar_y_predecir=reajustar,
        p_central=simulacion.p_yes,
    )
    print(
        f"banda: remuestreo de {len(retornos)} retornos "
        f"(paso {paso_retornos_s:.0f}s, bloque {max(1, bloque)})",
        flush=True,
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
    ventana_observada_s = ventana_volatilidad_s
    observaciones_volatilidad = detalle_volatilidad.get("retornos", len(precios))
    motivos_calidad = (
        libro.calidad(decidido_en, antiguedad_max_s=3.0)
        + motivos_fuera_de_dominio(
            ventana_observada_s=ventana_observada_s,
            tiempo_restante_s=tiempo_restante,
            observaciones=observaciones_volatilidad,
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
    print(f"volatilidad: {fuente_volatilidad} -> sigma={volatilidad:.4e} /s")
    if detalle_volatilidad.get("sigma_en_paso_tipico"):
        print(
            f"  equivale a {detalle_volatilidad['sigma_en_paso_tipico']*100:.3f} % "
            f"en {detalle_volatilidad['paso_tipico_s']:.0f}s"
        )
    print(f"nivel del indice: {nivel_indice} via {fuente_nivel}")
    print(
        f"horizonte: {tiempo_restante:.0f}s hasta el cierre de la ventana "
        f"+ {max(0.0, antiguedad_nivel_s or 0.0):.0f}s de difusion no observada "
        f"= {tiempo_efectivo:.0f}s efectivos"
    )
    if precios:
        print(
            f"  base spot-indice: {precios[-1] - nivel_indice:+.2f} USD "
            f"(spot Coinbase {precios[-1]:.2f})"
        )
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
