"""Graficas agregadas; exige resultados con verificacion independiente vigente."""
import hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    folder=Path(__file__).parent;out=folder/'resultados'
    read=lambda name:json.loads((out/name).read_text(encoding='utf-8'))
    checks=read('verificacion.json')
    for n,h in checks['entradas_publicas_sha256'].items():
        if hashlib.sha256((out/n).read_bytes()).hexdigest()!=h:raise ValueError('Resultados alterados')
    s=read('resumen.json'); reps=read('reparaciones.json')
    groups={ (r['cohorte'],r['caso']):r for r in s['agregado'] }
    colors=['#1b6989','#bd5b23']; labels=['Conocidas: 2–9 oct. (6 sesiones)','Nuevas al experimento: 12–16 oct. (5 sesiones)']
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    cases=['uniforme','l1_margen_0.1','referencias'];names=['Margen uniforme','Error total limitado\nL1 + 0.1 spread','L1 + 0.1 y\nreferencias variables']
    fig,axs=plt.subplots(1,2,figsize=(13.5,5.6))
    for j,co in enumerate(('conocidas','nuevas')):
        values=[100*next(v for v in groups[co,k]['cdf'] if v['ratio']==1.)['mediana_ancho'] for k in cases]
        hits=[100*groups[co,k]['holdout_solapan']/groups[co,k]['holdout_n'] for k in cases]
        for ax,vals in zip(axs,(values,hits)):
            bars=ax.bar(np.arange(3)+(j-.5)*.34,vals,width=.32,color=colors[j],label=labels[j])
            ax.bar_label(bars,labels=[f'{v:.1f}' for v in vals],padding=4,fontsize=11)
    axs[0].set(title='¿Cuánta incertidumbre queda en la CDF?',ylabel='Ancho mediano en K = F · puntos porcentuales')
    axs[1].set(title='Contraste con calls reservados',ylabel='Intervalos que solapan el bid/ask observado · %',ylim=(0,110))
    for ax in axs:
        ax.set_xticks(range(3),names);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axs[0].set_ylim(0,axs[0].get_ylim()[1]*1.12)
    fig.suptitle('Limitar el error total: qué cambia y qué persiste',fontsize=18,y=.99)
    fig.legend(*axs[0].get_legend_handles_labels(),loc='lower center',ncol=2,bbox_to_anchor=(.5,.075),frameon=False)
    fig.text(.5,.025,'CDF neutral al riesgo. Menor ancho no equivale a mayor exactitud; solapamiento no mide aciertos ni rentabilidad.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.16,1,.93));fig.savefig(out/'comparacion_l1.png',dpi=150);plt.close(fig)

    fig,axs=plt.subplots(1,2,figsize=(12,5.8))
    for j,co in enumerate(('conocidas','nuevas')):
        rr=[r for r in reps if r['cohorte']==co]
        series=[[100*r['participacion_top10'] for r in rr],[100*r['paridad']['fraccion_filas_min'] for r in rr]]
        for ax,vals in zip(axs,series):
            jitter=np.linspace(-.1,.1,len(vals));ax.scatter(j+jitter,vals,s=18,color=colors[j],alpha=.55)
            med=float(np.median(vals));ax.plot([j-.22,j+.22],[med,med],color=colors[j],linewidth=3)
            ax.text(j+.25,med,f'{med:.1f}%',va='center',fontsize=11)
    axs[0].set(title='Concentración de la magnitud del ajuste',ylabel='% del error total aportado por el 10% mayor')
    axs[1].set(title='Extensión mínima de las contradicciones',ylabel='% de filas que deben salir de su bid/ask')
    for ax in axs:
        ax.set_xticks([0,1],['2–9 octubre','12–16 octubre']);ax.set_xlim(-.4,1.65);ax.set_ylim(0,103)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('Unos errores grandes pueden coexistir con muchos precios incompatibles',fontsize=16)
    fig.text(.5,.025,'Izquierda: un óptimo L1, no una lista única de precios malos. Derecha: cota necesaria por paridad, con F/D fijos y cap.',ha='center',fontsize=9.5)
    fig.tight_layout(rect=(0,.07,1,.92));fig.savefig(out/'concentracion_y_extension.png',dpi=150);plt.close(fig)
    report=dict(graficas_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.png')},
        codigo_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        verificacion_sha256=hashlib.sha256((out/'verificacion.json').read_bytes()).hexdigest())
    (out/'graficas.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':main()
