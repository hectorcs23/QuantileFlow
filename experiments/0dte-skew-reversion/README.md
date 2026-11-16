# SPY 0DTE: demostrar o refutar la reversión del skew

**Estado: investigación pendiente de cotizaciones históricas reales. No hay un edge demostrado ni resultados de mercado en esta carpeta.** El módulo analiza CSV locales; no descarga datos, compra suscripciones ni coloca órdenes. Forma parte de las pruebas de QuantileFlow.

Esta hipótesis intradía de SPY 0DTE es adicional al piloto de SPXW con plazo objetivo de 30 días y etiquetas de 1/5 sesiones. Sus datos, señal, horizonte y resultados se mantienen identificados por separado. El CSV de este experimento es un contrato propio; no es una tabla Parquet del piloto ni hay una conversión automática desde la captura actual.

## Qué sería evidencia

La hipótesis tiene dos partes. Primero, una desviación del skew, ajustada por hora, debe predecir convergencia fuera de muestra. Segundo, una posición realizable debe capturar beneficio después de spreads, comisiones, cobertura y financiación. Aprobar sólo la primera parte no demuestra rentabilidad.

Definimos `RR25 = 100 * (IV_put_25_delta - IV_call_25_delta)` en puntos de volatilidad. Las IV de entrada son fracciones anuales: 0.20 significa 20%; nunca introducir 20. Las deltas son firmadas: -0.25 para put, +0.25 para call. No usamos diferencias de primas al mismo strike como señal.

Una desviación baja corresponde a puts relativamente baratos: comprar put y vender call. Una alta invierte los lados. La cobertura con SPY reduce delta, pero conserva gamma, vega, riesgo de salto y error de modelo. El risk reversal tiene una pata corta sin pérdida máxima fija: este experimento no establece tamaño operable ni autoriza decisiones de posición.

## Protocolo previo a ver resultados

1. Guarda `research-config.json`, su hash y una fecha de comienzo de evaluación antes de calcular resultados. Documenta en `data-manifest.json` cualquier revisión o historia ya examinada. Una división cronológica retrospectiva no se convierte en prueba prospectiva por llamarla holdout.
2. Consigue inicialmente unas 60 sesiones anteriores para estimar el patrón horario y al menos 60 sesiones posteriores para evaluación. Es preferible ampliar a distintos regímenes y 6–12 meses posteriores. Estas cantidades son mínimos operativos propuestos, no una garantía estadística. La suficiencia depende también de intervalos de confianza y estabilidad.
3. Reconstruye cotizaciones y Greeks conocidos en cada instante; muestrea cada cinco minutos desde 09:40 ET. Usa el calendario oficial, incluidos cierres a las 13:00. Conserva todas las sesiones previstas, aunque falten datos: el calendario no se debe construir sólo con fechas presentes en los CSV.
4. Interpola IV entre strikes OTM que rodean delta absoluta 0.25; no extrapoles. Normaliza cada franja horaria con media y desviación estándar de las últimas 60 sesiones anteriores, con mínimo 20 observaciones válidas. El día actual y días futuros no entran en su baseline. La regla de actualización está fija; actualizarla con días anteriores de evaluación es aprendizaje secuencial legítimo, no optimización retrospectiva.
5. Congela la regla primaria: entrada con `|z| >= 2`, una posición simultánea, dos contratos en total, selección de strikes en el instante de señal y salida 30 minutos después de la entrada. No reselecciones strikes en cada observación. Desde la señal hasta la salida, reserva el intervalo incluso si después resulta imposible reconstruirlo; no uses la disponibilidad futura para decidir nuevas entradas.
6. Ejecuta el estudio una vez. Cualquier cambio de umbral, horizonte o instrumento después de ver resultados constituye otro experimento y requiere datos nuevos de validación. Los horizontes 15/60 minutos, otros umbrales, eventos y regímenes quedan como extensiones pendientes, no resultados de esta implementación.

## Datos necesarios y formato

La captura de apertura descrita en [la fuente Alpaca](../../docs/fuente_alpaca.md) no acredita una historia completa de cadenas SPY 0DTE cada cinco minutos. Este experimento exige comprobar esa cobertura antes de ejecutarlo. Los agregados OHLC de opciones ni cotizaciones actuales sirven para demostrar este efecto. Verifica la cobertura del proveedor antes de comprar datos.

- `quotes.csv`: una fila por contrato y snapshot. Encabezado exacto en `quotes-template.csv`.
- `calendar.csv`: todas las sesiones oficiales del intervalo con `session_date,close_timestamp`. Encabezado en `calendar-template.csv`.
- `data-manifest.json`: procedencia, cobertura contratada, convenciones y fecha del split. Parte del expediente de investigación; el runner no verifica las declaraciones del manifest.

