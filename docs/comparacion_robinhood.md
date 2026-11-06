# Comparación con Robinhood

**Fecha:** 21 de octubre de 2026; totales al viernes 6 de noviembre. **Estado:** en curso; la revisión de las 10:27
suma una sesión por día y los totales se ponen al día los viernes.
**Código:** [`experiments/comparacion-robinhood/`](../experiments/comparacion-robinhood/), con los pasos de
cada día.

Solo se publican agregados. Los datos de Robinhood son para uso personal: quedan, con las cotizaciones de
Alpaca, en la rama privada `robinhood` de QuantileFlow-datos. El conector de Robinhood se usa solo para
leer datos de mercado, nunca para órdenes ni para ver la cuenta. Las claves de Alpaca están en el entorno
y no se escriben en ningún archivo.

## Resumen

- **El SPX implícito sirve.** En 50 cortes (26 sesiones, del 2 de octubre al 6 de noviembre), el nivel que
  sale de la paridad put-call de SPXW difiere del índice real en −0.07 puntos de media, con desviación de
  1.14. Es menos de lo que se mueve el SPX en ese mismo minuto: mediana de 3.2 puntos. En 39 de 50 cortes
  cae dentro del máximo y el mínimo del minuto; los otros 11 quedan a 1.21 puntos o menos.
- **Opciones fuera del dinero: cerca.** En 13 sesiones (168 comparaciones al corte), el mid de Alpaca
  queda +0.21 puntos sobre la marca de Robinhood en promedio (mediana +0.09). Son unos 0.08 puntos de
  volatilidad en promedio y 0.36 en el peor caso. La foto en vivo da lo mismo: +0.21 de media.
- **El bid y el ask de Alpaca no son los del mercado.** En las 12 fotos en vivo, ningún bid y ask de
  Alpaca coincide con el de Robinhood (0 de 168). El ancho típico se parece (razón mediana 1.06), pero
  los precios están corridos: la marca de Robinhood cae dentro del spread de Alpaca en 80 de 168 en vivo
  y en 176 de 329 al corte. El mid de Alpaca quedó arriba en 104 de 168.

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
| Cortes | 50 (26 sesiones × 09:45 y 10:00; el 29 de octubre y el 2 de noviembre, solo las 10:00) |
| Diferencia media (implícito − cierre del minuto) | −0.07 puntos |
| Mediana | −0.32 |
| Desviación | 1.14 (0.015 % del nivel) |
| Máxima en valor absoluto | 2.43 (5 de noviembre, 10:00) |
| Dentro del máximo y el mínimo del minuto | 39 de 50 |
| Distancia al rango de los 11 de afuera | 0.01 a 1.21 |
| Rango del SPX en ese minuto | 1.24 a 11.13; mediana 3.16 |

El error del forward que reporta la verificación no anticipa el tamaño de la diferencia (correlación
−0.01). El 29 de octubre, con el mayor error del forward del mes (1.48), la diferencia fue de +0.34. El
30, con errores chicos (0.27 y 0.20), los dos cortes quedaron fuera de su minuto. Las mayores diferencias
llegaron con el índice moviéndose rápido: +2.31 y +2.43 el 5 de noviembre y −2.42 el 6, en minutos de 5 a
11 puntos de rango; dos de esos tres cortes quedaron dentro de su minuto. Para el piloto basta: el nivel
implícito sigue al índice con un error menor que el ruido del propio minuto.

## 3. Opciones al corte (21 de octubre a 6 de noviembre)

Trece sesiones y 24 cortes (el 29 de octubre y el 2 de noviembre, solo las 10:00), con 14 contratos: 329
comparaciones. Se descartaron 7 barras interpoladas: 2 el 22, 3 el 27 y 2 el 30 de octubre. Vencimientos:
20, 23, 25, 27 y 30 de noviembre, y 2, 3, 4 y 7 de diciembre. Todas las cotizaciones de Alpaca tenían 23.9
segundos o menos (mediana 5.5).

| | Todas | Fuera del dinero |
|---|---:|---:|
| Comparaciones | 329 | 168 |
| Diferencia media (mid de Alpaca − marca) | +0.37 | +0.21 |
| Mediana | +0.14 | +0.09 |
| Desviación | 1.86 | 0.85 |
| Máxima en valor absoluto | 6.62 | 3.00 |
| Diferencia relativa (media y mediana) | +0.23 % y +0.14 % | +0.24 % y +0.19 % |
| En puntos de volatilidad (media, mediana y máxima) | | 0.08, 0.07 y 0.36 |
| Marca de Robinhood dentro del spread de Alpaca | 176 | 86 |

Los puntos de volatilidad salen de dividir cada diferencia, en valor absoluto, por la vega de
Black-Scholes del contrato (volatilidad de 15 %, plazo de su vencimiento). Las diferencias grandes están en
las opciones dentro del dinero, que el piloto no usa. Fuera del dinero, los spreads de Alpaca van de 0.06 a
4.85 puntos (mediana 0.89).

Parte de la diferencia puede ser de tiempo y no de calidad: la marca es la del instante del corte y cada
cotización de Alpaca tiene su propia edad (hasta 23.9 segundos en esta muestra).

## 4. Bid y ask en vivo (22 de octubre al 6 de noviembre)

