# Exploración con datos gratuitos

**Fecha:** 2 de octubre de 2026. **Estado:** exploratorio. Nada de esto es evidencia del piloto ni del
experimento 0DTE, ni autoriza a operar.

## Para qué existe

Mientras la captura diaria junta sesiones, interesa saber si hay alguna pista con datos que ya existen y son
gratis. Aquí hay dos pruebas rápidas:

1. **SKEW de Cboe.** ¿El cambio diario del índice SKEW anticipa la dirección o el riesgo de SPY?
2. **Skew 0DTE con el historial de Alpaca.** Es la parte estadística del experimento
   `codex/0dte-skew-reversion`: ¿una desviación del skew intradía de SPY revierte en 30 minutos?

## Datos y licencias

| Fuente | Qué se usa | Condiciones |
|---|---|---|
| Cboe, CSV públicos de índices | SKEW y VIX diarios desde 1990 | Descarga pública. Los CSV no se suben al repositorio. |
| Alpaca, plan gratuito | SPY diario y por minuto (SIP); barras de 1 minuto de las opciones de SPY que vencen cada día, desde febrero de 2024 | Son operaciones, no cotizaciones: Alpaca no guarda compra/venta histórica de opciones. Los datos se guardan en `data/`, fuera de Git. |

Se descartó usar las cotizaciones diferidas de Cboe, porque sus condiciones prohíben descargarlas de forma
automática. Solo se publican agregados, en `resultados/`.

## Cómo correrlo

```bash
python experiments/exploracion-datos-gratis/skew_cboe.py
python experiments/exploracion-datos-gratis/descargar_0dte_alpaca.py --desde 2024-02-01 --hasta 2026-10-01   # ~1 hora
python experiments/exploracion-datos-gratis/skew_0dte_alpaca.py
python -m pytest -q tests/test_exploracion_datos_gratis.py
```

