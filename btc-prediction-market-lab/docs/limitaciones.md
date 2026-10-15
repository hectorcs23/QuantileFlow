# Informe de limitaciones

Fecha: 2026-10-15. **Estado del proyecto: `DATA_ONLY`.**

Este documento existe para que nadie lea el repositorio como evidencia de algo que no contiene.
**No hay ventaja medida, ni afirmación de rentabilidad, ni importe sugerido distinto de cero.**

---

## 1. Lo que este proyecto no demuestra

- **No demuestra que exista una ventaja.** La hipótesis no se ha puesto a prueba todavía: falta
  cobertura de datos y falta el tramo final, que no se ha abierto.
- **No demuestra ventaja ejecutable.** No existe histórico de profundidad del libro, así que el
  coste de barrer una cantidad no se puede reconstruir hacia atrás.
- **No dice nada verificado sobre Robinhood.** No hay conector ni vía de acceso; cualquier coste o
  ejecución en esa plataforma queda sin evidencia propia.
- **No produce recomendaciones de inversión.** Los límites y el `alpha = 0.25` son hipótesis de
  ingeniería para simulación.

## 2. Bloqueos duros, con lo que los levantaría

| Bloqueo | Qué impide | Qué lo levanta |
| --- | --- | --- |
| `COSTS_UNVERIFIED` | cualquier importe distinto de cero | copia fechada del calendario de comisiones vigente |
| Sin profundidad histórica | afirmar ventaja **ejecutable** | capturar el libro prospectivamente (implementado) |
| Sin acceso al BRTI | reproducir `V_T` en vivo | vía verificada a CF Benchmarks, o aceptar sustituto y **medir** el error |
| Sin latencia medida del flujo manual | convertir ventaja en decisión | medir la distribución de retrasos del flujo real |
| Sin presupuesto configurado | mostrar cualquier cifra personal | que el usuario fije capital segregado y límites |
| Sin conector de Robinhood | hablar de costes o ejecución allí | evidencia propia, o declararlo fuera de alcance |

## 3. Limitaciones de datos

**El índice que liquida no está accesible.** El contrato liquida con el BRTI de CF Benchmarks. Las
fuentes disponibles (Coinbase, Kraken) son sustitutos. En una lectura casi simultánea Coinbase
marcaba `80795.14` mientras el promedio real del índice era `80833.68`: unos **39 USD**, del orden de
`0.05 %`. En un contrato de 15 minutos cuyo umbral **es** el nivel de apertura, esa diferencia es
comparable al movimiento típico del horizonte. **No es despreciable.**

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

**La ventana de estimación de volatilidad es el punto más frágil.** Observado en la demostración:
con 15 s de spot y un horizonte de 663 s, el modelo dio `p_yes = 0.9765` frente a `0.9455` del
mercado, una «ventaja» aparente de `+0.0157` que es **artefacto de subestimar la volatilidad**. El
proyecto rechaza esas observaciones por regla (`factor_maximo = 3.0×` y certeza máxima `0.995`), pero
esto ilustra lo fácil que es fabricar una ventaja inexistente.

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
5. Tres hallazgos medidos que cambian el diseño: el desfase de `updated_time`, la no simultaneidad
   de dos lecturas HTTP, y la magnitud de la base spot−índice.
