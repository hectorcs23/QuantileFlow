"""Las mediciones de §2.5: distribución, ejecutabilidad, persistencia y reparto.

Todo lo de aquí consume un panel ya sincronizado y devuelve tablas. Nada
grafica: las figuras se arman en los cuadernos a partir de estas tablas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import hodge
from .grafo import Grafo, desde_aristas
from .holonomia import Comisiones
from .limpieza import edades, pasos_de_ciclo, serie_de_ciclo

PB = 1e4   # un punto base en logaritmos ≈ 1e-4


def resumen_de_ciclo(p: pd.DataFrame, ciclo, comisiones: Comisiones | None = None,
                     delta_t: float = 1.0) -> dict:
    """Una fila de resumen para un ciclo: tamaño, costo y ejecutabilidad.

    Todo en puntos base de log-retorno. ``dentro_del_spread`` es la fracción
    de instantes en que ``|H_mid|`` no llega al medio spread del ciclo: ahí la
    inconsistencia no es explotable ni con comisión cero.
    """
    s = serie_de_ciclo(p, ciclo, comisiones, delta_t=delta_t)
    if s.empty:
        return {"ciclo": " → ".join(ciclo), "longitud": len(ciclo), "instantes": 0}
    h = s["h_mid"].to_numpy()
    return {
        "ciclo": " → ".join(ciclo),
        "longitud": len(ciclo),
        "instantes": int(len(s)),
        "mediana_abs_h_mid_pb": float(np.median(np.abs(h)) * PB),
        "p99_abs_h_mid_pb": float(np.quantile(np.abs(h), 0.99) * PB),
        "max_abs_h_mid_pb": float(np.max(np.abs(h)) * PB),
        "sesgo_h_mid_pb": float(np.mean(h) * PB),
        "mediana_medio_spread_pb": float(s["medio_spread"].median() * PB),
        "mediana_umbral_pb": float(s["umbral"].median() * PB),
        "frac_fuera_del_spread": float((np.abs(h) > s["medio_spread"]).mean()),
        "frac_h_exec_positiva": float((s["h_exec"] > 0).mean()),
        "max_h_exec_pb": float(s["h_exec"].max() * PB),
        "mediana_edad_max_s": float(s["edad_max"].median()),
    }


def resumen_por_ciclo(p: pd.DataFrame, ciclos, comisiones: Comisiones | None = None,
                      delta_t: float = 1.0) -> pd.DataFrame:
    """``resumen_de_ciclo`` para una lista de ciclos, ordenado por tamaño."""
    filas = [resumen_de_ciclo(p, c, comisiones, delta_t) for c in ciclos]
    df = pd.DataFrame(filas)
    if "mediana_abs_h_mid_pb" in df:
        df = df.sort_values("mediana_abs_h_mid_pb", ascending=False)
    return df.reset_index(drop=True)


def en_malla_regular(s: pd.DataFrame, columna: str, paso: str = "1s") -> pd.Series:
    """Lleva una serie de eventos a una malla regular tomando el último valor.

    Sin mirar al futuro: cada casilla se queda con el último dato de su
    intervalo. Las casillas sin dato quedan en NaN y no se rellenan: un hueco
    es un hueco, no una observación repetida.
    """
    return s[columna].resample(paso).last()


def autocorrelacion(serie: pd.Series, max_lag: int = 120) -> pd.Series:
    """ACF de una serie en malla regular, saltando los huecos."""
    x = serie.to_numpy(dtype=float)
    valido = np.isfinite(x)
    x = np.where(valido, x, np.nan)
    media = np.nanmean(x)
    centrado = x - media
    var = np.nanmean(centrado ** 2)
    out = {}
    for k in range(max_lag + 1):
        a = centrado[: len(centrado) - k] if k else centrado
        b = centrado[k:]
        par = np.isfinite(a) & np.isfinite(b)
        out[k] = float(np.mean(a[par] * b[par]) / var) if par.sum() > 10 and var > 0 else np.nan
    return pd.Series(out, name="acf")


def vida_media(acf: pd.Series) -> float:
    """Primer retardo en que la ACF baja de ½, interpolado linealmente.

    Devuelve ``nan`` si nunca baja de ½ dentro de los retardos calculados: eso
    significa que la inconsistencia dura más que la ventana mirada.
    """
    v = acf.dropna()
    if v.empty:
        return float("nan")
    bajo = v[v < 0.5]
    if bajo.empty:
        return float("nan")
    k = int(bajo.index[0])
    pos = v.index.get_loc(k)
    if pos == 0:
        return 0.0
    # El retardo anterior *disponible*: la ACF puede tener huecos, y entonces
    # k − 1 no existe. Se interpola entre los dos retardos que sí están.
    k_previo = int(v.index[pos - 1])
    y1, y0 = float(v.iloc[pos]), float(v.iloc[pos - 1])
    if y0 == y1:
        return float(k)
    return float(k_previo + (y0 - 0.5) * (k - k_previo) / (y0 - y1))


def volatilidad_realizada(p: pd.DataFrame, simbolo: str, paso: str = "1min") -> pd.Series:
    """Volatilidad realizada por casilla, en puntos base de log-retorno.

    Raíz de la suma de cuadrados de los log-retornos del medio dentro de cada
    casilla: la medida de actividad que pide §2.5.
    """
    bid = p[(simbolo, "bid")].astype(float)
    ask = p[(simbolo, "ask")].astype(float)
    lmid = 0.5 * (np.log(bid) + np.log(ask))
    r = lmid.diff()
    return np.sqrt((r ** 2).resample(paso).sum()) * PB


def intensidad(p: pd.DataFrame, simbolos, paso: str = "1min") -> pd.Series:
    """Cotizaciones nuevas por casilla, sumando los pares pedidos."""
    cuenta = None
    for s in simbolos:
        nuevo = p[(s, "ts_exchange")].ne(p[(s, "ts_exchange")].shift()).resample(paso).sum()
        cuenta = nuevo if cuenta is None else cuenta + nuevo
    return cuenta


def subgrafo_fresco(g: Grafo, frescas: set[tuple[str, str]]) -> Grafo:
    """Complejo de las aristas frescas, con **sus** triángulos como 2-celdas.

    Es la lectura literal de §2.4.4: las 2-celdas son los triángulos
    operables. Como la frescura cambia con el tiempo, el complejo cambia con
    el tiempo, y con él ``b₁``: la parte armónica aparece justo cuando la
    liquidez deja de rellenar un hueco.
    """
    aristas = [e for e in g.aristas if e in frescas]
    return desde_aristas(aristas)


def reparto_en_el_tiempo(p: pd.DataFrame, g: Grafo, delta_t: float = 1.0,
                         malla: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Reparto gradiente / rotacional / armónico instante a instante.

    En cada instante se arma el complejo con las aristas frescas y se
    descompone la cocadena restringida a ellas. Devuelve, por instante, las
    tres fracciones de energía, ``b₁`` del complejo fresco y cuántas aristas
    y caras tenía.
    """
    simbolos = sorted({c[0] for c in p.columns})
    por_arista = {}
    for s in simbolos:
        base, cot = s.split("/")
        por_arista[(base, cot) if base < cot else (cot, base)] = (s, 1.0 if base < cot else -1.0)

    ed = edades(p)
    indice = p.index if malla is None else p.index.intersection(pd.DatetimeIndex(malla))
    # El complejo sólo depende de *qué* aristas están frescas, y ese conjunto
    # toma pocos valores distintos a lo largo del día: vale la pena guardarlo.
    # b₁ se calcula por rango de matriz y es lo caro de todo esto.
    memo: dict[frozenset, tuple[Grafo, int]] = {}
    filas = []
    for t in indice:
        frescas = frozenset(e for e, (s, _) in por_arista.items() if ed.at[t, s] <= delta_t)
        if len(frescas) < 3:
            continue
        if frescas not in memo:
            gfr = subgrafo_fresco(g, set(frescas))
            memo[frescas] = (gfr, gfr.betti1() if gfr.n_aristas >= 3 else 0)
        gf, b1 = memo[frescas]
        if gf.n_aristas < 3:
            continue
        valores = {}
        ok = True
        for e in gf.aristas:
            s, signo = por_arista[e]
            b, a = p.at[t, (s, "bid")], p.at[t, (s, "ask")]
            if not (b > 0 and a > 0):
                ok = False
                break
            valores[e] = signo * 0.5 * (np.log(b) + np.log(a))
        if not ok:
            continue
        A = gf.cocadena({(i, j): v for (i, j), v in valores.items()})
        d = hodge.descomponer(gf, A)
        fr, frc = d.fracciones(), d.fracciones_de_curvatura()
        filas.append({
            "t": t,
            "aristas": gf.n_aristas, "caras": gf.n_caras, "b1": b1,
            "norma_rotacional_pb": float(np.linalg.norm(d.rotacional)) * PB,
            "norma_armonica_pb": float(np.linalg.norm(d.armonico)) * PB,
            "norma_curvatura_pb": d.norma_curvatura() * PB,
            # La fracción sobre ‖A‖² es casi toda gradiente por la escala de
            # los log-precios; la que informa es el reparto de la curvatura.
            "frac_gradiente": fr["gradiente"],
            "frac_rotacional": fr["rotacional"],
            "frac_armonico": fr["armonico"],
            "curv_frac_rotacional": frc["rotacional"],
            "curv_frac_armonica": frc["armonico"],
        })
    return pd.DataFrame(filas).set_index("t") if filas else pd.DataFrame()


