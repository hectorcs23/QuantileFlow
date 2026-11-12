# Ruido concentrado y contraste con otras sesiones

Continuación del camino B. Protocolo congelado el 22 de octubre de 2026 en
`bedbd5b`, antes de examinar la cohorte del 12–16 de octubre. Evaluación final
completada el 26 de octubre. Presupuesto de datos: **USD 0**.

Se compara un margen uniforme por cotización con un presupuesto de error medio
L1 y el mismo máximo individual. Se mantienen todas las filas de entrenamiento;
no se elimina automáticamente ningún contrato. Se calculan bandas de CDF y de
valoración reservada, con controles de forward, descuento, soporte y rampas.

Informe: [RUIDO_CONCENTRADO_2026-10-26.md](../../docs/RUIDO_CONCENTRADO_2026-10-26.md).

## Reproducir

Desde la raíz del repo, con Python y las dependencias científicas del proyecto:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python -X utf8 scripts/normalizar_alpaca.py --desde 2026-10-12 --hasta 2026-10-16 --datos ../datos_nuevos_20261022_privado --salida ../tablas_l1_20261022_privado
python -X utf8 experiments/ruido_concentrado_20261022/preparar_nuevos.py --tablas ../tablas_l1_20261022_privado --crudo ../datos_nuevos_20261022_privado --privado ../entradas_l1_20261022_privado
python -X utf8 experiments/ruido_concentrado_20261022/evaluar.py --origen ../forward_fijo_20261014_privado --nuevos ../entradas_l1_20261022_privado --privado ../ruido_concentrado_20261022_privado
python -X utf8 experiments/ruido_concentrado_20261022/verificar.py --origen ../forward_fijo_20261014_privado --nuevos ../entradas_l1_20261022_privado --privado ../ruido_concentrado_20261022_privado
python -X utf8 experiments/ruido_concentrado_20261022/graficas.py
python -X utf8 -m pytest experiments/ruido_concentrado_20261022/test_metodo_l1.py experiments/distribuciones_ruido_20261022/test_metodo.py experiments/factibilidad_20261020/test_factibilidad.py -q -p no:cacheprovider
```

La copia de datos usada está fijada en
`43b286c0df2de41d63d0475260517c01d6f36f54`. Las entradas antiguas requieren el
snapshot con las huellas de `forward_fijo_20261014/resultados/resumen.json`.
Una normalización regenerada puede cambiar su manifiesto de entorno aunque
los Parquet coincidan: se registran nuevamente todas las huellas utilizadas.

`resultados/` contiene solo agregados, bandas normalizadas y huellas.
Las cotizaciones, identificadores y soluciones completas permanecen en carpetas
privadas externas. El verificador reconstruye las restricciones y objetivos
desde esas soluciones sin volver a optimizar. Las gráficas exigen ese control.

Las sesiones nuevas son históricas y comparten proveedor. El preprocesamiento
heredado utiliza una referencia implícita de la cadena para seleccionar filas
e invertir IV; los precios reservados no entran directamente en el LP ni en
el ajuste central de F. No es una validación independiente del feed ni de todo
el proceso de selección. No hay probabilidad física, PDF única, órdenes ni
cambios en captura o simulador A.
