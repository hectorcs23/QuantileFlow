# QuantileFlow: Alpaca como fuente de datos

**Fecha:** 26 de septiembre de 2026 (sábado; el mercado reabre el lunes 28).
**Base:** [estado de la continuación](estado_continuacion.md), sección 1.

> El acceso a Alpaca ya funciona desde el entorno. La primera verificación con datos reales usa las
> últimas cotizaciones del viernes 25 al cierre: **no es una sesión de apertura** y no dice nada
> todavía sobre la señal. La primera captura a las 09:45 posible es la del lunes 28 de septiembre.
>
> **Actualización tras la revisión de `e2b92f0`:** ocho correcciones en `79c1554`; detalle en
> [respuesta a la revisión](respuesta_revision_e2b92f0.md). Cambian el diagnóstico (elegibilidad
> estricta siempre; modo descriptivo solo si se pide), los estados de captura y la separación de
> fuentes en el piloto.
>
> **Actualización tras la revalidación de `d815bdd` (27 de septiembre):** el objetivo es SPY
> observado en el SIP histórico. El SPX implícito queda como referencia de las opciones. Hay
> dividendos, diario de captura con recuperación, plazo absoluto y workflows por hora. Detalle en
> [respuesta a la revalidación](respuesta_revalidacion_d815bdd.md).
>
> **Actualización tras la revisión de `8c97b2b`:** la cobertura de dividendos va aparte. Los eventos
> y las etiquetas se versionan, y el rendimiento total es provisional, reconciliado o revisado. Un
> plazo de preparación deja llegar al respaldo de la misma hora. Detalle en
> [respuesta a la revisión de `8c97b2b`](respuesta_revision_8c97b2b.md). La captura queda fijada en
> `f2a5663`.
>
> **Actualización tras la revalidación de `a5e2748`:** una ausencia ya no retira un dividendo. Abre
> una discrepancia que deja la etiqueta pendiente hasta que la resuelva evidencia fechada: una
> reaparición, una corrección o una resolución registrada. Solo cuentan como cobertura las consultas
> que piden dividendos en efectivo. Los estados son provisional, aceptada bajo la política de 60 días
> (una regla, no una garantía) y pendiente. Detalle en
> [respuesta a la revalidación de `a5e2748`](respuesta_revalidacion_a5e2748.md). La captura queda
> fijada en `8316540`, sin cambios de comportamiento.
>
> **Actualización tras la revalidación de `5c15028`:** un dividendo que llega sin fecha ex o sin monto
> ya no queda fuera: es una versión con la discrepancia `incompleto`. Las etiquetas cuyo periodo podría
> contener su fecha ex quedan pendientes hasta que el proveedor lo complete o una resolución dé la
> fecha ex y el monto. Detalle en
> [respuesta a la revalidación de `5c15028`](respuesta_revalidacion_5c15028.md). La captura queda
> fijada en `7fb0585`, sin cambios de comportamiento.

---

## 1. Qué se comprobó

Todas las comprobaciones se hicieron el 26 de septiembre con la cuenta *paper* del entorno y la
documentación oficial de Alpaca (actualizada entre septiembre de 2025 y septiembre de 2026).

