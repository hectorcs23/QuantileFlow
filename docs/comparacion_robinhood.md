# Comparación con Robinhood

**Fecha:** 21 de octubre de 2026; totales al viernes 27 de noviembre. **Estado:** en curso; la revisión de las 10:27
suma una sesión por día y los totales se ponen al día los viernes.
**Código:** [`experiments/comparacion-robinhood/`](../experiments/comparacion-robinhood/), con los pasos de
cada día.

Solo se publican agregados. Los datos de Robinhood son para uso personal: quedan, con las cotizaciones de
Alpaca, en la rama privada `robinhood` de QuantileFlow-datos. El conector de Robinhood se usa solo para
leer datos de mercado, nunca para órdenes ni para ver la cuenta. Las claves de Alpaca están en el entorno
y no se escriben en ningún archivo.

## Resumen

- **El SPX implícito sirve.** En 77 cortes (40 sesiones, del 2 de octubre al 27 de noviembre), el nivel que
  sale de la paridad put-call de SPXW difiere del índice real en −0.06 puntos de media, con desviación de
  1.49. Es menos de lo que se mueve el SPX en ese mismo minuto: mediana de 4.07 puntos. En 62 de 77 cortes
  cae dentro del máximo y el mínimo del minuto; los otros 15 quedan a 1.35 puntos o menos.
- **Opciones fuera del dinero: cerca.** En 27 sesiones (357 comparaciones al corte), el mid de Alpaca
  queda +0.24 puntos sobre la marca de Robinhood en promedio (mediana +0.14). Son unos 0.12 puntos de
  volatilidad en promedio (mediana 0.09); el peor caso, 1.61, salió en el corte ruidoso de las 09:45 del 23
  de noviembre. La foto en vivo da algo más: +0.33 de media.
- **El bid y el ask de Alpaca no son los del mercado.** En las 26 fotos en vivo, ningún bid y ask de
  Alpaca coincide con el de Robinhood (0 de 364). El ancho típico se parece (razón mediana 1.14), pero
  los precios están corridos: la marca de Robinhood cae dentro del spread de Alpaca en 180 de 364 en vivo
  y en 365 de 702 al corte. El mid de Alpaca quedó arriba en 226 de 364, y en más de la mitad de los
  contratos en 22 de los 26 días. Desde el 9 de noviembre la razón de spreads mediana varía más: de 0.85 a
  1.80 por día (antes, de 0.98 a 1.29).
- **SPY, desde el 12 de noviembre.** Diez días válidos: el mid de Alpaca queda a unos centavos de la marca
  de Robinhood (fuera del dinero, +0.03 dólares de media al corte y +0.03 en vivo). Los spreads varían más
  (razón mediana 1.25; por día, de 0.97 a 3.07). El 19 todas las cotizaciones de SPY de Alpaca eran del
  cierre anterior y ese día se excluyó. Todavía es poco para concluir.

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
| Cortes | 77 (40 sesiones × 09:45 y 10:00; el 29 de octubre y el 2 y el 13 de noviembre, solo las 10:00) |
| Diferencia media (implícito − cierre del minuto) | −0.06 puntos |
| Mediana | −0.11 |
| Desviación | 1.49 (0.020 % del nivel) |
| Máxima en valor absoluto | 5.18 (24 de noviembre, 09:45) |
| Dentro del máximo y el mínimo del minuto | 62 de 77 |
| Distancia al rango de los 15 de afuera | 0.01 a 1.35 |
| Rango del SPX en ese minuto | 1.24 a 14.50; mediana 4.07 |

