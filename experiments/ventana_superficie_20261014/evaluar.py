"""Ampliación exploratoria sin cambiar captura, filtros ni filas históricas."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tomllib

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import numpy as np
import pandas as pd
from quantileflow.adaptador_comparador import preparar_comparador
from quantileflow.piloto import cargar_config
from quantileflow.opciones import precio_black
from quantileflow.superficies import funcion_g
from experiments.cadena_comparador_20261010.evaluar_cadena import integridad, sha
from experiments.forward_superficies_20261014.evaluar import restaurar
from experiments.forward_superficies_20261014.metodo import estimar_forward, cambiar_forward
from experiments.skew_bandas_20261010.evaluar import rebanadas, metricas
from experiments.estabilidad_superficie_20261014.evaluar import ajustar, verificar_origen
from experiments.estabilidad_superficie_20261014.metodo import cuantiles_modelo_diagnostico
from experiments.ventana_superficie_20261014.metodo import dividir_anidado, seleccionar


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')


def params(s):
    return dict(tiempos=s.tiempos.tolist(), thetas=s.thetas.tolist(), rho=s.rho, eta=s.eta, gamma=s.gamma)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('tablas', 'crudo', 'forward', 'privado'):
        ap.add_argument('--'+name, type=Path, required=True)
    a = ap.parse_args(); private = a.privado.resolve()
    if private.is_relative_to(RAIZ): raise ValueError('privados fuera del repo')
    private.mkdir(parents=True, exist_ok=True)
    out = Path(__file__).parent/'resultados'; out.mkdir(exist_ok=True)
    protocol_file = Path(__file__).with_name('protocolo.toml')
    proto = tomllib.loads(protocol_file.read_text(encoding='utf-8'))
    previous_file = RAIZ/'experiments/forward_superficies_20261014/resultados/resumen.json'
    previous = json.loads(previous_file.read_text(encoding='utf-8'))
    evidence = integridad(a.tablas, a.crudo)
    if evidence != previous['integridad']: raise ValueError('snapshot distinto')
    verificar_origen(previous['privado_sha256'], a.forward)
    cfg = cargar_config(RAIZ/'configs/piloto.toml')
    if sha(RAIZ/'configs/piloto.toml') != previous['config_sha256']: raise ValueError('config cambió')
    quotes = pd.read_parquet(a.tablas/'cotizaciones.parquet')
    refs = pd.read_parquet(a.tablas/'subyacente.parquet')
    cuts = []
    for cut in previous['cortes']:
        date, hour = cut['fecha'], cut['hora']; tag = date+'_'+hour.replace(':', '')
        old = pd.read_parquet(a.forward/(tag+'_evaluacion.parquet'))
        original = json.loads((a.forward/(tag+'_parametros.json')).read_text(encoding='utf-8'))
        prep = preparar_comparador(quotes, refs, date, hour, cfg.reglas, modo_descriptivo=True,
            tasa=cfg.tasa, q=cfg.rendimiento_dividendo, ancho_atm=.10, ancho_evaluacion=.10,
            minimo_dias=proto['minimo_dias'], maximo_dias=proto['maximo_dias'], minimo_entrenamiento=6)
        wide = dividir_anidado(prep.evaluacion, old)
        check = wide.set_index('id_contrato').loc[old.id_contrato]
        for field in ('bid', 'ask', 'strike', 'dias', 'entrenamiento', 'holdout'):
            if not np.array_equal(check[field], old[field]): raise ValueError('histórico cambió: '+field)
        if set(wide[wide.k.abs() <= .03].id_contrato) != set(old.id_contrato):
            raise ValueError('universo central cambió')
        wide['anillo'] = np.where(wide.k.abs() <= .03, 'centro', np.where(wide.k.abs() <= .06, 'alas_3_6', 'alas_6_10'))
        models = []; pub = []
        for width in proto['anchos_log_moneyness']:
            selected = seleccionar(wide, width)
            train = rebanadas(selected[selected.entrenamiento], prep.spot, cfg.tasa, cfg.rendimiento_dividendo)
            if width == .03:
                Fs = {r.T: original['forwards'][str(r.T)]['estimado'] for r in train}
                s = restaurar(original['ajustes']['estimado']).superficie
            else:
                Fs = {r.T: estimar_forward(r, proto['peso_mid']) for r in train}
                s = ajustar([cambiar_forward(r, Fs[r.T]) for r in train], proto['peso_mid'])
            col = 'precio_'+str(width); wide[col] = np.nan
            covered = np.zeros(len(proto['cuantiles']), int); slices = []
            for r in rebanadas(wide, prep.spot, cfg.tasa, cfg.rendimiento_dividendo):
                F = Fs[r.T]; mask = np.isclose(wide.dias, r.T*365, rtol=0, atol=1e-10)
                wide.loc[mask, col] = precio_black(F, r.K, s.w(np.log(r.K/F), r.T), r.D, r.es_call)
                training = selected[selected.entrenamiento & np.isclose(selected.dias, r.T*365, rtol=0, atol=1e-10)]
                lo, hi = training.strike.min()/F, training.strike.max()/F
                qs = cuantiles_modelo_diagnostico(s, r.T, proto['cuantiles'])
                inside = (qs >= lo) & (qs <= hi); covered += inside
                slices.append(dict(T=r.T, F=F, D=r.D, rango_training=[float(lo),float(hi)], cuantiles_modelo=qs.tolist()))
            k = np.linspace(-.3,.3,601); times = np.linspace(s.tiempos[0], s.tiempos[-1],25)
            gm = min(float(funcion_g(*s.derivadas(k,t),k).min()) for t in times)
            calendar = float(np.diff(s.w(k[None,:],times[:,None]),axis=0).min())
            if gm < -1e-10 or calendar < -1e-10: raise ValueError('restricciones fallaron')
            measures = {ring: metricas(wide[wide.holdout & wide.anillo.eq(ring)], col)
                        for ring in ('centro','alas_3_6','alas_6_10')}
            pub.append(dict(ancho=width, training=len(selected[selected.entrenamiento]),
                filas_en_ventana=len(selected), vencimientos=len(train), holdout_por_anillo=measures,
                cuantiles_dentro_training=covered.tolist(), g_min_malla=gm,
                incremento_w_min_malla=calendar, condiciones=s.condiciones()))
            models.append(dict(ancho=width, parametros=params(s), rebanadas=slices))
        wide.to_parquet(private/(tag+'_evaluacion.parquet'), index=False)
        dump(private/(tag+'_modelos.json'), dict(modelos=models, spot=prep.spot, tasa=cfg.tasa, q=cfg.rendimiento_dividendo))
        cuts.append(dict(fecha=date,hora=hour,apto_puntual=prep.apto_puntual,bloqueos=list(prep.bloqueos),
            calidad=prep.calidad, variantes=pub))
        print(tag, [(v['ancho'],v['filas_en_ventana'],v['holdout_por_anillo']['centro']['dentro']) for v in pub],flush=True)
    total = []
    for j,width in enumerate(proto['anchos_log_moneyness']):
        vv = [c['variantes'][j] for c in cuts]
        total.append(dict(ancho=width,training=sum(v['training'] for v in vv), filas=sum(v['filas_en_ventana'] for v in vv),
            rebanadas=sum(v['vencimientos'] for v in vv),
            cuantiles_dentro_training=np.sum([v['cuantiles_dentro_training'] for v in vv],axis=0).tolist(),
            holdout_por_anillo={ring:dict(filas=sum(v['holdout_por_anillo'][ring]['filas'] for v in vv),
                dentro=sum(v['holdout_por_anillo'][ring]['dentro'] for v in vv)) for ring in ('centro','alas_3_6','alas_6_10')}))
    if len(cuts)!=12 or total[0]['holdout_por_anillo']['centro']['dentro']!=744:
        raise ValueError('control histórico no reproduce 744')
    files = [Path(__file__),Path(__file__).with_name('metodo.py'),protocol_file,
        RAIZ/'quantileflow/adaptador_comparador.py',RAIZ/'quantileflow/cadenas.py',RAIZ/'quantileflow/superficies.py',
        RAIZ/'experiments/estabilidad_superficie_20261014/evaluar.py',
        RAIZ/'experiments/forward_superficies_20261014/metodo.py']
    dump(out/'resumen.json',dict(protocolo=proto,integridad=evidence,origen_sha256=sha(previous_file),
        cortes=cuts,total=total,config_sha256=previous['config_sha256'],
        codigo_sha256_lf={p.relative_to(RAIZ).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in files},
        privados_sha256={p.name:sha(p) for p in sorted(private.glob('*')) if p.suffix in ('.json','.parquet')}))


if __name__ == '__main__': main()