Una foto por día, hacia las 10:30, con las mismas 14 opciones: 12 fotos. Por contrato, entre la
cotización de Alpaca y la de Robinhood hay 1.3 segundos de mediana y 26 como máximo, en cotizaciones de
Robinhood que no habían cambiado. Desde el 27 de octubre, `importar` exige que la foto de Alpaca salga a
menos de 5 s de la cotización más reciente de Robinhood. Fuera del dinero se define aquí con la delta de
Robinhood (|delta| < 0.5).

| | Todas | Fuera del dinero |
|---|---:|---:|
| Contratos | 168 | 84 |
| Diferencia media de mids (Alpaca − marca) | +0.50 | +0.21 |
| Mediana | +0.34 | +0.18 |
| Máxima en valor absoluto | 5.25 | 2.07 |
| En puntos de volatilidad, con la vega de Robinhood (media y máxima) | | 0.08 y 0.27 |
| Razón de spreads (Alpaca entre Robinhood), mediana | 1.06 | 1.15 |
| Mismo ancho (±5 %), más ancho y más angosto | 20, 85 y 63 | 10, 46 y 28 |
| Bid y ask iguales | 0 | 0 |
| El spread de Alpaca encierra al de Robinhood | 39 | 21 |
| Marca de Robinhood dentro del spread de Alpaca | 80 | 38 |

El feed `indicative` no copia el bid y el ask del mercado: los anchos se parecen, pero los precios están
corridos. Para el piloto importa el mid, y fuera del dinero su error típico es de menos de una décima de
punto de volatilidad. El mid de Alpaca quedó arriba en 104 de 168 contratos, y en más de la mitad en 11 de
los 12 días: hay un sesgo chico hacia arriba (mediana +0.18 fuera del dinero), que se mantiene desde la
primera semana.

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
| 2 nov | — / −0.79 | — / −0.12 | — / 11 | Diferencia mediana +0.40; razón de spreads mediana 1.25; iguales 0 de 14; marca dentro del spread de Alpaca 7 de 14 | Solo las 10:00: la captura de las 09:45 se perdió. Vencimiento del 2 de diciembre. Primer día con horario de invierno: las ventanas siguieron al corte, a las 15:00 UTC. En vivo, el mid de Alpaca quedó arriba en 9 de 14. Foto pareada al primer intento (1.69 s). |
| 3 nov | −0.96 / −0.30 | +0.41 / −0.04 | 10 / 7 | Diferencia mediana +0.54; razón de spreads mediana 1.18; iguales 0 de 14; marca dentro del spread de Alpaca 7 de 14 | Vencimiento del 3 de diciembre. A las 10:00, fuera del dinero, la mediana fue −0.41 y solo 2 de las 7 marcas quedaron dentro del spread de Alpaca. En vivo, el mid de Alpaca quedó arriba en 9 de 14. Foto pareada al primer intento (2.08 s). |
| 4 nov | −0.76 / +1.26\* | −0.10 / +0.09 | 9 / 10 | Diferencia mediana +0.90; razón de spreads mediana 1.05; iguales 0 de 14; marca dentro del spread de Alpaca 6 de 14 | Vencimiento del 4 de diciembre. A las 10:00 el SPX implícito quedó fuera de su minuto, a 0.06 de la apertura del minuto siguiente. En vivo, la diferencia mediana es la mayor hasta ahora; el mid de Alpaca quedó arriba en 8 de 14. Foto pareada al primer intento (1.21 s). |
| 5 nov | +2.31 / +2.43\* | −0.33 / +0.11 | 5 / 10 | Diferencia mediana +0.22; razón de spreads mediana 0.98; iguales 0 de 14; marca dentro del spread de Alpaca 12 de 14 | Vencimiento del 4 de diciembre. Con el índice cayendo unos 78 puntos entre las 09:40 y las 09:57, el SPX implícito quedó 2.3 y 2.4 puntos por encima del real: las dos mayores diferencias hasta ahora. A las 09:45 solo 1 de las 7 marcas fuera del dinero quedó dentro del spread de Alpaca. En vivo, por primera vez la razón de spreads mediana quedó debajo de 1, y 12 de 14 marcas quedaron dentro del spread de Alpaca, el máximo hasta ahora. Foto pareada al primer intento (1.25 s). |
| 6 nov | −1.52 / −2.42 | +0.91 / +0.58 | 7 / 10 | Diferencia mediana +0.10; razón de spreads mediana 1.17; iguales 0 de 14; marca dentro del spread de Alpaca 5 de 14 | Vencimiento del 7 de diciembre. Con el SPX unos 185 puntos por debajo del jueves, la media fuera del dinero de las 09:45, +0.91, es la más alta hasta ahora; en puntos de volatilidad son 0.12 de media y 0.34 como máximo. Los dos cortes del SPX quedaron dentro de su minuto. En vivo, el mid de Alpaca quedó arriba en 8 de 14. Foto pareada al primer intento (1.17 s). |

## 7. Cómo repetir

```bash
python -m pytest -q tests/test_comparacion_robinhood.py
```

Con acceso a la rama privada, `comparar.py dia` y `comparar.py acumulado` reproducen las tablas de las
secciones 2, 3 y 6 a partir de lo importado y de las capturas de Alpaca (ver el README del experimento).
