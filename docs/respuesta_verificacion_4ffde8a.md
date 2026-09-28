# QuantileFlow: respuesta a la verificación de `4ffde8a`

**Fecha:** 28 de septiembre de 2026.
**Revisión recibida:** «verificación del trabajo de Claude y Codex», sobre `56cad99` (código `4ffde8a`).
Cierra la revisión de los cambios operativos: la suite pasa en Windows en los dos modos y no hay
defectos nuevos. Recomienda adoptar `4ffde8a` en los workflows y acreditar el despliegue con datos
reales.
**Commit de esta respuesta:** la documentación y el cambio de `REF_CODIGO`; el código no cambia.

> Tomo el cierre y hago lo que recomienda:
> - **Fijé `4ffde8a`** en los dos workflows (`captura-hora.yml` e `historico.yml`), con su registro de
>   verificación y la plantilla sintética regenerada en ese commit.
> - **Corregí dos afirmaciones mías.** El repositorio de datos «no existe o esta conexión no tiene
>   acceso», no «no existe». Y las 09:11 son el horario programado del primer disparo, no una
>   garantía de arranque.
> - **Convertí la puesta en marcha** del repositorio de datos en una lista de instalación y aceptación.
>
> Sigue sin estar acreditado que la captura diaria esté desplegada y funcionando.

---

## 1. Versión fijada: `4ffde8a`

- `REF_CODIGO` pasa de `7fb0585` a `4ffde8acda8c661b31d67e56dcde2dc0fb9c41f9` en los dos workflows. Así
  las plantillas ejecutan las mejoras de registro revisadas:
  - el registro al iniciar;
  - el de la recuperación aparte;
  - el de la normalización del día.
- **Registro de verificación:**
  [`reports/verificacion/4ffde8acda8c.json`](../reports/verificacion/4ffde8acda8c.json), con el árbol
  limpio y 203 pruebas pasadas en Linux. La revisión confirmó por su lado 203 en Windows, en modo normal
  y con la codificación obligatoria.
- **Plantilla sintética regenerada en `4ffde8a`,** con el árbol limpio. Etiquetas, tabla diaria e
  informe son idénticos byte a byte a los de `7fb0585`. Solo cambia el manifiesto, que registra el
  commit.
- **El código se toma por commit,** así que no depende de la rama predeterminada del repositorio público
  (hoy `claude/compassionate-brown-1w9f90`). La rama `claude/lucid-hamilton-hz8l80`, que contiene
  `4ffde8a`, no debe borrarse mientras los workflows lo fijen.

## 2. Correcciones a lo que dije

- **Repositorio de datos.** Mi consulta a `hectorcs23/QuantileFlow-datos` responde «no se encontró, o
  la credencial de esta sesión no tiene acceso». GitHub responde igual en los dos casos, porque así
  oculta los repositorios privados. Lo correcto es «no existe o esta conexión no tiene acceso; pendiente
  de verificar», no «todavía no existe». Queda corregido en la respuesta anterior.
- **Horario.** Las 09:11 de Nueva York son el horario **programado** del primer disparo de las 09:45, no
  una garantía. GitHub puede retrasar los disparos programados o descartarlos con carga. Los registros de
  `ejecuciones/` medirán cuándo arrancaron de verdad.
- **Diagnóstico del 25 de septiembre.** La regeneración desde el crudo real es evidencia mía, no
  independiente. La revisión comprobó el `resumen.json` versionado, no su regeneración.

## 3. Qué falta para considerar operativa la captura

Es la secuencia de aceptación de la revisión. Queda en `ops/repo_datos/README.md`, «Instalación y
aceptación»:

| Paso | Quién | Estado |
|---|---|---|
| 1. Fijar el commit revisado | Claude | Hecho: `4ffde8a` |
| 2. Resolver la existencia o el acceso a `QuantileFlow-datos` (privado, con acceso para quien lo revise) | Tú | Pendiente |
| 3. Instalar: `ops/repo_datos/` en la raíz de la rama predeterminada, secretos de Alpaca y permiso de escritura para `GITHUB_TOKEN` | Tú (o Claude, con la app de GitHub instalada en el repositorio) | Pendiente |
| 4. Prueba manual de captura inmediata e histórico: el commit usado en el registro y el crudo guardado en el repositorio | Tú o Claude | Pendiente |
| 5. Revisar 3–5 sesiones en ambos horarios: puntualidad, completitud, respaldo, recuperación, SIP y dividendos (`revisar_operacion.py`, y no solo su código de salida) | Claude, con acceso de lectura | Pendiente |

**Actualización del 28 de septiembre:** los pasos 2 a 4 quedaron hechos y verificados. Ver
[instalación del repositorio de datos](instalacion_repo_datos.md).

## 4. Alcance

Coincido con la sección 6 de la revisión:
- **Qué prueba este trabajo:** el comportamiento del código en los escenarios verificados.
- **Qué no prueba todavía:** que los residuos de paridad, el RR25 o las asimetrías call/put pronostiquen
  SPY con utilidad económica. La prueba operativa tampoco lo validará: con la política de 60 días, las
  etiquetas nuevas no estarán aceptadas al terminarla.
- **Qué falta para dar recomendaciones de posición:**
  - una muestra real suficiente;
  - la calidad del feed (OPRA);
  - la validación fuera de muestra.

No se tocaron el transporte, los regímenes, la optimización ni el análisis de volumen.
