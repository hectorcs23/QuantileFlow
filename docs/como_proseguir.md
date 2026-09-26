# QuantileFlow: cómo proseguir después del avance

**Fecha:** 26 de septiembre de 2026.  
**Base:** `avance_y_pendientes.md`, que reporta trabajo hasta el commit `0ad6e2b` de `claude/compassionate-brown-1w9f90`.  
**Alcance:** continuación del plan previo. El estado del código y las 114 pruebas se toman del informe recibido; este documento no constituye una nueva auditoría de esa versión.

## 1. Decisión principal

El siguiente hito es **producir un informe reproducible de sesiones reales de apertura**, con señales call/put, calidad de los datos y rendimientos posteriores. Las correcciones reportadas permiten avanzar hacia ese hito. Primero necesitamos comprobar qué sobrevive cuando las cotizaciones provienen del mercado.

El entregable inmediato debe contestar:

1. ¿Podemos medir de forma consistente la asimetría entre calls y puts a una hora determinada?
2. ¿Cuánto cambia esa medición al modificar razonablemente los supuestos de cotización, forward e interpolación?
3. ¿Qué cambia entre sesiones y qué parte se explica por el movimiento ya observado del subyacente?
4. ¿Tenemos suficiente historia y calidad para hacer una prueba predictiva defendible?

Una muestra piloto sirve para validar medición e ingestión. La existencia de señal predictiva se evaluará después, en un periodo distinto.

## 2. Qué ya podemos dar por avanzado y qué queda abierto

Según el informe, ya se corrigieron los cuantiles con masa faltante, el conformal adaptativo y la separación entre cotizaciones observadas y superficie ajustada. También se incorporaron controles de cadena y comparaciones de paridad y asimetría. El próximo trabajo debe reutilizar esas piezas y verificar su integración con una muestra real.

| Necesidad | Cuándo se requiere | Acción |
|---|---|---|
| Acceso a una muestra histórica y condiciones de uso | Antes de procesar datos reales | Revisar primero accesos existentes y muestras disponibles. Obtener una cotización si hace falta comprar; no asumir una suscripción. |
| Instrumento y convención de vencimiento | Antes de congelar el piloto | Usar SPXW con liquidación PM como candidato inicial; confirmar disponibilidad y calidad. |
| Posiciones actuales y moneda del capital | Antes de gestionar exposición | No bloquean la ingestión ni la evaluación de señales. |
| Costos y límites personales de riesgo | Antes de evaluar una política de posición | Durante la investigación se pueden documentar escenarios de costos; no equivalen a parámetros aprobados para operar. |
| Umbrales de calidad | Antes de cerrar la muestra piloto | Revisarlos con el piloto y congelarlos antes del periodo de evaluación. |

Mientras se resuelve el acceso a datos se puede construir el adaptador de archivos, el almacenamiento, el generador de etiquetas y la plantilla de informe con las capturas sintéticas existentes.

## 3. Diseño propuesto del piloto

| Elemento | Configuración inicial propuesta |
|---|---|
| Opciones | SPXW con liquidación PM y ejercicio europeo. No mezclar con contratos de liquidación AM. |
| Hora principal | 09:45, zona `America/New_York`, con calendario de sesiones real. |
| Hora secundaria | 10:00, solo para diagnosticar estabilidad de medición; no elegir retrospectivamente la hora con mejor retorno. |
| Horizonte de opciones | Objetivo de 30 días calendario. Usar vencimientos que lo encierren; marcar indisponible cuando no pueda interpolarse de forma válida. |
| Tamaño del piloto | Entre 20 y 40 sesiones históricas, incluyendo condiciones variadas cuando la muestra lo permita. Este tamaño no valida rentabilidad. |
| Objetivo posterior principal | Rendimiento del índice entre 09:45 de una sesión y 09:45 de la siguiente. |
| Objetivo secundario | Rendimiento a la misma hora cinco sesiones después. |
| Señal principal | Cambio diario de la asimetría de volatilidad implícita entre call y put a delta comparable. |
| Señales secundarias | Asimetría a distancia logarítmica comparable y residuos de paridad. |

