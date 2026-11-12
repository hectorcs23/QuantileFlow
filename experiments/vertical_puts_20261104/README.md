# Vertical de puts entre las 09:45 y las 10:00

[Informe y decisión](../../docs/VERTICAL_PUTS_2026-11-04.md). El protocolo se guardó en
`53939e9` antes de calcular el contraste. La zona principal usa los puts cercanos a
0.97F y 1.03F al primer corte; a las 10:00 se requieren sus mismos identificadores.
La observación directa usa todas las filas elegibles de las tablas, incluso las
reservadas para otros estudios. No se calibra una distribución.

Se necesitan las dos entradas privadas del estudio L1 y el snapshot privado
`43b286c0df2de41d63d0475260517c01d6f36f54`. Desde la raíz de esta rama:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python -X utf8 scripts/normalizar_alpaca.py --desde 2026-10-19 --hasta 2026-10-22 --datos ../datos_nuevos_20261022_privado --salida ../tablas_vertical_20261104_privado
python -X utf8 experiments/vertical_puts_20261104/preparar.py --tablas ../tablas_vertical_20261104_privado --crudo ../datos_nuevos_20261022_privado --privado ../entradas_vertical_20261104_privado
python -X utf8 experiments/vertical_puts_20261104/evaluar.py --primera ../forward_fijo_20261014_privado --segunda ../entradas_l1_20261022_privado --adicional ../entradas_vertical_20261104_privado --privado ../vertical_puts_20261104_privado
python -X utf8 experiments/vertical_puts_20261104/verificar.py --primera ../forward_fijo_20261014_privado --segunda ../entradas_l1_20261022_privado --adicional ../entradas_vertical_20261104_privado --privado ../vertical_puts_20261104_privado
python -X utf8 experiments/vertical_puts_20261104/grafica.py
python -X utf8 -m pytest experiments/vertical_puts_20261104/test_vertical.py experiments/cambio_cdf_20261103/test_cambio_cdf.py -q -p no:cacheprovider
```

La normalización puede incluir un manifiesto de entorno distinto al regenerarla;
se comprueban los archivos efectivamente utilizados. El verificador vuelve a
seleccionar los strikes desde el primer corte y enumera las 16 combinaciones de
extremos de las cuatro primas (dos contratos, dos fotos). Se conservan aparte
la prueba prefijada y el diagnóstico posterior que cambia el reloj de referencia.
La carpeta pública contiene agregados y huellas; las patas y sus identificadores
quedan fuera del repositorio de código.
