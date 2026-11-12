# Ventanas con forward central fijo

Contraste descriptivo de seis sesiones conocidas. Mantiene las filas/reservas del
ensayo de ventanas y congela F por vencimiento al estimado con training central.
Recalibra solo SSVI en ±6/10%; conserva pérdida e inicios. No modifica recopilación.

El centro cae de 45.31% dentro de bid/ask a 41.96%/38.25% con F fijo: congelarlo no
elimina el compromiso entre centro y alas. Incluso con cualquier F común por
vencimiento, 374/1,388 pares reservados amplios siguen siendo incompatibles con
paridad. El F libre es un límite posterior, nunca un ajuste elegido con holdout.

Informe: [FORWARD_FIJO_2026-10-14.md](../../docs/FORWARD_FIJO_2026-10-14.md).

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python -X utf8 experiments/forward_fijo_20261014/evaluar.py --ventana ../ventana_superficie_20261014_privado --privado ../forward_fijo_20261014_privado
python -X utf8 experiments/forward_fijo_20261014/verificar.py --ventana ../ventana_superficie_20261014_privado --privado ../forward_fijo_20261014_privado
python -X utf8 experiments/forward_fijo_20261014/graficas.py
python -X utf8 -m pytest experiments/forward_fijo_20261014/test_paridad_fija.py -q
```

Se requieren las entradas originales y sus huellas. Presupuesto de datos US$0;
sin API ni solver nuevo. `resultados/` publica agregados y verificaciones; datos y
parámetros permanecen en el directorio privado externo. Las fotos siguen bloqueadas.
