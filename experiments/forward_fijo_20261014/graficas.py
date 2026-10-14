"""Resultados agregados del contraste de ventanas con forward fijo."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    out=Path(__file__).parent/'resultados';r=json.loads((out/'resumen.json').read_text(encoding='utf-8'))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,'axes.titleweight':'bold'})
    fig,ax=plt.subplots(1,3,figsize=(15.5,5.5));fig.subplots_adjust(top=.80,bottom=.30,wspace=.31)
    widths=[.03,.06,.10];x=np.arange(3);colors={'reestimado':'#467fa8','fijo':'#167d78'}
    for j,name in enumerate(('reestimado','fijo')):
        rows=[next(v for v in r['total'] if v['ancho']==w and v['forward']==name) for w in widths]
        for a,region in zip(ax[:2],('centro','alas_6_10')):
            yy=[100*v['holdout'][region]['dentro']/v['holdout'][region]['filas'] for v in rows]
            bars=a.bar(x+(j-.5)*.34,yy,width=.33,color=colors[name],label='F reestimado' if name=='reestimado' else 'F central fijo')
            if region=='alas_6_10':
                for bar in bars[:2]:bar.set_hatch('//')
            a.bar_label(bars,labels=[f'{v:.1f}' for v in yy],padding=3,fontsize=9)
    ax[0].set(title='Centro: 1,642 precios reservados',ylabel='Dentro del bid/ask (%)',ylim=(0,65))
    ax[1].set(title='Alas 6–10%: 605 reservas',ylabel='Dentro del bid/ask (%)',ylim=(0,65))
    for a in ax[:2]:a.set(xticks=x,xticklabels=['±3%','±6%','±10%'],xlabel='Ventana de ajuste (log-moneyness)')
    ax[0].legend(loc='upper right',fontsize=9)
    rings=['centro','alas_3_6','alas_6_10'];labels=['Centro','Alas\n3–6%','Alas\n6–10%']
    selected=[next(d for d in r['paridad'] if (d['ancho'],d['forward'],d['grupo'],d['region'])==(.10,'fijo','holdout',ring)) for ring in rings]
    yy=[100*d['incompatibles']/d['pares'] for d in selected]
    zz=[100*d['minimo_incompatibles_F_libre']/d['pares'] for d in selected]
    bars=ax[2].bar(x-.17,yy,width=.33,color='#167d78',label='Con F central fijo')
    ax[2].bar_label(bars,labels=[f'{v:.1f}' for v in yy],padding=3,fontsize=9)
    bars=ax[2].bar(x+.17,zz,width=.33,color='#cc6946',label='Mínimo con cualquier F¹')
    ax[2].bar_label(bars,labels=[f'{v:.1f}' for v in zz],padding=3,fontsize=9)
    ax[2].set(title='Paridad C/P: reservas completas',xticks=x,xticklabels=labels,
        ylabel='Pares incompatibles (%)',ylim=(0,100))
    ax[2].legend(loc='upper right',fontsize=8)
    for a in ax:a.grid(axis='y',alpha=.15);a.set_axisbelow(True)
    fig.suptitle('¿El conflicto desaparece al mantener fijo el forward?',fontsize=17,fontweight='bold')
    fig.text(.5,.11,'Mismas filas y reservas; seis sesiones conocidas. No son probabilidades de éxito ni cotizaciones ejecutables.\n'
        'Rayado: región fuera de la ventana de ajuste. ¹ F libre optimizado por vencimiento/región, solo como diagnóstico posterior.\n'
        'La comparación cambia SSVI al recalibrar. La incompatibilidad de paridad no puede corregirse solo cambiando el smile.',ha='center',fontsize=10)
    fig.savefig(out/'forward_fijo.png',dpi=165);plt.close(fig)


if __name__=='__main__':main()
