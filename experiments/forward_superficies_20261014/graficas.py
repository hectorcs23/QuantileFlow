"""Figuras agregadas públicas y construcción de una superficie privada local."""
import argparse
import json
from pathlib import Path
import sys
RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import pandas as pd
from quantileflow.opciones import vol_implicita_black
from experiments.forward_superficies_20261014.evaluar import restaurar

NAVY='#17354b';TEAL='#167d78';BLUE='#467fa8';ORANGE='#cc6946'


def configurar():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,
        'axes.titleweight':'bold','axes.labelcolor':NAVY,'text.color':NAVY,
        'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})


def guardar(fig,path):
    fig.savefig(path,dpi=160,bbox_inches='tight')
    fig.savefig(path.with_suffix('.svg'),bbox_inches='tight')
    plt.close(fig)


def publicas(r,out):
    fig,ax=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    labels=['F declarado\nIV plana','F declarado\nSSVI','F estimado\nIV plana','F estimado\nSSVI']
    combos=[(f,m) for f in ('declarado','estimado') for m in ('plano','ssvi')]
    yy=[100*r['total'][f][m]['dentro']/r['total'][f][m]['filas'] for f,m in combos]
    bars=ax[0].bar(np.arange(4),yy,color=[BLUE,ORANGE,BLUE,ORANGE],width=.65)
    ax[0].bar_label(bars,labels=[f'{v:.1f}%' for v in yy],padding=5,fontweight='bold')
    ax[0].set(xticks=np.arange(4),xticklabels=labels,ylim=(0,100),ylabel='Cotizaciones reservadas dentro de bid/ask (%)',title='Separar referencia y forma del smile')
    x=np.arange(12)
    for f,m,color,style in [('declarado','plano',BLUE,'--'),('declarado','ssvi',ORANGE,'--'),('estimado','plano',BLUE,'-'),('estimado','ssvi',ORANGE,'-')]:
        ax[1].plot(x,r['total'][f][m]['medianas_por_corte'],style,marker='o',color=color,label=f'{m.upper()} / F {f}',markersize=4)
    ax[1].set(xticks=x,xticklabels=[c['fecha'][8:]+'\n'+c['hora'] for c in r['cortes']],ylabel='Mediana de error absoluto / semispread',title='Mejorar el ajuste no elimina el error',ylim=(0,14))
    ax[1].tick_params(axis='x',labelsize=7)
    ax[1].axhline(1,color=TEAL,alpha=.6,lw=1)
    ax[1].legend(fontsize=8,loc='upper right')
    for a in ax: a.grid(axis='y',alpha=.15);a.set_axisbelow(True)
    fig.suptitle('QuantileFlow | 6 sesiones conocidas, 12 fotos, 1,642 precios reservados',fontsize=14,fontweight='bold')
    fig.text(.5,-.045,'El forward se estima solo con entrenamiento. Misma selección de strikes y misma pérdida.\nResultados descriptivos del feed gratuito; no prueba predictiva ni cotizaciones ejecutables.',ha='center',fontsize=10)
    guardar(fig,out/'contraste_forward.png')

    fig,ax=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    for i,grp in enumerate(('train','holdout')):
        vals=[]
        for f in ('declarado','estimado'):
            pp=r['total'][f]['paridad'][f+('_holdout' if grp=='holdout' else '')]
            vals.append(100*pp['incompatibles']/pp['pares'])
        bars=ax[0].bar(np.arange(2)+i*.34-.17,vals,width=.33,color=[BLUE,TEAL][i],label=['Entrenamiento','Reservados'][i])
        ax[0].bar_label(bars,labels=[f'{v:.1f}%' for v in vals],padding=4)
    ax[0].set(xticks=[0,1],xticklabels=['F declarado','F estimado'],ylim=(0,100),title='Pares call/put incompatibles',ylabel='Pares cuya banda excluye la paridad (%)')
    ax[0].legend(loc='upper right')
    scenarios=[(.03,.013),(.04,.013),(.05,.013),(.04,.003),(.04,.023)]
    for field,color in [('declarado',BLUE),('estimado',TEAL),('minimo',ORANGE)]:
        vals=[]
        for rate,q in scenarios:
            rows=[v for v in r['carry'] if v['tasa']==rate and v['q']==q]
            vals.append(100*sum(v[field] for v in rows)/sum(v['pares'] for v in rows))
        ax[1].plot(np.arange(5),vals,'o',color=color,label={'declarado':'F declarado','estimado':'F estimado por pérdida','minimo':'Mínimo posible: mejor solapamiento'}[field])
    ax[1].set(xticks=np.arange(5),xticklabels=['r 3%\nq 1.3%','r 4%\nq 1.3%','r 5%\nq 1.3%','r 4%\nq 0.3%','r 4%\nq 2.3%'],ylim=(0,105),title='Sensibilidad a carry, solo entrenamiento',ylabel='Pares incompatibles (%)')
    ax[1].legend(loc='lower left',fontsize=8)
    for a in ax:a.grid(axis='y',alpha=.15);a.set_axisbelow(True)
    fig.suptitle('Un forward mejor no vuelve compatibles todas las cotizaciones',fontsize=14,fontweight='bold')
    fig.text(.5,-.05,'Shocks ilustrativos de tasa/dividendo: no son estimaciones de sus valores verdaderos.\nEste control de carry no recalibra superficies ni modifica rankings.',ha='center',fontsize=10)
    guardar(fig,out/'paridad_carry.png')


