"""Perturbaciones prefijadas de training y contraste de distribuciones nominales."""
import argparse,hashlib,json,math,platform,sys,tomllib
from pathlib import Path
RAIZ=Path(__file__).resolve().parents[2];sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
import scipy
from quantileflow.superficies import Rebanada,ajustar_superficie
from quantileflow.opciones import precio_black
from experiments.forward_superficies_20261014.evaluar import restaurar
from experiments.forward_superficies_20261014.metodo import estimar_forward
from experiments.skew_bandas_20261010.evaluar import metricas
from experiments.estabilidad_superficie_20261014.metodo import perturbar,cdf_comun,cuantiles_modelo_diagnostico,cuantiles_discretos,distancia_cdf_discreta


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')


def verificar_origen(summary,private):
    for name,h in summary.items():
        p=(private/name).resolve()
        if not p.is_relative_to(private.resolve()) or sha(p)!=h:raise ValueError('origen alterado')


def construir_rs(e,p,Fs=None):
    rs=[]
    for dias,g in e[e.entrenamiento].groupby('dias',sort=True):
        t=float(dias)/365;f=p['forwards'][str(t)]
        F=f['estimado'] if Fs is None else Fs[t]
        rs.append(Rebanada(t,F,f['D'],g.strike.to_numpy(float),g.bid.to_numpy(float),g.ask.to_numpy(float),g.tipo.eq('C').to_numpy(),(g.bid+.5*(g.ask-g.bid)).to_numpy()))
    return rs


