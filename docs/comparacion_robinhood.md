# Comparación con Robinhood

**Fecha:** 21 de octubre de 2026; totales al viernes 30. **Estado:** en curso; la revisión de las 10:27
suma una sesión por día y los totales se ponen al día los viernes.
**Código:** [`experiments/comparacion-robinhood/`](../experiments/comparacion-robinhood/), con los pasos de
cada día.

Solo se publican agregados. Los datos de Robinhood son para uso personal: quedan, con las cotizaciones de
Alpaca, en la rama privada `robinhood` de QuantileFlow-datos. El conector de Robinhood se usa solo para
leer datos de mercado, nunca para órdenes ni para ver la cuenta. Las claves de Alpaca están en el entorno
y no se escriben en ningún archivo.

## Resumen

- **El SPX implícito sirve.** En 41 cortes (21 sesiones, del 2 al 30 de octubre), el nivel que sale de la
  paridad put-call de SPXW difiere del índice real en −0.07 puntos de media, con desviación de 1.01. Es
  menos de lo que se mueve el SPX en ese mismo minuto: mediana de 2.9 puntos. En 32 de 41 cortes cae
  dentro del máximo y el mínimo del minuto; los otros 9 quedan a 1.04 puntos o menos.
- **Opciones fuera del dinero: cerca.** En ocho sesiones (105 comparaciones al corte), el mid de Alpaca
  queda +0.23 puntos sobre la marca de Robinhood en promedio (mediana +0.10). Son unos 0.08 puntos de
  volatilidad en promedio y 0.36 en el peor caso. La foto en vivo da casi lo mismo: +0.25 de media.
- **El bid y el ask de Alpaca no son los del mercado.** En las siete fotos en vivo, ningún bid y ask de
  Alpaca coincide con el de Robinhood (0 de 98). El ancho típico es el mismo (razón mediana 1.00), pero
  los precios están corridos: la marca de Robinhood cae dentro del spread de Alpaca en 43 de 98 en vivo y
  en 97 de 203 al corte. El mid de Alpaca quedó arriba en 61 de 98.

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
| Cortes | 41 (21 sesiones × 09:45 y 10:00; el 29 de octubre, solo las 10:00) |
| Diferencia media (implícito − cierre del minuto) | −0.07 puntos |
| Mediana | −0.28 |
| Desviación | 1.01 (0.013 % del nivel) |
| Máxima en valor absoluto | 2.04 (22 de octubre, 09:45) |
| Dentro del máximo y el mínimo del minuto | 32 de 41 |
| Distancia al rango de los 9 de afuera | 0.01 a 1.04 |
| Rango del SPX en ese minuto | 1.24 a 7.62; mediana 2.91 |

El error del forward que reporta la verificación no anticipa el tamaño de la diferencia (correlación
−0.02). El 29 de octubre, con el mayor error del forward del mes (1.48), la diferencia fue de +0.34. El
30, con errores chicos (0.27 y 0.20), los dos cortes quedaron fuera de su minuto. Para el piloto basta: el
nivel implícito sigue al índice con un error menor que el ruido del propio minuto.

## 3. Opciones al corte (21 a 30 de octubre)

Ocho sesiones y 15 cortes (el 29, solo las 10:00), con 14 contratos: 203 comparaciones. Se descartaron 7
barras interpoladas: 2 el 22, 3 el 27 y 2 el 30. Vencimientos: 20, 23, 25, 27 y 30 de noviembre. Todas las
cotizaciones de Alpaca tenían 21.5 segundos o menos (mediana 5.4).

| | Todas | Fuera del dinero |
|---|---:|---:|
| Comparaciones | 203 | 105 |
| Diferencia media (mid de Alpaca − marca) | +0.30 | +0.23 |
| Mediana | +0.15 | +0.10 |
| Desviación | 1.91 | 0.84 |
| Máxima en valor absoluto | 6.62 | 3.00 |
| Diferencia relativa (media y mediana) | +0.24 % y +0.13 % | +0.32 % y +0.22 % |
| En puntos de volatilidad (media, mediana y máxima) | | 0.08, 0.07 y 0.36 |
| Marca de Robinhood dentro del spread de Alpaca | 97 | 48 |

Los puntos de volatilidad salen de dividir cada diferencia, en valor absoluto, por la vega de
Black-Scholes del contrato (volatilidad de 15 %, plazo de su vencimiento). Las diferencias grandes están en
las opciones dentro del dinero, que el piloto no usa. Fuera del dinero, los spreads de Alpaca van de 0.06 a
4.83 puntos (mediana 0.70).

Parte de la diferencia puede ser de tiempo y no de calidad: la marca es la del instante del corte y cada
cotización de Alpaca tiene su propia edad (hasta 21.5 segundos en esta muestra).

## 4. Bid y ask en vivo (22 al 30 de octubre)

Una foto por día, hacia las 10:30, con las mismas 14 opciones: siete fotos. Por contrato, entre la
cotización de Alpaca y la de Robinhood hay 1.2 segundos de mediana y 26 como máximo, en cotizaciones de
Robinhood que no habían cambiado. Desde el 27 de octubre, `importar` exige que la foto de Alpaca salga a
menos de 5 s de la cotización más reciente de Robinhood. Fuera del dinero se define aquí con la delta de
Robinhood (|delta| < 0.5).

