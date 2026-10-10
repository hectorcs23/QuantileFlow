# Valoración consistente con la distribución reconstruida

[Informe](../../docs/VALORACION_CONSISTENTE_2026-10-10.md).
Presupuesto de datos: US$0. Casos europeos sintéticos, sin red.

Desde la raíz del repo, con las dependencias del proyecto:

```powershell
python experiments/valoracion_consistente_20261010/benchmark.py
python -m pytest -q tests experiments/expiraciones_20261008/test_expiraciones.py experiments/intradia_20261007/test_exploracion.py
```

La API `DistribucionPDE.valor_europeo` integra contra la misma base triangular
de PDF/CDF. `pde.resolver_europea` delega en ella y conserva sus campos.
El benchmark incluye 90 casos contra BS, una integral independiente de la PDF,
convergencia y recuperación de densidad por diferencias segundas de precio.
Los resultados guardan hashes de fuente normalizados a LF y versiones del entorno.

La paridad usa la media de esta distribución; su desviación del forward teórico
se devuelve explícitamente. No hay corrección oculta del momento. El payoff se
integra numéricamente por Gauss de ocho puntos tras dividir en nudos y strike;
los errores publicados corresponden a las mallas y parámetros probados.
No es un modelo americano ni una distribución física ni un predictor.
