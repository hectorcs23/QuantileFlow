"""Comparador histórico exploratorio; las tablas y posiciones permanecen privadas.

Calls SPXW europeos PM o, con ``subyacente='SPY'``, calls SPY americanos con
los dividendos en efectivo conocidos al corte. IV por contrato invertida de
bid/mid/ask, sin afirmar que esas IV formen una superficie libre de arbitraje.
Nunca recomienda operar.
"""
from dataclasses import asdict, dataclass, fields
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from scipy.optimize import brentq

from .calendario import apertura, instante, instante_liquidacion
from .opciones import binomial_crr, precio_bs, vol_implicita_black
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


# Qué contratos admite cada subyacente. SPX conserva el dividendo continuo
# heredado del piloto; SPY usa dividendos discretos: los declarados al corte.
SUBYACENTES = dict(SPX=dict(raiz='SPXW', ejercicio='europeo'),
                   SPY=dict(raiz='SPY', ejercicio='americano'))
REGLAS_SPY = dict(dividendo_continuo=0., pasos_arbol=400, margen_fecha_ex_dias=7)


def call_americano(S, K, T, r, sigma, dividendos=(), pasos=REGLAS_SPY['pasos_arbol']):
    """Call americano con dividendos en efectivo ``(t_i, monto)``, en años desde hoy.

    Sin dividendos en ``(0, T]`` y con ``r >= 0`` nunca conviene ejercer antes
    (Merton, 1973): vale lo que el europeo y se usa Black–Scholes con ``q = 0``.
    Con dividendos se usa el árbol CRR con el dividendo en depósito, cuyo error
    baja como ``1/pasos``; las pruebas lo contrastan con Roll–Geske–Whaley.
    """
    if r < 0:
        raise ValueError('call_americano supone una tasa no negativa')
    divs = [(t, m) for t, m in dividendos if 0. < t <= T]
    if not divs:
        return float(precio_bs(S, K, T, r, 0., sigma, True))
    if S <= sum(m*math.exp(-r*t) for t, m in divs):
        raise ValueError('Los dividendos superan el precio del subyacente')
    if sigma <= r*math.sqrt(T/pasos):
        raise ValueError('Volatilidad demasiado baja para el árbol')  # probabilidad fuera de (0, 1)
    return binomial_crr(S, K, T, r, sigma, True, 0., divs, pasos, True)


def _iv_americana(precios, S, K, T, r, divs, vol_min=.01, vol_max=5.):
    """IV de cada precio; NaN si no tiene raíz. Nunca se rellena.

    Sin dividendos en la vida es la inversión europea de siempre. Con ellos se
    invierte el árbol, que no admite volatilidades cercanas a cero.
    """
    if not any(0. < t <= T for t, _ in divs):
        return vol_implicita_black(precios, S*math.exp(r*T), K, T, math.exp(-r*T), True)
    salida = []
    for precio in precios:
        f = lambda v: call_americano(S, K, T, r, v, divs)-precio
        con_raiz = math.isfinite(precio) and f(vol_min) < 0. < f(vol_max)
        salida.append(brentq(f, vol_min, vol_max, xtol=1e-10) if con_raiz else float('nan'))
    return np.array(salida)


def dividendos_al_corte(dividendos, simbolo, corte):
    """Dividendos conocidos al corte y primera fecha ex que podría faltar por declarar.

    Solo cuentan las versiones recibidas antes del corte y no retiradas. De cada
    evento vale la última. ``futuros`` son los declarados con fecha ex posterior
    a la sesión del corte. ``limite`` es la última fecha ex conocida más la
    separación mínima entre dividendos ordinarios menos un margen: un contrato
    que vence ese día o después podría cruzar un dividendo todavía sin declarar.
    Con menos de dos ordinarios no hay cadencia y ``limite`` es ``None``.
    """
    d = dividendos[dividendos.simbolo == simbolo].copy()
    for col in ('recibido_utc', 'retirado_utc'):
        d[col] = pd.to_datetime(d[col], utc=True, errors='coerce')
    d = d[d.recibido_utc <= corte].sort_values('version').groupby('id_evento').tail(1)
    d = d[~(d.retirado_utc <= corte) & d.fecha_ex.notna() & d.monto.notna()]
    d = d.assign(fecha_ex=pd.to_datetime(d.fecha_ex).dt.date).sort_values('fecha_ex')
    if not (np.isfinite(d.monto) & (d.monto > 0)).all():
        raise ValueError('Dividendo con monto inválido')
    hoy = corte.tz_convert('America/New_York').date()
    ordinarios = list(d.fecha_ex[d.clase == 'ordinario'])
    saltos = [(b-a).days for a, b in zip(ordinarios, ordinarios[1:])]
    limite = None
    if saltos and min(saltos) > REGLAS_SPY['margen_fecha_ex_dias']:
        limite = ordinarios[-1]+dt.timedelta(days=min(saltos)-REGLAS_SPY['margen_fecha_ex_dias'])
    futuros = [(f, float(m)) for f, m in zip(d.fecha_ex, d.monto) if f > hoy]
    return dict(conocidos=len(d), futuros=futuros, limite=limite)


