# Diccionario de datos (Paso 2)

Formato: **JSONL por añadido**, un archivo por flujo y día UTC, bajo `datos/<raiz>/<flujo>/<AAAA-MM-DD>.jsonl`.
Se eligió frente a Parquet porque `pyarrow` no está en el entorno auditado y el capturador debe
poder ejecutarse sin instalar nada.

El dinero se guarda como **texto decimal**, nunca como coma flotante.

---

## Campos comunes a todo registro

| Campo | Tipo | Significado |
| --- | --- | --- |
| `event_time` | ISO-8601 UTC | cuándo ocurrió **según la fuente** |
| `received_at` | ISO-8601 UTC | cuándo **entró a nuestro proceso** |
| `fuente` | texto | `kalshi:markets:<serie>`, `kalshi:markets/.../orderbook`, `coinbase:ticker`, `kraken:ohlc`, `kalshi:settlement` |
| `contrato` | texto | ticker, o `BTC-USD` para spot |
| `secuencia` | entero o nulo | número de secuencia, si la fuente lo da |
| `unidad` | texto | `dolares`, `usd` |
| `latencia_s` | número | `received_at − event_time`; **puede ser negativa** y se conserva así |
| `payload` | objeto | **respuesta original intacta** |

**Toda unión temporal usa `received_at`.** Un mensaje con `event_time` antiguo recibido después de
decidir no estaba disponible.

**Una revisión entra como registro nuevo**, nunca sobrescribe: así el estado de información de
cualquier momento anterior sigue siendo reconstruible.

---

## Flujo `mercado`

`payload` = objeto `market` del API. Campos que usamos:

| Campo | Uso |
| --- | --- |
| `ticker`, `event_ticker` | identificación |
| `strike_type` | **operador y tratamiento del empate** |
| `floor_strike` | **umbral**, y observación del índice en la apertura |
| `cap_strike` | umbral superior en contratos de rango |
| `open_time`, `close_time`, `expected_expiration_time`, `latest_expiration_time` | calendario |
| `rules_primary`, `rules_secondary` | texto oficial de las reglas |
| `price_ranges`, `price_level_structure` | **rejilla de ticks** |
| `notional_value_dollars` | pago del ganador |
| `yes_bid_dollars`, `yes_ask_dollars`, `no_bid_dollars`, `no_ask_dollars` | mejores precios |
| `yes_bid_size_fp`, `yes_ask_size_fp` | tamaños en el mejor nivel |
| `volume_fp`, `open_interest_fp` | actividad |
| `result`, `expiration_value` | **etiqueta oficial** (solo al liquidar) |
| `status` | `active`, `settled`… |

### Advertencia medida sobre `updated_time`

**`updated_time` no sigue los cambios de cotización.** Medido sobre 30 ciclos: la diferencia entre
`received_at` y `updated_time` fue de **179 a 411 segundos (mediana 295 s)**, mientras los precios sí
cambiaban entre lecturas.

Consecuencia: **`updated_time` no sirve como `event_time` de las cotizaciones.** Para los precios, el
único instante fiable es `received_at`. El capturador lo guarda como `event_time` por completitud,
pero el análisis no debe tratarlo como la marca del precio.

---

## Flujo `libro`

`payload.cuerpo.orderbook_fp` = dos escaleras de **órdenes de compra**:

| Campo | Forma |
| --- | --- |
| `yes_dollars` | lista de `[precio, tamaño]`, ambos texto |
| `no_dollars` | lista de `[precio, tamaño]`, ambos texto |

**No hay escalera de ventas.** Se derivan por complemento (ver `docs/ficha_contrato.md` §5).

Un lado puede venir vacío o nulo; entonces ese lado **no tiene ventas** y el API reporta el extremo
(`0` para la compra, `1.00` para la venta). Eso no es una discrepancia.

### Advertencia medida sobre leer el libro y el mercado por separado

Sobre 30 pares capturados con una separación de **0.12–0.14 segundos** entre las dos llamadas HTTP,
**25 (83 %) discreparon** en 1–3 centavos. La estructura interna del libro cuadró en **30 de 30**.

Conclusión: la discrepancia es **antigüedad, no error estructural**. En un mercado de 15 minutos las
cotizaciones se mueven más rápido que 130 ms. Por tanto:

- los precios ejecutables se toman **del libro**, que es internamente consistente;
- el `mercado` se usa para reglas, umbral y calendario, no como precio simultáneo;
- toda recomendación caduca (`valid_until`), y la antigüedad máxima por omisión es **3 s**.

---

## Flujo `spot`

| Fuente | Extracción del precio | Latencia medida |
| --- | --- | --- |
| `coinbase:ticker` | `payload.cuerpo.price`; `time` como `event_time` | p50 **2.9 s**, máx **60 s** |
| `kraken:ohlc` | cierre de la última vela (`result.<par>[-1][4]`) | la vela de 1 min marca el inicio del periodo |

**Ninguna es el índice que liquida.** El contrato liquida con el **BRTI de CF Benchmarks**, para el
que no hay vía verificada desde este entorno. Estas fuentes son **sustitutos** y la diferencia
spot−índice es una variable del modelo.

Las dos observaciones reales del índice que sí tenemos, por contrato:

- `floor_strike` → promedio de 60 s que cierra en `open_time`;
- `expiration_value` → promedio de 60 s que cierra en el vencimiento.

Para medir la base índice−spot hay que comparar spot **de la ventana de apertura**; usar spot
posterior mezclaría la base con la deriva del precio, que es un efecto mucho mayor. El reporte de
cobertura aplica esa ventana (±90 s) y devuelve «no medible» cuando no hay spot en ella, en lugar de
un número engañoso.

---

## Flujo `resultado`

`payload` = objeto `market` ya liquidado. Campos clave: `result` ∈ {`yes`, `no`, `void`…} y
`expiration_value`.

`btclab.objetivo.etiqueta_desde_mercado` comprueba que **aplicar la regla reproduce el resultado
oficial**. Si discrepan, la etiqueta se marca `excepcional` y **no se resuelve en favor de ninguno**:
significa que nuestra lectura de las reglas o del operador es incorrecta.

---

## Calidad: qué se registra y qué bloquea una decisión

| Control | Dónde | Efecto |
| --- | --- | --- |
| Huecos entre recepciones | `union.detectar_huecos` | se registran, **nunca se interpolan** |
| Saltos de secuencia | `union.detectar_saltos_secuencia` | el libro por deltas deja de ser válido; exige snapshot nuevo |
| Línea corrupta | `almacen.leer` | se cuenta y se omite; no aborta la lectura |
| Libro cruzado (spread negativo) | `libro.calidad` | no operar |
| Cotización caducada | `libro.calidad` | no operar |
| Estructura complementaria | `libro.verificar_contra_mercado` | discrepancia → no operar |
| Vela aún abierta | `union.velas_disponibles` | se descarta |
| Extrapolación excesiva | `variables.motivos_fuera_de_dominio` | fuera de dominio → no operar |
| Predicción degenerada | `probabilidad.motivos_no_usable` | certeza ≥ 0.995 → no operar |

---

## Datos sintéticos

Los datos de prueba de `tests/` son sintéticos y **están identificados como tales** en cada módulo
de prueba. No se mezclan con `datos/`.
