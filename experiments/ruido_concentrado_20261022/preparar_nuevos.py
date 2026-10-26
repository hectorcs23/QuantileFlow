"""Congela las entradas nuevas y sus huellas, sin usar precios reservados al estimar F."""
import argparse,hashlib,json,subprocess,sys,tomllib
from pathlib import Path
RAIZ=Path(__file__).resolve().parents[2];sys.path.insert(0,str(RAIZ))
import numpy as np
import pandas as pd
from quantileflow.adaptador_comparador import preparar_comparador
from quantileflow.piloto import cargar_config
from experiments.cadena_comparador_20261010.evaluar_cadena import integridad
from experiments.skew_bandas_20261010.evaluar import rebanadas
from experiments.forward_superficies_20261014.metodo import estimar_forward
from experiments.ventana_superficie_20261014.metodo import dividir_anidado
from experiments.distribuciones_ruido_20261022.evaluar import dump,sha


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('tablas','crudo','privado'): ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args(); dst=a.privado.resolve()
    if dst.is_relative_to(RAIZ) or dst in (a.tablas.resolve(),a.crudo.resolve()):
        raise ValueError('Entradas y salidas separadas, privadas fuera de Git')
    dst.mkdir(parents=True,exist_ok=True)
    folder=Path(__file__).parent; out=folder/'resultados';out.mkdir(exist_ok=True)
    proto=tomllib.loads((folder/'protocolo.toml').read_text(encoding='utf-8'))
    checks=integridad(a.tablas,a.crudo)
    qs=pd.read_parquet(a.tablas/'cotizaciones.parquet');refs=pd.read_parquet(a.tablas/'subyacente.parquet')
    cfg=cargar_config(RAIZ/'configs/piloto.toml'); cuts=[];files=[]
    for dt in pd.date_range(proto['nuevos_desde'],proto['nuevos_hasta'],freq='B'):
        fecha=dt.date().isoformat()
        for hora in proto['nuevos_horas']:
            kw=dict(modo_descriptivo=True,tasa=cfg.tasa,q=cfg.rendimiento_dividendo,
                    minimo_dias=1.,maximo_dias=90.,minimo_entrenamiento=6)
            central=preparar_comparador(qs,refs,fecha,hora,cfg.reglas,ancho_atm=.03,ancho_evaluacion=.03,**kw)
            wide=preparar_comparador(qs,refs,fecha,hora,cfg.reglas,ancho_atm=.10,ancho_evaluacion=.10,**kw)
            if central.evaluacion.empty or wide.evaluacion.empty: raise ValueError('Corte sin datos: '+fecha+hora)
            e=dividir_anidado(wide.evaluacion,central.evaluacion)
            zs=[]
            for r in rebanadas(central.evaluacion[central.evaluacion.entrenamiento],central.spot,cfg.tasa,cfg.rendimiento_dividendo):
                zs.append(dict(T=r.T,F=estimar_forward(r,.02),D=r.D))
            ds=np.array([z['T']*365 for z in zs]);e=e[np.any(np.isclose(e.dias.to_numpy()[:,None],ds[None,:],rtol=0,atol=1e-10),axis=1)]
            assert not e.id_contrato.duplicated().any() and (e.entrenamiento==~e.holdout).all()
            tag=fecha+'_'+hora.replace(':','')
            ep=dst/(tag+'_evaluacion.parquet');mp=dst/(tag+'_modelos.json')
            e.to_parquet(ep,index=False);dump(mp,dict(modelos_fijos=[dict(rebanadas=zs)]));files.extend([ep,mp])
            cuts.append(dict(fecha=fecha,hora=hora,filas=len(e),training=int(e.entrenamiento.sum()),
                holdout=int(e.holdout.sum()),rebanadas=len(zs),calidad=wide.calidad,bloqueos=list(wide.bloqueos)))
            print(tag,len(e),'filas',len(zs),'vencimientos',flush=True)
    sources=[Path(__file__),folder/'protocolo.toml',RAIZ/'configs/piloto.toml',
        RAIZ/'quantileflow/adaptador_comparador.py',RAIZ/'quantileflow/cadenas.py',
        RAIZ/'experiments/forward_superficies_20261014/metodo.py',
        RAIZ/'experiments/ventana_superficie_20261014/metodo.py']
    dump(out/'entradas_nuevas.json',dict(cortes=cuts,integridad=checks,
        datos_commit=subprocess.check_output(['git','-c','safe.directory='+a.crudo.resolve().as_posix(),
            '-C',str(a.crudo),'rev-parse','HEAD'],text=True,encoding='utf-8').strip(),
        codigo_sha256_lf={p.relative_to(RAIZ).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in sources},
        privados_sha256={p.name:sha(p) for p in files}))


if __name__=='__main__': main()