| Comprobación | Resultado |
|---|---|
| Credenciales | `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY` de una cuenta *paper* activa, con opciones de nivel 3. No se escriben en ningún archivo. |
| Red | `paper-api.alpaca.markets`, `data.alpaca.markets` y `docs.alpaca.markets` responden. El reloj local difiere del de Alpaca en unos +0.2 s. |
| SPX y SPXW | **Disponibles.** El subyacente `SPX` lista las raíces `SPX` (mensual, liquidación AM) y `SPXW` (PM), europeas y con multiplicador 100. Hay vencimientos SPXW todos los días hábiles. La documentación de Alpaca sobre opciones de índices confirma AM/PM por raíz. |
| Cotizaciones SPXW | Llegan en el feed gratuito `indicative`. La cadena se pide por raíz (`/v1beta1/options/snapshots/SPXW`); pedida por `SPX` devuelve solo la raíz mensual. |
| Feed OPRA | `403: OPRA agreement is not signed`. Según la documentación, requiere el plan Algo Trader Plus (99 USD al mes) y firmar el acuerdo OPRA en el panel. |
| Qué es `indicative` | Según Alpaca, es un derivado gratuito de OPRA: sus cotizaciones «no son cotizaciones reales de OPRA», están **modificadas**, y sus operaciones llegan con 15 minutos de retraso. |
| Historia de cotizaciones | **No hay.** Solo barras y operaciones de opciones desde febrero de 2024. El bid/ask de las 09:45 de sesiones pasadas no se puede reconstruir: la muestra se captura hacia adelante. |
| Nivel del índice | **No hay** nivel de SPX (lo dice la documentación de opciones sobre índices). |
| SPY | Cotización IEX en tiempo real en el plan básico. El histórico SIP es consultable pasados 15 minutos. Los dividendos en efectivo de SPY están en `/v1/corporate-actions`. |
| Histórico SIP de SPY (27 de septiembre) | `/v2/stocks/quotes?feed=sip` devuelve el **NBBO consolidado**: bid y ask de bolsas distintas, hora en nanosegundos y spread de 1 a 3 centavos. Con una ventana que termina hace menos de 15 minutos responde `403: subscription does not permit querying recent SIP data`. En 10 cortes del 21 al 25 de septiembre, las 1 000 cotizaciones más recientes cubren entre 6 y 19 s antes del corte; la última está a menos de 10 ms. La mediana del spread es de 0.26 pb y el máximo de 1.2 pb. |
| Eventos corporativos de SPY | El dividendo del 18 de septiembre, con pago el 30 de octubre, ya figuraba antes de su pago. Pero Alpaca **no garantiza** cuándo publica un evento: puede llegar con retraso respecto del anuncio. El filtro por omisión excluye además los registros incompletos todavía no procesados, aunque los procesados se devuelven siempre. El filtro de fechas es por `process_date` (el pago, de 41 a 43 días después de la fecha ex en los últimos seis). No traen la hora del anuncio. |
| Límites | 200 solicitudes por minuto. Una cadena de un vencimiento cabe en una página de 1 000 contratos y tarda 0.25–0.45 s. |

Consecuencias para el plan:

1. **SPXW vuelve a ser posible con Alpaca.** El piloto sigue el diseño original: SPXW PM a las
   09:45, plazo constante de 30 días. SPY se captura como serie secundaria y **no** se mezcla con SPXW.
2. **Captura hacia adelante.** Con 20 a 40 sesiones, el piloto necesita de 4 a 8 semanas de captura
   diaria a partir del 28 de septiembre.
3. **Nivel implícito de SPX.** Sin índice, el nivel de SPX sale de la paridad del vencimiento SPXW
   más cercano (el del día, si existe), con el descuento fijado por la tasa de referencia, y se lleva a
   contado con `S = F e^{-(r-q)T}`. A plazo de horas, esa conversión mueve el nivel menos de 0.01 %
   (`quantileflow/implicito.py`). Es la **referencia de las opciones**: la usan los controles y las
   medidas de la cadena. Desde la revalidación de `d815bdd`, el **objetivo** de las etiquetas es SPY
   observado en el SIP histórico, con rendimiento total y de precio por separado.
4. **El feed importa.** Con `indicative` el piloto mide ese feed, no el NBBO de SPXW. Ver sección 3.

---

## 2. Qué se construyó

