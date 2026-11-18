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