El error del forward que reporta la verificación no anticipa el tamaño de la diferencia (correlación
0.11). El 29 de octubre, con el mayor error del forward del mes (1.48), la diferencia fue de +0.34. El
30, con errores chicos (0.27 y 0.20), los dos cortes quedaron fuera de su minuto. Las mayores diferencias
llegaron con el índice moviéndose rápido: +2.31 y +2.43 el 5 de noviembre y −2.42 el 6, en minutos de 5 a
11 puntos de rango; dos de esos tres cortes quedaron dentro de su minuto. El 10 de noviembre, con el índice
subiendo, −2.09 a las 10:00, también dentro, y la mayor, −2.66 el 19 a las 09:45, también. El 20, con el
SPX 3.5 % abajo y subiendo, un corte quedó 1.35 puntos fuera de su minuto. Las dos mayores llegaron
después, en los cortes ruidosos de las 09:45 del 23 y el 24 (−3.57 y −5.18), y las dos quedaron dentro de
su minuto, de hasta 14.5 puntos de rango. Para el piloto basta: el nivel
implícito sigue al índice con un error menor que el ruido del propio minuto.

## 3. Opciones al corte (21 de octubre a 27 de noviembre)

Veintisiete sesiones y 51 cortes (el 29 de octubre y el 2 y el 13 de noviembre, solo las 10:00), con 14
contratos de SPXW: 702 comparaciones. Robinhood marcó 16 barras como interpoladas, en diez cortes; las 12
que caían en el corte no se usan. Vencimientos: 20, 23, 25, 27 y 30 de noviembre, y 2, 3, 4, 7, 9, 10, 11,
14, 16, 17, 18, 21, 23, 24 y 28 de diciembre. Todas las cotizaciones de Alpaca de SPXW tenían 30.7 segundos o
menos (mediana 5.4); las de 30.7, en el corte de las 09:45 del 24 de noviembre.

| | Todas | Fuera del dinero |
|---|---:|---:|
| Comparaciones | 702 | 357 |
| Diferencia media (mid de Alpaca − marca) | +0.40 | +0.24 |
| Mediana | +0.25 | +0.14 |
| Desviación | 2.29 | 1.40 |
| Máxima en valor absoluto | 14.07 | 13.30 |
| Diferencia relativa (media y mediana) | +0.24 % y +0.22 % | +0.25 % y +0.24 % |
| En puntos de volatilidad (media, mediana y máxima) | | 0.12, 0.09 y 1.61 |
| Marca de Robinhood dentro del spread de Alpaca | 365 | 179 |

Los puntos de volatilidad salen de dividir cada diferencia, en valor absoluto, por la vega de
Black-Scholes del contrato (volatilidad de 15 %, plazo de su vencimiento). Las diferencias grandes están en
las opciones dentro del dinero, que el piloto no usa. Fuera del dinero, los spreads de Alpaca van de 0.01 a
15.68 puntos (mediana 1.09). Las seis mayores diferencias fuera del dinero, de 4.4 a 13.3 puntos, salieron en
los cortes ruidosos del 23 y el 24 de noviembre, con spreads de Alpaca de hasta 15.68; sin esos dos días, la
máxima es 3.97.

Parte de la diferencia puede ser de tiempo y no de calidad: la marca es la del instante del corte y cada
cotización de Alpaca tiene su propia edad (hasta 30.7 segundos en esta muestra).

## 4. Bid y ask en vivo (22 de octubre al 27 de noviembre)

Una foto por día, entre las 10:30 y las 11:05, con las mismas 14 opciones de SPXW: 26 fotos. Por contrato,
entre la cotización de Alpaca y la de Robinhood hay 1.1 segundos de mediana y 29.5 como máximo, en cotizaciones de
Robinhood que no habían cambiado. Desde el 27 de octubre, `importar` exige que la foto de Alpaca salga a
menos de 5 s de la cotización más reciente de Robinhood. Fuera del dinero se define aquí con la delta de
Robinhood (|delta| < 0.5).

