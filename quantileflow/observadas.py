"""Comparador histórico exploratorio; las tablas y posiciones permanecen privadas.

Calls SPXW europeos PM. IV por contrato invertida de bid/mid/ask, sin afirmar
que esas IV formen una superficie libre de arbitraje. Nunca recomienda operar.
"""
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .calendario import instante, instante_liquidacion
from .opciones import precio_bs, vol_implicita_black
from .simulador import ConfiguracionSimulador


@dataclass(frozen=True)
class ConfiguracionObservada:
    presupuesto: float = 300.
    movimiento_pct: float = 3.
    dias: int = 7
    cambio_iv_pp: float = 0.
    riesgo_pct: float = 100.
    max_contratos: int = 0
    comision: float = .65

    def __post_init__(self):
        # Validación de límites compartida, sin imponer una IV inicial sintética.
        datos = asdict(self)
        datos.pop('cambio_iv_pp')
        ConfiguracionSimulador(**datos)
        v = self.cambio_iv_pp
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not -100 <= v <= 100:
            raise ValueError('cambio_iv_pp: número entre -100 y 100 requerido')

    @classmethod
    def desde_dict(cls, datos):
        if not isinstance(datos, dict) or set(datos) - {f.name for f in fields(cls)}:
            raise ValueError('Configuración observada desconocida')
        return cls(**datos)


SELLOS = ('sello_evento_utc', 'sello_snapshot_utc', 'disponible_utc', 'recibido_utc')
REGLAS = dict(edad_maxima_s=60., spread_relativo_max=.5, tamano_minimo=1,
              maximo_dte=90., tasa=.04, dividendo_continuo=.013,
              semispread_salida_factores=[1., 2.], choques_adicionales_iv_pp=[-5., 0., 5.])


def cargar_tablas(ruta):
    """Verifica las huellas de TODAS las tablas de la normalización antes de leer."""
    ruta = Path(ruta).resolve()
    m = json.loads((ruta/'manifiesto_normalizacion.json').read_text(encoding='utf8'))
    if not {'cotizaciones', 'subyacente'} <= set(m['salidas']):
        raise ValueError('Manifiesto sin tablas requeridas')
    for nombre, esperado in m['salidas'].items():
        p = (ruta/(nombre+'.parquet')).resolve()
        if not p.is_relative_to(ruta) or hashlib.sha256(p.read_bytes()).hexdigest() != esperado:
            raise ValueError('Huella de tabla incorrecta')
    return pd.read_parquet(ruta/'cotizaciones.parquet'), pd.read_parquet(ruta/'subyacente.parquet')


