# Metodología: BTC Prediction Market Lab

Documento de diseño recibido el 2026-10-14, conservado **sin modificar** como referencia del
encargo. El estado de cumplimiento de cada paso está en `README.md`; las desviaciones y lo que las
motivó, en `capabilities.md` y `docs/limitaciones.md`.

Las cifras de configuración propuestas son hipótesis de ingeniería para simulación, no parámetros
que hayan demostrado rentabilidad ni recomendaciones de inversión.

---

## 1. Objetivo y alcance

Construir una herramienta que estime la distribución del valor de liquidación de BTC, la
probabilidad de cada resultado y su incertidumbre. Comparar esa estimación con el coste ejecutable
de YES y NO y calcular un presupuesto de pérdida, incluida la decisión de no operar.

La hipótesis que debe poder rechazarse es: «La información disponible en el momento de decidir
permite obtener una ventaja sobre el precio ejecutable, después de costes y retrasos». No establecer
metas de acierto, beneficios diarios ni ingresos garantizados.

Empezar con un solo mercado de BTC de 15 minutos y un solo proveedor de ejecución. Los contratos
diarios serán una segunda investigación con entrenamiento, calibración y evaluación separados. Para
ambos, el horizonte es el tiempo restante hasta el vencimiento concreto, no siempre 15 minutos o 24
horas.

MVP: datos, modelos, replay y simulación; sin órdenes reales. Claude utiliza el conector para
inspeccionar fuentes, recuperar datos y desarrollar el proyecto según sus capacidades verificadas.
Un conector no implica acceso a ticks, histórico, cotizaciones ejecutables ni ejecución de órdenes.

## 2. Paso 1: auditar el conector y fijar el contrato

Crear `capabilities.md` con proveedor, herramientas disponibles, permisos, autenticación, histórico
accesible, resolución, rate limits, licencias, restricciones y ejemplos de respuestas. No registrar
secretos. Si el conector solo accede al repositorio, documentarlo: no proporciona por sí solo datos
financieros.

Seleccionar un contrato real y guardar una ficha versionada:

- Plataforma visible, exchange subyacente, identificadores de serie/evento/contrato y moneda.
- Apertura, fin de negociación, vencimiento y liquidación; UTC como referencia, con zona IANA para
  la presentación y cambios de horario.
- Pregunta, umbral, operador exacto (`>`, `>=`, rango, etc.), tratamiento del empate, cancelaciones
  y resultados excepcionales.
- Índice de referencia, muestreo, promedio o ventana que determina el resultado y reglas de
  revisiones.
- Pago de YES/NO, tick, cantidad mínima, fracciones permitidas y horarios.
- Comisiones del intermediario y exchange, redondeos, posibles costes de liquidación y fecha de
  vigencia.

No asumir que todos los contratos de Robinhood son Kalshi. Usar cotizaciones de otro proveedor solo
tras verificar equivalencia de contrato, índice, ventana, umbral y reglas; aun entonces, la
ejecución y los costes de Robinhood requieren evidencia propia.

**Entrega:** ficha con fuentes oficiales, fecha de consulta y ejemplo de liquidación reproducido. Si
una regla esencial falta, el estado es `RULES_UNVERIFIED` y el tamaño es cero.

## 3. Paso 2: capturar datos que existían en ese momento

Separar cuatro conjuntos:

1. Índice que determina la liquidación, preferentemente con la resolución requerida por el contrato.
2. BTC spot de una o más fuentes como variables explicativas: precio, retornos, volumen y, si
   existe, flujo de órdenes.
3. Mercado de predicción: bid/ask de cada lado, cantidades, profundidad, operaciones y cambios de
   estado.
4. Resultado oficial, valor de liquidación, versión de reglas y calendario de comisiones.

Guardar para cada observación `event_time`, `received_at`, fuente, contrato, secuencia, unidad y
payload original. Para variables derivadas o revisadas, guardar también cuándo estuvieron
disponibles. Usar decimales o enteros escalados para dinero.

Realizar uniones temporales hacia atrás usando la información recibida antes de decidir. Un mensaje
con timestamp antiguo recibido después no estaba disponible. No rellenar huecos con datos futuros;
no utilizar velas aún abiertas como si ya estuvieran cerradas.

Guardar snapshots y deltas del libro y reconstruirlo solo con secuencias completas. Tras
desconexiones, exigir un nuevo snapshot válido. Registrar huecos, latencia, desalineación de relojes
y revisiones. Conservar la versión observada del índice junto a la revisada, si existe.

