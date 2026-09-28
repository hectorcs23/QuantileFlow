# QuantileFlow: instalación del repositorio de datos

**Fecha:** 28 de septiembre de 2026 (madrugada del lunes; el mercado abre a las 09:30 de Nueva York).
**Repositorio:** `hectorcs23/QuantileFlow-datos`, privado. Esta sesión lo lee con la app de GitHub de
Claude.
**Plantillas instaladas:** las de `ops/repo_datos/` en `e1a7832`. **Código de la captura:** `4ffde8a`
(`REF_CODIGO`).

> La instalación está hecha y la prueba manual salió bien: se cumplen los pasos 1 a 5 de «Instalación
> y aceptación» (`ops/repo_datos/README.md`). La hiciste tú, con Cowork, el domingo 27 por la noche.
> La verificación es mía, desde esta sesión y con acceso de lectura: no es independiente. La
> verificación independiente del mismo día llegó a lo mismo; ver la
> [respuesta a la verificación de la instalación](respuesta_verificacion_instalacion.md).
>
> Falta el paso 6, la aceptación con 3–5 sesiones programadas, que empieza hoy. El primer disparo
> está programado para las 09:11 de Nueva York, sin garantía de hora.

---

## 1. Qué se comprobó

| Comprobación | Resultado | Cómo |
|---|---|---|
| Repositorio | Privado, con rama predeterminada `main`. | API de GitHub |
| Plantillas | Los seis archivos son idénticos byte a byte a los de `e1a7832`: tienen el mismo blob de git. Se subieron en seis commits de `hectorcs23`, de 20:43 a 20:49 (Nueva York). | `git ls-files -s` frente a `git rev-parse e1a7832:ops/repo_datos/<ruta>` |
| `REF_CODIGO` | `4ffde8acda8c661b31d67e56dcde2dc0fb9c41f9` en `captura-hora.yml` y en `historico.yml`. | Los archivos |
| Workflows | Hay cuatro activos: `captura-0945`, `captura-1000`, `captura-hora` (reutilizable) e `historico-alpaca`. | API de Actions |
| Secretos | `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY` llegan enmascarados al paso de captura, y Alpaca los acepta: «cuenta paper». | Log de la ejecución |
| Permiso de escritura | El bot subió dos commits: `b68ac33` y `4161ecb`. | Historial |
| Captura inmediata (run `36364768552`) | En verde, en 46 s. Estado `completa`: 14 respuestas y 3 250 cotizaciones de 3 250 snapshots, sin errores. El registro dice `"commit": "4ffde8a…"` y `"cambios_sin_registrar": false`. Desfase del reloj local: +0.035 s (± 0.044). | `raw/alpaca/ejecuciones/2026-09-25/20260928T010810352511Z.json` |
| Histórico (run `36364888228`) | En verde, en 46 s. El SIP de SPY queda `completa` en los 10 cortes del 21 al 25 de septiembre, con 1 000 cotizaciones cada uno, y los eventos corporativos también quedan `completa`. Las capturas de esa semana figuran como `perdida`, porque todavía no había instalación. | `raw/alpaca/ejecuciones/2026-09-27/20260928T010959027511Z_historico.json` |
| Credenciales en el crudo | No hay ninguna. Revisé los 46 archivos, con los `.gz` descomprimidos, sin imprimir valores. No aparecen los valores de las claves de este entorno. Si en GitHub se pusieron otras claves, esa comparación no aplica y cuenta la segunda búsqueda. En ella, los nombres de las cabeceras de credenciales solo aparecen en el README y en los workflows. | Búsqueda local |
| Herramientas del proyecto, sobre una copia | `revisar_operacion.py` del 21 al 25 de septiembre da 10 cortes `perdida`, como se esperaba, el SIP completo en los 10 y ninguna incidencia. `normalizar_alpaca.py` con eventos termina con código 0: 3 250 cotizaciones, 10 001 filas de subyacente y 5 versiones de dividendos de 5 eventos, sin retiros ni discrepancias. | Local. Los informes no se versionan. |

## 2. Observaciones

1. **La captura inmediata repite la primera verificación real** ([fuente_alpaca.md](fuente_alpaca.md),
   sección 3). Salen las mismas 3 250 cotizaciones y el mismo precio de SPY en IEX. El nivel implícito tiene 0
   pares válidos con los controles estrictos, porque las cotizaciones llegaron después del corte. Fuera
   de sesión es lo esperado: la prueba acredita la instalación, no una captura válida al corte.
2. **El mensaje del commit de la prueba** dice «Captura de las 09:45 del 2026-09-27», porque la
   plantilla usa la hora del workflow y la fecha de la corrida. El registro y la etiqueta
   (`2026-09-25Tinmediata-010810`) son correctos. Es cosmético, y no lo cambio para no tocar las
   plantillas instaladas.
3. **GitHub avisa de que `actions/checkout@v4` y `actions/setup-python@v5` están hechos para
   Node.js 20** y de que los fuerza a correr en Node.js 24. Las corridas funcionan. Actualizarlos
   implica cambiar las plantillas y reinstalarlas, así que queda para el próximo cambio que haya en
   ellas. La verificación independiente señaló además que `ubuntu-latest` pasa a Ubuntu 26.04 desde
   el 19 de octubre. Los dos cambios irán en un mantenimiento con esa fecha límite
   ([respuesta a la verificación de la instalación](respuesta_verificacion_instalacion.md)).
4. **La prueba no se mezcla con los cortes.** Su registro queda en `ejecuciones/2026-09-25/`, y la
   revisión de la operación no la cuenta como captura de las 09:45 ni de las 10:00.

## 3. Estado de la aceptación

| Paso de «Instalación y aceptación» | Estado |
|---|---|
| 1. Crear el repositorio privado | Hecho |
| 2. Copiar la plantilla en la raíz de `main` | Hecho: idéntica a la de `e1a7832` |
| 3. Secretos | Hecho |
| 4. Permiso de escritura | Hecho |
| 5. Prueba manual | Hecho: las dos corridas en verde, con el commit `4ffde8a` y el crudo guardado |
| 6. Aceptación: revisar 3–5 sesiones con `revisar_operacion.py` | Pendiente; empieza el lunes 28 |

Disparos programados de hoy, en hora de Nueva York (EDT):
- 09:11 y 09:26 para las 09:45;
- 09:21 y 09:36 para las 10:00;
- 10:21 para el histórico.

GitHub puede retrasarlos o descartarlos con carga. Los registros de `ejecuciones/` dirán cuándo
arrancaron de verdad.

## 4. Alcance

**Qué prueba:** que la instalación funciona con la versión fijada. Autentica, descarga, guarda el
crudo sin credenciales y deja el registro con el commit usado.

**Qué no prueba:**
- que los disparos programados lleguen a tiempo al corte (lo mide la aceptación);
- nada sobre la capacidad predictiva.
