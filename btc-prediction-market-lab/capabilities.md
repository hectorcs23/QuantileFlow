# Auditoría de capacidades (Paso 1)

**Primera auditoría:** 2026-10-15 (UTC). **Revisión:** 2026-10-21, tras conectarse el conector
de Robinhood. **Entorno:** contenedor de sesión en la nube de
claude.ai, salida HTTPS a través de proxy. **Autor de la auditoría:** sesión de Claude Code.

Este documento registra lo que **se verificó ejecutando llamadas**, no lo que se supone
disponible. Cada afirmación lleva el endpoint o la fuente que la respalda. No contiene secretos:
todas las lecturas descritas son públicas y sin autenticar.

Reevaluar esta auditoría ante cualquier cambio de entorno: las capacidades aquí descritas son del
contenedor y del momento de consulta, no garantías de la plataforma.

---

## 1. Conectores: qué hay y qué no

| Conector | Estado (2026-10-21) | Sirve para este proyecto |
| --- | --- | --- |
| **Robinhood** | **conectado y activo, 83 herramientas** | **sí, pero no para contratos de eventos** |
| Canva | instalado, `needs_reconnect` | no |
| Google Calendar | instalado, `not_connected` | no |
| Microsoft 365 | instalado, `not_connected` | no |
| Opera | instalado, `needs_reconnect` | no |

El 2026-10-15 **no existía** conector de Robinhood (verificado en conectores instalados y en el
registro). El 2026-10-21 **sí está conectado**, con 83 herramientas. Esto es lo que cambia y lo que
no.

### Lo que el conector de Robinhood **no** da: contratos de eventos

Las 83 herramientas cubren acciones, opciones, cripto, índices, listas, escáneres, filings y
operaciones de cartera. **Ninguna cubre contratos de eventos ni mercados de predicción.** No es una
deducción: la propia descripción de `search` lo dice literalmente —

> «More categories (**events**, futures) will be added as their corresponding tools land.»

Consecuencia, idéntica a la que ya estaba y alineada con §2 y §14: **no hay vía verificada para
obtener de Robinhood cotizaciones ejecutables de contratos de eventos, sus comisiones reales ni
ejecución de órdenes.** Cualquier afirmación sobre coste o ejecución de contratos de eventos en
Robinhood sigue sin evidencia propia. La advertencia de §14 («no dar por existente una API de
prediction markets por disponer de una API de criptomonedas») se cumple al pie de la letra.

### Lo que el conector **sí** da, y es importante: el índice BRTI

`get_indexes` devuelve, entre otros, el símbolo **`BRTI`** (id `1b489c2d-6bb0-433d-bad1-d832b6931b33`).
Es el **CF Benchmarks Bitcoin Real-Time Index**, exactamente el índice que liquida el contrato de
Kalshi, y `get_index_quotes` devuelve su valor en vivo con precisión completa y marca de venue:

```
BRTI = 84282.0671111111111111   venue_timestamp 2026-10-21T19:29:14-04:00
```

**Verificación de identidad del índice.** El mercado `KXBTC15M-26OCT211930-30` (cierre 23:30:00Z)
liquidó en `expiration_value = 84259.75`, que es el promedio de 60 s del BRTI en 23:29:00–23:30:00.
Dos lecturas del conector lo encierran: `84282.07` a las 23:29:14 y `84249.12` a las 23:30:11. El
índice venía bajando y el promedio de la ventana cae entre ambas. **Es el mismo índice.**

**Pero el conector no resuelve la captura continua.** Las herramientas MCP solo son invocables desde
la sesión conversacional, **no desde `scripts/capturar.py`**. Así que el BRTI está disponible para
verificar y para contrastar puntualmente, no para registrarse cada pocos segundos de forma autónoma.
`scripts/demo_decision.py` acepta `--brti <valor>` para inyectar una lectura a mano, y queda
registrada como tal.

