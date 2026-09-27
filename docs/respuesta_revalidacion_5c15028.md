# QuantileFlow: respuesta a la revalidación de `5c15028`

**Fecha:** 27 de septiembre de 2026.
**Revisión recibida:** «revalidación de 5c15028» (código de captura `8316540`).
**Commits:** en la rama `claude/lucid-hamilton-hz8l80`:
- [`7fb0585`](https://github.com/hectorcs23/QuantileFlow/commit/7fb058525d93ebe1366165d16055d3dd103d1579):
  dividendos incompletos como versiones con discrepancia;
- la documentación.

**Commit fijado en los workflows:** `7fb0585`. La captura no cambia de comportamiento: desde `f2a5663`,
`capturar_alpaca.py`, `historico_alpaca.py` y `captura_alpaca.toml` no cambian, y en `alpaca.py` solo
cambia la normalización de eventos.
**Registro de verificación:** [`reports/verificacion/7fb058525d93.json`](../reports/verificacion/7fb058525d93.json).
Árbol limpio, 200 pruebas pasadas (197 en `5c15028`).

> Coincido con el dictamen. Reproduje el caso con las cifras de la revisión, lo convertí en prueba de
> regresión y lo corregí.
>
> Un dividendo que llega sin fecha ex o sin monto ya no se aparta. Es una versión con la discrepancia
> `incompleto`, y deja **pendientes** las etiquetas cuyo periodo podría contener su fecha ex. Así
> sigue hasta que el proveedor lo complete o una resolución registrada dé la fecha ex y el monto. Se
> cumplen los cinco criterios de aceptación.

---

## 1. Método

1. **Reproduje el caso contra `5c15028`** con el adaptador real, transporte falso, crudo y manifiesto.
   El dividendo de 1.80 llega sin fecha ex, con proceso y pago el 30 de diciembre, en una consulta
   completa del 20 de enero. La tabla de dividendos queda vacía y el evento va a «otros» con fecha 30
   de diciembre, así que no bloquea el rango del 17 y 18 de noviembre. La etiqueta sale `aceptada`, con
   dividendos 0, y la política aceptada la admite.
2. **Corregí la normalización, el contrato y la capa de etiquetas** (sección 2). Las pruebas nuevas
   recorren los cinco criterios de aceptación desde el crudo.
3. **Repetí el caso con el código corregido:** hay una versión con la discrepancia `incompleto`, y la
   etiqueta queda `pendiente` con el motivo
   «dividendo sin fecha ex (1.8) recibido incompleto desde 2026-01-20 21:00:00+00:00, con fecha ex
   posible entre 2025-10-31 y 2025-12-30, sin resolver». La política aceptada ya no la admite.

---

## 2. El hallazgo y la corrección

| Qué cambió | Dónde | Pruebas |
|---|---|---|
| Un dividendo sin fecha ex o sin monto es una **versión** más, con la discrepancia `incompleto`, que lo marca desde que se recibe. Sin fecha ex, guarda el intervalo de su fecha de proceso (`proceso_desde`, `proceso_hasta`): la del proveedor o, si falta, el intervalo de la consulta que lo trajo, que filtra por esa fecha. | `alpaca.normalizar_eventos`, `contrato.DIVIDENDOS` | `test_un_dividendo_incompleto_deja_pendientes_las_etiquetas_que_podria_afectar`, `test_validacion_de_dividendos_y_su_cobertura` |
| Las etiquetas cuyo periodo **podría contener** su fecha ex quedan `pendientes`, y no se suma al valor porque no se sabe si corresponde. Sin monto pero con fecha ex, solo la etiqueta que la contiene. La capa de etiquetas lo trata así aunque la tabla no traiga la discrepancia. | `etiquetas._versiones`, `_afecta`, `_con_dividendos` | `test_un_dividendo_sin_fecha_ex_afecta_las_etiquetas_que_podrian_contenerla` |
| Lo resuelve el **registro completo** del proveedor (una versión nueva, `corregido`) o una **resolución «vigente» con la fecha ex y el monto** que falten. `RESOLUCIONES_DIVIDENDOS` gana `fecha_ex` y `monto`: completan lo que falta y no corrigen un valor ya dado. Una «vigente» sin ellos, o que contradiga lo conocido, detiene la normalización. | `alpaca._completar`, `alpaca.cargar_resoluciones`, `contrato.RESOLUCIONES_DIVIDENDOS` | la misma prueba de punta a punta (registro completo y resolución) |
| Un listado con **menos datos** que la versión vigente no es novedad: no la corrige ni la reabre. Uno que trae un campo que faltaba, o un valor distinto, sí. | `alpaca._novedad` | la misma prueba: el proveedor sigue trayéndolo incompleto después de la resolución |
| Un dividendo **sin identificador** recibe uno estable, derivado de su contenido. **Sin símbolo**, toma el de la consulta si pidió uno solo. Si aun así no se puede atribuir, **detiene la normalización** con cualquier fecha, porque no se sabe a qué etiquetas toca. La cobertura cuenta los atribuidos. | `alpaca._identificar`, `tablas_para_piloto` | `test_un_dividendo_sin_simbolo_atribuible_detiene_la_normalizacion` |

---

## 3. Cómo se acota una fecha ex desconocida

Alpaca filtra los eventos por `process_date`. La política ya supone que el proceso cae entre la fecha
ex y 60 días después: en ese supuesto se basa para dar por cubierta una etiqueta. Con el mismo
supuesto, un dividendo con la fecha de proceso entre `P₀` y `P₁` tiene la fecha ex entre `P₀ − 60 días`
y `P₁`. En el caso de la revisión, eso va del 31 de octubre al 30 de diciembre, y el periodo del 17 y
18 de noviembre cae dentro.

No uso las fechas de registro ni de pago para estrechar el intervalo. Añadirían supuestos que la
política no hace: en un dividendo especial grande, la fecha ex cae después del pago.

**Límite:** si el supuesto de los 60 días falla, fallan a la vez la cobertura y este intervalo. Por
eso se miden las etiquetas que cambian después de aceptarse (`revisadas_tras_aceptar_objetivo`).

---

## 4. Criterios de aceptación

| Criterio | Cómo se cumple | Prueba |
|---|---|---|
| El caso no pasa `politica="aceptada"` | Queda `pendiente` desde el 20 de enero, sin fecha de caducidad | `test_un_dividendo_incompleto_…` (1) y la reproducción |
| La recepción incompleta no altera lo conocido antes | Hasta el 20 de enero sigue `aceptada` con 0, también en la reconstrucción truncada. En la capa de etiquetas, nada queda pendiente antes de recibirlo. | `test_un_dividendo_incompleto_…` (2), `test_un_dividendo_sin_fecha_ex_…` |
| Con la fecha ex o una resolución, se actualiza desde ese momento | **Registro completo** el 20 de febrero: la etiqueta pasa a 1.80 y queda `aceptada` desde esa consulta. **Resolución** con la fecha ex el 1 de febrero: `provisional` con 1.80 desde entonces, y `aceptada` con la consulta siguiente. | `test_un_dividendo_incompleto_…` (3 y 3′) |
| Una respuesta de verdad vacía se comporta como antes | Queda `aceptada` con 0 | `test_un_dividendo_incompleto_…` (4) y las pruebas anteriores |
| Una fecha ex conocida fuera del periodo no bloquea etiquetas ajenas | Ninguno de estos casos cambia la etiqueta de noviembre: <br>• fecha ex el 19 de diciembre, completo; <br>• fecha ex el 19 de diciembre, sin monto; <br>• sin fecha ex, con proceso el 30 de junio. <br>En la capa de etiquetas, solo quedan pendientes las etiquetas cuyo periodo toca del 31 de octubre al 30 de diciembre. Con fecha ex pero sin monto, solo la del 18 al 19 de diciembre. | `test_un_dividendo_incompleto_…` (5), `test_un_dividendo_sin_fecha_ex_…` |

---

## 5. Verificación

| Prueba | Resultado |
|---|---|
| Eventos reales de SPY (las 3 consultas guardadas) con `7fb0585` | 5 dividendos completos, ninguno incompleto, sin discrepancias |
| Diagnóstico del 25 de septiembre, regenerado con `7fb0585` | Idéntico byte a byte |
| Scripts de punta a punta, con un crudo sintético y un dividendo sin fecha ex | El Parquet conserva las fechas nulas. El manifiesto de la normalización resume `{"incompleto": 1}` abierta. El piloto cuenta «1 pendiente», con el motivo y el intervalo. |
| Plantilla sintética regenerada | Etiquetas y tabla diaria idénticas. Cambian el texto del alcance y el hash de la entrada de dividendos, que gana dos columnas. |

---

## 6. Cambios de interfaz

- **`DIVIDENDOS`:**
  - `fecha_ex` y `monto` pasan a ser opcionales;
  - columnas nuevas `proceso_desde` y `proceso_hasta`;
  - discrepancia nueva `incompleto`;
  - el contrato exige que un dividendo incompleto lleve su discrepancia y, sin fecha ex, su intervalo
    de proceso.
- **`RESOLUCIONES_DIVIDENDOS`:** `fecha_ex` y `monto`, opcionales en el CSV.
- **Etiquetas:** el motivo de una pendiente por un dividendo incompleto da el intervalo de fechas ex
  posibles.
- **Tablas ya normalizadas:** hay que renormalizar desde el crudo, porque el esquema volvió a cambiar.
- **Versión de medición:** `REF_CODIGO` pasa de `8316540` a `7fb0585`.

---

## 7. Qué sigue

Sigo la recomendación de la revisión:
- **Captura:** la experimental continúa.
- **Piloto real:**
  - renormalizar desde el crudo;
  - seleccionar las etiquetas con `politica="aceptada"` de forma explícita;
  - la vista provisional incluye las pendientes, pero solo para diagnóstico.
- **Alcance de las primeras sesiones:**
  - las 3–5 sesiones comprueban la operación, no la capacidad predictiva;
  - la puntualidad del respaldo en GitHub Actions sigue sin certificar: la medirán los registros de
    `ejecuciones/`.

| Prioridad | Trabajo | Estado |
|---|---|---|
| En paralelo | Repositorio privado y 3–5 sesiones | Pendiente de tu parte: `QuantileFlow-datos` sigue sin aparecer |
| Durante esas sesiones | Puntualidad, faltantes, recuperaciones, activaciones del respaldo, y discrepancias (también las `incompleto`) | Quedan en `ejecuciones/` y en el manifiesto de cada normalización |
| Antes de entrenar | Revisar `revisadas_tras_aceptar_objetivo` y las discrepancias abiertas. Decidir si se marca un trimestre de SPY sin dividendo listado. | Por decidir |
| Después | Aptitud del feed (OPRA) y umbrales congelados antes de evaluar | Sin cambios |