SPXW simplifica la primera prueba porque las opciones son europeas y tienen liquidación PM. Los horarios y el instante contractual de liquidación deben venir de las especificaciones y del calendario, incluidos los cierres anticipados. El plazo se calculará desde el corte hasta ese instante, con una convención de año explícita. [Especificaciones de Cboe](https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications).

Si el acceso disponible favorece claramente SPY, se puede cambiar el instrumento antes del piloto. En ese caso, dividendos, ejercicio anticipado y sensibilidad de la conversión americana pasan a ser requisitos de medición. No se mezclarán observaciones SPXW y SPY en una sola serie.

Los retornos de SPX son etiquetas de investigación. SPX no es un activo que se pueda comprar directamente; una política posterior sobre SPY o futuros necesitará precios de ejecución, costos, dividendos y diferencias respecto del índice propios de ese instrumento.

## 4. Bloque de trabajo A: asegurar el dato

### A1. Congelar una versión de referencia

- Obtener la rama remota que contiene los cambios reportados y registrar su commit completo. Preservar los documentos locales existentes.
- Ejecutar una vez la batería de pruebas en un entorno reproducible y registrar versiones y resultado. Si aparecen fallos, resolverlos antes de integrar datos.
- Guardar la configuración del piloto con un identificador de versión. No editar manualmente los resultados generados.

### A2. Contrato de datos y adaptador

El contrato debe incluir identificador del contrato, raíz, strike, tipo call/put, ejercicio, liquidación, vencimiento exacto, multiplicador, bid/ask y tamaños. También debe especificar la fuente del subyacente, tasas, timestamps y significado de cada campo.

Guardar los tiempos en UTC y convertir a Nueva York para calendario y presentación. Distinguir:

- hora del evento o actualización de la cotización;
- hora del snapshot suministrado por el proveedor;
- hora de disponibilidad histórica documentada, cuando exista;
- hora de descarga o recepción local.

La hora de descarga actual no demuestra cuándo estuvo disponible un dato histórico. Si el proveedor ofrece snapshots sin la hora de última actualización, no inventar una edad de cotización. Marcar esa limitación y evaluar si afecta la pregunta de apertura.

