# Ventana de superficie

Contraste descriptivo de ventanas de log-moneyness ±3/6/10%, presupuesto US$0,
seis sesiones conocidas. Mismos filtros y reservas centrales; extras anidados por
strike y ambos lados juntos. Forward reestimado solo con training, SSVI restringida.

±10% cubre geométricamente los cuantiles 5/95% en 48/48 curvas, pero el ajuste en las
reservas centrales cae de 45.31% a 38.37%. Más cobertura no prueba mayor fiabilidad.
Se conserva la referencia histórica; todas las fotos permanecen bloqueadas para uso
operativo. No cambia recopilación. Los vencimientos siguen concentrados cerca de 30 días.

Informe: [VENTANA_SUPERFICIE_2026-10-14.md](../../docs/VENTANA_SUPERFICIE_2026-10-14.md).

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python -X utf8 experiments/ventana_superficie_20261014/evaluar.py --tablas ../tablas_comparador_20261010_privadas --crudo ../datos_20261009_privados --forward ../forward_superficies_20261014_privado --privado ../ventana_superficie_20261014_privado
python -X utf8 experiments/ventana_superficie_20261014/verificar.py --privado ../ventana_superficie_20261014_privado --forward ../forward_superficies_20261014_privado
python -X utf8 experiments/ventana_superficie_20261014/graficas.py --privado ../ventana_superficie_20261014_privado
python -X utf8 -m pytest experiments/ventana_superficie_20261014/test_ventana.py -q
```

Las entradas requieren sus huellas originales. No requiere API ni contratación.
`resultados/` contiene solo agregados, verificación y gráfica agregada. Cotizaciones,
parámetros, cuantiles absolutos y `superficie_ampliada.png` permanecen fuera de Git.
La comparación de CDF se hace sobre el eje común S_T/F_central; al ampliar se cambian
simultáneamente training, F y superficie. No identifica causalmente cada componente.
