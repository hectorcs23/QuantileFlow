# Revisión del primer informe piloto

**Fecha:** 30 de octubre de 2026.
**Informe:** [`reports/piloto/informe.md`](../reports/piloto/informe.md), con la configuración `piloto-0.3`
y 21 sesiones reales, del 2 al 30 de octubre.

## Resumen

- **Dictamen: apto con limitaciones.** Falla un solo criterio, que no es crítico: casi todas las sesiones
  tienen alertas de sincronía. Es un umbral mal puesto, no un problema de los datos (sección 4).
- **RR25 a 30 días:** identificado en 20 de 21 sesiones. El 29 de octubre se perdió la captura de las
  09:45. Fue de −2.95 puntos de volatilidad (6 de octubre) a −6.23 (23 de octubre); el 30 quedó en
  −5.84. La banda que sale del bid y el ask es de unos ±0.1 puntos (ancho mediano 0.23).
- **Estable entre las 09:45 y las 10:00:** cambia 0.09 puntos de mediana, menos que el ancho de su banda
  (0.23).
- **Etiquetas:** 20 de 21 sesiones tienen el rendimiento de SPY a 1 sesión. Todas son provisionales: la
  política de dividendos espera 60 días, así que las primeras se aceptan a principios de diciembre.
- **Lo que no dice:** este piloto mide si los datos sirven, no si hay capacidad predictiva. La medición es
  indicativa: el feed gratis de Alpaca modifica las cotizaciones.
- **Propuesta para aprobar:** `piloto-0.4`, con un solo cambio, `desfase_spot_max_s` de 2 a 10 s. En una
  prueba, el dictamen pasa a «apto para ampliar historia». No se aplicó.

## 1. Cómo se hizo

```bash
python3 scripts/normalizar_alpaca.py --desde 2026-10-02 --hasta 2026-10-30 --datos ../quantileflow-datos
N=../quantileflow-datos/normalized/alpaca
python3 scripts/piloto.py --cotizaciones $N/cotizaciones.parquet --subyacente $N/subyacente.parquet \
    --dividendos $N/dividendos.parquet --cobertura-dividendos $N/cobertura_dividendos.parquet \
    --fuente-objetivo alpaca/sip --desde 2026-10-02 --hasta 2026-10-30
```

Entraron 41 capturas, 42 cortes del SIP de SPY y 23 consultas de dividendos. Las tablas normalizadas
quedan en `normalized/` del repositorio de datos, que Git ignora.

En [`reports/piloto/`](../reports/piloto/) se publican el informe, las cuatro gráficas y el manifiesto.
`tabla_diaria.csv`, `tabla_todas_las_horas.csv` y `etiquetas.csv` no se suben: traen niveles del SPX
implícito y mids de SPY del SIP, que no se pueden redistribuir. Se regeneran con los mismos comandos, y
sus huellas están en el manifiesto.

## 2. Dictamen y criterios

| Criterio | Valor | Umbral | Cumple |
|---|---:|---|---|
| Sesiones en la muestra | 21 | ≥ 20 | sí |
| RR25 a 30 días identificado a las 09:45 | 0.952 (20 de 21) | ≥ 0.9 | sí |
| Cambio diario de RR25 disponible | 0.900 (18 de 20) | ≥ 0.8 | sí |
| Estabilidad 09:45–10:00 (mediana del cambio / ancho de banda) | 0.393 | ≤ 1.0 | sí |
| Sesiones con alertas de sincronía, edad o disponibilidad | 0.952 | ≤ 0.2 | **no** |
| Etiqueta de SPY a 1 sesión disponible | 0.952 | ≥ 0.9 | sí |

El cambio diario se cuenta sobre las 20 sesiones procesadas. Falta en dos: el 2 de octubre, que no tiene
sesión anterior en la muestra, y el 30, porque su sesión anterior, el 29, no tiene RR25.

## 3. Qué muestra

**RR25.** Siempre negativo: el put de delta −0.25 vale más volatilidad que el call de delta +0.25. Se
hizo más negativo desde mediados de octubre: entre −3.0 y −3.6 hasta el 13, y entre −4.0 y −6.2 desde el
14. El mínimo fue el 23 (−6.23); se recuperó hasta −4.58 el 28 y volvió a −5.84 el 30. La asimetría a distancia logarítmica simétrica (call a F·1.03 frente a put a
F/1.03) se mueve igual. La gráfica de cambio de RR25 frente al movimiento previo es exploratoria: 20
sesiones no alcanzan para medir nada predictivo.

