"""Vista por posición del comparador: presupuesto común, cantidades y caja.

Reutiliza el motor y sus validaciones. No cambia la política de comprar la
cantidad entera máxima de una sola serie ni asigna probabilidades a escenarios.
"""

from .comparador import comparar_con_pdf


def comparar_posiciones(contratos, spot, escenarios, presupuesto,
                        escenario_objetivo, **opciones):
    """Compara el PnL neto total con el mismo presupuesto para cada candidato.

    ``ask`` es precio por unidad, no el costo del contrato completo. Se conserva
    el multiplicador del contrato y se reservan ambas comisiones. El interés de
    caja es cero, como en el comparador base. ``opciones`` admite sus parámetros,
    incluidos límite de pérdida y límites de cantidad por liquidez.

    Sensibilidades monetarias locales = cantidad * multiplicador * griega.
    Los escenarios usan repricing completo; no esa aproximación local.
    """
    resultado = comparar_con_pdf(contratos, spot, escenarios, presupuesto,
                                 escenario_objetivo, **opciones)
    posiciones = []
    for f in resultado["contratos"]:
        n, m = f["contratos"], f["multiplicador"]
        sensibilidad = {
            campo: n * m * f["sensibilidad_entrada"][campo]
            for campo in ("delta", "gamma", "vega_por_punto_iv", "theta_por_dia")
        }
        casos = {
            nombre: {
                "pnl_por_contrato": v["pnl"] / n,
                "pnl_posicion": v["pnl"],
                "capital_final_incluyendo_caja": presupuesto + v["pnl"],
                "retorno_presupuesto": v["pnl"] / presupuesto,
                "retorno_capital_reservado": v["pnl"] / f["capital_reservado"],
            }
            for nombre, v in f["escenarios"].items()
        }
        posiciones.append({
            "contrato": f["contrato"], "strike": f["strike"], "dte": f["dte"],
            "es_call": f["es_call"], "cantidad": n, "multiplicador": m,
            "prima_por_contrato": f["ask"] * m,
            "capital_reservado_por_contrato": f["capital_reservado"] / n,
            "prima_total": n * m * f["ask"],
            "desembolso_entrada": f["desembolso"],
            "reserva_comision_cierre": f["reserva_comision_cierre"],
            "capital_reservado": f["capital_reservado"],
            "efectivo_libre": f["efectivo_libre"],
            "uso_presupuesto": f["capital_reservado"] / presupuesto,
            "perdida_maxima_costos_asumidos": f["perdida_maxima_costos_asumidos"],
            "pnl_minimo_escenarios": f["pnl_minimo_escenarios"],
            "sensibilidad_posicion": sensibilidad,
            "escenarios": casos,
        })
    posiciones.sort(key=lambda f: (
        -f["escenarios"][escenario_objetivo]["pnl_posicion"], f["contrato"]))
    mejor = posiciones[0] if posiciones else None
    pnl_mejor = mejor["escenarios"][escenario_objetivo]["pnl_posicion"] if mejor else 0.
    resultado.update(
        posiciones=posiciones,
        comparacion_presupuesto={
            "criterio_principal": "PnL neto total en el escenario objetivo; mismo presupuesto",
            "mejor_en_objetivo_incluyendo_caja": mejor["contrato"] if pnl_mejor > 0 else "efectivo",
            "pnl_mejor_en_objetivo_incluyendo_caja": max(0., pnl_mejor),
            "efectivo": {"capital_inicial": presupuesto, "capital_final": presupuesto, "pnl": 0.},
            "politica_cantidad": "máximo entero por serie dentro de presupuesto, pérdida y límites de cantidad",
            "mezcla_series": False,
            "probabilidades_escenarios": "no estimadas",
            "unidades_sensibilidad": {
                "delta": "USD de posición por USD de cambio en spot",
                "gamma": "USD de posición por USD² de cambio en spot; término cuadrático 0.5*gamma*dS²",
                "vega_por_punto_iv": "USD de posición por punto porcentual de IV",
                "theta_por_dia": "USD de posición por día transcurrido",
            },
        },
    )
    return resultado
