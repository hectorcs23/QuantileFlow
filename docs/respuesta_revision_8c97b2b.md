# QuantileFlow: respuesta a la revisión de `8c97b2b`

**Fecha:** 27 de septiembre de 2026.
**Revisión recibida:** «revisión de SPY, dividendos y operación», sobre `8c97b2b` (código de captura
`fcb8637`).
**Commits:** en la rama `claude/lucid-hamilton-hz8l80`:
- [`6f0e748`](https://github.com/hectorcs23/QuantileFlow/commit/6f0e748): cobertura de dividendos
  separada y versiones de eventos y etiquetas;
- [`f2a5663`](https://github.com/hectorcs23/QuantileFlow/commit/f2a566353d8d6ac9979b5af2a241b15ac64b906e):
  plazo de preparación para que el respaldo llegue al corte;
- la documentación.

**Commit fijado en los workflows:** `f2a5663`.
**Registro de verificación:** [`reports/verificacion/f2a566353d8d.json`](../reports/verificacion/f2a566353d8d.json).
Árbol limpio, 191 pruebas pasadas (186 en `8c97b2b`).

> **Nota posterior (revalidación de `a5e2748`):** la política de esta entrega tenía tres fallos, ya
> corregidos:
> - el filtro «reconciliada» admitía una ausencia sin resolver como dividendo cero;
> - contaba como cobertura consultas que no pedían dividendos;
> - el replay de un instante exponía un estado futuro.
>
> Los estados son ahora provisional, aceptada (bajo la política de 60 días, una regla y no una
> garantía) y pendiente, y una ausencia abre una discrepancia en vez de retirar. Donde este documento
> dice «reconciliada», léase la política anterior. Ver
> [respuesta a la revalidación de `a5e2748`](respuesta_revalidacion_a5e2748.md).

> Coincido con el dictamen. Los tres hallazgos se reprodujeron con las cifras de la revisión, se
> convirtieron en pruebas y se corrigieron. La premisa sobre Alpaca era falsa y se retira: la propia
> documentación que había descargado lo advierte. El respaldo de la misma hora ahora llega al corte
> cuando el titular se cuelga antes de estar listo. El rendimiento total queda con estados
> **provisional, reconciliada y revisada**. Recomiendo usar solo etiquetas reconciliadas para
> entrenar, calibrar o reportar resultados.

---

## 1. Método

1. Reproduje los tres casos contra `8c97b2b`, sin red y con el transporte falso de las pruebas:
   - **P1:** la etiqueta del 17→18 de noviembre sale `ok` con madurez el 18 a las 10:00, y el filtro la
     muestra a esa hora.
   - **P2, retirada:** el dividendo retirado se sigue sumando: `log(101.8/100) = 0.0178399181`.
   - **P2, consulta vacía:** una consulta vacía produce el motivo «sin consulta de dividendos».
   - **Respaldo:** el escenario se confirma por configuración. El plazo absoluto es 09:46 y el
     último arranque permitido, 09:43.
2. Rediseñé la cobertura y los dividendos. Las pruebas nuevas cubren el caso exacto de cada
   hallazgo.
3. Repetí los tres casos con el código corregido:
   - **P1:** la etiqueta madura el 20 a las 16:00 y no se ve el 18 a las 10:00.
   - **P2, retirada:** hay dos versiones, con 1.80 y con 0. La vigente vale 0, y en un instante
     anterior al retiro se sigue viendo 0.0178.
   - **P2, consulta vacía:** la consulta queda en la cobertura con 0 eventos y la etiqueta sale `ok`.
4. Verifiqué con la cuenta de Alpaca la normalización de eventos reales y los dos plazos de la
   captura (sección 5).

---

## 2. Hallazgos

| # | Qué cambió | Dónde | Pruebas |
|---|---|---|---|
| P1 · la confirmación futura se retrotraía | La etiqueta con rendimiento total madura con su **consulta habilitante**: la primera consulta completa recibida después del fin que cubre el periodo. Su recepción entra en `label_available_at`. Una consulta posterior no puede volver disponible una etiqueta en el pasado. `conocido_hasta` reconstruye lo sabido en cualquier instante. | `etiquetas.etiquetas_retorno`, `_con_dividendos`, `_cubre` | `test_una_consulta_futura_no_habilita_etiquetas_en_el_pasado`: el caso de la tabla y la invariancia al añadir consultas, comparada con la reconstrucción `conocido_hasta` |
| P2 · un evento retirado se seguía sumando | Los dividendos son **versiones**. Cada una lleva `recibido_utc` (desde cuándo se conoce) y `retirado_utc`/`motivo_retiro`. Una versión se retira si una consulta comparable la corrige (`corregido`) o ya no la trae (`ausente`). Comparable quiere decir completa, con el mismo `data_quality`, con tipos que incluyen dividendos y con un intervalo que contiene su fecha de proceso. La ausencia no se da por cancelación segura, pero deja de sumarse y la etiqueta queda revisada. Nada se borra. | `alpaca.normalizar_eventos`, `_comparable`, `contrato.DIVIDENDOS` | `test_versiones_y_cobertura_de_los_eventos_corporativos` (aparición, corrección, ausencia, ausencia no comparable), `test_versiones_de_un_dividendo_revisan_la_etiqueta` (retirada, importe y fecha ex, antes y después de conocerlos) |
| P2 · una consulta vacía perdía su evidencia | Tabla propia **`COBERTURA_DIVIDENDOS`**: una fila por consulta y símbolo, con intervalo, campo de fecha del filtro (`process_date`), recepción, estado (completa, parcial o fallida), número de eventos, filtros e identificador. Existe con cien eventos o con cero. | `contrato.COBERTURA_DIVIDENDOS`, `alpaca.normalizar_eventos`, `scripts/normalizar_alpaca.py`, `--cobertura-dividendos` | `test_consulta_vacia_distinta_de_fallida_o_inexistente` (vacía, fallida, inexistente, que no cubre), `test_validacion_de_dividendos_y_su_cobertura` |
| §5 · la completitud no está garantizada | La premisa se retira (sección 4). El rendimiento total pasa a tener estados: **provisional** al madurar; **reconciliada** con una consulta que cubre el periodo, recibida `margen_proceso_dias` (60) después del fin; **revisada** si una versión posterior cambia el valor. Cada etiqueta tiene una fila por versión, con `vigente_desde_utc` y `vigente_hasta_utc`. `etiquetas_maduras(..., politica="reconciliada")` filtra por el estado. | `etiquetas.py`, `configs/piloto.toml` (`margen_proceso_dias`), `piloto.py` (`estado_div_{h}_objetivo`), informe | `test_reconciliacion_despues_del_margen_de_proceso`, `test_dividendo_en_el_rendimiento_total_y_en_la_madurez` |
| §6 · el respaldo no rescataba un titular colgado | **Plazo de preparación.** La captura debe estar lista (contratos y vencimientos) 6 minutos antes del corte; una ejecución que arranca tarde tiene al menos 2 minutos, sin pasar del inicio de la ráfaga. Si no lo está, termina con código 4 y deja el registro. Así el respaldo, en cola en el mismo grupo, arranca antes de la compuerta de las 09:43. Además, el histórico registra el estado de cada hora del rango, así que un corte perdido queda anotado aunque no haya corrido ninguna captura. | `alpaca.plazo_preparacion`, `alpaca.Vigilante` (`motivo`, `al_vencer`), `scripts/capturar_alpaca.py`, `scripts/historico_alpaca.py`, `configs/captura_alpaca.toml` | `test_plazo_de_preparacion_deja_llegar_al_respaldo`, `test_vigilante_de_preparacion_registra_y_termina` |

---

## 3. La política de dividendos, completa

**Qué acredita una consulta.** Una consulta con todas sus páginas acredita que la descarga terminó.
No acredita que el proveedor ya tuviera todos los anuncios. Por eso la cobertura se guarda aparte y
cada etiqueta dice en qué estado está.

**Cuándo una consulta cubre una etiqueta.**
- Alpaca filtra por `process_date`, que en un dividendo en efectivo es el pago, posterior a la fecha
  ex. Por eso el intervalo debe empezar antes del inicio de la etiqueta y llegar hasta el fin más
  `margen_proceso_dias`.
- En los seis dividendos de SPY observados, el proceso cae entre 41 y 43 días después de la fecha ex;
  el margen es de 60.
- La cobertura guarda el campo que filtra (`campo_fecha`). No se equipara `process_date` con
  `ex_date`: se consulta por la primera y los derechos se calculan con la segunda.

**Provisional.** La etiqueta madura con la consulta habilitante y vale con los dividendos conocidos
en ese momento. Un anuncio que Alpaca publique tarde no está en ese valor.

**Reconciliada.** Una consulta que cubre el periodo llega al menos 60 días después del fin. Para
entonces, cualquier dividendo con fecha ex en el periodo ya fue procesado, y Alpaca documenta que
los eventos procesados se devuelven siempre con el filtro por omisión (`data_quality=complete`). Es la
garantía más fuerte que da el endpoint, y depende de que el proceso no tarde más que el margen.

**Revisada.** Una versión posterior cambia el valor: un anuncio tardío, una corrección de importe o
de fecha ex, o una retirada. La etiqueta gana otra fila y la anterior se conserva con su vigencia.

**Uso.** `etiquetas_maduras(etiquetas, t)` devuelve, para el instante `t`, la versión vigente y ya
madura. Con `politica="reconciliada"`, solo las reconciliadas en `t`. Recomiendo:
- entrenamiento, calibración y resultados predictivos: solo `reconciliada`;
- seguimiento: la versión provisional.

Con 60 días de margen, una etiqueta se puede usar para evaluar unos dos meses después de su fin.

**No resuelto:**
- Las ausencias se tratan como retiro. No hay una segunda fuente (el emisor) para contrastar las
  distribuciones de SPY: esa integración está sin definir ni validar.
- `data_quality=all`, que adelanta registros incompletos, podría servir como aviso temprano de
  anuncios pendientes. No se usa todavía.

---

## 4. Correcciones a lo que dijo la entrega anterior

- **«Un dividendo aparece desde que se anuncia.»** Era una sola observación (el dividendo del 18 de
  septiembre listado antes de su pago), no una garantía. La documentación de Alpaca dice: *«Currently
  Alpaca has no guarantees on the creation time of corporate actions… corporate actions may not be
  available immediately after they are announced»*. El filtro por omisión, además, excluye registros
  incompletos todavía no procesados. Quedó corregido en `fuente_alpaca.md` y en
  `respuesta_revalidacion_d815bdd.md`.
- **SPX implícito frente a SPY.** Comparar el nivel implícito con SPY del SIP es un diagnóstico amplio
  de coherencia del forward. **No mide el sesgo de RR25 del feed indicativo**: dos cadenas pueden dar
  un forward parecido y un skew distinto. Para eso hace falta una referencia de opciones comparable,
  como OPRA. La lista de «qué mirar» de la entrega anterior lo sugería mal y se corrigió.

---

## 5. Verificación con la cuenta de Alpaca

Solo agregados:

| Prueba | Resultado |
|---|---|
| Eventos reales de SPY con la normalización nueva | 2 consultas completas en la cobertura (5 eventos cada una) y 5 dividendos, todos en su versión 1. Cada versión se conoce desde la primera consulta que la trajo; la segunda consulta, con los mismos valores, no abre versiones nuevas. |
| Captura inmediata real con los dos plazos | Lista a los 2 s. El registro de la ejecución trae `listo_utc`, `listo_antes_utc` y `plazo_utc`, y el plazo absoluto queda después del de preparación. |
| Histórico en una carpeta sin capturas | Registra las horas del rango como `perdida`. |
| Diagnóstico del 25 de septiembre, regenerado | Idéntico byte a byte. |

---

## 6. Operación: qué rescata ahora el respaldo y qué no

Cronología de las 09:45 con un titular colgado mientras se prepara (hora de Nueva York):

| Paso | Hora |
|---|---|
| Arranque del titular (cron de las 09:11, con su retraso habitual) | ≈ 09:13 |
| Plazo de preparación: si no está listo, termina con código 4 y registra | 09:39 |
| Recuperación y commit del crudo del titular; se libera el grupo `captura-0945` | ≈ 09:40 |
| El respaldo (cron de las 09:26, en cola) arranca y pasa la compuerta | ≈ 09:40–09:41 (compuerta: 09:43) |
| Preparación del respaldo (dependencias, contratos, vencimientos) | ≈ 09:42–09:43 |
| Ráfaga | 09:44:55 |

**Qué sigue sin rescatarse:**
- **Un cuelgue durante la ráfaga**, ya pasadas las 09:44:55. El plazo absoluto (09:46) conserva lo que
  llegó como `parcial` o `fallida`, pero el instante de mercado se pierde.
- **Que no corra ninguna ejecución.** Queda registrado: el histórico de las 10:21 anota la hora como
  `perdida` aunque no haya corrido ninguna captura.

No adopté colectores independientes. Duplicarían la carga y el crudo cada día para un riesgo todavía
no observado. Si en las sesiones de prueba aparecen cuelgues en la ráfaga, es el siguiente paso: los
contratos repetidos ya se marcan como `reemplazada` y no se duplican en la medida.

---

## 7. Cambios de interfaz y de resultados

- **`DIVIDENDOS`:** son versiones.
  - Pierde `consultado_utc`, porque la cobertura va en `COBERTURA_DIVIDENDOS`.
  - Gana `retirado_utc` y `motivo_retiro`, y el adaptador añade `version`.
- **Etiquetas:** columnas nuevas `version`, `vigente_desde_utc`, `vigente_hasta_utc`,
  `estado_dividendos`, `consulta_habilitante_utc` y `reconciliada_utc`. Con rendimiento total,
  `dividendos` es NaN si el total falta; antes era 0 y podía confundirse con «sin dividendos».
- **Piloto:**
  - `ejecutar(..., cobertura=...)` y la opción `--cobertura-dividendos`.
  - La tabla diaria añade `estado_div_{h}_objetivo`.
  - El alcance resume las consultas y cuenta los estados.
- **Normalización:** escribe `cobertura_dividendos.parquet`.
- **Configuración:**
  - piloto: `[objetivo] margen_proceso_dias = 60`;
  - captura: `preparacion_s = 360` y `preparacion_minima_s = 120`.
- **Versión de medición:** `REF_CODIGO` pasa de `fcb8637` a `f2a5663`.
- **Plantilla sintética:**
  - Los dividendos se consultan cada sesión a las 10:21, como el workflow del histórico, y la
    etiqueta del objetivo madura a esa hora.
  - Una consulta final, el día de la descarga, reconcilia las 28 etiquetas a 1 sesión.
  - Las medidas de SPXW, en `tabla_todas_las_horas.csv`, no cambian.

---

## 8. Qué sigue

| Prioridad | Trabajo | Estado |
|---|---|---|
| Antes de usar etiquetas | Cobertura separada y madurez con la consulta habilitante | Hecho (`6f0e748`) |
| Antes de usar el rendimiento total | Eventos versionados, retiradas y reconciliación | Hecho (`6f0e748`). Falta decidir si se contrasta con el emisor. |
| En paralelo | Repositorio privado y 3–5 sesiones | Pendiente de tu parte. El repositorio sigue sin aparecer (404). |
| Durante esas sesiones | Puntualidad, faltantes, recuperaciones, horas `perdida` y cuántas veces actúa el plazo de preparación | Queda en los registros de `ejecuciones/` |
| Después | Aptitud del feed (OPRA) y umbrales congelados antes de evaluar | Sin cambios |

No se tocaron el transporte, los regímenes ni la optimización de posiciones.
