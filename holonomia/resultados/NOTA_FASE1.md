# Curvatura de gauge en un mercado cripto real

**Fase 1.** Holonomía, descomposición de Hodge y ejecutabilidad en el grafo de
pares cripto de Alpaca. Una semana de cotizaciones tick a tick, del 10 al 16 de
noviembre de 2026.

---

## 1. La pregunta

Un mercado de cambios es una teoría de gauge discreta y exacta. Las monedas son
los nodos; los pares cotizados de forma independiente, las aristas; el log del
tipo de conversión, la conexión:

$$A_{ij} = \log(\text{unidades de } j \text{ por unidad de } i).$$

Reexpresar todo en otro numerario es un cambio de gauge, `A_ij → A_ij + c_j − c_i`,
y ningún observable económico puede depender de él. Lo que sobrevive es la
**holonomía** de los ciclos, `H(C) = Σ A_ij`, que es invariante de gauge y
cumple: `H(C) > 0` con precios ejecutables **es** arbitraje.

La descomposición de Hodge del grafo parte la conexión en tres piezas
ortogonales:

| pieza | qué es | lectura económica |
| --- | --- | --- |
| gradiente | `im(d₀)` | gauge puro: existen precios consistentes |
| rotacional | `im(d₁ᵀ)` | inconsistencia **local**: arbitraje triangular |
| armónico | `ker d₁ ∩ ker d₀ᵀ` | inconsistencia **global**: ciclos que ningún triángulo operable rellena |

El armónico es el análogo directo de `c₁`: no lo produce ninguna curvatura
local, vive en los huecos del complejo.

La pregunta de esta fase no es si el arbitraje se puede leer como holonomía
—eso ya está escrito, ver §5— sino **cuánta curvatura hay en un mercado real,
cómo se reparte entre local y global, cuánto dura y cuánta sobrevive a los
costos de ejecución.**

## 2. Método

**Datos.** Alpaca, `GET /v1beta3/crypto/us/quotes`: histórico de cotizaciones
de dos lados, con bid, ask, tamaños y sello del exchange en nanosegundos. No
pide suscripción. Se capturan 26 pares sobre 9 monedas (BTC, ETH, LTC, BCH,
LINK, UNI, USD, USDC, USDT), el subgrafo líquido que contiene todos los cruces
cripto-cripto. El crudo se guarda tal como llega, comprimido y direccionado por
SHA-256, con un manifiesto por captura; la normalización sólo lee el crudo y
comprueba los hashes, así que reprocesar da las mismas tablas.

**Sincronización.** Un ciclo se evalúa en el instante `t` sólo si **todas** sus
patas tienen cotización con sello del exchange en `[t − Δt, t]`. El panel se
arma con semántica *asof*: nunca entra una cotización posterior a `t`. Δt base:
1 s, con barrido de 0.01 s a 10 s.

**Las dos conexiones.** Con el medio geométrico `mid = √(bid·ask)` y el medio
spread en logaritmos `s = ½log(ask/bid)`, cada pata cumple **exactamente**, en
los dos sentidos,

$$A^{\text{exec}} = A^{\text{mid}} - s + \log(1-f),$$

de donde, para un ciclo de longitud `L`,

$$H_{\text{exec}}(C) = H_{\text{mid}}(C) - \sum_{\text{patas}} s + L\log(1-f).$$

Esa identidad es la vara que separa «hay curvatura» de «hay dinero». `f` es la
comisión *taker* de Alpaca, 0.25 % en el nivel 1, que es lo que corresponde a
cruzar el mercado.

**El complejo.** Las 2-celdas son los triángulos **operables**. Como la
frescura cambia instante a instante, el complejo cambia con ella, y con él el
número de Betti: la parte armónica aparece justo cuando la liquidez deja de
rellenar un hueco.

## 3. Verificación

Todo el núcleo matemático se probó contra respuestas conocidas **antes** de
tocar datos reales. Los controles corren sin red ni credenciales:

