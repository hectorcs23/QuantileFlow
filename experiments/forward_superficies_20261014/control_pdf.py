"""Cuadratura independiente de masa, momento y payoffs de los 48 slices SSVI."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
import numpy as np
from scipy.integrate import quad
from quantileflow.opciones import precio_black
from experiments.forward_superficies_20261014.evaluar import restaurar


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--privado',type=Path,required=True)
    a=ap.parse_args()
    carpeta=Path(__file__).parent/'resultados'
    resumen=json.loads((carpeta/'resumen.json').read_text(encoding='utf-8'))
    errs=[]
    for c in resumen['cortes']:
        name=c['fecha']+'_'+c['hora'].replace(':','')+'_parametros.json'
        file=(a.privado/name).resolve()
        if not file.is_relative_to(a.privado.resolve()) or hashlib.sha256(file.read_bytes()).hexdigest()!=resumen['privado_sha256'][name]:
            raise ValueError('parámetros distintos a la corrida')
        p=json.loads(file.read_text(encoding='utf-8'))
        s=restaurar(p['ajustes']['estimado']).superficie
        for t in s.tiempos:
            F=p['forwards'][str(t)]['estimado'];D=np.exp(-p['tasa']*t)
            mass=quad(lambda k:float(s.densidad(k,t)),-20,20,epsabs=2e-9,points=[-.1,0,.1],limit=300)[0]
            mean=quad(lambda k:float(s.densidad(k,t))*np.exp(k),-20,20,epsabs=2e-9,points=[-.1,0,.1],limit=300)[0]
            errors=[]
            for ratio in [.97,1.,1.03]:
                k0=np.log(ratio)
                call=quad(lambda k:(np.exp(k)-ratio)*float(s.densidad(k,t)),k0,20,epsabs=2e-9,points=[.1],limit=300)[0]*D
                analytic=float(precio_black(F,F*ratio,s.w(k0,t),D,True))/F
                errors.append(abs(call-analytic))
            errs.append((abs(mass-1),abs(mean-1),max(errors)))
    values=np.max(errs,axis=0)
    if max(values)>1e-7: raise ValueError('PDF/precio/momento no coinciden')
    out=dict(rebanadas=len(errs),rango_integracion_k=[-20,20],
        max_error_masa=float(values[0]),max_error_media_S_sobre_F=float(values[1]),
        max_error_call_sobre_F=float(values[2]),precio_vs_integral_PDF=True,
        naturaleza='comprobación numérica de superficies estimadas; no validación de mercado',
        resumen_sha256=hashlib.sha256((carpeta/'resumen.json').read_bytes()).hexdigest(),
        codigo_sha256_lf=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest())
    (carpeta/'control_pdf.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
