"""Exploracion descriptiva SPXW: mismos pares, dos cortes; sin entrenamiento.

Uso: python explorar_intradia.py --codigo CHECKOUT --tablas PARQUETS
       --diagnosticos AUDITORIA --salida AGREGADOS --privado DETALLE_PRIVADO
No escribe cotizaciones ni filas por contrato en la salida de agregados.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from dataclasses import replace
from datetime import date as calendar_date
from pathlib import Path

import numpy as np
import pandas as pd

DATES = ["2026-10-02", "2026-10-05", "2026-10-06"]
KEYS = ["fecha", "vencimiento", "strike"]


def validar_fechas(fechas):
    """Fechas ISO unicas y ordenadas; no acepta cambios silenciosos de muestra."""
    if not fechas or fechas != sorted(set(fechas)):
        raise ValueError("--fechas requiere fechas unicas en orden cronologico")
    for fecha in fechas:
        if calendar_date.fromisoformat(fecha).isoformat() != fecha:
            raise ValueError("las fechas deben usar YYYY-MM-DD")
    return list(fechas)


def clean_json(x):
    if isinstance(x, dict):
        return {str(k): clean_json(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)):
        return [clean_json(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    return x


def paired_changes(frame):
    a = frame[frame.hora == "09:45"]
    b = frame[frame.hora == "10:00"]
    m = a.merge(b, on=KEYS, suffixes=("_a", "_b"), validate="one_to_one")
    m["delta_residuo"] = m.residuo_b - m.residuo_a
    m["banda_cambio"] = .5 * (m.ancho_a + m.ancho_b)
    m["cambio_supera_bandas"] = m.delta_residuo.abs() > m.banda_cambio
    m["fuera_ambos_mismo_signo"] = m.fuera_a & m.fuera_b & (np.sign(m.residuo_a) == np.sign(m.residuo_b))
    m["fresco_ambos"] = (m.edad_max_a <= 10) & (m.edad_max_b <= 10) & (m.desfase_patas_a <= 2) & (m.desfase_patas_b <= 2)
    # Cohorte descriptiva definida con ambos cortes; nunca se usa como feature de 09:45.
    m["cerca_ambos"] = (m.k_a.abs() <= .05) & (m.k_b.abs() <= .05)
    return m


def stat(g):
    if not len(g):
        return {"n": 0}
    return {"n": len(g), "fuera": int(g.fuera.sum()), "fraccion_fuera": g.fuera.mean(),
            "residuo_abs_mediana": g.residuo.abs().median(),
            "multiplo_medio_ancho_mediana": g.z.abs().median(),
            "ancho_mediana": g.ancho.median(), "edad_mediana": g.edad_max.median(),
            "desfase_patas_mediana": g.desfase_patas.median(),
            "excluidos_estimacion": int((~g.en_estimacion).sum())}


def rank_corr(a, b):
    if len(a) < 5 or a.nunique() < 2 or b.nunique() < 2:
        return None
    return float(a.rank().corr(b.rank()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("codigo", "tablas", "diagnosticos", "salida", "privado"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--fechas", nargs="+", default=DATES,
                        help="Fechas ISO, unicas y ordenadas. Omision: muestra original de tres sesiones.")
    args = parser.parse_args()
    dates = validar_fechas(args.fechas)
    sys.path.insert(0, str(args.codigo.resolve()))
    from quantileflow import cadenas, contrato, piloto
    from quantileflow.calendario import instante
    args.salida.mkdir(parents=True, exist_ok=True)
    args.privado.mkdir(parents=True, exist_ok=True)
    cfg = piloto.cargar_config(args.codigo / "configs/piloto.toml")
    q = pd.read_parquet(args.tablas / "cotizaciones.parquet")
    s = pd.read_parquet(args.tablas / "subyacente.parquet")
    all_pairs, summaries, rr_rows, chain_correlations, checks = [], [], [], [], []
    scenarios = {"base": (60, None), "edad30_gap5": (30, 5), "edad10_gap2": (10, 2)}
    scenarios.update({f"tasa_fija_{r}": (60, None) for r in (3, 4, 5)})
    for date in dates:
        diagnostic = json.loads((args.diagnosticos / f"diagnostico_{date}" / "resumen.json").read_text(encoding="utf-8"))
        for record in diagnostic["capturas"]:
            for root in ("SPXW", "SPY"):
                rr = record["raices"][root]["plazo_constante_30d"]["rr25"]
                rr_rows.append({"fecha": date, "hora": record["hora"], "raiz": root,
                                **{k: 100 * rr[k] for k in ("valor", "inferior", "superior")}})
        for hour in ("09:45", "10:00"):
            label = date + "T" + hour.replace(":", "")
            rows = q[(q.captura == label) & (q.raiz == "SPXW")].copy()
            if set(rows["feed"].unique()) != {"indicative"} or set(rows["proveedor"].unique()) != {"alpaca"}:
                raise ValueError(f"{label}: este experimento requiere una captura alpaca/indicative completa")
            ref = s[(s.captura == label) & (s.subyacente == "SPX") & (s.tipo_precio == "implicito")]
            assert len(ref) == 1
            spot = ref.iloc[0]
            cut = instante(date, hour)
            for col in ("sello_evento_utc", "sello_snapshot_utc", "disponible_utc", "recibido_utc"):
                assert rows[col].notna().all() and (rows[col] <= cut).all(), (label, col)
            for expiry, group in rows.groupby("vencimiento", sort=True):
                cap, info = contrato.captura_de_filas(group, date, cut, spot.precio, spot.sello_evento_utc,
                                                      cfg.tasa, cfg.rendimiento_dividendo)
                segment = "0DTE" if info["dias"] < 1 else "plazo_mensual"
                assert cap.ejercicio == "europeo"
                for scenario, (age, gap) in scenarios.items():
                    ctl = cadenas.controlar(cap, replace(cfg.reglas, edad_maxima=age))
                    if gap is not None:
                        _, ic, ip, _ = cadenas.pares_mismo_strike(cap, ctl)
                        reasons = [list(m) for m in ctl.motivos]
                        for i, j in zip(ic, ip):
                            if abs(cap.sello[i] - cap.sello[j]) > gap:
                                reasons[i].append("desfase_entre_patas")
                                reasons[j].append("desfase_entre_patas")
                        ctl = cadenas.Controles(tuple(tuple(m) for m in reasons), ctl.alertas)
                    # 0DTE: descuento fijado como en implicito.py; mensual: D libre como en cadenas.py.
                    discount = np.exp(-cfg.tasa * cap.T) if segment == "0DTE" else None
                    if scenario.startswith("tasa_fija_"):
                        discount = np.exp(-int(scenario.rsplit("_", 1)[1])/100 * cap.T)
                    p = cadenas.residuos_paridad(cap, ctl, descuento=discount, minimo_pares=5)
                    k, ic, ip, _ = cadenas.pares_mismo_strike(cap, ctl)
                    assert np.array_equal(k, p.strike)
                    valid = (np.isfinite(p.residuo) & np.isfinite(p.forward) & (p.forward > 0)
                             & np.isfinite(p.descuento) & (p.descuento > 0) & (p.ancho > 0))
                    d = pd.DataFrame({"fecha": date, "hora": hour, "vencimiento": str(expiry), "segmento": segment,
                                      "escenario": scenario, "strike": k, "residuo": p.residuo,
                                      "ancho": p.ancho, "z": 2 * p.residuo / p.ancho,
                                      "fuera": p.fuera_de_banda, "en_estimacion": p.en_estimacion,
                                      "edad_max": np.maximum(cap.corte-cap.sello[ic], cap.corte-cap.sello[ip]),
                                      "desfase_patas": abs(cap.sello[ic]-cap.sello[ip]),
                                      "k": np.log(k / p.forward), "forward": p.forward,
                                      "descuento": p.descuento})[valid].copy()
                    if len(d):
                        assert np.allclose(d.residuo, (cap.mid[ic]-cap.mid[ip])[valid] - p.descuento[valid] * (p.forward[valid]-k[valid]))
                        assert np.array_equal(d.fuera.to_numpy(), (d.z.abs() > 1).to_numpy())
                        all_pairs.append(d)
                    summaries.append({"fecha": date, "hora": hour, "vencimiento": str(expiry),
                                      "segmento": segment, "escenario": scenario, "pares_validos": len(k),
                                      "pares_estimables": len(d), "forward_global": p.forward_global,
                                      "tasa_estimada": p.tasa_implicita, "alertas": list(ctl.alertas)})
                checks.append({"captura": label, "vencimiento": str(expiry), "filas": len(group)})
    pairs = pd.concat(all_pairs, ignore_index=True)
    assert not pairs.duplicated(["escenario", "fecha", "hora", "vencimiento", "strike"]).any()
    pairs.to_parquet(args.privado / "pares.parquet", index=False)
    base = pairs[pairs.escenario == "base"].copy()
    base["cerca"] = base.k.abs() <= .05
    base["fresco"] = (base.edad_max <= 10) & (base.desfase_patas <= 2)
    panel = paired_changes(base)
    panel.to_parquet(args.privado / "cambios_pares.parquet", index=False)
    aggregate, quality, changes, sensitivity = [], [], [], []
    for (date, hour, seg), g in base[base.cerca].groupby(["fecha", "hora", "segmento"]):
        aggregate.append({"fecha": date, "hora": hour, "segmento": seg, **stat(g)})
        for fresh, h in g.groupby("fresco"):
            quality.append({"fecha": date, "hora": hour, "segmento": seg, "fresco": bool(fresh), **stat(h)})
    for (date, hour, exp), g in base[base.cerca].groupby(["fecha", "hora", "vencimiento"]):
        chain_correlations.append({"fecha": date, "hora": hour, "vencimiento": exp, "n": len(g),
                                   "rho_absres_edad": rank_corr(g.residuo.abs(), g.edad_max),
                                   "rho_absres_desfase": rank_corr(g.residuo.abs(), g.desfase_patas),
                                   "rho_absres_ancho": rank_corr(g.residuo.abs(), g.ancho),
                                   "rho_absz_ancho": rank_corr(g.z.abs(), g.ancho)})
    for (date, seg), g in panel[panel.cerca_ambos].groupby(["fecha", "segmento_a"]):
        prev = g[g.fuera_a]
        changes.append({"fecha": date, "segmento": seg, "pares_comunes": len(g),
                        "fuera_0945": int(g.fuera_a.sum()), "fuera_1000": int(g.fuera_b.sum()),
                        "persisten_mismo_signo": int(g.fuera_ambos_mismo_signo.sum()),
                        "regresan_a_banda": int((g.fuera_a & ~g.fuera_b).sum()),
                        "cambian_signo_fuera": int((g.fuera_a & g.fuera_b & ~g.fuera_ambos_mismo_signo).sum()),
                        "delta_abs_mediana": g.delta_residuo.abs().median(),
                        "cambio_supera_bandas": int(g.cambio_supera_bandas.sum()),
                        "frescos_en_ambos": int(g.fresco_ambos.sum()),
                        "fraccion_persistente_condicional": g.fuera_ambos_mismo_signo.sum()/len(prev) if len(prev) else None})
    for (sc, seg), g in pairs[pairs.k.abs() <= .05].groupby(["escenario", "segmento"]):
        sensitivity.append({"escenario": sc, "segmento": seg, **stat(g)})
    selection_refit = []
    for seg, g in base[base.cerca].groupby("segmento"):
        fresh = g[g.fresco]
        # Freeze the evaluation cohort with BASE moneyness, then re-estimate F/D on fresh pairs.
        strict = pairs[(pairs.escenario == "edad10_gap2") & (pairs.segmento == seg)]
        join_keys = ["fecha", "hora", "vencimiento", "strike"]
        common = fresh[join_keys].merge(strict, on=join_keys, validate="one_to_one")
        before = common[join_keys].merge(fresh, on=join_keys, validate="one_to_one")
        selection_refit.append({"segmento": seg, "todos_base": stat(g), "seleccion_frescos_sin_reajustar": stat(fresh),
                                "cohorte_comun_base": stat(before), "cohorte_comun_reajustada": stat(common),
                                "frescos_sin_estimacion_estricta": len(fresh)-len(common)})
    rate_sensitivity = []
    for seg, g in base[base.cerca].groupby("segmento"):
        for rate in (3, 4, 5):
            fixed = pairs[(pairs.escenario == f"tasa_fija_{rate}") & (pairs.segmento == seg)]
            join_keys = ["fecha", "hora", "vencimiento", "strike"]
            common = g[join_keys].merge(fixed, on=join_keys, validate="one_to_one")
            rate_sensitivity.append({"segmento": seg, "tasa_fija_porcentaje": rate,
                                     "cohorte_base": len(g), "sin_estimacion": len(g)-len(common), **stat(common)})
    rr = pd.DataFrame(rr_rows)
    rr_diff = rr[rr.hora == "09:45"].merge(rr[rr.hora == "10:00"], on=["fecha", "raiz"], suffixes=("_a", "_b"), validate="one_to_one")
    rr_diff["cambio"] = rr_diff.valor_b - rr_diff.valor_a
    rr_diff["cambio_inferior"] = rr_diff.inferior_b - rr_diff.superior_a
    rr_diff["cambio_superior"] = rr_diff.superior_b - rr_diff.inferior_a
    rr_diff["intervalos_separados"] = (rr_diff.cambio_inferior > 0) | (rr_diff.cambio_superior < 0)
    result = {"fechas": dates, "raiz_residuos": "SPXW", "feed": "indicative", "codigo_captura": "4ffde8a",
              "hipotesis": "Exploracion descriptiva; no se prueba prediccion ni se calculan p-valores.",
              "pares_todos_base": len(base), "pares_cerca_base": int(base.cerca.sum()),
              "resumen_cortes": aggregate, "calidad": quality, "cambios": changes,
              "sensibilidad": sensitivity, "seleccion_vs_reajuste": selection_refit,
              "sensibilidad_tasa_cohorte_fija": rate_sensitivity,
              "correlaciones_por_cadena": chain_correlations,
              "rr25": rr_diff.to_dict("records"), "ajustes": summaries,
              "sha_tablas": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.tablas.glob("*.parquet")},
              "versiones": {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__},
              "verificaciones": {"cadenas_procesadas": len(checks), "identidad_residuo": True,
                                  "banda_equivale_z_mayor_1": True, "pares_unicos": True,
                                  "marcas_antes_del_corte": True}}
    (args.salida / "resultados.json").write_text(json.dumps(clean_json(result), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    for name, records in [("resumen_cortes", aggregate), ("calidad", quality), ("cambios", changes), ("sensibilidad", sensitivity), ("rr25", rr_diff.to_dict("records"))]:
        pd.DataFrame(records).to_csv(args.salida / f"{name}.csv", index=False, encoding="utf-8")
    print(json.dumps(clean_json({"cambios": changes, "sensibilidad": sensitivity,
                                "rr25": rr_diff[["fecha", "raiz", "cambio", "cambio_inferior", "cambio_superior", "intervalos_separados"]].to_dict("records")}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
