# Holonomía en el grafo de pares cripto

Geometría de gauge medida en datos de mercado. **Fase 1** del proyecto: cuánta
curvatura hay en el grafo de pares cripto de Alpaca, cómo se reparte entre
rotacional y armónica, cuánto dura y cuánta sobrevive a los costos.

No es una aplicación del paper de LEFEOs. Toma la misma idea estructural
—gauge puro ⟺ curvatura cero; lo que sobrevive a todo cambio de gauge es
holonomía o topología— y la mide donde la estructura es exacta y discreta.

## La idea en veinte líneas

* **Nodos**: monedas. **Aristas**: pares cotizados de forma independiente.
* **Conexión**: `A_ij = log(unidades de j por unidad de i)` en la arista `i → j`.
* **Gauge**: cambiar de numerario es `A_ij → A_ij + c_j − c_i`. Ningún
  observable puede depender de `c`.
* **Gauge puro**: existe `φ` con `A_ij = φ_j − φ_i`. Eso es «no hay
  inconsistencias de precio».
* **Holonomía**: `H(C) = Σ A_ij` sobre un ciclo. Invariante de gauge.
  `H(C) > 0` con precios ejecutables es arbitraje.
* **Hodge en el grafo**: `A = gradiente ⊕ rotacional ⊕ armónico`.
  El gradiente son los precios; el rotacional es la inconsistencia local que
  cierran los triángulos; el **armónico** es la inconsistencia global, el
  análogo de `c₁`: no la produce ninguna curvatura local, vive en los huecos.

La convención de signos está fijada en `src/holonomia/grafo.py` y es la única
que hace coincidir «gradiente de φ» con «log del tipo de conversión».

## Qué hay aquí

```
src/holonomia/
  grafo.py       grafo, complejo de cliques, d0 y d1, ciclos, números de Betti
  hodge.py       descomposición por mínimos cuadrados, ortogonalidad, precios implícitos
  holonomia.py   H_mid, H_exec, comisiones de Alpaca, medio spread
  datos.py       descarga de Alpaca y crudo inmutable con manifiesto y hashes
  limpieza.py    filtros, panel *asof* sin mirar al futuro, sincronización por Δt
  medidas.py     las mediciones de §2.5
scripts/
  capturar.py    baja un día al crudo inmutable
  medir.py       corre las mediciones sobre los días capturados
  figuras.py     arma las figuras desde las tablas de resultados/
tests/           los controles de §2.6, todos
resultados/      tablas y figuras (derivados, sí van en Git)
datos_crudos/    crudo de Alpaca (NO va en Git)
```

## Reproducir de cero

Hace falta una cuenta de Alpaca; basta el plan gratuito.

```bash
export APCA_API_KEY_ID=...
export APCA_API_SECRET_KEY=...
pip install -e .
```

```bash
python -m pytest
```

Los tests no tocan la red ni las credenciales: son todos sintéticos, con
respuesta conocida. Tienen que pasar antes de mirar un solo dato real.

```bash
for d in 2026-11-10 2026-11-11 2026-11-12 2026-11-13 2026-11-14 2026-11-15 2026-11-16; do
  python scripts/capturar.py $d
done
```

```bash
python scripts/medir.py --delta-t 1.0
```

```bash
python scripts/figuras.py
```

## Lo que da Alpaca (comprobado el 18 de noviembre de 2026)

| Qué | Dónde | Resultado |
| --- | --- | --- |
| Inventario | `GET /v2/assets?asset_class=crypto` | 73 pares activos, 37 monedas, 60 triángulos |
| Histórico de cotizaciones | `GET /v1beta3/crypto/us/quotes` | bid/ask tick a tick, sello en nanosegundos, plan gratuito |
| Profundidad | sondeo por año | hay datos en 2023-06, 2024-06 y 2025-06; no en 2021-06 ni 2022-06 |
| Límite | cabecera `X-Ratelimit-Limit` | 200 peticiones por minuto |
| Comisiones | [docs.alpaca.markets](https://docs.alpaca.markets/docs/crypto-fees) | nivel 1: 0.15 % maker, 0.25 % taker |

Como el histórico ya trae las dos puntas, **no hace falta captura en vivo**:
se cae el problema de los cinco minutos de GitHub Actions de §2.2.

## Los controles (§2.6)

Todos están en `tests/` y corren sin red:

| Control | Dónde |
| --- | --- |
| Sintético consistente: `H = 0`, rotacional = armónico = 0 | `test_hodge.py` |
| Arbitraje inyectado: `ε` se recupera exacto en los ciclos que lo contienen | `test_hodge.py` |
| Hueco topológico: cuadrado sin diagonal, todo armónico | `test_hodge.py` |
| Ortogonalidad y reconstrucción | `test_hodge.py` |
| Contraste independiente: enumeración directa contra descomposición | `test_hodge.py` |
| Invariancia de gauge con `φ` aleatorio | `test_hodge.py` |
| Asincronía: la sincronización quita la holonomía espuria | `test_limpieza.py` |
| El panel no mira hacia adelante | `test_limpieza.py` |
| `H_exec = H_mid − Σs + L·log(1−f)`, exacta | `test_holonomia.py` |