| | Todas | Fuera del dinero |
|---|---:|---:|
| Contratos | 364 | 183 |
| Diferencia media de mids (Alpaca − marca) | +0.43 | +0.33 |
| Mediana | +0.36 | +0.25 |
| Máxima en valor absoluto | 6.81 | 3.32 |
| En puntos de volatilidad, con la vega de Robinhood (media y máxima) | | 0.10 y 0.43 |
| Razón de spreads (Alpaca entre Robinhood), mediana | 1.14 | 1.22 |
| Mismo ancho (±5 %), más ancho y más angosto | 34, 197 y 133 | 16, 106 y 61 |
| Bid y ask iguales | 0 | 0 |
| El spread de Alpaca encierra al de Robinhood | 90 | 51 |
| Marca de Robinhood dentro del spread de Alpaca | 180 | 91 |

El feed `indicative` no copia el bid y el ask del mercado: los anchos se parecen, pero los precios están
corridos. Para el piloto importa el mid, y fuera del dinero su error típico es de menos de una décima de
punto de volatilidad. El mid de Alpaca quedó arriba en 226 de 364 contratos, y en más de la mitad en 22 de
los 26 días: hay un sesgo chico hacia arriba (mediana +0.25 fuera del dinero), que se mantiene desde la
primera semana y fue el más fuerte el 27 de noviembre (12 de 14 y diferencia mediana de +1.64).

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
- **Cotizaciones viejas de Alpaca.** Los totales solo usan cotizaciones de Alpaca con 60 s o menos. El 19 de
  noviembre todas las de SPY eran del cierre del 18, en las capturas y en vivo, y quedaron fuera. Antes,
  ninguna había pasado de 30 s.
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
| 9 nov | −1.61 / −1.17 | +0.63 / +0.48 | 8 / 6 | Diferencia mediana +0.64; razón de spreads mediana 1.54; iguales 0 de 14; marca dentro del spread de Alpaca 7 de 14 | Vencimiento del 9 de diciembre. En vivo, la razón de spreads mediana, 1.54, es la más alta hasta ahora: el spread de Alpaca salió más ancho que el de Robinhood. El mid de Alpaca quedó arriba en 8 de 14. Foto pareada al primer intento (1.29 s). |
| 10 nov | +1.13 / −2.09 | +0.07 / +0.71 | 7 / 5 | Diferencia mediana +0.30; razón de spreads mediana 1.76; iguales 0 de 14; marca dentro del spread de Alpaca 6 de 14 | Vencimiento del 10 de diciembre. A las 10:00, con el índice subiendo unos 27 puntos entre las 09:52 y las 10:00, el SPX implícito quedó 2.09 por debajo del real, dentro de su minuto: es la cuarta mayor diferencia de 54 cortes. En vivo, la razón de spreads mediana, 1.76, vuelve a ser la más alta hasta ahora (1.54 el 9): el spread de Alpaca salió más ancho en 9 de 14 contratos, igual en 1 y más angosto en 4. El mid de Alpaca quedó arriba en 9 de 14. Foto pareada al primer intento (1.07 s). |
| 11 nov | +1.24 / −0.05 | +0.24 / +0.52 | 4 (de 13) / 4 | Diferencia mediana +0.12; razón de spreads mediana 1.54; iguales 0 de 14; marca dentro del spread de Alpaca 8 de 14 | Vencimiento del 11 de diciembre. A las 09:45 se descartó una barra interpolada. En vivo, tercer día seguido con la razón de spreads mediana en 1.5 o más (1.54 el 9 y 1.76 el 10; antes, como mucho 1.29): el spread de Alpaca salió más ancho en 9 de 14 contratos, igual en 3 y más angosto en 2. El mid de Alpaca quedó arriba en 9 de 14. Foto pareada al primer intento (1.06 s). |
| 12 nov | −1.88 / −0.35 | +0.46 / +0.31 | 9 / 8 | Diferencia mediana +0.35; razón de spreads mediana 1.07; iguales 0 de 14; marca dentro del spread de Alpaca 8 de 14 | Vencimiento del 11 de diciembre. En vivo, la razón de spreads mediana vuelve a 1.07, después de tres días en 1.5 o más. El mid de Alpaca quedó arriba en 8 de 14. Primer día con 28 contratos (14 de SPY, en su tabla); foto pareada al primer intento (1.19 s). |
| 13 nov | — / +0.60\* | — / +0.57 | — / 7 | Diferencia mediana −0.01; razón de spreads mediana 1.80; iguales 0 de 14; marca dentro del spread de Alpaca 10 de 14 | Solo las 10:00: la captura de las 09:45 se perdió. Vencimiento del 14 de diciembre. El SPX implícito quedó 0.23 puntos por encima del máximo de su minuto. En vivo, la razón de spreads mediana, 1.80, es la más alta hasta ahora; el mid de Alpaca quedó arriba en 7 de 14. Foto pareada al primer intento (0.99 s). |
| 16 nov | −1.96 / +0.72 | +0.48 / +0.06 | 8 (de 13) / 3 (de 11) | Diferencia mediana +0.98; razón de spreads mediana 0.98; iguales 0 de 14; marca dentro del spread de Alpaca 6 de 14 | Vencimiento del 16 de diciembre. A las 09:45 se descartó una barra interpolada y a las 10:00, tres, todas dentro del dinero. A las 10:00, fuera del dinero, solo 1 de las 7 marcas quedó dentro del spread de Alpaca. En vivo, la diferencia mediana, +0.98, es la mayor hasta ahora (+0.90 el 4 de noviembre), y la razón de spreads mediana, 0.98, iguala la menor (el 5 de noviembre): el spread de Alpaca salió más ancho en 7 de 14 contratos y más angosto en 7. El mid de Alpaca quedó arriba en 11 de 14. Foto pareada al primer intento (1.52 s). |
| 17 nov | +1.80 / +1.91\* | +0.36 / −0.54 | 6 / 4 | Diferencia mediana −0.01; razón de spreads mediana 0.94; iguales 0 de 14; marca dentro del spread de Alpaca 7 de 14 | Vencimiento del 17 de diciembre. A las 10:00 el SPX implícito quedó 0.04 puntos por encima del máximo de su minuto. A las 10:00, fuera del dinero, solo 1 de las 7 marcas quedó dentro del spread de Alpaca, como el 16. En vivo, la razón de spreads mediana, 0.94, es la menor hasta ahora (0.98 el 5 y el 16 de noviembre): el spread de Alpaca salió más ancho en 7 de 14 contratos y más angosto en 7. El mid de Alpaca quedó arriba en 7 de 14. Foto pareada con fotos de Alpaca en bucle, a 0.05 s. |
| 18 nov | +0.62 / −0.07 | −0.16 / +0.63 | 6 / 6 | Diferencia mediana +0.29; razón de spreads mediana 1.33; iguales 0 de 14; marca dentro del spread de Alpaca 5 de 14 | Vencimiento del 18 de diciembre, strikes de 7 025 a 7 625. Los dos cortes del SPX quedaron dentro de su minuto, aunque el índice subió unos 30 puntos entre las 09:50 y las 10:00. En vivo, el spread de Alpaca salió más ancho en 9 de 14 contratos y más angosto en 5; el mid de Alpaca quedó arriba en 8 de 14. Foto pareada con fotos de Alpaca en bucle, a 0.54 s. |
| 19 nov | −2.66 / +1.27 | +0.60 / −0.17 | 4 / 6 | Diferencia mediana +0.48; razón de spreads mediana 1.38; iguales 0 de 14; marca dentro del spread de Alpaca 5 de 14 | Vencimiento del 18 de diciembre, strikes de 7 100 a 7 700. A las 09:45 el SPX implícito quedó 2.66 puntos por debajo del real, dentro de su minuto: es la mayor diferencia de 67 cortes (antes, 2.43). A las 09:45, fuera del dinero, solo 1 de las 7 marcas quedó dentro del spread de Alpaca. En vivo, el spread de Alpaca salió más ancho en 9 de 14 contratos y más angosto en 5; el mid de Alpaca quedó arriba en 9 de 14. Foto pareada con fotos de Alpaca en bucle, a 0.85 s. |
| 20 nov | +0.64 / +2.60\* | +0.29 / +0.42 | 11 / 10 | Diferencia mediana +0.03; razón de spreads mediana 1.68; iguales 0 de 14; marca dentro del spread de Alpaca 8 de 14 | Vencimiento del 21 de diciembre, strikes de 6 850 a 7 450. El SPX implícito de las 09:45 quedó unos 256 puntos (3.5 %) por debajo del jueves. A las 10:00, con el índice subiendo unos 35 puntos desde las 09:50, quedó 1.35 puntos por encima del máximo de su minuto. Al corte, 11 y 10 de las 14 marcas quedaron dentro del spread de Alpaca. En vivo, el spread de Alpaca salió más ancho en 8 de 14 contratos, más angosto en 5 e igual en 1; el mid de Alpaca quedó arriba en 7 de 14. Foto pareada con fotos de Alpaca en bucle, a 0.63 s. |
| 23 nov | +1.97 / −3.57 | −1.09 / +0.36 | 11 / 8 | Diferencia mediana +1.26; razón de spreads mediana 1.27; iguales 0 de 14; marca dentro del spread de Alpaca 9 de 14 | Vencimiento del 23 de diciembre, strikes de 6 900 a 7 500. A las 10:00, con el índice subiendo unos 45 puntos desde las 09:50, el SPX implícito quedó 3.57 puntos por debajo del real, dentro de un minuto de 8 puntos de rango: es la mayor diferencia de 71 cortes (antes, 2.66). A las 09:45 los spreads de Alpaca cerca del dinero fueron muy anchos y la media fuera del dinero, −1.09, es la mayor en valor absoluto hasta ahora. En vivo, la diferencia mediana, +1.26, también es la mayor (antes, +0.98): el mid de Alpaca quedó arriba en 10 de 14 y su spread salió más ancho en 11. Foto pareada con fotos de Alpaca en bucle, a 1.32 s. |
| 24 nov | −5.18 / +1.82\* | +2.33 / −0.24 | 9 / 10 | Diferencia mediana +0.13; razón de spreads mediana 0.85; iguales 0 de 14; marca dentro del spread de Alpaca 7 de 14 | Vencimiento del 24 de diciembre (cierra a las 13:00 por Nochebuena), strikes de 6 875 a 7 475. A las 09:45, con cotizaciones de Alpaca de unos 20 s, un error del forward de 0.80 y un minuto de 14.5 puntos de rango, el SPX implícito quedó 5.18 puntos por debajo del real, dentro del minuto: otra vez la mayor diferencia (antes, 3.57 el 23). En ese corte la media fuera del dinero, +2.33, también es la mayor. A las 10:00 el implícito quedó 0.84 puntos por encima del máximo de su minuto. En vivo, la razón de spreads mediana, 0.85, es la menor hasta ahora: el spread de Alpaca salió más angosto en 8 de 14 y más ancho en 6. El mid de Alpaca quedó arriba en 8 de 14. Foto pareada con fotos de Alpaca en bucle, a 1.17 s. |
| 25 nov | +2.94 / +1.02 | −0.05 / −0.66 | 10 / 7 | Diferencia mediana +0.31; razón de spreads mediana 1.03; iguales 0 de 14; marca dentro del spread de Alpaca 9 de 14 | Vencimiento del 24 de diciembre, strikes de 6 675 a 7 275 (cinco de los contratos, los mismos que el 24). Con el índice subiendo unos 71 puntos entre los cortes, el SPX implícito quedó dentro de su minuto en los dos. A las 09:45 las cotizaciones de Alpaca tenían 6 s de edad mediana, pero el spread cerca del dinero era ancho y la banda del RR25 llegó a 1.30 puntos; aun así, la media fuera del dinero fue −0.05. En vivo, el spread de Alpaca salió más ancho en 8 de 14 y más angosto en 6; el mid de Alpaca quedó arriba en 9 de 14. Foto pareada con fotos de Alpaca en bucle, a 0.83 s. |
| 27 nov | −1.56 / +1.01 | −0.47 / +1.02 | 7 / 5 | Diferencia mediana +1.64; razón de spreads mediana 1.04; iguales 0 de 14; marca dentro del spread de Alpaca 5 de 14 | Vencimiento del 28 de diciembre, strikes de 6 950 a 7 550. Sesión corta (cierre a las 13:00) después de Acción de Gracias. Los dos cortes quedaron dentro de su minuto. A las 10:00 la media fuera del dinero, +1.02, es la segunda mayor hasta ahora (la mayor, +2.33 el 24). En vivo, la diferencia mediana, +1.64, es la mayor hasta ahora (antes, +1.26 el 23): el mid de Alpaca quedó arriba en 12 de 14 y la marca de Robinhood dentro del spread de Alpaca solo en 5. El spread de Alpaca salió más ancho en 8 y más angosto en 5. Foto pareada con fotos de Alpaca en bucle, a 0.76 s. |

