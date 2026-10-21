# Comparación con Robinhood

**Fecha:** 21 de octubre de 2026. **Estado:** en curso; la revisión de las 10:27 suma una sesión por día.
**Código:** [`experiments/comparacion-robinhood/`](../experiments/comparacion-robinhood/), con los pasos de
cada día.

Solo se publican agregados. Los datos de Robinhood son para uso personal: quedan, con las cotizaciones de
Alpaca, en la rama privada `robinhood` de QuantileFlow-datos. El conector de Robinhood se usa solo para
leer datos de mercado, nunca para órdenes ni para ver la cuenta. Las claves de Alpaca están en el entorno
y no se escriben en ningún archivo.

## Resumen

- **El SPX implícito sirve.** En 28 cortes (14 sesiones, del 2 al 21 de octubre), el nivel que sale de la
  paridad put-call de SPXW difiere del índice real en −0.19 puntos de media, con desviación de 0.97. Es
  menos de lo que se mueve el SPX en ese mismo minuto: mediana de 3.4 puntos. En 23 de 28 cortes cae
  dentro del máximo y el mínimo del minuto; los otros 5 quedan a 0.51 puntos o menos.
- **Opciones fuera del dinero, primer día (21 de octubre).** El mid de Alpaca queda cerca de la marca de
  Robinhood: diferencia media de +0.23 puntos a las 09:45 y +0.03 a las 10:00, unos 0.07 y 0.04 puntos
  de volatilidad. Un día no alcanza para concluir.
- **El bid y el ask de Alpaca son raros.** La marca de Robinhood cae dentro del spread de Alpaca en solo
  11 de 28 casos, y algunos spreads de Alpaca son enormes (17.67 puntos en un call muy dentro del
  dinero). Desde el 22 de octubre una foto en vivo compara los dos bid y ask a la vez.

## 1. Qué se compara

| Comparación | Alpaca | Robinhood | Desde |
|---|---|---|---|
| Nivel del SPX | Nivel implícito de la paridad put-call de SPXW al corte | Barra de un minuto del índice que contiene el sello del nivel implícito (hh:mm:54 aproximadamente) | 2 de octubre (el histórico del SPX llega a un año) |
| Opciones al corte | Mid de la captura de 09:45 o 10:00 | Marca al cierre de la barra de 15 segundos que termina en el corte | 21 de octubre (solo hay barras del día) |
| Bid y ask en vivo | Foto del feed `indicative` | `get_option_quotes` en el mismo instante | 22 de octubre |

La muestra de opciones son 14 contratos SPXW al vencimiento más cercano a 30 días: siete strikes, del
múltiplo de 25 más cercano al nivel implícito hasta ±300 puntos, con su call y su put. Las diferencias son
siempre Alpaca menos Robinhood.

## 2. SPX implícito frente al índice real

| Medida | Valor |
|---|---|
| Cortes | 28 (14 sesiones × 09:45 y 10:00) |
| Diferencia media (implícito − cierre del minuto) | −0.19 puntos |
| Mediana | −0.31 |
| Desviación | 0.97 (0.013 % del nivel) |
| Máxima en valor absoluto | 2.02 (14 de octubre, 10:00) |
| Dentro del máximo y el mínimo del minuto | 23 de 28 |
| Distancia al rango de los 5 de afuera | 0.01 a 0.51 |
| Rango del SPX en ese minuto | 1.24 a 7.62; mediana 3.38 |

El error del forward que reporta la verificación no anticipa el tamaño de la diferencia (correlación
−0.16). Para el piloto basta: el nivel implícito sigue al índice con un error menor que el ruido del
propio minuto.

## 3. Opciones al corte (21 de octubre)

Vencimiento 20 de noviembre (30 días). Las 14 cotizaciones de Alpaca tenían menos de 7 segundos en los dos
cortes.

| | 09:45, todas | 09:45, fuera del dinero | 10:00, todas | 10:00, fuera del dinero |
|---|---:|---:|---:|---:|
| Contratos | 14 | 7 | 14 | 7 |
| Diferencia media (mid de Alpaca − marca) | +1.03 | +0.23 | +0.04 | +0.03 |
| Mediana | +0.41 | +0.18 | +0.09 | +0.09 |
| Máxima en valor absoluto | 4.88 | 1.08 | 6.62 | 0.62 |
| Diferencia relativa media | +0.62 % | +0.34 % | −0.01 % | +0.08 % |
| En puntos de volatilidad (media y máxima) | | 0.07 y 0.13 | | 0.04 y 0.08 |
| Marca de Robinhood dentro del spread de Alpaca | 6 | 3 | 5 | 4 |

