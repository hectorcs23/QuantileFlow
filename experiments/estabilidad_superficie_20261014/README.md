# Estabilidad de superficie y distribución

14 octubre 2026. Presupuesto de datos US$0. Seis sesiones conocidas, 48 rebanadas.
No se recolectaron datos nuevos ni se modificó la operación.

Probamos seis shocks de precios de training (5% del spread completo, preservando su
ancho), dos pesos de regularización y la diferencia nominal SSVI/convexo. Holdout intacto.
Reestimamos F solo con training en shocks de precio; en regularización lo congelamos.

Conclusión: máximo cambio de CDF dentro del rango de strikes de **0.06024 pp** por precio,
**0.00397 pp** por regularización y **13.29007 pp** entre modelos. La última cifra incluye
los átomos del convexo; no es un intervalo de confianza ni demuestra qué modelo es verdadero.
Los cuantiles 5%/95% quedan fuera del rango observado en las 48 rebanadas y se calculan
solo como diagnóstico de extrapolación; no sustituyen los cuantiles identificados del contrato.

Informe: [ESTABILIDAD_SUPERFICIE_2026-10-14.md](../../docs/ESTABILIDAD_SUPERFICIE_2026-10-14.md).

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python -X utf8 experiments/estabilidad_superficie_20261014/evaluar.py --forward ../forward_superficies_20261014_privado --ml ../ml_superficie_20261014_privado --privado ../estabilidad_superficie_20261014_privado
python -X utf8 experiments/estabilidad_superficie_20261014/verificar.py --privado ../estabilidad_superficie_20261014_privado --forward ../forward_superficies_20261014_privado --ml ../ml_superficie_20261014_privado
python -X utf8 experiments/estabilidad_superficie_20261014/graficas.py --privado ../estabilidad_superficie_20261014_privado --ml ../ml_superficie_20261014_privado
python -X utf8 -m pytest experiments/estabilidad_superficie_20261014/test_estabilidad.py -q
```

Las entradas y salidas privadas requieren las huellas originales. No se necesita API,
credenciales ni el solver del modelo convexo para este ensayo: solo se leen sus masas
nominales anteriores. `resultados/` contiene agregados; parámetros/F/cuantiles absolutos
y figuras de ejemplo permanecen fuera de Git. Toda foto conserva su bloqueo operativo.
