"""Sensibilidad agregada pública y ejemplo de CDF solo local, fuera de Git."""
import argparse,json,sys
from pathlib import Path
RAIZ=Path(__file__).resolve().parents[2];sys.path.insert(0,str(RAIZ))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from quantileflow.superficies import SuperficieSSVI
from experiments.estabilidad_superficie_20261014.metodo import cdf_comun


def restore(p):return SuperficieSSVI(np.array(p['tiempos']),np.array(p['thetas']),p['rho'],p['eta'],p['gamma'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('privado','ml'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();folder=Path(__file__).parent/'resultados';r=json.loads((folder/'resumen.json').read_text(encoding='utf-8'))
    if a.privado.resolve().is_relative_to(RAIZ):raise ValueError('ejemplos privados fuera de Git')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold'})
    colors=['#167d78','#9c783a','#467fa8'];names=['Precio ±5%\ndel spread','Peso hacia mid\n0.01 / 0.04','Cambiar modelo\nSSVI / convexo']
    groups=['precio','regularizacion','contraste_modelos'];fig,ax=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    vals=[r['total'][g]['cdf_observada_max_pp'] for g in groups]
    bars=ax[0].bar(np.arange(3),vals,color=colors,width=.65)
    ax[0].bar_label(bars,labels=[f'{v:.4f}' if v<1 else f'{v:.2f}' for v in vals],padding=5)
    ax[0].set(yscale='log',ylim=(.001,100),xticks=[0,1,2],xticklabels=names,title='Máximo cambio de CDF dentro del rango observado',ylabel='Puntos porcentuales; escala logarítmica')
    for j,g in enumerate(groups):
        key='cuantiles_diferencia_max_bp' if g=='contraste_modelos' else 'cuantiles_mov_max_bp'
        ax[1].bar(np.arange(5)+(j-1)*.24,r['total'][g][key],width=.23,color=colors[j],label=['Perturbar precios','Regularización','Modelo diferente'][j])
    ax[1].set(yscale='log',ylim=(.01,500),xticks=np.arange(5),xticklabels=['5% †','25%','50%','75%','95% †'],title='Máximo movimiento del cuantil de modelo',ylabel='Puntos básicos del forward nominal (1 bp = 0.01%)')
    ax[1].legend(fontsize=8,loc='upper right')
    for aa in ax:aa.grid(axis='y',alpha=.15);aa.set_axisbelow(True)
    fig.suptitle('Estable dentro de SSVI no significa una distribución identificada',fontsize=14,fontweight='bold')
    fig.text(.5,-.12,'Máximos entre 48 curvas de seis sesiones conocidas: no intervalos de confianza.\n'
        '† Cuantiles 5% y 95% fuera del rango de strikes en 48/48 curvas: solo extrapolación de modelo.\n'
        'La comparación con el convexo incluye sus átomos; no identifica el modelo verdadero.',ha='center',fontsize=10)
    fig.savefig(folder/'estabilidad.png',dpi=160,bbox_inches='tight');plt.close(fig)
    c=r['cortes'][0];tag=c['fecha']+'_'+c['hora'].replace(':','')
    data=json.loads((a.privado/(tag+'_sensibilidad.json')).read_text(encoding='utf-8'))
    mp=json.loads((a.ml/(tag+'_modelos.json')).read_text(encoding='utf-8'))
    base=data['casos'][0];s0=restore(base['parametros']);t=s0.tiempos[0];F0=base['rebanadas'][0]['F_nominal']
    x=np.linspace(.97,1.03,601);xwide=np.linspace(.92,1.08,1601)
    fig,ax=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    for case in data['casos']:
        if case['familia']!='precio':continue
        s=restore(case['parametros']);factor=case['rebanadas'][0]['F']/F0
        delta=100*(cdf_comun(s,t,x,factor)-cdf_comun(s0,t,x))
        ax[0].plot(x*100,delta,lw=1,label=case['caso'].replace('_',' '))
    ax[0].set(title='Cotizaciones pequeñas: desplazamientos pequeños',xlabel='Precio terminal / F nominal × 100',ylabel='Cambio de CDF Q, puntos porcentuales')
    ax[0].legend(fontsize=7,ncol=2);ax[0].axhline(0,color='#555555',lw=.6)
    ax[1].plot(xwide*100,cdf_comun(s0,t,xwide),color=colors[0],lw=2,label='SSVI nominal')
    nodes=np.array(mp['convexo_soporte']);mass=np.array(mp['convexo_masas'])[0]
    points=np.unique(np.r_[xwide,nodes[(nodes>=xwide.min())&(nodes<=xwide.max())]])
    ax[1].step(points*100,(points[:,None]>=nodes)@mass,where='post',color=colors[2],lw=1.5,label='Convexo nominal')
    ax[1].axvspan(97,103,color=colors[0],alpha=.08,label='Ventana aproximada de strikes')
    ax[1].set(title='Otro modelo: diferencias de distribución mayores',xlabel='Precio terminal / F nominal × 100',ylabel='Probabilidad acumulada Q',ylim=(0,1))
    ax[1].legend(fontsize=8)
    for aa in ax:aa.grid(alpha=.15)
    fig.suptitle(f'Primera foto: {c["fecha"]} {c["hora"]} ET; primer vencimiento observado',fontsize=14,fontweight='bold')
    fig.text(.5,-.08,'Las probabilidades son Q del modelo, no probabilidades físicas de ganar.\n'
        'Los saltos del convexo dependen de su soporte discreto. Fuera de la ventana se extrapola.',ha='center',fontsize=10)
    fig.savefig(a.privado/'ejemplo_cdf.png',dpi=160,bbox_inches='tight');plt.close(fig)


if __name__=='__main__':main()
