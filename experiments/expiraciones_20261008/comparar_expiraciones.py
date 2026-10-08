"""Cobertura y RR25 de SPXW por plazo constante; salida exclusivamente agregada."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quantileflow import alpaca, cadenas, contrato, piloto
from quantileflow.calendario import instante


def configuraciones(cfg, protocolo):
    """0DTE queda fuera: mínimo de un día, bracketing y límites fijados por protocolo."""
    return [replace(cfg, objetivo_dias=float(h["dias"]), minimo_dias=1.0,
                    separacion_maxima_dias=float(h["separacion_maxima_dias"]))
            for h in protocolo["horizontes"]]


def medir_objetivo(medidas, plazos, cfg):
    elegidos, motivo = piloto.elegir_vencimientos(plazos, cfg)
    if not elegidos:
        return {"estado": "no identificada", "motivo": motivo, "vencimientos": []}
    rr = piloto.plazo_constante([medidas[v] for v in elegidos],
                                [plazos[v] / cfg.base_dias for v in elegidos],
                                cfg.objetivo_dias / cfg.base_dias, cfg.base_dias)
    return {**rr, "vencimientos": [str(v) for v in elegidos]}


def cambios(inicial, final):
    if inicial["estado"] != "identificada" or final["estado"] != "identificada":
        return {"estado": "no identificada"}
    # Bandas de cotización conservadoras; no son intervalos de confianza estadística.
    bajo = final["inferior"] - inicial["superior"]
    alto = final["superior"] - inicial["inferior"]
    return {"estado": "identificada", "delta": final["valor"] - inicial["valor"],
            "inferior": bajo, "superior": alto, "excluye_cero": bajo > 0 or alto < 0}


def json_seguro(x):
    if isinstance(x, dict):
        return {str(k): json_seguro(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [json_seguro(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    return x


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tablas", type=Path, required=True)
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--fechas", nargs="+", required=True)
    p.add_argument("--protocolo", type=Path, default=Path(__file__).with_name("protocolo.toml"))
    args = p.parse_args()
    if args.fechas != sorted(set(args.fechas)) or any(date.fromisoformat(d).isoformat() != d for d in args.fechas):
        p.error("fechas ISO únicas y ordenadas")
    with args.protocolo.open("rb") as f:
        protocolo = tomllib.load(f)
    cfg = piloto.cargar_config(ROOT / "configs/piloto.toml")
    configs = configuraciones(cfg, protocolo)
    q = pd.read_parquet(args.tablas / "cotizaciones.parquet")
    s = pd.read_parquet(args.tablas / "subyacente.parquet")
    registros, calidad, cambios_rr = [], [], []
    for fecha in args.fechas:
        por_hora = {}
        for hora in ("09:45", "10:00"):
            label = fecha + "T" + hora.replace(":", "")
            corte = instante(fecha, hora)
            filas = q[(q.captura == label) & (q.raiz == "SPXW")]
            referencias = s[(s.captura == label) & (s.subyacente == "SPX") & (s.tipo_precio == "implicito")]
            if len(referencias) != 1 or filas.empty:
                raise ValueError(f"{label}: requiere cadena y una referencia SPX implícita")
            if set(zip(filas.proveedor, filas.feed)) != {("alpaca", "indicative")}:
                raise ValueError("esta versión se limita a la muestra gratuita; no mezcla feeds")
            for col in ("sello_evento_utc", "sello_snapshot_utc", "disponible_utc", "recibido_utc"):
                if filas[col].isna().any() or (filas[col] > corte).any():
                    raise ValueError(f"{label}: sello ausente o posterior al corte: {col}")
            ref = referencias.iloc[0]
            if pd.isna(ref.disponible_utc) or ref.disponible_utc > corte:
                raise ValueError(f"{label}: referencia no disponible al corte")
            medidas, plazos = {}, {}
            for venc, grupo in filas.groupby("vencimiento", sort=True):
                cap, info = contrato.captura_de_filas(grupo, fecha, corte, ref.precio, ref.sello_evento_utc,
                                                    cfg.tasa, cfg.rendimiento_dividendo)
                if cap.ejercicio != "europeo" or info["liquidacion"] != "PM":
                    raise ValueError("requiere SPXW europeo PM")
                res = cadenas.procesar_captura(cap, cfg.reglas, distancia=cfg.factor_strike - 1,
                                               delta=cfg.delta, hueco_max=cfg.hueco_max_k,
                                               hueco_max_delta=cfg.hueco_max_delta)
                m = cadenas.metricas_calidad(res, cfg.reglas)
                calidad.append({"fecha": fecha, "hora": hora, "vencimiento": str(venc),
                                "dias": info["dias"], "segmento": "0DTE" if str(venc) == fecha else "otros",
                                **{k: m[k] for k in ("filas", "filas_validas", "pares_completos",
                                                     "edad_mediana_s", "ancho_relativo_mediano", "alertas")}})
                medidas[venc], plazos[venc] = res.asimetria_delta, info["dias"]
            por_hora[hora] = {}
            for hcfg in configs:
                rr = medir_objetivo(medidas, plazos, hcfg)
                por_hora[hora][hcfg.objetivo_dias] = rr
                registros.append({"fecha": fecha, "hora": hora, "objetivo_dias": hcfg.objetivo_dias,
                                  **rr})
        for hcfg in configs:
            d = hcfg.objetivo_dias
            cambios_rr.append({"fecha": fecha, "objetivo_dias": d,
                               **cambios(por_hora["09:45"][d], por_hora["10:00"][d])})
    cobertura = []
    for hcfg in configs:
        d = hcfg.objetivo_dias
        r = [x for x in registros if x["objetivo_dias"] == d]
        cobertura.append({"objetivo_dias": d, "cortes": len(r),
                          "identificados": sum(x["estado"] == "identificada" for x in r),
                          "cambios_identificados": sum(x["estado"] == "identificada" for x in cambios_rr
                                                       if x["objetivo_dias"] == d)})
    archivos = [args.tablas / n for n in ("cotizaciones.parquet", "subyacente.parquet")]
    informe = {"version": "expiraciones-0.1", "fechas": args.fechas, "instrumento": "SPXW europeo PM",
               "feed": "alpaca/indicative", "referencia": "SPX inferido, no independiente",
               "codigo_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "config_base_sha256": hashlib.sha256((ROOT / "configs/piloto.toml").read_bytes()).hexdigest(),
               "protocolo_sha256": hashlib.sha256(args.protocolo.read_bytes()).hexdigest(),
               "entradas_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in archivos},
               "cobertura": cobertura, "rr25": registros, "cambios": cambios_rr,
               "calidad_cadenas": calidad}
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "resumen.json").write_text(json.dumps(json_seguro(informe), ensure_ascii=False,
                                                       allow_nan=False, indent=2) + "\n", encoding="utf-8")
    texto = ["# Cobertura de expiraciones", "", "Muestra descriptiva gratuita; no prueba de rentabilidad.", "",
             "| Plazo | Cortes con RR25 | Cambios 09:45–10:00 disponibles |",
             "|---|---:|---:|"]
    texto += [f"| {x['objetivo_dias']:g} días | {x['identificados']}/{x['cortes']} | "
              f"{x['cambios_identificados']}/{len(args.fechas)} |" for x in cobertura]
    texto += ["", "Las ausencias no demuestran falta de contratos en el mercado: la captura antigua "
              "seleccionaba alrededor de 30 días. No se extrapola ni se interpola desde 0DTE.", "",
              "0DTE figura solo en calidad_cadenas. Los plazos se miden hasta la liquidación, con "
              "calendario real; los límites de separación están en protocolo.toml.", ""]
    (args.salida / "COBERTURA.md").write_text("\n".join(texto), encoding="utf-8")
    print(json.dumps(cobertura))


if __name__ == "__main__":
    main()