No confundir histórico de velas u operaciones con histórico completo del libro. Si falta el libro
histórico, entrenar la predicción con lo disponible y comenzar captura prospectiva. No afirmar
rentabilidad ejecutable basada solo en velas de BTC.

**Entrega:** diccionario de datos y reporte de cobertura por día/contrato, antigüedad de
cotizaciones, huecos y diferencias entre spot e índice. Datos sintéticos solo para comprobar
funcionamiento, identificados como tales.

## 4. Paso 3: definir objetivo y momento de decisión

Definir `Y=1` cuando YES liquida a $1 conforme a sus reglas; `Y=0` cuando liquida a $0.
Cancelaciones o pagos especiales se registran aparte y el simulador aplica su flujo de caja real. No
convertirlos arbitrariamente en pérdidas ni borrarlos del registro.

Definir `V_T` como el valor de referencia utilizado en la liquidación. Si el contrato usa un
promedio final, el objetivo es ese promedio. Si compara promedios de apertura y cierre, reproducir
ambos.

Propuesta inicial para el experimento: una observación y una entrada máxima por contrato, 60
segundos después de abrir; mantener hasta liquidación. Es una elección para reducir grados de
libertad, no una señal validada. Confirmar que el umbral ya se conoce, existe libro válido y todavía
se puede negociar. Descartes se registran con motivo.

No escoger retrospectivamente el mejor minuto. Una futura estrategia dinámica requiere otro
experimento, evaluación agrupada por contrato y control del riesgo acumulado de entradas sucesivas.

## 5. Paso 4: empezar con referencias simples

Comparar como máximo estos candidatos iniciales:

- **Referencia de mercado:** punto medio bid/ask de YES cuando sea coherente, acompañado del spread.
  Es una referencia de evaluación aproximada, no una probabilidad verdadera ni un precio de
  ejecución. Incluir no operar como referencia económica.
- **Modelo del subyacente:** simulación sencilla de trayectorias a partir de volatilidad reciente y
  retornos históricos condicionados por régimen. Empezar sin drift; justificar cualquier tendencia
  con validación.
- **Modelo supervisado simple:** regresión logística regularizada con distancia al umbral, tiempo
  restante, volatilidad, retornos y variables de liquidez disponibles.

Primero comprobar estos modelos. Añadir un único candidato más complejo solo si la validación
demuestra una carencia concreta; registrar cada variante probada. Una extensión posible es corregir
la probabilidad de mercado mediante `logit(p)=logit(p_market)+g(features)`, comparándola con usar el
mercado sin corrección.

Variables iniciales: distancia logarítmica al umbral normalizada por volatilidad y raíz del tiempo;
volatilidad realizada en ventanas predefinidas; retornos recientes; spread; profundidad e imbalance
si están disponibles; diferencia spot/índice; hora y día. Los periodos son hiperparámetros
documentados. Todos los escaladores se ajustan exclusivamente con entrenamiento.

Para obtener rangos de precio, simular trayectorias completas y aplicarles la regla de liquidación.
Un modelo normal puede servir de referencia, pero comprobar colas, saltos y cambios de volatilidad.
Un clasificador por sí solo no produce intervalos de precio.

**Entrega:** especificación de variables, modelos, supuestos y límites. Claude implementa los
cálculos; no inventa probabilidades mediante una respuesta de lenguaje natural.

## 6. Paso 5: distinguir precio, probabilidad e incertidumbre

Publicar tres objetos distintos:

1. Cuantiles de `V_T` e intervalos de predicción centrales del 50%, 80% y 95%.
2. Probabilidad calibrada `p_yes` y `p_no=1-p_yes` para resultados binarios ordinarios.
3. Banda aproximada `[L,U]` que refleje incertidumbre de estimación de `p_yes`, con método y
   supuestos visibles.

Calibrar con un tramo cronológico posterior al entrenamiento y anterior a la validación; empezar con
calibración sigmoide. No recalibrar con resultados aún desconocidos. Comprobar cobertura de
intervalos y calibración por probabilidad, volatilidad y tiempo restante; agrupar rangos con pocas
observaciones.

Para la banda de probabilidad, usar remuestreo por bloques temporales, reajustando modelo y
calibrador con datos anteriores a la decisión. Elegir longitud de bloque según dependencia en
entrenamiento. Reportar sensibilidad y cobertura empírica cuando sea medible; la dispersión entre
modelos o simulaciones no es automáticamente un intervalo de confianza válido. Tampoco puede
observarse directamente la «probabilidad verdadera» de un único evento.

