# QuantileFlow: respuesta a la revalidación de `a5e2748`

**Fecha:** 27 de septiembre de 2026.
**Revisión recibida:** «revalidación de la entrega de Claude», sobre `a5e2748` (código de captura
`f2a5663`).
**Commits:** en la rama `claude/lucid-hamilton-hz8l80`:
- [`c5aaded`](https://github.com/hectorcs23/QuantileFlow/commit/c5aaded207ccc64b42becbd479174928d6a0a968):
  ausencias como discrepancias pendientes y tramos de etiqueta con estado puntual;
- [`8316540`](https://github.com/hectorcs23/QuantileFlow/commit/8316540a70dd4c9024a1df90bff3c10d2ff0ac88):
  medir las revisiones del objetivo después de aceptarse;
- la documentación.

**Commit fijado en los workflows:** `8316540`. La captura no cambia de comportamiento: desde `f2a5663`,
`capturar_alpaca.py`, `historico_alpaca.py` y `captura_alpaca.toml` no cambian, y en `alpaca.py` solo
cambia la normalización de eventos.
**Registro de verificación:** [`reports/verificacion/8316540a70dd.json`](../reports/verificacion/8316540a70dd.json).
Árbol limpio, 197 pruebas pasadas (191 en `a5e2748`).

> **Nota posterior (revalidación de `5c15028`):** esta entrega apartaba los dividendos recibidos sin
> fecha ex o sin monto, y uno así podía terminar como cero aceptado. Ahora son versiones con la
> discrepancia `incompleto`. Ver [respuesta a la revalidación de `5c15028`](respuesta_revalidacion_5c15028.md).

> Coincido con el dictamen y conservo la arquitectura. Reproduje los tres hallazgos con las cifras de
> la revisión, los convertí en pruebas de regresión y los corregí.
>
> «Reconciliada» desaparece. La política separa tres cosas: la **madurez**, la **aceptación** y las
> **discrepancias**. El estado se llama «aceptada bajo la política de 60 días»: es una regla que se
> mide, no una garantía.
>
> Una ausencia ya no retira un dividendo. Abre una discrepancia que deja la etiqueta **pendiente**
> hasta que la resuelva evidencia fechada. La captura experimental sigue como estaba.

---

## 1. Método

1. **Reproduje los tres casos contra `a5e2748`,** sin red. El primero pasa por el adaptador real, con
   transporte falso, crudo y manifiestos.
   - **P1:** la consulta del 20 de enero sin el dividendo lo retira (`motivo_retiro="ausente"`). El
     rendimiento pasa de 0.01784 a 0 (`revisada`), con `reconciliada_utc` del 20 de enero, y
     `etiquetas_maduras(..., politica="reconciliada")` lo admite ese mismo día.
   - **P2:** si la única consulta es una de splits, recibida el 20 de enero, la etiqueta sale `ok`,
     `reconciliada` y con dividendos 0.
   - **P3:** para el 1 de diciembre, el replay del histórico completo devuelve `reconciliada` con
     fecha de enero. La reconstrucción truncada devuelve `provisional`.
2. **Rediseñé la normalización de eventos y la capa de etiquetas.** Cada caso quedó como prueba de
   regresión; P1 y P2 también de punta a punta, del crudo a la vista de la política.
3. **Repetí los tres casos con el código corregido** y el mismo crudo:
   - **P1:** el dividendo sigue vigente, con la discrepancia `ausente` desde el 20 de enero. La
     etiqueta pasa de `provisional` a `pendiente`. La política aceptada la excluye:
     - el 20 de enero;
     - el 21 de marzo, con la ausencia repetida y pasados 60 días;
     - el 27 de septiembre.

     Antes de la ausencia se reconstruye provisional, con 1.80.
   - **P2:** «sin dividendos confirmados; 1 consultas sin dividendos en los tipos pedidos no cuentan».
   - **P3:** el 1 de diciembre y el 21 de enero, el histórico completo y la reconstrucción truncada
     coinciden en rendimiento, estado, versión, tramo y vigencia.
4. **Verifiqué con la cuenta de Alpaca** la normalización de eventos reales y regeneré el
   diagnóstico real (sección 6).

---

## 2. Hallazgos

| # | Qué cambió | Dónde | Pruebas |
|---|---|---|---|
| P1 · una ausencia sin resolver pasaba como reconciliada | Una ausencia en una consulta comparable ya **no retira** la versión: abre una discrepancia (`discrepancia="ausente"`, `discrepancia_desde_utc`). La capa de etiquetas la recibe y deja la etiqueta **`pendiente`**, con el valor conservado para diagnóstico, marcado, y con motivo. `politica="aceptada"` la excluye. Ni el paso del tiempo ni repetir la ausencia la resuelven: solo evidencia fechada (sección 3). | `alpaca.normalizar_eventos`, `contrato.DIVIDENDOS` y `RESOLUCIONES_DIVIDENDOS`, `alpaca.cargar_resoluciones`, `etiquetas._con_dividendos` | `test_una_ausencia_sin_resolver_deja_pendiente_la_etiqueta_despues_de_60_dias` (del crudo a la vista, antes y después de la ausencia), `test_ausencia_sin_resolver_queda_pendiente_y_fuera_de_la_politica_aceptada`, `test_resoluciones_registradas_resuelven_y_fijan_el_estado_del_dividendo`, `test_versiones_y_cobertura_de_los_eventos_corporativos` |
| P2 · una consulta de splits confirmaba dividendos | Una consulta cuenta como cobertura (habilitante o aceptadora) solo si cumple las cuatro condiciones: es completa, pide dividendos en efectivo (`tipos` = `todos` o incluye `cash_dividend`), usa la calidad admitida (`complete`) y filtra por un campo de fecha soportado. Las demás no cuentan, y el motivo de la etiqueta y el alcance del piloto dicen cuántas y por qué. El contrato valida `campo_fecha`. | `etiquetas._consultas`, `contrato.CAMPOS_FECHA_COBERTURA`, `piloto.alcance` | `test_una_consulta_sin_dividendos_en_sus_tipos_no_confirma_ni_acepta` (splits, `calidad="all"`, y `todos`, `cash_dividend` o ambos, que siguen funcionando), `test_rendimiento_total_sin_dividendos_queda_ausente` (en el piloto), `test_validacion_de_dividendos_y_su_cobertura` |
| P3 · el replay exponía un estado futuro | Cada etiqueta se parte en **tramos** de valor y estado constantes (`tramo`, `vigente_desde_utc`, `vigente_hasta_utc`); `version` cuenta los cambios de valor. `etiquetas_maduras(e, t)` devuelve el tramo vigente en `t`, con el estado de `t` y `vigente_hasta_utc` nulo. El almacén conserva todos los tramos para la auditoría. | `etiquetas._con_dividendos`, `etiquetas_maduras` | `test_la_vista_de_un_instante_coincide_con_la_reconstruccion_truncada`: estados, versión, tramo, vigencia y motivo, con las dos políticas y en muchos instantes, no solo rendimiento y madurez |
| §4 · 60 días son una política | El estado se llama `aceptada`: «aceptada bajo la política de 60 días (una regla, no una garantía de completitud)», también en el informe. Madurez, aceptación y discrepancias se definen por separado (sección 3). Se miden las revisiones: el alcance cuenta las etiquetas cuyo valor cambió **después de madurar** y **después de aceptarse**. La normalización resume versiones, retiros, discrepancias y contradicciones. | `etiquetas.py`, `piloto.py` (`revisadas_objetivo`, `revisadas_tras_aceptar_objetivo`), `informe.py`, `alpaca.resumen_dividendos`, `normalizar_alpaca.py`, `configs/piloto.toml` | `test_aceptada_despues_del_margen_de_proceso`, `test_revisiones_despues_de_madurar_y_de_aceptarse` |
| §5 · la cronología del respaldo | Se presenta como un escenario favorable, con sus supuestos, no como una garantía (sección 5). | `ops/repo_datos/README.md`, este documento | — |

---

## 3. La política de dividendos, en tres partes

**Madurez** (`label_available_at`). La etiqueta madura con la **consulta habilitante**: la primera
consulta recibida después del fin que puede confirmar dividendos (P2) y cuyo intervalo cubre el
periodo. Con el filtro de Alpaca por `process_date`, el intervalo debe llegar hasta el fin más 60 días.
Madurar no dice nada sobre la calidad del valor: solo que ya se puede usar para seguimiento.

**Aceptación** (bajo la política). Una etiqueta queda `aceptada` cuando se cumplen las tres
condiciones:
- una consulta que cubre el periodo llegó al menos 60 días después del fin;
- también llegó después del último cambio de valor y de la última discrepancia resuelta;
- no queda ninguna discrepancia abierta.

La regla sale de lo observado: en seis dividendos de SPY, el proceso cayó entre 41 y 43 días después
de la fecha ex. Además, Alpaca devuelve los eventos procesados con el filtro por omisión. Pero Alpaca
no garantiza cuándo publica un evento, y seis casos no prueban un máximo. Por eso se mide cuántas
etiquetas cambian después de aceptarse (`revisadas_tras_aceptar_objetivo`). Si alguna cambia, hay que
revisar el margen.

**Discrepancias** (`pendiente`). Una etiqueta queda pendiente mientras un dividendo de su periodo tenga
una discrepancia abierta. Cómo se abre y cómo se cierra:

| Evidencia, con su fecha | Efecto en las versiones | Efecto en la etiqueta |
|---|---|---|
| Una consulta comparable ya no trae el dividendo | Abre `ausente`; la versión sigue vigente | `pendiente`, con el valor anterior marcado |
| Otra ausencia | Nada | Sigue `pendiente` |
| El dividendo reaparece igual | Se cierra (`reaparecido`) y sigue una versión idéntica | `provisional`, o `aceptada` si esa consulta ya cumple la política |
| El dividendo reaparece con otros valores | Se cierra (`corregido`) y se abre la nueva | Nuevo valor (`version` + 1): `provisional`, o `aceptada` si esa consulta ya cumple la política |
| Resolución «vigente» | Se cierra (`confirmado`) y sigue una versión idéntica de origen `resolucion` | Con una discrepancia abierta, `provisional` hasta la siguiente consulta que cumpla la política; sin ella, no cambia |
| Resolución «cancelado» | Se cierra (`cancelado`); deja de sumarse | Nuevo valor, `provisional` hasta la siguiente consulta que cumpla |

Una consulta es **comparable** si es completa, usa el mismo filtro de calidad, pide dividendos en
efectivo y su intervalo contiene la fecha de proceso del dividendo.

**Resoluciones.** Son evidencia registrada a mano, por ejemplo el aviso de distribución del emisor.
Van en `resoluciones_dividendos.csv`, en la raíz del repositorio de datos, con estas columnas:

| Columna | Qué lleva |
|---|---|
| `id_evento` | El identificador del evento en Alpaca |
| `simbolo` | El símbolo |
| `resolucion` | `vigente` o `cancelado` |
| `conocido_utc` | Desde cuándo se conoce la evidencia, con zona explícita. Nunca antes de que se publicara la fuente. |
| `fuente` | De dónde sale la evidencia |
| `nota` | Opcional |

La normalización valida el archivo y registra su hash en el manifiesto. Rechaza un símbolo que no
coincide con el evento, una hora sin zona y una resolución repetida. Una resolución actúa en su
`conocido_utc`, haya o no una discrepancia abierta, así que el replay de un instante anterior no la
ve.

La evidencia fija el estado con los valores que tenía el dividendo:
- **Tras «vigente»:** la versión confirmada ya no abre discrepancias por ausencia. Si no, una omisión
  persistente del proveedor obligaría a registrar otra resolución cada día.
- **Tras «cancelado»:** si el proveedor vuelve a traer el dividendo igual, no aporta nada nuevo. Una
  resolución «vigente» posterior lo devuelve: nuevo valor, `provisional` hasta la siguiente consulta
  que cumpla la política.

Esas contradicciones sin valores nuevos no se descartan en silencio: se cuentan
(`omitido_tras_confirmar`, `listado_tras_cancelar`). Si el proveedor trae un dividendo cancelado **con
otros valores**, se abre la discrepancia `reaparece_cancelado`, que solo cierra otra resolución.

**Uso:**
- Entrenamiento, calibración y resultados predictivos: `etiquetas_maduras(e, t, politica="aceptada")`.
- Seguimiento: la vista provisional. Incluye las pendientes, marcadas.
- Con 60 días de margen, una etiqueta se acepta unos dos meses después de su fin.

**Lo que la política no resuelve:**
- **Un dividendo que Alpaca no publique nunca.** No hay ninguna versión que pueda faltar, así que
  ninguna discrepancia lo detecta, y la política lo acepta como cero. Solo lo detectaría una segunda
  fuente o una regla de calendario: SPY distribuye cada trimestre, así que un trimestre sin dividendo
  listado se podría marcar. No lo implementé; queda propuesto en la sección 8.
- **Las resoluciones valen lo que su fuente.** `conocido_utc` lo declara quien registra la resolución:
  el archivo guarda la fuente, pero no la verifica.

---

## 4. Correcciones a lo que dijo la entrega anterior

- **«Reconciliada … es la garantía más fuerte que da el endpoint».** Era una regla con nombre de
  garantía. Ahora se llama «aceptada bajo la política de 60 días» y se mide.
- **«Recomiendo usar solo etiquetas reconciliadas para entrenar».** Con `a5e2748`, ese filtro admitía
  una ausencia sin resolver como dividendo cero (P1). La recomendación vale ahora para
  `politica="aceptada"`, que excluye las pendientes.
- **«Las ausencias se tratan como retiro».** Figuraba como limitación pendiente. Ya no ocurre: una
  ausencia abre una discrepancia.
- **La cronología del respaldo.** Se presentó como una línea de tiempo. Es un escenario favorable que
  depende de supuestos (sección 5).

La [respuesta a la revisión de `8c97b2b`](respuesta_revision_8c97b2b.md) lleva una nota que remite
aquí.

---

## 5. Operación: la cronología del respaldo es un escenario favorable

La cronología de las 09:45 con el titular colgado antes de estar listo supone que cada paso tarda lo
habitual. Ninguno está garantizado:

| Paso | Hora supuesta (Nueva York) | De qué depende |
|---|---|---|
| Arranque del titular (cron de las 09:11) | ≈ 09:13 | GitHub retrasa los cron, a veces muchos minutos, y con carga puede no dispararlos |
| Plazo de preparación: código 4 y registro | 09:39 | Lo impone el propio proceso |
| Recuperación y commit del crudo del titular; se libera el grupo | ≈ 09:40 | Del commit y del push, que pueden reintentar |
| Arranque del respaldo (cron de las 09:26, en cola) y compuerta | ≈ 09:40–09:41 (compuerta: 09:43) | De que el disparo del respaldo exista y esté en cola, y de la asignación de una máquina |
| Preparación del respaldo | ≈ 09:42–09:43 | Del checkout, `setup-python`, la instalación desde la caché y las consultas de contratos |
| Ráfaga | 09:44:55 | — |

Si algún paso se alarga lo bastante, el respaldo no pasa la compuerta o no está listo a tiempo. La hora
queda entonces `parcial`, `fallida` o `perdida`, y queda registrada. Sigue fuera de lo resuelto el
cuelgue durante la ráfaga.

Las 3–5 sesiones de prueba medirán la cronología real con los registros de `ejecuciones/`:
- arranque de cada disparo;
- `listo_utc` y `plazo_utc`;
- cuántas veces actúa el plazo de preparación;
- si el respaldo llegó.

Una corrida en verde en Actions no lo demuestra.

---

## 6. Verificación con la cuenta de Alpaca

Solo agregados:

| Prueba | Resultado |
|---|---|
| Eventos reales de SPY con la normalización nueva | 3 consultas completas (2 anteriores y una de hoy), con 5 eventos cada una. Quedan 5 dividendos, todos en su versión 1, sin retiros, discrepancias ni anotaciones. Repetir una consulta comparable no abre nada. |
| Credenciales en el crudo | Ninguna en los 27 archivos revisados |
| Diagnóstico del 25 de septiembre, regenerado con `8316540` | Idéntico byte a byte (informe, resumen y gráficas) |
| Normalización y piloto de punta a punta, con un crudo sintético y un dividendo ausente | Sin resoluciones: 1 discrepancia abierta y la etiqueta `pendiente`. Con una resolución «vigente»: versión confirmada, etiqueta `provisional` y el hash del archivo en el manifiesto. |

---

## 7. Cambios de interfaz y de resultados

- **`DIVIDENDOS`:**
  - gana `discrepancia` y `discrepancia_desde_utc`;
  - los motivos de retiro son `corregido`, `cancelado`, `reaparecido` y `confirmado` (ya no `ausente`);
  - el adaptador añade `origen` (`consulta` o `resolucion`).
- **`RESOLUCIONES_DIVIDENDOS`** (nuevo), con `alpaca.cargar_resoluciones`.
- **`COBERTURA_DIVIDENDOS`:** `campo_fecha` se valida (`ex_date`, `process_date` o `payable_date`).
- **Etiquetas:**
  - `estado_dividendos` vale `provisional`, `aceptada`, `pendiente` o `no aplica`;
  - columna nueva `tramo`;
  - `version` cuenta los cambios de valor;
  - se va `reconciliada_utc`;
  - la política es `etiquetas_maduras(..., politica="aceptada")` (antes `"reconciliada"`).
- **Piloto:**
  - la tabla diaria añade `version_{h}_objetivo`;
  - el alcance cuenta provisionales, aceptadas y pendientes, y las revisiones después de madurar y
    después de aceptarse;
  - solo cuentan las consultas que pueden confirmar dividendos, y el alcance dice cuántas no cuentan.
- **Normalización:**
  - opción `--resoluciones` (por omisión, `<datos>/resoluciones_dividendos.csv` si existe);
  - el manifiesto registra `resoluciones` (archivo, hash y filas) y `dividendos` (resumen de revisiones).
- **Versión de medición:** `REF_CODIGO` pasa de `f2a5663` a `8316540`.
- **Plantilla sintética:**
  - Las 28 etiquetas a 1 sesión quedan aceptadas, con 0 revisiones.
  - Cada etiqueta del objetivo tiene dos tramos, provisional y aceptada, así que `etiquetas.csv` pasa
    de 140 a 200 filas.
  - Las medidas de SPXW y las figuras no cambian.
- **Tablas ya normalizadas:** la de dividendos cambia de esquema, así que hay que renormalizar desde
  el crudo. Todavía no hay sesiones reales, así que no afecta a ningún dato.

---

## 8. Qué sigue

| Prioridad | Trabajo | Estado |
|---|---|---|
| En paralelo | Repositorio privado y 3–5 sesiones | Pendiente de tu parte: `QuantileFlow-datos` sigue sin aparecer |
| Durante esas sesiones | Puntualidad, faltantes, recuperaciones, horas `perdida`, activaciones del plazo de preparación y del respaldo, y discrepancias y revisiones de dividendos | Quedan en `ejecuciones/` y en el manifiesto de cada normalización |
| Antes de entrenar | Revisar `revisadas_tras_aceptar_objetivo` y las discrepancias abiertas. Decidir si se marca un trimestre de SPY sin dividendo listado. | Por decidir |
| Después | Aptitud del feed (OPRA) y umbrales congelados antes de evaluar | Sin cambios |

No se tocaron la captura, el transporte, los regímenes ni la optimización de posiciones.