Todos los timestamps deben ser ISO-8601 con offset explícito o `Z`. `timestamp` es el instante de observación en la cuadrícula; `quote_timestamp`, `greeks_timestamp` y `underlying_quote_timestamp` son tiempos auténticos de los datos disponibles para esa observación. No sustituyas la hora de una cotización vieja por el cierre del intervalo. No uses datos posteriores para calcular IV, delta o selección.

Cada fila incluye símbolo `SPY`, vencimiento local igual al día de sesión, identificador único de contrato, right `P`/`C`, strike, multiplicador 100 y `exercise_style=american`. Bid y ask son USD por acción; sizes son contratos disponibles. `underlying_bid/ask` son USD por acción de SPY. Todas las filas del mismo snapshot deben compartir la misma observación del subyacente.

El prototipo rechaza mercados cruzados, bid cero, tamaños insuficientes, timestamps futuros, quotes de opciones de más de 10 segundos, Greeks de más de 10 segundos y quotes del subyacente de más de 5 segundos. No tolera snapshots duplicados ni datos inconsistentes del subyacente. Esas cifras son decisiones de investigación, no umbrales universales de mercado.

Hay que conservar todos los strikes que pudieran ser elegidos y sus trayectorias posteriores, incluso cuando dejan de estar cerca de 25 delta. Para SPY, usa IV/delta calculadas con un modelo americano consistente con dividendos, tasas y tiempo exacto hasta vencimiento. Si el proveedor usa una aproximación europea, audita su error y regístralo: esa incertidumbre no la resuelve el importador. La paridad europea del texto original es una aproximación para SPY, que permite ejercicio americano.

