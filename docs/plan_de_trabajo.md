# QuantileFlow — plan de trabajo

**Estado:** plan de investigación, 26 de septiembre de 2026.  
**Propósito:** averiguar si los precios de las opciones al inicio de la sesión aportan información útil para gestionar una posición en el subyacente. Ninguna señal ni rentabilidad está demostrada todavía.

## 1. Pregunta y alcance inicial

La primera pregunta es: **¿el encarecimiento relativo de calls frente a puts, y su cambio desde la sesión anterior, anticipa dirección o riesgo futuro una vez considerado lo que ya muestra el precio del subyacente?** La segunda pregunta, condicionada a la primera, es si los cambios de la distribución implícita y su transporte añaden algo a esas medidas más sencillas.

El primer estudio se limitará a un subyacente muy líquido y sus opciones, con una captura reproducible alrededor de las 09:45 ET. Usaremos vencimientos cercanos a 30 días calendario y evaluaremos rendimientos posteriores de **1 y 5 sesiones**. El análisis diario comienza después de contar con datos utilizables; por ahora el sistema emitirá investigación y recomendaciones simuladas, sin órdenes reales.

**Decisión de instrumento al cerrar la fase de datos:** SPX ofrece opciones europeas y simplifica la paridad; SPY puede ser más accesible, pero sus opciones americanas requieren tratar dividendos y ejercicio anticipado. No mezclaremos precios de ambos instrumentos como si fueran equivalentes. Elegiremos uno tras inspeccionar cobertura, calidad, costo y sincronización de una muestra histórica de apertura.

## 2. Reglas matemáticas que gobiernan el experimento

- **Mismo strike y vencimiento:** para opciones europeas, `call − put = descuento × (forward − strike)`. El residuo de esa relación puede servir como control de calidad y, si sobrevive a todos los controles, como señal candidata. El forward usado para evaluar un par se estimará con información independiente de ese mismo par; evitar así construir una señal circular.
- **Strikes simétricos alrededor del forward:** un call a +3 % y un put a −3 % *no* son un par de paridad. Su comparación mide asimetría de precios de cola. Compararemos volatilidades implícitas, precios estandarizados y sensibilidad a los pagos, además de primas brutas. Repetiremos con distancias comparables por delta, porque una separación fija de 3 % cambia de significado con la volatilidad y el plazo.
- **Precio de opción ≠ probabilidad de ejercicio:** la prima combina probabilidad y tamaño del pago. La distribución que respalda el precio, `Q`, también contiene primas de riesgo; la probabilidad de subida real, `P`, se estimará con resultados posteriores.
- **Conservar las cotizaciones originales:** guardaremos bid, ask, tamaños y sellos de tiempo antes del ajuste de superficies. Un ajuste que impone paridad puede borrar el residuo que se pretende estudiar. La superficie ajustada y las diferencias observadas tendrán salidas distintas.
- **Horizontes consistentes:** una superficie a 30 días alimenta variables explicativas para pronósticos a 1 y 5 sesiones. No convertiremos una probabilidad a 30 días en una probabilidad diaria dividiéndola por 30.

## 3. Fases y criterios para avanzar

| Fase | Trabajo y entregable verificable | Criterio de salida |
|---|---|---|
| **0. Datos y horario** | Definir el contrato de datos; obtener una muestra histórica de cadenas con bid/ask, tamaños, subyacente sincronizado, tipo de ejercicio, tasas, dividendos y hora de recepción. Guardar snapshots inmutables. | Se puede reconstruir exactamente qué se sabía a las 09:45; se conocen cobertura, latencia, huecos y costo. Si no, cambiar fuente u horario antes de modelar. |
| **1. Señales simples de calls y puts** | Calcular asimetría ±3 % alrededor del forward, asimetría por delta, pendiente local de la sonrisa y residuo de paridad de pares del mismo strike. Guardar niveles y diferencias respecto del día anterior, con bandas de sensibilidad a bid/ask. | Las medidas son estables ante pequeños cambios de cotización; se distinguen efectos de dividendos, ejercicio, spread y cotizaciones desfasadas. |
| **2. Prueba predictiva** | Crear etiquetas de retorno, signo, pérdida de cola y volatilidad futura a 1 y 5 sesiones. Comparar una referencia de precio/volatilidad/mercado con la misma familia de modelo más cada señal de opciones. | Reporte fuera de muestra de mejora o falta de ella, con intervalos que consideran la dependencia temporal. Mantener separados dirección y riesgo. |
| **3. Distribuciones y transporte** | Si los datos lo permiten, ajustar una superficie sin arbitraje, extraer cuantiles identificados, calcular cambios firmados, W1/W2 e innovación condicionada por precio y mercado. Comparar con la fase 2. | El transporte mejora una métrica predefinida frente a las señales simples, o se documenta que no justifica su complejidad. |
| **4. Gestión de posición** | Traducir pronósticos físicos calibrados a `mantener / reducir / aumentar`, sujetos a costos, exposición y riesgo. Comparar contra mantener la posición y una regla sencilla de control de volatilidad. | Mejora neta y estable frente a referencias comparables; ninguna recomendación depende de una cola no identificada o de datos degradados. |
| **5. Operación simulada** | Informe diario con hora de corte, fuentes, señal, incertidumbre, motivo de decisión y registro reproducible. Reconciliar posiciones y órdenes simuladas. | Corridas reproducibles; fallos de proveedor o datos no producen órdenes ni cambios silenciosos de posición. |

