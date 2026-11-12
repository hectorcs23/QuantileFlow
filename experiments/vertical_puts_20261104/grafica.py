import json,hashlib
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def main():
    o=Path(__file__).parent/'resultados';p=o/'resumen.json';v=json.loads((o/'verificacion.json').read_text('utf8'))
    assert hashlib.sha256(p.read_bytes()).hexdigest()==v['resumen_sha256']
    summary=json.loads(p.read_text('utf8'));g=summary['grupos']['total']['central'];d=v['diagnostico_temporal_exploratorio']
    plt.rcParams.update({'font.size':10,'axes.spines.right':False,'axes.spines.top':False})
    fig,(a,b)=plt.subplots(1,2,figsize=(12.8,5.4),gridspec_kw={'width_ratios':[1.15,1]})
    labels=['Dos puts en ambos cortes','Cambio fuera del bid/ask','Calls con el mismo signo','Paridad compatible en ambos cortes','También recientes y sincronizados']
    vals=[g['interpretables'],sum(g['signos'].get(s,0) for s in ('sube','baja')),g['mismo_signo'],g['mismo_signo_y_coherente'],g['corroborados']]
    bars=a.barh(labels,vals,color=['#a9b9c4','#2a758e','#2a758e','#2a758e','#c26328'])
    a.bar_label(bars,padding=4);a.invert_yaxis();a.set_xlim(0,max(vals)*1.14);a.set_xlabel('Comparaciones fecha–vencimiento');a.set_title('Zona central: cuántos casos pasan cada control')
    for j,(co,label,color) in enumerate([('previas','2–16 oct.','#2a758e'),('adicionales','19–22 oct.','#c26328')]):
        values=[d[co]['mediana_edad_max_s'],d[co]['mediana_desfase_max_s']]
        bars=b.bar(np.arange(2)+(j-.5)*.35,values,.33,color=color,label=label)
        b.bar_label(bars,fmt='%.1f',padding=3)
    for x,h in enumerate([5,2]):b.plot([x-.43,x+.43],[h,h],ls='--',c='#292e33',label='Límite fijado' if x==0 else None)
    b.set_xticks([0,1],['Antigüedad al corte','Desfase entre patas']);b.set_ylabel('Segundos · mediana del peor valor entre los dos cortes')
    b.set_ylim(0,max(14,1.25*d['previas']['mediana_edad_max_s']));b.legend(frameon=False,loc='upper right');b.set_title('Antigüedad y sincronía de las cuatro cotizaciones')
    a.grid(axis='x',alpha=.15);b.grid(axis='y',alpha=.15);a.set_axisbelow(True);b.set_axisbelow(True)
    fig.suptitle('El vertical de puts distingue algunos movimientos; ninguno pasa el control temporal',fontsize=15)
    fig.text(.5,.04,'SPXW · zona de −3% a +3% del forward inicial · 09:45–10:00 ET · datos indicativos, sin prueba de retorno posterior.',ha='center',fontsize=9.5)
    fig.tight_layout(rect=(0,.08,1,.92));fig.savefig(o/'vertical_central.png',dpi=155);plt.close(fig)
if __name__=='__main__':main()
