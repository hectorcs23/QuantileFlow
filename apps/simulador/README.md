# QuantileFlow: simulador condicional local

Camino A, actualizado el 6 de noviembre de 2026. El modo inicial usa datos sintéticos;
el modo observado, descrito al final, carga una captura histórica privada.
La app no necesita claves ni servicios externos y no ejecuta órdenes.

## Abrir

Desde la raíz del repositorio, con sus dependencias Python instaladas:

    python scripts/simulador_opciones.py

Abre <http://127.0.0.1:8791>. Mantén el proceso activo mientras usas la interfaz.
Para otro puerto agrega --puerto 8792. Si ya está ocupado, el servidor falla
en lugar de compartirlo con otra aplicación. Solo escucha en la máquina local.

Entradas: presupuesto, movimiento acumulado, días naturales, cambio de IV,
capital máximo en riesgo, límite de contratos, precio inicial, IV inicial,
comisiones, semispread, tasa y dividendo continuo.

Salidas: comparación por ganancia neta de toda la posición, contratos enteros,
caja, pérdida máxima con costos, controles adversos, superficie de PnL,
sensibilidad a IV y cambios de ganador al variar la hipótesis.
El botón de descarga conserva parámetros, datos sintéticos, escenarios y alcance.

En **Dos compras con el mismo presupuesto** puedes elegir dos series y fijar
cuántos contratos compras de cada una. Son alternativas independientes. La
comparación mantiene las compras fijas, muestra su punto de equilibrio al
horizonte objetivo y contrasta siete salidas con conservar el efectivo.
Las cifras no disponibles no compiten y los empates se muestran al centavo.
La sección tiene su propia descarga de las dos compras y sus escenarios.
[Ejemplo de tres calls frente a uno por US$300](../../docs/DOS_COMPRAS_2026-11-04.md).

## Convenciones que afectan el resultado

- Se generan 12 candidatos: calls europeos, strikes de 100%, 103%, 105% y 108%
  del spot inicial, DTE de 14, 30 y 60 días, multiplicador 100.
- Entrada = Black–Scholes + semispread; venta = máximo de cero y
  Black–Scholes − semispread. Al vencer: valor intrínseco, sin semispread.
- Comisión por contrato tanto al abrir como al cerrar, incluso al vencer;
  no se simulan ejercicio, entrega física, financiación ni impuestos.
- Cantidad = máximo entero de una sola serie que cabe en capital arriesgable,
  reservando ambas comisiones, con el límite de cantidad si se indica.
- La prima y cantidad de cada posición se mantienen fijas en las gráficas.
  Cada celda de la tabla de **ganadores** sí vuelve a comparar alternativas.
- Un escenario posterior al vencimiento es ausente; necesita el precio en
  la fecha de vencimiento. No se prolonga artificialmente la opción.
- Un control adicional posterior al vencimiento no elimina una opción cuyo
  horizonte objetivo sí es válido. Se muestra la ausencia.
- Se excluyen ask sintéticos menores a $0.01 por unidad. Es una convención de
  esta demo, no una regla general de ticks de todos los mercados.
- El efectivo es alternativa con PnL cero e intereses cero.
- No hay probabilidades estimadas, mezcla de series ni recomendación real.
  Una IV plana sirve como referencia condicional, no como superficie de
  mercado validada. No es adecuada por sí sola para opciones americanas
  con ejercicio anticipado y dividendos discretos.

El detalle del resultado y el siguiente paso están en
[SIMULADOR_CONDICIONAL_2026-10-21.md](../../docs/SIMULADOR_CONDICIONAL_2026-10-21.md).

## Verificar

    python -m pytest tests/test_duelo.py tests/test_simulador.py tests/test_escenarios.py tests/test_posiciones.py tests/test_comparador_pdf.py -q -p no:cacheprovider
    python experiments/simulador_20261021/generar_ejemplo.py

Para verificar la UI con el servidor abierto, Node.js, Playwright y un navegador
instalado:

    node apps/simulador/verificar_ui.cjs

Variables opcionales: BASE_URL (por defecto http://127.0.0.1:8791),
BROWSER_CHANNEL (msedge o chrome; por defecto Chromium de Playwright),
QA_DIR (capturas para inspección visual). NODE_PATH puede señalar el directorio
de dependencias de Node si Playwright no está instalado localmente.

La lógica financiera vive en Python; el navegador solo presenta resultados.
El servidor sirve una lista fija de archivos, valida cuerpo y origen de las
solicitudes, y no tiene endpoints para leer archivos privados ni enviar órdenes.
## Modo observado, 6 de noviembre de 2026

La página `/observadas` admite una captura privada normalizada. Arranque:

```text
python scripts/simulador_opciones.py --tablas-observadas RUTA_TABLAS_PRIVADAS --fecha-observada 2026-10-22
```

Sólo SPXW europeo PM se valora. Se filtran precios, tamaños, timestamps,
disponibilidad, spread y plazo; se invierte la IV bid/mid/ask de cada contrato.
El servidor verifica las huellas de las tablas al cargar. Sin captura devuelve
un mensaje explícito. El API no admite rutas ni cargas de archivos vía HTTP.

El modo es histórico y exploratorio, con `apto_compra=false`. No comparte IV ni
spot del ejemplo sintético. Sus exportaciones incluyen posiciones individuales:
mantenerlas fuera del repositorio público. Ver [informe](../../docs/CONTRATOS_OBSERVADOS_2026-11-06.md).

Prueba de UI: `node apps/simulador/verificar_observadas.cjs`, con Playwright
disponible, Edge y el servidor configurado. `QA_DIR` debe apuntar fuera del repo.
