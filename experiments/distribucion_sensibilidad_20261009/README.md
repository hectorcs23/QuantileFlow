# Sensibilidad de distribuciones Q sin datos comprados

Actualización 10 de octubre: la conexión entre PDF y primas ya está implementada
en `valor_europeo`; ver [el nuevo informe](../../docs/VALORACION_CONSISTENTE_2026-10-10.md).
Los resultados de este directorio conservan la procedencia del commit `8d05af5`.

[Informe y límites](../../docs/SENSIBILIDAD_DISTRIBUCION_2026-10-09.md).
Presupuesto: US$0. Datos exclusivamente sintéticos; no hay llamadas de red.

Desde la raíz del repo, con las dependencias de `pyproject.toml`:

```powershell
python experiments/distribucion_sensibilidad_20261009/benchmark.py
python -m pytest -q tests experiments/expiraciones_20261008/test_expiraciones.py experiments/intradia_20261007/test_exploracion.py
```

Ejemplo de uso:

```python
from quantileflow.distribucion_pde import resolver_distribucion

d = resolver_distribucion(spot=100, plazo=30/365, tasa=.04, q=.013,
                          volatilidad=.25, nodos=3201, pasos=2400)
m = d.evaluar([95.13, 100.13, 105.13])
cola = d.probabilidad_cola(105)       # evento con umbral monetario fijo
retorno = d.probabilidad_retorno(.05) # umbral que cambia junto con el spot
q05 = d.cuantil(.05)
grad_cdf = d.gradiente_vol_cdf(105)   # todos los nodos de sigma(y)
grad_q05 = d.gradiente_vol_cuantil(.05)

cambio_iv_1pp = m.pdf_sigma * .01
cambio_por_dia_transcurrido = -m.pdf_plazo / 365
```

Las derivadas son del sistema numérico y de su reconstrucción triangular,
manteniendo la sigma en coordenadas relativas al spot. El adjunto sirve para
muchos parámetros espaciales y pocos objetivos; dos tangentes globales permiten
obtener sensibilidades de PDF/CDF en muchos umbrales. No hay recalibración oculta.
La derivada spot de PDF se marca `NaN` en vértices de la reconstrucción;
consultar `pdf_spot_diferenciable`. Cuantiles en colas con poca densidad se rechazan.

La probabilidad Q no representa confianza física ni una predicción. El ejemplo
europeo no valora el ejercicio americano de SPY. La conexión a primas necesita
una cuadratura consistente con la reconstrucción; ver el informe.

`resultados/` contiene solo escenarios sintéticos, errores contra lognormal,
75 cuantiles, escenarios finitos, comprobación adjunta/Taylor y una gráfica.
Los hashes de fuente del JSON se calculan tras normalizar finales de línea a LF.
El benchmark anterior permanece como registro del primer commit `a5fa04d`;
sus hashes originales no corresponden al operador refactorizado actual.