| control | qué exige |
| --- | --- |
| sintético consistente | precios generados con un φ → toda `H = 0`, rotacional = armónico = 0 a precisión de máquina |
| arbitraje inyectado | un `ε` conocido en un par se recupera **exacto** en los ciclos que lo contienen y en la parte rotacional |
| hueco topológico | cuadrado sin diagonal con circulación constante → todo queda en la parte armónica |
| ortogonalidad y reconstrucción | las tres partes son ortogonales y suman `A` |
| contraste independiente | holonomía por enumeración directa = holonomía de la descomposición |
| invariancia de gauge | sumar `d₀χ` con χ aleatorio no mueve `H` ni las normas de rotacional y armónico |
| asincronía | con quotes desfasadas a propósito aparece holonomía espuria, y apretar Δt la elimina, monótonamente |
| sin mirar al futuro | el panel en `t` nunca usa una cotización posterior a `t` |
| identidad `H_exec` | se cumple a precisión de máquina en los ocho niveles de comisión |

## 4. Resultados

### 4.0 Lo primero no es del mercado: el complejo no tiene huecos

Antes de mirar un precio. En el grafo cripto completo de Alpaca —37 monedas,
73 pares, conexo— hay **60 triángulos y el espacio de ciclos tiene dimensión
37**, y los 60 triángulos lo generan entero. Por lo tanto **b₁ = 0**: la parte
armónica es cero *por construcción*, diga lo que diga el mercado. Lo mismo en
el subgrafo medido: 9 monedas, 26 pares, 34 triángulos, rango de ciclos 18,
b₁ = 0.

La razón es la forma del grafo: USD, USDC y USDT son centros conectados a casi
todo, y cualquier ciclo pasa por un centro, de modo que algún triángulo lo
rellena. **El análogo de c₁ no existe en este mercado**, salvo que se le quiten
caras. Eso convierte la parte armónica en una cantidad endógena a la liquidez,
y es lo que mide §4.5.

### 4.1 Los datos

Siete días, del 10 al 16 de noviembre de 2026. **7 883 051 cotizaciones**, de
las que se descarta el **0.147 %**: casi todo son bids en cero de USDC/USD
(unas 1 500 al día) más entre 0 y 136 spreads absurdos. **En toda la semana no
hay un solo mercado cruzado ni bloqueado.** Quedan **1 471 222 instantes
triángulo-sincronizados** a Δt = 1 s, repartidos entre 34 triángulos.

No todos los triángulos son medibles. `USD → USDC → USDT`, el de las
stablecoins puras, deja **4 instantes al día**: USDC/USD cotiza 1.2 veces por
minuto y nunca coincide con las otras dos patas dentro de un segundo. Se
reporta, no se interpreta.

### 4.2 Cuánta curvatura hay

| | rango entre los 32 triángulos medibles |
| --- | --- |
| mediana de \|H_mid\| | 1.4 a 19 pb |
| mediana del medio spread del ciclo | 16 a 90 pb |
| **mediana de \|H_mid\| / medio spread** | **0.035 a 0.26** |
| p99 de esa razón | 0.15 a 0.86 |

La curvatura existe y se mide, pero vive **dentro del spread**: en la mediana,
entre el 3 % y el 26 % de lo que cuesta cruzar el ciclo.

Hay estructura clara en la sección cruzada. Los triángulos que pasan por USDC
llevan de 8 a 19 pb de holonomía mediana; los que van por USD o USDT, de 1.4 a
4 pb. `BTC → USD → USDT` y `ETH → USD → USDT` son los más consistentes del
mercado, con 1.4 pb.

El peor instante de la semana llega a **razón 2.99** (`BTC → LTC → USD`), y hay
otros dos triángulos que pasan de 1: `BTC → USD → USDT` (1.26) y
`BCH → BTC → USD` (1.16). Los 29 restantes nunca lo hacen. En total, **57 de
1 471 222 instantes** —unos 4 de cada 100 000— tienen \|H_mid\| por encima del
medio spread de su ciclo.

