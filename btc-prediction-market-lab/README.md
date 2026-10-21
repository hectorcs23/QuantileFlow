# BTC Prediction Market Lab

Laboratorio de investigación para mercados de predicción de BTC: estima la distribución del valor de
liquidación, la probabilidad de cada resultado y su incertidumbre; la compara con el **coste
ejecutable** de YES y NO; y calcula un presupuesto de pérdida, **incluida la decisión de no operar**.

**Estado: `DATA_ONLY`.** No hay ventaja medida, no hay afirmación de rentabilidad y todo importe
sugerido real es cero por construcción. Versión de investigación: **no emite órdenes** y no produce
recomendaciones de inversión.

La hipótesis que debe poder rechazarse: *«La información disponible en el momento de decidir permite
obtener una ventaja sobre el precio ejecutable, después de costes y retrasos.»*

---

## Lo primero: tres supuestos del diseño que había que corregir

La auditoría de capacidades (Paso 1) cambió el plan original:

1. **Sí existe API público de Kalshi, sin autenticación**, con el **libro completo de profundidad**,
   reglas, umbral, resultado oficial y valor de liquidación. Eso convierte el proyecto en viable
   mucho más allá de un diagnóstico.
2. **El conector de Robinhood no cubre contratos de eventos.** Está conectado (83 herramientas), pero
   ninguna es de mercados de predicción; su propia documentación anuncia «events» como pendiente. Así
   que **ninguna afirmación sobre coste o ejecución de contratos de eventos allí tiene evidencia
   propia.** La advertencia de §14 se cumple al pie de la letra.
3. **Pero ese conector sí expone `BRTI`**, el índice de CF Benchmarks que liquida el contrato, en
   vivo y con precisión completa. Era el mayor hueco de datos del proyecto. Verificado: dos lecturas
   encierran el `expiration_value` con el que el exchange liquidó. **Salvedad: las herramientas MCP
   no son invocables desde el capturador**, así que sirve para verificar, no para capturar en
   continuo.

Detalle y evidencia reproducible en [`capabilities.md`](capabilities.md).

## Hallazgos medidos que cambian el diseño

| Hallazgo | Medición | Consecuencia |
| --- | --- | --- |
| **La cadena de promedios es real** | `expiration_value(n) == floor_strike(n+1)` en **49/49** pares | el umbral **es** el promedio de 60 s de la apertura, verificado y no supuesto |
| **`updated_time` no sigue al precio** | desfase de **179–411 s** (mediana 295 s) mientras los precios cambiaban | para cotizaciones, el único instante fiable es `received_at` |
| **Dos lecturas HTTP no son simultáneas** | **83 %** de 30 pares discreparon con solo **0.12–0.14 s** entre llamadas; la estructura interna cuadró **30/30** | los precios se toman del libro, y toda señal caduca (3 s por omisión) |
| **No hay profundidad histórica** | `candlesticks` da OHLC de 1 min de `yes_bid`/`yes_ask`, sin niveles | **no se puede afirmar ventaja ejecutable** con el histórico; la profundidad se captura prospectivamente |
| **La cadena se cumple a escala** | **1597/1597** pares, **0 conflictos** sobre 17 días | de ahí sale la serie real del índice: **1603 puntos** |
| **La volatilidad estaba subestimada 2.83×** | σ real del objetivo **0.170 % a 15 min**; la ventana corta de spot daba 1/2.83 de eso | era la causa de una «ventaja» de `+0.0157` que no existía |
| **El horizonte estaba inflado** | se usaba `expected_expiration_time`, 5 min después del cierre | en un contrato de 15 min, **un tercio** de difusión de más |
| **La base spot−índice no es estable** | +39 USD (10-15), +18.81 USD (10-21); Robinhood `mark` +33.06 | el libro de cripto de Robinhood mide ~1590 USD de ancho: peor proxy que Coinbase |
| **La comisión es cuadrática** | `fee_type=quadratic`, `fee_multiplier=1` | una tarifa plana subestima el coste donde más se opera (cerca de `$0.50`) |
| **El mercado es casi una moneda** | 200 liquidados: **100 yes / 100 no** | la referencia honesta es `0.5`, no una intuición direccional |

## Cómo se corre

Sin instalar nada, el capturador y la auditoría funcionan con biblioteca estándar:

