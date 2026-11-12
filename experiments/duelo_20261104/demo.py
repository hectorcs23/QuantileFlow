"""Ejemplo de dos compras sintéticas; figura y evidencia de los cruces locales."""
import json,sys
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import brentq
from quantileflow.duelo import comparar_dos
from quantileflow.simulador import ConfiguracionSimulador,cadena_sintetica
from quantileflow.escenarios import Escenario,comparar_contratos

def main():
    cfg=ConfiguracionSimulador()
    pick=[dict(contrato='C103-14d',cantidad=3),dict(contrato='C103-60d',cantidad=1)]
    resultado=comparar_dos(cfg,pick);cs={c.identificador:c for c in cadena_sintetica(cfg)[0]}
    def value(j,m,d):
        pos=pick[j];c=cs[pos['contrato']]
        if d>c.dte:return None
        f=comparar_contratos([c],cfg.spot,[Escenario('salida',d,m/100,0)],cfg.presupuesto,
            comision=cfg.comision,semispread_salida=cfg.semispread,tasa=cfg.tasa_pct/100,
            q=cfg.dividendo_pct/100,limites_cantidad={c.identificador:pos['cantidad']})['contratos'][0]
        assert f['contratos']==pos['cantidad']
        return f['escenarios']['salida']['pnl']
    diferencia=lambda m,d:value(0,m,d)-value(1,m,d)
    cruce_m=brentq(lambda m:diferencia(m,7),1.5,3)
    cruce_d=brentq(lambda d:diferencia(3,d),7,14)
    assert abs(diferencia(cruce_m,7))<1e-8 and abs(diferencia(3,cruce_d))<1e-8
    moves=np.linspace(-3,6,121);days=np.arange(0,22)
    curves=[dict(pnl_por_movimiento=[value(j,m,7) for m in moves],
                 pnl_por_dia=[value(j,3,d) for d in days]) for j in (0,1)]
    out=Path(__file__).parent/'resultados';out.mkdir(exist_ok=True)
    data=dict(configuracion=asdict(cfg),**resultado,movimientos_pct=moves.tolist(),dias_comparados=days.tolist(),
        curvas=curves,cruce_movimiento_pct_entre_1_5_y_3=cruce_m,cruce_dias_entre_7_y_14=cruce_d)
    (out/'comparacion.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf8',newline='\n')
    fig,(a,b)=plt.subplots(1,2,figsize=(11.5,5.1),layout='constrained')
    for j,(color,label) in enumerate([('#166487','A · 3 calls / 14 DTE'),('#b35a26','B · 1 call / 60 DTE')]):
        a.plot(moves,curves[j]['pnl_por_movimiento'],color=color,lw=2.4,label=label)
        b.plot(days,[np.nan if x is None else x for x in curves[j]['pnl_por_dia']],color=color,lw=2.4)
    for ax in (a,b):
        ax.axhline(0,color='0.35',ls='--',lw=1);ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',alpha=.18);ax.set_ylabel('Ganancia / pérdida neta (USD)')
    a.set(title='Si vendes el día 7',xlabel='Movimiento del subyacente (%)');a.legend(frameon=False,loc='upper left')
    b.set(title='Si vendes cuando el subyacente está en $103',xlabel='Días transcurridos desde la compra')
    for ax,x,y,lab in [(a,cruce_m,value(0,cruce_m,7),f'Cruce: +{cruce_m:.2f}%'),
                       (b,cruce_d,value(0,3,cruce_d),f'Cruce: día {cruce_d:.1f}')]:
        ax.scatter([x],[y],c='#323c46',s=22,zorder=5)
        offset=(-42,26) if ax is a else (8,18)
        ax.annotate(lab,(x,y),xytext=offset,textcoords='offset points',fontsize=9,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.9,pad=1.5))
    b.scatter([14],[value(0,3,14)],color='#166487',s=25);b.annotate('A vence sin valor',(14,value(0,3,14)),xytext=(7,9),textcoords='offset points',fontsize=9)
    fig.suptitle('Presupuesto: 300 USD · strike: 103 USD · cantidades y vencimientos distintos\nCalls europeos sintéticos · precio inicial 100 USD · IV 25% constante en estas curvas',fontsize=13)
    fig.savefig(out/'comparacion.png',dpi=155);plt.close(fig)
    print(f'Cruce por movimiento: {cruce_m:.5f}% · cruce por plazo: {cruce_d:.5f} días')
if __name__=='__main__':main()