Un proveedor posible es ThetaData: su documentación describe cotizaciones NBBO históricas y el muestreo por intervalos. Este paquete exige normalización al CSV común y Greeks; no implementa una conexión de proveedor. No asume que exista una suscripción o acuerdo OPRA activo. [Documentación oficial](https://docs.thetadata.us/operations/option_history_quote.html).

## Qué calcula el programa

El OU se aproxima mediante AR(1) de los residuos de skew, con intercepto, usando sólo pares consecutivos intradía separados exactamente cinco minutos. Se reportan entrenamiento y evaluación por separado. Para `0 < beta < 1`, la vida media es `-5 * ln(2) / ln(beta)` minutos; fuera de ese rango no hay vida media OU válida. Es un diagnóstico agrupado: no incluye prueba de estacionariedad ni incertidumbre del parámetro. Una vida media de dos horas, por sí sola, no descarta ni valida rentabilidad.

La prueba de señal mide convergencia a 30 minutos desde la señal: `direction * (residual_futuro - residual_actual)`, donde positivo representa movimiento hacia la media. El baseline del horario futuro usa sólo sesiones anteriores y, por tanto, era calculable al detectar la señal. Este endpoint no es el precio de salida de la operación, que ocurre cinco minutos más tarde por la demora de entrada.

El replay opera contratos reales elegidos en la señal, no las IV interpoladas. Entra cinco minutos después; compra al ask y vende al bid, con slippage adverso adicional. La cobertura inicial usa las deltas de la señal y se ejecuta en la entrada; las siguientes coberturas usan deltas del snapshot anterior. Redondea acciones de SPY a enteros. Sale 30 minutos después de entrar y liquida también las acciones. No sustituye una pata cuando falta su cotización.

Supuestos de costos, congelados en config: USD 0.65 por contrato por lado, USD 0.005 por acción negociada, USD 0.01 por acción de slippage adicional en cada ejecución de opciones y SPY, financiación de saldo deudor al 5% anual y préstamo de acciones cortas al 3%. Son supuestos, no tarifas verificadas de tu broker. El estrés duplica el slippage adicional; mantiene los spreads observados. Sustitúyelos por costos de tu cuenta antes de congelar una prueba nueva.

La theta y los cambios de gamma/volatilidad ya aparecen en los precios sucesivos de las opciones. No se vuelve a restar una theta teórica. Los Greeks se usan para señal y cobertura, no para inventar precios históricos.

Se agregan resultados por sesión incluyendo días sin señales y se calcula un intervalo aproximado del 95% con bootstrap circular de bloques de diez sesiones, 3,000 repeticiones y semilla fija. Esto evita tratar muchas observaciones intradía como independientes. El intervalo de convergencia pondera por igual cada sesión activa. Se necesitan al menos dos bloques; los intervalos no corrigen selección de parámetros ni prueban causalidad.

Si cualquier operación intentada queda sin trayectoria completa, la rentabilidad total y su intervalo se publican como `null`. El P&L del subconjunto cubierto se etiqueta explícitamente. Las ausencias no se contabilizan como operaciones con cero beneficio. Si faltan endpoints de señal, tampoco se publica un intervalo confirmatorio de convergencia.

## Cómo correrlo

Desde la raíz de QuantileFlow, con Python 3.11+ y base horaria IANA disponible (`tzdata` en Windows):

```powershell
python -m pytest -q tests/test_0dte_skew_reversion.py
```

Después de preparar datos reales y fijar el split, reemplaza `FECHA_FIJADA_YYYY-MM-DD`:

```powershell
python experiments/0dte-skew-reversion/run_study.py --quotes experiments/0dte-skew-reversion/data/quotes.csv --calendar experiments/0dte-skew-reversion/data/calendar.csv --evaluation-start FECHA_FIJADA_YYYY-MM-DD --out experiments/0dte-skew-reversion/results/run-01
```

Se generan `report.json` (diagnósticos, costos, cobertura, gates y hashes), `signals.csv` (RR, baseline, z y patas), `trade-ledger.json` (cada intento y trayectoria de cobertura) y `daily-results.json` (sesiones con y sin señales). Guarda el manifest con los resultados y conserva los archivos originales. `data/`, `results/` y cachés de Python están excluidos de Git localmente. Las 16 pruebas también se incluyen en `make test` mediante `tests/test_0dte_skew_reversion.py`.

## Cómo interpretar y decidir

| Resultado | Lectura |
| --- | --- |
| Skew sin convergencia fuera de muestra | La regla probada no muestra reversión explotable. |
| Convergencia positiva, P&L neto sin evidencia positiva | Hay señal estadística, pero no se demuestra beneficio capturable. |
| Faltan datos o los intervalos incluyen cero | Resultado inconcluso; no significa que se haya probado inexistencia de edge. |
| Convergencia y P&L base/estrés con límites inferiores > 0, suficiente cobertura | Candidato para una prueba prospectiva con fills observados. |

El gate automatizado exige 60 sesiones de evaluación, 20 activas, cobertura RR de al menos 95%, todas las operaciones intentadas reconstruidas y límites inferiores positivos en convergencia y P&L base/estrés. Estos mínimos son reglas previas propuestas; superar el gate no equivale a aprobar trading. Se debe revisar cobertura por régimen y día, influencia de las mejores operaciones, pérdidas extremas, exposición y capital/margen necesario. Esas revisiones todavía son manuales.

El siguiente paso después de un resultado favorable es registrar prospectivamente órdenes simuladas y fills observables con reglas congeladas, comparar ejecución contra el replay y repetir el análisis. Hasta entonces esta señal no alimenta decisiones automáticas de QuantileFlow. El prototipo tampoco modela margen del broker, profundidad del subyacente, ejecución parcial, excursiones dentro de cinco minutos, impuestos, interés positivo de efectivo ni stops intradía.

## Fuentes y precisión del argumento original

- Bollen & Whaley (2004), *Does Net Buying Pressure Affect the Shape of Implied Volatility Functions?*, Journal of Finance 59(2), 711–753: documenta relación entre demanda e IV y cambios transitorios. No demuestra inviabilidad de este experimento moderno 0DTE después de costos. [PDF del autor](https://www.whaley.info/_files/ugd/1362e1_81f94ba850fb4ec4aea173770b355408.pdf).
- Muravyev & Pearson (2020), *Option Trading Costs Are Lower Than You Think*, RFS 33(11), 4973–5014: los costos dependen de cómo se ejecuta. Aquí no suponemos fills a mid; la prueba de execution timing del artículo tampoco garantiza nuestros fills. [Publicaciones del autor](https://www.dmurav.com/).
- [Cboe: diferencias de ejercicio y liquidación entre SPY y XSP](https://ir.cboe.com/news/news-details/2013/CBOE-To-Introduce-Mini-SPX-Options-With-PM-Settlement-On-November-5-10-29-2013/default.aspx). SPY americano y entrega física; no transferir automáticamente resultados de SPX europeo.
- [CFA Institute: paridad europea](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/option-replication-using-put-call-parity). La fórmula exacta depende del tipo de ejercicio y carry.

Las pruebas unitarias usan mercados sintéticos para verificar contabilidad, reloj y ausencia de look-ahead. Ninguna representa evidencia de rentabilidad de mercado.