def ajustar(rs,peso):
    models=[ajustar_superficie(rs,rho0=rho,eta0=1.,gamma0=.4,peso_mid=peso) for rho in (-.6,0,.6)]
    good=[s for s in models if s.info['exito'] and math.isfinite(s.info['costo']) and all(s.condiciones().values())]
    if not good:raise ValueError('sin SSVI convergente admisible')
    return min(good,key=lambda s:s.info['costo'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('forward','ml','privado'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--publico',type=Path,default=Path(__file__).parent/'resultados');a=ap.parse_args()
    private,pub=a.privado.resolve(),a.publico.resolve()
    if private.is_relative_to(RAIZ) or private.is_relative_to(pub) or pub.is_relative_to(private):raise ValueError('salidas privadas fuera de Git')
    pf=RAIZ/'experiments/forward_superficies_20261014/resultados/resumen.json';pm=RAIZ/'experiments/ml_superficie_20261014/resultados/resumen.json'
    fwd=json.loads(pf.read_text(encoding='utf-8'));ml=json.loads(pm.read_text(encoding='utf-8'))
    verificar_origen(fwd['privado_sha256'],a.forward);verificar_origen(ml['privados_sha256'],a.ml)
    for name,h in (fwd['fuentes_sha256_lf']|ml['codigo_sha256_lf']).items():
        if hashlib.sha256((RAIZ/name).read_text(encoding='utf-8').encode()).hexdigest()!=h:raise ValueError('código de origen cambió')
    proto_path=Path(__file__).with_name('protocolo.toml');proto=tomllib.loads(proto_path.read_text(encoding='utf-8'))
    private.mkdir(parents=True,exist_ok=True);pub.mkdir(parents=True,exist_ok=True)
    alpha=proto['cuantiles'];cuts=[];inside=np.zeros(len(alpha),int)
    for c in fwd['cortes']:
        tag=c['fecha']+'_'+c['hora'].replace(':','');e=pd.read_parquet(a.forward/(tag+'_evaluacion.parquet'))
        p=json.loads((a.forward/(tag+'_parametros.json')).read_text(encoding='utf-8'))
        mp=json.loads((a.ml/(tag+'_modelos.json')).read_text(encoding='utf-8'))
        if mp['origen_parametros']!=p:raise ValueError('bases ML/forward distintas')
        s0=restaurar(p['ajustes']['estimado']).superficie
        baseline={};contraste=[]
        for j,(dias,g) in enumerate(e[e.entrenamiento].groupby('dias',sort=True)):
            t=float(dias)/365;F0=p['forwards'][str(t)]['estimado'];lo,hi=float(g.strike.min()/F0),float(g.strike.max()/F0)
            q0=cuantiles_modelo_diagnostico(s0,t,alpha);within=(q0>=lo)&(q0<=hi);inside+=within
            baseline[t]=dict(q=q0,lo=lo,hi=hi,F=F0)
            x=np.array(mp['convexo_soporte']);m=np.array(mp['convexo_masas'])[j];qc=cuantiles_discretos(x,m,alpha)
            ks=distancia_cdf_discreta(lambda z:cdf_comun(s0,t,z),x,m,(lo,hi))
            contraste.append(dict(T=t,cuantiles_modelo_ssvi=q0.tolist(),cuantiles_modelo_convexo=qc.tolist(),
                cuantiles_dentro_rango_training=within.tolist(),cdf_observada_max_pp=100*ks,
                diferencia_cuantiles_bp=(10000*(qc-q0)).tolist()))
        variants=[];params_cases=[]
        casos=[('nominal','nominal',.02)]+[(name,'precio',.02) for name in proto['casos_precio']]+[(f'reg_{peso}','regularizacion',peso) for peso in proto['pesos_mid_control']]
        for name,family,peso in casos:
            changed,shock=perturbar(e,name,proto['amplitud_semispread']) if family=='precio' else (e.copy(deep=True),{})
            if not changed[~changed.entrenamiento].equals(e[~e.entrenamiento]):raise ValueError('holdout alterado')
            rs=construir_rs(changed,p)
            Fs={r.T:estimar_forward(r,.02) if family=='precio' else r.F for r in rs}
            rs=construir_rs(changed,p,Fs)
            s=s0 if name=='nominal' else ajustar(rs,peso)
            pred=e.copy();pred['nuevo']=np.nan;slices=[]
            for dias,g in e.groupby('dias',sort=True):
                t=float(dias)/365;F=Fs[t];F0=baseline[t]['F'];factor=F/F0
                pred.loc[g.index,'nuevo']=precio_black(F,g.strike.to_numpy(),s.w(np.log(g.strike.to_numpy()/F),t),p['forwards'][str(t)]['D'],g.tipo.eq('C').to_numpy())
                obs=np.linspace(baseline[t]['lo'],baseline[t]['hi'],401);glob=np.linspace(.85,1.15,1201)
                cq=cdf_comun(s,t,glob,factor)
                if (np.diff(cq)<-1e-10).any() or cq.min()<-1e-8 or cq.max()>1+1e-8:raise ValueError('CDF inválida')
                q=cuantiles_modelo_diagnostico(s,t,alpha,factor)
                slices.append(dict(T=t,F=F,F_nominal=F0,cuantiles_modelo_diagnostico=q.tolist(),
                    desplazamiento_cuantiles_bp=(10000*(q-baseline[t]['q'])).tolist(),
                    cdf_observada_max_pp=float(100*np.max(abs(cdf_comun(s,t,obs,factor)-cdf_comun(s0,t,obs)))),
                    cdf_global_max_pp=float(100*np.max(abs(cq-cdf_comun(s0,t,glob)))),
                    cdf_forma_max_pp=float(100*np.max(abs(cdf_comun(s,t,glob)-cdf_comun(s0,t,glob)))),
                    forward_mov_bp=float(10000*(factor-1))))
            v=dict(caso=name,familia=family,peso_mid=peso,shock=shock,
                cdf_observada_max_pp=max(z['cdf_observada_max_pp'] for z in slices),
                cdf_global_max_pp=max(z['cdf_global_max_pp'] for z in slices),
                cdf_forma_max_pp=max(z['cdf_forma_max_pp'] for z in slices),
                forward_mov_max_bp=max(abs(z['forward_mov_bp']) for z in slices),
                cuantiles_mov_max_bp=np.max(np.abs([z['desplazamiento_cuantiles_bp'] for z in slices]),axis=0).tolist(),
                holdout=metricas(pred[pred.holdout],'nuevo'),condiciones=s.condiciones())
            variants.append(v)
            params_cases.append(dict(caso=name,familia=family,parametros=dict(tiempos=s.tiempos.tolist(),thetas=s.thetas.tolist(),rho=s.rho,eta=s.eta,gamma=s.gamma),rebanadas=slices))
        cuts.append(dict(fecha=c['fecha'],hora=c['hora'],apto_puntual=c['apto_puntual'],variantes=variants,
            contraste_modelos=dict(cdf_observada_max_pp=max(z['cdf_observada_max_pp'] for z in contraste),
            cuantiles_diferencia_max_bp=np.max(np.abs([z['diferencia_cuantiles_bp'] for z in contraste]),axis=0).tolist())))
        dump(private/(tag+'_sensibilidad.json'),dict(casos=params_cases,contraste_modelos=contraste))
        print(tag,'microshock CDF pp',round(max(v['cdf_observada_max_pp'] for v in variants if v['familia']=='precio'),4),'modelo pp',round(cuts[-1]['contraste_modelos']['cdf_observada_max_pp'],4),flush=True)
    def aggregate(family):
        vv=[v for c in cuts for v in c['variantes'] if v['familia']==family]
        return dict(casos=len(vv),cdf_observada_max_pp=max(v['cdf_observada_max_pp'] for v in vv),
            cdf_observada_mediana_pp=float(np.median([v['cdf_observada_max_pp'] for v in vv])),
            cuantiles_mov_max_bp=np.max([v['cuantiles_mov_max_bp'] for v in vv],axis=0).tolist(),
            forward_mov_max_bp=max(v['forward_mov_max_bp'] for v in vv))
    if len(cuts)!=12 or sum(c['variantes'][0]['holdout']['dentro'] for c in cuts)!=744:
        raise ValueError('control nominal no reproduce el ensayo previo de doce fotos')
    fuentes=[Path(__file__),Path(__file__).with_name('metodo.py'),proto_path,
        Path(__file__).with_name('graficas.py'),Path(__file__).with_name('verificar.py'),
        RAIZ/'quantileflow/superficies.py',RAIZ/'quantileflow/opciones.py']
    dump(pub/'resumen.json',dict(protocolo=proto,naturaleza=proto['alcance'],presupuesto_datos=0,cortes=cuts,
        cuantiles_nominales_dentro_rango_training=inside.tolist(),rebanadas_nominales=sum(len(x['contraste_modelos']) for x in [json.loads(p.read_text(encoding='utf-8')) for p in private.glob('*_sensibilidad.json')]),
        total=dict(precio=aggregate('precio'),regularizacion=aggregate('regularizacion'),
            contraste_modelos=dict(cdf_observada_max_pp=max(c['contraste_modelos']['cdf_observada_max_pp'] for c in cuts),
                cuantiles_diferencia_max_bp=np.max([c['contraste_modelos']['cuantiles_diferencia_max_bp'] for c in cuts],axis=0).tolist())),
        origenes_sha256=dict(forward=sha(pf),ml=sha(pm)),
        codigo_sha256_lf={x.relative_to(RAIZ).as_posix():hashlib.sha256(x.read_text(encoding='utf-8').encode()).hexdigest() for x in fuentes},
        privados_sha256={x.name:sha(x) for x in sorted(private.glob('*_sensibilidad.json'))},
        entorno=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,pandas=pd.__version__)))


if __name__=='__main__':main()
