"""Entradas para la réplica histórica; solo los resúmenes salen de la carpeta privada."""
import argparse,json,subprocess,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import pandas as pd
from quantileflow.adaptador_comparador import preparar_comparador
from quantileflow.piloto import cargar_config
from experiments.cadena_comparador_20261010.evaluar_cadena import integridad
from experiments.skew_bandas_20261010.evaluar import rebanadas
from experiments.forward_superficies_20261014.metodo import estimar_forward
from experiments.distribuciones_ruido_20261022.evaluar import dump,sha

DIR=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser()
    for n in ('tablas','crudo','privado'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();dst=a.privado.resolve();cfg=cargar_config(ROOT/'configs/piloto.toml')
    if dst.is_relative_to(ROOT) or any(dst.is_relative_to(x.resolve()) or x.resolve().is_relative_to(dst) for x in (a.tablas,a.crudo)):
        raise ValueError('Mantener entradas y salidas privadas separadas')
    proto=tomllib.loads((DIR/'protocolo.toml').read_text('utf8'))
    head=subprocess.check_output(['git','-c','safe.directory='+a.crudo.resolve().as_posix(),'-C',str(a.crudo),'rev-parse','HEAD'],encoding='utf8').strip()
    if head!=proto['raw_commit']: raise ValueError('Revisión privada diferente')
    checks=integridad(a.tablas,a.crudo);dst.mkdir(exist_ok=True,parents=True);out=DIR/'resultados';out.mkdir(exist_ok=True)
    qs=pd.read_parquet(a.tablas/'cotizaciones.parquet');refs=pd.read_parquet(a.tablas/'subyacente.parquet')
    files={};cuts=[]
    for day in proto['adicionales']:
        for hr in proto['horas']:
            kw=dict(modo_descriptivo=True,tasa=cfg.tasa,q=cfg.rendimiento_dividendo,minimo_dias=1.,maximo_dias=90.,minimo_entrenamiento=6)
            get=lambda width:preparar_comparador(qs,refs,day,hr,cfg.reglas,ancho_atm=width,ancho_evaluacion=width,**kw)
            central,wide=get(.03),get(.10)
            if central.evaluacion.empty or wide.evaluacion.empty: raise ValueError('Corte vacío: '+day+hr)
            zs=[dict(T=r.T,F=estimar_forward(r,.02),D=r.D) for r in rebanadas(central.evaluacion[central.evaluacion.entrenamiento],central.spot,cfg.tasa,cfg.rendimiento_dividendo)]
            tag=day+'_'+hr.replace(':','');ep=dst/(tag+'_evaluacion.parquet');mp=dst/(tag+'_modelos.json')
            wide.evaluacion.to_parquet(ep,index=False);dump(mp,dict(modelos_fijos=[dict(rebanadas=zs)]))
            files.update({p.name:sha(p) for p in (ep,mp)})
            cuts.append(dict(fecha=day,hora=hr,filas=len(wide.evaluacion),anclas=len(zs),bloqueos=list(wide.bloqueos)))
    dump(out/'entrada_adicional.json',dict(raw_commit=head,privados_sha256=files,integridad=checks,cortes=cuts))
    print('Cortes:',len(cuts),'Huellas:',checks['manifiestos'],checks['paginas_unicas'])
if __name__=='__main__':main()
