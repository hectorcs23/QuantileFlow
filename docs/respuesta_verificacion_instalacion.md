# QuantileFlow: respuesta a la verificación independiente de la instalación

**Fecha:** 28 de septiembre de 2026.
**Revisión recibida:** «verificación independiente de la instalación», sobre el informe de instalación
(`5eb9506`).
**Commit de esta respuesta:** solo documentación. No cambian el código, las plantillas ni el repositorio
de datos.

> Tomo el dictamen. La instalación y la prueba manual quedan acreditadas en lo verificado, y no hay
> defectos que bloqueen la prueba programada. Sigue pendiente la aceptación de 3–5 sesiones, que
> empieza hoy.
>
> Hago dos cosas:
> - **Registro el cambio de entorno con fecha límite.** GitHub pasa `ubuntu-latest` a Ubuntu 26.04 de
>   forma gradual entre el 19 de octubre y el 19 de noviembre, en medio del piloto. Propongo fijar
>   `ubuntu-24.04` antes del 19 de octubre, junto con las acciones para Node.js 24. Irá en un solo
>   mantenimiento, después de la semana de aceptación.
> - **Anoto cómo correr el diagnóstico gráfico** en un entorno sin interfaz gráfica utilizable. El
>   código no cambia: el problema era del entorno local, como dice la revisión.

---

## 1. Coincidencias

Las dos verificaciones llegan a lo mismo por caminos distintos: yo, con el clon de git y la API de
GitHub; la revisión, con una descarga ZIP desde el navegador.

| Punto | Mi verificación | La revisión |
|---|---|---|
| Repositorio | Privado, con `main` | Privado, con `main` en la raíz |
| Plantillas | Blobs iguales a los de `e1a7832` | Iguales byte a byte y en blob |
| `REF_CODIGO` y registros | `4ffde8a` y `cambios_sin_registrar: false` | Igual |
| Corridas manuales | En verde, 46 s cada una | En verde, 46 s cada una; el histórico corrió sobre `b68ac33` |
| Normalización con eventos | Código 0: 3 250 cotizaciones, 10 001 filas de subyacente y 5 versiones de 5 dividendos | Igual, con una consulta de cobertura |
| Revisión de la operación | Código 1, el esperado: 10 cortes `perdida` y SIP completo | Igual |
| Elegibilidad de la prueba | 0 pares válidos para el nivel implícito | `verificar_alpaca.py`: 0 de 3 250 filas válidas al corte |
| Credenciales | Ninguna coincidencia con las claves de este entorno ni nombres de cabeceras en `raw/` | Ningún nombre en `raw/` ni coincidencias con el patrón del identificador |

**Coincido con el límite que marca la revisión sobre las credenciales.** Mi comparación usó las claves de
este entorno, que pueden no ser las de GitHub. Ninguna de las dos búsquedas prueba la ausencia de
cualquier secreto posible, solo que no hay indicios.

## 2. Entorno de los runners

**Qué dicen los logs.**
- La captura pidió `ubuntu-latest` y recibió la imagen `ubuntu-24.04`, versión `20260920.314`.
- Las dos corridas avisan de que `actions/checkout@v4` y `actions/setup-python@v5` se fuerzan a
  Node.js 24.
- El aviso de la migración no está en el texto del log del job. La revisión lo vio en la página de la
  corrida.

**Lo confirma el changelog de GitHub del 17 de septiembre**
([Ubuntu 26 generally available and latest migration](https://github.blog/changelog/2026-09-17-ubuntu-26-generally-available-and-latest-migration/)):
- `ubuntu-latest` pasa de Ubuntu 24.04 a 26.04 de forma gradual entre el 19 de octubre y el 19 de
  noviembre;
- la imagen nueva actualiza, y en algunos casos quita, herramientas y versiones;
- GitHub recomienda fijar `ubuntu-24.04` a quien no esté listo para el cambio.

**Por qué importa aquí.**
- **La ventana cae dentro del piloto.** Antes del 19 de octubre caben 15 sesiones. La sesión 20 es el
  23 de octubre y la 40, el 20 de noviembre.
- **No decidiríamos qué imagen usa cada corrida.** Al ser gradual, unas corridas usarían 24.04 y otras
  26.04. Los registros de ejecución no guardan la imagen. Solo la guardan los logs, que GitHub borra
  al vencer su plazo de retención (90 días por omisión).
- **Un fallo en la imagen nueva cuesta cortes.** Si `setup-python` o las dependencias fallan ahí, esos
  cortes se pierden.

**Propuesta: un solo mantenimiento de las plantillas.**
1. `runs-on: ubuntu-24.04` en `captura-hora.yml` y en `historico.yml`. Es la misma imagen que se usa hoy,
   así que no cambia el comportamiento.
2. `actions/checkout` y `actions/setup-python` en versiones hechas para Node.js 24.
3. Lo que salga de la semana de aceptación y también toque las plantillas.

**Calendario.**
- Prepararlo y revisarlo después de la semana de aceptación (28 de septiembre a 2 de octubre).
- Instalarlo un fin de semana y probarlo con una corrida manual.
- Fecha límite: antes del primer disparo del lunes 19 de octubre.

La instalación cambia dos archivos del repositorio de datos, con la misma comprobación por hashes que
la primera. No lo cambio ahora porque la semana de aceptación debe correr sobre la instalación
verificada.

## 3. Diagnóstico gráfico en un entorno local

Coincido con la revisión: fue una limitación del entorno local, no del workflow. Las figuras solo se
escriben en archivos, así que basta un backend no interactivo. Lo anoto en
[fuente_alpaca.md](fuente_alpaca.md), en «Cómo operar»:
- usar `MPLBACKEND=Agg`;
- si matplotlib no puede crear su caché, apuntar `MPLCONFIGDIR` a una carpeta escribible.

## 4. Acceso para las próximas revisiones

El conector de GitHub de la revisión sigue recibiendo 404 porque no tiene acceso al repositorio privado.
Hay dos formas de seguir:
- el dueño le da acceso a `QuantileFlow-datos`, igual que se hizo con la app de Claude;
- se descarga el ZIP, como en esta revisión.

En los dos casos, los datos no deben salir a sitios públicos.

## 5. Próxima aceptación

Coincido con los cuatro puntos de la revisión. Hoy es la primera sesión programada.
- Revisaré los dos cortes después del histórico, que como tarde arranca a las 11:15 de Nueva York. Uso
  `revisar_operacion.py` y el diagnóstico de elegibilidad con `verificar_alpaca.py --fecha 2026-09-28`.
- Los informes que se versionen tendrán solo agregados.

## 6. Alcance

Esta respuesta no cambia código ni plantillas.
- **Lo acreditado sigue siendo** la instalación y la prueba manual.
- **Desde hoy se miden** la puntualidad en los cortes y la elegibilidad de las capturas programadas.
- **Nada de esto dice todavía** algo sobre la capacidad predictiva.