def preparar_observadas(cotizaciones, referencias, fecha, hora='09:45'):
    """Selecciona una única foto causal; SIP disponible más tarde no se incorpora."""
    corte = instante(fecha, hora)
    tag = f"{fecha}T{hora.replace(':', '')}"
    filas = cotizaciones[(cotizaciones.captura == tag) & (cotizaciones.tipo == 'C')].copy()
    refs = referencias[(referencias.captura == tag) & (referencias.subyacente == 'SPX')].copy()
    if filas.empty or len(refs) != 1:
        raise ValueError('Requiere calls y una referencia SPX en la captura')
    if filas.id_contrato.duplicated().any():
        raise ValueError('Contratos duplicados en la captura')
    for col in SELLOS:
        filas[col] = pd.to_datetime(filas[col], utc=True, errors='coerce')
        refs[col] = pd.to_datetime(refs[col], utc=True, errors='coerce')
    ref = refs.iloc[0]
    if not math.isfinite(ref.precio) or ref.precio <= 0:
        raise ValueError('Referencia SPX inválida')
    if any(pd.isna(ref[c]) or ref[c] > corte for c in SELLOS):
        raise ValueError('Referencia no disponible al corte')
    if ref.sello_evento_utc > ref.sello_snapshot_utc or ref.sello_snapshot_utc > ref.recibido_utc:
        raise ValueError('Cronología de referencia inválida')
    edad_ref = (corte-ref.sello_evento_utc).total_seconds()
    if edad_ref > REGLAS['edad_maxima_s']:
        raise ValueError('Referencia SPX demasiado antigua')
    filas = filas.sort_values('id_contrato')
    registros = []
    for _, row in filas.iterrows():
        motivos = []
        def mal(m): motivos.append(m)
        c = dict(contrato=str(row.id_contrato), raiz=str(row.raiz))
        if not (row.raiz == 'SPXW' and row.subyacente == 'SPX' and row.ejercicio == 'europeo' and row.liquidacion == 'PM'):
            mal('instrumento_no_admitido')
        if row.proveedor != 'alpaca' or row.feed not in ('indicative', 'opra'):
            mal('fuente_no_admitida')
        nums = [row[k] for k in ('strike', 'bid', 'ask', 'tam_bid', 'tam_ask', 'multiplicador')]
        finitos = all(isinstance(x, (int, float)) and math.isfinite(x) for x in nums)
        precio_valido = finitos and row.strike > 0 and 0 <= row.bid <= row.ask and row.ask > 0 and row.multiplicador == 100
        c['coste_unitario_sin_comision'] = float(row.ask*100) if precio_valido else None
        if not precio_valido or row.bid <= 0:
            mal('precio_o_multiplicador_invalido')
        if not finitos or min(row.tam_bid, row.tam_ask) < 1:
            mal('sin_tamano')
        if any(pd.isna(row[k]) or row[k] > corte for k in SELLOS):
            mal('sello_ausente_o_futuro')
        else:
            if row.sello_evento_utc > row.sello_snapshot_utc or row.sello_snapshot_utc > row.recibido_utc:
                mal('cronologia_invalida')
            if (corte-row.sello_evento_utc).total_seconds() > REGLAS['edad_maxima_s']:
                mal('precio_antiguo')
        if precio_valido and (row.ask-row.bid)/((row.ask+row.bid)/2) > REGLAS['spread_relativo_max']:
            mal('spread_amplio')
        try:
            dte = (instante_liquidacion(row.vencimiento, row.liquidacion)-corte).total_seconds()/86400
            if not 0 < dte <= REGLAS['maximo_dte']: mal('plazo_fuera_de_dominio')
        except (ValueError, TypeError):
            dte = None
            mal('vencimiento_invalido')
        c.update(dte=dte, motivos=motivos)
        if not motivos:
            t = dte/365
            F = ref.precio*math.exp((REGLAS['tasa']-REGLAS['dividendo_continuo'])*t)
            iv = vol_implicita_black([row.bid, (row.bid+row.ask)/2, row.ask], F, row.strike,
                                    t, math.exp(-REGLAS['tasa']*t), True)
            if not np.isfinite(iv).all():
                mal('iv_no_identificada')
            else:
                c.update(strike=float(row.strike), bid=float(row.bid), ask=float(row.ask),
                         multiplicador=100, tam_ask=math.floor(row.tam_ask),
                         iv_bid=float(iv[0]), iv=float(iv[1]), iv_ask=float(iv[2]),
                         edad_s=(corte-row.sello_evento_utc).total_seconds())
        registros.append(c)
    bloqueos = ['Modelo de salida por contrato sin validación predictiva ni ejecución verificada']
    if (filas.feed == 'indicative').any():
        bloqueos.append('Feed indicative: cotizaciones modificadas; no son precios ejecutables')
    if ref.tipo_precio != 'observado' or 'indicative' in str(ref.feed):
        bloqueos.append('Referencia SPX implícita por paridad, sin precio independiente')
    if edad_ref > 2:
        bloqueos.append('Referencia a más de 2 segundos del corte')
    return dict(fecha=fecha, hora=hora, captura=tag, corte_utc=corte.isoformat(),
                spot=float(ref.precio), referencia=dict(tipo=str(ref.tipo_precio), feed=str(ref.feed), edad_s=edad_ref),
                reglas=dict(REGLAS), registros=registros, bloqueos=bloqueos, apto_compra=False)


