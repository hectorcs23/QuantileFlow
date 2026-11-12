# QuantileFlow: expiraciones y decisión de comprar datos

> Actualización 2026-10-09: presupuesto vigente **US$0**, por instrucción del usuario.
> Las opciones de compra y el límite anterior de US$250 quedan como referencia
> histórica suspendida. El trabajo actual usa datos existentes, indicative/IEX y
> benchmarks sintéticos; no se autoriza ninguna contratación.

Fecha original: 8 de octubre de 2026. El presupuesto inicial de evaluación era hasta US$250 mensuales; ahora queda suspendido y reemplazado por US$0. No se ha contratado una suscripción.

Queremos saber si podemos medir bien la forma de la distribución y sus cambios en distintos vencimientos. Después investigaremos si esas medidas aportan información sobre retornos de SPY a 1 y 5 sesiones. Son dos preguntas distintas: mejorar la medición no demuestra rentabilidad.

## Lo que sabemos hoy

Las cinco sesiones auditadas contienen dos cortes diarios. El nuevo análisis identifica RR25 a 30 días en 10/10 cortes. Para 7, 14, 60 y 90 días identifica 0/10. La captura antigua buscaba metadatos hasta 50 días y cotizaba vencimientos alrededor de 30: no es evidencia de que los contratos de otros plazos no existan. No rellenamos esas ausencias ni extrapolamos desde 0DTE.

La revisión anterior encontró persistencia del mismo signo en 94/488 residuos inicialmente fuera de banda (19.3%). Es una estadística descriptiva de pares, no una probabilidad de acierto. El nivel SPX se infiere de las propias opciones: no constituye una referencia externa independiente. Las cotizaciones gratuitas son indicativas y modificadas por el proveedor.

El nuevo código conserva el piloto de producción de 30 días y añade una configuración experimental con horizonte de consulta de 120 días y selección de 7, 14, 30, 60 y 90 días. La unión de vencimientos elimina solicitudes repetidas. El contrato más cercano sigue sirviendo para la referencia implícita; solo un vencimiento en la fecha de la sesión se clasifica como 0DTE. No se supone que siempre haya 0DTE.

## Qué necesitamos comprobar antes de pagar

| Pregunta | Evidencia que necesitamos | Por qué cambia la decisión |
|---|---|---|
| ¿Son precios reales? | Bid/ask OPRA consolidado, tamaños y sellos de evento; muestra descargable con procedencia | El feed indicativo sirve para ensayar el sistema, pero no para interpretar arbitraje ejecutable |
| ¿Cubre nuestros contratos? | SPXW europeo PM, calls/puts y strikes alrededor de delta 25; expiraciones que encierren 7–90 días | Una suscripción con cobertura nominal de “opciones” puede no resolver nuestra muestra |
| ¿Podemos reconstruir el pasado? | Confirmación de histórico de **cotizaciones bid/ask** por contrato y a qué granularidad/desde cuándo; precios y límites de descarga | Barras OHLC y operaciones no reconstruyen la cadena al corte ni sus bandas |
| ¿Tenemos referencia independiente? | Fuente del nivel observado SPX con hora/disponibilidad; SIP de SPY para el objetivo | Comprar OPRA no resuelve por sí solo el índice SPX usado en controles |
| ¿Llegan a tiempo? | Páginas, contratos, duración p50/p95, recepción antes del corte, reloj y errores 429 | La selección ampliada puede superar la ráfaga actual de 5 segundos |
| ¿Cuánto cuesta realmente? | Suscripción + tarifas por condición profesional/no profesional + índice + histórico + impuestos/descargas | El total debe caber en US$250; no solo el precio anunciado |
| ¿Podemos usar y guardar la información? | Términos de almacenamiento y uso de resultados derivados; conservación privada del detalle | El código público no debe incorporar cotizaciones por contrato |

Alpaca publica Algo Trader Plus a **US$99/mes**, con cobertura completa de acciones y opciones para Trading API. Su documentación distingue OPRA del feed indicativo. Es un candidato de bajo esfuerzo porque el adaptador ya admite `opra`; el precio final, el acceso concreto de esta cuenta y la cobertura se deben confirmar antes de contratar. No asumir que una tarifa del Broker API aplica a una cuenta individual.