| | Todas | Fuera del dinero |
|---|---:|---:|
| Contratos | 98 | 49 |
| Diferencia media de mids (Alpaca − marca) | +0.55 | +0.25 |
| Mediana | +0.41 | +0.18 |
| Máxima en valor absoluto | 4.66 | 2.07 |
| En puntos de volatilidad, con la vega de Robinhood (media y máxima) | | 0.08 y 0.25 |
| Razón de spreads (Alpaca entre Robinhood), mediana | 1.00 | 1.00 |
| Mismo ancho (±5 %), más ancho y más angosto | 15, 47 y 36 | 8, 23 y 18 |
| Bid y ask iguales | 0 | 0 |
| El spread de Alpaca encierra al de Robinhood | 24 | 12 |
| Marca de Robinhood dentro del spread de Alpaca | 43 | 18 |

El feed `indicative` no copia el bid y el ask del mercado: los anchos se parecen, pero los precios están
corridos. Para el piloto importa el mid, y fuera del dinero su error típico es de menos de una décima de
punto de volatilidad. El mid de Alpaca quedó arriba en 61 de 98 contratos, y en más de la mitad en 6 de los
7 días: apunta a un sesgo chico hacia arriba (mediana +0.18 fuera del dinero). Con siete días todavía no es
concluyente.

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
- **Cotizaciones atrasadas.** El bid y el ask en vivo de Robinhood traen su hora (`updated_at`). El 27 de
  octubre, las dos primeras consultas devolvieron precios de unos 6 y 4 minutos antes. Desde entonces
  `importar` exige que la foto de Alpaca salga a menos de 5 s de la cotización más reciente de Robinhood; si
  no, se repite (pasos en el README del experimento).
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
| 22 oct | +2.04\* / +0.99 | +0.29 / +0.19 | 9 / 4 (de 12) | Diferencia mediana +0.43; razón de spreads mediana 1.00; iguales 0 de 14; marca dentro del spread de Alpaca 6 de 14 | Primera foto en vivo (10:33). A las 09:45 el error del forward fue de 1.19: la mayor diferencia del SPX hasta ahora. A las 10:00 se descartaron dos barras interpoladas de contratos muy dentro del dinero. |
| 23 oct | +0.00 / −0.22 | +0.73 / +0.28 | 8 / 6 | Diferencia mediana +0.62; razón de spreads mediana 1.00; iguales 0 de 14; marca dentro del spread de Alpaca 6 de 14 | Vencimiento del 23 de noviembre. A las 09:45 la media fuera del dinero sube por tres puts con +1 a +3 puntos, cuando sus marcas saltaban de una barra a la otra; la mediana fue +0.18. |
| 26 oct | −0.90\* / −0.58 | +0.07 / +0.03 | 5 / 9 | Diferencia mediana −0.12; razón de spreads mediana 1.29; iguales 0 de 14; marca dentro del spread de Alpaca 6 de 14 | Vencimiento del 25 de noviembre. En vivo, el mid de Alpaca quedó arriba solo en 6 de 14 (antes, 8 y 11): el sesgo hacia arriba no se repitió. |
| 27 oct | −0.35 / −0.47 | +0.37 / +0.33 | 6 / 4 (de 11) | Diferencia mediana +0.42; razón de spreads mediana 1.00; iguales 0 de 14; marca dentro del spread de Alpaca 7 de 14 | Vencimiento del 27 de noviembre. A las 10:00 se descartaron tres barras interpoladas de contratos dentro del dinero. En vivo, las dos primeras respuestas de Robinhood llegaron con unos 6 y 4 minutos de atraso y la tercera quedó a 34 s de la foto de Alpaca; con fotos de Alpaca en bucle, la cuarta quedó pareada a 0.4 s. |
| 28 oct | −1.00 / −0.95 | +0.53 / +0.23 | 8 / 5 | Diferencia mediana +0.25; razón de spreads mediana 1.12; iguales 0 de 14; marca dentro del spread de Alpaca 6 de 14 | Vencimiento del 27 de noviembre. La foto en vivo quedó pareada al primer intento (1.95 s). El mid de Alpaca quedó arriba en 9 de 14. |
| 29 oct | — / +0.34 | — / +0.20 | — / 9 | Diferencia mediana +0.39; razón de spreads mediana 1.09; iguales 0 de 14; marca dentro del spread de Alpaca 7 de 14 | Solo las 10:00: la captura de las 09:45 se perdió. Son los mismos contratos que el 28. A las 10:00 el error del forward fue de 1.48, el mayor hasta ahora, y aun así el SPX implícito quedó a +0.34 del real. Foto en vivo pareada al primer intento (1.59 s). |
| 30 oct | +1.65\* / +1.87\* | +0.16 / −0.16 | 4 (de 12) / 9 | Diferencia mediana +0.75; razón de spreads mediana 1.28; iguales 0 de 14; marca dentro del spread de Alpaca 5 de 14 | Vencimiento del 30 de noviembre. Los dos cortes del SPX quedaron fuera de su minuto, con errores del forward chicos (0.27 y 0.20). A las 09:45 se descartaron dos barras interpoladas. En vivo, el mid de Alpaca quedó arriba en 10 de 14. Foto pareada al primer intento (1.32 s). |

## 7. Cómo repetir

```bash
python -m pytest -q tests/test_comparacion_robinhood.py
```

Con acceso a la rama privada, `comparar.py dia` y `comparar.py acumulado` reproducen las tablas de las
secciones 2, 3 y 6 a partir de lo importado y de las capturas de Alpaca (ver el README del experimento).
