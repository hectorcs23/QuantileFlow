# QuantileFlow: Alpaca como fuente de datos

**Fecha:** 26 de septiembre de 2026 (sábado; el mercado reabre el lunes 28).
**Base:** [estado de la continuación](estado_continuacion.md), sección 1.

> El acceso a Alpaca ya funciona desde el entorno. La primera verificación con datos reales usa las
> últimas cotizaciones del viernes 25 al cierre: **no es una sesión de apertura** y no dice nada
> todavía sobre la señal. La primera captura a las 09:45 posible es la del lunes 28 de septiembre.

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
| Límites | 200 solicitudes por minuto. Una cadena de un vencimiento cabe en una página de 1 000 contratos y tarda 0.25–0.45 s. |

Consecuencias para el plan:

1. **SPXW vuelve a ser posible con Alpaca.** El piloto sigue el diseño original: SPXW PM a las
   09:45, plazo constante de 30 días. SPY se captura como serie secundaria y **no** se mezcla con SPXW.
2. **Captura hacia adelante.** Con 20 a 40 sesiones, el piloto necesita de 4 a 8 semanas de captura
   diaria a partir del 28 de septiembre.
3. **Nivel implícito de SPX.** Sin índice, el nivel de SPX sale de la paridad del vencimiento SPXW
   más cercano (el del día, si existe), con el descuento fijado por la tasa de referencia, y se lleva a
   contado con `S = F e^{-(r-q)T}`. A plazo de horas, esa conversión mueve el nivel menos de 0.01 %.
   Las etiquetas son rendimientos de ese nivel implícito, no del índice publicado.
   (`quantileflow/implicito.py`).
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
| Captura diaria | Consulta el reloj de Alpaca y los contratos del día. Elige, por raíz, dos vencimientos a cada lado de 30 días (y el más cercano en SPXW). Espera hasta 5 s antes de cada corte (09:45 y 10:00) y lanza todas las solicitudes en paralelo; la ráfaga completa tardó 0.7 s. Después escribe las tablas del día. | `scripts/capturar_alpaca.py`, `configs/captura_alpaca.toml` |
| Tablas para el piloto | Reconstruye desde el crudo las tablas de un rango de sesiones, con manifiesto. Reprocesar da los mismos bytes (comprobado). | `scripts/normalizar_alpaca.py` |
| Diagnóstico | Cobertura, grilla de ticks, anchos, edades, agrupación de sellos, paridad y medidas por vencimiento y a 30 días. Solo publica agregados. | `scripts/verificar_alpaca.py` |
| Pruebas | 11 pruebas sin red con respuestas de la forma real y precios sintéticos. Cubren reintentos, paginación, crudo sin secretos, normalización, replay, crudo alterado y nivel implícito. Una de ellas va de punta a punta: capturas → piloto con RR25 identificado. | `tests/test_alpaca.py` |

`contrato.captura_de_filas` separa, de `captura_desde_tabla`, la construcción de la captura a partir de
filas ya elegidas y un corte explícito. Lo usan el nivel implícito y el diagnóstico; el piloto no
cambia. La batería pasa de 142 a 153 pruebas.

---

## 3. Primera verificación con datos reales (cierre del viernes 25)

Informe completo, solo con agregados: [`reports/verificacion_alpaca/2026-09-25/`](../reports/verificacion_alpaca/2026-09-25/informe.md).
Son las últimas cotizaciones antes de las 16:00, capturadas el sábado; como llegaron después del corte,
el diagnóstico omite las horas de snapshot y de disponibilidad (declarado en el informe).

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
| Dónde corre la captura y dónde quedan los datos | Repositorio **privado** `QuantileFlow-datos` con un workflow programado de GitHub Actions. Este repositorio es público y los datos de Alpaca/OPRA no se pueden redistribuir: el crudo no puede ir aquí. | La plantilla está en [`ops/repo_datos/`](../ops/repo_datos/): workflow, `.gitignore` y README. El workflow arranca hacia las 09:17 de Nueva York, con un respaldo a las 09:32, y espera al corte: así tolera los retrasos habituales del cron de GitHub. Solo guarda el crudo. Consume unos 1 000 minutos de Actions al mes. |
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
4. Probar con **Actions → captura-alpaca → Run workflow** y la opción «ahora».

## 5. Cómo operar

```bash
python scripts/capturar_alpaca.py --ahora          # prueba inmediata (fuera de sesión: cierre anterior)
python scripts/capturar_alpaca.py                  # día hábil: espera y captura a las 09:45 y 10:00 ET
python scripts/verificar_alpaca.py --fecha 2026-09-28
python scripts/normalizar_alpaca.py --desde 2026-09-28 --hasta 2026-11-06
python scripts/piloto.py --cotizaciones data/normalized/alpaca/cotizaciones.parquet \
    --subyacente data/normalized/alpaca/subyacente.parquet --desde 2026-09-28 --hasta 2026-11-06
```

`data/` sigue fuera de Git. Con el repositorio de datos, se pasa `--datos ../QuantileFlow-datos` a los
scripts. Una captura ocupa unos 0.3 MB comprimida (1.6 MB sin comprimir), y los contratos del día,
unos 0.7 MB comprimidos: cuarenta sesiones caben en menos de 100 MB.

## 6. Limitaciones conocidas

- La hora del snapshot es la de recepción local. El desfase del reloj se mide y se registra en cada
  corrida, pero no se corrige.
- El nivel implícito depende de la tasa y el dividendo de referencia fijos (4 % y 1.3 %), aunque a
  plazo de horas su efecto es despreciable. La curva de tasas con fuente sigue pendiente.
- Para SPY no se cargan todavía dividendos discretos en la captura: el próximo ex-dividendo cae en
  diciembre, fuera de la ventana de 30 días hasta mediados de noviembre.
- El ajuste robusto de superficie (B4) sigue pendiente.
