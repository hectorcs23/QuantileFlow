"""Valoración condicional de opciones largas; no estima probabilidades de escenarios."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .opciones import binomial_crr, griegas_bs, precio_bs
from .distribucion_pde import resolver_distribucion


@dataclass(frozen=True)
class ContratoEscenario:
    identificador: str
    strike: float
    dte: float  # días naturales hasta liquidación desde el instante de entrada
    es_call: bool
    ejercicio: str
    iv: float
    bid: float
    ask: float
    multiplicador: int = 100

    def __post_init__(self):
        if not isinstance(self.identificador, str) or not self.identificador.strip():
            raise ValueError("identificador no vacío requerido")
        if not isinstance(self.es_call, bool):
            raise ValueError("es_call debe ser booleano")
        nums = (self.strike, self.dte, self.iv, self.bid, self.ask)
        if not all(math.isfinite(v) for v in nums) or min(self.strike, self.dte, self.iv) <= 0:
            raise ValueError("parámetros de contrato no finitos o no positivos")
        if self.bid < 0 or self.ask <= 0 or self.bid > self.ask:
            raise ValueError("cotización inválida")
        if self.ejercicio not in ("europeo", "americano"):
            raise ValueError("ejercicio desconocido")
        if isinstance(self.multiplicador, bool) or not isinstance(self.multiplicador, int) or self.multiplicador <= 0:
            raise ValueError("multiplicador debe ser un entero positivo")


@dataclass(frozen=True)
class Escenario:
    nombre: str
    dias: float
    retorno_spot: float  # retorno acumulado al momento de salida, no anualizado
    cambio_iv: float = 0  # absoluto: -.05 significa 25% -> 20%, cinco puntos de IV

    def __post_init__(self):
        if not isinstance(self.nombre, str) or not self.nombre.strip():
            raise ValueError("nombre de escenario no vacío requerido")
        if not all(math.isfinite(v) for v in (self.dias, self.retorno_spot, self.cambio_iv)):
            raise ValueError("escenario no finito")
        if self.dias < 0 or self.retorno_spot <= -1:
            raise ValueError("plazo negativo o spot no positivo")


def _valor_pde(contrato, spot, escenario, tasa, q, pasos, nodos, semiancho, cache):
    restante = contrato.dte-escenario.dias
    sigma = contrato.iv+escenario.cambio_iv
    if sigma <= 0 or not math.isfinite(sigma):
        raise ValueError("volatilidad del escenario no positiva")
    s = spot*(1+escenario.retorno_spot)
    clave = (s, restante, sigma)
    if clave not in cache:
        cache[clave] = resolver_distribucion(s, restante/365, tasa, q, sigma,
                                            nodos=nodos, pasos=pasos, semiancho=semiancho)
    d = cache[clave]
    return d, d.valor_europeo(contrato.strike, contrato.es_call)


def _validar_motor(motor, contratos, dividendos):
    if motor not in ("clasico", "pde"):
        raise ValueError("motor debe ser clasico o pde")
    if motor == "pde" and (dividendos or any(c.ejercicio != "europeo" for c in contratos)):
        raise ValueError("PDE solo admite ejercicio europeo y q continuo, sin dividendos en efectivo")


def valor_en_escenario(contrato, spot, escenario, tasa=.04, q=0., dividendos=(), pasos=500,
                      *, motor="clasico", nodos=801, semiancho=1.5):
    """Reprecio completo, con dividendos en días desde la entrada y salida antes/igual al vencimiento.

    No se puede usar el precio final posterior al vencimiento para valorar una
    opción ya vencida: haría falta el precio/path en su fecha de liquidación.
    """
    if not math.isfinite(spot) or spot <= 0 or not all(math.isfinite(v) for v in (tasa, q)):
        raise ValueError("referencia inválida")
    if escenario.dias > contrato.dte:
        raise ValueError("el escenario ocurre después del vencimiento")
    dividendos = tuple(dividendos)
    _validar_motor(motor, [contrato], dividendos)
    if any(not math.isfinite(d) or not math.isfinite(m) or m < 0 for d, m in dividendos):
        raise ValueError("dividendos inválidos")
    S = spot * (1 + escenario.retorno_spot)
    restante = contrato.dte - escenario.dias
    if restante == 0:
        return max(S - contrato.strike, 0) if contrato.es_call else max(contrato.strike - S, 0)
    if motor == "pde":
        return _valor_pde(contrato, spot, escenario, tasa, q, pasos, nodos, semiancho, {})[1].precio
    sigma = contrato.iv + escenario.cambio_iv
    if sigma <= 0 or not math.isfinite(sigma):
        raise ValueError("volatilidad del escenario no positiva")
    divs = tuple(((d-escenario.dias)/365, m) for d, m in dividendos
                 if escenario.dias < d <= contrato.dte)
    T = restante / 365
    if contrato.ejercicio == "europeo" and not divs:
        return float(precio_bs(S, contrato.strike, T, tasa, q, sigma, contrato.es_call))
    if isinstance(pasos, bool) or not isinstance(pasos, int) or pasos < 2:
        raise ValueError("pasos del árbol inválidos")
    u = math.exp(sigma * math.sqrt(T/pasos))
    p = (math.exp((tasa-q)*T/pasos)-1/u)/(u-1/u)
    if not 0 <= p <= 1 or S <= sum(m*math.exp(-tasa*t) for t, m in divs):
        raise ValueError("árbol fuera de dominio; revisar pasos/volatilidad/dividendos")
    return binomial_crr(S, contrato.strike, T, tasa, sigma, contrato.es_call, q, divs,
                        pasos, americana=contrato.ejercicio == "americano")


def sensibilidad_europea(spot, strike, dte, iv, tasa=.04, q=0., es_call=True):
    """Sensibilidad local BS: delta por $1, gamma por $1², vega por punto de IV y theta por día.

    Ilustración con rendimiento continuo; no representa griegas de una opción
    americana con dividendos discretos. Para cambios grandes, repricing.
    """
    c = ContratoEscenario("sensibilidad", strike, dte, es_call, "europeo", iv, 0., 1.)
    inicial = valor_en_escenario(c, spot, Escenario("hoy", 0, 0), tasa, q)
    delta, gamma, vega = griegas_bs(spot, strike, dte/365, tasa, q, iv, es_call)
    paso = min(1e-3, dte/2)
    futuro = valor_en_escenario(c, spot, Escenario("paso", paso, 0), tasa, q)
    return {"valor": inicial, "delta": float(delta), "gamma": float(gamma),
            "vega_por_punto_iv": float(vega)/100, "theta_por_dia": (futuro-inicial)/paso}


def comparar_contratos(contratos, spot, escenarios, presupuesto, comision=.65,
                       semispread_salida=.04, tasa=.04, q=0., dividendos=(), pasos=500,
                       *, motor="clasico", nodos=801, semiancho=1.5):
    """Compra a ask, contratos enteros; salida teórica menos semispread asumido.

    Presenta PnL condicional y peor caso de la lista, sin inventar probabilidades.
    El peor caso de la lista no es la pérdida máxima: en opciones largas puede
    perderse todo el desembolso de entrada. No ejecuta órdenes.
    """
    escenarios = list(escenarios)
    contratos, dividendos = list(contratos), tuple(dividendos)
    _validar_motor(motor, contratos, dividendos)
    if len({c.identificador for c in contratos}) != len(contratos):
        raise ValueError("identificadores de contrato deben ser únicos")
    if not math.isfinite(spot) or spot <= 0 or not all(math.isfinite(x) for x in (tasa, q)):
        raise ValueError("referencia inválida")
    if not escenarios or len({e.nombre for e in escenarios}) != len(escenarios):
        raise ValueError("escenarios únicos y no vacíos requeridos")
    if (not all(math.isfinite(x) for x in (presupuesto, comision, semispread_salida))
            or presupuesto <= 0 or min(comision, semispread_salida) < 0):
        raise ValueError("presupuesto o costos inválidos")
    filas, excluidos, cache = [], [], {}
    for c in contratos:
        unitario = c.ask*c.multiplicador + comision
        n = math.floor(presupuesto/(unitario + comision))  # reservar también el cierre
        if n == 0 or any(e.dias > c.dte for e in escenarios):
            excluidos.append({"contrato": c.identificador,
                              "motivo": "no cabe en presupuesto" if n == 0 else "vence antes de un escenario"})
            continue
        valores = {}
        desembolso = n*unitario
        for e in escenarios:
            al_vencer = e.dias == c.dte
            diagnostico = {}
            if motor == "pde" and not al_vencer:
                d, v = _valor_pde(c, spot, e, tasa, q, pasos, nodos, semiancho, cache)
                teorico = v.precio
                diagnostico = {"delta": v.delta, "gamma": v.gamma,
                    "vega_por_punto_iv": v.vega_paralela/100,
                    "theta_por_dia": -v.sensibilidad_plazo/365,
                    "probabilidad_q_itm_al_vencimiento": d.probabilidad_cola(c.strike, c.es_call).probabilidad,
                    "cuantil_q_05": d.cuantil(.05).precio, "cuantil_q_95": d.cuantil(.95).precio,
                    "masa_fronteras": d.masa_fronteras, "error_media_financiera": v.error_media_financiera,
                    "error_dualidad": v.error_dualidad}
            else:
                teorico = valor_en_escenario(c, spot, e, tasa, q, dividendos, pasos,
                                             motor=motor, nodos=nodos, semiancho=semiancho)
            salida = teorico if al_vencer else max(0., teorico-semispread_salida)
            # Convención explícita: comisión de cierre también al vencer; no incluye entrega/ejercicio.
            pnl = n*(salida*c.multiplicador-comision)-desembolso
            valores[e.nombre] = {"valor_teorico": teorico, "precio_salida_asumido": salida,
                                 "pnl": pnl, "retorno_desembolso": pnl/desembolso,
                                 "retorno_capital_reservado": pnl/(desembolso+n*comision),
                                 "diagnostico_pde": diagnostico}
        filas.append({"contrato": c.identificador, "strike": c.strike, "dte": c.dte,
                      "es_call": c.es_call, "ejercicio": c.ejercicio, "iv": c.iv,
                      "bid": c.bid, "ask": c.ask, "multiplicador": c.multiplicador,
                      "contratos": n, "desembolso": desembolso, "efectivo_sobrante": presupuesto-desembolso,
                      "reserva_comision_cierre": n*comision,
                      "efectivo_libre": presupuesto-desembolso-n*comision,
                      "perdida_maxima_prima_y_entrada": desembolso,
                      "perdida_maxima_costos_asumidos": desembolso + n*comision,
                      "pnl_minimo_escenarios": min(v["pnl"] for v in valores.values()), "escenarios": valores})
    return {"contratos": filas, "excluidos": excluidos, "probabilidades": "no estimadas",
            "motor": motor}