```bash
make capacidades                  # reaudita capacidades en vivo -> reportes/capacidades.json
make indice                       # reconstruye la serie del BRTI -> datos/indice/brti.jsonl
make capturar CAPTURA_S=600       # captura prospectiva -> datos/captura/
make cobertura                    # reporte de cobertura -> reportes/cobertura.json
make demo                         # cadena completa sobre un mercado vivo, sin órdenes
make pruebas                      # 218 pruebas
```

Empieza por `make indice`: reconstruye la serie real del índice de liquidación desde los mercados ya
liquidados, y es lo que da al modelo la volatilidad correcta del objetivo. 17 días salen en una
llamada de medio minuto.

Los modelos y la evaluación necesitan `numpy` y `pandas` (ver `requirements.txt`). No hay secretos ni
credenciales: el cliente **no acepta** credenciales por diseño.

### Qué muestra la demostración

La cadena completa Paso 1 → Paso 12 sobre un mercado vivo. Su historia es la mejor descripción de
para qué sirve el proyecto:

**Primera ejecución.** El modelo dio `p_yes = 0.9765` contra `0.9455` del mercado — una ventaja de
`+0.0157`. El sistema la **rechazó** por extrapolación fuera de dominio: estimaba la volatilidad con
15 segundos de spot para un horizonte de 663.

**Tras reconstruir la serie del índice** se pudo medir el error: la volatilidad real del objetivo es
`0.170 %` a 15 minutos y la ventana corta la subestimaba **2.83 veces**. Con la volatilidad correcta,
el horizonte corregido y la difusión del ancla antigua contabilizada, el modelo pasó a
`p_yes ≈ 0.50` en el dinero y la ventaja se volvió **negativa**:

```
Probabilidad central: p_yes=0.5006 p_no=0.4994
Lado yes: compra=0.620 venta=0.630
edge(n)=-0.1464
horizonte: 370s hasta el cierre de la ventana + 530s de difusion no observada = 900s efectivos
DECISION: NO OPERAR
```

**La ventaja era enteramente un artefacto de medición.** Que el sistema la rechazara antes de poder
demostrarlo es la propiedad de diseño más importante del proyecto.

## Estructura

```
capabilities.md         Paso 1: auditoría del conector, con evidencia y fechas
btclab/
  tiempo.py             UTC, event_time vs received_at, zonas IANA y DST
  dinero.py             Decimal, mils, rejilla escalonada de ticks, redondeos
  contrato.py           ficha versionada, operador, empate, estado y bloqueo
  ficha.py              construye la ficha desde el mercado vivo
  kalshi.py             cliente REST público con cubo de fichas y retroceso
  spot.py               Coinbase y Kraken (sustitutos del índice, no el índice)
  libro.py              ventas derivadas por complemento, profundidad, barridos
  almacen.py            JSONL por añadido, manifiesto y huella de entorno
  captura.py            capturador prospectivo con diagnóstico
  cobertura.py          auditoría de cobertura, huecos, latencias y base spot-índice
  indice.py             reconstruye la serie del BRTI desde los mercados liquidados
  union.py              uniones as-of hacia atrás; velas cerradas; huecos
  objetivo.py           Y, V_T, cadena de promedios, momento de decisión
  variables.py          variables, escalador solo-entrenamiento, dominio de validez
  modelos.py            referencia de mercado, Monte Carlo, logística, corrección logit
  calibracion.py        Platt, Brier, log loss, fiabilidad, cobertura por grupo
  bandas.py             bootstrap por bloques, p_robust, cobertura agregada
  costes.py             A(n), F(n), C(n), EV, edge, elegibilidad
  limites.py            presupuesto, pérdida diaria, exposición, concentración
  sizing.py             Kelly fraccionado y búsqueda discreta de G(n)
  replay.py             latencia por etapa, libro a la llegada, fills, estrés
  evaluacion.py         separación cronológica, purga, walk-forward, cota por bloques
  probabilidad.py       p_yes/p_no, banda, p_robust, predicción no usable
  decision.py           pantalla y registro con valid_until
scripts/                auditar_capacidades, reconstruir_indice, capturar, auditar_cobertura,
                        demo_decision, extraer_repo
configs/                captura.toml, riesgo.toml (sin secretos, todo etiquetado)
docs/                   metodologia, ficha_contrato, protocolo, diccionario_datos, limitaciones
tests/                  218 pruebas
```

## Estado por fase

