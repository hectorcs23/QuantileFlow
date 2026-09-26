"""Cadenas de opciones crudas: captura, controles, paridad y asimetría call/put.

Este módulo trabaja **solo con cotizaciones observadas** (bid, ask, tamaños y
sellos de tiempo). Sus salidas —residuos de paridad, volatilidades implícitas
y asimetrías— forman la serie *observada* y se guardan separadas de cualquier
superficie ajustada (``ajustar_captura``): un ajuste sin arbitraje impone la
paridad y puede borrar justamente el residuo que se quiere estudiar.

Contrato mínimo de una captura (un vencimiento, una hora de corte)
-------------------------------------------------------------------
Por fila (una por actualización de cada contrato): ``strike``, ``es_call``,
``bid``, ``ask``, ``tam_bid``, ``tam_ask`` y ``sello``. Por captura: ``T`` en
años, ``spot`` y ``sello_spot`` (subyacente sincronizado), ``tasa`` continua,
dividendos en efectivo ``((t_i, monto), ...)`` o rendimiento continuo, tipo de
ejercicio, hora de ``corte`` y ``fecha``. Los sellos se expresan en segundos
desde la medianoche de la sesión en hora de Nueva York; la conversión de zona
horaria (con horario de verano) se hace al ingerir, no aquí.

Cada fila excluida conserva todos sus motivos (``MOTIVOS``). Los umbrales de
``ReglasCalidad`` son provisionales: se fijan en la fase 0 con una muestra real.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from .opciones import binomial_crr, precio_black, vol_implicita_black
from .superficies import Rebanada, ajustar_rebanada

HORA_APERTURA = 9.5 * 3600.0  # 09:30
HORA_CORTE = 9.75 * 3600.0  # 09:45

MOTIVOS = {
    "posterior_al_corte": "sello posterior a la hora de corte: no se conocía al decidir",
    "reemplazada": "hay una actualización posterior del mismo contrato antes del corte",
    "antes_de_apertura": "cotización de preapertura o de la sesión anterior",
    "ventana_de_apertura": "primeros minutos de la sesión: cotizaciones inestables",
    "desfasada": "más antigua que la edad máxima al corte: no refleja el subyacente actual",
    "sin_bid": "bid nulo: el precio solo queda acotado por arriba",
    "cruzada": "bid mayor que ask",
    "bloqueada": "bid igual a ask: ancho nulo, habitual en datos consolidados desincronizados",
    "sin_tamano": "tamaño menor que el mínimo en bid o en ask",
    "spread_ancho": "spread relativo mayor que el máximo",
    "fuera_de_cotas": "viola cotas sin modelo (call > spot, put > strike o, si es americana, "
                      "ask menor que el ejercicio inmediato)",
}


# ---------------------------------------------------------------------------
# Captura inmutable y reglas
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Captura:
    """Cotizaciones crudas de un vencimiento tal como se recibieron (inmutable)."""

    strike: np.ndarray
    es_call: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    tam_bid: np.ndarray
    tam_ask: np.ndarray
    sello: np.ndarray
    T: float
    spot: float
    sello_spot: float
    tasa: float
    dividendos: tuple = ()
    rendimiento_dividendo: float = 0.0
    ejercicio: str = "europeo"
    corte: float = HORA_CORTE
    fecha: str = ""

    def __post_init__(self):
        n = np.size(self.strike)
        for nombre, tipo in (("strike", float), ("es_call", bool), ("bid", float), ("ask", float),
                             ("tam_bid", float), ("tam_ask", float), ("sello", float)):
            arreglo = np.array(getattr(self, nombre), dtype=tipo).reshape(-1)  # copia propia
            if arreglo.shape != (n,):
                raise ValueError(f"{nombre} debe tener {n} elementos")
            arreglo.setflags(write=False)
            object.__setattr__(self, nombre, arreglo)
        if self.ejercicio not in ("europeo", "americano"):
            raise ValueError("ejercicio debe ser 'europeo' o 'americano'")
        object.__setattr__(self, "dividendos",
                           tuple((float(t), float(m)) for t, m in self.dividendos))

    @property
    def mid(self):
        return 0.5 * (self.bid + self.ask)

    @property
    def americana(self):
        return self.ejercicio == "americano"

    def vp_dividendos(self):
        """Valor presente de los dividendos en efectivo pagados antes del vencimiento."""
        return sum(m * np.exp(-self.tasa * t) for t, m in self.dividendos if 0.0 < t <= self.T)

    @property
    def descuento_contractual(self):
        return float(np.exp(-self.tasa * self.T))

    @property
    def forward_contractual(self):
        """Forward con la tasa y los dividendos declarados (no con la paridad)."""
        return float((self.spot - self.vp_dividendos())
                     * np.exp((self.tasa - self.rendimiento_dividendo) * self.T))


@dataclass(frozen=True)
class ReglasCalidad:
    """Umbrales de los controles por fila (provisionales hasta la fase 0)."""

    apertura: float = HORA_APERTURA
    margen_apertura: float = 300.0  # s tras la apertura con cotizaciones inestables
    edad_maxima: float = 60.0  # s antes del corte
    desfase_spot_max: float = 2.0  # s entre el sello del subyacente y el corte
    spread_relativo_max: float = 0.5  # (ask - bid) / mid
    tamano_minimo: float = 1.0


@dataclass(frozen=True)
class Controles:
    """Resultado de los controles: motivos por fila y alertas de la captura."""

    motivos: tuple  # por fila, tupla de códigos de MOTIVOS; vacía si la fila es válida
    alertas: tuple = ()

    @property
    def valida(self):
        return np.array([len(m) == 0 for m in self.motivos], dtype=bool)

    def resumen(self):
        """Número de filas afectadas por cada motivo (una fila puede tener varios)."""
        return dict(Counter(c for m in self.motivos for c in m))

    def exclusiones(self, captura: Captura):
        """Tabla de filas excluidas con todos sus motivos."""
        return [{"strike": float(captura.strike[i]), "tipo": "call" if captura.es_call[i] else "put",
                 "sello": float(captura.sello[i]), "motivos": m}
                for i, m in enumerate(self.motivos) if m]


def controlar(captura: Captura, reglas: ReglasCalidad = ReglasCalidad()) -> Controles:
    """Aplica los controles por fila y registra **todos** los motivos de exclusión.

    Por contrato solo puede quedar válida la última actualización anterior o
    igual al corte; si esa actualización falla un control, el contrato queda
    fuera (no se recurre a una cotización más vieja).
    """
    c, r = captura, reglas
    n = len(c.strike)
    motivos = [[] for _ in range(n)]

    def marcar(mascara, codigo):
        for i in np.flatnonzero(mascara):
            motivos[i].append(codigo)

    posterior = c.sello > c.corte
    marcar(posterior, "posterior_al_corte")
    ultima = {}
    for i in range(n):
        if posterior[i]:
            continue
        clave = (float(c.strike[i]), bool(c.es_call[i]))
        if clave not in ultima or c.sello[i] >= c.sello[ultima[clave]]:
            ultima[clave] = i
    elegidas = set(ultima.values())
    marcar([i not in elegidas and not posterior[i] for i in range(n)], "reemplazada")
    marcar(c.sello < r.apertura, "antes_de_apertura")
    marcar((c.sello >= r.apertura) & (c.sello < r.apertura + r.margen_apertura), "ventana_de_apertura")
    marcar(~posterior & (c.corte - c.sello > r.edad_maxima), "desfasada")
    marcar(c.bid <= 0.0, "sin_bid")
    marcar(c.bid > c.ask, "cruzada")
    marcar((c.bid > 0.0) & (c.bid == c.ask), "bloqueada")
    marcar((c.tam_bid < r.tamano_minimo) | (c.tam_ask < r.tamano_minimo), "sin_tamano")
    with np.errstate(divide="ignore", invalid="ignore"):
        relativo = (c.ask - c.bid) / c.mid
    marcar((c.bid > 0.0) & (relativo > r.spread_relativo_max), "spread_ancho")
    cotas = np.where(c.es_call, c.bid > c.spot, c.bid > c.strike)
    if c.americana:
        inmediato = np.where(c.es_call, c.spot - c.strike, c.strike - c.spot)
        cotas = cotas | (c.ask < inmediato - 1e-12)
    marcar(cotas, "fuera_de_cotas")

    alertas = []
    if abs(c.corte - c.sello_spot) > r.desfase_spot_max:
        alertas.append(f"subyacente desfasado {c.corte - c.sello_spot:.0f} s respecto del corte")
    if c.sello_spot < r.apertura + r.margen_apertura:
        alertas.append("subyacente dentro de la ventana de apertura")
    return Controles(tuple(tuple(m) for m in motivos), tuple(alertas))


# ---------------------------------------------------------------------------
# Ejercicio anticipado
# ---------------------------------------------------------------------------


def desamericanizar(precio, S, K, T, r, es_call, dividendos=(), q=0.0, n=200, vol_min=1e-3,
                    vol_max=3.0):
    """Precio europeo equivalente, prima de ejercicio anticipado y volatilidad.

    Busca la volatilidad que reproduce ``precio`` en el árbol americano y valora
    la europea en el **mismo** árbol. Devuelve NaN si el precio no identifica
    una volatilidad (por ejemplo, si está en el valor de ejercicio inmediato).
    """
    def americana(s):
        return binomial_crr(S, K, T, r, s, es_call, q, dividendos, n, americana=True)

    if not americana(vol_min) < precio < americana(vol_max):
        return np.nan, np.nan, np.nan
    sigma = brentq(lambda s: americana(s) - precio, vol_min, vol_max, xtol=1e-7)
    prima = americana(sigma) - binomial_crr(S, K, T, r, sigma, es_call, q, dividendos, n,
                                            americana=False)
    return precio - prima, prima, sigma


def primas_ejercicio(captura: Captura, filas, n_arbol=200):
    """Prima de ejercicio anticipado estimada en el mid de cada fila (0 si es europea)."""
    primas = np.full(len(captura.strike), np.nan)
    filas = np.asarray(filas, dtype=int)
    if not captura.americana:
        primas[filas] = 0.0
        return primas
    for i in filas:
        _, primas[i], _ = desamericanizar(
            float(captura.mid[i]), captura.spot, float(captura.strike[i]), captura.T, captura.tasa,
            bool(captura.es_call[i]), captura.dividendos, captura.rendimiento_dividendo, n_arbol)
    return primas


# ---------------------------------------------------------------------------
# Paridad put-call del mismo strike
# ---------------------------------------------------------------------------


def pares_mismo_strike(captura: Captura, controles: Controles):
    """Pares (call, put) válidos del mismo strike y strikes sin pareja con su motivo."""
    valida = controles.valida
    calls = {float(captura.strike[i]): i for i in np.flatnonzero(valida & captura.es_call)}
    puts = {float(captura.strike[i]): i for i in np.flatnonzero(valida & ~captura.es_call)}
    comunes = sorted(set(calls) & set(puts))
    sin_pareja = []
    for K in sorted(set(calls) ^ set(puts)):
        presente, falta = ("call", "put") if K in calls else ("put", "call")
        filas = [i for i in range(len(captura.strike))
                 if captura.strike[i] == K and bool(captura.es_call[i]) == (falta == "call")]
        if not filas:
            motivo = "sin cotización"
        else:
            codigos = sorted({m for i in filas for m in controles.motivos[i]})
            motivo = "excluida: " + ", ".join(codigos)
        sin_pareja.append({"strike": K, "presente": presente, "falta": falta, "motivo": motivo})
    idx_call = np.array([calls[K] for K in comunes], dtype=int)
    idx_put = np.array([puts[K] for K in comunes], dtype=int)
    return np.array(comunes, dtype=float), idx_call, idx_put, sin_pareja


def forward_implicito(K, diferencia, ancho, descuento=None):
    """``F`` y ``D`` de ``C - P = D (F - K)`` por mínimos cuadrados ponderados.

    Pesos ``1 / ancho**2``: los pares con banda bid/ask más estrecha pesan más.
    Con ``descuento`` conocido solo se estima ``F``.
    """
    K = np.asarray(K, dtype=float)
    y = np.asarray(diferencia, dtype=float)
    w = 1.0 / np.asarray(ancho, dtype=float) ** 2
    if descuento is None:
        Km, ym = np.average(K, weights=w), np.average(y, weights=w)
        b = np.sum(w * (K - Km) * (y - ym)) / np.sum(w * (K - Km) ** 2)
        D = -b
        a = ym - b * Km
    else:
        D = float(descuento)
        a = np.average(y + D * K, weights=w)
    return float(a / D), float(D)


@dataclass(frozen=True, eq=False)
class ResiduosParidad:
    """Residuos observados de ``C - P = D (F - K)`` por strike (serie observada).

    ``residuo`` usa mids y un forward estimado **sin** el propio par; la banda
    usa los extremos bid/ask y su ancho total es ``ancho``. Dentro de la banda
    (``|multiplo_ancho| <= 1/2``) la diferencia no supera el costo de negociar.
    En americanas se descuenta la prima de ejercicio estimada y se exige que el
    residuo la supere para interpretarlo.
    """

    strike: np.ndarray
    residuo: np.ndarray
    banda_inferior: np.ndarray
    banda_superior: np.ndarray
    ancho: np.ndarray
    multiplo_ancho: np.ndarray
    forward: np.ndarray  # forward usado para cada par (sin ese par)
    descuento: np.ndarray
    prima_ejercicio: np.ndarray  # efecto del ejercicio anticipado sobre C - P (0 si europea)
    fuera_de_banda: np.ndarray
    interpretable: np.ndarray
    motivo_no_interpretable: tuple
    en_estimacion: np.ndarray  # si el par entra en el forward de los demás
    forward_global: float
    descuento_global: float
    sin_pareja: tuple = ()
    alertas: tuple = ()


def residuos_paridad(captura: Captura, controles: Controles | None = None, primas=None,
                     descuento=None, forward=None, umbral_z=3.0, umbral_robusto=5.0, minimo_pares=3,
                     n_arbol=200):
    """Residuo de paridad de cada par del mismo strike con forward fuera de muestra.

    El forward de cada par se estima con los **demás** pares (ninguna
    cotización evalúa su propia paridad). Un par sale, de uno en uno, de la
    estimación del forward de los demás si su residuo supera ``umbral_z``
    medios anchos de su banda **y** ``umbral_robusto`` desviaciones robustas
    (MAD) de los residuos del resto; conserva su residuo. Con ``forward`` (y
    ``descuento``) externos no se estima nada: sirve para mostrar el sesgo de un
    forward contractual mal especificado.
    """
    controles = controles or controlar(captura)
    K, ic, ip, sin_pareja = pares_mismo_strike(captura, controles)
    alertas = list(controles.alertas)
    n = len(K)
    if primas is None:
        primas = primas_ejercicio(captura, np.concatenate([ic, ip]), n_arbol)
    e_c, e_p = primas[ic], primas[ip]
    c_bid, c_ask, p_bid, p_ask = captura.bid[ic], captura.ask[ic], captura.bid[ip], captura.ask[ip]
    diferencia = (0.5 * (c_bid + c_ask) - e_c) - (0.5 * (p_bid + p_ask) - e_p)
    ancho = (c_ask - c_bid) + (p_ask - p_bid)
    estimable = np.isfinite(diferencia)
    en_estimacion = estimable.copy()
    F_par = np.full(n, np.nan)
    D_par = np.full(n, np.nan)

    def ajustar(mascara):
        if forward is not None:
            return float(forward), float(descuento if descuento is not None
                                         else captura.descuento_contractual)
        return forward_implicito(K[mascara], diferencia[mascara], ancho[mascara], descuento)

    def fuera_de_muestra():
        for j in range(n):
            mascara = en_estimacion.copy()
            mascara[j] = False
            F_par[j], D_par[j] = ajustar(mascara)
        return diferencia - D_par * (F_par - K)

    minimo = 2 if descuento is not None else 3
    if n == 0 or (forward is None and en_estimacion.sum() < max(minimo, minimo_pares)):
        alertas.append(f"paridad insuficiente: {int(en_estimacion.sum())} pares estimables")
        vacio = np.full(n, np.nan)
        return ResiduosParidad(K, vacio, vacio, vacio, ancho, vacio, vacio, vacio, e_c - e_p,
                               np.zeros(n, bool), np.zeros(n, bool),
                               tuple("paridad insuficiente" for _ in range(n)), en_estimacion,
                               np.nan, np.nan, tuple(sin_pareja), tuple(alertas))
    while True:
        residuo = fuera_de_muestra()
        z = np.abs(residuo) / (0.5 * ancho)
        centro = np.median(residuo[en_estimacion])
        escala = 1.4826 * np.median(np.abs(residuo[en_estimacion] - centro))
        z_robusto = np.abs(residuo - centro) / max(escala, 1e-12)
        candidatos = en_estimacion & (z > umbral_z) & (z_robusto > umbral_robusto)
        if forward is not None or not candidatos.any() or en_estimacion.sum() <= max(minimo, minimo_pares):
            break
        en_estimacion[np.argmax(np.where(candidatos, z, -np.inf))] = False
    F_global, D_global = ajustar(en_estimacion)
    prediccion = D_par * (F_par - K)
    banda_inferior = (c_bid - e_c) - (p_ask - e_p) - prediccion
    banda_superior = (c_ask - e_c) - (p_bid - e_p) - prediccion
    fuera = (banda_inferior > 0.0) | (banda_superior < 0.0)
    umbral = 0.5 * ancho + np.abs(e_c) + np.abs(e_p)
    sincronizado = not any(a.startswith("subyacente") for a in controles.alertas)
    motivos = []
    for j in range(n):
        if not np.isfinite(residuo[j]):
            motivos.append("prima de ejercicio no estimable")
        elif not fuera[j]:
            motivos.append("dentro de la banda bid/ask")
        elif captura.americana and abs(residuo[j]) <= umbral[j]:
            motivos.append("menor que la banda más la prima de ejercicio")
        elif captura.americana and not sincronizado:
            motivos.append("subyacente desfasado: prima de ejercicio poco fiable")
        else:
            motivos.append("")
    interpretable = np.array([m == "" for m in motivos], dtype=bool)
    return ResiduosParidad(K, residuo, banda_inferior, banda_superior, ancho, residuo / ancho, F_par,
                           D_par, e_c - e_p, fuera, interpretable, tuple(motivos), en_estimacion,
                           F_global, D_global, tuple(sin_pareja), tuple(alertas))


# ---------------------------------------------------------------------------
# Volatilidades observadas y asimetría call/put
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class VolatilidadesObservadas:
    """Volatilidades implícitas de las cotizaciones OTM válidas, ordenadas por ``k``."""

    fila: np.ndarray
    strike: np.ndarray
    k: np.ndarray  # ln(K / F)
    es_call: np.ndarray
    iv: np.ndarray  # en el mid (europeo equivalente si la opción es americana)
    iv_bid: np.ndarray
    iv_ask: np.ndarray
    delta: np.ndarray  # delta forward con iv: N(d1) en calls, N(d1) - 1 en puts
    forward: float
    descuento: float
    T: float


def volatilidades_observadas(captura: Captura, controles: Controles, forward, descuento,
                             primas=None, n_arbol=200):
    """IV en bid, mid y ask de puts con ``K <= F`` y calls con ``K >= F`` válidos."""
    valida = controles.valida
    otm = np.where(captura.es_call, captura.strike >= forward, captura.strike <= forward)
    filas = np.flatnonzero(valida & otm)
    if primas is None:
        primas = primas_ejercicio(captura, filas, n_arbol)
    e = primas[filas]
    K = captura.strike[filas]
    es_call = captura.es_call[filas]
    T = captura.T

    def iv(precio):
        return vol_implicita_black(precio, forward, K, T, descuento, es_call)

    iv_mid = iv(captura.mid[filas] - e)
    iv_bid = iv(captura.bid[filas] - e)
    iv_ask = iv(captura.ask[filas] - e)
    k = np.log(K / forward)
    raiz_w = iv_mid * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (-k + 0.5 * raiz_w**2) / raiz_w
    delta = np.where(es_call, norm.cdf(d1), norm.cdf(d1) - 1.0)
    orden = np.argsort(k, kind="stable")
    return VolatilidadesObservadas(filas[orden], K[orden], k[orden], es_call[orden], iv_mid[orden],
                                   iv_bid[orden], iv_ask[orden], delta[orden], float(forward),
                                   float(descuento), float(T))


def _tramo(x, objetivo, k, hueco_max):
    """Índices consecutivos ``(a, b)`` con ``x`` cruzando ``objetivo`` y ``k_b - k_a <= hueco_max``."""
    iguales = np.flatnonzero(x == objetivo)
    if len(iguales):
        return int(iguales[0]), int(iguales[0])
    for a in range(len(x) - 1):
        lo, hi = sorted((x[a], x[a + 1]))
        if lo < objetivo < hi:
            return (a, a + 1) if k[a + 1] - k[a] <= hueco_max else None
    return None


def _interpolar(x, objetivo, tramo, *series):
    a, b = tramo
    if a == b:
        return [float(s[a]) for s in series]
    peso = (objetivo - x[a]) / (x[b] - x[a])
    return [float(s[a] + peso * (s[b] - s[a])) for s in series]


def _lado(vols, es_call):
    m = (vols.es_call == es_call) & np.isfinite(vols.iv) & np.isfinite(vols.iv_bid) & np.isfinite(vols.iv_ask)
    return vols.k[m], vols.iv[m], vols.iv_bid[m], vols.iv_ask[m], vols.delta[m]


def asimetria_simetrica(vols: VolatilidadesObservadas, distancia=0.03, hueco_max=0.02):
    """Call OTM en ``k = +d`` frente a put OTM en ``k = -d``, con ``d = ln(1 + distancia)``.

    Los strikes son simétricos en logaritmo alrededor del forward (``F e^{±d}``),
    no ``F (1 ± distancia)``. No es un par de paridad: mide asimetría de precios
    de cola. Con sonrisa simétrica ``P(F e^{-d}) = e^{-d} C(F e^{d})``, así que la
    comparación de primas brutas usa ``razon_simetrica = P / (e^{-d} C) - 1``, que
    vale 0 sin asimetría. Solo se interpola entre strikes válidos separados a lo
    sumo ``hueco_max`` en ``k``; si no, la medida queda «no identificada».
    """
    d = float(np.log1p(distancia))
    salida = {"estado": "no identificada", "motivo": "", "k": d}
    resultado = {}
    for nombre, es_call, objetivo in (("call", True, d), ("put", False, -d)):
        k, iv, iv_b, iv_a, _ = _lado(vols, es_call)
        tramo = _tramo(k, objetivo, k, hueco_max) if len(k) > 1 else None
        if tramo is None:
            salida["motivo"] = f"sin strikes {nombre} válidos a menos de {hueco_max} de k = {objetivo:+.4f}"
            return salida
        resultado[nombre] = _interpolar(k, objetivo, tramo, iv, iv_b, iv_a)
    (sc, sc_b, sc_a), (sp, sp_b, sp_a) = resultado["call"], resultado["put"]
    F, D, T = vols.forward, vols.descuento, vols.T
    prima_c = float(precio_black(F, F * np.exp(d), sc**2 * T, D, True))
    prima_p = float(precio_black(F, F * np.exp(-d), sp**2 * T, D, False))

    def griegas(k, s, es_call):
        raiz_w = s * np.sqrt(T)
        d1 = (-k + 0.5 * raiz_w**2) / raiz_w
        delta = norm.cdf(d1) if es_call else norm.cdf(d1) - 1.0
        return float(delta), float(D * F * norm.pdf(d1) * np.sqrt(T))

    delta_c, vega_c = griegas(d, sc, True)
    delta_p, vega_p = griegas(-d, sp, False)
    salida.update({
        "estado": "identificada",
        "iv_call": sc, "iv_call_banda": (sc_b, sc_a),
        "iv_put": sp, "iv_put_banda": (sp_b, sp_a),
        "diferencia_iv": sp - sc, "diferencia_iv_banda": (sp_b - sc_a, sp_a - sc_b),
        "prima_call": prima_c, "prima_put": prima_p,
        "razon_simetrica": prima_p / (np.exp(-d) * prima_c) - 1.0,
        "delta_call": delta_c, "delta_put": delta_p, "vega_call": vega_c, "vega_put": vega_p,
    })
    return salida


def asimetria_delta(vols: VolatilidadesObservadas, delta=0.25, hueco_max=0.05):
    """Diferencia de IV entre el put con delta ``-delta`` y el call con delta ``+delta``.

    La delta es forward y usa la IV de cada opción. Positiva: los puts OTM son
    más caros en volatilidad (la asimetría habitual de un índice).
    """
    salida = {"estado": "no identificada", "motivo": "", "delta": delta}
    resultado = {}
    for nombre, es_call in (("call", True), ("put", False)):
        k, iv, iv_b, iv_a, dl = _lado(vols, es_call)
        x = np.abs(dl)
        tramo = _tramo(x, delta, k, hueco_max) if len(k) > 1 else None
        if tramo is None:
            salida["motivo"] = f"ningún tramo de {nombre}s válidos cruza |delta| = {delta}"
            return salida
        resultado[nombre] = _interpolar(x, delta, tramo, iv, iv_b, iv_a, k)
    (sc, sc_b, sc_a, kc), (sp, sp_b, sp_a, kp) = resultado["call"], resultado["put"]
    salida.update({
        "estado": "identificada", "iv_call": sc, "iv_put": sp, "k_call": kc, "k_put": kp,
        "diferencia_iv": sp - sc, "diferencia_iv_banda": (sp_b - sc_a, sp_a - sc_b),
    })
    return salida


def pendiente_local(vols: VolatilidadesObservadas, ventana=0.05, minimo=3):
    """Pendiente ``d sigma / d k`` en ``k = 0`` por mínimos cuadrados ponderados.

    Usa las IV OTM con ``|k| <= ventana``; cada punto pesa con el inverso del
    cuadrado de su medio ancho en IV, y el error estándar supone ese medio
    ancho como desviación del ruido.
    """
    m = (np.abs(vols.k) <= ventana) & np.isfinite(vols.iv) & np.isfinite(vols.iv_bid) & np.isfinite(vols.iv_ask)
    k, iv = vols.k[m], vols.iv[m]
    medio = np.maximum(0.5 * (vols.iv_ask[m] - vols.iv_bid[m]), 1e-6)
    if len(k) < minimo or not (np.any(k < 0) and np.any(k > 0)):
        return {"estado": "no identificada", "motivo": f"menos de {minimo} puntos o un solo lado del forward",
                "n": int(len(k))}
    w = 1.0 / medio**2
    km, ym = np.average(k, weights=w), np.average(iv, weights=w)
    sxx = np.sum(w * (k - km) ** 2)
    b = np.sum(w * (k - km) * (iv - ym)) / sxx
    return {"estado": "identificada", "motivo": "", "pendiente": float(b),
            "error": float(np.sqrt(1.0 / sxx)), "nivel_atm": float(ym - b * km), "n": int(len(k))}


# ---------------------------------------------------------------------------
# Serie observada, serie ajustada e informe
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class ResultadoObservado:
    """Todo lo calculado con cotizaciones crudas de una captura."""

    captura: Captura
    controles: Controles
    paridad: ResiduosParidad
    volatilidades: VolatilidadesObservadas
    asimetria: dict
    asimetria_delta: dict
    pendiente: dict
    primas: np.ndarray  # prima de ejercicio anticipado por fila (0 en europeas, NaN sin estimar)
    alertas: tuple = field(default_factory=tuple)


def procesar_captura(captura: Captura, reglas: ReglasCalidad = ReglasCalidad(), distancia=0.03,
                     delta=0.25, hueco_max=0.02, n_arbol=200) -> ResultadoObservado:
    """Controles, paridad, volatilidades y asimetrías de una captura (serie observada)."""
    controles = controlar(captura, reglas)
    primas = primas_ejercicio(captura, np.flatnonzero(controles.valida), n_arbol)
    paridad = residuos_paridad(captura, controles, primas)
    alertas = list(paridad.alertas)
    F, D = paridad.forward_global, paridad.descuento_global
    if not np.isfinite(F):
        F, D = captura.forward_contractual, captura.descuento_contractual
        alertas.append("forward contractual: la paridad no permitió estimarlo")
    vols = volatilidades_observadas(captura, controles, F, D, primas, n_arbol)
    return ResultadoObservado(captura, controles, paridad, vols,
                              asimetria_simetrica(vols, distancia, hueco_max),
                              asimetria_delta(vols, delta), pendiente_local(vols), primas,
                              tuple(alertas))


@dataclass(frozen=True, eq=False)
class AjusteCaptura:
    """Serie **ajustada**: rebanada SSVI sin arbitraje y medidas leídas de ella.

    La paridad se cumple por construcción en el ajuste (``residuo_paridad`` es
    cero en todos los strikes): por eso nunca sustituye a la serie observada.
    """

    theta: float
    rho: float
    phi: float
    cotizaciones_fuera: int
    diferencia_iv: float  # sigma(-d) - sigma(+d)
    pendiente: float  # d sigma / d k en k = 0
    residuo_paridad: np.ndarray


def ajustar_captura(resultado: ResultadoObservado, distancia=0.03, peso_mid=0.02) -> AjusteCaptura:
    """Ajusta una rebanada SSVI a las cotizaciones OTM válidas sin tocar ``resultado``."""
    v, c, e = resultado.volatilidades, resultado.captura, resultado.primas
    reb = Rebanada(T=v.T, F=v.forward, D=v.descuento, K=v.strike.copy(),
                   bid=c.bid[v.fila] - e[v.fila], ask=c.ask[v.fila] - e[v.fila],
                   es_call=v.es_call.copy())
    rebanada, _ = ajustar_rebanada(reb, peso_mid=peso_mid)
    k = np.log(reb.K / reb.F)
    ajustados = precio_black(reb.F, reb.K, rebanada.w(k), reb.D, reb.es_call)
    fuera = int(np.sum((ajustados < reb.bid - 1e-9) | (ajustados > reb.ask + 1e-9)))
    d = float(np.log1p(distancia))
    s_mas, s_menos = np.sqrt(rebanada.w(np.array([d, -d])) / v.T)
    w0, w1, _ = rebanada.derivadas(np.array([0.0]))
    K_par = resultado.paridad.strike
    w_par = rebanada.w(np.log(K_par / reb.F))
    residuo = (precio_black(reb.F, K_par, w_par, reb.D, True)
               - precio_black(reb.F, K_par, w_par, reb.D, False) - reb.D * (reb.F - K_par))
    return AjusteCaptura(rebanada.theta, rebanada.rho, rebanada.phi, fuera, float(s_menos - s_mas),
                         float(w1[0] / (2.0 * np.sqrt(w0[0] * v.T))), residuo)


def fila_informe(resultado: ResultadoObservado, ajuste: AjusteCaptura | None = None) -> dict:
    """Fila plana del informe diario: ``obs_*`` (crudo) y ``aj_*`` (ajustado) por separado."""
    c, p = resultado.captura, resultado.paridad
    a, ad, pl = resultado.asimetria, resultado.asimetria_delta, resultado.pendiente
    nan = float("nan")
    fila = {
        "fecha": c.fecha, "corte": c.corte,
        "tipo_captura": "apertura" if c.corte <= 12 * 3600 else "cierre",
        "ejercicio": c.ejercicio, "filas": len(c.strike),
        "filas_validas": int(resultado.controles.valida.sum()),
        "exclusiones": resultado.controles.resumen(),
        "strikes_sin_pareja": len(p.sin_pareja), "alertas": resultado.alertas,
        "obs_forward": p.forward_global, "obs_descuento": p.descuento_global,
        "obs_paridad_pares": len(p.strike),
        "obs_paridad_mediana_multiplo": float(np.nanmedian(np.abs(p.multiplo_ancho)))
        if np.any(np.isfinite(p.multiplo_ancho)) else nan,
        "obs_paridad_fuera_de_banda": int(p.fuera_de_banda.sum()),
        "obs_paridad_interpretables": int(p.interpretable.sum()),
        "obs_asimetria_estado": a["estado"],
        "obs_dif_iv_k": a.get("diferencia_iv", nan),
        "obs_dif_iv_k_inferior": a.get("diferencia_iv_banda", (nan, nan))[0],
        "obs_dif_iv_k_superior": a.get("diferencia_iv_banda", (nan, nan))[1],
        "obs_prima_call_k": a.get("prima_call", nan), "obs_prima_put_k": a.get("prima_put", nan),
        "obs_razon_simetrica": a.get("razon_simetrica", nan),
        "obs_dif_iv_delta": ad.get("diferencia_iv", nan),
        "obs_pendiente": pl.get("pendiente", nan), "obs_pendiente_error": pl.get("error", nan),
    }
    if ajuste is not None:
        fila.update({
            "aj_theta": ajuste.theta, "aj_rho": ajuste.rho, "aj_phi": ajuste.phi,
            "aj_cotizaciones_fuera": ajuste.cotizaciones_fuera, "aj_dif_iv_k": ajuste.diferencia_iv,
            "aj_pendiente": ajuste.pendiente,
            "aj_paridad_max_abs": float(np.max(np.abs(ajuste.residuo_paridad)))
            if len(ajuste.residuo_paridad) else nan,
        })
    return fila


def diferencia_diaria(actual: dict, anterior: dict, feriados=()) -> dict:
    """Cambio de cada medida numérica entre dos filas, con el calendario explícito.

    Registra días naturales y sesiones transcurridas (``np.busday_count`` con
    ``feriados``) y el tipo de comparación (apertura–apertura, cierre–apertura):
    un fin de semana no se trata como una sesión ordinaria.
    """
    fecha, previa = np.datetime64(actual["fecha"]), np.datetime64(anterior["fecha"])
    if fecha <= previa:
        raise ValueError("la fila anterior debe ser de una fecha previa")
    dias = int((fecha - previa).astype(int))
    sesiones = int(np.busday_count(previa, fecha, holidays=list(feriados)))
    salida = {
        "fecha": actual["fecha"], "fecha_anterior": anterior["fecha"],
        "tipo": f"{anterior['tipo_captura']}–{actual['tipo_captura']}",
        "dias_naturales": dias, "sesiones": sesiones, "cruza_dias_no_habiles": dias > sesiones,
    }
    for clave, valor in actual.items():
        previo = anterior.get(clave)
        if (clave.startswith(("obs_", "aj_")) and isinstance(valor, (int, float))
                and isinstance(previo, (int, float)) and not isinstance(valor, bool)):
            salida["cambio_" + clave] = float(valor) - float(previo)
    return salida
