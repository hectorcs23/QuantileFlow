"""Verticales causales SPXW: datos individuales solo en --privado; no opera en el mercado."""
import argparse,hashlib,json,sys,tomllib
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from experiments.distribuciones_ruido_20261022.evaluar import dump,sha
from experiments.vertical_puts_20261104.metodo import banda,cambio,seleccionar,signo,resumen,sincronas,compatible
DIR=Path(__file__).resolve().parent;OUT=DIR/'resultados'
OLD=ROOT/'experiments/ruido_concentrado_20261022/resultados'
read=lambda p:json.loads(p.read_text('utf8'))
def cli():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('primera','segunda','adicional','privado'):ap.add_argument('--'+n,type=Path,required=True)
    return ap.parse_args()
def fuentes(a):
    old=read(OLD/'resumen.json')
    if sha(OLD/'resumen.json')!=read(OLD/'verificacion.json')['entradas_publicas_sha256']['resumen.json']:raise ValueError('Fuente modificada')
    return [(a.primera,old['origenes']['conocidas']['privados_sha256']),(a.segunda,old['origenes']['nuevas']['privados_sha256']),(a.adicional,read(OUT/'entrada_adicional.json')['privados_sha256'])]
def archivo_par(origin,day,hr):
    t=day+'_'+hr.replace(':','')
    return origin/(t+'_evaluacion.parquet'),origin/(t+'_modelos.json')
def instante(day,hr):return pd.Timestamp(day+' '+hr,tz='America/New_York').tz_convert('UTC')
def cargar(origin,day,hr):
    ep,mp=archivo_par(origin,day,hr)
    e=pd.read_parquet(ep);t=instante(day,hr)
    if (not e.raiz.eq('SPXW').all() or not e.subyacente.eq('SPX').all() or not e.feed.eq('indicative').all()
            or not e.ejercicio.eq('europeo').all() or not e.liquidacion.eq('PM').all() or not e.multiplicador.eq(100).all()
            or not e.captura.eq(day+'T'+hr.replace(':','')).all() or e.id_contrato.duplicated().any()
            or ((e[['sello_evento_utc','sello_snapshot_utc','disponible_utc','recibido_utc']].isna())|
                (e[['sello_evento_utc','sello_snapshot_utc','disponible_utc','recibido_utc']]>t)).any().any()):
        raise ValueError('Universo o sellos incompatibles: '+day+hr)
    result={}
    for z in read(mp)['modelos_fijos'][0]['rebanadas']:
        g=e[np.isclose(e.dias,z['T']*365,atol=1e-10,rtol=0)&(e.k.abs()<=.10)]
        if g.empty or g.vencimiento.nunique()!=1 or g.duplicated(['strike','tipo']).any():raise ValueError('Vencimiento ambiguo')
        v=str(g.vencimiento.iloc[0])
        if v in result:raise ValueError('Ancla duplicada')
        result[v]=(g.set_index(['strike','tipo'],drop=False),z)
    return result

def analizar(day,v,zone,targets,pair,proto):
    g,z=pair[0];F=z['F'];strikes=g[g.tipo=='P'].strike
    ks=[seleccionar(strikes,F,k,proto['distancia_max_F']) for k in targets]
    record=dict(fecha=day,vencimiento=v,zona=zone,dte=z['T']*365,objetivos=list(targets),strikes=ks)
    if None in ks or ks[0]>=ks[1]:return dict(**record,motivo='sin_dos_strikes_0945')
    if pair[1] is None:return dict(**record,motivo='sin_vencimiento_1000')
    if abs((z['T']-pair[1][1]['T'])*365-15/1440)>1e-8:raise ValueError('Tiempo distinto de 15 minutos')
    legs={};bands={};fresh={};tol=proto['tolerancia'];w=ks[1]-ks[0];times=[instante(day,h) for h in proto['horas']]
    for tipo in ('P','C'):
        bytime=[];available=True
        for table,_ in pair:
            if any((k,tipo) not in table.index for k in ks):available=False;break
            bytime.append([table.loc[k,tipo] for k in ks])
        if not available:
            if tipo=='P':return dict(**record,motivo='pata_put_no_elegible_1000')
            continue
        if any(q0.id_contrato!=q1.id_contrato for q0,q1 in zip(*bytime)):raise ValueError('Cambió identidad OCC')
        bs=[banda(tipo,*[(float(q.bid),float(q.ask)) for q in qs],zz['D'],w) for qs,(_,zz) in zip(bytime,pair)]
        bands[tipo]=bs
        legs[tipo]=[[q.id_contrato for q in qs] for qs in bytime]
        fresh[tipo]=all(sincronas(qs,t,proto['edad_max_s'],proto['desfase_patas_max_s']) for qs,t in zip(bytime,times))
    pa,pb=bands['P'];p=resumen(pa,pb,tol)
    # Q-band * D * ancho recupera la diferencia de primas en unidades de índice.
    prima=cambio([x*pair[0][1]['D']*w for x in pa],[x*pair[1][1]['D']*w for x in pb])
    record.update(motivo='ok',ids=legs,bandas=bands,put=p,signo_prima=signo([x/w for x in prima],tol),
        recientes_put=fresh['P'],recientes_todas=False,coherente=False,coincide=False,corrobora=False,call=None)
    if 'C' in bands:
        ca,cb=bands['C'];c=resumen(ca,cb,tol); record['call']=c
        record['coherente']=compatible(pa,ca,tol) and compatible(pb,cb,tol)
        record['coincide']=p['signo'] in ('sube','baja') and p['signo']==c['signo']
        qs=[[table.loc[k,tipo] for k in ks for tipo in ('P','C')] for table,_ in pair]
        record['recientes_todas']=all(sincronas(q,t,proto['edad_max_s'],proto['desfase_patas_max_s']) for q,t in zip(qs,times))
        record['corrobora']=record['coherente'] and record['coincide'] and record['recientes_todas']
    return record