La banda es aproximada, está condicionada a supuestos y puede fallar con cambios de régimen. No
implica que una operación individual vaya a ganar con un nivel de confianza del 95%.

Para una regla conservadora, definir `p_robust_yes=L` y `p_robust_no=1-U`. No utilizar `1-L` como
probabilidad conservadora de NO. Si no se puede estimar la incertidumbre de forma defendible,
mostrar la limitación y mantener el tamaño monetario desactivado.

## 7. Paso 6: medir ventaja con precios ejecutables

Para un lado y una cantidad `n`, definir:

```text
A(n) = coste de comprar n contratos al libro ejecutable
F(n) = comisiones y cargos aplicables a esa orden/cantidad
C(n) = A(n) + F(n)
EV(n) = n * p_robust - C(n)              # pago $1/$0, sin otros cargos
c(n) = C(n) / n
edge(n) = p_robust - c(n)
```

Cuando existan cargos o pagos especiales, usar los flujos de caja de cada resultado, en lugar de
forzar estas fórmulas. Mostrar EV central y EV conservador; «conservador» no garantiza una cota del
beneficio real.

Comprar YES al ask de YES y NO al ask de NO. Si una API solo devuelve bids, derivar asks
complementarios únicamente según la estructura documentada de esa plataforma. No asumir que
`ask_no=1-ask_yes`.

Simular profundidad, cantidad y redondeos de comisiones. El spread ya está incorporado al comprar al
ask: no sumarlo otra vez como coste independiente. Igualmente, no duplicar slippage si se usa el
libro posterior al retraso para simular el fill.

La señal es elegible solo si su EV conservador supera un margen operativo predefinido y se cumplen
los filtros de calidad. Ese margen se fija antes de la prueba final y su sensibilidad se presenta
sin elegir a posteriori la variante ganadora.

No operar cuando las reglas o costes estén sin verificar, falte cobertura crítica, haya secuencias
rotas, quotes caducadas, liquidez insuficiente, datos fuera del dominio validado o límites de riesgo
agotados.

## 8. Paso 7: convertir ventaja en presupuesto de pérdida

Definir `B` como capital segregado para esta estrategia; no como patrimonio total ni poder de compra
con crédito. Falta de presupuesto configurado implica tamaño monetario cero. En investigación se
puede usar un capital ficticio explícito.

Para coste unitario constante `0<c<1`, pago $1/$0 y probabilidad conservadora `p`, Kelly completo
asigna como fracción de capital comprometido:

```text
f_full = max(0, (p-c)/(1-c))
f_candidate = alpha * f_full
```

`alpha=0.25` puede ser un punto de partida de simulación, no una recomendación personalizada. No
usar esta aproximación sin ajustar cuando los costes cambien con la cantidad.

Con libro y comisiones no lineales, evaluar cantidades discretas. Para una posición aislada, sin
exposición previa y con capital libre `B`, maximizar como referencia:

```text
G(n) = p * log((B-C(n)+n)/B) + (1-p) * log((B-C(n))/B)
```

Incluir `n=0`; exigir patrimonio positivo en ambos resultados; aplicar reducción fraccionada y
recalcular costes exactos. Si existen posiciones relacionadas, se requiere evaluación conjunta por
escenarios: la fórmula aislada no basta.

El tamaño final debe respetar simultáneamente coste total, capital disponible, pérdida máxima por
operación, pérdida diaria restante, exposición abierta, liquidez y concentración. Para el MVP, una
sola posición abierta reduce el problema de correlación; los contratos diarios se incorporan después
con límites conjuntos de exposición BTC.

Implementar límites configurables con valores iniciales de simulación claramente etiquetados. No
mostrar una cifra personal hasta recibir el presupuesto y límites del usuario. Antes de validación,
separar `suggested_live_amount=0` de `simulated_amount`.

La pérdida máxima de una compra binaria mantenida a vencimiento es el coste total comprometido
cuando el contrato pierde. Un stop de P&L no asegura salida ni limita por sí solo esa pérdida. Al
alcanzar el límite diario, bloquear nuevas entradas; contabilizar pérdidas realizadas y riesgo
máximo de posiciones abiertas, con zona de reinicio definida. No aumentar tamaño para recuperar
pérdidas.

## 9. Paso 8: evaluar sin información futura

