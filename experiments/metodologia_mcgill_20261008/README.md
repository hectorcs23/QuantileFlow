# Puente analítico para la metodología de sensibilidad

La propuesta está en [docs/METODOLOGIA_SENSIBILIDAD_MCGILL_2026-10-08.md](../../docs/METODOLOGIA_SENSIBILIDAD_MCGILL_2026-10-08.md).

Este experimento verifica la relación entre una densidad terminal lognormal, su derivada respecto al spot y el precio/delta de calls europeas. Es sintético, con IV y plazo fijos. No implementa un solver PDE ni un adjunto y no estima probabilidades físicas.

Desde la raíz:

```bash
python experiments/metodologia_mcgill_20261008/puente_analitico.py
```

Comprueba 225 casos mediante cuadratura contra Black–Scholes, masa total uno, masa derivada cero y diferencias centrales. Genera un JSON con los errores y una figura en `resultados/`. El criterio se verifica con excepciones de aserción; ejecutar Python sin `-O`.