| Pieza | Qué hace | Dónde |
|---|---|---|
| Cliente | GET con reintentos ante 429, 5xx y errores de red; paginación; sin dependencias nuevas. Las credenciales van solo en las cabeceras. | `quantileflow/alpaca.py` |
| Crudo inmutable | Cada respuesta se guarda tal cual, comprimida con gzip, en `data/raw/alpaca/`, direccionada por el SHA-256 del archivo y en solo lectura. El manifiesto de cada captura registra solicitud, parámetros, estado, cabeceras, horas de envío y recepción y los hashes del archivo y del contenido. | `alpaca.capturar`, `almacen.guardar_crudo_bytes` |
| Normalización | Del crudo al contrato `COTIZACIONES`/`SUBYACENTE`. Verifica los hashes, cruza cada símbolo OCC con los metadatos del contrato y cuenta las filas sin cotización o sin metadatos. La liquidación sale de una tabla por raíz con fuente; una raíz desconocida detiene el proceso. | `alpaca.normalizar` |
| Sellos | `sello_evento_utc`: hora de la cotización según Alpaca (nanosegundos truncados a microsegundos). `sello_snapshot_utc`, `disponible_utc` y `recibido_utc`: hora local de recepción, cota superior del snapshot. | `alpaca.filas_cadena` |
| Nivel implícito | Una fila de subyacente `SPX` por captura, con el vencimiento, los pares, el error jackknife del forward y la hora mediana de las cotizaciones usadas. | `quantileflow/implicito.py` |
| Captura diaria | Consulta el reloj de Alpaca y los contratos del día. Elige, por raíz, dos vencimientos a cada lado de 30 días (y el más cercano en SPXW). Espera hasta 5 s antes de cada corte (09:45 y 10:00) y lanza todas las solicitudes en paralelo; la ráfaga completa tardó 0.7 s. Cada página se guarda al llegar. Cada captura queda `completa`, `parcial` o `fallida`, y una hora sin captura, `perdida`. El código de salida es 0 solo si todas las horas están completas, y cada ejecución deja un registro en `raw/alpaca/ejecuciones/`. | `scripts/capturar_alpaca.py`, `configs/captura_alpaca.toml` |
| Tablas para el piloto | Reconstruye desde el crudo las tablas de un rango de sesiones, con manifiesto. Reprocesar da los mismos bytes (comprobado). | `scripts/normalizar_alpaca.py` |
| Diagnóstico | Elegibilidad al corte con controles estrictos, siempre. Además, cobertura, grilla de ticks, anchos, edades, agrupación de sellos, paridad y medidas por vencimiento y a 30 días. El modo descriptivo del cierre solo se aplica con `--cierre-descriptivo` y a capturas inmediatas recibidas con la sesión cerrada, y se declara no elegible. Solo publica agregados. | `quantileflow/diagnostico.py`, `scripts/verificar_alpaca.py` |
| Histórico SIP del objetivo | Pasados 15 minutos y un margen de cada corte, pide las 1 000 cotizaciones más recientes de SPY hasta el corte, en una página y en orden descendente. Un corte completo no se repite; un intento fallido sí. Normaliza a `SUBYACENTE` (feed `sip`): el snapshot es el corte, la disponibilidad documentada es el corte más 15 minutos y la recepción es la de la descarga. | `scripts/historico_alpaca.py`, `alpaca.pedir_historico`, `alpaca.normalizar_historico` |
| Dividendos | Consulta los eventos corporativos de SPY del último año y los ya anunciados. Guarda la **cobertura** de cada consulta, aunque venga vacía o falle, y las **versiones** de cada dividendo, con desde cuándo se conoce cada una y hasta cuándo vale. Una consulta comparable que ya no trae un dividendo abre una **discrepancia**: no lo retira. Un dividendo que llega sin fecha ex o sin monto también abre una (`incompleto`) y deja pendientes las etiquetas cuyo periodo podría contener su fecha ex. Solo la resuelve evidencia fechada: una reaparición, una corrección o una resolución registrada en `resoluciones_dividendos.csv`. Las etiquetas maduran con la primera consulta posterior a su fin que puede confirmar dividendos. Son provisionales, aceptadas bajo la política de 60 días o pendientes (con una discrepancia abierta). Un evento no tratado (split, fusión, etc.) dentro del rango detiene la normalización. | `alpaca.normalizar_eventos`, `alpaca.cargar_resoluciones`, esquemas `contrato.DIVIDENDOS`, `COBERTURA_DIVIDENDOS` y `RESOLUCIONES_DIVIDENDOS`, `etiquetas.py` |
| Diario y recuperación | Cada captura tiene un diario (`<etiqueta>.diario.jsonl`), creado de forma atómica con su inicio, con una línea sincronizada por solicitud, página y fin. `recuperar` convierte un diario sin manifiesto en un manifiesto `parcial` o `fallida`, marcado como interrumpido. Manifiestos y registros se escriben de forma atómica y sin sobrescribir. | `alpaca.Diario`, `alpaca.recuperar`, `almacen.crear_nuevo`, `capturar_alpaca.py --recuperar` |
| Plazo absoluto | 60 s después del último corte, el proceso anota la interrupción y termina con código 3, aunque una solicitud siga colgada. | `alpaca.Vigilante`, `plazo_s` |
| Pruebas | 22 pruebas sin red, con respuestas de la forma real y precios sintéticos. Cubren reintentos, paginación, crudo sin secretos, normalización, replay, crudo alterado, nivel implícito, histórico SIP y dividendos. Dos van de punta a punta: capturas → piloto con RR25 identificado, y SIP → etiquetas del objetivo. Otras dos matan el proceso: tras la primera página (SIGKILL) y con una solicitud colgada (plazo). | `tests/test_alpaca.py` |

