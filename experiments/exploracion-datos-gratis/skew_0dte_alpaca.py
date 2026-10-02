"""Exploración del skew intradía 0DTE de SPY con las operaciones gratuitas de Alpaca.

Sigue la parte estadística del experimento ``codex/0dte-skew-reversion``: ¿una desviación del skew a 25
delta, normalizada por hora, converge en 30 minutos? Usa sus parámetros: cuadrícula de 5 minutos desde
las 09:40, señales hasta 45 minutos antes del cierre, |z| >= 2, base de las 60 sesiones anteriores con al
menos 20 observaciones, entrada 5 minutos después de la señal, salida 30 minutos después de la entrada y
bootstrap circular por bloques de 10 sesiones, con 3 000 repeticiones y semilla 1729.

Diferencias con el experimento, todas por los datos:

- **Precio:** el de cada contrato es el VWAP de su última barra de 1 minuto con operaciones en los 5
  minutos previos a cada punto de la cuadrícula. No hay compra/venta histórica.
- **IV y delta:** se calculan aquí con Black-Scholes (r = 4.5 %, sin dividendos) y el VWAP de SPY del mismo
  minuto. No hay griegas del proveedor.
- **Convergencia:** se mide de dos maneras.
  - *Ingenua*, como en el experimento: ``d * (residuo[t+30] - residuo[t])``.
  - *Operable*: ``d * (residuo[t+35] - residuo[t+5])``, el intervalo entre la entrada y la salida.

  Si la medida tiene ruido, la ingenua revierte por construcción y la operable no. Aquí ``d = -signo
  del residuo en t``.
- **Sin ganancia:** no se mide la ganancia después de costos, porque hacen falta compra y venta.

RR25 = 100 * (IV put 25 delta - IV call 25 delta), en puntos de volatilidad, con el convenio del
experimento: el piloto usa call - put. Solo escribe agregados.

Uso, desde la raíz del repositorio, después de ``descargar_0dte_alpaca.py``::

    python experiments/exploracion-datos-gratis/skew_0dte_alpaca.py
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "data" / "exploracion" / "0dte"
SALIDA = Path(__file__).resolve().parent / "resultados"
NY = "America/New_York"
TASA = 0.045
PRIMER_MINUTO = 9 * 60 + 40
PASO = 5
ULTIMA_SENAL_ANTES = 45
DELTA = 0.25
HUECO_DELTA = 0.15
BASE_SESIONES, BASE_MINIMO = 60, 20
UMBRAL_Z = 2.0
ESPERA, HORIZONTE = 5, 30
HORIZONTES_SECUNDARIOS = (10, 20, 45)  # solo descriptivos: el horizonte fijado es 30
PRECIO_MINIMO = 0.05
SIMBOLO = re.compile(r"^SPY(\d{6})([CP])(\d{8})$")


def precio_bs(S, K, T, sigma, call):
    raiz = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (TASA + 0.5 * sigma ** 2) * T) / raiz
    d2 = d1 - raiz
    descuento = np.exp(-TASA * T)
    return np.where(call, S * norm.cdf(d1) - K * descuento * norm.cdf(d2),
                    K * descuento * norm.cdf(-d2) - S * norm.cdf(-d1))


def iv_y_delta(precio, S, K, T, call):
    """IV por bisección vectorial entre 1 % y 500 %, y delta de Black-Scholes. NaN si no hay solución."""
    precio, S, K, T, call = map(np.asarray, (precio, S, K, T, call))
    bajo, alto = np.full(precio.shape, 0.01), np.full(precio.shape, 5.0)
    valido = (precio > precio_bs(S, K, T, bajo, call)) & (precio < precio_bs(S, K, T, alto, call))
    for _ in range(60):
        medio = 0.5 * (bajo + alto)
        caro = precio_bs(S, K, T, medio, call) > precio
        alto, bajo = np.where(caro, medio, alto), np.where(caro, bajo, medio)
    sigma = np.where(valido, 0.5 * (bajo + alto), np.nan)
    d1 = (np.log(S / K) + (TASA + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return sigma, np.where(call, norm.cdf(d1), norm.cdf(d1) - 1)


def interpolar(deltas, ivs):
    """IV a |delta| 0.25 entre los dos contratos que la rodean, sin extrapolar. NaN si el hueco es mayor que 0.15."""
    d, v = np.abs(np.asarray(deltas, float)), np.asarray(ivs, float)
    ok = np.isfinite(d) & np.isfinite(v)
    d, v = d[ok], v[ok]
    arriba, abajo = d >= DELTA, d <= DELTA
    if not arriba.any() or not abajo.any():
        return np.nan
    i, j = np.argmin(np.where(arriba, d, np.inf)), np.argmax(np.where(abajo, d, -np.inf))
    if d[i] - d[j] > HUECO_DELTA:
        return np.nan
    if d[i] == d[j]:
        return float(v[i])
    return float(v[j] + (v[i] - v[j]) * (DELTA - d[j]) / (d[i] - d[j]))


def rr_de_la_sesion(registro):
    """RR25 en cada punto de la cuadrícula de una sesión: una serie indexada por minuto del día en Nueva York."""
    cierre = pd.Timestamp(registro["cierre_utc"])
    spy = pd.DataFrame(registro["spy"])
    if spy.empty:
        return pd.Series(dtype=float)
    spy["t"] = pd.to_datetime(spy["t"])
    spy = spy.set_index("t")["vw"]
    filas = []
    for simbolo, barras in registro["opciones"].items():
        m = SIMBOLO.match(simbolo)
        if not m or not barras:
            continue
        b = pd.DataFrame(barras)
        b["t"] = pd.to_datetime(b["t"])
        b["call"], b["K"] = m.group(2) == "C", int(m.group(3)) / 1000
        filas.append(b[["t", "vw", "n", "call", "K"]])
    if not filas:
        return pd.Series(dtype=float)
    op = pd.concat(filas)
    op = op[op["vw"] >= PRECIO_MINIMO]
    op["S"] = op["t"].map(spy)
    op = op.dropna(subset=["S"])
    op = op[(op["call"] & (op["K"] >= op["S"])) | (~op["call"] & (op["K"] <= op["S"]))]
    op["T"] = (cierre - op["t"] - pd.Timedelta(seconds=30)).dt.total_seconds() / (365 * 86400)
    op = op[op["T"] > 0]
    if op.empty:
        return pd.Series(dtype=float)
    iv, delta = iv_y_delta(op["vw"].to_numpy(), op["S"].to_numpy(), op["K"].to_numpy(), op["T"].to_numpy(),
                           op["call"].to_numpy())
    op["iv"], op["delta"] = iv, delta
    op["minuto"] = (op["t"].dt.tz_convert(NY).dt.hour * 60 + op["t"].dt.tz_convert(NY).dt.minute).astype(int)
    fin = cierre.tz_convert(NY).hour * 60 + cierre.tz_convert(NY).minute
    salida = {}
    for punto in range(PRIMER_MINUTO, fin - 10 + 1, PASO):
        ventana = op[(op["minuto"] > punto - PASO - 1) & (op["minuto"] <= punto - 1)]
        if ventana.empty:
            continue
        ultimo = ventana.sort_values("t").groupby(["K", "call"]).tail(1)
        put = interpolar(ultimo.loc[~ultimo["call"], "delta"], ultimo.loc[~ultimo["call"], "iv"])
        call = interpolar(ultimo.loc[ultimo["call"], "delta"], ultimo.loc[ultimo["call"], "iv"])
        if np.isfinite(put) and np.isfinite(call):
            salida[punto] = 100 * (put - call)
    return pd.Series(salida, dtype=float)


def base_horaria(tabla):
    """Media y desviación de cada franja con las 60 sesiones anteriores (mínimo 20). El día actual no entra."""
    previas = tabla.shift(1)
    return (previas.rolling(BASE_SESIONES, min_periods=BASE_MINIMO).mean(),
            previas.rolling(BASE_SESIONES, min_periods=BASE_MINIMO).std())


def bootstrap(valores_por_sesion, semilla=1729, repeticiones=3000, bloque=10):
    """IC del 95 % de la media sobre sesiones activas con bootstrap circular por bloques de sesiones."""
    v = np.asarray(valores_por_sesion, float)
    n = len(v)
    if n < 2 * bloque or np.isfinite(v).sum() < 2:
        return None
    rng = np.random.default_rng(semilla)
    medias = []
    for _ in range(repeticiones):
        inicios = rng.integers(0, n, size=int(np.ceil(n / bloque)))
        idx = (inicios[:, None] + np.arange(bloque)[None, :]).ravel()[:n] % n
        muestra = v[idx]
        if np.isfinite(muestra).any():
            medias.append(np.nanmean(muestra))
    return [float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))]


def senales_y_residuos(tabla, cierres):
    """Residuo frente a la base de su franja, z y las señales no solapadas con sus dos convergencias."""
    media, desv = base_horaria(tabla)
    residuo = tabla - media
    z = residuo / desv
    senales = []
    for fecha in tabla.index:
        fin = cierres[fecha]
        libre_desde = -1
        for punto in tabla.columns:
            if punto > fin - ULTIMA_SENAL_ANTES or punto < libre_desde:
                continue
            zz = z.at[fecha, punto]
            if not np.isfinite(zz) or abs(zz) < UMBRAL_Z:
                continue
            d = -np.sign(residuo.at[fecha, punto])

            def res(m):
                return residuo.at[fecha, m] if m in residuo.columns else np.nan
            fila = {"fecha": fecha, "minuto": punto, "z": zz,
                    "ingenua": d * (res(punto + HORIZONTE) - res(punto)),
                    "operable": d * (res(punto + ESPERA + HORIZONTE) - res(punto + ESPERA))}
            for h in HORIZONTES_SECUNDARIOS:
                fila[f"operable_{h}"] = d * (res(punto + ESPERA + h) - res(punto + ESPERA))
            senales.append(fila)
            libre_desde = punto + ESPERA + HORIZONTE
    columnas = ["fecha", "minuto", "z", "ingenua", "operable"] + [f"operable_{h}" for h in HORIZONTES_SECUNDARIOS]
    return residuo, z, pd.DataFrame(senales, columns=columnas)


def convergencia(senales, sesiones, columna):
    """Media por sesión activa (cada sesión pesa igual) e IC por bloques de sesiones."""
    medias = senales.groupby("fecha")[columna].mean() if len(senales) else pd.Series(dtype=float)
    por_sesion = np.array([medias.get(f, np.nan) for f in sesiones], float)
    activas = np.isfinite(por_sesion)
    return {"sesiones_activas": int(activas.sum()), "senales_validas": int(np.isfinite(senales[columna]).sum()),
            "media_puntos_vol": float(np.nanmean(por_sesion)) if activas.any() else None,
            "ic95": bootstrap(por_sesion)}


def persistencia(residuo):
    """Pendiente del residuo a 5, 10 y 30 minutos, y parte de su varianza que es ruido de medida.

    Con un proceso AR(1) más ruido blanco de medida, cov(5)/cov(10) estima la persistencia real cada
    5 minutos sin el ruido, y la varianza de la señal es cov(5)/rho.
    """
    pares = {}
    for rezago in (5, 10, 30):
        a, b = [], []
        for punto in residuo.columns:
            if punto + rezago in residuo.columns:
                x, y = residuo[punto].to_numpy(), residuo[punto + rezago].to_numpy()
                ok = np.isfinite(x) & np.isfinite(y)
                a.append(x[ok])
                b.append(y[ok])
        x, y = np.concatenate(a), np.concatenate(b)
        pares[rezago] = {"beta": float(np.polyfit(x, y, 1)[0]), "cov": float(np.cov(x, y)[0, 1]), "n": int(len(x))}
    varianza = float(np.nanvar(residuo.to_numpy()))
    rho = pares[10]["cov"] / pares[5]["cov"] if pares[5]["cov"] > 0 else np.nan
    senal = pares[5]["cov"] / rho if np.isfinite(rho) and rho > 0 else np.nan
    return {"pendiente": {f"{k}_min": v for k, v in pares.items()},
            "persistencia_cada_5_min_sin_ruido": float(rho),
            "parte_de_la_varianza_que_es_ruido": float(1 - senal / varianza) if np.isfinite(senal) else None}


def resumir(tabla, z, senales, filtro_fechas=None):
    sesiones = [f for f in tabla.index if np.isfinite(z.loc[f].to_numpy()).any()
                and (filtro_fechas is None or filtro_fechas(f))]
    s = senales[senales["fecha"].isin(sesiones)]
    return {
        "sesiones_con_base": len(sesiones),
        "cobertura_rr": float(np.isfinite(tabla.loc[sesiones].to_numpy()).mean()) if sesiones else None,
        "senales": int(len(s)),
        "convergencia_ingenua": convergencia(s, sesiones, "ingenua"),
        "convergencia_operable": convergencia(s, sesiones, "operable"),
        "operable_otros_horizontes": {f"{h}_min": convergencia(s, sesiones, f"operable_{h}")
                                      for h in HORIZONTES_SECUNDARIOS},
        "por_tamano_de_z": {
            nombre: {"ingenua": convergencia(s[f], sesiones, "ingenua"),
                     "operable": convergencia(s[f], sesiones, "operable")}
            for nombre, f in (("2<=|z|<3", s["z"].abs() < 3), ("|z|>=3", s["z"].abs() >= 3))},
    }


def main() -> int:
    archivos = sorted(DATOS.glob("*.json.gz"))
    filas, cierres = {}, {}
    for i, ruta in enumerate(archivos, 1):
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            registro = json.load(f)
        fecha = pd.Timestamp(registro["fecha"])
        filas[fecha] = rr_de_la_sesion(registro)
        c = pd.Timestamp(registro["cierre_utc"]).tz_convert(NY)
        cierres[fecha] = c.hour * 60 + c.minute
        if i % 100 == 0:
            print(f"{i} sesiones procesadas", flush=True)
    tabla = pd.DataFrame(filas).T.sort_index()
    tabla = tabla.reindex(columns=sorted(tabla.columns))
    residuo, z, senales = senales_y_residuos(tabla, cierres)
    resultado = {"periodo": [str(tabla.index[0].date()), str(tabla.index[-1].date())],
                 "sesiones": len(tabla),
                 "rr25_medio_por_hora": {f"{m // 60:02d}:{m % 60:02d}": float(tabla[m].mean())
                                         for m in tabla.columns if m % 30 == 10},
                 "persistencia": persistencia(residuo),
                 "todo": resumir(tabla, z, senales)}
    for anio in sorted({f.year for f in tabla.index}):
        resultado[str(anio)] = resumir(tabla, z, senales, lambda f, a=anio: f.year == a)
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "skew_0dte_alpaca.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resultado.items() if k in ("periodo", "sesiones", "persistencia", "todo")},
                     indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