def sensibilidad_delta_t(p: pd.DataFrame, ciclo, comisiones: Comisiones | None = None,
                         deltas=(10.0, 3.0, 1.0, 0.3, 0.1, 0.03, 0.01)) -> pd.DataFrame:
    """Cómo cambia la holonomía al apretar la ventana de sincronización.

    Si ``|H_mid|`` baja al apretar Δt, lo que se estaba midiendo era
    asincronía. Si se queda igual, es inconsistencia de verdad.
    """
    filas = []
    for dt in deltas:
        s = serie_de_ciclo(p, ciclo, comisiones, delta_t=dt)
        if s.empty:
            continue
        filas.append({
            "delta_t_s": dt,
            "instantes": int(len(s)),
            "mediana_abs_h_mid_pb": float(np.median(np.abs(s["h_mid"])) * PB),
            "p90_abs_h_mid_pb": float(np.quantile(np.abs(s["h_mid"]), 0.90) * PB),
            "mediana_edad_max_s": float(s["edad_max"].median()),
        })
    return pd.DataFrame(filas)


def holonomia_por_antiguedad(p: pd.DataFrame, ciclo, delta_t: float = 1.0,
                             n_cortes: int = 8) -> pd.DataFrame:
    """``|H_mid|`` por cuantil de antigüedad de la pata más rancia.

    Complemento necesario de ``sensibilidad_delta_t``. Apretar Δt no sólo
    quita cotizaciones viejas: también selecciona los instantes en que las
    tres patas cotizaron casi a la vez, que son ráfagas de actividad. Esta
    tabla separa los dos efectos, porque mira la antigüedad **dentro de una
    sola ventana**, sin cambiar la muestra.

    Si ``|H_mid|`` crece con la antigüedad, parte de lo medido es rancidez.
    Si sale plano, la holonomía no viene de la asincronía.
    """
    s = serie_de_ciclo(p, ciclo, delta_t=delta_t)
    if len(s) < 10 * n_cortes:
        return pd.DataFrame()
    s = s.assign(abs_h=lambda d: d["h_mid"].abs() * PB)
    try:
        cortes = pd.qcut(s["edad_max"], n_cortes, duplicates="drop")
    except ValueError:
        return pd.DataFrame()
    g = s.groupby(cortes, observed=True)
    return pd.DataFrame({
        "edad_mediana_s": g["edad_max"].median(),
        "mediana_abs_h_mid_pb": g["abs_h"].median(),
        "p90_abs_h_mid_pb": g["abs_h"].quantile(0.90),
        "instantes": g.size(),
    }).reset_index(drop=True)
