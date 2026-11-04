# ¿Cambió la probabilidad implícita entre las 09:45 y las 10:00?

[Informe y figura](../../docs/CAMBIO_CDF_2026-11-03.md). Experimento descriptivo
con cero gasto y sin cambios en la captura o en el simulador de contratos.

**Entradas:** mismos dos snapshots privados y presupuestos de reparación
verificados en [el ensayo L1](../ruido_concentrado_20261022/README.md).
Protocolo congelado en `4d8965d`, antes de ejecutar la comparación. El programa
comprueba las huellas del estudio fuente y de las entradas privadas, conserva
la partición original y empareja por fecha y vencimiento SPXW PM exactos.
Las etiquetas «conocidas» y «nuevas» del JSON se heredan del ensayo anterior:
ambas cohortes eran conocidas al comenzar este contraste temporal.

**Salida:** bandas de cambio a cinco precios absolutos; posibilidad de cambio
nulo construida por umbral y comprobación simultánea para el caso principal.
El orden de cada vector marginal es [inferior exterior, inferior alcanzable,
superior alcanzable, superior exterior]. El JSON público usa niveles relativos
al forward inicial; los niveles absolutos, masas y grillas se mantienen en
la carpeta privada. Los días sin vencimiento común no se completan con otros
plazos. Un fallo de integridad o del solver interrumpe el estudio.

Desde la raíz de este repo, con las dependencias científicas existentes:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python -X utf8 experiments/cambio_cdf_20261103/evaluar.py --conocidas ../forward_fijo_20261014_privado --segunda ../entradas_l1_20261022_privado --privado ../cambio_cdf_20261103_privado
python -X utf8 experiments/cambio_cdf_20261103/verificar.py --conocidas ../forward_fijo_20261014_privado --segunda ../entradas_l1_20261022_privado --privado ../cambio_cdf_20261103_privado
python -X utf8 experiments/cambio_cdf_20261103/control_malla.py --conocidas ../forward_fijo_20261014_privado --segunda ../entradas_l1_20261022_privado --privado ../cambio_cdf_20261103_privado
python -X utf8 experiments/cambio_cdf_20261103/verificar_control.py --conocidas ../forward_fijo_20261014_privado --segunda ../entradas_l1_20261022_privado --privado ../cambio_cdf_20261103_privado
python -X utf8 experiments/cambio_cdf_20261103/grafica.py
python -X utf8 -m pytest experiments/cambio_cdf_20261103/test_cambio_cdf.py experiments/ruido_concentrado_20261022/test_metodo_l1.py experiments/distribuciones_ruido_20261022/test_metodo.py -q -p no:cacheprovider
```

La comprobación independiente reconstruye precios de calls y puts, restricciones
de masa, media y error, extremos de la CDF y clasificación temporal. Cuando los
rangos alcanzables se solapan, mezcla dos medidas de cada corte hasta una misma
CDF y vuelve a poner precio a todos los contratos. Para el programa conjunto
comprueba las dos medidas contra las cotizaciones y sus cinco CDF, sin volver
a optimizar. La figura solo se dibuja si las huellas coinciden.

El protocolo inicial certificó igualdad simultánea en 43 de 44 pares. El control
posterior añade nodos cerca de los umbrales y comprueba el único par pendiente
con los mismos presupuestos; el resultado combinado está en
`resultados/verificacion_control.json` (44/44, 220/220). Los resultados iniciales
se conservan sin sobrescribir.
