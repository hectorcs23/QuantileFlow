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
2. Corre `python experiments/exploracion-datos-gratis/skew_cboe.py`. Descarga los datos a `data/exploracion/`
   y reescribe `resultados/skew_cboe.json`.
3. Comprueba que el JSON no cambió: `git diff experiments/exploracion-datos-gratis/resultados/`.
   - La muestra está fija: SPY llega hasta el 1 de octubre de 2026.
   - Que Cboe agregue días nuevos no la cambia.
   - Los dividendos futuros de SPY reescalan todos los precios por igual, así que no cambian los
     rendimientos.
4. Revisa las cifras de la tabla siguiente y los puntos débiles de la sección 1.

**Cifras que se deben reproducir** (`resultados/skew_cboe.json`):

| Cifra | Valor |
|---|---|
| Sesiones y período | 2 698; del 4 de enero de 2016 al 1 de octubre de 2026 |
| t del cambio del SKEW sobre el día siguiente (solo / con controles / apertura a cierre) | −0.94 / −0.39 / 0.02 |
| t del cambio del SKEW por período (2016–2020 / 2021–2026) | −1.51 / +1.59 |
| R² fuera de muestra (con SKEW / referencia sin SKEW) | −3.5 % / −2.9 % |
| Acierto del signo (modelo / siempre sube) | 50.0 % / 54.1 % |
| t del nivel del SKEW sobre la volatilidad de 5 días (completo / 2016–2020 / 2021–2026) | −2.88 / −2.29 / −2.63 |

**Qué conviene mirar con ojo crítico.**
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

## 2. Skew 0DTE de SPY con el historial de Alpaca

*En curso: la descarga de unas 670 sesiones termina el 2 de octubre.*
