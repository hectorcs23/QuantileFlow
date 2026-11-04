"""Dos compras alternativas a tamaño exacto, con el mismo capital y salida común."""
from math import floor

from scipy.optimize import brentq

from .escenarios import Escenario, comparar_contratos
from .opciones import precio_bs
from .simulador import ConfiguracionSimulador, cadena_sintetica


def _equilibrio(cfg, c):
    """Spot que cubre el ask y los dos lados de comisiones en el horizonte elegido."""
    coste = c.ask + 2 * cfg.comision / c.multiplicador
    if cfg.dias == c.dte:
        spot = c.strike + coste
    else:
        t = (c.dte - cfg.dias) / 365
        sigma = (cfg.iv_pct + cfg.cambio_iv_pp) / 100
        def residual(s):
            return float(precio_bs(s, c.strike, t, cfg.tasa_pct/100,
                                   cfg.dividendo_pct/100, sigma, True)) - cfg.semispread - coste
        spot = brentq(residual, cfg.spot * 1e-10, 4 * (cfg.spot + c.strike + coste))
    return dict(spot=spot, movimiento_pct=100*(spot/cfg.spot-1))


def _escenarios(cfg):
    m, d, iv = cfg.movimiento_pct, cfg.dias, cfg.cambio_iv_pp
    return [
        ('objetivo', 'Objetivo', m, d, iv),
        ('mitad', 'Mitad del movimiento', m/2, d, iv),
        ('sin_movimiento', 'Sin movimiento', 0., d, iv),
        ('baja', 'Baja 3%', -3., d, iv),
        ('iv', 'IV cae 5 puntos más', m, d, iv-5),
        ('tarde', 'Llega 7 días tarde', m, d+7, iv),
        ('combinado', 'Mitad, tarde e IV menor', m/2, d+7, iv-5),
    ]


def comparar_dos(cfg: ConfiguracionSimulador, elecciones):
    if not isinstance(elecciones, list) or len(elecciones) != 2:
        raise ValueError('Elige exactamente dos posiciones alternativas')
    cadena = {c.identificador:c for c in cadena_sintetica(cfg)[0]}
    capital = cfg.presupuesto * cfg.riesgo_pct / 100
    posiciones, series = [], []
    for letra, e in zip(('A', 'B'), elecciones):
        if not isinstance(e,dict) or set(e) != {'contrato','cantidad'}:
            raise ValueError(f'{letra}: indica contrato y cantidad')
        nombre, n = e['contrato'], e['cantidad']
        if not isinstance(nombre, str) or nombre not in cadena:
            raise ValueError(f'{letra}: serie sintética no disponible')
        if type(n) is not int or n < 1:
            raise ValueError(f'{letra}: cantidad entera positiva requerida')
        c = cadena[nombre]
        if c.dte < cfg.dias:
            raise ValueError(f'{letra}: el objetivo es posterior al vencimiento')
        entrada_unitaria = c.ask*c.multiplicador + cfg.comision
        limite = floor(capital/(entrada_unitaria+cfg.comision))
        if cfg.max_contratos: limite = min(limite,cfg.max_contratos)
        if n > limite:
            raise ValueError(f'{letra}: caben como máximo {limite} contratos bajo estos límites')
        entrada, cierre = n*entrada_unitaria, n*cfg.comision
        posiciones.append(dict(lado=letra, contrato=nombre, strike=c.strike, dte=c.dte, cantidad=n,
            max_cantidad=limite, prima_por_contrato=c.ask*c.multiplicador, desembolso=entrada,
            reserva_cierre=cierre, capital_reservado=entrada+cierre, efectivo_libre=cfg.presupuesto-entrada-cierre,
            perdida_maxima=entrada+cierre, equilibrio=_equilibrio(cfg,c)))
        series.append(c)
    filas=[]
    for key, label, mov, dias, choque in _escenarios(cfg):
        valores=[]
        for c,pos in zip(series,posiciones):
            if dias > c.dte:
                valores.append(dict(pnl=None,capital_final=None,motivo='Falta el precio al vencer'))
                continue
            if dias < c.dte and cfg.iv_pct+choque <= 0:
                valores.append(dict(pnl=None,capital_final=None,motivo='IV de salida no positiva'))
                continue
            e=Escenario(key,dias,mov/100,choque/100)
            comparacion=comparar_contratos([c],cfg.spot,[e],capital,comision=cfg.comision,
                semispread_salida=cfg.semispread,tasa=cfg.tasa_pct/100,q=cfg.dividendo_pct/100,
                limites_cantidad={c.identificador:pos['cantidad']})
            f,=comparacion['contratos']
            if f['contratos']!=pos['cantidad']:raise RuntimeError('Cambió la cantidad de entrada')
            pnl=f['escenarios'][key]['pnl']
            valores.append(dict(pnl=pnl,capital_final=cfg.presupuesto+pnl,motivo=None))
        pnls=[v['pnl'] for v in valores]
        diferencia=None;mejores=None
        if None not in pnls:
            diferencia=pnls[0]-pnls[1]
            cents=[round(x,2) for x in [*pnls,0.]]
            mejores=[nombre for nombre,x in zip(('A','B','Efectivo'),cents) if x==max(cents)]
        filas.append(dict(id=key,nombre=label,dias=dias,movimiento_pct=mov,iv_salida_pct=cfg.iv_pct+choque,
            valores=valores,diferencia_a_menos_b=diferencia,mejores=mejores))
    return dict(presupuesto=cfg.presupuesto,capital_arriesgable=capital,alternativas=posiciones,
                escenarios=filas,efectivo=dict(pnl=0.,capital_final=cfg.presupuesto),
                fuente='Calls europeos sintéticos; salidas condicionales, sin probabilidades estimadas')
