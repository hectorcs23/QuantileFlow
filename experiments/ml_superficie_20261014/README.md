# Primera red de superficie y control convexo

Fecha: 14 octubre 2026. Presupuesto de datos US$0. **Exploratorio: seis sesiones ya conocidas.**

La red pequeña corrige SSVI por strike relativo al forward. No pronostica dirección,
no entrena con resultados futuros y no cambia la captura diaria.
El control convexo aprende probabilidades en un soporte común con masa/media/calendario
como restricciones, en lugar de penalizaciones aproximadas.

Resultado: SSVI **744/1,642 = 45.31%**, red **741/1,642 = 45.13%** antes de rechazar
dos fotos con PDF negativa; convexo **778/1,642 = 47.38%**. No adoptamos esta red.

Informe: [RESULTADO_ML_SUPERFICIE_2026-10-14.md](../../docs/RESULTADO_ML_SUPERFICIE_2026-10-14.md).

## Reproducción

Requiere las salidas privadas de `forward_superficies_20261014` con sus huellas correctas.
Código adicional: una librería de solver gratuita, sin instalarla en el Python global.

```powershell
python -m pip install -r experiments/ml_superficie_20261014/requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python -X utf8 experiments/ml_superficie_20261014/evaluar.py --origen ../forward_superficies_20261014_privado --privado ../ml_superficie_20261014_privado
python -X utf8 experiments/ml_superficie_20261014/verificar.py --privado ../ml_superficie_20261014_privado
python -X utf8 experiments/ml_superficie_20261014/graficas.py --privado ../ml_superficie_20261014_privado
python -X utf8 -m pytest tests experiments/expiraciones_20261008/test_expiraciones.py experiments/intradia_20261007/test_exploracion.py experiments/cadena_comparador_20261010/test_evaluar_cadena.py experiments/skew_bandas_20261010/test_control_forward.py experiments/forward_superficies_20261014/test_metodo.py experiments/ml_superficie_20261014/test_modelos.py -q
```

En `resultados/` solo hay agregados y huellas. Pesos neuronales, masas por nodo, parámetros
de mercado, cotizaciones y la figura de curvas/CDF permanecen **fuera del repo**.
`intentos_numericos.json` conserva los fallos de convergencia anteriores: no fueron modelos
elegidos por holdout. Se conservan copias de datos/código anteriores en el almacenamiento privado.

El caso convexo del 7 octubre 10:00 terminó `AlmostSolved`; satisface las restricciones,
pero se declara esa precisión reducida. Los otros once terminaron `Solved`.
El calendario certificado es el de calls **normalizados por D*F**, con soporte común;
no certifica una curva de carry externa ni ejecutabilidad de indicative.