### 4.3 Nada de eso es ejecutable

El umbral es el medio spread acumulado más tres comisiones *taker* de 25 pb:
entre **91 y 165 pb** según el triángulo. La holonomía media no se le acerca.

> **Cero instantes con `H_exec > 0`**, en 34 triángulos por 7 días. El mejor
> momento de la semana entera deja **−73.6 pb**: perder un 0.74 % por vuelta.

El resultado no depende del esquema de comisiones, pero conviene decirlo con
precisión. Las comisiones son 75 de los ~120 pb del umbral típico; el resto es
spread. Con comisión **cero**, el umbral sería el medio spread, y la razón de
§4.2 lo cruza en 4 de cada 100 000 instantes, sólo en 3 de 32 triángulos. Es
decir: incluso un participante sin comisiones que cruce el spread encontraría
oportunidades rarísimas y en ciclos concretos. Queda fuera del alcance la
estrategia pasiva *maker*, que no cruza el spread pero asume riesgo de pata.

### 4.4 No es asincronía, y no es redondeo

Este es el control que decide si lo medido es mercado o artefacto.

| Δt | BTC→ETH→USD | BTC→ETH→USDT | BTC→LTC→USD |
| --- | --- | --- | --- |
| 0.01 s | 1.62 pb | 2.12 pb | 1.48 pb |
| 1 s | 1.55 pb | 2.26 pb | 2.29 pb |
| 10 s | 1.50 pb | 2.22 pb | 2.14 pb |

**Plano en tres órdenes de magnitud.** En el mercado sintético asíncrono de los
tests —consistente en todo instante, muestreado a ritmos distintos— apretar la
ventana cien veces corta la mediana más de diez, monótonamente. Aquí no la
mueve ni un 15 %.

Tampoco es granularidad de precio: el tick observado es de 0.0001 pb en
BTC/USD, 0.0024 en ETH/USD y 0.036 en ETH/BTC, entre 40 y 15 000 veces por
debajo de la holonomía medida.

### 4.5 Local contra global: el armónico no es medible aquí

Barrido de Δt sobre el grafo entero de 26 pares, un instante cada 30 s:

| Δt | aristas vivas (de 26) | caras | b₁ | rotacional | armónico | grafo entero |
| --- | --- | --- | --- | --- | --- | --- |
| 1 s | 4 | 0 | 0 | — | — | 0.0 % |
| 5 s | 9 | 3 | 0 | 1.82 pb | 0 | 0.0 % |
| 15 s | 16 | 8 | 0 | 4.08 pb | 0 | 0.1 % |
| 60 s | 26 | 34 | 0 | 7.89 pb | 0 | 99.7 % |
| 300 s | 26 | 34 | 0 | 7.89 pb | 0 | 99.9 % |

Hay un compromiso que no se puede esquivar: **o se sincroniza, o se tiene el
grafo**. A Δt = 1 s viven 4 de 26 aristas y no hay un solo triángulo completo;
a Δt = 60 s vive el grafo entero, pero las patas lentas llevan hasta un minuto
de retraso, y la norma rotacional crece monótonamente con Δt —de 1.8 a 7.9 pb—
que es exactamente la firma de la rancidez, no del mercado.

**La parte armónica sale cero en todos los Δt**, y la mediana de b₁ del
complejo vivo también. No porque el mercado sea globalmente consistente, sino
porque el complejo vivo nunca tiene un hueco: cuando es denso, los triángulos
lo rellenan; cuando es ralo, no tiene ni ciclos. Con este grafo, la afirmación
del preprint de agosto sobre vigilar la componente armónica **no se puede ni
confirmar ni refutar**: no hay armónico que vigilar.

### 4.6 Persistencia: segundos