def agregado(rr):
    ok=[r for r in rr if r['motivo']=='ok'];util=[r for r in ok if r['put']['cambio'] is not None]
    sig=[r for r in util if r['put']['signo'] in ('sube','baja')]
    med=lambda xs:float(np.median(xs)) if xs else None
    return dict(plan=len(rr),pareados=len(ok),interpretables=len(util),faltantes=dict(Counter(r['motivo'] for r in rr if r['motivo']!='ok')),
        signos=dict(Counter(r['put']['signo'] for r in ok)),dias_con_signo=sorted({r['fecha'] for r in sig}),
        con_calls=sum(r['call'] is not None for r in ok),mismo_signo=sum(r['coincide'] for r in ok),
        mismo_signo_y_coherente=sum(r['coincide'] and r['coherente'] for r in ok),
        coherentes_ambos=sum(r['coherente'] for r in ok),recientes_todas=sum(r['recientes_todas'] for r in ok),
        recientes_put=sum(r['recientes_put'] for r in ok),corroborados=sum(r['corrobora'] for r in ok),
        dias_corroborados=sorted({r['fecha'] for r in ok if r['corrobora']}),
        signos_prima=dict(Counter(r['signo_prima'] for r in ok)),
        ancho_mediano_pp=med([100*(r['put']['cambio'][1]-r['put']['cambio'][0]) for r in util]),
        abs_mid_mediano_pp=med([100*abs(r['put']['punto_medio']) for r in util]))

def main():
    a=cli();private=a.privado.resolve();sources=fuentes(a)
    if (private.is_relative_to(ROOT) or ROOT.is_relative_to(private) or
            any(private.is_relative_to(p.resolve()) or p.resolve().is_relative_to(private) for p,_ in sources)):raise ValueError('Salida privada externa requerida')
    private.mkdir(parents=True,exist_ok=True);proto=tomllib.loads((DIR/'protocolo.toml').read_text('utf8'))
    for p,files in sources:
        for name,h in files.items():
            if sha(p/name)!=h:raise ValueError('Entrada alterada: '+name)
    zones={'central':proto['principal'],**{f'z{i+1}':z for i,z in enumerate(proto['secundarias'])}}
    rows=[];files={};diarios=[]
    for co,days in [('previas',proto['previas']),('adicionales',proto['adicionales'])]:
        for day in days:
            ep,_=archivo_par(Path('.'),day,proto['horas'][0]);src,=[p for p,fs in sources if ep.name in fs]
            early,late=[cargar(src,day,hr) for hr in proto['horas']]
            daily=[]
            for v,s0 in sorted(early.items()):
                if not proto['dte_0945'][0]<=s0[1]['T']*365<=proto['dte_0945'][1]:continue
                for name,zone in zones.items():daily.append(dict(cohorte=co,**analizar(day,v,name,zone,(s0,late.get(v)),proto)))
            if not daily:raise ValueError('Sin vencimientos en el rango: '+day)
            f=private/(day+'_verticales.json');dump(f,daily);files[f.name]=sha(f);rows.extend(daily)
            diarios.append(dict(cohorte=co,fecha=day,**agregado([r for r in daily if r['zona']=='central'])))
    groups={co:{z:agregado([r for r in rows if r['zona']==z and (co=='total' or r['cohorte']==co)]) for z in zones} for co in ('previas','adicionales','total')}
    dump(OUT/'resumen.json',dict(grupos=groups,diarios_central=diarios,protocolo=proto,testigos_sha256=files,
        hash_entrada_adicional=sha(OUT/'entrada_adicional.json'),sha_origen=sha(OLD/'resumen.json')))
    print(json.dumps({co:z['central'] for co,z in groups.items()},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