Un producto candidato es Cboe DataShop Option Quotes, que documenta snapshots NBBO, tamaños y datos por intervalos. Antes de elegirlo hay que confirmar la entrega del nivel del índice, los timestamps, la cobertura concreta y el precio; no asumir que todo viene incluido. Tampoco confundir un histórico entregado con retraso con un feed apto para decidir en tiempo real. [Descripción oficial del producto](https://datashop.cboe.com/option-quote-intervals).

### A3. Almacenamiento y replay

Propuesta mínima:

```text
data/raw/             archivos originales inmutables, fuera de Git
data/normalized/      contratos y cotizaciones normalizados en Parquet
data/labels/          resultados posteriores con su fecha de disponibilidad
configs/              configuración del piloto y reglas versionadas
reports/piloto/       informe, tabla diaria y gráficas
tests/fixtures/       muestras pequeñas o anonimizadas permitidas por la licencia
```

Cada corrida debe registrar hashes de archivos, proveedor, fecha de descarga, corte, commit, parámetros y exclusiones. Reprocesar el mismo snapshot con la misma configuración debe producir las mismas señales, estados y motivos.

**Salida de A:** una cadena real se puede leer, filtrar, procesar y reproducir desde sus archivos originales. Los datos recibidos después del corte no cambian esa corrida.

## 5. Bloque de trabajo B: medir sin borrar la señal

### B1. Revisar los controles provisionales

El límite de 60 segundos de edad, la ventana inicial de cinco minutos y el spread de 50 % del mid son parámetros provisionales. Revisarlos con el piloto por rango de precio y liquidez. Un spread relativo se vuelve enorme en opciones casi sin valor; registrar también ancho absoluto y ticks.

Medir por sesión: filas recibidas, utilizables, excluidas por motivo, pares completos, vencimientos, cobertura de strikes, amplitud bid/ask, sincronía y disponibilidad de cada señal. Mantener separado el conjunto apto para residuos de paridad del conjunto que solo proporciona cotas para ajustar una superficie; un bid cero puede seguir aportando una cota superior mediante el ask.

### B2. Fijar convenciones y signos

Definir una sola convención de delta para el piloto. Propuesta europea: delta respecto del forward sin descuento, `N(d1)` para calls y `N(d1) − 1` para puts. Si se usan deltas del proveedor, comprobar su definición antes de interpolar.

Definir `RR25 = IV(call delta +0.25) − IV(put delta −0.25)`. Un valor positivo significa mayor volatilidad implícita del call comparable; no equivale por sí mismo a una probabilidad de subida. La señal principal será `RR25 hoy − RR25 sesión anterior`, calculada con igual horario y plazo.

Para la segunda comparación, usar `K+ = F × 1.03` y `K− = F / 1.03`. El strike inferior está aproximadamente a −2.91 % del forward: nombrarlo «distancia logarítmica simétrica», no «±3 % simple».

La identidad de precios simétricos mencionada en el avance sirve como referencia bajo los supuestos de simetría correspondientes. No es una identidad universal impuesta por la paridad en mercados con sonrisa asimétrica. Documentar la hipótesis de referencia y comprobarla con el caso sintético apropiado.

### B3. Separar discrepancias locales de desplazamientos comunes

Estimar el forward dejando fuera el par evaluado evita que ese par ajuste su propio residuo. Sin embargo, un desplazamiento común de todos los pares puede ser absorbido por el forward estimado. El hallazgo del dividendo omitido del informe demuestra por qué importa esto.

Guardar por separado:

1. residuo local de cada par respecto del forward estimado con los otros pares;
2. nivel y cambio del forward implícito;
3. discrepancia frente a una referencia externa coherente, si se dispone de ella, con sus propias incertidumbres.

No presentar el primer residuo como una medida de toda la información direccional. Tampoco estimar libremente una tasa por sesión a partir de pocos strikes sin registrar su estabilidad; comparar contra una curva externa cuando esté disponible.

La paridad será inicialmente un diagnóstico de calidad y una señal secundaria. La hipótesis principal del piloto será la evolución de la asimetría.

### B4. Ajuste de superficie

Probar una pérdida robusta frente a la actual únicamente para resolver el problema observado de cotizaciones desviadas. Comparar ajuste dentro de spreads, estabilidad de cuantiles, convergencia y restricciones de arbitraje. Una pérdida robusta no sustituye los filtros de datos y podría ocultar un movimiento real localizado; conservar y mostrar los residuos originales.

**Salida de B:** señales con definición estable, signo explícito, soporte suficiente y sensibilidad cuantificada. Una señal no identificada se conserva como ausente; no se rellena para completar la tabla.

## 6. Bloque de trabajo C: etiquetas e informe por sesión

Construir etiquetas de 1 y 5 sesiones a partir del calendario bursátil, con la misma hora inicial y final. Por ejemplo, una observación del viernes termina en la siguiente sesión hábil, no necesariamente el lunes. Si falta el precio final, dejar la etiqueta ausente.

Guardar `decision_at`, `label_end_at` y `label_available_at`. El generador puede calcular etiquetas históricas para evaluación, pero el entrenamiento y la calibración solo pueden consultar las que ya habrían madurado en la fecha simulada. El instante de ejecución de una futura estrategia debe ser posterior al cálculo y a la latencia supuesta.

El informe piloto contendrá:

- Tabla diaria: calidad, forward, RR25, cambio de RR25, asimetría logarítmica, residuos de paridad, bandas de sensibilidad y etiquetas posteriores.
- Gráfica de disponibilidad y causas de exclusión por sesión.
- Gráfica de asimetría y cambios con bandas, junto con el movimiento ya ocurrido del subyacente.
- Comparación 09:45–10:00 como diagnóstico de estabilidad.
- Ejemplos de sesiones normales y problemáticas, con las cotizaciones que explican el resultado.
- Dictamen de datos: «apto para ampliar historia», «apto con limitaciones» o «insuficiente», y motivos verificables.

**Salida de C:** reporte reproducible de 20–40 sesiones y una lista concreta de limitaciones. Cualquier relación visual con retornos será exploratoria; no se declarará capacidad predictiva a partir de este piloto.

## 7. Después del piloto: protocolo predictivo pequeño

Antes de ampliar el estudio, fijar por escrito la señal principal, un objetivo principal, familias de modelo, ventanas, métricas, costos si aplican y criterios de éxito. Propuesta: cambio de RR25 para predecir el signo del retorno a una sesión, con Brier como métrica principal. El horizonte de cinco sesiones y el riesgo de cola quedan como análisis secundarios explícitos.

Comparar gradualmente:

| Variante | Información disponible |
|---|---|
| A | Retornos pasados, gap, volatilidad reciente y controles de calendario. |
| B | A más volatilidad implícita ATM y plazo. Controla si el beneficio proviene del nivel general de volatilidad. |
| C | B más nivel de asimetría. |
| D | C más cambio de asimetría e innovación respecto de controles contemporáneos. |
| E | D más residuo de paridad, cuando sea identificable. |
| F, posterior | E más cuantiles y transporte. |

Mantener la misma familia de predicción y presupuesto de ajuste en las comparaciones. Usar particiones temporales, etiquetas maduras y un periodo final reservado. Calcular intervalos del diferencial de pérdidas con bloques y declarar todas las variantes probadas.

La estimación de unas 50 observaciones independientes por año a cinco sesiones es una heurística para rendimientos solapados bajo supuestos sencillos. No determina automáticamente el tamaño efectivo de Brier o de cualquier otro estadístico. Evaluar la dependencia de la serie de pérdidas y estimar qué efecto mínimo se puede detectar con la historia disponible.

Un resultado puede ser: mejora direccional, mejora exclusiva de riesgo, evidencia insuficiente o ausencia de mejora detectable. Ninguno obliga a incorporar otro modelo. El transporte se mantiene como comparación posterior; la aceleración se añade solo si el cambio diario resulta estable y útil.

## 8. Orden de implementación y criterio de cierre

| Prioridad | Entregable | Se considera terminado cuando… |
|---|---|---|
| P0 | Versión y entorno reproducibles | El commit está identificado y la batería existente tiene resultado registrado. |
| P0 | Contrato, adaptador y almacenamiento | Una captura real se conserva y reprocesa sin cambios silenciosos. |
| P0 | Etiquetas de 1 y 5 sesiones | Calendario, ausencias y disponibilidad temporal están comprobados. |
| P0 | Informe piloto | Incluye sesiones reales, exclusiones y sensibilidad; todas las cifras se remontan a sus datos. |
| P1 | Ajuste robusto | Mejora el problema observado sin degradar restricciones ni ocultar residuos. |
| P1 | Protocolo e historia ampliada | Hipótesis y evaluación están fijadas antes de mirar el periodo reservado. |
| Posterior | Transporte, conformal y posición | Cada bloque responde a una necesidad demostrada y tiene evaluación propia. |

La aceleración de árboles americanos se priorizará solo si se elige SPY y la latencia medida lo exige. BOCPD, conjuntos de modelos, optimización robusta y conexión a un bróker quedan para después del informe y la evaluación predictiva.

Cuando se incorpore conformal, además de cobertura se mostrarán ancho y proporción de intervalos vacíos o infinitos. Una garantía promedio con intervalos poco informativos no basta para recomendar una posición.

**Próxima entrega esperada:** informe piloto, tabla diaria exportable, configuración congelada, registro de calidad y recomendación fundada sobre si ampliar la historia. Las decisiones personales de cartera se solicitan al entrar en la fase de posición.

## Fuentes y alcance

- [Avance recibido](avance_y_pendientes.md): fuente del estado reportado y de los hallazgos sintéticos.
- [Plan previo](plan_de_trabajo.md): arquitectura y fases de investigación que este documento concreta.
- [Cboe: especificaciones SPX/SPXW](https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications): ejercicio, vencimientos y liquidación.
- [Cboe DataShop: Option Quotes](https://datashop.cboe.com/option-quote-intervals): candidato de datos que requiere confirmar cobertura y contratación.

Los tamaños del piloto y las configuraciones iniciales son propuestas de trabajo. No se han contratado datos ni validado señales de mercado mediante este documento.
