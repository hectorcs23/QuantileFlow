"""Ventaja y riesgo de una estructura: de dónde sale exactamente el número.

Si la estructura se monta a su precio teórico bajo ``Q``, su ventaja esperada es
cero por construcción. Toda ventaja positiva procede de la diferencia entre la
vista ``P`` y la distribución implícita ``Q``, menos lo que se paga por ejecutar.

Para un put vendido de strike ``K`` la ventaja tiene forma cerrada. Usando
``E[(K - S)^+] = int_0^K F(s) ds``,

    ventaja(put corto K) = D * ( E_Q[(K-S)^+] - E_P[(K-S)^+] )
                         = D * int_0^K ( F_Q(s) - F_P(s) ) ds.

Es decir: **vender un put solo tiene ventaja si tu función de distribución
acumulada está por debajo de la del mercado en el tramo que hay bajo el
strike**. No basta con creer que el subyacente sube; hay que creer que la caída
concreta que el mercado está cotizando bajo ese strike es menos probable de lo
que dice el precio. Un put spread mide lo mismo sobre un tramo acotado, y
cualquier pago convexo es una superposición de estos tramos (Carr y Madan,
2001). ``ventaja_por_tramos`` reparte el desacuerdo por zonas de precio y dice,
antes de elegir nada, dónde está la opinión y qué strike la expresa.

El valor bajo ``Q`` y el precio al que se cotiza la estructura no coinciden:
``Q`` sale de un ajuste y el ajuste tiene residuo. Esa diferencia
(``residuo_ajuste``) es error de modelo, no ventaja, y se mide para exigir que
la ventaja la supere; si no, lo que se estaría operando es el error.

La ventaja que procede de una zona sin cotizaciones utilizables se mide aparte
(``zona_no_fiable``): si la recomendación se apoya en la cola que nadie cotiza,
no es una recomendación.

La pérdida se mide al vencimiento con la prima capitalizada,
``pnl(S) = pago(S) - (precio + comisiones) / D``, y el valor presente esperado
es ``D * E_P[pnl]``. CVaR y pérdida máxima describen la cola **bajo la vista**:
si la vista está equivocada, el número también.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .distribucion import Distribucion
from .estructuras import Estructura
from .precios import ADVERSO, Mercado, precio_entrada, valor

TOL_MASA_COLA = 1e-9


# ---------------------------------------------------------------------------
# Desacuerdo entre P y Q
# ---------------------------------------------------------------------------


def integral_cdf(d: Distribucion, a, b):
    """``int_a^b F(s) ds`` exacta para una CDF escalonada."""
    a, b = float(a), float(b)
    if b <= a:
        return 0.0
    bordes = np.unique(np.clip(np.concatenate([[a, b], d.s]), a, b))
    medios = 0.5 * (bordes[1:] + bordes[:-1])
    return float(np.sum(d.cdf(medios) * np.diff(bordes)))


def ventaja_por_tramos(p: Distribucion, q: Distribucion, D, bordes):
    """Ventaja por unidad de put vendido en cada tramo: ``D * int (F_Q - F_P)``.

    Un valor positivo en el tramo ``[a, b]`` significa que el mercado asigna más
    probabilidad acumulada que la vista a esa zona de precios: vender exposición
    a la caída **dentro de ese tramo** tiene ventaja según la vista. Negativo,
    lo contrario: ahí conviene comprarla.
    """
    bordes = np.asarray(bordes, dtype=float)
    if np.any(np.diff(bordes) <= 0.0):
        raise ValueError("los bordes deben ser crecientes")
    filas = []
    for a, b in zip(bordes[:-1], bordes[1:]):
        v = float(D) * ((q.precio_put(b) - q.precio_put(a)) - (p.precio_put(b) - p.precio_put(a)))
        filas.append({"desde": float(a), "hasta": float(b), "ventaja": v,
                      "prob_q": float(q.cdf(b) - q.cdf(a)), "prob_p": float(p.cdf(b) - p.cdf(a))})
    return filas


def ventaja_put_por_strike(p: Distribucion, q: Distribucion, D, strikes):
    """``D * (E_Q[(K-S)^+] - E_P[(K-S)^+])`` para cada strike: la ventaja de vender ese put.

    Es la curva que contesta «¿qué put vendo?» antes de mirar ninguna
    estructura: su máximo señala el strike donde el desacuerdo con el mercado
    es mayor en términos de prima, y su derivada es ``D * (F_Q - F_P)``.
    """
    K = np.asarray(strikes, dtype=float)
    return np.array([float(D) * (q.precio_put(k) - p.precio_put(k)) for k in K])


def comparar(p: Distribucion, q: Distribucion, F, D):
    """Resumen del desacuerdo: momentos, colas y ventaja por tramos del forward."""
    from .distribucion import kl

    mp, mq = p.momentos_log(F), q.momentos_log(F)
    bordes = F * np.array([0.80, 0.90, 0.95, 0.975, 1.0, 1.025, 1.05, 1.10, 1.20])
    return {
        "retorno_vista": p.media / float(F) - 1.0,
        "sd_log_p": mp["sd_log"], "sd_log_q": mq["sd_log"],
        "factor_vol": mp["sd_log"] / mq["sd_log"] if mq["sd_log"] > 0 else float("nan"),
        "asimetria_p": mp["asimetria_log"], "asimetria_q": mq["asimetria_log"],
        "kl_p_sobre_q": kl(p, q),
        "prob_caida_5_q": float(q.cdf(F * 0.95)), "prob_caida_5_p": float(p.cdf(F * 0.95)),
        "prob_caida_10_q": float(q.cdf(F * 0.90)), "prob_caida_10_p": float(p.cdf(F * 0.90)),
        "tramos": ventaja_por_tramos(p, q, D, bordes),
    }


# ---------------------------------------------------------------------------
# Riesgo
# ---------------------------------------------------------------------------


def var_cvar_discreto(perdidas, probabilidades, alfa=0.95):
    """VaR y CVaR de una pérdida discreta con probabilidades.

    Misma definición que ``quantileflow.decision.var_cvar`` (Rockafellar y
    Uryasev): ``VaR`` es el cuantil superior y
    ``CVaR = VaR + E[(L - VaR)^+] / (1 - alfa)``.
    """
    L = np.asarray(perdidas, dtype=float)
    w = np.asarray(probabilidades, dtype=float)
    orden = np.argsort(L)
    L, w = L[orden], w[orden]
    acum = np.cumsum(w)
    idx = int(np.searchsorted(acum, alfa * float(w.sum()), side="left"))
    idx = min(idx, len(L) - 1)
    var = float(L[idx])
    cvar = var + float(w @ np.maximum(L - var, 0.0)) / (1.0 - alfa)
    return var, cvar


def _puntos_criticos(estructura: Estructura, s):
    extra = [0.0, *estructura.strikes]
    return np.unique(np.concatenate([np.asarray(s, dtype=float), np.asarray(extra, dtype=float)]))


def extremos_pnl(estructura: Estructura, s, coste_capitalizado):
    """Pérdida y ganancia máximas del pago, incluidos ``S_T = 0`` y los strikes."""
    puntos = _puntos_criticos(estructura, s)
    pnl = estructura.pago(puntos) - coste_capitalizado
    perdida = float(-pnl.min())
    ganancia = float("inf") if estructura.pendiente_derecha > 0.0 else float(pnl.max())
    if estructura.perdida_no_acotada:
        perdida = float("inf")
    return perdida, ganancia


def puntos_equilibrio(estructura: Estructura, s, coste_capitalizado):
    """Precios del subyacente donde el resultado al vencimiento cambia de signo."""
    puntos = _puntos_criticos(estructura, s)
    pnl = estructura.pago(puntos) - coste_capitalizado
    signos = np.sign(pnl)
    cortes = []
    for i in np.flatnonzero(signos[:-1] * signos[1:] < 0.0):
        a, b, fa, fb = puntos[i], puntos[i + 1], pnl[i], pnl[i + 1]
        cortes.append(float(a - fa * (b - a) / (fb - fa)))
    cortes.extend(float(x) for x in puntos[signos == 0.0])
    return tuple(sorted(set(round(c, 6) for c in cortes)))


def zona_no_fiable(p: Distribucion, q: Distribucion, estructura: Estructura, D):
    """Cuánto de la ventaja procede de donde no hay cotizaciones utilizables.

    Fuera del rango respaldado por cotizaciones, la forma de la distribución es
    una extrapolación. Dos cantidades distintas, y conviene no confundirlas:

    * ``contribucion``: la parte de ``D * (E_P - E_Q)[pago]`` que aportan los
      puntos de esa zona. Como ``P`` se construye deformando ``Q``, las dos
      colas se parecen y buena parte se cancela; lo que queda es la ventaja que
      de verdad depende de la extrapolación. Si es casi toda la ventaja, la
      recomendación se apoya en lo que no se puede ver.
    * ``cota``: el peor caso si la masa de esa zona se recolocara donde más
      daño hace, en ``P`` y en ``Q``. Es una cota válida pero floja; se reporta
      para dimensionar la incertidumbre, no para filtrar.

    ``cola_abierta`` avisa de que el pago crece sin límite a la derecha y hay
    masa allí: la cota depende entonces de hasta dónde llegue la malla.
    """
    lo, hi = p.rango_fiable
    pago = estructura.pago(p.s)
    fuera = (p.s < lo) | (p.s > hi)
    contribucion = float(D) * float((p.p[fuera] - q.p[fuera]) @ pago[fuera])
    cota, abierta = 0.0, False
    for mask, borde in ((p.s < lo, 0.0), (p.s > hi, None)):
        masa = float(p.p[mask].sum() + q.p[mask].sum())
        if not mask.any() or masa <= TOL_MASA_COLA:
            continue
        puntos = p.s[mask] if borde is None else np.concatenate([[borde], p.s[mask]])
        valores = estructura.pago(puntos)
        cota += masa * float(valores.max() - valores.min())
        abierta = abierta or (borde is None and estructura.pendiente_derecha != 0.0)
    return {"contribucion": contribucion, "cota": float(D) * cota, "cola_abierta": abierta,
            "masa_p": float(p.p[fuera].sum()), "masa_q": float(q.p[fuera].sum())}


# ---------------------------------------------------------------------------
# Evaluación completa
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Evaluacion:
    estructura: Estructura
    identificada: bool
    motivo: str
    precio: float
    comisiones: float
    valor_q: float
    valor_p: float
    ventaja: float                 # valor presente esperado, neto de ejecución
    ventaja_sin_costos: float      # D * (E_P - E_Q): solo la vista
    coste_ejecucion: float         # deslizamiento contra el mid más comisiones
    residuo_ajuste: float          # valor bajo Q menos el precio al mid: error del modelo
    capital: float
    rendimiento_sobre_capital: float
    prob_ganancia: float
    perdida_maxima: float
    ganancia_maxima: float
    equilibrio: tuple
    var: float
    cvar: float
    ventaja_no_fiable: float       # parte de la ventaja que viene de la zona sin cotizaciones
    cota_extrapolacion: float      # peor caso de esa zona (cota floja, informativa)
    detalle: dict = field(default_factory=dict)

    @property
    def fraccion_no_fiable(self):
        """Fracción de la ventaja que depende de la zona no identificada.

        Solo tiene sentido con ventaja positiva: con ventaja negativa o nula la
        estructura ya está descartada por otro motivo y el cociente solo
        confundiría. En ese caso es ``nan``.
        """
        if not np.isfinite(self.ventaja) or self.ventaja <= 0.0:
            return float("nan")
        return float(self.ventaja_no_fiable / self.ventaja)


def evaluar(estructura: Estructura, p: Distribucion, q: Distribucion, mercado: Mercado,
            alfa=0.95, modo=ADVERSO):
    """Evalúa una estructura bajo la vista ``P`` con precios de ``mercado``."""
    D = mercado.D
    entrada = precio_entrada(mercado, estructura, modo)
    v_q = valor(q, estructura, D)
    v_p = valor(p, estructura, D)
    vacio = dict(valor_q=v_q, valor_p=v_p, ventaja=float("nan"),
                 ventaja_sin_costos=v_p - v_q, coste_ejecucion=float("nan"),
                 capital=float("nan"), rendimiento_sobre_capital=float("nan"),
                 prob_ganancia=float("nan"), perdida_maxima=float("nan"),
                 ganancia_maxima=float("nan"), equilibrio=(), var=float("nan"),
                 cvar=float("nan"), residuo_ajuste=float("nan"))
    zona = zona_no_fiable(p, q, estructura, D)
    if not entrada["identificada"]:
        return Evaluacion(estructura, False, entrada["motivo"], float("nan"), float("nan"),
                          ventaja_no_fiable=zona["contribucion"], cota_extrapolacion=zona["cota"],
                          detalle={"entrada": entrada, "zona_no_fiable": zona}, **vacio)

    precio, comisiones = entrada["precio"], entrada["comisiones"]
    coste_total = precio + comisiones
    capitalizado = coste_total / D
    pnl = estructura.pago(p.s) - capitalizado
    ventaja = v_p - coste_total
    perdida_max, ganancia_max = extremos_pnl(estructura, p.s, capitalizado)
    var, cvar = var_cvar_discreto(-pnl, p.p, alfa)
    capital = max(D * perdida_max, coste_total, 0.0) if np.isfinite(perdida_max) else float("inf")
    referencia = precio_entrada(mercado, estructura, "medio")
    return Evaluacion(
        estructura=estructura, identificada=True, motivo="",
        precio=float(precio), comisiones=float(comisiones),
        valor_q=v_q, valor_p=v_p, ventaja=float(ventaja),
        ventaja_sin_costos=float(v_p - v_q),
        coste_ejecucion=float(precio - referencia["precio"] + comisiones),
        residuo_ajuste=float(v_q - referencia["precio"]),
        capital=float(capital),
        rendimiento_sobre_capital=float(ventaja / capital) if np.isfinite(capital) and capital > 0
        else float("nan"),
        prob_ganancia=float(p.p[pnl > 0.0].sum()),
        perdida_maxima=float(perdida_max), ganancia_maxima=float(ganancia_max),
        equilibrio=puntos_equilibrio(estructura, p.s, capitalizado),
        var=float(var), cvar=float(cvar),
        ventaja_no_fiable=zona["contribucion"], cota_extrapolacion=zona["cota"],
        detalle={"entrada": entrada, "precio_medio": referencia["precio"],
                 "via_paridad": entrada["via_paridad"], "zona_no_fiable": zona,
                 "vende_volatilidad": estructura.vende_volatilidad})
