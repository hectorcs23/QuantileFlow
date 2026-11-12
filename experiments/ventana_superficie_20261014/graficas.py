"""Agregados públicos y ejemplo de superficie local, sin publicar cotizaciones."""
import argparse
import json
from pathlib import Path
import sys
RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from quantileflow.superficies import SuperficieSSVI
from quantileflow.opciones import vol_implicita_black

COLORS=['#167d78','#467fa8','#cc6946']


def restore(p):
    return SuperficieSSVI(np.array(p['tiempos']),np.array(p['thetas']),p['rho'],p['eta'],p['gamma'])


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--privado',type=Path,required=True)
    a=ap.parse_args()
    if a.privado.resolve().is_relative_to(RAIZ):raise ValueError('privados fuera del repo')
    out=Path(__file__).parent/'resultados';r=json.loads((out/'resumen.json').read_text(encoding='utf-8'))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':13,'axes.titleweight':'bold'})
    fig,ax=plt.subplots(1,2,figsize=(13,5.1));fig.subplots_adjust(bottom=.29,top=.83,wspace=.27)
    rings=['centro','alas_3_6','alas_6_10'];x=np.arange(3)
    for j,t in enumerate(r['total']):
        yy=[100*t['holdout_por_anillo'][ring]['dentro']/t['holdout_por_anillo'][ring]['filas'] for ring in rings]
        bars=ax[0].bar(x+(j-1)*.24,yy,width=.23,color=COLORS[j],label=f'Ventana ±{100*t["ancho"]:.0f}% log')
        for i,bar in enumerate(bars):
            if i>j:bar.set_hatch('//')
        ax[0].bar_label(bars,labels=[f'{y:.1f}' for y in yy],padding=3,fontsize=9)
        ax[1].plot(np.arange(5),t['cuantiles_dentro_training'],'o-',color=COLORS[j],label=f'±{100*t["ancho"]:.0f}% log')
    ax[0].set(xticks=x,xticklabels=['Centro ≤3%\n1,642 reservas','Alas 3–6%\n800 reservas','Alas 6–10%\n605 reservas'],
        ylabel='Precios reservados dentro del bid/ask (%)',ylim=(0,65),title='Más cobertura no mejora todo el ajuste')
    ax[0].legend(fontsize=9,loc='upper right')
    ax[1].set(xticks=np.arange(5),xticklabels=['5%','25%','50%','75%','95%'],ylim=(-3,54),
        ylabel='Curvas con cuantil dentro del rango de training',title='Cobertura geométrica de los cuantiles')
    ax[1].legend(loc='lower center',ncol=3,fontsize=9)
    for v in ax:v.grid(axis='y',alpha=.15);v.set_axisbelow(True)
    fig.suptitle('Ampliar strikes: ganamos alcance, aparece un compromiso de ajuste',fontsize=16,fontweight='bold')
    fig.text(.5,.075,'48 curvas de seis sesiones conocidas. Reservas centrales idénticas entre versiones.\n'
        'Barras rayadas: extrapolación fuera de la ventana de ajuste. Anchos de log-moneyness, aproximadamente porcentajes.\n'
        'Estar dentro del rango no identifica una probabilidad verdadera; todas las fotos siguen bloqueadas para uso operativo.',ha='center',fontsize=10)
    fig.savefig(out/'cobertura_ajuste.png',dpi=165);plt.close(fig)

    # First chronological photo, never selected by fit quality.
    c=r['cortes'][0];tag=c['fecha']+'_'+c['hora'].replace(':','')
    e=pd.read_parquet(a.privado/(tag+'_evaluacion.parquet'))
    p=json.loads((a.privado/(tag+'_modelos.json')).read_text(encoding='utf-8'))
    fig=plt.figure(figsize=(13,6));fig.subplots_adjust(left=.07,right=.96,bottom=.24,top=.83,wspace=.27)
    ax=fig.add_subplot(121);surf=fig.add_subplot(122,projection='3d')
    first=p['modelos'][0]['rebanadas'][0];T=first['T'];g=e[np.isclose(e.dias,T*365,rtol=0,atol=1e-10)]
    Fdecl=p['spot']*np.exp((p['tasa']-p['q'])*T)
    Fwide=p['modelos'][-1]['rebanadas'][0]['F'];D=first['D']
    for typ,marker,color in [('C','o','#467fa8'),('P','^','#cc6946')]:
        gg=g[g.tipo.eq(typ)]
        iv=vol_implicita_black(((gg.bid+gg.ask)/2).to_numpy(),Fwide,gg.strike.to_numpy(),T,D,typ=='C')
        ok=np.isfinite(iv)
        ax.scatter(100*gg.k[ok],100*iv[ok],s=14,marker=marker,color=color,alpha=.55,label=f'{typ} mid: IV con F amplio')
    kk=np.linspace(-.1,.1,301)
    for model,color in zip(p['modelos'],COLORS):
        s=restore(model['parametros']);z=model['rebanadas'][0]
        iv=100*np.sqrt(s.w(kk+np.log(Fdecl/z['F']),T)/T)
        inside=abs(kk)<=model['ancho']
        ax.plot(100*kk,iv,color=color,ls=':',lw=1.2)
        ax.plot(100*kk[inside],iv[inside],color=color,lw=2,label=f'SSVI ±{100*model["ancho"]:.0f}%')
    ax.set(title='Tres ajustes sobre un eje de strike común',xlabel='100 × log(K / F declarado)',ylabel='Volatilidad implícita (%)')
    ax.grid(alpha=.15);ax.legend(fontsize=8)
    model=p['modelos'][-1];s=restore(model['parametros']);tt=np.linspace(s.tiempos[0],s.tiempos[-1],35)
    kk=np.linspace(-.1,.1,71);km,tm=np.meshgrid(kk,tt)
    ratios=np.array([np.log(p['spot']*np.exp((p['tasa']-p['q'])*z['T'])/z['F']) for z in model['rebanadas']])
    shift=np.interp(tt,s.tiempos,ratios)[:,None]
    iv=100*np.sqrt(s.w(km+shift,tm)/tm)
    surf.plot_surface(100*km,tm*365,iv,cmap='viridis',alpha=.88,linewidth=0)
    for z in model['rebanadas']:
        tr=e[e.entrenamiento & np.isclose(e.dias,z['T']*365,rtol=0,atol=1e-10)]
        k=tr.k.to_numpy();Fdecl=p['spot']*np.exp((p['tasa']-p['q'])*z['T'])
        surf.plot(100*k,np.full(len(k),z['T']*365),100*np.sqrt(s.w(k+np.log(Fdecl/z['F']),z['T'])/z['T']),color='#17354b',lw=1)
    surf.set(title='Superficie SSVI ajustada hasta ±10%',xlabel='100 × log(K / F declarado)',ylabel='Días hasta vencer',zlabel='IV (%)')
    surf.view_init(25,-58);surf.tick_params(labelsize=8)
    fig.suptitle(f'SPXW | primera foto: {c["fecha"]}, {c["hora"]} ET',fontsize=16,fontweight='bold')
    fig.text(.5,.06,'Líneas punteadas: extrapolación. Los puntos usan el F de ±10%; cada curva su propio F. Los errores se comparan en precios.\n'
        'Líneas oscuras 3D: tramos de strikes de training en los cuatro vencimientos. Entre líneas se interpola; los huecos no desaparecen.\n'
        'Cotizaciones indicative y referencia implícita: forma de un ajuste descriptivo, no probabilidad física ni señal de posición.',ha='center',fontsize=10)
    fig.savefig(a.privado/'superficie_ampliada.png',dpi=165);plt.close(fig)


if __name__=='__main__':main()