### SPY, desde el 12 de noviembre

Las mismas medidas con 14 contratos de SPY a unos 30 días: strikes del precio de IEX ±10, ±20 y ±30
dólares. Diferencias en dólares por acción, Alpaca menos Robinhood. Mide el feed que usa el
[comparador de contratos con SPY](contratos_observados_spy.md).

| Sesión | Opciones fuera del dinero, media 09:45 / 10:00 | Marca dentro del spread (de 14) | En vivo | Notas |
|---|---|---|---|---|
| 12 nov | +0.01 / +0.03 | 9 / 7 | Diferencia mediana +0.015; razón de spreads mediana 1.11; iguales 0 de 14; marca dentro del spread de Alpaca 8 de 14 | Primer día. Vencimiento del 11 de diciembre, strikes de 727 a 787. Fuera del dinero, el mid de Alpaca quedó 0.1 % y 0.6 % por encima de la marca de Robinhood en los cortes. En vivo, los spreads de Alpaca fueron de 1 centavo a 1.78 dólares (Robinhood, de 3 centavos a 2.22): más anchos en 7 de 14, iguales en 3 y más angostos en 4. El mid de Alpaca quedó arriba en 9 de 14. |
| 13 nov | — / +0.02 | — / 5 | Diferencia mediana +0.05; razón de spreads mediana 1.13; iguales 0 de 14; marca dentro del spread de Alpaca 5 de 14 | Solo las 10:00. Vencimiento del 11 de diciembre, strikes de 725 a 785: desde hoy, múltiplos de 5, porque Robinhood no lista el 724. Spreads de Alpaca más anchos en 8 de 14, iguales en 2 y más angostos en 4. El mid de Alpaca quedó arriba en 8 de 14. |
| 16 nov | 0.00 / +0.04 | 5 / 8 | Diferencia mediana +0.005; razón de spreads mediana 1.31; iguales 0 de 14; marca dentro del spread de Alpaca 8 de 14 | Vencimiento del 18 de diciembre, strikes de 720 a 780. Spreads de Alpaca más anchos en 11 de 14 y más angostos en 3; fuera del dinero, la razón mediana fue 2.0. El mid de Alpaca quedó arriba en 7 de 14. |
| 17 nov | +0.06 / +0.02 | 6 / 6 | Diferencia mediana −0.055; razón de spreads mediana 3.07; iguales 0 de 14; marca dentro del spread de Alpaca 4 de 14 | Vencimiento del 18 de diciembre, strikes de 710 a 770. En vivo, la razón de spreads mediana, 3.07, es la más alta en SPY hasta ahora (de 1.11 a 1.31 antes): Robinhood mostró spreads de 1 centavo en 7 de 14 contratos y el de Alpaca salió más ancho en 13 de 14. La diferencia mediana es la primera negativa en SPY; el mid de Alpaca quedó arriba en 6 de 14. |
| 18 nov | 0.00 / 0.00 | 7 / 7 | Diferencia mediana −0.05; razón de spreads mediana 1.35; iguales 0 de 14; marca dentro del spread de Alpaca 4 de 14 | Vencimiento del 18 de diciembre, strikes de 700 a 760. Fuera del dinero, la media fue 0.00 en los dos cortes. En vivo, Robinhood no mostró spreads de 1 centavo (5 a 31 centavos) y la razón mediana volvió a 1.35; el spread de Alpaca salió más ancho en 9 de 14 y más angosto en 5. Segundo día con la diferencia mediana negativa; el mid de Alpaca quedó arriba en 6 de 14. |
| 19 nov | — / — | — / — | Excluido | **Sin datos válidos de Alpaca.** Todas las cotizaciones de SPY, en las dos capturas y en la foto en vivo, eran las del cierre del 18 (21:14:59 UTC): unas 17.5 horas de antigüedad. Robinhood sí mostró SPY operando. No entran en los totales. |
| 20 nov | +0.03 / +0.02 | 6 / 6 | Diferencia mediana +0.05; razón de spreads mediana 1.00; iguales 0 de 14; marca dentro del spread de Alpaca 5 de 14 | Vencimiento del 18 de diciembre, strikes de 685 a 745. Las cotizaciones de Alpaca volvieron a llegar al día. En vivo, el spread de Alpaca salió más ancho en 6 de 14, más angosto en 6 e igual en 2; el mid de Alpaca quedó arriba en 9 de 14. |
| 23 nov | +0.07 / +0.09 | 11 / 6 | Diferencia mediana +0.04; razón de spreads mediana 0.99; iguales 0 de 14; marca dentro del spread de Alpaca 9 de 14 | Vencimiento del 24 de diciembre, strikes de 685 a 745. En vivo, el spread de Alpaca salió más ancho en 6 de 14, más angosto en 7 e igual en 1; el mid de Alpaca quedó arriba en 11 de 14. |
| 24 nov | −0.02 / +0.02 | 12 / 7 | Diferencia mediana +0.04; razón de spreads mediana 1.34; iguales 0 de 14; marca dentro del spread de Alpaca 10 de 14 | Los mismos contratos que el 23. En vivo, el spread de Alpaca salió más ancho en 11 de 14 y más angosto en 3; el mid de Alpaca quedó arriba en 10 de 14. |
| 25 nov | 0.00 / +0.05 | 8 / 4 | Diferencia mediana +0.05; razón de spreads mediana 0.97; iguales 0 de 14; marca dentro del spread de Alpaca 9 de 14 | Strikes de 665 a 725 (cinco de los contratos, los mismos que el 24). Cotizaciones de Alpaca frescas en todos los contratos. En vivo, el spread de Alpaca salió más ancho en 6 de 14 y más angosto en 8; el mid de Alpaca quedó arriba en 8 de 14. |
| 27 nov | +0.06 / +0.06 | 6 / 9 | Diferencia mediana +0.10; razón de spreads mediana 1.25; iguales 0 de 14; marca dentro del spread de Alpaca 11 de 14 | Strikes de 690 a 750, del mismo vencimiento del 24 de diciembre. En vivo, el spread de Alpaca salió más ancho en 12 de 14 y más angosto en 1; el mid de Alpaca quedó arriba en 9 de 14. |

## 7. Cómo repetir

```bash
python -m pytest -q tests/test_comparacion_robinhood.py
```

Con acceso a la rama privada, `comparar.py dia` y `comparar.py acumulado` reproducen las tablas de las
secciones 2, 3 y 6 a partir de lo importado y de las capturas de Alpaca (ver el README del experimento).