La documentación de opciones sobre índices indica que el nivel SPX no forma parte de su oferta inicial. La API publicada de opciones ofrece cotizaciones actuales, barras y operaciones históricas; **no hemos confirmado un endpoint de histórico bid/ask de opciones**. Por eso una suscripción de tiempo real debe considerarse una captura hacia adelante hasta demostrar lo contrario. “Historia desde febrero de 2024” no basta para concluir que tenemos historia de quotes.

Fuentes oficiales consultadas el 8 de octubre de 2026:

- [Planes y cobertura de Alpaca](https://docs.alpaca.markets/us/docs/about-market-data-api).
- [Fuentes de datos de opciones](https://docs.alpaca.markets/us/docs/historical-option-data).
- [Cotizaciones actuales de opciones](https://docs.alpaca.markets/us/reference/optionlatestquotes).
- [Barras históricas](https://docs.alpaca.markets/us/reference/optionbars) y [operaciones históricas](https://docs.alpaca.markets/us/reference/optiontrades).
- [Opciones sobre índices y ausencia inicial del nivel SPX](https://docs.alpaca.markets/us/docs/index-options).

## Prueba que propongo

1. **Calificar la captura ampliada sin comprar.** El archivo `captura_propuesta.toml` consulta metadatos hasta 120 días, conserva dos vencimientos por lado y el cercano de SPXW. Antes de activarlo en los workflows, ejecutar una prueba manual en un almacén privado independiente; contar las páginas reales y medir el tiempo. Una prueba inmediata fuera de mercado comprueba ingestión, no frescura a la apertura. No adelantar cotizaciones recibidas tarde para hacerlas pasar por disponibles.
2. **Capturar prospectivamente los plazos.** Mantener 09:45 y 10:00 ET. Comparar 7/14/30/60/90 como plazos constantes; 0DTE separado. No introducir todavía fotos cada 30 segundos: primero medir la carga de la cadena ampliada y asegurar los cortes. Usar fechas de liquidación reales, incluidos feriados y medios días.
3. **Si el paquete cubre las necesidades, evaluar un mes de OPRA.** Máximo US$250 total, previa decisión de compra del usuario. Registrar el primer día de acceso y una fecha de reevaluación antes de renovar. Propuesta: reunir al menos 20 sesiones emparejadas; si no alcanzamos la muestra, el resultado es inconcluso, no aprobado por defecto.
4. **Comparar gratuito y pagado en las mismas sesiones y contratos.** Las dos fuentes se almacenan como series separadas. Emparejar los eventos por antigüedad y desfase; medir el sesgo temporal de solicitudes sucesivas y alternar el orden o consultar en paralelo si los límites lo permiten. Comparar la intersección de contratos y reportar además cobertura propia de cada feed para evitar selección favorable.
5. **Tomar la decisión por calidad y utilidad medible.** Prioridad inicial 14/30/60 días; 7 y 90 exploratorios. Examinar cobertura de RR25, edades/desfase, ancho de bandas de IV, sensibilidad a tasas/forward, pérdidas de captura y estabilidad al cambiar filtros. Menos residuos por sí solo no justifica comprar: las anomalías reales pueden existir, y cambiar la referencia también puede moverlos.
6. **Después evaluar predicción.** Reunir historia suficiente y etiquetas aceptadas, aplicar validación temporal con purga de horizontes solapados y comparar con un modelo base sin opciones. Mantener prueba final intacta y separar costos de datos, spreads, comisiones y rotación. Veinte sesiones califican datos; no validan una estrategia. La política actual de dividendos puede retrasar la aceptación de etiquetas: no confundir esto con imposibilidad de estudiar calidad hoy.

## Regla propuesta para continuar o cancelar el gasto

`protocolo.toml` registra objetivos y límites antes de la nueva muestra. Los umbrales de esta tabla son propuestas operativas; deben congelarse con una versión antes de observar OPRA. No son garantías de rentabilidad ni requisitos de que todos los strikes ilíquidos sean recientes.

| Criterio | Continuar la investigación con datos pagados | Cancelar o buscar otra fuente |
|---|---|---|
| Costo/licencia | Total confirmado ≤US$250 y derechos adecuados | Total mayor o uso/almacenamiento incompatible |
| Plazos prioritarios | RR25 identificada en ≥90% de cortes para cada uno de 14/30/60 días | Cobertura insuficiente por falta de contratos/cotizaciones útiles |
| Frescura | ≥90% de pares de la cohorte necesaria para RR25 con edad ≤10 s y desfase entre patas ≤2 s, por plazo | Los datos comprados siguen sin permitir sincronizar la medida |
| Operación | Sin cortes perdidos; páginas/latencias documentadas y recepción antes del corte | La carga impide capturar causalmente con la infraestructura disponible |
| Valor agregado | Bandas y sensibilidad permiten medir mejor que el gratuito; diferencias y tamaños de efecto por sesión documentados | No resuelve las limitaciones relevantes de nuestro experimento |
| Histórico | Si necesitamos backtest retrospectivo, quotes verificadas o proveedor complementario dentro del presupuesto | Compra solo tiempo real cuando el requisito indispensable era reconstruir el pasado |

Una comparación inconclusa no demuestra que la fuente sea mala. Evitar renovar automáticamente por inercia: decidir entre extender con justificación, reducir instrumentos o detener. La estabilidad de RR25 entre 09:45 y 10:00 puede ser un resultado válido; no exigir que cambie para declarar útiles los datos.

## Qué calcularemos por vencimiento

- RR25 = IV call delta +0.25 − IV put delta −0.25, con bandas de bid/ask. Estima el precio relativo del riesgo de cola, no directamente la dirección futura ni una probabilidad física.
- Cambios a la misma hora entre sesiones y entre los dos cortes. La banda del cambio usa extremo inferior final menos superior inicial y viceversa; no es un intervalo estadístico de confianza.
- Pendiente y curvatura de la estructura por plazo, por ejemplo diferencia RR25(60)−RR25(14). Es una derivada **respecto del vencimiento**, distinta de la derivada temporal de una distribución.
- Más adelante: cambios de cuantiles/transportes entre distribuciones comparables al mismo plazo, separando desplazamiento del forward de cambios de forma, con controles de arbitraje y cobertura de strikes. Las probabilidades implícitas son neutrales al riesgo; para convertirlas en confianza predictiva hace falta validación contra retornos observados.

Para RR25 a plazo constante interpolamos **varianza total por pata**, no RR25 directamente. Si no hay contratos a ambos lados o exceden el hueco del protocolo, la medida queda ausente. SPY americano se mantendrá como contraste separado con su modelo de ejercicio/dividendos; el analizador nuevo es de SPXW europeo PM y no aplica paridad europea sin ajustes a SPY.

## Cambios y límites de esta entrega

Se añadieron la selección múltiple en `quantileflow/alpaca.py`, el uso opcional de `objetivos_dias` en la captura, una configuración experimental y el analizador reproducible de cobertura/RR25. La configuración vigente y los workflows privados no se desplegaron ni se cambiaron; el experimento previo conserva sus reglas y resultados. El nuevo camino de captura está probado con una API sintética; falta medir su paginación/latencia real antes de usarlo diariamente.

La configuración propuesta conserva IEX para SPY y `indicative` para las opciones. Cambiar solo a OPRA **no** convierte todas las referencias en independientes ni activa automáticamente SIP para la captura puntual. La comparación pagada necesita una configuración versionada propia, ajustes explícitos de feeds y registros separados; no basta con reemplazar cotizaciones en tablas anteriores.

Como cota de dimensionamiento, cinco objetivos con dos vencimientos por lado seleccionan hasta 20 vencimientos por raíz, más uno cercano en SPXW: hasta 41 solicitudes de cadena y una de acciones por corte, antes de paginación/reintentos. Los solapamientos normalmente reducen ese número. Es una cota de selecciones, no de llamadas totales ni una garantía de límite de API. La ventana de 120 días también puede aumentar mucho las páginas de metadatos. Medir llamadas efectivas y cabeceras de rate limit; no trasladar sin comprobar el límite publicado de llamadas históricas a cualquier endpoint.