Los puntos de volatilidad salen de dividir cada diferencia por la vega de Black-Scholes del contrato
(volatilidad de 15 %, 30 días). Las diferencias grandes están en las opciones dentro del dinero, que el
piloto no usa. Fuera del dinero, los spreads de Alpaca van de 0.13 a 2.81 puntos.

Parte de la diferencia puede ser de tiempo y no de calidad: la marca es la del instante del corte y cada
cotización de Alpaca tiene su propia edad (hasta 7 segundos en esta muestra).

## 4. Bid y ask en vivo

Empieza el 22 de octubre, en la revisión de las 10:27. Por contrato se mide la diferencia de mids, la razón
entre los spreads (Alpaca entre Robinhood), cuántas veces los dos bid y ask son iguales y cuántas el de
Alpaca encierra al de Robinhood. Fuera del dinero se define aquí con la delta de Robinhood (|delta| < 0.5).

## 5. Límites

- **Copia de los datos.** El conector solo lo ve Claude, así que sus respuestas se copian a archivos. El
  importador rechaza un id que no corresponde a su símbolo, una barra incoherente, una marca que no es el
  punto medio y un contrato que falta. Los datos del 21, copiados a mano, se compararon con el crudo bajado
  otra vez: iguales. También 12 barras del SPX de otros tres días.
- **Qué es la marca.** Es el punto medio del bid y el ask de Robinhood. Se supone que son las cotizaciones
  consolidadas del mercado; no está verificado.
- **Muestra chica.** 14 contratos de un vencimiento por día, no la cadena entera.
- **Solo el mismo día.** Las barras de 15 segundos de opciones solo existen para el día en curso, y el
  bid y el ask solo en vivo. Si la revisión no corre ese día, la parte de opciones se pierde; la del SPX no.
- **Cambio de horario.** Las ventanas salen de `corte_utc`, así que siguen el cambio del 1 de noviembre
  (09:45 pasa a ser 14:45 UTC). Hay una prueba con el 2 de noviembre.

## 6. Registro diario

Diferencias en puntos, Alpaca menos Robinhood. Un asterisco marca un nivel implícito fuera del máximo y el
mínimo de su minuto.

| Sesión | SPX 09:45 / 10:00 | Opciones fuera del dinero, media 09:45 / 10:00 | Marca dentro del spread (de 14) | En vivo | Notas |
|---|---|---|---|---|---|
| 2 oct | −1.91 / −0.07 | — | — | — | Solo SPX: las barras de opciones de días pasados ya no están. |
| 5 oct | −1.83 / −1.19 | — | — | — | |
| 6 oct | −0.73 / −0.94 | — | — | — | |
| 7 oct | +0.87 / +1.44\* | — | — | — | |
| 8 oct | −0.28 / −0.36\* | — | — | — | |
| 9 oct | −0.11 / +0.65 | — | — | — | |
| 12 oct | −0.01\* / −1.22 | — | — | — | |
| 13 oct | −0.04 / −1.23 | — | — | — | |
| 14 oct | −0.56 / +2.02 | — | — | — | |
| 15 oct | +0.32 / −0.33 | — | — | — | |
| 16 oct | −0.50 / +0.95\* | — | — | — | Vencimiento mensual. |
| 19 oct | −1.26\* / −0.99 | — | — | — | |
| 20 oct | +1.36 / −0.46 | — | — | — | |
| 21 oct | +0.71 / +0.38 | +0.23 / +0.03 | 6 / 5 | — | Primer día con opciones; la foto en vivo no se tomó porque el mercado ya había cerrado. |

## 7. Cómo repetir

```bash
python -m pytest -q tests/test_comparacion_robinhood.py
```

Con acceso a la rama privada, `comparar.py dia` y `comparar.py acumulado` reproducen las tablas de las
secciones 2, 3 y 6 a partir de lo importado y de las capturas de Alpaca (ver el README del experimento).
