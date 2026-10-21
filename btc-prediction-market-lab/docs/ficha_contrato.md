# Ficha de contrato: `KXBTC15M` (Paso 1)

**Fecha de consulta:** 2026-10-15 (UTC). **Estado:** `COSTS_UNVERIFIED` → el tamaño monetario
está desactivado.

Esta ficha describe la **serie**. La ficha del contrato concreto se construye en ejecución con
`btclab.ficha.ficha_desde_mercado`, que lee el mercado vivo y vuelve a comprobar cada campo. Los
términos del contrato concreto prevalecen sobre este documento y sobre la plantilla de clase.

---

## 1. Identificación

| Campo | Valor | Fuente |
| --- | --- | --- |
| Plataforma visible | Kalshi | `GET /series/KXBTC15M` |
| Exchange subyacente | Kalshi (`exchange_index` 2: Crypto & Commodities) | `GET /exchange/status` |
| Serie | `KXBTC15M` | API |
| Frecuencia | `fifteen_min` | API |
| Evento | `KXBTC15M-<AAMMMDDHHMM>` | API |
| Contrato | `KXBTC15M-<AAMMMDDHHMM>-<MM>` | API |
| Moneda | USD | términos del contrato |
| Título | «BTC price up in next 15 mins?» | API |

**No se asume que un contrato visto en otra plataforma sea este mismo contrato.** Usar cotizaciones
de otro proveedor exige verificar antes contrato, índice, ventana, umbral y reglas; y aun entonces,
la ejecución y los costes de esa plataforma necesitan evidencia propia. Para Robinhood **no existe
esa evidencia** en este proyecto: no hay conector ni vía verificada (ver `capabilities.md` §1).

## 2. Calendario

| Campo | Valor |
| --- | --- |
| Apertura | `open_time` (en punto, y cada 15 min) |
| Fin de negociación | `close_time` = apertura + 15 min |
| Vencimiento esperado | `expected_expiration_time` = cierre + ~5 min |
| Vencimiento límite | `latest_expiration_time` = cierre + 7 días |
| Referencia temporal | **UTC** |
| Zona de presentación | `America/New_York` (IANA, no desplazamiento fijo) |

La zona IANA importa: las reglas se publican en hora de Nueva York («12:15 AM EDT»), que pasa a EST
en invierno. Verificado en código: `21:00Z` = 17:00 EDT en octubre y 16:00 EST en enero. Codificar
`-04:00` produciría un error de una hora medio año.

**El horizonte termina en `close_time`, no en el vencimiento.** La ventana de 60 s que determina
`V_T` cierra al **cerrar la negociación**; `expected_expiration_time` llega unos cinco minutos
después, cuando el exchange publica y liquida. Usar el vencimiento como horizonte añadiría cinco
minutos de difusión que el objetivo no tiene: en un contrato de 15 minutos, **un tercio del horizonte
real**. Por eso la ficha expone dos cuentas separadas:

| Método | Mide | Para qué |
| --- | --- | --- |
| `tiempo_restante_s` | hasta `close_time` (= `fin_ventana_liquidacion`) | el modelo de precio |
| `tiempo_hasta_vencimiento_s` | hasta `expected_expiration_time` | el capital inmovilizado |

Y no es una constante de 15 minutos: a 60 s de la apertura quedan ~840 s, no 900.

## 3. Regla de liquidación

> «If the simple average of the sixty seconds of CF Benchmarks' BRTI before 12:15 AM EDT on Oct 15,
> 2026 **is at least** the simple average of the sixty seconds of CF Benchmarks' BRTI before 12:00
> AM EDT on October 15, 2026, then the market resolves to Yes.»

| Campo | Valor | Consecuencia |
| --- | --- | --- |
| Índice | CF Benchmarks **BRTI** | no es el spot de ningún exchange |
| Agencia fuente | CF Benchmarks | |
| Ventana de promedio | **60 segundos**, cerrando en `close_time` | `V_T` es un promedio, no el precio terminal |
| Operador | `greater_or_equal` (`strike_type`) | **el empate liquida YES** |
| Umbral | `floor_strike` | **es el promedio de 60 s de la apertura** |
| Revisiones posteriores | no cuentan | vale el valor observado |
| Sin datos | **liquida NO** | no es cancelación |

**El umbral no es una constante del calendario:** es un dato que se publica al abrir el mercado.
El momento de decisión debe confirmar que ya se conoce (`MomentoDecision.admisible`).

**Verificación numérica de la cadena de promedios.** El `expiration_value` de un contrato es
exactamente el `floor_strike` del siguiente: `KXBTC15M-26OCT150000-00` liquidó en `80833.68`, que
es el `floor_strike` de `KXBTC15M-26OCT150015-15`. Confirma que el contrato compara dos promedios
consecutivos y que ambos son observaciones reales del BRTI.

Comprobado **a escala** el 2026-10-21: sobre 1600 mercados liquidados (17 días), la cadena se cumple
en **1597 de 1597** casos comprobables, con **0 conflictos**. De ahí sale
`scripts/reconstruir_indice.py`, que reconstruye la serie real del índice de liquidación.

