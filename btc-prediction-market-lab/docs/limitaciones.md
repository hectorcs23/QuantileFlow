# Informe de limitaciones

Fecha: 2026-10-15, revisado el 2026-10-21. **Estado del proyecto: `DATA_ONLY`.**

Este documento existe para que nadie lea el repositorio como evidencia de algo que no contiene.
**No hay ventaja medida, ni afirmación de rentabilidad, ni importe sugerido distinto de cero.**

---

## 1. Lo que este proyecto no demuestra

- **No demuestra que exista una ventaja.** La hipótesis no se ha puesto a prueba todavía: falta
  cobertura de datos y falta el tramo final, que no se ha abierto.
- **No demuestra ventaja ejecutable.** No existe histórico de profundidad del libro, así que el
  coste de barrer una cantidad no se puede reconstruir hacia atrás.
- **No dice nada verificado sobre contratos de eventos en Robinhood.** El conector ya está conectado
  (83 herramientas), pero **ninguna cubre contratos de eventos**: su propia documentación anuncia
  «events» como pendiente. Cualquier coste o ejecución de contratos de eventos allí sigue sin
  evidencia propia.
- **No produce recomendaciones de inversión.** Los límites y el `alpha = 0.25` son hipótesis de
  ingeniería para simulación.

## 2. Bloqueos duros, con lo que los levantaría

| Bloqueo | Qué impide | Qué lo levanta |
| --- | --- | --- |
| `COSTS_UNVERIFIED` | cualquier importe distinto de cero | copia fechada del calendario de comisiones vigente |
| Sin profundidad histórica | afirmar ventaja **ejecutable** | capturar el libro prospectivamente (implementado) |
| BRTI no capturable de forma autónoma | registrar el índice en continuo | clave de CF Benchmarks (el conector lo da en sesión, no al capturador) |
| Sin latencia medida del flujo manual | convertir ventaja en decisión | medir la distribución de retrasos del flujo real |
| Sin presupuesto configurado | mostrar cualquier cifra personal | que el usuario fije capital segregado y límites |
| Robinhood sin contratos de eventos | hablar de costes o ejecución allí | que Robinhood publique esas herramientas |

## 3. Limitaciones de datos

**El índice que liquida sí está accesible, pero no para el capturador.** El conector de Robinhood
expone `BRTI` en vivo y se verificó que es el índice que liquida (ver `capabilities.md`). Pero las
herramientas MCP solo son invocables desde la sesión conversacional, **no desde
`scripts/capturar.py`**. Para captura autónoma haría falta una clave de CF Benchmarks.

**Mientras tanto hay dos anclas buenas, y una tiene antigüedad.** Cada mercado liquidado aporta dos
valores exactos del índice, de modo que `scripts/reconstruir_indice.py` reconstruye la serie real: se
obtuvieron **1603 puntos sobre 17 días, con 0 conflictos** en la cadena. Pero esa serie publica un
valor **cada 15 minutos**, así que al decidir el ancla puede tener cientos de segundos de antigüedad.
El modelo lo trata sumando la difusión no observada al horizonte; ignorarlo estrecharía la
distribución justo cuando el ancla está más vieja.

**La base spot−índice es de orden 20–40 USD y no es estable.** Medido el 2026-10-15, Coinbase estaba
a +39 USD del índice; el 2026-10-21, a +18.81 USD, y el `mark_price` de Robinhood a +33.06 USD. Y el
libro de cripto de Robinhood tiene ~1590 USD de ancho (*market maker routing*), así que es **peor**
proxy que Coinbase pese a ser de la misma casa.

**El histórico es solo top-of-book a 1 minuto.** `candlesticks` da OHLC de la mejor compra y la mejor
venta, volumen e interés abierto. Sirve para entrenar predicción; **no** para medir coste de
ejecución. Además, una vela es un agregado del minuto: usar el cierre de una vela aún abierta es
fuga temporal, y el código solo admite velas cerradas.

**El límite de tasa condiciona el diseño.** Sin autenticar aparecen `429` muy por debajo del límite
documentado del nivel Basic, y sin cabecera `Retry-After`. Esto acota cuántos contratos se pueden
seguir en paralelo y obliga a cubo de fichas con retroceso exponencial.

**`updated_time` no sirve como marca del precio.** Medido: 179–411 s de desfase (mediana 295 s)
mientras los precios cambiaban. Para las cotizaciones, el único instante fiable es `received_at`.

**Dos lecturas HTTP no son simultáneas.** Con 0.12–0.14 s entre la ficha del mercado y el libro,
**83 %** de los pares discreparon. La estructura interna del libro cuadró en 30 de 30, así que es
antigüedad y no error estructural; pero obliga a tomar los precios del libro y a que toda señal
caduque.

**Binance está bloqueado** por geolocalización (`451`) desde este entorno.

## 4. Limitaciones de modelado

**El Monte Carlo normal subestima las colas.** El modelo por omisión usa incrementos normales, que
no capturan saltos ni agrupamiento de volatilidad. El remuestreo por bloques de retornos históricos
está implementado y es la vía preferida, pero exige una serie de retornos del mismo paso tomada solo
de datos anteriores a la decisión.