### CF Benchmarks directo: requiere clave

`api.cfbenchmarks.com` no es alcanzable desde este entorno (`CONNECT tunnel failed, 502`).
`www.cfbenchmarks.com` sí responde, pero sin clave no sirve: `/api/v1/assets` → `401 "not
authorized"`, `/api/v1/indices` → `200` con `payload: []`, `/api/v1/values?id=BRTI` → `400 "Unknown
id"`. **Una clave de CF Benchmarks sería la vía que permitiría al capturador registrar el BRTI de
forma autónoma.**

### Cripto de Robinhood: peor proxy de lo que parece

`get_crypto_quotes` para `BTC-USD` devuelve bid `83507` / ask `85097` — **unos 1590 USD de ancho**,
por *Market Maker Routing*. Su `mark_price` es el medio de ese spread. Medido en el mismo instante
(23:31:13–16Z):

| Fuente | Valor | Base vs BRTI |
| --- | --- | --- |
| **BRTI** | `84269.20` | — |
| Coinbase (`bid/ask` a 1 céntimo) | `84288.01` | **+18.81** (+0.022 %) |
| Robinhood `mark_price` | `84302.26` | +33.06 (+0.039 %) |

Conclusión contraintuitiva pero medida: **el libro de cripto de Robinhood es un proxy peor que
Coinbase** para el índice, pese a ser de la misma casa, porque su spread es cinco órdenes de magnitud
más ancho.

### Acceso GitHub de esta sesión

La sesión está vinculada a `hectorcs23/QuantileFlow`. La creación de repositorios nuevos está
bloqueada por el proxy, verificado por dos vías:

- `POST /user/repos` vía herramienta MCP → `403 Resource not accessible by integration`
- `gh api -X POST user/repos` → `403 This GitHub API path is not available: sessions are bound to
  their configured repositories.`

Por eso este proyecto vive en una carpeta autocontenida y trae `scripts/extraer_repo.sh`, que
produce el repositorio independiente con su propia historia en un paso. Ver `README.md`.

---

## 2. Kalshi: API público de lectura (funciona sin autenticación)

Base verificada: `https://api.elections.kalshi.com/trade-api/v2`

| Endpoint | Resultado | Qué entrega |
| --- | --- | --- |
| `GET /exchange/status` | 200 | `exchange_active`, estado por índice de exchange |
| `GET /exchange/schedule` | 200 | horario de negociación por día |
| `GET /series?category=Crypto` | 200 | 278 series; 40 contienen `BTC` |
| `GET /series/{serie}` | 200 | `fee_type`, `fee_multiplier`, `frequency`, términos del contrato |
| `GET /markets?series_ticker=…` | 200 | reglas, umbral, operador, horarios, mejores precios y tamaños |
| `GET /markets/{ticker}` | 200 | ficha de un mercado |
| `GET /markets/{ticker}/orderbook` | 200 | **escalera completa de profundidad**, ambos lados |
| `GET /markets/trades?ticker=…` | 200 / 429 | operaciones; se agota la tasa con facilidad |
| `GET /series/{s}/markets/{t}/candlesticks` | 200 | **histórico de 1 minuto**: OHLC de `yes_bid` y `yes_ask`, volumen, interés abierto |

No se probó ningún endpoint de escritura, de cuenta ni de órdenes, y el cliente del repositorio
(`btclab/kalshi.py`) no acepta credenciales por diseño.

### 2.1 Series de BTC relevantes

| Serie | Frecuencia | Título |
| --- | --- | --- |
| `KXBTC15M` | `fifteen_min` | BTC price up down |
| `KXBTCD` | `hourly` | Bitcoin price Above/below |
| `BTCD` | `daily` | Bitcoin price Above/below |
| `KXBTC` | `hourly` | Bitcoin range |

El mercado elegido para la primera investigación es **`KXBTC15M`** (§1: un solo mercado de 15
minutos, un solo proveedor). Los contratos diarios quedan para la Fase H, con entrenamiento,
calibración y evaluación separados.