Construir una separación cronológica: entrenamiento, calibración, validación para selección y un
tramo final intacto. Fijar las fechas según cobertura y regímenes disponibles, antes de ajustar
candidatos. No repartir filas al azar.

Durante el desarrollo utilizar walk-forward: entrenar solo con pasado, calibrar con pasado más
reciente y evaluar el siguiente bloque. Purgar observaciones cuyos periodos de resultado o
disponibilidad invadan el tramo siguiente; establecer separación temporal según horizonte y
publicación de etiquetas. Documentar ventanas de variables y dependencia residual.

Mantener todas las observaciones de un contrato en el mismo grupo. Los contratos y señales dentro de
un día pueden estar correlacionados; estimar incertidumbre por días o bloques más largos si la
dependencia lo exige. Miles de ticks no equivalen a miles de apuestas independientes.

Congelar modelo, variables, calibrador, momento de entrada, filtros, umbral de ventaja y límites
antes de abrir el test final. Registrar todos los ensayos; limitar candidatos y controlar selección
múltiple. Si el resultado final falla y se modifica la estrategia, se necesita nueva evidencia
futura; el test anterior pasa a desarrollo.

Métricas de predicción: Brier, log loss, calibración y cobertura/ancho de intervalos, comparadas con
referencias sobre las mismas observaciones. Acierto direccional es secundario.

Métricas económicas: P&L neto, retorno sobre capital, pérdidas máximas, drawdown, costes, rotación,
concentración, cobertura de señales, operaciones descartadas y beneficio medio por contrato.
Reportar los días sin operaciones. Mostrar conteos de días, contratos y número efectivo de
observaciones, además de incertidumbre agrupada.

## 10. Paso 9: replay de ejecución realista

Reproducir en orden de disponibilidad: mensaje recibido, decisión, cálculo, retraso, orden simulada,
fill y liquidación. Registrar versiones de modelo/datos/configuración para poder repetirlo.

Para una compra agresiva simulada, usar el libro que habría estado disponible a la llegada de la
orden y consumir profundidad. Si se especifica límite y el precio ya lo supera, no ejecutar.
Contemplar fills parciales, órdenes rechazadas, falta de datos y saldo inmovilizado hasta que los
fondos sean reutilizables. Una orden limitada no garantiza ejecución.

Para el MVP no simular órdenes pasivas con supuestos optimistas de cola. No rellenar al midpoint, al
último trade ni al mejor precio de toda la vela.

Medir por separado latencia de datos, cálculo y acción humana. En operación manual por Robinhood,
usar distribución de retrasos observados en ese flujo; las latencias de una API distinta no son
equivalentes. Si aún no hay mediciones, ensayar escenarios explícitos y marcar la conclusión como
provisional.

Realizar estrés predefinido: retrasos mayores, menor profundidad, costes superiores, saltos y
sesiones de alta volatilidad. No excluir días malos de manera retrospectiva. La ausencia de
histórico ejecutable impide afirmar una ventaja ejecutable.

## 11. Paso 10: criterios de avance y simulación prospectiva

Escribir el protocolo y los criterios antes de la prueba final. Evaluar al menos:

- Reglas, costes y datos críticos verificados; replay reproducible.
- Calibración y cobertura dentro de tolerancias predefinidas y muestra suficiente por región
  utilizada.
- Ventaja económica fuera de muestra, incluyendo costes y retraso. Para afirmar evidencia de
  ventaja, exigir que una cota inferior unilateral predefinida del beneficio medio neto por día sea
  positiva, calculada por bloques y ajustada por selección si corresponde.
- Estabilidad frente a estrés y ausencia de dependencia excesiva de un día, horario o régimen, bajo
  umbrales definidos previamente.
- Drawdown y exposición dentro de límites configurados; conciliar correctamente todos los flujos de
  caja.

Un resultado incierto se etiqueta `INCONCLUSIVE`; uno que incumple criterios, `FAIL`. No convertir
ambos en aprobaciones ni buscar variantes indefinidamente.

Después de congelar la estrategia, ejecutar paper trading prospectivo. Calcular antes su duración y
muestra objetivo según una ventaja mínima económicamente relevante, variabilidad y dependencia; un
piloto corto solo verifica operación. No elegir el día de parada cuando el P&L se vuelve positivo.
Si se desea revisión secuencial, definir antes un método que controle ese seguimiento.

Estados sugeridos: `DATA_ONLY`, `RESEARCH`, `INCONCLUSIVE`, `FAIL`, `PAPER_VALIDATED`. La validez
histórica puede degradarse: suspender nuevas señales ante datos rotos, desviación persistente de
calibración o costes fuera del rango validado. La ejecución real queda fuera de este encargo.