**La ventana de estimación de volatilidad era el punto más frágil, y está corregido.** Con 15 s de
spot y un horizonte de 663 s, el modelo daba `p_yes = 0.9765` frente a `0.9455` del mercado: una
«ventaja» de `+0.0157` que era **puro artefacto**. La serie del índice permitió cuantificar el error:
la volatilidad real del objetivo es **σ = 0.170 % a 15 minutos** (5.64e-05 por segundo, sobre 1602
retornos), y la ventana corta de spot la **subestimaba 2.83 veces**. Con la volatilidad correcta y el
horizonte corregido, el modelo pasó a `p_yes ≈ 0.50` en el dinero y la ventaja se volvió **negativa**.
El repliegue a spot sigue existiendo, pero queda marcado como `REPLIEGUE, subestima`.

**El horizonte estaba inflado, y está corregido.** `tiempo_restante_s` usaba
`expected_expiration_time`, que llega unos cinco minutos después del cierre de negociación. La
ventana de 60 s que determina `V_T` cierra en **`close_time`**. En un contrato de 15 minutos eran
cinco minutos de difusión de más: un tercio del horizonte real. Ahora hay dos cuentas separadas:
`tiempo_restante_s` (el objetivo) y `tiempo_hasta_vencimiento_s` (el capital inmovilizado).

**La banda por remuestreo de σ no mide la incertidumbre que importa en el dinero.** Es una propiedad
matemática, no un fallo de implementación: cuando el umbral iguala el nivel actual, `p ≈ 0.5` para
cualquier volatilidad, así que remuestrear σ produce una banda de ancho cero. Queda fijado en una
prueba (`test_en_el_dinero_la_probabilidad_es_insensible_a_la_volatilidad`). El guardián la marca
`degenerada` y rechaza operar, que es el comportamiento conservador correcto, **pero por el mecanismo
equivocado**. La banda defendible para este problema tiene que venir de **error de calibración fuera
de muestra**, no de remuestrear un parámetro al que el objetivo es insensible. Eso es Fase D sobre
datos reales y está pendiente.

**Sin calibrador ajustado no hay probabilidad publicable.** La demostración corre con
`version_calibrador = "sin_calibrar(demo)"` precisamente para que quede visible.

**La banda es aproximada.** Está condicionada a supuestos y puede fallar ante cambios de régimen. No
implica que una operación individual gane con el nivel nominal, y la «probabilidad verdadera» de un
evento único no es observable. La dispersión entre modelos está disponible pero marcada **no
defendible**.

## 5. Limitaciones de evaluación

**No hay test final.** El tramo final no se ha abierto y no se abrirá hasta cumplir los criterios de
`docs/protocolo.md` §5.

**La dependencia reduce drásticamente la muestra.** Verificado en pruebas: 1000 observaciones
repartidas en 10 días correlacionados equivalen a **10 observaciones efectivas**. Miles de ticks no
son miles de apuestas independientes, y el número efectivo se reporta siempre.

**Los perfiles de retraso no están medidos.** Los tres escenarios llevan `medido = False`. Cualquier
conclusión que dependa del retraso es provisional.

**Una sola posición abierta.** El MVP reduce así el problema de correlación. Los contratos diarios
son una investigación aparte (Fase H) y exigen límites conjuntos de exposición a BTC; la fórmula de
Kelly aislada no basta cuando hay posiciones relacionadas.

## 6. Limitaciones de alcance

- Sin órdenes reales. El cliente no acepta credenciales por diseño.
- Sin órdenes pasivas: el MVP no simula colas, porque hacerlo con supuestos optimistas es la vía
  rápida a un backtest irreal.
- Un solo mercado (`KXBTC15M`) y un solo proveedor (Kalshi), como exige el alcance.
- La ejecución real queda fuera del encargo.

## 7. Qué sí aporta hoy

1. Una auditoría de capacidades con evidencia reproducible, que corrige dos supuestos del diseño
   original: **sí** hay API público de lectura con libro completo, y **no** hay conector de
   Robinhood.
2. Una ficha de contrato verificada contra los términos oficiales, incluidos empate, sin-datos→NO,
   rejilla escalonada y límite de posición.
3. Un capturador prospectivo funcionando, con almacén por añadido, manifiesto y auditoría de
   cobertura.
4. La cadena completa de costes, probabilidad conservadora, sizing y replay, con 191 pruebas que
   fijan los errores que la metodología prohíbe.
5. Hallazgos medidos que cambiaron el diseño: el desfase de `updated_time`, la no simultaneidad de
   dos lecturas HTTP, la magnitud y variabilidad de la base spot−índice, la identidad verificada del
   BRTI, el horizonte inflado y la subestimación de la volatilidad por 2.83×.
6. La serie real del índice de liquidación: 1603 puntos sobre 17 días, 0 conflictos en la cadena, con
   sus 1600 etiquetas (798 `yes` / 802 `no`). Es el insumo que la Fase C necesitaba.