`contrato.captura_de_filas` separa, de `captura_desde_tabla`, la construcción de la captura a partir de
filas ya elegidas y un corte explícito. Lo usan el nivel implícito y el diagnóstico. La batería pasó
de 142 a 153 pruebas, a 167 con las regresiones de la revisión y a 186 con la revalidación.

---

## 3. Primera verificación con datos reales (cierre del viernes 25)

Informe completo, solo con agregados: [`reports/verificacion_alpaca/2026-09-25/`](../reports/verificacion_alpaca/2026-09-25/informe.md).
Son las últimas cotizaciones antes de las 16:00, capturadas el sábado. Con los controles estrictos
dan **0 filas válidas al corte**: llegaron después. Las cifras de esta sección salen del modo
**descriptivo del cierre** (`--cierre-descriptivo`), que omite las horas de snapshot y de
disponibilidad para describir el feed. El informe lo declara no elegible para el piloto.

| Medida | SPXW (4 vencimientos, 27–32 días) | SPY (4 vencimientos, 21–42 días) |
|---|---|---|
| Contratos con cotización | 3 250 de 3 250 (junto con SPY) | — |
| Precios en la grilla de ticks de la bolsa | **9–15 %** (SPXW cotiza en múltiplos de 0.05/0.10) | 99 % (grilla de 1 centavo: no discrimina) |
| Ancho mediano cerca del dinero (\|k\| ≤ 0.05) | 1.2–1.4 puntos (≈ 2 % del mid) | 0.12–0.30 USD (≈ 3 %) |
| Horas de las cotizaciones | 13–18 segundos distintos; 80–85 % en tres de ellos | 2–6 segundos distintos |
| Pares de paridad fuera de la banda bid/ask | **20–28 %** | 8–22 % |
| Error jackknife del forward | 0.45–0.72 puntos | 0.05–0.10 USD |
| Tasa implícita de la paridad | −0.6 % a 7.3 % según el vencimiento | no interpretable (americanas, sin dividendos) |
| RR25 a 30 días | −3.08 puntos, banda [−3.24, −2.93] | −3.20, banda [−3.31, −3.10] |
| Asimetría a ±ln 1.03 a 30 días | −3.58 puntos | −3.60 puntos |

