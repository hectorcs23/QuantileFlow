"""Prueba exploratoria con datos gratis: ¿el cambio diario del índice SKEW de Cboe anticipa a SPY?

Datos:
- SKEW y VIX diarios de Cboe (CSV públicos, desde 1990);
- SPY diario de Alpaca (feed SIP, ajustado por dividendos y splits), desde 2016.

Señales conocidas al cierre del día t (el SKEW de cierre se calcula con las opciones de SPX, que cierran a
las 16:15): cambio del SKEW, nivel del SKEW frente a su último año, cambio del VIX y rendimiento del día.

Objetivos:
- rendimiento de SPY al día siguiente, de cierre a cierre y de apertura a cierre (este último no
  depende de lo que pase entre las 16:00 y las 16:15);
- rendimiento a 5 días;
- riesgo: el tamaño del movimiento del día siguiente y la volatilidad realizada a 5 días.

Errores estándar de Newey-West. Muestra de ajuste 2016–2020 y evaluación fuera de muestra 2021 en
adelante. **Es exploratorio**: el SKEW no es el RR25 del piloto y son datos de cierre, no de las 09:45.
Solo escribe agregados.

Uso, desde la raíz del repositorio::

    python experiments/exploracion-datos-gratis/skew_cboe.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "exploracion" / "cboe"
SALIDA = Path(__file__).resolve().parent / "resultados"
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"
CORTE = "2021-01-01"


def cboe(indice):
    CACHE.mkdir(parents=True, exist_ok=True)
    ruta = CACHE / f"{indice}.csv"
    if not ruta.exists():
        with urllib.request.urlopen(CBOE.format(indice), timeout=60) as r:
            ruta.write_bytes(r.read())
    df = pd.read_csv(ruta)
    df["fecha"] = pd.to_datetime(df["DATE"], format="%m/%d/%Y")
    return df.set_index("fecha")


def spy_diario(desde="2016-01-01", hasta="2026-10-02"):
    ruta = CACHE / "spy_diario.json"
    if not ruta.exists():
        cab = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
        filas, token = [], None
        while True:
            p = {"symbols": "SPY", "timeframe": "1Day", "feed": "sip", "adjustment": "all",
                 "start": f"{desde}T00:00:00Z", "end": f"{hasta}T00:00:00Z", "limit": 10000}
            if token:
                p["page_token"] = token
            url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(p)
            with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=60) as r:
                d = json.loads(r.read())
            filas += d["bars"]["SPY"]
            token = d.get("next_page_token")
            if not token:
                break
        ruta.write_text(json.dumps(filas), encoding="utf-8")
    df = pd.DataFrame(json.loads(ruta.read_text(encoding="utf-8")))
    df["fecha"] = pd.to_datetime(df["t"].str[:10])
    return df.set_index("fecha")[["o", "c"]]


def newey_west(y, X, rezagos):
    """MCO con errores de Newey-West (núcleo de Bartlett). Devuelve coeficientes y estadísticos t."""
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    xu = X * u[:, None]
    S = xu.T @ xu
    for l in range(1, rezagos + 1):
        w = 1 - l / (rezagos + 1)
        g = xu[l:].T @ xu[:-l]
        S += w * (g + g.T)
    cov = XtX_inv @ S @ XtX_inv
    return b, b / np.sqrt(np.diag(cov))


def ajustar(df, objetivo, senales, rezagos):
    d = df[[objetivo] + senales].dropna()
    X = np.column_stack([np.ones(len(d))] + [d[s].to_numpy() for s in senales])
    b, t = newey_west(d[objetivo].to_numpy(), X, rezagos)
    return {"n": len(d), **{s: {"coef": float(b[i + 1]), "t": float(t[i + 1])} for i, s in enumerate(senales)}}


def fuera_de_muestra(df, objetivo, senales):
    """R² fuera de muestra frente a la media de la muestra de ajuste (Campbell y Thompson)."""
    d = df[[objetivo] + senales].dropna()
    ajuste, prueba = d[d.index < CORTE], d[d.index >= CORTE]
    X = lambda x: np.column_stack([np.ones(len(x))] + [x[s].to_numpy() for s in senales])
    b = np.linalg.lstsq(X(ajuste), ajuste[objetivo].to_numpy(), rcond=None)[0]
    pred = X(prueba) @ b
    y = prueba[objetivo].to_numpy()
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - ajuste[objetivo].mean()) ** 2)
    acierto = float(np.mean(np.sign(pred) == np.sign(y)))
    return {"n_ajuste": len(ajuste), "n_prueba": len(prueba), "r2_fuera": float(r2), "acierto_signo": acierto,
            "acierto_siempre_sube": float(np.mean(y > 0))}


def main() -> int:
    skew = cboe("SKEW")["SKEW"].rename("skew")
    vix = cboe("VIX")["CLOSE"].rename("vix")
    spy = spy_diario()
    df = spy.join(skew, how="inner").join(vix, how="inner").sort_index()
    c, o = np.log(df["c"]), np.log(df["o"])
    df["r"] = c.diff()
    df["dskew"] = df["skew"].diff()
    media, desv = df["skew"].rolling(252, min_periods=126).mean(), df["skew"].rolling(252, min_periods=126).std()
    df["zskew"] = (df["skew"] - media) / desv
    df["dvix"] = df["vix"].diff()
    df["y1"] = c.shift(-1) - c
    df["y1_ac"] = c.shift(-1) - o.shift(-1)
    df["y5"] = c.shift(-5) - c
    df["abs1"] = df["y1"].abs()
    df["rv5"] = np.sqrt(sum(df["r"].shift(-k) ** 2 for k in range(1, 6)))
    df["abs_r"] = df["r"].abs()
    resultado = {
        "periodo": [str(df.index[0].date()), str(df.index[-1].date())], "sesiones": len(df),
        "direccion": {
            "y1 ~ dskew": ajustar(df, "y1", ["dskew"], 1),
            "y1 ~ dskew + r + dvix": ajustar(df, "y1", ["dskew", "r", "dvix"], 1),
            "y1_ac ~ dskew + r + dvix": ajustar(df, "y1_ac", ["dskew", "r", "dvix"], 1),
            "y5 ~ dskew + r + dvix": ajustar(df, "y5", ["dskew", "r", "dvix"], 5),
            "y5 ~ zskew + vix": ajustar(df, "y5", ["zskew", "vix"], 5),
        },
        "riesgo": {
            "abs1 ~ dskew + vix + abs_r": ajustar(df, "abs1", ["dskew", "vix", "abs_r"], 1),
            "rv5 ~ dskew + vix + abs_r": ajustar(df, "rv5", ["dskew", "vix", "abs_r"], 5),
            "rv5 ~ zskew + vix + abs_r": ajustar(df, "rv5", ["zskew", "vix", "abs_r"], 5),
        },
        "fuera_de_muestra": {
            "y1 con dskew, r, dvix": fuera_de_muestra(df, "y1", ["dskew", "r", "dvix"]),
            "y1 solo r, dvix (referencia)": fuera_de_muestra(df, "y1", ["r", "dvix"]),
        },
    }
    q = pd.qcut(df["dskew"], 5, labels=False)
    resultado["quintiles_dskew"] = [
        {"quintil": int(k) + 1, "n": int(len(g)), "dskew_medio": float(g["dskew"].mean()),
         "y1_medio_pb": float(g["y1"].mean() * 1e4), "sube": float((g["y1"] > 0).mean()),
         "abs1_medio_pb": float(g["abs1"].mean() * 1e4)}
        for k, g in df.groupby(q)]
    for nombre, parte in (("2016-2020", df[df.index < CORTE]), ("2021-2026", df[df.index >= CORTE])):
        resultado.setdefault("por_periodo", {})[nombre] = {
            "y1 ~ dskew + r + dvix": ajustar(parte, "y1", ["dskew", "r", "dvix"], 1),
            "rv5 ~ dskew + vix + abs_r": ajustar(parte, "rv5", ["dskew", "vix", "abs_r"], 5),
            "rv5 ~ zskew + vix + abs_r": ajustar(parte, "rv5", ["zskew", "vix", "abs_r"], 5)}
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "skew_cboe.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultado, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
