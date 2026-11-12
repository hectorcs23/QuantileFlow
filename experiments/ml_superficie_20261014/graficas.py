"""Conteos públicos; curvas y CDF de mercado permanecen solo localmente."""
import argparse,json
from pathlib import Path
import sys
RAIZ=Path(__file__).resolve().parents[2];sys.path.insert(0,str(RAIZ))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from quantileflow.opciones import vol_implicita_black
from quantileflow.superficies import Rebanada,cdf_logmoneyness
from experiments.forward_superficies_20261014.evaluar import restaurar
from experiments.ml_superficie_20261014.modelos import CorreccionRed,DistribucionConvexa

COLORS={'ssvi':'#167d78','red':'#cc6946','convexo':'#467fa8'}
LABELS={'ssvi':'SSVI','red':'SSVI + red pequeña','convexo':'Distribución convexa'}


def save(fig,path):
    fig.savefig(path,dpi=160,bbox_inches='tight');plt.close(fig)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--privado',type=Path,required=True);a=ap.parse_args()
    if a.privado.resolve().is_relative_to(RAIZ):raise ValueError('curvas privadas fuera de Git')
    folder=Path(__file__).parent/'resultados';r=json.loads((folder/'resumen.json').read_text(encoding='utf-8'))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold'})
    fig,axs=plt.subplots(1,3,figsize=(15,5.4),layout='constrained')
    vals=[100*r['total'][m]['dentro']/r['total'][m]['filas'] for m in LABELS]
    bars=axs[0].bar(np.arange(3),vals,color=list(COLORS.values()),width=.65)
    axs[0].bar_label(bars,labels=[f'{v:.2f}%' for v in vals],padding=4,fontweight='bold')
    axs[0].set(xticks=[0,1,2],xticklabels=['SSVI','SSVI + red\n(candidatos)','Convexo'],ylim=(0,100),ylabel='Reservados dentro de bid/ask (%)',title='Más flexibilidad no asegura mejora')
    x=np.arange(len(r['cortes']))
    for m in LABELS:axs[1].plot(x,r['total'][m]['medianas_error_por_corte'],'o-',color=COLORS[m],label=LABELS[m],markersize=4)
    axs[1].set(title='Error de precio por foto',ylabel='Mediana / semispread',xticks=x,xticklabels=[c['fecha'][8:] for c in r['cortes']])
    axs[1].legend(fontsize=8);axs[1].set_xlabel('Día de octubre; 09:45 y 10:00 en cada par')
    gm=[c['red']['elegido']['g_min_malla'] for c in r['cortes']]
    axs[2].axhline(0,color='#333333',lw=1)
    axs[2].scatter(x,gm,c=[COLORS['red'] if g<0 else COLORS['ssvi'] for g in gm],s=40)
    axs[2].set(title='Control de densidad de la red',ylabel='Mínimo de g en malla independiente',xticks=x,xticklabels=[c['fecha'][8:] for c in r['cortes']],ylim=(-.18,.30),yticks=[-.15,-.10,0,.10,.20,.30])
    for i,g in enumerate(gm):
        if g<0:axs[2].annotate(f'{g:.3f}',(i,g),xytext=(4,-15),textcoords='offset points',fontsize=9,color=COLORS['red'])
    axs[2].set_xlabel('g negativo implica PDF negativa en algún punto')
    for ax in axs:ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('QuantileFlow | mismo F y mismos 1,642 precios reservados | seis sesiones conocidas',fontsize=14,fontweight='bold')
    fails=len(r['cortes'])-r['total']['red']['cortes_pasan_malla']
    fig.text(.5,-.13,f'La cobertura de la red muestra todos los candidatos, incluidos {fails} rechazados por coherencia.\n'
        'Malla positiva no certifica ausencia global de arbitraje. El convexo tiene átomos, no una PDF suave.\n'
        'Ajuste exploratorio del feed gratuito; no predicción ni precios ejecutables.',ha='center',fontsize=10)
    save(fig,folder/'comparacion_modelos.png')

    c=r['cortes'][0];tag=c['fecha']+'_'+c['hora'].replace(':','')
    p=json.loads((a.privado/(tag+'_modelos.json')).read_text(encoding='utf-8'))
    fit=restaurar(p['origen_parametros']['ajustes']['estimado']);s=fit.superficie
    red=CorreccionRed(s,np.array(p['red_pesos']))
    conv=DistribucionConvexa(np.array(p['convexo_tiempos']),np.array(p['convexo_soporte']),np.array(p['convexo_masas']))
    t=s.tiempos[0];forward=p['origen_parametros']['forwards'][str(t)];F,D=forward['estimado'],forward['D']
    k=np.linspace(-.08,.08,601);K=F*np.exp(k)
    reb=Rebanada(t,F,D,K,np.zeros(len(k)),np.ones(len(k)),np.ones(len(k),dtype=bool))
    fig,ax=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    ivs={'ssvi':np.sqrt(s.w(k,t)/t),'red':np.sqrt(red.w(k,t)/t),
         'convexo':vol_implicita_black(conv.precios(reb),F,K,t,D,True)}
    for m in LABELS:ax[0].plot(k*100,ivs[m]*100,color=COLORS[m],label=LABELS[m])
    ax[0].set(title='Curvas distintas sobre los mismos datos',xlabel='100 × log(K/F)',ylabel='Volatilidad implícita (%)')
    wb,wb1,_=s.derivadas(k,t);wr,wr1,_=red.derivadas(k,t)
    cdfs={'ssvi':cdf_logmoneyness(k,wb,wb1),'red':cdf_logmoneyness(k,wr,wr1),
          'convexo':(np.exp(k[:,None])>=conv.soporte)@conv.masas[0]}
    for m in LABELS:
        if m=='convexo':ax[1].step(np.exp(k)*100,cdfs[m],where='post',color=COLORS[m],label=LABELS[m])
        else:ax[1].plot(np.exp(k)*100,cdfs[m],color=COLORS[m],label=LABELS[m])
    ax[1].set(title='Distribuciones Q: suave frente a discreta',xlabel='Precio terminal / forward × 100',ylabel='Probabilidad acumulada Q',ylim=(0,1))
    ax[0].axvspan(-3,3,color=COLORS['ssvi'],alpha=.08)
    ax[1].axvspan(np.exp(-.03)*100,np.exp(.03)*100,color=COLORS['ssvi'],alpha=.08)
    for aa in ax:aa.grid(alpha=.15);aa.legend(fontsize=8)
    fig.suptitle(f'Primera foto cronológica: {c["fecha"]} {c["hora"]} ET',fontsize=14,fontweight='bold')
    fig.text(.5,-.07,'Zona sombreada: aproximación de la ventana de datos. Fuera de ella se extrapola.\n'
        'La distribución discreta respeta masa/media y calendario, pero sus escalones no son un descubrimiento de mercado.',ha='center',fontsize=10)
    save(fig,a.privado/'curvas_modelos.png')


if __name__=='__main__':main()
