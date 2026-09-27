# QuantileFlow: respuesta al cierre de la revalidación de `b240dc2`

**Fecha:** 27 de septiembre de 2026.
**Revisión recibida:** «cierre de revalidación de b240dc2», sin defectos nuevos. Recomienda pasar a la
prueba operativa de captura con `7fb0585`.
**Commits:** en la rama `claude/lucid-hamilton-hz8l80`:
- [`7a59d04`](https://github.com/hectorcs23/QuantileFlow/commit/7a59d04): registro de la ejecución de la
  captura a prueba de errores;
- [`bbbdc6e`](https://github.com/hectorcs23/QuantileFlow/commit/bbbdc6e): revisión de la operación de
  la captura por sesión;
- la documentación.

**Versión fijada:** sigue siendo `7fb0585`, como recomienda el cierre. Los dos commits nuevos quedan
propuestos hasta que se revisen; `REF_CODIGO` no se movió.
**Registro de verificación del commit propuesto:**
[`reports/verificacion/bbbdc6e95080.json`](../reports/verificacion/bbbdc6e95080.json). Árbol limpio,
202 pruebas pasadas.

> Acepto el cierre y sigo su plan. Para la prueba operativa hice dos cosas:
> - el registro de cada ejecución, que es la evidencia de puntualidad, ya no se pierde si algo falla
>   después de capturar;
> - un script resume la operación de cada sesión, para revisar los pasos 4 y 5 sin leer los registros
>   uno por uno.
>
> La prueba sigue sin poder empezar: el repositorio privado de datos no existe, o la app de GitHub de
> Claude no tiene acceso a él.

---

## 1. El repositorio privado

Lo comprobé hoy, porque el cierre no lo revalidó. La consulta de `hectorcs23/QuantileFlow-datos`
responde que no existe o que esta sesión no tiene acceso. Sin él, los workflows no corren y la prueba
de 3–5 sesiones no empieza. Pasos:

1. Crear el repositorio privado `QuantileFlow-datos`.
2. Agregarle los secretos de Actions `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY`.
3. Subir el contenido de `ops/repo_datos/`, ya fijado en `7fb0585`. Otra opción es instalar la app de
   GitHub de Claude en ese repositorio desde <https://claude.ai/connect-github> y lo subo yo.
4. Probar a mano **captura-0945** con «ahora» y **historico-alpaca**, y dejar correr las sesiones.

---

## 2. El registro de cada ejecución, a prueba de errores (`7a59d04`)

**Qué encontré.** En `capturar_alpaca.py`, la normalización del día corría después de capturar y
**antes** de escribir el registro de la ejecución, sin protección. Una excepción ahí terminaba el
proceso con la captura completa y su manifiesto, pero sin registro y en rojo en Actions. Lo reproduje
con el script real y el transporte falso: la captura quedó `completa` y no quedó ningún registro.

**Por qué importa ahora.** Ese registro es lo que mide la puntualidad en la prueba operativa:
- el arranque;
- cuándo quedó lista la captura;
- los plazos;
- el margen de la ráfaga.

**Qué lo podía disparar.** Con la configuración actual, que consulta solo SPY, un dividendo sin símbolo
atribuible no puede ocurrir, porque toma el de la consulta. Sí pueden hacerlo:
- un evento corporativo que no es un dividendo, el mismo día de la captura, porque la normalización
  del piloto se detiene ante él;
- un error al escribir el Parquet;
- un fallo inesperado en el nivel implícito.

**Qué cambió:**
- El resumen del día que escribe la captura ya no lee los eventos
  (`tablas_para_piloto(..., eventos=False)`). No los usa, y un evento que la normalización del piloto
  rechaza no tiene por qué tumbar la captura. La normalización del piloto, `normalizar_alpaca.py`, sigue
  deteniéndose como antes.
- Un error inesperado al preparar o al capturar deja el registro con el error y su etapa, y la hora
  queda `fallida` (código 1).
- Un error en la normalización del día deja el registro, con las horas como quedaron, y termina con el
  código 5 (`CODIGO_SIN_NORMALIZAR`) si todas estaban completas. El crudo y sus manifiestos ya estaban
  escritos.

**Prueba.** `test_cada_ejecucion_de_la_captura_deja_su_registro` es la primera prueba de punta a punta de
`main()` de la captura, con la API sintética. Recorre tres casos:
- un evento anómalo en el crudo;
- un fallo en la normalización del día;
- un fallo en la preparación.

Con el script anterior falla en el primero, porque la normalización del día se cae por el evento. Con
el nuevo, los tres dejan su registro.

---

## 3. Revisión de la operación (`bbbdc6e`)

Sirve para los pasos 4 y 5 del cierre:

```bash
python scripts/revisar_operacion.py --datos ../QuantileFlow-datos --desde 2026-09-28 --hasta 2026-10-02
```

Lee los registros de `ejecuciones/` y los manifiestos, y escribe `reports/operacion/<desde>_<hasta>/`
(`informe.md` y `resumen.json`). Solo agregados: estados, tiempos y conteos, nunca cotizaciones.

| Qué da | De dónde |
|---|---|
| Estado final de cada corte: `completa`, `parcial`, `fallida`, `perdida` (o `pendiente`) | La misma regla que usa la captura (`alpaca.planificar`) |
| Ejecuciones que lo planificaron, intentos de captura y el `cron` de la que capturó | Registros de captura. En la plantilla, el minuto 11 es el titular y el 26 el respaldo: se ve quién capturó sin suponerlo. |
| Retraso del arranque del script respecto de su `cron` | Incluye la preparación del workflow (checkout, instalación), no solo la cola de GitHub |
| Margen hasta el corte al quedar lista la captura y al empezar la ráfaga | `listo_utc` y el margen de cada hora |
| Plazo de preparación y plazo absoluto vencidos, errores y recuperaciones | Registros de captura y de recuperación |
| SIP del objetivo en cada corte | Manifiestos del histórico |
| Dividendos: versiones, discrepancias abiertas por tipo (también `incompleto`), retiros, contradicciones | `alpaca.resumen_dividendos`, con `resoluciones_dividendos.csv` si existe |

El código de salida es 1 si algún corte quedó `parcial`, `fallido` o `perdido`. La prueba
(`test_revision_de_la_operacion_de_las_sesiones`) arma dos sesiones:
- una sin incidencias, en la que el respaldo encuentra la hora completa y la omite;
- otra en la que el titular no queda listo a tiempo, se recupera su diario, el respaldo captura y un
  corte se pierde. También hay un dividendo recibido sin fecha ex.

---

## 4. El plan del cierre, paso a paso

| Paso | Estado |
|---|---|
| 1. Fijar la versión del piloto | `REF_CODIGO` en `7fb0585`. `7a59d04` y `bbbdc6e` se fijarán solo después de revisarse. `revisar_operacion.py` corre fuera de los workflows, así que no hace falta fijarlo para usarlo. |
| 2. Renormalizar desde el crudo | `normalizar_alpaca.py` sobre el crudo completo, sin mezclar tablas anteriores al cambio del contrato de dividendos |
| 3. Verificar la operación del repositorio privado | Pendiente de tu parte (sección 1) |
| 4. Observar 3–5 sesiones | `revisar_operacion.py`, después de cada sesión y al final |
| 5. Revisar la calidad | La sección de dividendos de la revisión y el resumen de cada normalización |
| 6. Seleccionar etiquetas con `politica="aceptada"` | Documentado. Con 60 días de política, ninguna etiqueta nueva estará aceptada al terminar la prueba: valida la operación, no la capacidad predictiva. |

No se tocaron el transporte, los regímenes ni la optimización.

---

## 5. Verificación

- 202 pruebas pasadas en `bbbdc6e`, con el árbol limpio.
- El diagnóstico real del 25 de septiembre, regenerado con `bbbdc6e`, sale idéntico byte a byte.
- La plantilla sintética y las tablas del piloto no cambian, porque la normalización del piloto lee los
  eventos como antes.