### 2.2 Límites de tasa (medidos, no supuestos)

La documentación de Kalshi describe un presupuesto por fichas: la mayoría de las peticiones cuesta
10 fichas y el nivel `Basic` dispone de 200 fichas/s de lectura (≈20 lecturas/s). **Sin autenticar
observamos `429 too_many_requests` muy por debajo de ese ritmo**: una secuencia de cuatro lecturas
seguidas ya devolvió 429 en dos de ellas. La respuesta 429 **no trae cabecera `Retry-After`**.

Por eso `btclab/kalshi.py` implementa cubo de fichas conservador y retroceso exponencial con
jitter, y expone un diagnóstico (`peticiones`, `respuestas_429`, `segundos_esperando`) que el
reporte de cobertura debe incluir. **El límite de tasa es una restricción de diseño del capturador,
no un detalle:** condiciona cuántos contratos se pueden seguir en paralelo.

### 2.3 Estructura del libro: ventas derivadas, y verificadas

Kalshi publica el libro como **dos escaleras de órdenes de compra**, una por lado (`yes_dollars`,
`no_dollars`). **No publica escalera de ventas.** La estructura documentada de la plataforma es
complementaria: una compra de NO en reposo a `q` es ejecutable como venta de YES a `1 − q`.

- ventas de YES = `{(1 − q, tamaño)}` sobre las compras de NO
- ventas de NO  = `{(1 − p, tamaño)}` sobre las compras de YES

Esto **no** es el supuesto prohibido `ask_no = 1 − ask_yes` (que relaciona dos ventas y es falso en
presencia de spread). Verificación en un mercado quieto (`KXBTCD-26OCT1517-T92749.99`):

| Magnitud | API | Derivado del libro |
| --- | --- | --- |
| mejor compra NO | `0.9900` | `0.990` |
| mejor venta YES | `0.0100` | `0.010` = 1 − 0.990 ✓ |
| tamaño de esa venta | `14644.00` | `14644.00` ✓ |

Discrepancias: **ninguna**. `btclab/libro.py` conserva esta comprobación como invariante de
ejecución (`verificar_contra_mercado`): si la derivación y el API discrepan, es motivo de no operar.

**Advertencia medida:** en `KXBTC15M` dos llamadas separadas por segundos ya discrepan (el `yes_bid`
pasó de `0.35` a `0.33` entre la ficha del mercado y el libro). La discrepancia era antigüedad, no
error estructural: dentro de un mismo snapshot, compra de un lado + venta complementaria del otro
sumaban exactamente 1000 mils. Esto fija un requisito operativo: **el libro y la ficha deben leerse
como un par con marca temporal conjunta, y toda recomendación caduca.**

### 2.4 Rejilla de precios: escalonada, no plana

`KXBTC15M` declara `price_level_structure = "tapered_deci_cent"` y `price_ranges`:

| Tramo | Paso |
| --- | --- |
| `[0.000, 0.100)` | `0.001` |
| `[0.100, 0.900)` | `0.010` |
| `[0.900, 1.000]` | `0.001` |

El tick mínimo del contrato es **$0.001** (términos del contrato). Codificar un tick plano de un
centavo generaría precios inexistentes: `$0.455` no está en la rejilla, `$0.045` sí.

### 2.5 Histórico: hay top-of-book a 1 minuto, **no** hay libro histórico

`candlesticks` entrega, por minuto: OHLC de `yes_bid`, OHLC de `yes_ask`, OHLC del precio operado,
`volume_fp` e `open_interest_fp`. Máximo **5000 velas por petición**, así que el rango se trocea.

Lo que esto **sí** permite: entrenar y evaluar la parte de predicción con la mejor compra y la mejor
venta históricas.

Lo que esto **no** permite, y es la limitación central del proyecto:

- **No hay profundidad histórica.** Solo el mejor nivel. El coste de barrer una cantidad no se puede
  reconstruir hacia atrás.
- **La vela es un agregado del minuto.** Usar el cierre de una vela aún abierta como si estuviera
  cerrada es fuga temporal; `btclab/union.py` solo admite velas cerradas.
- Por tanto, **no se puede afirmar una ventaja ejecutable a partir de este histórico.** La
  profundidad debe capturarse prospectivamente (`scripts/capturar.py`).

Los mercados liquidados sí traen el resultado oficial: `result` ∈ {`yes`,`no`} y `expiration_value`
(el promedio real del índice). Sobre 200 mercados liquidados de `KXBTC15M` (2026-10-13 a 10-15):
**101 `yes` / 99 `no`**. La paginación por `cursor` permite recorrer el histórico hacia atrás.

**Verificación de la cadena de promedios:** el `expiration_value` de un mercado es exactamente el
`floor_strike` del siguiente. Comprobado: `KXBTC15M-26OCT150000-00` tiene
`expiration_value = 80833.68`, que es el `floor_strike` de `KXBTC15M-26OCT150015-15`. Esto confirma
documental y numéricamente que el umbral de cada contrato es el promedio de apertura.

### 2.6 Comisiones: estructura verificada, constante **no** verificada

Verificado desde el propio API (`GET /series/KXBTC15M`): `fee_type = "quadratic"`,
`fee_multiplier = 1`. Es decir, **la comisión depende del precio y es máxima cerca de 0.50** — es
ponderada por probabilidad, coherente con lo que §14 describe para Robinhood. **Una tarifa plana
universal sería incorrecta.**

**La constante del modelo cuadrático no se pudo verificar contra fuente primaria desde este
entorno:** `kalshi.com/fee-schedule` y `kalshi.com/docs/kalshi-fee-schedule.pdf` devolvieron
`429 Too Many Requests`, y `docs.kalshi.com/getting_started/fees` devolvió `404`.

Consecuencia aplicada en el código: el estado de la ficha es **`COSTS_UNVERIFIED`** y
`permite_tamano_monetario` es `False`, de modo que **ningún importe sugerido puede ser distinto de
cero**. La constante vive en `configs/riesgo.toml`, marcada como no verificada. Para cerrar este
punto hace falta adjuntar la copia del calendario de comisiones vigente y su fecha.

---

## 3. Términos del contrato (fuente primaria obtenida)

Descargado y leído: `https://assets.kalshi.com/contract_terms/CRYPTO.pdf` (2 páginas, 2026-10-15).
Es la plantilla de la clase CRYPTO; **los términos del contrato concreto prevalecen** y los
marcadores (`<time>`, `<price>`) se instancian por iteración.

Extractos que fijan reglas esenciales:

- **Subyacente:** promedio simple del índice de CF Benchmarks correspondiente **durante los 60
  segundos previos** a `<time>`. **Agencia fuente:** CF Benchmarks.
- **Operadores, literal:** «"Above X" means strictly greater than X […] "at least X" means X or
  greater.» Por tanto `strike_type = greater_or_equal` ⇒ **el empate liquida YES**; `greater` ⇒ el
  empate liquida NO. Esta distinción decide los casos de borde, que son los más frecuentes a 15
  minutos.
- **Sin datos:** «If no data is available or incomplete on the Expiration Date at the Expiration
  Time, then affected strikes resolve to No.» No es cancelación: **liquida NO**.
- **Revisiones:** «Revisions to the Underlying made after Expiration will not be accounted for.»
  Cuenta el valor observado, no el revisado.
- **Tick mínimo:** `$0.001`. **Valor de liquidación:** `$1.00`.
- **Límite de posición:** `$25,000` por strike y por miembro — restricción real para el Paso 7.
- **Contingencias:** Kalshi puede abrir el Market Outcome Review Process (Regla 6.3(d)); los pagos
  excepcionales se rigen por la Regla 6.3(b).

