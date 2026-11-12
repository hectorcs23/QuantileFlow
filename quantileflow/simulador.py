"""Simulador condicional sintético: posición completa, sin probabilidades estimadas.

Reutiliza escenarios.py para el flujo de caja y Black–Scholes para el reprecio
europeo. Una superficie de PnL NO es una superficie de IV ni una PDF calibrada.
No lee cotizaciones ni envía órdenes. Mantiene fija la entrada al variar salidas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math

from .escenarios import (
    ContratoEscenario, Escenario, comparar_contratos, sensibilidad_europea,
)
from .opciones import precio_bs


@dataclass(frozen=True)
class ConfiguracionSimulador:
    presupuesto: float = 300.
    spot: float = 100.
    movimiento_pct: float = 3.
    dias: int = 7
    iv_pct: float = 25.
    cambio_iv_pp: float = 0.
    riesgo_pct: float = 100.
    max_contratos: int = 0  # 0 = sin límite adicional a presupuesto/riesgo
    comision: float = .65  # por contrato y lado
    semispread: float = .04  # por unidad de subyacente, entrada y salida
    tasa_pct: float = 4.
    dividendo_pct: float = 1.3  # rendimiento continuo; no eventos en efectivo

    def __post_init__(self):
        limites = {
            "presupuesto": (1, 100000), "spot": (1, 10000),
            "movimiento_pct": (-50, 100), "dias": (0, 90),
            "iv_pct": (1, 150), "cambio_iv_pp": (-100, 100),
            "riesgo_pct": (0, 100), "max_contratos": (0, 10000),
            "comision": (0, 25), "semispread": (0, 10),
            "tasa_pct": (-5, 25), "dividendo_pct": (0, 25),
        }
        for nombre, (lo, hi) in limites.items():
            valor = getattr(self, nombre)
            if (isinstance(valor, bool) or not isinstance(valor, (int, float))
                    or not math.isfinite(valor) or not lo <= valor <= hi):
                raise ValueError(f"{nombre}: se requiere un número entre {lo} y {hi}")
        for nombre in ("dias", "max_contratos"):
            if not isinstance(getattr(self, nombre), int):
                raise ValueError(f"{nombre}: se requiere un entero")
        if self.iv_pct + self.cambio_iv_pp <= 0:
            raise ValueError("La IV de salida debe ser positiva")

    @classmethod
    def desde_dict(cls, datos):
        if not isinstance(datos, dict):
            raise ValueError("Se requiere un objeto de parámetros")
        extra = set(datos) - {f.name for f in fields(cls)}
        if extra:
            raise ValueError("Parámetros desconocidos: " + ", ".join(sorted(extra)))
        return cls(**datos)


def cadena_sintetica(cfg):
    """12 candidatos europeos. Omite ask < .01, piso explícito de esta demo."""
    salida, excluidos = [], []
    for dte in (14, 30, 60):
        for factor in (1., 1.03, 1.05, 1.08):
            strike = cfg.spot * factor
            mid = float(precio_bs(cfg.spot, strike, dte/365, cfg.tasa_pct/100,
                                 cfg.dividendo_pct/100, cfg.iv_pct/100, True))
            identificador = f"C{factor * 100:g}-{dte}d"
            if mid+cfg.semispread < .01:
                excluidos.append({"contrato": identificador, "strike": strike, "dte": dte,
                    "motivo": "prima sintética inferior al piso de 0.01 USD/unidad de esta demo"})
                continue
            salida.append(ContratoEscenario(
                identificador, strike, dte, True, "europeo",
                cfg.iv_pct/100, max(0., mid-cfg.semispread), mid+cfg.semispread))
    return salida, excluidos


def _comparar(cfg, contratos, escenario):
    """El mismo criterio de reserva y cantidades que el comparador previo."""
    disponible = cfg.presupuesto * cfg.riesgo_pct / 100
    if disponible == 0:
        return {"contratos": [], "excluidos": [
            {"contrato": c.identificador, "motivo": "capital arriesgable cero"}
            for c in contratos]}
    return comparar_contratos(
        contratos, cfg.spot, [escenario], disponible, comision=cfg.comision,
        semispread_salida=cfg.semispread, tasa=cfg.tasa_pct/100,
        q=cfg.dividendo_pct/100,
        limites_cantidad=({c.identificador: cfg.max_contratos for c in contratos}
                          if cfg.max_contratos else None))


def _mejor(filas):
    if not filas:
        return {"contrato": "efectivo", "cantidad": 0, "pnl": 0.}
    fila = sorted(filas, key=lambda f: (-f["escenarios"]["objetivo"]["pnl"], f["contrato"]))[0]
    pnl = fila["escenarios"]["objetivo"]["pnl"]
    return ({"contrato": fila["contrato"], "cantidad": fila["contratos"], "pnl": pnl}
            if pnl > 0 else {"contrato": "efectivo", "cantidad": 0, "pnl": 0.})


def _valor_posicion(cfg, c, n, nombre, dias, movimiento, choque):
    # Un control fuera de dominio no excluye una compra válida en el objetivo.
    if dias > c.dte:
        return {"nombre": nombre, "pnl": None, "motivo": "ya venció; falta el precio al vencimiento"}
    if c.iv + choque <= 0 and dias < c.dte:
        return {"nombre": nombre, "pnl": None, "motivo": "IV no positiva"}
    # El presupuesto de entrada y el límite de cantidad fijan n en cada celda.
    r = comparar_contratos([c], cfg.spot, [Escenario(nombre, dias, movimiento, choque)],
        cfg.presupuesto, comision=cfg.comision, semispread_salida=cfg.semispread,
        tasa=cfg.tasa_pct/100, q=cfg.dividendo_pct/100,
        limites_cantidad={c.identificador: n})
    f = r["contratos"][0]
    v = f["escenarios"][nombre]
    return {"nombre": nombre, **v, "capital_final": cfg.presupuesto + v["pnl"]}


def simular(cfg=None):
    cfg = ConfiguracionSimulador() if cfg is None else cfg
    contratos, excluidos_prima = cadena_sintetica(cfg)
    por_id = {c.identificador: c for c in contratos}
    objetivo = Escenario("objetivo", cfg.dias, cfg.movimiento_pct/100, cfg.cambio_iv_pp/100)
    comparacion = _comparar(cfg, contratos, objetivo)
    orden = sorted(comparacion["contratos"],
                   key=lambda f: (-f["escenarios"]["objetivo"]["pnl"], f["contrato"]))
    movimientos = sorted(set([-6., -3., 0., 3., 6., 9., 12., cfg.movimiento_pct]))
    plazos = sorted(set([0, 3, 7, 14, 21, 30, 45, 60, cfg.dias]))
    choques = sorted(set([-10., -5., 0., 5., 10., cfg.cambio_iv_pp]))
    controles = [
        ("objetivo", cfg.dias, cfg.movimiento_pct/100, cfg.cambio_iv_pp/100),
        ("sin_movimiento", cfg.dias, 0., cfg.cambio_iv_pp/100),
        ("baja_3_pct", cfg.dias, -.03, cfg.cambio_iv_pp/100),
        ("iv_menos_5_pp", cfg.dias, cfg.movimiento_pct/100, (cfg.cambio_iv_pp-5)/100),
        ("siete_dias_tarde", cfg.dias+7, cfg.movimiento_pct/100, cfg.cambio_iv_pp/100),
    ]
    posiciones = []
    for f in orden:
        c, n = por_id[f["contrato"]], f["contratos"]
        reservado = f["desembolso"] + f["reserva_comision_cierre"]
        griegas = sensibilidad_europea(cfg.spot, c.strike, c.dte, c.iv,
                                     cfg.tasa_pct/100, cfg.dividendo_pct/100)
        casos = [_valor_posicion(cfg, c, n, *e) for e in controles]
        superficie = [[_valor_posicion(cfg, c, n, "celda", d, m/100,
                                      cfg.cambio_iv_pp/100)["pnl"]
                       for m in movimientos] for d in plazos]
        curva_iv = [_valor_posicion(cfg, c, n, "iv", cfg.dias,
                                   cfg.movimiento_pct/100, v/100)["pnl"] for v in choques]
        posiciones.append({
            "contrato": c.identificador, "strike": c.strike, "dte": c.dte,
            "cantidad": n, "prima_por_contrato": c.ask*c.multiplicador,
            "prima_total": n*c.ask*c.multiplicador,
            "desembolso": f["desembolso"], "reserva_cierre": f["reserva_comision_cierre"],
            "capital_reservado": reservado, "efectivo_libre": cfg.presupuesto-reservado,
            "perdida_maxima_costos_asumidos": reservado,
            "pnl_objetivo": f["escenarios"]["objetivo"]["pnl"],
            "retorno_presupuesto": f["escenarios"]["objetivo"]["pnl"]/cfg.presupuesto,
            "capital_final": cfg.presupuesto+f["escenarios"]["objetivo"]["pnl"],
            "sensibilidad_posicion": {k: n*c.multiplicador*v for k, v in griegas.items()
                                      if k != "valor"},
            "controles": casos, "pnl_por_plazo_movimiento": superficie,
            "pnl_por_iv": curva_iv,
        })
    # Perturbaciones explícitas de la hipótesis. No son frecuencias ni confianza.
    vecinos_dias = sorted(set([max(0, cfg.dias-2), cfg.dias, cfg.dias+2]))
    vecinos_move = [cfg.movimiento_pct-1, cfg.movimiento_pct, cfg.movimiento_pct+1]
    vecinos = [[_mejor(_comparar(cfg, contratos, Escenario(
        "objetivo", d, m/100, cfg.cambio_iv_pp/100))["contratos"])
        for m in vecinos_move] for d in vecinos_dias]
    return {
        "version": 1, "configuracion": asdict(cfg),
        "fuente": "sintética; Black–Scholes +/- semispread, sin cotizaciones de mercado",
        "motor": "Black–Scholes europeo, IV plana y dividendo continuo",
        "probabilidades": "no estimadas", "mezcla_series": False,
        "regla_cantidad": "máximo entero por serie bajo presupuesto, riesgo y límite de cantidad",
        "efectivo": {"pnl": 0., "capital_final": cfg.presupuesto, "intereses": 0.},
        "mejor_objetivo": _mejor(orden), "posiciones": posiciones,
        "excluidos": excluidos_prima + comparacion["excluidos"],
        "cadena": [asdict(c) for c in contratos],
        "ejes": {"movimientos_pct": movimientos, "plazos_dias": plazos, "choques_iv_pp": choques},
        "vecindad": {"movimientos_pct": vecinos_move, "plazos_dias": vecinos_dias,
                     "mejores": vecinos},
        "alcance": [
            "El ganador maximiza dólares netos solo bajo el escenario introducido.",
            "Las cantidades y primas de entrada permanecen fijas al variar salidas.",
            "La superficie representa PnL de una posición; no una IV ni una PDF de mercado.",
            "IV plana es una referencia de valoración, no una superficie calibrada.",
            "Calls europeos de ejemplo: no modela ejercicio anticipado ni dividendos discretos.",
            "El cierre al vencimiento usa valor intrínseco y reserva comisión; no simula entrega.",
            "Salida teórica menos semispread no garantiza un precio ejecutable.",
            "Se excluyen primas sintéticas inferiores a 0.01 USD/unidad; piso de esta demo.",
            "No estima dirección, probabilidad de ganar ni nivel de confianza.",
        ],
    }
