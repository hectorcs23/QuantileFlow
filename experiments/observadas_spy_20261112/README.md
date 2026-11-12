# SPY frente a SPXW con US$300

Continúa [`observadas_20261106`](../observadas_20261106/README.md) con la misma foto (22 de octubre de 2026,
09:45 de Nueva York) y la misma hipótesis (+3 % en siete días). Agrega los calls de SPY: ejercicio americano
y dividendos conocidos al corte. Resultados y alcance: [informe](../../docs/contratos_observados_spy.md).

```text
python scripts/normalizar_alpaca.py --desde 2026-10-22 --hasta 2026-10-22 --datos RUTA_REPO_DATOS --salida RUTA_TABLAS
python experiments/observadas_spy_20261112/evaluar.py --tablas RUTA_TABLAS --crudo RUTA_REPO_DATOS --privado RUTA_SALIDA_PRIVADA
```

`evaluar.py` compara las dos raíces, junta sus compras para buscar un ganador separado, mueve la referencia
de SPY a su bid y su ask, recalcula todas las celdas con otra fórmula y corre el árbol americano en cada
candidato. La salida privada (`analisis_spy.json`) va fuera del repositorio; su huella queda en el resumen.

```text
python scripts/normalizar_alpaca.py --desde 2026-10-02 --hasta 2026-11-06 --datos RUTA_REPO_DATOS --salida RUTA_TABLAS_DESARROLLO
python experiments/observadas_spy_20261112/sesiones.py --tablas RUTA_TABLAS_DESARROLLO --crudo RUTA_REPO_DATOS
```

`sesiones.py` repite solo los conteos en las sesiones de desarrollo (hasta el 6 de noviembre). No usa
rendimientos ni sesiones de la muestra confirmatoria del [protocolo predictivo](../../docs/protocolo_predictivo.md).

En `resultados/` solo hay agregados: `resumen.json`, `sesiones.json` y cuatro gráficas.

Pruebas:

```text
python -m pytest tests/test_observadas_spy.py tests/test_observadas.py -q
```

Interfaz, con el servidor en modo SPY y Playwright disponible:

```text
RAIZ=SPY ESPERADAS=145 BROWSER_CHANNEL= node apps/simulador/verificar_observadas.cjs
```