---

## 4. Datos del subyacente (variables explicativas)

| Fuente | Endpoint | Estado | Nota |
| --- | --- | --- | --- |
| Coinbase Exchange | `api.exchange.coinbase.com/products/BTC-USD/ticker` | 200 | bid/ask/último, con `time` |
| Kraken | `api.kraken.com/0/public/OHLC?pair=XBTUSD` | 200 | OHLC de 1 minuto |
| Binance | `api.binance.com` | **451** | bloqueado por geolocalización: `Service unavailable from a restricted location` |
| CF Benchmarks BRTI | conector de Robinhood, `get_index_quotes` | **verificado en vivo** | es el índice que liquida; disponible en la sesión, **no** desde el capturador |
| CF Benchmarks directo | `www.cfbenchmarks.com/api/v1` | **requiere clave** | `401`/`payload: []` sin autenticar |

**La brecha más importante:** el índice que determina la liquidación es el **BRTI de CF
Benchmarks**, y **no tenemos acceso verificado a él**. Las fuentes spot disponibles son
*sustitutos*, no el índice.

Magnitud del problema, medida: en una lectura casi simultánea, Coinbase marcaba `80795.14` y el
`floor_strike` de Kalshi (que **es** un promedio real del BRTI) era `80833.68` — una diferencia de
unos **39 USD**, del orden de `0.05%`. En un contrato de 15 minutos cuyo umbral es el propio nivel
de apertura, esa diferencia es comparable al movimiento típico del horizonte, así que **no es
despreciable**. Kraken mostró en la misma ventana `≈81613`, a unos 780 USD, lo que sugiere
desalineación o caché y refuerza la exigencia de registrar `event_time` y `received_at` por fuente.

Mitigación disponible sin acceso al BRTI: el `expiration_value` de cada mercado liquidado **es** una
observación del índice (el promedio de 60 s), y `floor_strike` es otra. Eso da **dos lecturas
reales del BRTI por contrato** y permite estimar y seguir la diferencia spot−índice, que es
exactamente la variable que §5 pide. No sustituye al índice en tiempo real.

---

## 5. Entorno de cómputo

Python 3.13.16; `numpy` 2.5.3, `pandas` 3.0.5, `requests` 2.34.2 presentes; `scipy`, `sklearn`,
`matplotlib`, `pyarrow` **ausentes**; `pytest` 9.1.1 instalado para este proyecto. Node 22, git 2.43.

Decisión de diseño derivada: el capturador, el cliente, los costes, el sizing y el contrato usan
**solo biblioteca estándar**, para que puedan ejecutarse sin instalar nada. La regresión logística y
la calibración se implementan sobre `numpy`, sin `scipy` ni `sklearn`.

---

## 6. Estado resultante y qué desbloquea qué

**Estado del proyecto: `DATA_ONLY`.**

Esto es lo que §13 anticipa como primer entregable útil: diagnóstico de capacidades más capturador
prospectivo funcionando. No hay ventaja medida, ni afirmación de rentabilidad, ni importe sugerido
distinto de cero.

| Bloqueo | Qué impide | Qué lo levanta |
| --- | --- | --- |
| `COSTS_UNVERIFIED` | cualquier importe distinto de cero | copia fechada del calendario de comisiones vigente |
| sin profundidad histórica | afirmar ventaja **ejecutable** | capturar libro prospectivamente (ya implementado) |
| BRTI no capturable de forma autónoma | registrar el índice cada pocos segundos | clave de CF Benchmarks; el conector lo da en sesión pero no al capturador |
| Robinhood sin contratos de eventos | cualquier afirmación sobre coste/ejecución de contratos de eventos allí | que Robinhood publique esas herramientas («events» está anunciado como pendiente) |
| sin latencia medida del flujo manual | convertir ventaja en decisión | medir la distribución de retrasos del flujo real |
