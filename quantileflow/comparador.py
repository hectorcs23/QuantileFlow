"""Rankings condicionales por contrato, con efectivo como alternativa.

El presupuesto se reparte en contratos enteros de una sola serie por candidato.
No optimiza una cartera, no asigna probabilidades físicas ni ejecuta órdenes.
"""
import math

from .escenarios import Escenario, _valor_pde, comparar_contratos


def comparar_con_pdf(contratos, spot, escenarios, presupuesto, escenario_objetivo,
                    *, limite_perdida=None, comision=.65, semispread_salida=.04,
                    tasa=.04, q=0., nodos=801, pasos=800, semiancho=1.5,
                    fuente_cotizaciones="no especificada",
                    tolerancia_fronteras=1e-6, tolerancia_momento_relativo=1e-3,
                    limites_cantidad=None):
    """Tres rankings independientes, usando compra a ask y repricing PDE europeo.

    limite_perdida limita prima y ambas comisiones, no solo pérdida en escenarios.
    Si el mejor mínimo de escenarios <=0, el efectivo gana el ranking robusto.
    La política invierte el máximo entero permitido; no busca tamaño óptimo.
    """
    contratos, escenarios = list(contratos), list(escenarios)
    if not all(math.isfinite(t) and t > 0 for t in (tolerancia_fronteras, tolerancia_momento_relativo)):
        raise ValueError("tolerancias numéricas deben ser positivas y finitas")
    if escenario_objetivo not in {e.nombre for e in escenarios}:
        raise ValueError("escenario objetivo debe estar en la lista")
    if not math.isfinite(presupuesto) or presupuesto <= 0:
        raise ValueError("presupuesto debe ser positivo y finito")
    limite = presupuesto if limite_perdida is None else limite_perdida
    if not math.isfinite(limite) or limite < 0:
        raise ValueError("límite de pérdida debe ser finito y no negativo")
    # Presupuesto positivo para el motor base incluso con límite de riesgo cero:
    # evaluar validación de entradas, luego excluir todos sin comprar.
    resultado = comparar_contratos(contratos, spot, escenarios, min(presupuesto, limite) if limite else presupuesto,
        comision, semispread_salida, tasa, q, pasos=pasos, motor="pde", nodos=nodos, semiancho=semiancho,
        limites_cantidad=limites_cantidad)
    if limite == 0:
        resultado["excluidos"].extend({"contrato": f["contrato"], "motivo": "límite de pérdida cero"}
                                      for f in resultado["contratos"])
        resultado["contratos"] = []
    mapa_contratos, cache = {c.identificador: c for c in contratos}, {}
    filas_aptas = []
    for f in resultado["contratos"]:
        d, v = _valor_pde(mapa_contratos[f["contrato"]], spot, Escenario("entrada", 0, 0),
                          tasa, q, pasos, nodos, semiancho, cache)
        f["sensibilidad_entrada"] = dict(valor_modelo=v.precio, delta=v.delta, gamma=v.gamma,
            vega_por_punto_iv=v.vega_paralela/100, theta_por_dia=-v.sensibilidad_plazo/365,
            masa_fronteras=d.masa_fronteras, error_media_financiera=v.error_media_financiera)
        # Descartar del ranking dominios con momento/fronteras inaceptables.
        diagn = [("entrada", f["sensibilidad_entrada"], spot)] + [
            (e.nombre, f["escenarios"][e.nombre]["diagnostico_pde"], spot*(1+e.retorno_spot)) for e in escenarios]
        alertas = [nombre for nombre, dx, s in diagn if dx and (
            dx["masa_fronteras"] > tolerancia_fronteras or abs(dx["error_media_financiera"])/s > tolerancia_momento_relativo)]
        if alertas:
            resultado["excluidos"].append(dict(contrato=f["contrato"], motivo="dominio o momento numérico insuficiente",
                                               escenarios=alertas))
            continue
        capital = f["desembolso"]+f["reserva_comision_cierre"]
        f["capital_reservado"] = capital
        f["efectivo_sobrante"] = presupuesto-f["desembolso"]
        f["efectivo_libre"] = presupuesto-capital
        f["pnl_objetivo"] = f["escenarios"][escenario_objetivo]["pnl"]
        f["retorno_objetivo"] = f["pnl_objetivo"]/capital
        f["retorno_minimo_escenarios"] = f["pnl_minimo_escenarios"]/capital
        filas_aptas.append(f)
    resultado["contratos"] = filas_aptas
    campos = {"ganancia_objetivo": "pnl_objetivo", "retorno_objetivo": "retorno_objetivo",
              "robustez": "pnl_minimo_escenarios"}
    resultado["rankings"] = {nombre: [f["contrato"] for f in sorted(resultado["contratos"],
        key=lambda f: (-f[campo], f["contrato"]))] for nombre, campo in campos.items()}
    orden = sorted(resultado["contratos"], key=lambda f: (-f["pnl_minimo_escenarios"], f["contrato"]))
    ganador = orden[0] if orden else None
    resultado.update(presupuesto=presupuesto, limite_perdida=limite, escenario_objetivo=escenario_objetivo,
        criterio_robusto="maximizar mínimo PnL de la lista; efectivo tiene PnL cero",
        alternativa_robusta=ganador["contrato"] if ganador and ganador["pnl_minimo_escenarios"] > 0 else "efectivo",
        pnl_robusto_con_efectivo=max(0., ganador["pnl_minimo_escenarios"] if ganador else 0.),
        costos=dict(comision_por_contrato_y_lado=comision, semispread_salida_por_unidad=semispread_salida),
        malla=dict(nodos=nodos, pasos=pasos, semiancho=semiancho),
        fuente_cotizaciones=fuente_cotizaciones,
        tolerancias_numericas=dict(masa_fronteras=tolerancia_fronteras, error_momento_sobre_spot=tolerancia_momento_relativo),
        alcance="europeo, IV plana por contrato; rankings condicionados, no pronóstico")
    return resultado
