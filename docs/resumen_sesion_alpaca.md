# QuantileFlow: resumen de la sesión con Alpaca y mapa de archivos

**Fecha:** 26 de septiembre de 2026 (sábado; el mercado reabre el lunes 28); actualizado el 27.
**Rama:** [`claude/lucid-hamilton-hz8l80`](https://github.com/hectorcs23/QuantileFlow/tree/claude/lucid-hamilton-hz8l80),
sobre `853047b`.
**Commits de la sesión:**
- `f6ee438` (adaptador y captura), `f447f9b` (verificación y documentos), `40c80ab` (plantilla del
  repositorio de datos) y `e2b92f0` (este resumen);
- revisión de `e2b92f0`: `79c1554` (correcciones) y `d815bdd` (su documentación);
- revalidación de `d815bdd`: `03f2230` (señal, referencia y objetivo), `79bf8a7` (SIP histórico y
  dividendos), `3b266a4` (recuperación operativa), `fcb8637` (rastro de las cotizaciones repetidas) y
  `8c97b2b` (su documentación);
- revisión de `8c97b2b`: `6f0e748` (cobertura y versiones de dividendos), `f2a5663` (plazo de
  preparación) y el de su documentación.

> En una frase: Alpaca ya funciona desde el entorno y ofrece SPXW, pero no guarda cotizaciones
> pasadas de opciones, no da el nivel de SPX y su feed gratuito modifica las cotizaciones. Se construyó
> la captura diaria hacia adelante, que empieza el lunes 28 a las 09:45. Falta que crees el repositorio
> privado de datos y le pongas las claves.
>
> **Después hubo una revisión externa del commit `e2b92f0`** con ocho hallazgos. Los ocho se
> reprodujeron, se convirtieron en pruebas de regresión y se corrigieron en `79c1554` (153 → 167
> pruebas). Detalle en [respuesta a la revisión](respuesta_revision_e2b92f0.md).
>
> **La revalidación de `d815bdd`** confirmó las ocho correcciones y eligió SPY observado como objetivo.
> Ahora las señales salen de SPXW, la referencia de las opciones es el SPX implícito y el objetivo es
> SPY del SIP histórico (NBBO consolidado, descargado pasados 15 minutos), con dividendos. Las capturas
> tienen diario, recuperación y plazo absoluto, y cada hora corre en su propio workflow. Detalle en
> [respuesta a la revalidación](respuesta_revalidacion_d815bdd.md).
>
> **La revisión de `8c97b2b`** encontró que una consulta de dividendos futura volvía disponible una
> etiqueta en el pasado, que un evento retirado se seguía sumando y que una consulta vacía perdía su
> evidencia. También que Alpaca no garantiza cuándo publica los eventos. Ahora la cobertura va aparte,
> eventos y etiquetas se versionan (provisional, reconciliada, revisada) y un plazo de preparación
> deja llegar al respaldo de la misma hora. Hay 191 pruebas; detalle en
> [respuesta a la revisión de `8c97b2b`](respuesta_revision_8c97b2b.md).

---

## 1. Qué hicimos, en orden

1. **Comprobamos el acceso.** Las claves *paper* están en el entorno, la cuenta está activa y tiene
   opciones de nivel 3, y la red deja pasar a `paper-api`, `data` y `docs.alpaca.markets`. En la
   sesión anterior, el proxy las rechazaba.
2. **Verificamos qué ofrece Alpaca**, con la API y la documentación oficial: contratos, cadenas,
   feeds, historia, nivel del índice, SPY, dividendos y límites (sección 2).
3. **Exploramos una cadena SPXW real** y encontramos que el feed gratuito altera los precios.
4. **Construimos el adaptador y la captura:**
   - cliente con reintentos;
   - crudo inmutable y comprimido, con sus hashes y sin credenciales;
   - manifiesto por captura;
   - normalización al contrato de datos del piloto;
   - nivel implícito de SPX por paridad;
   - captura a hora fija, reconstrucción de tablas y diagnóstico.
5. **Escribimos 11 pruebas sin red.** La batería pasó de 142 a 153 pruebas, todas en verde (167 tras
   la revisión). Una de
   ellas va de punta a punta: respuestas con forma de Alpaca → crudo → normalización → nivel implícito →
   piloto con RR25 identificado.
6. **Capturamos datos reales y los diagnosticamos.** Como el mercado estaba cerrado, fueron las
   últimas cotizaciones del viernes 25. Reprocesar el crudo da exactamente los mismos bytes.
7. **Decidimos** dónde corre la captura y con qué feed (sección 4).
8. **Preparamos el repositorio privado de datos.** La plantilla del workflow de GitHub Actions quedó
   en `ops/repo_datos/`, y su simulación local funcionó. Crear el repositorio falló: la integración
   de GitHub no tiene ese permiso (403).

---

## 2. Qué encontramos

### Sobre Alpaca

| Tema | Resultado |
|---|---|
| SPX y SPXW | **Disponibles.** El subyacente `SPX` lista `SPX` (mensual, AM) y `SPXW` (PM), europeas, con multiplicador 100 y vencimientos todos los días hábiles. La cadena se pide por raíz: `/v1beta1/options/snapshots/SPXW`. |
| Historia de cotizaciones | **No hay.** Solo barras y operaciones desde febrero de 2024. No se puede reconstruir el bid/ask de las 09:45 pasadas: hay que capturar hacia adelante. |
| Nivel de SPX | **No hay.** Se estima por paridad con el vencimiento SPXW más cercano (`quantileflow/implicito.py`). |
| Feed `indicative` (gratis) | Según Alpaca, sus cotizaciones están *modificadas* y sus operaciones llegan con 15 minutos de retraso. |
| Feed OPRA | `403: OPRA agreement is not signed`. Requiere Algo Trader Plus (99 USD al mes) y firmar el acuerdo. |
| SPY | Cotización IEX en tiempo real en el plan gratuito; SIP histórico pasados 15 minutos; dividendos en `/v1/corporate-actions`. |
| Límites y velocidad | 200 solicitudes por minuto. Una cadena de un vencimiento cabe en una página y tarda 0.25–0.45 s. La ráfaga completa (10 respuestas) tardó 0.71 s. |
| Reloj | El reloj local difiere del de Alpaca en unos +0.2 s. |

### Primera verificación con datos reales (cierre del viernes 25, no es una sesión de apertura)

| Medida | SPXW | SPY |
|---|---|---|
| Contratos con cotización | 3 250 de 3 250 (junto con SPY) | — |
| Precios en la grilla de ticks de la bolsa | **9–15 %** (en un NBBO real serían todos) | 99 % (grilla de 1 centavo: no discrimina) |
| Pares fuera de la banda de paridad | **20–28 %** | 8–22 % |
| Ancho cerca del dinero | 1.2–1.4 puntos (≈ 2 %) | 0.12–0.30 USD (≈ 3 %) |
| Tasa implícita de la paridad | −0.6 % a 7.3 % según el vencimiento | no interpretable |
| RR25 a 30 días | −3.08 puntos, banda [−3.24, −2.93] | −3.20, banda [−3.31, −3.10] |
| Asimetría a ±ln 1.03 a 30 días | −3.58 puntos | −3.60 puntos |

- SPX implícito: 7 741.49, con 182 pares del vencimiento del lunes 28. Error del forward: 0.14.
  SPY (IEX): 771.34. Razón SPX/SPY: 10.037.
- Lectura: el feed gratuito sirve para montar y probar la captura, y sus volatilidades se ven
  coherentes. Pero sus residuos de paridad no sirven ni como señal ni como control fino de calidad.
  Sin OPRA no se puede medir cuánto sesga el RR25.

---

## 3. Qué construimos

| Pieza | Qué hace |
|---|---|
| Cliente de Alpaca | GET con reintentos ante 429, 5xx, errores de red y lecturas cortadas, y paginación. Sin dependencias nuevas. Las credenciales van solo en cabeceras y `repr` no las muestra. |
| Crudo inmutable | Cada respuesta se guarda sin tocar, comprimida con gzip y en solo lectura, con el SHA-256 del archivo y del contenido. |
| Manifiesto por captura | Registra solicitud, parámetros, estado, cabeceras, horas de envío y recepción, hashes, desfase del reloj, vencimientos elegidos, configuración y commit del código. Nunca se sobrescribe. |
| Normalización | Del crudo al contrato `COTIZACIONES`/`SUBYACENTE`. Comprueba hashes y cruza cada símbolo OCC con los metadatos del contrato. Cuenta los contratos sin cotización o sin metadatos, y se detiene ante una raíz de liquidación desconocida. |
| Nivel implícito de SPX | Forward de paridad del vencimiento SPXW más cercano, con el descuento fijado, llevado a contado. Registra vencimiento, pares, error jackknife y hora mediana. |
| Captura diaria | Reloj de Alpaca y contratos del día. Elige, por raíz, dos vencimientos a cada lado de 30 días (más el más cercano en SPXW). Lanza una ráfaga paralela 5 s antes de las 09:45 y de las 10:00. No repite horas ya capturadas y sale limpio en feriados. |
| Tablas para el piloto | Reconstruye desde el crudo un rango de sesiones, con manifiesto. Reprocesar da los mismos bytes. |
| Diagnóstico | Por vencimiento: cobertura, grilla de ticks, anchos, edades, agrupación de sellos, paridad, RR25 y asimetría, también a 30 días. Solo publica agregados. |
| Workflow de captura | GitHub Actions para el repositorio privado. Un disparo y un respaldo por horario, con una compuerta horaria para EDT/EST, y commit del crudo aunque la captura sea parcial. |

Cambios en código existente: `contrato.captura_de_filas` separa la construcción de una captura con corte
explícito (el piloto no cambia) y `almacen.guardar_crudo_bytes` guarda crudo recibido en memoria.

---

## 4. Decisiones tomadas

| Decisión | Elección |
|---|---|
| Dónde corre la captura | GitHub Actions en un repositorio **privado** `QuantileFlow-datos`. El repositorio del código es público, y los datos de Alpaca/OPRA no se pueden redistribuir. |
| Feed de opciones | `indicative` por ahora; OPRA se decide después de ver 3–5 sesiones reales a las 09:45. Si se cambia, las dos series no se mezclan. |
| Instrumento | SPXW PM como serie principal (diseño original del plan); SPY como serie secundaria aparte. |

---

## 5. Dónde están los archivos

### Código (repositorio público `hectorcs23/QuantileFlow`, rama `claude/lucid-hamilton-hz8l80`)

| Archivo | Qué es | Estado |
|---|---|---|
| [`quantileflow/alpaca.py`](../quantileflow/alpaca.py) | Adaptador: cliente, solicitudes, crudo, diario y manifiestos, recuperación, plazo absoluto (`Vigilante`), histórico SIP, dividendos, elección de vencimientos y normalización | nuevo (ampliado en la revalidación) |
| [`quantileflow/implicito.py`](../quantileflow/implicito.py) | Nivel implícito del subyacente por paridad | nuevo |
| [`quantileflow/diagnostico.py`](../quantileflow/diagnostico.py) | Diagnóstico de capturas: elegibilidad estricta al corte y calidad del feed; modo descriptivo del cierre solo si se pide | nuevo (revisión) |
| [`quantileflow/contrato.py`](../quantileflow/contrato.py) | `captura_de_filas`, `precio_al_corte` (regla puntual), `precio_para_etiqueta` (regla histórica), esquema `DIVIDENDOS`, `tipo_precio`, rechazo de mezclas de fuentes, último snapshot por contrato | modificado |
| [`quantileflow/piloto.py`](../quantileflow/piloto.py) | Señal, referencia y objetivo separados; fuentes explícitas; procedencia por fila; segmentos; rendimiento total del objetivo; alcance del dictamen | modificado (revisión y revalidación) |
| [`quantileflow/etiquetas.py`](../quantileflow/etiquetas.py) | Madurez con la disponibilidad de precios y dividendos; rendimiento total y de precio; «sin dividendos confirmados» | modificado (revisión y revalidación) |
| [`quantileflow/filtrado.py`](../quantileflow/filtrado.py), [`distribuciones.py`](../quantileflow/distribuciones.py), [`opciones.py`](../quantileflow/opciones.py) | Filtros causales, inversa generalizada con mesetas, volatilidad implícita sin abortar el lote | modificados (revisión) |
| [`quantileflow/almacen.py`](../quantileflow/almacen.py) | `guardar_crudo_bytes`, `crear_nuevo` y `escribir_json_nuevo` (atómicos, sin sobrescribir) | modificado |
| [`scripts/capturar_alpaca.py`](../scripts/capturar_alpaca.py) | Captura diaria a las 09:45 y 10:00 ET (o una hora con `--horas`), inmediata con `--ahora`; recupera diarios con `--recuperar`; plazo absoluto | nuevo |
| [`scripts/historico_alpaca.py`](../scripts/historico_alpaca.py) | SIP de SPY en cada corte, pasados 15 minutos, y eventos corporativos | nuevo (revalidación) |
| [`scripts/normalizar_alpaca.py`](../scripts/normalizar_alpaca.py) | Tablas para el piloto de un rango de sesiones, desde el crudo | nuevo |
| [`scripts/verificar_alpaca.py`](../scripts/verificar_alpaca.py) | Diagnóstico agregado de las capturas de una fecha | nuevo |
| [`configs/captura_alpaca.toml`](../configs/captura_alpaca.toml) | Qué, cuándo y con qué feed se captura; histórico y eventos; plazo absoluto (versión `captura-alpaca-0.2`) | nuevo |
| [`configs/piloto.toml`](../configs/piloto.toml) | Sección `[objetivo]`: SPY observado, regla histórica, rendimiento total (versión `piloto-0.3`) | modificado |
| [`tests/test_alpaca.py`](../tests/test_alpaca.py) | Pruebas sin red del adaptador, la captura y el diagnóstico | nuevo |
| [`tests/conftest.py`](../tests/conftest.py) | Gráficas sin interfaz en las pruebas (backend `Agg`) | nuevo (revisión) |
| [`Makefile`](../Makefile) | `captura`, `captura-prueba`, `historico-alpaca`, `normalizar-alpaca`, `verificar-alpaca` | modificado |

### Documentos e informes

| Archivo | Qué es |
|---|---|
| [`docs/resumen_sesion_alpaca.md`](resumen_sesion_alpaca.md) | Este resumen |
| [`docs/respuesta_revision_e2b92f0.md`](respuesta_revision_e2b92f0.md) | Los ocho hallazgos de la revisión externa, sus correcciones, pruebas y decisiones pendientes |
| [`docs/respuesta_revalidacion_d815bdd.md`](respuesta_revalidacion_d815bdd.md) | La entrega de la revalidación: papeles, SIP histórico, convenciones, recuperación y lo que falta |
| [`reports/verificacion/f2a566353d8d.json`](../reports/verificacion/f2a566353d8d.json) | Registro del commit fijado en los workflows: árbol limpio, 191 pruebas pasadas |
| [`reports/verificacion/fcb863782508.json`](../reports/verificacion/fcb863782508.json) | Registro del commit fijado en la entrega anterior: 186 pruebas pasadas |
| [`docs/respuesta_revision_8c97b2b.md`](respuesta_revision_8c97b2b.md) | Cobertura y versiones de dividendos, estados de las etiquetas, plazo de preparación y correcciones |
| [`reports/verificacion/79c15549bacd.json`](../reports/verificacion/79c15549bacd.json) | Registro del commit revisado anterior: árbol limpio, 167 pruebas pasadas |
| [`reports/piloto_sintetico/informe.md`](../reports/piloto_sintetico/informe.md) | Plantilla del informe piloto (datos sintéticos) con referencia y objetivo separados |
| [`docs/fuente_alpaca.md`](fuente_alpaca.md) | Documento de referencia: qué se comprobó, qué se construyó, verificación, decisiones, puesta en marcha y limitaciones |
| [`docs/estado_continuacion.md`](estado_continuacion.md) | Estado de la etapa anterior, con nota de actualización y lista de pendientes al día |
| [`README.md`](../README.md) | Estructura, documentos y comandos de captura actualizados |
| [`reports/verificacion_alpaca/2026-09-25/informe.md`](../reports/verificacion_alpaca/2026-09-25/informe.md) | Diagnóstico del cierre del viernes, en tablas por vencimiento |
| [`reports/verificacion_alpaca/2026-09-25/resumen.json`](../reports/verificacion_alpaca/2026-09-25/resumen.json) | Las mismas cifras en JSON |
| [`reports/verificacion_alpaca/2026-09-25/sonrisa_30d.png`](../reports/verificacion_alpaca/2026-09-25/sonrisa_30d.png) | Sonrisa de volatilidad SPXW a 31 días, con bandas bid/ask |
| [`reports/verificacion_alpaca/2026-09-25/paridad_30d.png`](../reports/verificacion_alpaca/2026-09-25/paridad_30d.png) | Residuos de paridad en múltiplos del ancho bid/ask |

### Plantilla del repositorio privado de datos

| Archivo | Qué es |
|---|---|
| [`ops/repo_datos/.github/workflows/captura-hora.yml`](../ops/repo_datos/.github/workflows/captura-hora.yml) | Workflow reutilizable de una hora de corte: compuerta, captura con plazo absoluto, recuperación y commit del crudo. Toma el código del commit `f2a5663` (`REF_CODIGO`). |
| [`ops/repo_datos/.github/workflows/captura-0945.yml`](../ops/repo_datos/.github/workflows/captura-0945.yml), [`captura-1000.yml`](../ops/repo_datos/.github/workflows/captura-1000.yml) | Disparos y respaldos de cada hora, cada una en su máquina y con su concurrencia |
| [`ops/repo_datos/.github/workflows/historico.yml`](../ops/repo_datos/.github/workflows/historico.yml) | SIP de SPY y eventos corporativos hacia las 10:21 de Nueva York |
| [`ops/repo_datos/README.md`](../ops/repo_datos/README.md) | Configuración de secretos, qué hace el workflow, estructura y uso de los datos |
| [`ops/repo_datos/.gitignore`](../ops/repo_datos/.gitignore) | Solo el crudo va a Git; las tablas se reconstruyen |

Una vez creado, el repositorio `hectorcs23/QuantileFlow-datos` guardará:

```
raw/alpaca/<hash[:2]>/<sha256>_<nombre>.json.gz          respuestas de la API, inmutables
raw/alpaca/capturas/<fecha>/<fecha>T<HHMM>.json           manifiesto de cada captura
raw/alpaca/capturas/<fecha>/<fecha>T<HHMM>.diario.jsonl   diario de la captura, página por página
raw/alpaca/historico/<fecha>/<fecha>T<HHMM>.json          SIP de SPY en cada corte
raw/alpaca/eventos/<fecha>/eventos-<instante>.json        eventos corporativos (dividendos)
raw/alpaca/ejecuciones/<fecha>/<inicio>[_sufijo].json     registro de cada ejecución
```

Una captura ocupa unos 0.3 MB comprimida, y los contratos del día, unos 0.7 MB. Cuarenta sesiones
caben en menos de 100 MB.

### Fuera de Git

- **`data/` local de este entorno.** Aquí están el crudo y las tablas de la captura de prueba del
  sábado (`2026-09-25Tinmediata-185224`). El contenedor es efímero, así que esos archivos no se
  conservan. Sus cifras sí quedaron en `reports/verificacion_alpaca/2026-09-25/`.
- **Credenciales.** Están en las variables de entorno del entorno de Claude: `APCA_API_KEY_ID`,
  `APCA_API_SECRET_KEY` y `ALPACA_PAPER`. Para el workflow irán como secretos del repositorio privado.
  El código no lee `ALPACA_DATA_FEED` ni `OPTIONS_DATA_PROVIDER`: el feed sale de
  `configs/captura_alpaca.toml`, que queda versionado.

---

## 6. Qué falta

### Tu parte, antes del lunes 28 hacia las 09:15 ET

- [ ] Crear en GitHub el repositorio privado vacío `QuantileFlow-datos`.
- [ ] Agregarle los secretos de Actions `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY`.
- [ ] Copiar ahí el contenido de `ops/repo_datos/`, o dar acceso a la app de GitHub de Claude a ese
      repositorio para que lo suba Claude. Si lo subes tú, GitHub te avisará por correo cuando falle una
      corrida programada: esos avisos le llegan a quien modificó el cron por última vez.
- [ ] Probar en **Actions → captura-0945 → Run workflow** con la opción «ahora», y en
      **Actions → historico-alpaca → Run workflow**.
- [ ] Dejar correr 3–5 sesiones y revisar los registros de `ejecuciones/`: puntualidad, estados y
      recuperaciones.

### Siguiente trabajo técnico

- [ ] Diagnosticar la primera sesión real (`verificar_alpaca.py --fecha 2026-09-28`) y revisar con
      ella `desfase_spot_max_s` (hoy 2 s, avisará en casi todas las capturas) y `edad_maxima_s`.
- [ ] Decidir OPRA con 3–5 sesiones reales.
- [ ] Piloto de 20–40 sesiones en `reports/piloto/` y congelar los umbrales en una versión nueva de
      `configs/piloto.toml`.
- [ ] Curva de tasas con fuente para la referencia del forward (FRED y el Tesoro responden desde el
      entorno).
- [x] Dividendos de SPY: eventos corporativos de Alpaca, rendimiento total y de precio.
- [ ] B4: pérdida robusta en el ajuste de superficie.
- [x] Precio objetivo independiente: SPY observado en el SIP histórico
      ([respuesta a la revalidación](respuesta_revalidacion_d815bdd.md)).
- [ ] Los workflows están fijados al commit `f2a5663` (`REF_CODIGO`): actualizarlo es cambiar la
      versión de medición.

---

## 7. Comandos

```bash
pip install -r requirements-bloqueo.txt
make test                                                   # 191 pruebas
python scripts/capturar_alpaca.py --ahora                   # captura de prueba inmediata
python scripts/capturar_alpaca.py                           # día hábil: espera y captura 09:45 y 10:00 ET
python scripts/capturar_alpaca.py --recuperar               # convierte diarios sin manifiesto
python scripts/historico_alpaca.py --esperar                # SIP de SPY (pasados 15 min) y dividendos
python scripts/verificar_alpaca.py --fecha 2026-09-28       # diagnóstico agregado
python scripts/normalizar_alpaca.py --desde 2026-09-28 --hasta 2026-11-13
N=data/normalized/alpaca
python scripts/piloto.py --cotizaciones $N/cotizaciones.parquet --subyacente $N/subyacente.parquet \
    --dividendos $N/dividendos.parquet --cobertura-dividendos $N/cobertura_dividendos.parquet \
    --fuente-objetivo alpaca/sip --desde 2026-09-28 --hasta 2026-11-06
```

Con el repositorio de datos clonado al lado, se agrega `--datos ../QuantileFlow-datos` a los scripts
de Alpaca.

## 8. Contexto anterior

- [Plan de trabajo](plan_de_trabajo.md), [avance y pendientes](avance_y_pendientes.md),
  [cómo proseguir](como_proseguir.md) y [estado de la continuación](estado_continuacion.md): la
  propuesta técnica, el núcleo y el pipeline del piloto construidos con datos sintéticos antes de
  esta sesión.
