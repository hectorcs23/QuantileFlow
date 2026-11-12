"""Auditoría independiente: evalúa las 16 esquinas bid/ask partiendo de los Parquet."""
import argparse,hashlib,itertools,json,sys,tomllib
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
DIR=Path(__file__).resolve().parent;OLD=DIR.parent/'ruido_concentrado_20261022/resultados';OUT=DIR/'resultados'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def etiqueta(x,t):return 'sube' if min(x)>t else 'baja' if max(x)<-t else 'incluye_cero'

def main():
    if not __debug__:raise RuntimeError('No ejecutar con -O')
    ap=argparse.ArgumentParser()
    for n in ('primera','segunda','adicional','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();s=read(OUT/'resumen.json');proto=tomllib.loads((DIR/'protocolo.toml').read_text('utf8'));t=proto['tolerancia']
    assert s['protocolo']==proto and sha(OUT/'entrada_adicional.json')==s['hash_entrada_adicional'] and sha(OLD/'resumen.json')==s['sha_origen']
    os=read(OLD/'resumen.json')['origenes']
    sources=[(a.primera,os['conocidas']['privados_sha256']),(a.segunda,os['nuevas']['privados_sha256']),(a.adicional,read(OUT/'entrada_adicional.json')['privados_sha256'])]
    zones=dict(central=proto['principal'],**{f'z{i+1}':z for i,z in enumerate(proto['secundarias'])})
    checked=[];times=[];corners=0;maxerr=0.
    for day in proto['previas']+proto['adicionales']:
        co='previas' if day in proto['previas'] else 'adicionales'
        f=a.privado/(day+'_verticales.json');assert sha(f)==s['testigos_sha256'][f.name]
        records=read(f);assert all(r['fecha']==day and r['cohorte']==co for r in records)
        orig,fs=next((o,h) for o,h in sources if (day+'_0945_evaluacion.parquet') in h)
        frames=[];anchors=[];clock=[]
        for hr in proto['horas']:
            tag=day+'_'+hr.replace(':','');ep=orig/(tag+'_evaluacion.parquet');mp=orig/(tag+'_modelos.json')
            assert sha(ep)==fs[ep.name] and sha(mp)==fs[mp.name]
            frame=pd.read_parquet(ep);frame=frame[frame.k.abs()<=.10];frames.append(frame)
            anchors.append(read(mp)['modelos_fijos'][0]['rebanadas']);clock.append(pd.Timestamp(day+'T'+hr,tz='America/New_York').tz_convert('UTC'))
        a0=frames[0];inwindow=a0.dias.between(*proto['dte_0945']) & a0.dias.apply(lambda d:any(abs(d-z['T']*365)<1e-10 for z in anchors[0]))
        expect=set(itertools.product(a0.loc[inwindow,'vencimiento'].astype(str).unique(),zones))
        assert {(r['vencimiento'],r['zona']) for r in records}==expect and len(records)==len(expect)
        for r in records:
            v=r['vencimiento'];zname=r['zona']
            tables=[df[df.vencimiento.astype(str)==v] for df in frames]
            zz=[next((z for z in zs if not tbl.empty and abs(tbl.dias.iloc[0]-365*z['T'])<1e-10),None) for zs,tbl in zip(anchors,tables)]
            F=zz[0]['F'];initial=tables[0][tables[0].tipo=='P'].strike.tolist()
            ks=[]
            for u in zones[zname]:
                possibles=sorted((abs(k-u*F),k) for k in initial if abs(k-u*F)<=proto['distancia_max_F']*F+1e-12)
                ks.append(possibles[0][1] if possibles else None)
            assert ks==r['strikes'];reason='ok'
            if None in ks or ks[0]>=ks[1]:reason='sin_dos_strikes_0945'
            elif zz[1] is None:reason='sin_vencimiento_1000'
            elif not set(ks)<=set(tables[1].loc[tables[1].tipo=='P','strike']):reason='pata_put_no_elegible_1000'
            assert reason==r['motivo'];checked.append(r)
            if reason!='ok':continue
            w=ks[1]-ks[0];ts=[[],[]]; physical={};signs={};ppage=None
            for tipo,name in [('P','put'),('C','call')]:
                legs=[tbl[(tbl.tipo==tipo)&tbl.strike.isin(ks)].sort_values('strike') for tbl in tables]
                if min(map(len,legs))<2:
                    assert name=='call' and r['call'] is None;continue
                assert legs[0].id_contrato.tolist()==legs[1].id_contrato.tolist()
                assert r['ids'][tipo]==[g.id_contrato.tolist() for g in legs]
                corners+=16;lohi=[];allvals=[];precios=[]
                for j,g in enumerate(legs):
                    ts[j].extend(list(zip(g.sello_evento_utc,g.recibido_utc)))
                    price=[y-x if tipo=='P' else x-y for x,y in itertools.product(*g[['bid','ask']].to_numpy())]
                    precios.append(price);vals=np.array(price)/(zz[j]['D']*w)
                    if tipo=='C':vals=1-vals
                    allvals.append(vals);lohi.append([min(vals),max(vals)])
                raw=[b-a for a,b in itertools.product(*allvals)]
                maxerr=max(maxerr,float(np.max(np.abs(np.array([min(raw),max(raw)])-r[name]['cambio_raw']))))
                maxerr=max(maxerr,float(np.max(abs(np.array(lohi)-r['bandas'][tipo]))))
                assert abs(np.mean(raw)-r[name]['punto_medio'])<1e-10
                physical[name]=[[max(0.,l),min(1.,h)] for l,h in lohi]
                if any(l>h for l,h in physical[name]):
                    signs[name]='incompatible';assert r[name]['cambio'] is None
                else:
                    deltas=[v-u for u,v in itertools.product(*physical[name])]
                    signs[name]=etiqueta(deltas,t);assert np.allclose([min(deltas),max(deltas)],r[name]['cambio'],atol=1e-11,rtol=0)
                assert signs[name]==r[name]['signo']
                if tipo=='P':
                    assert etiqueta([(b-a)/w for a,b in itertools.product(*precios)],t)==r['signo_prima']
                    ppage=all(all(pd.Timedelta(0)<=clock[j]-x<=pd.Timedelta(seconds=5) for x,_ in tt)
                        and max(x for x,_ in tt)-min(x for x,_ in tt)<=pd.Timedelta(seconds=2) for j,tt in enumerate(ts))
                    assert ppage==r['recientes_put']
            full='call' in signs;same=full and signs['put'] in ('sube','baja') and signs['call']==signs['put']
            consistent=full and all(max(a[0],b[0])<=min(a[1],b[1])+t for a,b in zip(physical['put'],physical['call']))
            assert same==r['coincide'] and consistent==r['coherente']
            if not full:assert not r['corrobora'] and not r['recientes_todas'];continue
            ages=[];spans=[];arrival=[];leads=[];future=False
            for j,tt in enumerate(ts):
                stamps=[v[0] for v in tt];last=max(v[1] for v in tt)
                ages.append((clock[j]-min(stamps)).total_seconds())
                spans.append((max(stamps)-min(stamps)).total_seconds())
                leads.append((clock[j]-last).total_seconds());arrival.append((last-min(stamps)).total_seconds())
                future |= any(x>rec for x,rec in tt)
            fresh=max(ages)<=5 and max(spans)<=2 and all(x<=clock[j] for j,k in enumerate(ts) for x,_ in k)
            assert fresh==r['recientes_todas'] and (same and consistent and fresh)==r['corrobora']
            if zname=='central':
                times.append(dict(co=co,day=day,sig=same and consistent,edad=max(ages),desfase=max(spans),anticipacion=leads,
                    edad_real=max(arrival),reloj_real_ok=not future and max(arrival)<=5 and max(spans)<=2))
    assert maxerr<1e-10
    def verify_group(rs,group):
        ok=[r for r in rs if r['motivo']=='ok'];valid=[r for r in ok if r['put']['cambio'] is not None]
        assert [len(rs),len(ok),len(valid)]==[group[k] for k in ('plan','pareados','interpretables')]
        assert dict(Counter(r['put']['signo'] for r in ok))==group['signos']
        assert sum(r['corrobora'] for r in ok)==group['corroborados'] and sum(r['coincide'] and r['coherente'] for r in ok)==group['mismo_signo_y_coherente']
        assert sorted({r['fecha'] for r in ok if r['corrobora']})==group['dias_corroborados']
        if valid:assert abs(100*np.median([np.ptp(r['put']['cambio']) for r in valid])-group['ancho_mediano_pp'])<1e-9
    for co,gr in s['grupos'].items():
        for zone,g in gr.items():verify_group([r for r in checked if r['zona']==zone and co in ('total',r['cohorte'])],g)
    for d in s['diarios_central']:verify_group([r for r in checked if r['fecha']==d['fecha'] and r['zona']=='central'],d)
    diag={}
    for co in ('previas','adicionales','total'):
        rs=[r for r in times if co in ('total',r['co'])]; sig=[r for r in rs if r['sig']]
        diag[co]=dict(pares=len(rs),pasan_solo_edad=sum(r['edad']<=5 for r in rs),pasan_solo_desfase=sum(r['desfase']<=2 for r in rs),
            pasan_al_recibir=sum(r['reloj_real_ok'] for r in rs),coincidencias_coherentes=len(sig),
            coinciden_y_pasan_al_recibir=sum(r['reloj_real_ok'] for r in sig),
            dias_coinciden_al_recibir=sorted({r['day'] for r in sig if r['reloj_real_ok']}),
            mediana_edad_max_s=float(np.median([r['edad'] for r in rs])),mediana_desfase_max_s=float(np.median([r['desfase'] for r in rs])),
            mediana_anticipacion_recepcion_s=float(np.median([x for r in rs for x in r['anticipacion']])))
    result=dict(casos=len(checked),esquinas=corners,error_max=maxerr,diagnostico_temporal_exploratorio=diag,
        resumen_sha256=sha(OUT/'resumen.json'),codigo_sha256_lf={p.name:hashlib.sha256(p.read_text('utf8').encode()).hexdigest() for p in [DIR/n for n in ('protocolo.toml','preparar.py','metodo.py','evaluar.py','verificar.py')]})
    (OUT/'verificacion.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