- SPX implícito: 7 741.49, a partir de 182 pares del vencimiento del lunes 28. Error del forward: 0.14.
  SPY (IEX): 771.34. Razón SPX/SPY: 10.037.

Lectura:

- **Las cotizaciones están modificadas.** Entre el 85 y el 91 % de los precios de SPXW caen fuera de
  la grilla de ticks de Cboe, algo imposible en un NBBO real. Coincide con la documentación.
- **La paridad sale mal.** Entre el 20 y el 28 % de los pares violan la banda bid/ask, y la tasa
  implícita cambia de −0.6 % a 7.3 % entre vencimientos contiguos. Parte se explica por la hora: las
  cotizaciones se actualizan en lotes (pocos segundos distintos) justo al cierre. Aun así, con este
  feed los residuos de paridad **no sirven** como señal ni como control fino de calidad.
- **Las volatilidades se ven coherentes.** La sonrisa es suave, y SPXW y SPY dan RR25 y asimetría
  logarítmica parecidos (−3.08 frente a −3.20; −3.58 frente a −3.60). Es un solo corte al cierre: hace
  falta ver sesiones a las 09:45.
- Sin OPRA no hay contra qué comparar el feed indicativo; no se puede cuantificar su sesgo en RR25.

---

## 4. Decisiones

Tomadas el 26 de septiembre:

| Decisión | Elección | Consecuencia |
|---|---|---|
| Dónde corre la captura y dónde quedan los datos | Repositorio **privado** `QuantileFlow-datos` con workflows programados de GitHub Actions. Este repositorio es público y los datos de Alpaca/OPRA no se pueden redistribuir: el crudo no puede ir aquí. | La plantilla está en [`ops/repo_datos/`](../ops/repo_datos/): workflows, `.gitignore` y README. `captura-0945` y `captura-1000` corren cada uno en su máquina: arrancan hacia las 09:11 y 09:21 de Nueva York, con un respaldo 15 minutos después, y esperan al corte. `historico-alpaca` corre hacia las 10:21. Solo guardan el crudo. Consumen unos 1 700 minutos de Actions al mes, sobre todo en la espera al corte (comprobar la cuota de minutos del plan para repositorios privados). |
| Feed de opciones | `indicative` por ahora. OPRA se decide después de ver 3–5 sesiones reales a las 09:45. | Si se contrata OPRA, se cambia `feed_opciones` en una versión nueva de `configs/captura_alpaca.toml`. Las dos series no se mezclan: el piloto cuenta sus sesiones desde que empieza OPRA. |

Pendiente de revisar con las primeras sesiones: `desfase_spot_max_s = 2` avisará en casi todas las
capturas, porque la ráfaga empieza 5 s antes del corte y el feed actualiza por lotes. Conviene revisarlo
junto con `edad_maxima_s`, sin tocar ninguno antes de ver datos.

### Puesta en marcha del repositorio de datos

1. Crear en GitHub el repositorio privado `hectorcs23/QuantileFlow-datos`, vacío. La integración de
   Claude no tiene permiso para crear repositorios.
2. Copiar ahí el contenido de `ops/repo_datos/` (o pedir a Claude que lo suba; la aplicación de GitHub
   de Claude necesita acceso a ese repositorio).
3. En **Settings → Secrets and variables → Actions**, crear `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY`.
4. Probar con **Actions → captura-0945 → Run workflow** y la opción «ahora», y con
   **Actions → historico-alpaca → Run workflow**.

## 5. Cómo operar