def _valores(c, spot, n, cfg, dias, movimientos, choque):
    """Matrices de una compra fija. Banda de supuestos, NO intervalo de confianza."""
    ds, ms = np.broadcast_arrays(np.asarray(dias, float), np.asarray(movimientos, float))
    restante = c['dte']-ds
    antes, vence = restante > 1e-10, np.abs(restante) <= 1e-10
    s = spot*(1+ms/100)
    salida = {}
    for clave, vol, factor in [('nominal', c['iv'], 1.), ('inferior', c['iv_bid'], 2.), ('superior', c['iv_ask'], 1.)]:
        sigma = vol+choque/100
        valores = np.full(ds.shape, np.nan)
        validos = antes & (sigma > 0)
        if validos.any():
            teorico = precio_bs(s[validos], c['strike'], restante[validos]/365,
                               REGLAS['tasa'], REGLAS['dividendo_continuo'], sigma, True)
            valores[validos] = np.maximum(0., teorico-factor*(c['ask']-c['bid'])/2)
        valores[vence] = np.maximum(0., s[vence]-c['strike'])
        salida[clave] = n*(100*(valores-c['ask'])-2*cfg.comision)
    return salida


def _json_array(a):
    a = np.asarray(a)
    return np.where(np.isfinite(a), a, None).tolist()


def _mejor(valores):
    """Criterio a centavos, con efectivo. None no equivale a pérdida ni a cero."""
    disponibles = {k:round(v, 2) for k,v in valores.items() if v is not None}
    disponibles['efectivo'] = 0.
    top = max(disponibles.values())
    return sorted(k for k,v in disponibles.items() if v == top)