La vida media de `H_mid` es de **1.0 a 1.4 segundos** según el triángulo. La
autocorrelación a un segundo es 0.83 para `BTC → ETH → USD` y ya es
indistinguible de cero a los cinco. Las inconsistencias se cierran en segundos:
ni en milisegundos ni en minutos.

Con una advertencia: los instantes sincronizados son a ráfagas, y cubren sólo
el 6–10 % de los segundos del día, así que la ACF se calcula saltando huecos.

### 4.7 Régimen: sí, pero poco

Hay más curvatura cuando hay más actividad, con correlación de Spearman 0.35
contra la volatilidad realizada de BTC/USD a 5 minutos (0.31 contra la
intensidad de cotizaciones). Pero el efecto es muy sublineal: **del octil más
tranquilo al más agitado la volatilidad se multiplica por 3.6 y la holonomía
sólo por 1.4.**

### 4.8 Veredicto según §2.7

Es el **resultado negativo válido** del criterio: `|H_mid|` vive dentro del
medio spread y no hay arbitraje ejecutable en ningún momento de la semana. Pero
no es un resultado vacío, porque sí hay estructura:

1. **Sección cruzada**: la ruta por USDC lleva sistemáticamente de 5 a 10 veces
   más curvatura que la ruta por USD o USDT.
2. **Escala de tiempo propia**: vida media de ~1.4 s, sin ambigüedad.
3. **Régimen**: positivo y claramente sublineal en la volatilidad.
4. **Estructural**: el grafo cripto de Alpaca no admite parte armónica, y eso
   es una propiedad del mercado (todo pasa por tres centros), no del método.

### 4.9 Qué haría falta para la pregunta armónica

La Fase 1 responde la pregunta de tamaño y la de persistencia, y deja la
pregunta de §0 —cuánta inconsistencia es *global*— sin responder por falta de
topología, no por falta de datos. Para abrir un hueco de verdad hacen falta
ciclos que ningún triángulo operable rellene, y eso pide una de dos cosas:

* **Varios exchanges.** El mismo par en dos venues es una arista distinta, y
  los ciclos entre venues no se cierran con triángulos: ahí hay b₁ > 0 por
  construcción. Es el camino natural, y además es donde la literatura dice que
  sí hay arbitraje cripto.
* **Un grafo con más cruces cripto-cripto y sin centro.** Alpaca sólo cotiza
  cinco cruces contra BTC; no alcanza.

## 5. Novedad

El encuadre conceptual **ya está publicado**. Mishra,
[arXiv:2608.11252](https://arxiv.org/abs/2608.11252) (4 de agosto de 2026), un
paper de razonamiento con agentes, usa divisas como banco de calibración en su
§7.2 y dice justo esto: con el nulo de no-arbitraje la cocadena es un coborde
exacto, el arbitraje triangular es el rotacional y el arbitraje de lazo sobre
ciclos sin triángulo ejecutable es el armónico. Pero **no usa datos de
mercado**: es un complejo construido de 15 monedas, 400 libros simulados por
escenario y arbitraje inyectado de 4 pb. Los autores dicen que les falta
validación empírica.

La equivalencia «rotacional cero ⟺ no hay arbitraje triangular» es más vieja
todavía: está en la base de HodgeRank (Jiang, Lim, Yao y Ye, *Math. Program.*
127, 2011), junto con el punto que manda aquí — en un grafo completo no hay
componente armónica.

Lo que no estaba hecho, y es lo que aporta esta nota, es la **medición sobre
cotizaciones reales con dos puntas y costos de ejecución**: tamaños, reparto,
persistencia y ejecutabilidad.

## 6. Reproducir

```bash
python -m pytest                      # los controles de §3, sin red
python scripts/capturar.py 2026-11-10 # un día al crudo inmutable
python scripts/medir.py --delta-t 1.0
python scripts/barrido_hodge.py
python scripts/figuras.py
```
