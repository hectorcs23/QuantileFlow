"""Corrida reproducible del recomendador: vista, evaluación, informe y manifiesto.

El manifiesto registra la configuración y su huella, la vista declarada, el
estado del código y los hashes de las salidas. La misma cadena con la misma
configuración y la misma vista produce el mismo informe. La vista va en el
manifiesto porque es una entrada tan determinante como las cotizaciones: sin
ella no hay recomendación, y cambiarla cambia el resultado.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from quantileflow import almacen

from .estructuras import catalogo
from .informe import escribir_informe
from .recomendacion import recomendar

RAIZ = Path(__file__).resolve().parents[1]


def construir_vista(q, F, especificacion):
    """Construye ``P`` a partir de una especificación declarativa (la de la configuración)."""
    from . import vista as mod

    esp = dict(especificacion)
    tipo = esp.pop("tipo")
    constructores = {
        "neutral": lambda: mod.neutral(q),
        "tilt_media": lambda: mod.tilt_media(q, F, esp["retorno"]),
        "tilt_momentos": lambda: mod.tilt_momentos(q, F, esp.get("retorno"), esp.get("factor_vol")),
        "reponderar_cola": lambda: mod.reponderar_cola(q, esp["factor"], esp["umbral_log"],
                                                       esp.get("lado", "izquierda"),
                                                       esp.get("preservar_media", False)),
        "escenarios": lambda: mod.escenarios(q, F, [tuple(e) for e in esp["lista"]]),
        "desplazamiento": lambda: mod.desplazar(q, esp["deriva"]),
    }
    if tipo not in constructores:
        raise ValueError(f"tipo de vista desconocido: {tipo}; opciones: {sorted(constructores)}")
    return constructores[tipo]()


def correr(cfg, mundo, salida, titulo, aviso="", especificacion_vista=None, raiz=RAIZ):
    """Evalúa el catálogo sobre un mundo ya construido y escribe informe y manifiesto."""
    entorno = almacen.huella_entorno(raiz)
    mercado, q, q_alt = mundo["mercado"], mundo["q"], mundo.get("q_alternativa")
    especificacion = especificacion_vista or cfg.fuente["vista"]
    p = construir_vista(q, mercado.F, especificacion)
    candidatas = catalogo(mercado.F, mundo["strikes_fiables"], cfg.distancias, cfg.anchuras)
    resultado = recomendar(candidatas, p, q, mercado, cfg, q_alt)
    salida = Path(salida)
    rutas = escribir_informe(resultado, p, q, mercado, salida, titulo, aviso,
                             contexto={"dias": mundo.get("dias")})
    dic = resultado["dictamen"]
    manifiesto = {
        "fecha_corrida_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "config": {"version": cfg.version, "huella": almacen.huella_datos(cfg.fuente)},
        "vista": {"especificacion": especificacion, "origen": p.origen,
                  "detalle": {k: v for k, v in p.detalle.items() if isinstance(v, (int, float))}},
        "mercado": {"T": mercado.T, "forward": mercado.F, "descuento": mercado.D,
                    "rango_fiable": list(q.rango_fiable), **mercado.detalle},
        "q": {"origen": q.origen, "alternativa": q_alt.origen if q_alt is not None else None},
        "diagnostico": {k: v for k, v in resultado["diagnostico"].items() if k != "tramos"},
        "escenarios": resultado["escenarios"],
        "candidatas": {"n": len(resultado["filas"]), "aptas": len(resultado["aptas"])},
        "dictamen": {"accion": dic["accion"], "texto": dic["texto"],
                     "estructura": dic["estructura"]["estructura"].nombre
                     if dic["estructura"] else None},
        "motivos_globales": resultado["motivos_globales"],
        "entorno": entorno,
        "salidas": almacen.hashes(rutas.values()),
    }
    almacen.escribir_json(manifiesto, salida / "manifiesto.json")
    return resultado, p, manifiesto