## 12. Pantalla y registro de cada decisión

Mostrar: proveedor y contrato; umbral y vencimiento; índice y antigüedad; rango de liquidación;
probabilidad central y banda aproximada; bid/ask y coste total para la cantidad; EV
central/conservador; capital en riesgo; pérdida máxima; estado de validación y explicación de
operar/no operar.

Guardar `decision_id`, timestamps UTC, contrato, horizonte, versión de reglas, calidad, variables,
versión de modelo/calibrador/configuración, probabilidades, cotizaciones, costes, restricciones
activas, cantidad propuesta/simulada, fill y resultado. Cada importe debe indicar claramente si es
ficticio, simulado o real.

La recomendación se recalcula o caduca al cambiar las cotizaciones. Registrar `valid_until` y
condiciones de invalidez, según límites de antigüedad validados; no presentar una señal vieja como
vigente.

## 13. Orden de implementación y entregables

| Fase | Entrega | Condición para continuar |
| --- | --- | --- |
| A | Capacidades del conector, ficha de contrato y protocolo fechado | Fuentes y limitaciones explícitas |
| B | Capturador, esquema y auditoría de cobertura | Datos suficientes para el análisis declarado |
| C | Dataset temporal y referencias simples | Sin fuga temporal y etiquetas verificadas |
| D | Predicción, calibración y bandas aproximadas | Evaluación cronológica reproducible |
| E | Costes, sizing y replay | Pruebas financieras y de ejecución correctas |
| F | Informe con validación y prueba final reservada | PASS/FAIL/INCONCLUSIVE según protocolo |
| G | Dashboard y paper trading congelado | Seguimiento prospectivo sin reajustes ocultos |
| H | Investigación de contratos diarios | Protocolo y evaluación independientes |

En este repositorio, mantener la investigación en `experiments/btc-prediction-markets/` y la
interfaz en un módulo separado si posteriormente se solicita integración. RiskGate utiliza
Next.js/TypeScript/Prisma; no mezclar sus puntuaciones actuales de opciones con probabilidades de
BTC. Python puede emplearse para investigación si el entorno lo permite, con dependencias fijadas y
resultados exportados mediante un esquema versionado. Evitar nuevas dependencias o cambios de base
de datos hasta justificar la integración.

Entregar configuración de ejemplo sin secretos, comandos reproducibles, datos de prueba pequeños,
informe de limitaciones y pruebas de: reglas/empates, `p_no=1-p_yes`, banda conservadora de NO,
comisiones/redondeos, cálculo de pérdida máxima, profundidad y fills, latencia, uniones temporales,
separación de muestras y límite diario. Contrastar sizing y P&L con ejemplos calculados a mano y,
donde corresponda, búsqueda exhaustiva de cantidades.

No fabricar resultados cuando los datos no alcancen. El primer entregable útil puede ser únicamente
un diagnóstico de capacidades y un capturador prospectivo funcionando.

## 14. Fuentes oficiales y puntos que deben revalidarse

Consultadas para este diseño; Claude debe verificar vigencia al implementar, y los términos del
contrato específico prevalecen.

- [Robinhood: contratos de eventos, costes y exchanges](https://robinhood.com/us/en/support/articles/event-contracts-overview/).
  La página consultada describe comisiones ponderadas por probabilidad desde junio de 2026 y cargos
  del exchange: no codificar una tarifa plana universal.
- [Robinhood: negociación de contratos](https://robinhood.com/us/en/support/articles/trading-event-contracts/).
  Verificar el canal disponible; no dar por existente una API de prediction markets por disponer de
  una API de criptomonedas.
- [Kalshi: reglas generales de mercados cripto](https://help.kalshi.com/en/articles/13823838-crypto-markets).
  Explica índices, promedios de liquidación y prevalencia de términos específicos.
- [Kalshi: documentación oficial de API](https://docs.kalshi.com/welcome). Descubrir endpoints y
  capacidades vigentes desde documentación oficial.
- [Kalshi: datos históricos](https://docs.kalshi.com/getting_started/historical_data). Separación de
  datos recientes e históricos, cortes y paginación.
- [Kalshi: actualizaciones de libro](https://docs.kalshi.com/websockets/orderbook-updates).
  Snapshots, deltas y requisitos de acceso; disponer de stream actual no demuestra disponer de un
  archivo histórico completo.