Las fases son puertas de evidencia, no fechas obligatorias. La estimación de 6–10 semanas del documento técnico corresponde a ingeniería de un prototipo con datos disponibles; demostrar habilidad predictiva puede requerir bastante más historia y seguimiento prospectivo.

## 4. Diseño de la prueba de señales

**Variables candidatas, calculadas solo con información disponible al corte:**

1. Diferencia de volatilidad entre call y put fuera del dinero a distancia comparable del forward; luego repetir con delta comparable. Registrar también el nivel de volatilidad, el spread y la liquidez.
2. Cambio de esa diferencia desde la captura comparable anterior. Separar cierre–apertura de apertura–apertura; no tratar un fin de semana como una sesión ordinaria.
3. Residuo de paridad entre call y put del mismo strike y vencimiento, expresado en unidades económicas y en múltiplos del ancho de bid/ask. Para SPY, estimar y documentar la prima de ejercicio anticipado o abstenerse de interpretar residuos pequeños.
4. Variables de control: retorno y gap ya observados, volatilidad implícita total, volatilidad realizada reciente, movimiento del mercado, plazo, dividendos y anuncios conocidos.

**Comparaciones incrementales:**

`A = controles de precio y volatilidad` → `B = A + asimetría call/put` → `C = B + cambio diario` → `D = C + residuo de paridad` → `E = D + cuantiles y transporte`.

Mantendremos el mismo algoritmo y una complejidad comparable en cada escalón. Empezaremos con regresión regularizada o cuantílica sencilla; un modelo más flexible entrará solo si mejora los resultados fuera de muestra. Las etiquetas de 5 sesiones se incorporarán al entrenamiento únicamente después de madurar.

**Resultados que se medirán:** Brier o log loss para eventos direccionales, pérdida cuantílica para colas, CRPS cuando se produzca una distribución física completa y desempeño de una política simulada **después de costos**. Informaremos además calibración, rotación, drawdown y rendimiento frente a un benchmark con riesgo comparable. Una mejora de pronóstico no se contará automáticamente como mejora de posición.

## 5. Protección frente a señales falsas

- Usar bid/ask y marcas de tiempo, no tratar mids o volatilidades calculadas por el proveedor como observaciones exactas.
- Revisar sincronía entre opción y subyacente, dividendos y tipo de ejercicio antes de interpretar diferencias call/put. Una diferencia pequeña dentro del costo de negociar no se etiquetará como señal.
- Fijar por adelantado universo, horario, vencimientos, señales, métricas y número de variantes. Reservar un periodo final sin tocar para la evaluación.
- Hacer validación temporal hacia adelante con purga cuando las etiquetas se solapan; estimar incertidumbre con bloques temporales. Reportar todos los experimentos realizados, incluidos los que fallan.
- Distinguir cuatro fuentes de confianza: calidad de datos, sensibilidad a supuestos, calibración predictiva y estabilidad de la decisión. Si fallan datos o ajuste, abstenerse de incrementar una posición basándose en la señal.

## 6. Correcciones previas del núcleo existente

El repositorio de Claude contiene un núcleo matemático y pruebas sobre datos sintéticos; todavía no integra ingestión real ni backtest de mercado. Antes de usarlo como fuente de recomendaciones:

1. Cambiar `cuantiles_desde_densidad` para que no normalice por defecto una densidad con masa faltante ni silencie densidades negativas. Si la cola necesaria no está identificada, devolver estado de «no identificada».
2. Corregir el tratamiento de `alfa >= 1` en conformal adaptativo y volver a comprobar su cota con secuencias límite, además de datos sintéticos aleatorios. No anunciar una garantía que el programa no cumple.
3. Añadir pruebas de cadenas bid/ask con cotizaciones desfasadas, dividendos, strikes ausentes y ventanas de apertura. Las pruebas sintéticas actuales no demuestran validez predictiva ni calidad de datos reales.
4. Conservar como series diferentes los residuos call/put observados y las superficies sin arbitraje ajustadas. Documentar qué observaciones se excluyen y por qué.

## 7. Primer entregable y decisiones pendientes

**Primer entregable:** un informe reproducible de una muestra de sesiones de apertura que muestre, para cada día, las primas y volatilidades call/put comparables, su cambio, el residuo de paridad con su banda bid/ask, la calidad del snapshot y el rendimiento posterior a 1 y 5 sesiones. Después de revisar esa muestra se congelará el protocolo del backtest amplio.

Quedan por fijar el proveedor y presupuesto de datos, el instrumento exacto tras la auditoría de la muestra, las posiciones actuales, la moneda del capital de referencia, los costos y límites de riesgo. Hasta entonces, las salidas de posición serán simulaciones bajo supuestos declarados.

## Referencias para este enfoque

- [Documento técnico de QuantileFlow](QuantileFlow_propuesta_tecnica.pdf) y [repositorio de referencia](https://github.com/hectorcs23/QuantileFlow).
- [Options Industry Council: paridad put–call](https://www.optionseducation.org/advancedconcepts/put-call-parity).
- [Cremers y Weinbaum (2010): diferencias call/put y rendimientos posteriores](https://doi.org/10.1017/S002210901000013X).
- [Wallmeier (2024): errores en volatilidades implícitas por sincronización y dividendos](https://onlinelibrary.wiley.com/doi/10.1002/fut.22495).