def simular_observadas(foto, cfg=None, alternativas=None):
    cfg = cfg or ConfiguracionObservada()
    capital = cfg.presupuesto*cfg.riesgo_pct/100
    candidatos, exclusiones = [], []
    embudo = dict(calls=len(foto['registros']), modelo=0, calidad=0, horizonte=0, presupuesto=0)
    inventario = {}
    for c in foto['registros']:
        raiz = inventario.setdefault(c['raiz'], dict(calls=0, caben_sin_filtrar=0))
        raiz['calls'] += 1
        coste = c['coste_unitario_sin_comision']
        if coste is not None and coste+2*cfg.comision <= capital:
            raiz['caben_sin_filtrar'] += 1
        motivos = list(c['motivos'])
        if 'instrumento_no_admitido' not in motivos: embudo['modelo'] += 1
        if not motivos:
            embudo['calidad'] += 1
            if c['dte'] < cfg.dias:
                motivos.append('vence_antes_del_objetivo')
            else:
                embudo['horizonte'] += 1
                n = min(math.floor(capital/(100*c['ask']+2*cfg.comision)), c['tam_ask'])
                if cfg.max_contratos: n = min(n, cfg.max_contratos)
                if n < 1: motivos.append('fuera_del_presupuesto')
                else:
                    embudo['presupuesto'] += 1
                    candidatos.append((c, n))
        if motivos: exclusiones.append(dict(contrato=c['contrato'], motivos=motivos))
    cs = {c['contrato']:(c,n) for c,n in candidatos}
    if alternativas is not None:
        if not isinstance(alternativas,list) or len(alternativas) != 2:
            raise ValueError('Indica dos compras alternativas')
        elegidos = []
        for e in alternativas:
            if not isinstance(e,dict) or set(e) != {'contrato','cantidad'} or not isinstance(e['contrato'], str) or e['contrato'] not in cs:
                raise ValueError('Contrato observado no elegible')
            c, limite = cs[e['contrato']]
            n = e['cantidad']
            if type(n) is not int or not 1 <= n <= limite:
                raise ValueError(f'Cantidad fuera del límite de {limite}')
            elegidos.append((c, n))
    else:
        elegidos = candidatos
    movimientos = sorted(set([-6., -3., 0., 1.5, 3., 4.5, 6., 9., 12., cfg.movimiento_pct]))
    plazos = sorted(set([0, 3, 7, 14, 21, 28, 35, 45, cfg.dias]))
    choques = [cfg.cambio_iv_pp+x for x in (-5., 0., 5.)]
    casos = [('objetivo',cfg.dias,cfg.movimiento_pct,cfg.cambio_iv_pp),
             ('mitad',cfg.dias,cfg.movimiento_pct/2,cfg.cambio_iv_pp),
             ('sin_movimiento',cfg.dias,0.,cfg.cambio_iv_pp),
             ('baja_3',cfg.dias,-3.,cfg.cambio_iv_pp),
             ('iv_menor',cfg.dias,cfg.movimiento_pct,cfg.cambio_iv_pp-5),
             ('tarde',cfg.dias+7,cfg.movimiento_pct,cfg.cambio_iv_pp),
             ('combinado',cfg.dias+7,cfg.movimiento_pct/2,cfg.cambio_iv_pp-5)]
    posiciones = []
    for j, (c,n) in enumerate(elegidos):
        mapas = []
        for v in choques:
            z = _valores(c, foto['spot'], n, cfg, np.asarray(plazos)[:,None], np.asarray(movimientos)[None,:], v)
            mapas.append({k:_json_array(a) for k,a in z.items()})
        controles = []
        for nombre,d,m,v in casos:
            z = _valores(c, foto['spot'], n, cfg, d, m, v)
            controles.append(dict(nombre=nombre,dias=d,movimiento_pct=m,cambio_iv_pp=v,
                                  **{k:_json_array(a) for k,a in z.items()}))
        reservado = n*(100*c['ask']+2*cfg.comision)
        posiciones.append(dict(contrato=c['contrato'], lado=('AB'[j] if alternativas is not None else None),
            strike=c['strike'], dte=c['dte'], cantidad=n, max_cantidad=cs[c['contrato']][1],
            capital_reservado=reservado, efectivo_libre=cfg.presupuesto-reservado,
            prima_por_contrato=100*c['ask'], iv_pct=100*c['iv'], edad_s=c['edad_s'],
            controles=controles, mapas=mapas))
    # Comparación por índice para conservar dos cantidades distintas del mismo contrato.
    ganadores, separados = [], []
    for k in range(len(casos)):
        vals = {str(i):p['controles'][k]['nominal'] for i,p in enumerate(posiciones)}
        mejor = _mejor(vals)
        ganadores.append(mejor if all(v is not None for v in vals.values()) else None)
        dominantes = []
        bandas_completas = all(p['controles'][k][extremo] is not None
                              for p in posiciones for extremo in ('inferior', 'superior'))
        for i,p in enumerate(posiciones):
            lo = p['controles'][k]['inferior']
            otros = [0.] + [x['controles'][k]['superior'] for j,x in enumerate(posiciones) if j != i]
            if bandas_completas and lo is not None and all(x is not None for x in otros) and lo > max(otros)+.01:
                dominantes.append(str(i))
        separados.append(dominantes)
    motivos = {}
    for e in exclusiones:
        for m in e['motivos']: motivos[m] = motivos.get(m,0)+1
    return dict(version=1, configuracion=asdict(cfg), captura=foto['captura'],
        spot=foto['spot'], referencia=foto['referencia'], reglas=foto['reglas'],
        apto_compra=False, bloqueos=foto['bloqueos'], probabilidades='no estimadas',
        embudo=embudo, inventario=inventario, exclusiones=exclusiones, motivos=motivos,
        posiciones=posiciones, mejores_nominales=ganadores, separados_banda=separados,
        mejor_objetivo=ganadores[0],
        ejes=dict(movimientos_pct=movimientos,plazos_dias=plazos,choques_iv_pp=choques),
        alcance=['Foto histórica: no describe el mercado actual.',
                 'IV bid/mid/ask por contrato; no es una superficie calibrada ni una PDF.',
                 'Banda: IV bid–ask y salida menos 1–2 semispreads; no es confianza estadística.',
                 'Cantidades fijas, limitadas por presupuesto y tamaño ask publicado.',
                 'Tasa 4% y dividendo continuo 1.3% son supuestos; no curvas observadas.',
                 'Fuera del vencimiento o IV no positiva: ausente, nunca cero.',
                 'Una ausencia impide declarar ganador completo; efectivo conserva su valor.',
                 'No se modela ejecución ni ejercicio americano; SPY se excluye.',
                 'Los días son naturales; valoración teórica, sin garantizar sesión abierta.'])