| Fase | Entrega | Estado |
| --- | --- | --- |
| A | Capacidades, ficha de contrato y protocolo fechado | **completa** |
| B | Capturador, esquema y auditoría de cobertura | **completa**; falta acumular datos |
| C | Dataset temporal y referencias simples | **serie del índice y 1600 etiquetas ya disponibles**; falta el libro |
| D | Predicción, calibración y bandas | implementadas; **sin calibrar**, y la banda necesita otro método (ver abajo) |
| E | Costes, sizing y replay | **completa y probada** |
| F | Informe con prueba final reservada | **no iniciada**; el tramo final no se ha abierto |
| G | Dashboard y paper trading congelado | no iniciada |
| H | Contratos diarios (`KXBTCD`) | no iniciada; investigación independiente |

## Los errores que el código impide por construcción

Cada uno tiene una prueba que falla si se reintroduce:

- **`p_robust_no = 1 − U`**, nunca `1 − L`. La clase solo expone `p_robust(lado)` para que el error
  no se pueda escribir.
- **El empate sigue al operador.** `greater_or_equal` → YES; `greater` → NO. Un `strike_type`
  desconocido **falla** en lugar de interpretarse.
- **Sin datos liquida NO**, no cancela.
- **El spread no se suma dos veces**: se compra al lado de las ventas, que ya lo incorpora.
- **`ask_no ≠ 1 − ask_yes`**: en un libro real suman `1.050`.
- **La comisión se redondea al centavo superior**, por nivel ejecutado.
- **La pérdida máxima es el coste total comprometido.** Un stop de P&L no la limita.
- **El replay usa el libro de la llegada**, no el de la decisión: un retraso de 15 s costó `19.86`
  en la prueba.
- **Una orden limitada no garantiza ejecución.**
- **Las uniones usan `received_at`**: un mensaje con marca antigua recibido después no existía.
- **Las velas abiertas se descartan.**
- **Los huecos se registran, nunca se interpolan.**
- **Las etiquetas se purgan** si invaden el tramo siguiente.
- **1000 observaciones en 10 días correlacionados = 10 efectivas**, y se reporta así.
- **Sin presupuesto configurado, sin banda defendible o sin comisiones verificadas → tamaño cero.**
- **El horizonte acaba en `close_time`**, no en el vencimiento; el capital inmovilizado se mide aparte.
- **Un ancla antigua suma su difusión no observada** al horizonte, en lugar de tratarse como actual.
- **En el dinero, `p` es insensible a σ**, así que una banda por remuestreo de σ sale degenerada y se
  rechaza. Fijado en una prueba: la banda defendible tendrá que venir del error de calibración fuera
  de muestra, no de remuestrear un parámetro al que el objetivo es insensible.

## Repositorio independiente

Este proyecto es **autocontenido** y está pensado para vivir en su propio repositorio. La sesión que
lo generó **no pudo crearlo**: el proxy limita el token a los repositorios configurados y devolvió
`403 "sessions are bound to their configured repositories"` por las dos vías probadas (API MCP y
`gh api`).

Para extraerlo con su propia historia, en un paso:

```bash
bash scripts/extraer_repo.sh ~/btc-prediction-market-lab
gh repo create btc-prediction-market-lab --private --source=~/btc-prediction-market-lab --push
```

## Siguiente paso que más desbloquea

1. **Calibrar sobre la serie del índice.** Ya hay 1600 contratos con etiqueta y 17 días de la serie
   real. Eso permite la Fase D de la parte de predicción **hoy**, sin esperar nada: separación
   cronológica, calibrador sigmoide y bandas por cobertura empírica. Es el trabajo que más avanza y
   no necesita a nadie.
2. **Adjuntar el calendario de comisiones vigente.** Único bloqueo documental; por sí solo cambia
   `COSTS_UNVERIFIED` y habilita los importes simulados.
3. **Dejar el capturador corriendo** en una máquina que no se recicle. Es lo único que levanta el
   bloqueo de profundidad, y los mínimos están en `configs/captura.toml`.
4. **Una clave de CF Benchmarks**, si se quiere el BRTI en continuo. El conector lo da en sesión pero
   no al capturador.
5. **Medir la latencia del flujo manual real.** Mientras no exista, toda conclusión que dependa del
   retraso es provisional.

## Advertencia

Versión de investigación. Las cifras de configuración son hipótesis de ingeniería para simulación,
no parámetros que hayan demostrado rentabilidad ni recomendaciones de inversión. La ejecución real
queda fuera de este encargo. Ver [`docs/limitaciones.md`](docs/limitaciones.md).