Necesita las claves de Alpaca en el entorno (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`).

## Cómo validar

**Versión.** Rama `claude/lucid-hamilton-hz8l80`, carpeta `experiments/exploracion-datos-gratis/`. Requiere
Python 3.11 o superior, las dependencias de `requirements-bloqueo.txt` y las claves gratuitas de Alpaca. Los
CSV de Cboe son públicos.

**Pasos.**
1. Corre las pruebas de las piezas de cálculo, sin red:
   `python -m pytest -q tests/test_exploracion_datos_gratis.py`. Deben dar 6 pruebas pasadas.
2. **SKEW.** Corre `python experiments/exploracion-datos-gratis/skew_cboe.py`. Descarga los datos a
   `data/exploracion/` y reescribe `resultados/skew_cboe.json`.
3. **0DTE.** Descarga el historial con
   `descargar_0dte_alpaca.py --desde 2024-02-01 --hasta 2026-10-01`. Tarda cerca de una hora y ocupa unos
   141 MB en `data/exploracion/0dte/`. Después corre `skew_0dte_alpaca.py`, que tarda unos 5 minutos y
   reescribe `resultados/skew_0dte_alpaca.json`.
   - **Sin descargar.** Con acceso al repo privado `QuantileFlow-datos`, se puede usar la copia de la rama
     `exploracion`. Tiene los mismos 669 archivos y la huella SHA-256 de cada uno. Su README dice cómo
     copiarla a `data/exploracion/0dte/`.
4. Comprueba que los dos JSON no cambiaron: `git diff experiments/exploracion-datos-gratis/resultados/`.
   - **SKEW.** La muestra está fija: SPY llega hasta el 1 de octubre de 2026, y que Cboe agregue días nuevos
     no la cambia. Los dividendos futuros de SPY reescalan todos los precios por igual, así que no cambian
     los rendimientos.
   - **0DTE.** El análisis usa todos los archivos de `data/exploracion/0dte/`: si se descarga otro rango,
     las cifras cambian. El bootstrap usa una semilla fija, 1729.
5. Revisa las cifras de las tablas de validación y los puntos débiles: los del SKEW, aquí abajo; los del
   0DTE, al final de la sección 2.

**Cifras del SKEW que se deben reproducir** (`resultados/skew_cboe.json`):

| Cifra | Valor |
|---|---|
| Sesiones y período | 2 698; del 4 de enero de 2016 al 1 de octubre de 2026 |
| t del cambio del SKEW sobre el día siguiente (solo / con controles / apertura a cierre) | −0.94 / −0.39 / 0.02 |
| t del cambio del SKEW por período (2016–2020 / 2021–2026) | −1.51 / +1.59 |
| R² fuera de muestra (con SKEW / referencia sin SKEW) | −3.5 % / −2.9 % |
| Acierto del signo (modelo / siempre sube) | 50.0 % / 54.1 % |
| t del nivel del SKEW sobre la volatilidad de 5 días (completo / 2016–2020 / 2021–2026) | −2.88 / −2.29 / −2.63 |

**Qué conviene mirar con ojo crítico en el SKEW.**
- **Hora.** El SKEW de cierre usa opciones de SPX, que cierran a las 16:15, y SPY cierra a las 16:00. Por
  eso se incluye la prueba de apertura a cierre del día siguiente.
- **Ventanas solapadas.** Los objetivos a 5 días se solapan; se usan errores de Newey-West con 5 rezagos.
- **Varias pruebas.** Se hicieron unas ocho regresiones. Un t de −2.9 resiste una corrección de Bonferroni
  simple, pero sigue siendo exploratorio.
- **SKEW no es RR25.** El SKEW mide la cola de toda la distribución; el RR25 compara puts y calls a 25 delta.

## 1. SKEW de Cboe frente a SPY (2016–2026)

Son 2 698 sesiones, del 4 de enero de 2016 al 1 de octubre de 2026. Todas las señales se conocen al cierre
del día *t* y el objetivo es el día siguiente o los 5 siguientes. Los errores estándar son de Newey-West. Se
ajustó con 2016–2020 y se evaluó fuera de muestra con 2021–2026.

**Dirección: no hay señal.**
- **Rendimiento del día siguiente:** el cambio del SKEW no lo anticipa. El estadístico t es −0.94; con
  controles, −0.39; de apertura a cierre, 0.02. A 5 días es 0.60.
- **El signo cambia según el período:** −1.51 en 2016–2020 y +1.59 en 2021–2026.
- **Fuera de muestra:** R² de −3.5 %, peor que no usarlo. Acierta el signo el 50.0 % de las veces, cuando
  apostar siempre a que sube acierta el 54.1 %.
- **Por quintiles:** no hay patrón en el rendimiento del día siguiente. Según el quintil del cambio del SKEW
  va de +0.4 a +13.4 puntos básicos, sin orden.

**Riesgo: una señal débil del nivel, no del cambio.**
- **El cambio diario del SKEW no añade nada al VIX** para el movimiento del día siguiente (t de 0.00) ni para
  la volatilidad de 5 días (t de −1.08).
- **El nivel del SKEW frente a su último año sí añade algo.** Con un SKEW alto, la volatilidad realizada de
  los 5 días siguientes sale algo menor de lo que indican el VIX y el movimiento del día:
  - es un 5 % menos por cada desviación típica;
  - el estadístico t es −2.88 en la muestra completa, −2.29 en 2016–2020 y −2.63 en 2021–2026.

**Lectura.** Con este índice no hay pista de dirección. Sobre el riesgo hay una relación pequeña y estable,
que encaja con el resultado posible «mejora solo de riesgo» del plan. Pero es una de varias pruebas, se mide
al cierre y el SKEW no es el RR25 del piloto. Sirve para orientar, no como evidencia.

## 2. Skew 0DTE de SPY con el historial de Alpaca (febrero de 2024 a octubre de 2026)

Son 669 sesiones, todas las del calendario, y 632 tienen base horaria. Los parámetros son los del
experimento `codex/0dte-skew-reversion`:
- cuadrícula de 5 minutos desde las 09:40;
- señal con |z| >= 2 frente a las 60 sesiones anteriores de la misma franja;
- entrada 5 minutos después de la señal y salida 30 minutos después de la entrada;
- bootstrap por bloques de 10 sesiones.

El RR25 se calcula con el precio de las operaciones de cada minuto, porque no hay compra/venta histórica.

**Qué se midió.**
- **Cobertura.** Hay RR25 válido en el 56 % de los puntos de la cuadrícula: el 48 % en 2024 y el 63 % en
  2026.
- **Perfil del día.** El RR25 medio baja a lo largo de la sesión: 4.0 puntos a las 09:40, 3.3 a mediodía y
  2.4 a las 15:10. Cerca del vencimiento vuelve a subir: 3.7 a las 15:40. Por eso hay que normalizar por hora.
- **Señales.** Hubo 442 señales. De ellas, 393 se pueden medir a 30 minutos, repartidas en 149 sesiones. En
  las medias, cada sesión pesa igual.

**Resultado: la desviación revierte, pero despacio.**

| Convergencia media por sesión (puntos de volatilidad, IC 95 %) | Todo | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| Ingenua, como el experimento: de la señal a +30 min | +1.27 [1.06, 1.52] | +0.82 | +1.47 | +1.39 |
| Operable, de la entrada (+5) a la salida (+35) | **+0.63 [0.43, 0.88]** | +0.42 [0.18, 0.70] | +0.96 [0.53, 1.51] | +0.43 [0.23, 0.63] |

- **La mitad de la convergencia ingenua es ruido de medida.** Al elegir los |z| más extremos se eligen
  también los errores de medida, que desaparecen en la observación siguiente. La convergencia operable no
  tiene ese sesgo.
- **La parte operable es positiva cada año** y su intervalo excluye el cero.
- **Crece con el tiempo y con el tamaño de la señal.**
  - Tras la entrada: +0.30 puntos a 10 minutos, +0.58 a 20, +0.63 a 30 y +0.78 a 45. Es una reversión
    gradual, no un salto, como cabría esperar de una reversión real.
  - No todos los años crecen igual. En 2024 deja de crecer después de 20 minutos: +0.48 a 20, +0.42 a 30 y
    +0.39 a 45.
  - Con |z| >= 3 es +1.17, frente a +0.56 con |z| entre 2 y 3. Pero son solo 74 señales y el intervalo es
    ancho: de 0.47 a 1.86.
- **Persistencia del residuo.** La pendiente es 0.93 a 5 minutos, 0.91 a 10 y 0.85 a 30. Descontando el
  ruido, cada 5 minutos conserva el 98.6 %: la vida media es de unas 4 horas. El ruido es solo el 1.4 % de la
  varianza total, pero pesa mucho en las observaciones extremas.

**Orden de magnitud de la ganancia.** Esto no es una medición, es una cuenta aproximada.
- **Cuánto vale un punto.** Una opción de SPY a 25 delta tiene una vega de unos 3.8 USD por contrato y punto
  de volatilidad, con SPY cerca de 600 y unas 3.5 horas al vencimiento. Según la hora, va de 3.5 a 4.2 USD.
- **Ganancia antes de costos.** Si el RR25 converge 0.63 puntos, un par de contratos (un put y un call)
  gana unos 2.4 USD.
- **Costos.** Entrar y salir de las dos patas son 4 ejecuciones. Con los supuestos del experimento, cada
  ejecución cuesta:
  - 0.65 USD de comisión;
  - 1 USD de deslizamiento, que son 0.01 USD por acción;
  - medio spread: 0.50 USD si el spread es de 1 centavo.

  En total son unos 8.6 USD, o 10.6 USD con un spread de 2 centavos. Eso sin contar la cobertura con SPY.
- **Punto de equilibrio.** Para cubrir 8.6 USD haría falta una convergencia de unos 2.3 puntos. La operable
  es de 0.63, y aun con |z| >= 3 es de 1.17.

Con esa cuenta, la reversión no pagaría los costos. La prueba de verdad necesita compra/venta histórica.

**Lectura.** La primera mitad de la hipótesis 0DTE tiene apoyo exploratorio: hay una reversión real y
estable del skew intradía, que no es solo ruido de medida. Pero es lenta, y su tamaño parece menor que los
costos de capturarla. Para decidir hace falta la segunda mitad, el replay con compra/venta y costos del
experimento. Requiere datos de cotizaciones, como ThetaData Value.

**Cifras del 0DTE que se deben reproducir** (`resultados/skew_0dte_alpaca.json`, tras descargar con
`--desde 2024-02-01 --hasta 2026-10-01`):

| Cifra | Valor |
|---|---|
| Sesiones / con base | 669 / 632 |
| Señales / medibles a 30 min / sesiones con señal medible | 442 / 393 / 149 |
| Cobertura del RR25 | 0.56 |
| Convergencia ingenua a 30 min | +1.274 [1.063, 1.515] |
| Convergencia operable a 30 min | +0.634 [0.432, 0.878] |
| Operable por año (2024 / 2025 / 2026) | +0.424 / +0.962 / +0.431 |
| Operable a 10 / 20 / 45 min | +0.299 / +0.580 / +0.777 |
| Operable con 2 <= \|z\| < 3 / con \|z\| >= 3 | +0.560 / +1.171 |
| Pendiente del residuo a 5 / 10 / 30 min | 0.929 / 0.910 / 0.854 |
| Persistencia sin ruido cada 5 min / parte de ruido | 0.986 / 0.014 |

**Qué conviene mirar con ojo crítico en el 0DTE.**
- **Precios.** Son de operaciones, no de compra/venta. El VWAP de un minuto rebota entre los dos lados, y las
  patas de cada punto pueden venir de minutos distintos dentro de la ventana de 5.
- **Modelo.** IV y delta son de Black-Scholes, con la tasa fija en 4.5 %, sin dividendos y con tiempo de
  calendario hasta las 16:00. SPY es americano, pero en el día del vencimiento la diferencia es pequeña.
- **Convenio.** RR25 = put − call, el del experimento; el piloto usa call − put.
- **Muestra.** El 44 % de los puntos no tiene RR25, por falta de operaciones a los dos lados de 25 delta. Las
  ausencias se dejan como ausencias, nunca como cero.
- **Horizontes.** Los de 10, 20 y 45 minutos y los cortes por |z| son descriptivos: el horizonte fijado era 30.