```bash
python scripts/capturar_alpaca.py --ahora          # prueba inmediata (fuera de sesión: cierre anterior)
python scripts/capturar_alpaca.py                  # día hábil: espera y captura a las 09:45 y 10:00 ET
python scripts/capturar_alpaca.py --horas 09:45    # una sola hora (así corre cada workflow)
python scripts/capturar_alpaca.py --recuperar      # convierte diarios sin manifiesto
python scripts/historico_alpaca.py --esperar       # SIP de SPY en cada corte (pasados 15 min) y dividendos
python scripts/verificar_alpaca.py --fecha 2026-09-28            # elegibilidad y calidad del feed
python scripts/verificar_alpaca.py --fecha 2026-09-25 --cierre-descriptivo
python scripts/normalizar_alpaca.py --desde 2026-09-28 --hasta 2026-11-13   # cinco sesiones más que el piloto
N=data/normalized/alpaca
python scripts/piloto.py --cotizaciones $N/cotizaciones.parquet --subyacente $N/subyacente.parquet \
    --dividendos $N/dividendos.parquet --cobertura-dividendos $N/cobertura_dividendos.parquet \
    --fuente-objetivo alpaca/sip --desde 2026-09-28 --hasta 2026-11-06
```

SPY llega de dos fuentes: IEX en vivo (diagnóstico) y el SIP histórico (objetivo). Por eso el piloto
exige `--fuente-objetivo alpaca/sip`. Lo mismo vale si las opciones traen `indicative` y `opra`:
`--fuente-opciones alpaca/opra --fuente-referencia alpaca/implicito_paridad_SPXW_opra`. Nunca las
mezcla, y el informe dice de qué fuente sale cada serie.

`data/` sigue fuera de Git. Con el repositorio de datos, se pasa `--datos ../QuantileFlow-datos` a los
scripts. Una captura ocupa unos 0.3 MB comprimida (1.6 MB sin comprimir), y los contratos del día,
unos 0.7 MB comprimidos: cuarenta sesiones caben en menos de 100 MB.

## 6. Limitaciones conocidas

- La hora del snapshot es la de recepción local. El desfase del reloj se mide y se registra en cada
  corrida, pero no se corrige.
- El nivel implícito depende de la tasa y el dividendo de referencia fijos (4 % y 1.3 %), aunque a
  plazo de horas su efecto es despreciable. La curva de tasas con fuente sigue pendiente.
- Alpaca no da la hora del anuncio de un dividendo ni garantiza cuándo lo publica.
  - Una etiqueta con rendimiento total madura con la primera consulta posterior a su fin que puede
    confirmar dividendos (provisional).
  - Queda aceptada con una consulta que cubre el periodo, recibida 60 días después y sin
    discrepancias abiertas. Esos 60 días son una regla operativa (41–43 días observados en seis
    dividendos de SPY), no una garantía, y se mide cuántas etiquetas cambian después de aceptarse.
  - Para entrenar o evaluar, solo etiquetas aceptadas.
  - Un dividendo que Alpaca no publicara nunca no abre ninguna discrepancia: solo lo detectaría otra
    fuente. Uno publicado sin fecha ex, en cambio, deja pendientes las etiquetas que podría afectar:
    entre la primera fecha de proceso posible menos 60 días y la última.
  - El próximo ex-dividendo de SPY cae en diciembre.
- El respaldo de una hora puede llegar al corte si el titular se cuelga antes de estar listo (plazo de
  preparación). La cronología es un escenario favorable, no una garantía: depende del retraso de los
  cron de GitHub, de la cola, de la recuperación, del commit, del checkout y de la instalación. No
  rescata un cuelgue durante la ráfaga: el plazo absoluto conserva lo recibido, pero ese instante de
  mercado se pierde y queda registrado.
- El precio del objetivo sale de la primera página del SIP (1 000 cotizaciones, de 6 a 19 s en la
  prueba). Si todas fueran anómalas, la etiqueta quedaría ausente, aunque hubiera una válida más atrás
  dentro de los 60 s.
- Una captura recuperada nunca queda `completa`, aunque su diario muestre que llegó todo: la ejecución
  no terminó.
- El ajuste robusto de superficie (B4) sigue pendiente.
