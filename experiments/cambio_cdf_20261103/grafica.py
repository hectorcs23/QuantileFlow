"""Figura a partir de los intervalos públicos comprobados, sin elegir el mejor día."""
import hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def main():
    out=Path(__file__).parent/'resultados'
    v=json.loads((out/'verificacion.json').read_text('utf-8'))
    for n,h in v['fuentes_publicas'].items():
        if hashlib.sha256((out/n).read_bytes()).hexdigest()!=h:raise ValueError('Informe distinto del verificado')
    ctrl=json.loads((out/'control_malla.json').read_text('utf-8'))
    cv=json.loads((out/'verificacion_control.json').read_text('utf-8'))
    if hashlib.sha256((out/'control_malla.json').read_bytes()).hexdigest()!=cv['control_sha256']:raise ValueError('Control distinto del verificado')
    fine={(r['fecha'],r['vencimiento']) for r in ctrl['resultados'] if r['caso']=='principal' and r['igualdad_testificada']}
    rows=sorted(json.loads((out/'por_vencimiento.json').read_text('utf-8')),key=lambda r:(r['fecha'],r['vencimiento']))
    days=sorted({r['fecha'] for r in rows})
    plt.rcParams.update({'font.size':10,'axes.spines.right':False,'axes.spines.top':False})
    fig,(a,b)=plt.subplots(1,2,figsize=(12.8,5.6),gridspec_kw={'width_ratios':[1.2,1]})
    outer='#bccad2';inner='#226783';zero='#ac4a2c'
    def draw(ax,x,c):
        ax.vlines(x,100*c['inferior'],100*c['superior'],lw=5,color=outer)
        ax.vlines(x,100*c['interior_inferior'],100*c['interior_superior'],lw=2,color=inner)
    for j,day in enumerate(days):
        d=[r for r in rows if r['fecha']==day]
        for offset,r in zip(np.linspace(-.25,.25,len(d)),d):
            c=next(c for c in r['casos']['principal'] if c['ratio']==1.)
            draw(a,j+offset,c)
            if (r['fecha'],r['vencimiento']) in fine:
                a.plot(j+offset,0,'D',ms=5,color=inner,zorder=4)
    a.set_xticks(range(len(days)),[d[-2:] for d in days])
    a.set(xlabel='Día de octubre de 2026 · cada barra es un vencimiento',ylabel='Cambio en probabilidad implícita (puntos porcentuales)', title='Nivel central de las 09:45 · todas las sesiones')
    example=rows[0];cs=example['casos']['principal']
    for j,c in enumerate(cs): draw(b,j,c)
    b.set_xticks(range(len(cs)),[f"{(c['ratio']-1)*100:+.0f}%" if c['ratio']!=1. else '0%' for c in cs])
    b.set(xlabel='Nivel de SPX relativo al forward de las 09:45',title='Cinco niveles · '+example['fecha']+'\nVencimiento '+example['vencimiento'])
    bounds=[100*v[k] for r in rows for v in r['casos']['principal'] if v['ratio']==1. or r is example for k in ('inferior','superior')]
    lim=max(5.,np.ceil(max(abs(z) for z in bounds)/5)*5)
    for ax in (a,b):
        ax.set_ylim(-lim*1.08,lim*1.08);ax.grid(axis='y',alpha=.18);ax.axhline(0,color=zero,ls='--',lw=1.3)
        ax.set_axisbelow(True)
    fig.suptitle('¿Los precios exigen un cambio entre las 09:45 y las 10:00?',fontsize=17)
    handles=[Line2D([],[],color=outer,lw=5,label='Rango exterior'),Line2D([],[],color=inner,lw=2,label='Cambios alcanzables'),Line2D([],[],color=zero,ls='--',label='Sin cambio')]
    handles.append(Line2D([],[],marker='D',ms=5,linestyle='none',color=inner,label='Testigo adicional en malla fina'))
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.09),ncol=4,frameon=False)
    fig.text(.5,.045,'Positivo: más probabilidad neutral al riesgo de acabar por debajo o en el mismo nivel de SPX.',ha='center')
    fig.text(.5,.012,'Las bandas expresan lo que permiten los precios y los supuestos de error; no son intervalos estadísticos de confianza.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.18,1,.94));fig.savefig(out/'cambio_0945_1000.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