def cargar_tablas(ruta, con_dividendos=False):
    """Verifica las huellas de TODAS las tablas de la normalización antes de leer."""
    ruta = Path(ruta).resolve()
    m = json.loads((ruta/'manifiesto_normalizacion.json').read_text(encoding='utf8'))
    if not {'cotizaciones', 'subyacente'} <= set(m['salidas']):
        raise ValueError('Manifiesto sin tablas requeridas')
    for nombre, esperado in m['salidas'].items():
        p = (ruta/(nombre+'.parquet')).resolve()
        if not p.is_relative_to(ruta) or hashlib.sha256(p.read_bytes()).hexdigest() != esperado:
            raise ValueError('Huella de tabla incorrecta')
    tablas = [pd.read_parquet(ruta/'cotizaciones.parquet'), pd.read_parquet(ruta/'subyacente.parquet')]
    if con_dividendos:
        if 'dividendos' not in m['salidas']:
            raise ValueError('Manifiesto sin tabla de dividendos')
        tablas.append(pd.read_parquet(ruta/'dividendos.parquet'))
    return tuple(tablas)


def preparar_observadas(cotizaciones, referencias, fecha, hora='09:45', subyacente='SPX', dividendos=None):
    """Selecciona una única foto causal; SIP disponible más tarde no se incorpora."""
    if subyacente not in SUBYACENTES:
        raise ValueError('Subyacente no admitido')
    admitido = SUBYACENTES[subyacente]
    americano = admitido['ejercicio'] == 'americano'
    if americano and dividendos is None:
        raise ValueError('El ejercicio americano requiere la tabla de dividendos')
    corte = instante(fecha, hora)
    tag = f"{fecha}T{hora.replace(':', '')}"
    filas = cotizaciones[(cotizaciones.captura == tag) & (cotizaciones.tipo == 'C')].copy()
    refs = referencias[(referencias.captura == tag) & (referencias.subyacente == subyacente)].copy()
    if filas.empty or len(refs) != 1:
        raise ValueError(f'Requiere calls y una referencia {subyacente} en la captura')
    if filas.id_contrato.duplicated().any():
        raise ValueError('Contratos duplicados en la captura')
    for col in SELLOS:
        filas[col] = pd.to_datetime(filas[col], utc=True, errors='coerce')
        refs[col] = pd.to_datetime(refs[col], utc=True, errors='coerce')
    ref = refs.iloc[0]
    if not math.isfinite(ref.precio) or ref.precio <= 0:
        raise ValueError(f'Referencia {subyacente} inválida')
    if any(pd.isna(ref[c]) or ref[c] > corte for c in SELLOS):
        raise ValueError('Referencia no disponible al corte')
    if ref.sello_evento_utc > ref.sello_snapshot_utc or ref.sello_snapshot_utc > ref.recibido_utc:
        raise ValueError('Cronología de referencia inválida')
    edad_ref = (corte-ref.sello_evento_utc).total_seconds()
    if edad_ref > REGLAS['edad_maxima_s']:
        raise ValueError(f'Referencia {subyacente} demasiado antigua')
    conocidos = dividendos_al_corte(dividendos, subyacente, corte) if americano else None
    filas = filas.sort_values('id_contrato')
    registros = []
    for _, row in filas.iterrows():
        motivos = []
        def mal(m): motivos.append(m)
        c = dict(contrato=str(row.id_contrato), raiz=str(row.raiz))
        if not (row.raiz == admitido['raiz'] and row.subyacente == subyacente
                and row.ejercicio == admitido['ejercicio'] and row.liquidacion == 'PM'):
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
        divs = []
        if americano and 'instrumento_no_admitido' not in motivos and dte is not None:
            vence = pd.Timestamp(row.vencimiento).date()
            if conocidos['limite'] is None:
                mal('historial_de_dividendos_insuficiente')
            elif vence >= conocidos['limite']:
                mal('dividendo_esperado_sin_declarar')
            # El precio cae al abrir la fecha ex: el vencimiento de ese mismo día ya la cruzó.
            divs = [((apertura(f)-corte).total_seconds()/86400, m)
                    for f, m in conocidos['futuros'] if f <= vence]
        c.update(dte=dte, motivos=motivos)
        if not motivos and americano:
            t, r = dte/365, REGLAS['tasa']
            en_anios = [(x/365, m) for x, m in divs]
            try:
                iv = _iv_americana([row.bid, (row.bid+row.ask)/2, row.ask], ref.precio, row.strike, t, r, en_anios)
            except ValueError:
                iv = np.array([np.nan])
            if not np.isfinite(iv).all():
                mal('iv_no_identificada')
            else:
                c.update(strike=float(row.strike), bid=float(row.bid), ask=float(row.ask),
                         multiplicador=100, tam_ask=math.floor(row.tam_ask),
                         iv_bid=float(iv[0]), iv=float(iv[1]), iv_ask=float(iv[2]),
                         edad_s=(corte-row.sello_evento_utc).total_seconds(),
                         ejercicio='americano', dividendos=divs)
        elif not motivos:
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
        bloqueos.append(f'Referencia {subyacente} implícita por paridad, sin precio independiente')
    elif ref.feed != 'sip':
        bloqueos.append(f'Referencia {subyacente} de {ref.feed}: una sola bolsa, no el consolidado')
    if edad_ref > 2:
        bloqueos.append('Referencia a más de 2 segundos del corte')
    foto = dict(fecha=fecha, hora=hora, captura=tag, corte_utc=corte.isoformat(), subyacente=subyacente,
                spot=float(ref.precio), referencia=dict(tipo=str(ref.tipo_precio), feed=str(ref.feed), edad_s=edad_ref),
                reglas=dict(REGLAS), registros=registros, bloqueos=bloqueos, apto_compra=False)
    if americano:
        foto['reglas'].update(REGLAS_SPY)
        foto['dividendos'] = dict(conocidos_al_corte=conocidos['conocidos'],
            declarados_futuros=[dict(fecha_ex=str(f), monto=m) for f, m in conocidos['futuros']],
            primera_fecha_ex_sin_declarar=None if conocidos['limite'] is None else str(conocidos['limite']))
    return foto