**Calidad.** A las 09:45 se excluyeron, en total, 782 cotizaciones desfasadas (de más de 60 s), 295 con
el spread demasiado ancho, 275 sin bid y 18 de la ventana de apertura. El spread mediano es de 13 ticks.

**El 29 de octubre.** Cuenta como sesión de la muestra, pero sin RR25: no hubo captura de las 09:45, y el
piloto no usa la de las 10:00 en su lugar. Sí tiene etiqueta de SPY, porque el SIP de ese corte está
completo. Dos textos del informe sobre ese día confunden, aunque no cambian ningún número:

- el motivo dice «no hay vencimientos a ambos lados de 30 días», cuando la causa es que no hubo captura;
- la limitación «Hay sesiones sin hora de evento en las cotizaciones» aparece porque ese corte no tiene
  cotizaciones.

Conviene que el piloto diga «sin captura a la hora principal»; es un cambio de código chico, para
después.

## 4. Propuesta de `piloto-0.4` (para que la apruebes)

**Un cambio:** `desfase_spot_max_s`, de 2 a 10 segundos.

- **Por qué.** En los 41 cortes, el nivel de referencia (el SPX implícito) lleva de 5.0 a 6.2 s de
  atraso al corte. Es por diseño: la ráfaga de la captura empieza 5 s antes del corte, para que ninguna
  respuesta llegue después. Con 2 s, todas las sesiones salen con alerta y la alerta deja de decir algo.
- **Lo que se conserva.** Con 10 s, un atraso real sigue marcando alerta. El escenario sintético de
  subyacente desfasado usa 30 s.
- **Prueba.** Con este único cambio, en el scratchpad y sin publicar, el dictamen pasa a «apto para
  ampliar historia», ninguna sesión tiene alertas y aparece un ejemplo de sesión normal, la del 30 de
  octubre.

**El resto, sin cambios**, con lo que mostró el piloto:

| Umbral | Valor | Evidencia |
|---|---|---|
| `edad_maxima_s` (cotización) | 60 s | Deja fuera 782 cotizaciones viejas a las 09:45; el RR25 se identifica igual en 20 de 21 sesiones |
| `spread_relativo_max` y `spread_ticks_tolerados` | 0.5 y 2 | 295 exclusiones; las bandas del RR25 quedan en ±0.1 |
| `margen_apertura_s` | 300 s | Solo 18 exclusiones |
| `min_sesiones` | 20 | Se cumple con 21 |
| `rr25_apto`, `cambio_rr25_minimo` y `etiquetas_min` | 0.9, 0.8 y 0.9 | Se cumplen con margen (0.952, 0.900 y 0.952) |
| `estabilidad_max` | 1.0 | Valor 0.393: amplio margen |
| `alertas_max` | 0.2 | Con el cambio de arriba, 0.000 |
| `[referencia]`: tasa y dividendo fijos | 4 % y 1.3 % | Solo sirven para un diagnóstico del forward; sigue pendiente una curva con fuente |

Si lo apruebas: se crea `piloto-0.4` con ese cambio, se congela, se vuelve a correr el informe y se
publica en lugar de este.

## 5. Limitaciones y qué sigue

- **Feed indicativo.** El piloto no permite evaluar con precios de mercado. La comparación con Robinhood
  muestra que el mid de Alpaca, fuera del dinero, se aleja unos 0.08 puntos de volatilidad de la marca
  ([comparación](comparacion_robinhood.md)): para el RR25 es poco, frente a bandas de ±0.1.
- **Otro instrumento como objetivo.** Las etiquetas son de SPY, no de SPX, con sus dividendos y gastos.
- **Etiquetas a 5 sesiones.** Se solapan: no son observaciones independientes.
- **Muestra chica.** Con 20 sesiones se valida la medición, no una señal.
- **Siguiente paso del plan** ([cómo proseguir](como_proseguir.md), sección 7): con la medición apta, lo
  que toca es ampliar la historia y fijar por escrito el protocolo predictivo antes de mirar resultados.
  Las etiquetas maduras empiezan en diciembre.
- **Riesgo operativo.** Las rutinas que lanzan la captura llegaron hasta 45 minutos tarde esta semana, y
  el 29 se perdió una hora. Para ampliar la historia sin huecos hay que resolverlo
  ([estado](estado_continuacion.md), sección 5).

## 6. Cómo repetir

Con los comandos de la sección 1, desde la raíz de QuantileFlow y con el repositorio de datos al lado.
Para la prueba de `piloto-0.4`, copiar `configs/piloto.toml`, cambiar `desfase_spot_max_s = 10` y pasar la
copia con `--config` y otra `--salida`.
