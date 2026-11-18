"""Sincronización y filtros. Aquí nacen los arbitrajes falsos.

Dos cosas fabrican holonomía donde no la hay:

1. **Asincronía.** Si una pata del ciclo se cotizó hace diez segundos y las
   otras hace un milisegundo, la holonomía que sale no mide inconsistencia del
   mercado: mide la deriva del precio en esos diez segundos. Por eso un ciclo
   sólo se evalúa si **todas** sus patas tienen cotización con antigüedad ≤ Δt.
2. **Cotizaciones rotas.** Mercados cruzados o bloqueados (``bid ≥ ask``),
   bids en cero y spreads absurdos.

Todo se registra: cuántas filas y cuántos instantes se descartan y por qué.

Sin mirar hacia adelante (regla 4). El panel se arma con semántica *asof*:
en el instante ``t`` cada par lleva su última cotización con sello del
exchange **≤ t**, nunca la siguiente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .holonomia import Comisiones

CAMPOS = ("bid", "ask", "bid_size", "ask_size", "ts_exchange")


@dataclass
class Registro:
    """Cuenta de lo que se descartó y por qué."""

    filas_entrada: int = 0
    filas_salida: int = 0
    motivos: dict[str, int] = field(default_factory=dict)

    def anotar(self, motivo: str, n: int) -> None:
        if n:
            self.motivos[motivo] = self.motivos.get(motivo, 0) + int(n)

    def como_tabla(self) -> pd.DataFrame:
        filas = [{"motivo": k, "filas": v, "fraccion": v / max(self.filas_entrada, 1)}
                 for k, v in sorted(self.motivos.items(), key=lambda kv: -kv[1])]
        return pd.DataFrame(filas)

    def __str__(self) -> str:
        partes = [f"{self.filas_entrada} filas -> {self.filas_salida}"]
        partes += [f"  {k}: {v}" for k, v in sorted(self.motivos.items(), key=lambda kv: -kv[1])]
        return "\n".join(partes)


def filtrar(df: pd.DataFrame, medio_spread_max: float = 0.05,
            exigir_tamanos: bool = False) -> tuple[pd.DataFrame, Registro]:
    """Quita cotizaciones no utilizables y devuelve el registro de descartes.

    ``medio_spread_max`` está en logaritmos: 0.05 son unos 500 puntos base de
    medio spread, que para cripto líquido ya es absurdo.
    """
    reg = Registro(filas_entrada=len(df))
    if df.empty:
        reg.filas_salida = 0
        return df.copy(), reg

    vivo = pd.Series(True, index=df.index)

    malos = ~np.isfinite(df["bid"]) | ~np.isfinite(df["ask"])
    reg.anotar("no finitos", int((malos & vivo).sum()))
    vivo &= ~malos

    malos = (df["bid"] <= 0) | (df["ask"] <= 0)
    reg.anotar("precio no positivo", int((malos & vivo).sum()))
    vivo &= ~malos

    malos = df["bid"] >= df["ask"]
    reg.anotar("cruzado o bloqueado", int((malos & vivo).sum()))
    vivo &= ~malos

    with np.errstate(invalid="ignore", divide="ignore"):
        medio = 0.5 * np.log(df["ask"].to_numpy() / df["bid"].to_numpy())
    malos = pd.Series(~np.isfinite(medio) | (medio > medio_spread_max), index=df.index)
    reg.anotar("medio spread absurdo", int((malos & vivo).sum()))
    vivo &= ~malos

    if exigir_tamanos:
        malos = ~(df["bid_size"] > 0) | ~(df["ask_size"] > 0)
        reg.anotar("tamaño nulo", int((malos & vivo).sum()))
        vivo &= ~malos

    salida = df[vivo].copy()
    reg.filas_salida = len(salida)
    return salida, reg


def panel(df: pd.DataFrame, simbolos=None, malla=None) -> pd.DataFrame:
    """Panel *asof*: en cada instante, la última cotización de cada par.

    Las columnas son un ``MultiIndex`` ``(símbolo, campo)`` con los campos de
    ``CAMPOS``. La malla, si no se da, es la unión de los sellos del exchange
    de los pares pedidos: un reloj de eventos, sin muestreo arbitrario.
    """
    simbolos = sorted(df["par"].unique()) if simbolos is None else list(simbolos)
    faltan = [s for s in simbolos if s not in set(df["par"])]
    if faltan:
        raise KeyError(f"el marco no trae estos pares: {faltan}")

    sub = df[df["par"].isin(simbolos)]
    if malla is None:
        malla = pd.DatetimeIndex(sorted(sub["ts_exchange"].unique()))
    else:
        malla = pd.DatetimeIndex(malla)

    trozos = {}
    for s in simbolos:
        d = (sub[sub["par"] == s]
             .sort_values("ts_exchange", kind="stable")
             .drop_duplicates("ts_exchange", keep="last")
             .set_index("ts_exchange"))
        d = d[["bid", "ask", "bid_size", "ask_size"]]
        d["ts_exchange"] = d.index
        trozos[s] = d.reindex(malla, method="ffill")   # asof: nada del futuro

    salida = pd.concat(trozos, axis=1)
    salida.columns = pd.MultiIndex.from_tuples(salida.columns)
    salida.index.name = "t"
    return salida


def edades(p: pd.DataFrame) -> pd.DataFrame:
    """Antigüedad en segundos de la cotización vigente de cada par."""
    simbolos = sorted({c[0] for c in p.columns})
    t = p.index.to_series()
    return pd.DataFrame(
        {s: (t - p[(s, "ts_exchange")]).dt.total_seconds() for s in simbolos},
        index=p.index)


def _resolver(paso: tuple[str, str], simbolos) -> tuple[str, int]:
    """Devuelve el símbolo que cotiza el paso ``a → b`` y su sentido.

    Sentido ``+1``: ``a`` es la base y se vende al bid.
    Sentido ``-1``: ``b`` es la base y se compra al ask.
    """
    a, b = paso
    if f"{a}/{b}" in simbolos:
        return f"{a}/{b}", +1
    if f"{b}/{a}" in simbolos:
        return f"{b}/{a}", -1
    raise KeyError(f"ningún par cotiza el paso {a} → {b}")


def pasos_de_ciclo(ciclo) -> list[tuple[str, str]]:
    nodos = list(ciclo)
    if len(nodos) > 1 and nodos[0] == nodos[-1]:
        nodos = nodos[:-1]
    return list(zip(nodos, nodos[1:] + nodos[:1]))


def serie_de_ciclo(p: pd.DataFrame, ciclo, comisiones: Comisiones | None = None,
                   delta_t: float | None = 1.0, usar_taker: bool = True) -> pd.DataFrame:
    """Serie temporal de ``H_mid``, ``H_exec`` y el umbral, para un ciclo.

    Con ``delta_t`` en segundos se quedan sólo los instantes en que las tres
    (o L) patas tienen cotización de antigüedad ≤ Δt. Con ``delta_t=None`` no
    se sincroniza: eso es el control de asincronía, no una medición.

    Columnas: ``h_mid``, ``h_exec``, ``medio_spread``, ``umbral``, ``edad_max``.
    """
    comisiones = comisiones or Comisiones.alpaca(1)
    f = comisiones.taker if usar_taker else comisiones.maker
    log1mf = math.log1p(-f)

    simbolos = {c[0] for c in p.columns}
    pasos = pasos_de_ciclo(ciclo)

    h_mid = np.zeros(len(p))
    h_exec = np.zeros(len(p))
    medio_spread = np.zeros(len(p))
    usados = []
    for paso in pasos:
        s, sentido = _resolver(paso, simbolos)
        usados.append(s)
        bid = p[(s, "bid")].to_numpy(dtype=float)
        ask = p[(s, "ask")].to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            lbid, lask = np.log(bid), np.log(ask)
        lmid = 0.5 * (lbid + lask)          # medio geométrico
        s_medio = 0.5 * (lask - lbid)
        h_mid += sentido * lmid
        medio_spread += s_medio
        h_exec += (lbid if sentido > 0 else -lask) + log1mf

    edad = edades(p)[usados].max(axis=1).to_numpy()
    salida = pd.DataFrame({
        "h_mid": h_mid,
        "h_exec": h_exec,
        "medio_spread": medio_spread,
        "umbral": medio_spread - len(pasos) * log1mf,
        "edad_max": edad,
    }, index=p.index)

    salida = salida[np.isfinite(salida[["h_mid", "h_exec", "medio_spread"]]).all(axis=1)]
    if delta_t is not None:
        salida = salida[salida["edad_max"] <= delta_t]
    return salida


def cocadenas_del_panel(p: pd.DataFrame, g, delta_t: float | None = 1.0):
    """Genera ``(t, A_mid)`` para los instantes en que **todo** el grafo está fresco.

    Es lo que necesita la descomposición de Hodge: una cocadena completa, sin
    huecos. Con muchos pares esto se vuelve raro muy rápido, y esa escasez es
    en sí misma un resultado que hay que reportar.
    """
    simbolos = sorted({c[0] for c in p.columns})
    indice = g.indice_arista
    columnas = []
    for s in simbolos:
        base, cotizada = s.split("/")
        par = (base, cotizada) if base < cotizada else (cotizada, base)
        if par not in indice:
            continue
        columnas.append((s, indice[par], 1.0 if base < cotizada else -1.0))

    if len(columnas) != g.n_aristas:
        raise ValueError(f"el panel cubre {len(columnas)} de las {g.n_aristas} aristas del grafo")

    ed = edades(p)[[s for s, _, _ in columnas]].max(axis=1).to_numpy()
    A = np.full((len(p), g.n_aristas), np.nan)
    for s, k, signo in columnas:
        bid = p[(s, "bid")].to_numpy(dtype=float)
        ask = p[(s, "ask")].to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            A[:, k] = signo * 0.5 * (np.log(bid) + np.log(ask))

    completo = np.isfinite(A).all(axis=1)
    if delta_t is not None:
        completo &= ed <= delta_t
    for t, fila in zip(p.index[completo], A[completo]):
        yield t, fila