def superficie_privada(r,private):
    # Protocol-fixed first chronological photo, no selection by outcome.
    c=r['cortes'][0];tag=c['fecha']+'_'+c['hora'].replace(':','')
    p=json.loads((private/(tag+'_parametros.json')).read_text(encoding='utf-8'))
    e=pd.read_parquet(private/(tag+'_evaluacion.parquet'))
    fit=restaurar(p['ajustes']['estimado']);old=restaurar(p['ajustes']['declarado'])
    ts=fit.superficie.tiempos;T=ts[0];D=np.exp(-p['tasa']*T)
    F=p['forwards'][str(T)]['estimado'];F0=p['forwards'][str(T)]['declarado']
    gg=e[np.isclose(e.dias,T*365,rtol=0,atol=1e-10)]
    k=np.linspace(-.035,.035,251)
    fig=plt.figure(figsize=(13.4,10),layout='constrained')
    a=fig.add_subplot(221)
    dropped=0
    for typ,marker,color in [('C','o',BLUE),('P','^',ORANGE)]:
        g=gg[gg.tipo==typ];ks=np.log(g.strike.to_numpy()/F)
        vals=[vol_implicita_black(v.to_numpy(),F,g.strike.to_numpy(),T,D,typ=='C') for v in (g.bid,(g.bid+g.ask)/2,g.ask)]
        lo,mid,hi=vals;valid=np.isfinite(lo)&np.isfinite(mid)&np.isfinite(hi)
        dropped+=int((~valid).sum())
        a.vlines(100*ks[valid],100*lo[valid],100*hi[valid],color=color,alpha=.35,lw=.8)
        tr=g.entrenamiento.to_numpy()
        for train in (True,False):
            mask=valid&(tr==train)
            a.scatter(100*ks[mask],100*mid[mask],s=22,marker=marker,
                facecolors=color if train else 'none',edgecolors=color,label=f'{typ}: '+('ajuste' if train else 'reserva'))
    a.plot(100*k,100*np.sqrt(fit.superficie.w(k,T)/T),color=TEAL,lw=2,label='SSVI / F estimado')
    a.plot(100*k,100*np.sqrt(old.superficie.w(k+np.log(F/F0),T)/T),color=NAVY,lw=1.4,ls='--',label='SSVI / F declarado')
    a.axhline(100*fit.planas[T],color='#777777',ls=':',label='IV plana / F estimado')
    a.set(title='1. Un vencimiento: cotizaciones y curva ajustada',xlabel='100 × log(K / F estimado)',ylabel='Volatilidad implícita (%)')
    a.grid(alpha=.15);a.legend(fontsize=7,ncol=2)

    a3=fig.add_subplot(222,projection='3d')
    tt=np.linspace(ts[0],ts[-1],35);kk=np.linspace(-.03,.03,55)
    km,tm=np.meshgrid(kk,tt);iv=100*np.sqrt(fit.superficie.w(km,tm)/tm)
    a3.plot_surface(100*km,tm*365,iv,cmap='viridis',alpha=.85,linewidth=0,antialiased=True)
    for t in ts:a3.plot(100*kk,np.full_like(kk,t*365),100*np.sqrt(fit.superficie.w(kk,t)/t),color=NAVY,lw=1)
    a3.set(title='2. Unir las cuatro curvas por varianza ATM',xlabel='100 × log(K / F)',ylabel='Días hasta vencer',zlabel='IV (%)')
    a3.view_init(25,-58);a3.tick_params(labelsize=8)

    b=fig.add_subplot(223)
    tt=np.linspace(7/365,60/365,180);kk=np.linspace(-.10,.10,151)
    km,tm=np.meshgrid(kk,tt);iv=100*np.sqrt(fit.superficie.w(km,tm)/tm)
    im=b.pcolormesh(100*km,tm*365,iv,cmap='viridis',shading='auto')
    shifts=np.array([np.log(p['forwards'][str(t)]['declarado']/p['forwards'][str(t)]['estimado']) for t in ts])
    boundaries=100*np.interp(tt,ts,shifts)
    supported=(tt>=ts[0])&(tt<=ts[-1])
    ys=tt[supported]*365;left=boundaries[supported]-3;right=boundaries[supported]+3
    # Include exact maturity endpoints rather than omit them on a coarse heatmap grid.
    ys=np.r_[ts[0]*365,ys,ts[-1]*365]
    left=np.r_[100*shifts[0]-3,left,100*shifts[-1]-3]
    right=np.r_[100*shifts[0]+3,right,100*shifts[-1]+3]
    b.plot(np.r_[left,right[::-1],left[0]],np.r_[ys,ys[::-1],ys[0]],color='white',lw=2.2)
    b.annotate('Única franja respaldada\npor esta muestra',xy=(0,ts.mean()*365),xytext=(-9,47),color='white',fontsize=10,
        arrowprops={'arrowstyle':'->','color':'white','lw':1.5})
    b.set(title='3. La fórmula dibuja más de lo que observamos',xlabel='100 × log(K / F)',ylabel='Días hasta vencer')
    fig.colorbar(im,ax=b,label='IV del modelo (%)',shrink=.8)

    d=fig.add_subplot(224)
    kp=np.linspace(-.14,.14,801);xx=100*np.exp(kp)
    # Density of X=100*S_T/F, not the physical density of realized returns.
    dens=fit.superficie.densidad(kp,T)/xx
    w=fit.planas[T]**2*T
    flat=np.exp(-.5*((kp+w/2)/np.sqrt(w))**2)/np.sqrt(2*np.pi*w)/xx
    d.plot(xx,dens,color=TEAL,lw=2,label='PDF Q / SSVI')
    d.plot(xx,flat,color=BLUE,lw=1.6,ls='--',label='PDF Q / IV plana')
    d.axvspan(100*np.exp(-.03)*F0/F,100*np.exp(.03)*F0/F,color=TEAL,alpha=.10,label='Ventana de ajuste original ≈ ±3%')
    d.set(title='4. Curvatura de precios → densidad Q',xlabel='Precio terminal / forward × 100',ylabel='Densidad por punto de este eje')
    d.grid(alpha=.15);d.legend(fontsize=8)
    # Window is schematic on normalized axis because training used the original F.
    fig.suptitle(f'Cómo construimos la superficie | SPXW {c["fecha"]}, {c["hora"]} ET',fontsize=15,fontweight='bold')
    fig.text(.5,-.085,f'Primera foto cronológica, no el mejor ajuste. Panel 1: intervalos bid/ask; {dropped} filas sin IV invertible con F estimado.\n'
        'La franja conserva la ventana de ±3% del F original, sin refiltrar. Entre vencimientos se interpola; fuera se extrapola.\n'
        'Superficie y PDF Q de un modelo: no son probabilidades físicas ni una predicción de ganancia.',ha='center',fontsize=10)
    guardar(fig,private/'construccion_superficie.png')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--privado',type=Path,required=True)
    a=ap.parse_args()
    if a.privado.resolve().is_relative_to(RAIZ):raise ValueError('figuras de cotizaciones fuera del repo')
    configurar()
    out=Path(__file__).parent/'resultados';r=json.loads((out/'resumen.json').read_text(encoding='utf-8'))
    publicas(r,out);superficie_privada(r,a.privado)


if __name__=='__main__':main()
