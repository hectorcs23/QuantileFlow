"""Caso US$300 con una foto histórica. Nada individual se publica en Git."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
from quantileflow.observadas import cargar_tablas, preparar_observadas, simular_observadas, ConfiguracionObservada
from experiments.cadena_comparador_20261010.evaluar_cadena import integridad

DIR=Path(__file__).resolve().parent


def dump(p,x):
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')


def bs(s,k,t,v):
    d1=(math.log(s/k)+(.04-.013+v*v/2)*t)/(v*math.sqrt(t));d2=d1-v*math.sqrt(t)
    N=lambda x:(1+math.erf(x/math.sqrt(2)))/2
    return s*math.exp(-.013*t)*N(d1)-k*math.exp(-.04*t)*N(d2)


def verificar(foto,r):
    """Auditor independiente de precio (erf), caja y ausencias de todas las celdas."""
    cfg=r['configuracion'];errors=[];celdas=ausentes=inversiones=0
    byid={c['contrato']:c for c in foto['registros']}
    for p in r['posiciones']:
        c=byid[p['contrato']];n=p['cantidad']
        cap=cfg['presupuesto']*cfg['riesgo_pct']/100
        assert n==min(math.floor(cap/(c['ask']*100+2*cfg['comision'])),c['tam_ask'])
        assert p['capital_reservado']<=cap and p['efectivo_libre']>=0
        for key,price in [('iv_bid',c['bid']),('iv',(c['bid']+c['ask'])/2),('iv_ask',c['ask'])]:
            errors.append(abs(bs(foto['spot'],c['strike'],c['dte']/365,c[key])-price));inversiones+=1
        for z,shock in zip(p['mapas'],r['ejes']['choques_iv_pp']):
            for kind,iv,factor in [('nominal',c['iv'],1),('inferior',c['iv_bid'],2),('superior',c['iv_ask'],1)]:
                for i,d in enumerate(r['ejes']['plazos_dias']):
                    for j,m in enumerate(r['ejes']['movimientos_pct']):
                        actual=z[kind][i][j];remaining=c['dte']-d
                        if remaining < -1e-10 or (remaining>1e-10 and iv+shock/100<=0):
                            assert actual is None;ausentes+=1;continue
                        s=foto['spot']*(1+m/100)
                        val=(max(0.,s-c['strike']) if abs(remaining)<=1e-10 else
                             max(0.,bs(s,c['strike'],remaining/365,iv+shock/100)-factor*(c['ask']-c['bid'])/2))
                        expected=n*((val-c['ask'])*100-2*cfg['comision'])
                        errors.append(abs(expected-actual));celdas+=1
                        assert actual>=-p['capital_reservado']-1e-7
    error=max(errors,default=0.)
    assert error < 1e-6
    return dict(celdas_con_valor=celdas,celdas_ausentes_verificadas=ausentes,
                inversiones_comprobadas=inversiones,error_maximo_abs=error,
                formula='Normal CDF mediante math.erf, independiente del ndtr del motor')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('tablas','crudo','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();priv=a.privado.resolve()
    if priv.is_relative_to(ROOT) or any(priv.is_relative_to(x.resolve()) or x.resolve().is_relative_to(priv) for x in (a.tablas,a.crudo)):
        raise ValueError('La salida privada debe estar separada de código y entradas')
    priv.mkdir(parents=True,exist_ok=True);out=DIR/'resultados';out.mkdir(exist_ok=True)
    checks=integridad(a.tablas,a.crudo)
    q,s=cargar_tablas(a.tablas)
    # Última sesión de las tablas locales verificadas, primer corte. No elegida por PnL.
    foto=preparar_observadas(q,s,'2026-10-22','09:45')
    cfg=ConfiguracionObservada();r=simular_observadas(foto,cfg)
    ver=verificar(foto,r)
    dump(priv/'analisis.json',r)
    ps=r['posiciones'];cases=[]
    for k in range(7):
        nom=[p['controles'][k]['nominal'] for p in ps]
        lo=[p['controles'][k]['inferior'] for p in ps]
        cases.append(dict(nombre=ps[0]['controles'][k]['nombre'],
            positivas_nominal=sum(x is not None and x>0 for x in nom),
            positivas_banda_inferior=sum(x is not None and x>0 for x in lo),
            faltantes=sum(x is None for x in nom),
            ganador_efectivo=r['mejores_nominales'][k]==['efectivo'],
            ganador_separado=bool(r['separados_banda'][k])))
    changes=[]
    for presupuesto in (100.,200.,300.,500.):
        x=simular_observadas(foto,ConfiguracionObservada(presupuesto=presupuesto))
        changes.append(dict(presupuesto=presupuesto,elegibles=x['embudo']['presupuesto']))
    resumen=dict(fecha_analisis='2026-11-06',captura=r['captura'],configuracion=asdict(cfg),
        apto_compra=False,bloqueos=r['bloqueos'],embudo=r['embudo'],inventario=r['inventario'],
        motivos=r['motivos'],reglas=r['reglas'],casos=cases,sensibilidad_presupuesto=changes,
        dte_min=min(p['dte'] for p in ps),dte_max=max(p['dte'] for p in ps),
        strike_distancia_pct_min=min(100*(p['strike']/foto['spot']-1) for p in ps),
        strike_distancia_pct_max=max(100*(p['strike']/foto['spot']-1) for p in ps),
        ganador_cambia_con_retraso=r['mejores_nominales'][0]!=r['mejores_nominales'][5],
        integridad=checks,verificacion_numerica=ver,
        analisis_privado_sha256=hashlib.sha256((priv/'analisis.json').read_bytes()).hexdigest())
    dump(out/'resumen.json',resumen)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(12,5),gridspec_kw={'width_ratios':[1,1.35]})
    counts=[r['embudo']['calls'],r['embudo']['modelo'],r['embudo']['calidad'],r['embudo']['horizonte'],r['embudo']['presupuesto'],0]
    labels=['Calls observados','SPXW europeo PM','Calidad básica + IV','Cubre siete días','Cabe en 300 USD','Compra habilitada']
    bars=axes[0].barh(labels,counts,color=['#9aabb3']*4+['#217c9c','#b45430'])
    axes[0].invert_yaxis();axes[0].bar_label(bars,padding=4);axes[0].set_xlim(0,2200)
    axes[0].set_title('Del inventario a una comparación posible',loc='left',fontweight='bold')
    labels2=['+3%, 7 días','+1.5%, 7 días','Sin movimiento','−3%, 7 días','+3%, IV −5 pp','+3%, 14 días','Mitad + tarde + IV −5']
    yy=np.arange(7);axes[1].barh(yy-.17,[x['positivas_nominal'] for x in cases],height=.32,color='#217c9c',label='Ganancia nominal')
    axes[1].barh(yy+.17,[x['positivas_banda_inferior'] for x in cases],height=.32,color='#84b6a4',label='Ganancia con supuestos adversos')
    axes[1].set_yticks(yy,labels2);axes[1].invert_yaxis();axes[1].set_xlim(0,60)
    axes[1].set_xlabel('Posiciones con PnL positivo, entre 57')
    axes[1].set_title('El resultado depende de la hipótesis',loc='left',fontweight='bold');axes[1].legend(loc='lower right',fontsize=8)
    for ax in axes:ax.spines[['top','right']].set_visible(False)
    fig.suptitle('QuantileFlow · 300 USD · captura histórica del 22 oct 2026, 09:45 ET',fontsize=15,fontweight='bold')
    fig.text(.01,.015,'Feed indicativo + SPX implícito. Conteos condicionales; no probabilidades ni recomendaciones de compra.',fontsize=9,color='#555')
    fig.tight_layout(rect=[0,.05,1,.94]);fig.savefig(out/'diagnostico.png',dpi=160);plt.close(fig)
    # Detalle por contrato solo en carpeta privada. Mantiene la posición ganadora del escenario base.
    i=int(r['mejores_nominales'][0][0]);p=ps[i]
    fig,axes=plt.subplots(1,3,figsize=(16,6),sharey=True)
    arrays=[np.array([[np.nan if x is None else x for x in row] for row in p['mapas'][k]['nominal']]) for k in range(3)]
    vmax=max(1.,max(np.nanmax(x) for x in arrays));norm=TwoSlopeNorm(vmin=-p['capital_reservado'],vcenter=0,vmax=vmax)
    cmap=plt.get_cmap('RdBu').copy();cmap.set_bad('#e5e6e5')
    for ax,z,shock in zip(axes,arrays,r['ejes']['choques_iv_pp']):
        im=ax.imshow(z,cmap=cmap,norm=norm,aspect='auto')
        ax.set_xticks(range(len(r['ejes']['movimientos_pct'])),[f'{x:g}%' for x in r['ejes']['movimientos_pct']],rotation=45)
        ax.set_yticks(range(len(r['ejes']['plazos_dias'])),r['ejes']['plazos_dias'])
        ax.set_title(f'IV {shock:+g} puntos');ax.set_xlabel('Movimiento acumulado de SPX')
        for row in range(z.shape[0]):
            for col in range(z.shape[1]):
                val=z[row,col]
                dark=np.isfinite(val) and (val>vmax*.55 or val < -p['capital_reservado']*.55)
                ax.text(col,row,'—' if np.isnan(val) else f'{val:,.0f}',ha='center',va='center',fontsize=7,color='white' if dark else '#202020')
    axes[0].set_ylabel('Días naturales hasta salir')
    fig.suptitle(f"Compra fija: {p['cantidad']} contrato(s) call · {p['dte']:.2f} DTE · reservado {p['capital_reservado']:.2f} USD",fontweight='bold')
    fig.text(.02,.025,'Misma entrada y cantidad en todas las celdas. PnL teórico en USD; gris = plazo no valorable. Feed indicativo: ninguna compra validada.',fontsize=10)
    fig.tight_layout(rect=[0,.08,.94,.94]);cb=fig.add_axes([.95,.22,.012,.5]);fig.colorbar(im,cax=cb,label='PnL, USD')
    fig.savefig(priv/'mapa_posicion.png',dpi=160);plt.close(fig)
    print(json.dumps(dict(embudo=r['embudo'],casos=cases,verificacion=ver),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