**Identidad del índice verificada contra una fuente independiente.** El conector de Robinhood expone
`BRTI` en vivo; dos lecturas (`84282.07` a las 23:29:14 y `84249.12` a las 23:30:11) encierran el
`expiration_value = 84259.75` del mercado que cerró a las 23:30:00. Es el mismo índice.

**Operadores, literal de los términos:** «"Above X" means strictly greater than X, while "below X"
means strictly less than X. "Exactly X" means equal to X […] and "at least X" means X or greater.
"Between X and Y" means greater or equal to X and less than or equal to Y.» El código traduce
`strike_type` → operador con una tabla explícita y **falla ante un valor desconocido**, porque de
ese campo depende el empate.

## 4. Precios, tick y cantidades

| Campo | Valor |
| --- | --- |
| Pago del ganador | `$1.00` (`notional_value_dollars`) |
| Pago del perdedor | `$0.00` |
| Tick mínimo del contrato | `$0.001` |
| Estructura de rejilla | `tapered_deci_cent` |
| Cantidad mínima | 1 contrato |
| Fracciones | el API devuelve tamaños fraccionarios (`*_fp`) |

Rejilla (`price_ranges`), **escalonada**:

| Tramo | Paso |
| --- | --- |
| `[0.000, 0.100)` | `0.001` |
| `[0.100, 0.900)` | `0.010` |
| `[0.900, 1.000]` | `0.001` |

Consecuencia comprobada en pruebas: `$0.455` **no existe**; `$0.045` y `$0.955` sí. Un tick plano
de un centavo generaría órdenes imposibles.

## 5. Estructura del libro

Kalshi publica **dos escaleras de compras** (`yes_dollars`, `no_dollars`) y **ninguna de ventas**.
Las ventas se derivan por complemento del lado opuesto:

- ventas de YES = `{(1 − q, tamaño)}` sobre las compras de NO
- ventas de NO = `{(1 − p, tamaño)}` sobre las compras de YES

Verificado: 30 de 30 snapshots capturados cumplen `mejor compra(lado) + mejor venta(opuesto) = 1000`
mils, exactamente. En un mercado quieto la derivación reprodujo el `yes_ask` y su tamaño sin ninguna
discrepancia.

**Esto no autoriza `ask_no = 1 − ask_yes`**, que relaciona dos ventas entre sí y es falso con
spread: en un libro observado, venta YES `0.450` y venta NO `0.600` suman `1.050`, no `1.000`.

## 6. Costes

| Campo | Valor | Estado |
| --- | --- | --- |
| Tipo | `quadratic` | **verificado** (`GET /series/KXBTC15M`) |
| Multiplicador | `1` | **verificado** |
| Constante | `0.07` (configurable) | **NO verificada** |
| Comisión del intermediario | `0` | no aplica (acceso directo a Kalshi) |
| Redondeo | al centavo superior, por nivel ejecutado | elección conservadora |
| Vigencia | — | pendiente |

La comisión es **ponderada por probabilidad** y máxima cerca de `$0.50`, que es donde opera un
mercado de 15 minutos. Una tarifa plana subestimaría el coste en el tramo más usado: para 100
contratos a `$0.50` la cuadrática da `$1.75` frente a `$1.00` de una plana de un centavo.

Mientras la constante no se verifique contra fuente primaria, `permite_tamano_monetario` es `False`
y ningún importe sugerido puede ser distinto de cero.

## 7. Límites y contingencias

| Campo | Valor |
| --- | --- |
| Límite de posición | **`$25,000` por strike y por miembro** |
| Revisión de resultado | Market Outcome Review Process, Regla 6.3(d) |
| Pagos excepcionales | Regla 6.3(b) |
| Prohibiciones | empleados de las agencias fuente; tenedores de información material no pública |

Las cancelaciones y los pagos especiales se registran aparte, con su flujo de caja real: una
cancelación **reembolsa el coste** (neto cero), no se convierte en pérdida ni se borra del registro.

## 8. Fuentes

| Fuente | Consultada | Qué aporta |
| --- | --- | --- |
| [`assets.kalshi.com/contract_terms/CRYPTO.pdf`](https://assets.kalshi.com/contract_terms/CRYPTO.pdf) | 2026-10-15 | operadores, sin-datos→NO, tick, pago, límite de posición, revisiones |
| [`help.kalshi.com/.../crypto-markets`](https://help.kalshi.com/en/articles/13823838-crypto-markets) | 2026-10-15 | índice, promedio de 60 s, estructura de los contratos de 15 min |
| `GET /series/KXBTC15M` | 2026-10-15 | `fee_type`, `fee_multiplier`, frecuencia, URLs de términos |
| `GET /markets?series_ticker=KXBTC15M` | 2026-10-15 | reglas, umbral, operador, calendario, rejilla |
| Calendario de comisiones | **no obtenido** (429) | **falta la constante** |

## 9. Reglas que faltan para pasar a `VERIFICADO`

1. **Constante del calendario de comisiones vigente**, con copia fechada y fecha de vigencia.

Ese es el único bloqueo documental restante. Los demás campos esenciales están verificados contra
fuente primaria o contra el propio API.
