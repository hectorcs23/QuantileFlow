"""Construcción de la vista ``P``: en qué se aparta la opinión de la distribución del mercado.

``Q`` es la distribución implícita en los precios. Una recomendación solo puede
venir de un desacuerdo explícito con ella, así que la vista se construye
**siempre a partir de Q**, deformándola lo menos posible para cumplir lo que el
usuario afirma. La deformación mínima en el sentido de Kullback–Leibler sujeta a
restricciones de momentos es un tilt exponencial,

    p(s) proporcional a q(s) * exp(lambda * x + eta * x^2),    x = ln(S/F),

y es la forma por omisión: fija la media (y, si se pide, la dispersión) sin
inventar estructura adicional en la cola. Las otras vistas sirven para opiniones
que no son de momentos: un desplazamiento puro, una reponderación explícita de
la cola izquierda o una mezcla de escenarios.

Cada constructor registra en ``detalle`` lo pedido y lo conseguido. Una vista
que no se puede representar sobre la malla no se aproxima en silencio: falla.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq, root

from .distribucion import Distribucion, desde_probabilidades, kl

TOL_OBJETIVO = 1e-8


def _pesos_tilt(q: Distribucion, F, lam, eta=0.0):
    x = np.log(q.s / float(F))
    expo = lam * x + eta * x**2
    w = q.p * np.exp(expo - expo.max())
    total = w.sum()
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("el tilt produce pesos degenerados")
    return w / total


def neutral(q: Distribucion):
    """``P = Q``: ninguna opinión. Toda estructura tiene ventaja cero antes de costos."""
    return q.con(q.p, "vista neutral (P = Q)", tipo="neutral")


def tilt_media(q: Distribucion, F, retorno):
    """Vista de dirección: ``E_P[S_T] = F * (1 + retorno)``, con mínima entropía relativa.

    ``retorno`` es el rendimiento esperado **sobre el forward**, no sobre el
    precio de contado: afirmar que algo «sube un 2 %» cuando el forward ya está
    un 1 % por encima del contado es, aquí, un ``retorno`` de aproximadamente
    1 %. Es la traducción honesta de «creo que esto va para arriba».
    """
    F = float(F)
    objetivo = F * (1.0 + float(retorno))
    if not (q.s[0] < objetivo < q.s[-1]):
        raise ValueError(f"el objetivo {objetivo:.4f} cae fuera del soporte "
                         f"[{q.s[0]:.4f}, {q.s[-1]:.4f}]")

    def exceso(lam):
        return float(_pesos_tilt(q, F, lam) @ q.s) - objetivo

    lo, hi = -50.0, 50.0
    while exceso(lo) > 0.0 and lo > -1e4:
        lo *= 2.0
    while exceso(hi) < 0.0 and hi < 1e4:
        hi *= 2.0
    lam = float(brentq(exceso, lo, hi, xtol=1e-12, rtol=1e-14))
    p = _pesos_tilt(q, F, lam)
    conseguido = float(p @ q.s) / F - 1.0
    return desde_probabilidades(
        q.s, p, q.rango_fiable, f"tilt de media ({retorno:+.2%} sobre el forward)",
        tipo="tilt_media", lambda_=lam, retorno_pedido=float(retorno),
        retorno_conseguido=conseguido, kl_sobre_q=kl(q.con(p, "tmp"), q))


def tilt_momentos(q: Distribucion, F, retorno=None, factor_vol=None, tol=1e-7,
                  tol_borde=1e-3):
    """Vista de dirección y de dispersión con mínima entropía relativa.

    ``factor_vol`` multiplica la desviación típica de ``ln(S_T/F)`` implícita.
    Un ``factor_vol`` menor que 1 dice que la volatilidad implícita está cara;
    mayor que 1, que está barata.

    Con ``eta > 0`` el tilt ensancha las colas y acumula masa en los extremos de
    la malla. Esa masa es un artefacto de la discretización, así que se mide y
    se rechaza por encima de ``tol_borde``. Los extremos de la malla caen muy
    por fuera del rango respaldado por cotizaciones, de modo que lo que quede
    por debajo del umbral lo recoge después ``evaluacion.zona_no_fiable``: no se
    cuela en la recomendación sin dejar rastro.
    """
    if retorno is None and factor_vol is None:
        raise ValueError("indica al menos retorno o factor_vol")
    F = float(F)
    sd_q = q.momentos_log(F)["sd_log"]
    objetivos = {}
    if retorno is not None:
        objetivos["media"] = F * (1.0 + float(retorno))
    if factor_vol is not None:
        if float(factor_vol) <= 0.0:
            raise ValueError("factor_vol debe ser positivo")
        objetivos["sd_log"] = float(factor_vol) * sd_q

    def estado(z):
        lam, eta = float(z[0]), float(z[1])
        p = _pesos_tilt(q, F, lam, eta)
        x = np.log(q.s / F)
        m = float(p @ x)
        return p, float(p @ q.s), float(np.sqrt(max(p @ (x - m) ** 2, 0.0)))

    def ecuaciones(z):
        _, media, sd = estado(z)
        e1 = media / objetivos["media"] - 1.0 if "media" in objetivos else float(z[0])
        e2 = sd / objetivos["sd_log"] - 1.0 if "sd_log" in objetivos else float(z[1])
        return [e1, e2]

    sol = root(ecuaciones, [0.0, 0.0], method="hybr", tol=1e-13)
    p, media, sd = estado(sol.x)
    fallos = [k for k, v in (("media", media / objetivos.get("media", media) - 1.0),
                             ("sd_log", sd / objetivos.get("sd_log", sd) - 1.0)) if abs(v) > tol]
    if not sol.success or fallos:
        raise ValueError(f"el tilt no alcanza los objetivos {fallos or list(objetivos)}: {sol.message}")
    borde = float(p[0] + p[-1])
    if borde > tol_borde:
        raise ValueError(f"el tilt acumula {borde:.3g} de masa en los extremos de la malla "
                         f"(máximo {tol_borde:g}): amplía la malla o modera la vista")
    partes = []
    if retorno is not None:
        partes.append(f"{retorno:+.2%} sobre el forward")
    if factor_vol is not None:
        partes.append(f"volatilidad x{factor_vol:.2f}")
    return desde_probabilidades(
        q.s, p, q.rango_fiable, "tilt de momentos (" + ", ".join(partes) + ")",
        tipo="tilt_momentos", lambda_=float(sol.x[0]), eta=float(sol.x[1]),
        retorno_conseguido=media / F - 1.0, sd_log_q=sd_q, sd_log_p=sd, masa_en_bordes=borde,
        kl_sobre_q=kl(q.con(p, "tmp"), q))


def desplazar(q: Distribucion, deriva, tol_fuga=1e-8):
    """Traslada el rendimiento logarítmico: ``S_P = S_Q * exp(deriva)``.

    Conserva la forma exacta de ``Q`` y solo mueve su localización. Sobre la
    malla geométrica el desplazamiento es un reindexado entero, así que la
    deriva efectiva se redondea al paso de la malla y se reporta. La masa que
    saldría de la malla debe ser despreciable.
    """
    paso = q.paso_log
    n_pasos = int(np.round(float(deriva) / paso))
    conseguida = n_pasos * paso
    p = np.zeros_like(q.p)
    if n_pasos >= 0:
        fuga = float(q.p[len(q.p) - n_pasos:].sum()) if n_pasos > 0 else 0.0
        p[n_pasos:] = q.p[:len(q.p) - n_pasos] if n_pasos > 0 else q.p
    else:
        m = -n_pasos
        fuga = float(q.p[:m].sum())
        p[:len(q.p) - m] = q.p[m:]
    if fuga > tol_fuga:
        raise ValueError(f"el desplazamiento sacaría {fuga:.3g} de masa de la malla")
    p = p / p.sum()
    return desde_probabilidades(
        q.s, p, q.rango_fiable, f"desplazamiento de {conseguida:+.4f} en log",
        tipo="desplazamiento", deriva_pedida=float(deriva), deriva_conseguida=conseguida,
        masa_perdida=fuga)


def reponderar_cola(q: Distribucion, factor, umbral_log, lado="izquierda",
                    preservar_media=False):
    """Multiplica la masa de una cola por ``factor`` y renormaliza.

    Es la vista que justifica de verdad vender puts: «el mercado paga de más por
    la caída». ``factor < 1`` dice que la cola implícita está sobrevalorada;
    ``factor > 1``, que está infravalorada. ``umbral_log`` es la frontera en
    ``ln(S/F)`` (por ejemplo ``-0.05`` para el 5 % por debajo del forward).

    Renormalizar sube el resto de la distribución: la vista no es solo «menos
    caída», es «menos caída y, por tanto, más de todo lo demás». El efecto sobre
    la media se reporta siempre.

    Con ``preservar_media`` la media vuelve a la de ``Q`` y la opinión queda
    limpia de dirección: «la cola está cara» sin añadir «y además sube». La
    compensación se aplica **solo fuera de la zona**, con un tilt de mínima
    entropía restringido al complemento. Hacerlo con un tilt global sería un
    error: al reponderar hacia abajo para recuperar la media volvería a cargar
    la propia cola que la vista acaba de aligerar, y la masa de la zona dejaría
    de ser ``factor`` veces la implícita. Con la compensación restringida,
    ``P(zona) = factor * Q(zona)`` se cumple exactamente en los dos casos.
    """
    if float(factor) < 0.0:
        raise ValueError("factor debe ser no negativo")
    F = q.detalle.get("forward", q.media)
    x = np.log(q.s / F)
    zona = x <= float(umbral_log) if lado == "izquierda" else x >= float(umbral_log)
    if not zona.any() or zona.all():
        raise ValueError("el umbral deja vacía la zona o su complemento")
    fuera = ~zona
    masa_zona = float(factor) * float(q.p[zona].sum())
    if not masa_zona < 1.0:
        raise ValueError(f"la zona reponderada se llevaría toda la masa ({masa_zona:.4f})")
    masa_objetivo = q.media

    def pesos(lam):
        """Zona fijada en ``factor * q``; el complemento absorbe el resto con un tilt."""
        expo = lam * x[fuera]
        w = q.p[fuera] * np.exp(expo - expo.max())
        total = w.sum()
        if not np.isfinite(total) or total <= 0.0:
            raise ValueError("la reponderación produce pesos degenerados")
        p = np.zeros_like(q.p)
        p[zona] = float(factor) * q.p[zona]
        p[fuera] = (1.0 - masa_zona) * w / total
        return p

    if not preservar_media:
        p, lam = pesos(0.0), 0.0
    else:
        def exceso(lam):
            return float(pesos(lam) @ q.s) - masa_objetivo

        lo, hi = -50.0, 50.0
        while exceso(lo) > 0.0 and lo > -1e4:
            lo *= 2.0
        while exceso(hi) < 0.0 and hi < 1e4:
            hi *= 2.0
        if exceso(lo) > 0.0 or exceso(hi) < 0.0:
            raise ValueError("no se puede preservar la media con esta reponderación")
        lam = float(brentq(exceso, lo, hi, xtol=1e-12, rtol=1e-14))
        p = pesos(lam)
    return desde_probabilidades(
        q.s, p, q.rango_fiable,
        f"cola {lado} reponderada x{factor:.2f} más allá de {umbral_log:+.3f} en log"
        + (", con la media de Q" if preservar_media else ""),
        tipo="reponderar_cola", factor=float(factor), umbral_log=float(umbral_log), lado=lado,
        preservar_media=bool(preservar_media), lambda_compensacion=lam,
        masa_zona_q=float(q.p[zona].sum()), masa_zona_p=float(p[zona].sum()),
        cambio_media=float(p @ q.s) / q.media - 1.0, kl_sobre_q=kl(q.con(p, "tmp"), q))


def mezcla(componentes, pesos, origen="mezcla de escenarios"):
    """Mezcla de distribuciones sobre la misma malla (vista por escenarios)."""
    componentes = list(componentes)
    pesos = np.asarray(pesos, dtype=float)
    if len(componentes) != len(pesos) or len(componentes) == 0:
        raise ValueError("hacen falta tantos pesos como componentes")
    if pesos.min() < 0.0 or abs(pesos.sum() - 1.0) > 1e-10:
        raise ValueError("los pesos deben ser no negativos y sumar 1")
    base = componentes[0]
    if not all(base.misma_malla(c) for c in componentes[1:]):
        raise ValueError("todas las componentes deben compartir la malla")
    p = sum(w * c.p for w, c in zip(pesos, componentes))
    lo = max(c.rango_fiable[0] for c in componentes)
    hi = min(c.rango_fiable[1] for c in componentes)
    return desde_probabilidades(base.s, p, (lo, hi), origen, tipo="mezcla",
                                pesos=[float(w) for w in pesos],
                                componentes=[c.origen for c in componentes])


def escenarios(q: Distribucion, F, lista):
    """Vista por escenarios: ``lista`` de ``(peso, retorno, factor_vol)`` sobre ``Q``.

    Cada escenario es un tilt de mínima entropía de la misma ``Q``; la vista es
    su mezcla. Permite decir «60 % de probabilidad de subir un 3 %, 40 % de caer
    un 5 %» sin abandonar la forma que el mercado está cotizando.
    """
    pesos, partes = [], []
    for peso, retorno, factor_vol in lista:
        pesos.append(float(peso))
        partes.append(tilt_momentos(q, F, retorno, factor_vol) if factor_vol is not None
                      else tilt_media(q, F, retorno))
    return mezcla(partes, np.asarray(pesos) / float(np.sum(pesos)),
                  "escenarios: " + "; ".join(f"{w:.0%} {p.origen}" for w, p in zip(pesos, partes)))


def desde_cuantiles(q: Distribucion, F, u, valores_log, origen="pronóstico cuantílico"):
    """Vista a partir de un pronóstico cuantílico de ``ln(S_T/F)``.

    Es la vía que conecta con ``quantileflow.pronostico``: los cuantiles
    estimados sobre datos definen una CDF, y de ella sale la vista. Los niveles
    deben ser crecientes y los valores también (sin cruces); la masa fuera del
    rango cubierto por los cuantiles se asigna a las colas de ``Q``,
    reescaladas, y esa dependencia queda registrada.
    """
    u = np.asarray(u, dtype=float)
    x = np.asarray(valores_log, dtype=float)
    if u.shape != x.shape or len(u) < 2:
        raise ValueError("u y valores_log deben ser vectores de igual longitud (>= 2)")
    if np.any(np.diff(u) <= 0.0) or np.any(np.diff(x) <= 0.0):
        raise ValueError("u y valores_log deben ser estrictamente crecientes (cuantiles cruzados)")
    if u[0] <= 0.0 or u[-1] >= 1.0:
        raise ValueError("los niveles deben estar en el interior de (0, 1)")
    malla_x = np.log(q.s / float(F))
    cdf_q = np.concatenate([[0.0], q.acumulada[:-1]])
    f_lo, f_hi = float(np.interp(x[0], malla_x, cdf_q)), float(np.interp(x[-1], malla_x, cdf_q))
    if not (0.0 < f_lo < f_hi < 1.0):
        raise ValueError("el rango de cuantiles no es compatible con el soporte de Q")
    # Dentro del rango manda el pronóstico; fuera se reescala la cola de Q para
    # casar con la masa que el pronóstico deja en cada extremo.
    cdf = np.where(malla_x < x[0], cdf_q * u[0] / f_lo,
                   np.where(malla_x > x[-1], 1.0 - (1.0 - cdf_q) * (1.0 - u[-1]) / (1.0 - f_hi),
                            np.interp(malla_x, x, u)))
    cdf = np.maximum.accumulate(np.clip(cdf, 0.0, 1.0))
    p = np.diff(np.concatenate([[0.0], cdf, [1.0]]))[:-1]
    p[-1] += 1.0 - p.sum()
    return desde_probabilidades(q.s, p, q.rango_fiable, origen, tipo="cuantiles",
                                u=[float(v) for v in u], cola_izquierda_de_q=u[0] / f_lo,
                                cola_derecha_de_q=(1.0 - u[-1]) / (1.0 - f_hi))