def _teorico(c, s, restante, transcurrido, sigma):
    """Precio teórico por celda. Tras la última fecha ex, el call americano vale lo que el europeo."""
    if c.get('ejercicio') != 'americano':
        return precio_bs(s, c['strike'], restante/365, REGLAS['tasa'], REGLAS['dividendo_continuo'], sigma, True)
    con = np.array([any(t > x for t, _ in c['dividendos']) for x in transcurrido], bool)
    precios = np.empty(s.shape)
    precios[~con] = precio_bs(s[~con], c['strike'], restante[~con]/365, REGLAS['tasa'], 0., sigma, True)
    for i in np.flatnonzero(con):
        divs = [((t-transcurrido[i])/365, m) for t, m in c['dividendos']]
        try:
            precios[i] = call_americano(s[i], c['strike'], restante[i]/365, REGLAS['tasa'], sigma, divs)
        except ValueError:
            precios[i] = np.nan  # fuera del dominio del árbol: ausente, nunca cero
    return precios


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
            teorico = _teorico(c, s[validos], restante[validos], ds[validos], sigma)
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
    alcance_modelo = ['Tasa 4% y dividendo continuo 1.3% son supuestos; no curvas observadas.',
                      'No se modela ejecución ni ejercicio americano; SPY se excluye.']
    if 'dividendos' in foto:
        alcance_modelo = ['Tasa 4% supuesta. Dividendos en efectivo declarados al corte; ninguno estimado.',
                          'Ejercicio americano: sin dividendo en lo que queda de vida vale lo que el europeo; '
                          'con dividendo declarado, árbol binomial. La salida es vender: no se simula ejercer.']
    return dict(version=1, configuracion=asdict(cfg), captura=foto['captura'],
        subyacente=foto['subyacente'], dividendos=foto.get('dividendos'),
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
                 alcance_modelo[0],
                 'Fuera del vencimiento o IV no positiva: ausente, nunca cero.',
                 'Una ausencia impide declarar ganador completo; efectivo conserva su valor.',
                 alcance_modelo[1],
                 'Los días son naturales; valoración teórica, sin garantizar sesión abierta.'])
