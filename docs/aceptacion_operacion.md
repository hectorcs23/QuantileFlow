# QuantileFlow: aceptación de la operación

**Periodo previsto:** de 3 a 5 sesiones. Empezó el 28 de septiembre de 2026; las cuatro primeras sesiones se
perdieron, y la aceptación se reinició el 2 de octubre con las capturas lanzadas por Claude (sección 5).
**Repositorio de datos:** `hectorcs23/QuantileFlow-datos`, privado. **Código de la captura:** `4ffde8a`.
**Herramienta:** `scripts/revisar_operacion.py`. Solo se publican agregados: estados, tiempos y conteos,
nunca cotizaciones.

**Criterio**, según la verificación independiente de la instalación. En los dos cortes se revisan:
- estado, retraso del arranque, preparación, margen de la ráfaga y respuestas tardías;
- el respaldo, cuando actúe;
- el SIP y los dividendos, no solo el código de salida;
- que las capturas sean elegibles para el piloto y que cada registro conserve el commit fijado.

## Resumen por sesión

| Sesión | 09:45 | 10:00 | SIP del objetivo | Cómo se lanzó | Observaciones |
|---|---|---|---|---|---|
| Lunes 28 de septiembre | `perdida` | `perdida` | Sin descargar | No se lanzó a tiempo: los cron llegaron unas 6–7 horas tarde | Secciones 1 y 2 |
| Martes 29 de septiembre | `perdida` | `perdida` | Sin descargar | No se lanzó: a las 11:32 de Nueva York no había corridas programadas ni manuales | Sección 2 |
| Miércoles 30 de septiembre | `perdida` | `perdida` | Sin descargar | No se lanzó: a las 11:31 de Nueva York no había corridas programadas ni manuales | Sección 3 |
| Jueves 1 de octubre | `perdida` | `perdida` | Sin descargar | No se lanzó: a las 11:31 de Nueva York no había corridas programadas ni manuales | Sección 4 |
| Viernes 2 de octubre | `completa` | `completa` | Completo en los 2 cortes | Claude, a las 09:16 de Nueva York (`workflow_dispatch`) | Sección 6. Elegibles con controles estrictos |
| Lunes 5 de octubre | `completa` | `completa` | Completo en los 2 cortes | Claude, a las 09:16 de Nueva York (`workflow_dispatch`) | Sección 7. Elegibles con controles estrictos |
| Martes 6 de octubre | `completa` | `completa` | Completo en los 2 cortes | Claude, a las 09:16 de Nueva York (`workflow_dispatch`) | Sección 8. Elegibles con controles estrictos |
| Miércoles 7 de octubre | `completa` | `completa` | Completo en los 2 cortes | Claude, a las 09:16 de Nueva York (`workflow_dispatch`) | Sección 9. Elegibles con controles estrictos |

---

## 1. Lunes 28 de septiembre: GitHub no disparó los workflows programados

**Qué pasó.**
- **Ningún cron del día generó una corrida.** No corrieron:
  - `captura-0945` (09:11 y 09:26 de Nueva York);
  - `captura-1000` (09:21 y 09:36);
  - `historico-alpaca` (10:21).
- **La API de Actions solo lista las dos corridas manuales del domingo.**
- **Los workflows están bien.** Los cuatro están activos, en `main`, y son idénticos a los revisados. Las
  corridas manuales funcionaron. La página de estado de GitHub no informó incidentes ese día.
- **`revisar_operacion.py` del 28** da:
  - 2 cortes `perdida` y 0 ejecuciones;
  - SIP `sin descargar`;
  - dividendos sin cambios: 5 versiones y ninguna discrepancia.

**Qué se perdió.** Las cotizaciones de opciones de las 09:45 y las 10:00, que no se recuperan porque Alpaca
no guarda su historia. El SIP de SPY de esos cortes sí se puede descargar: lo hará la próxima corrida del
histórico, que completa lo que falte de la última semana.

**Causa probable.** Es un problema conocido de GitHub con repositorios privados nuevos: los cron no se
disparan durante las primeras horas o días, aunque las corridas manuales funcionen. Hay reportes de julio y
agosto de 2026 en la comunidad de GitHub, con esperas de 12 a 48 horas y sin una solución oficial:
[#201436](https://github.com/orgs/community/discussions/201436) y
[#203822](https://github.com/orgs/community/discussions/203822). No es un fallo del código, porque no llegó a
correr nada.

**Qué se hace.**
1. **Red de seguridad hasta confirmar que GitHub dispara solo.**
   - Lanzar a mano `captura-0945` y `captura-1000`, sin marcar «ahora», entre las 09:15 y las 09:35 de Nueva
     York. No antes de las 09:10: el job tiene un límite de 60 minutos, y la de las 10:00 esperaría
     demasiado.
   - Lanzar `historico-alpaca` después de las 10:20.
   - Es seguro: una corrida manual pasa la compuerta y el script espera hasta el corte. Si después llega
     también la programada, espera a que termine la manual y no repite lo ya capturado.
   - Mientras las corridas sean manuales, la aceptación no mide la puntualidad de los disparos
     programados.
2. **Comprobación el martes a las 09:16 de Nueva York.** Si no hay corrida de `captura-0945`, Claude avisa al
   usuario para que la lance. A las 11:30 se revisa la sesión completa.
3. **Si los cron siguen sin dispararse el miércoles:**
   - abrir un caso en el soporte de GitHub;
   - forzar que GitHub vuelva a registrar el cron, cambiando su sintaxis sin cambiar el horario (por ejemplo,
     `1-5` por `MON-FRI`), dentro del mantenimiento de las plantillas;
   - o usar un disparador externo: un servicio de cron que llame a la API de GitHub con un token limitado a
     ese repositorio, o Claude con permiso de escritura en el repositorio y la aprobación del usuario.

## 2. Martes 29 de septiembre: los cron llegan horas tarde

**Qué pasó el lunes, visto el martes.** GitHub sí lanzó los diez disparos programados del lunes, pero entre
las 16:06 y las 17:15 de Nueva York: unas 6 a 7 horas después de sus horarios. La compuerta los descartó a
todos, como debe hacer fuera de la ventana, y no guardaron nada. Esos disparos descartados no dejan registro
en el repositorio de datos, así que `revisar_operacion.py` no los ve. Su retraso solo consta en la API de
Actions.

**El martes.** A las 11:32 de Nueva York no había ninguna corrida del día, ni programada ni manual. El aviso
de las 09:18 para lanzarlas a mano no tuvo respuesta. `revisar_operacion.py` del 28 al 29 da:
- 4 cortes `perdida` y 0 ejecuciones;
- SIP `sin descargar` en los 4 cortes.

El SIP de los dos días se puede descargar hasta una semana después, con una corrida de `historico-alpaca`
dentro de su horario o lanzada a mano.

**Conclusión.** Con los cron de GitHub así, la captura no llega al corte. La red de seguridad manual depende
de que alguien esté disponible cada mañana, y el martes no funcionó.

**Propuesta: un disparador externo puntual**, pendiente de la decisión del usuario.
- Un servicio de cron, como cron-job.org, llama a la API de GitHub (`workflow_dispatch`) de lunes a viernes,
  en hora de Nueva York:
  - `captura-0945` a las 09:25, con un respaldo a las 09:33;
  - `captura-1000` a las 09:40, con un respaldo a las 09:48;
  - `historico-alpaca` a las 10:25.
- **Token.** Usa un token de GitHub *fine-grained*, limitado a `QuantileFlow-datos` y con un solo permiso,
  `Actions: Read and write`. Lo pega el usuario; nunca pasa por el chat.
- **Por qué es seguro.**
  - Una corrida manual pasa la compuerta y el script espera hasta el corte.
  - El respaldo espera a la primera por la concurrencia y no repite lo capturado.
  - Los cron de GitHub quedan como respaldo: si llegan tarde, la compuerta los descarta.
- **Minutos de Actions.** Al lanzar cerca del corte, cada job espera unos 20 minutos en lugar de 35–48.
  Contando los respaldos y los disparos tardíos de GitHub que la compuerta descarta (cerca de un minuto cada
  uno), la sesión gasta unos 45–60 minutos. El mes queda en unos 1 200 como mucho, por debajo del límite
  gratuito de 2 000.
- **Alternativa.** Que las lance Claude con tareas programadas. Requiere dar a la app de GitHub de Claude
  permiso de escritura en el repositorio y la aprobación expresa del usuario.

**Para el mantenimiento de las plantillas** (antes del 19 de octubre):
- que la compuerta deje un registro también cuando descarta un disparo, para medir los retrasos de GitHub
  desde el repositorio de datos;
- que el histórico acepte disparos tardíos del mismo día, porque el SIP es histórico y sigue disponible;
- fijar `ubuntu-24.04` y actualizar las acciones a Node.js 24.

## 3. Miércoles 30 de septiembre: sigue igual

- **Los cron del martes** llegaron entre las 14:37 y las 16:01 de Nueva York, unas 5 horas y media tarde. La
  compuerta los descartó.
- **El miércoles** no había ninguna corrida a las 11:31 de Nueva York, ni programada ni manual. El aviso de
  las 09:18 no tuvo respuesta.
- **`revisar_operacion.py` del 28 al 30** da 6 cortes `perdida`, 0 ejecuciones y el SIP `sin descargar` en
  los 6.

Van tres sesiones perdidas de las cinco previstas para la aceptación. La operación no puede aceptarse
mientras dependa de los cron de GitHub. La decisión pendiente sigue siendo el disparador externo de la
sección 2.

## 4. Jueves 1 de octubre: cuarta sesión perdida

- **Los cron del miércoles** llegaron entre las 14:26 y las 16:04 de Nueva York, unas 5 horas tarde. La
  compuerta los descartó.
- **El jueves** no había ninguna corrida a las 11:31 de Nueva York, ni programada ni manual.
- **`revisar_operacion.py` del 28 de septiembre al 1 de octubre** da 8 cortes `perdida`, 0 ejecuciones y el
  SIP `sin descargar` en los 8.

| Día de los cron | Hora programada del primer disparo | Llegada de las corridas (Nueva York) | Retraso aproximado |
|---|---|---|---|
| Lunes 28 | 09:11 | 16:06–17:15 | 6–7 h |
| Martes 29 | 09:11 | 14:37–16:01 | 5 h 30 min |
| Miércoles 30 | 09:11 | 14:26–16:04 | 5 h 15 min |
| Jueves 1 | 09:11 | 14:51–16:21 (visto el viernes) | 5 h 40 min |
| Viernes 2 | 09:11 | 14:22–15:58 (visto el lunes) | 5 h 10 min |
| Lunes 5 | 09:11 | 17:05–18:02 (visto el martes) | 7 h 55 min |
| Martes 6 | 09:11 | 14:53–16:21 (visto el miércoles) | 5 h 40 min |

El retraso baja poco a poco, pero ningún día llegó a menos de cinco horas. La decisión pendiente sigue
siendo el disparador externo de la sección 2.

## 5. Decisión del 1 de octubre: Claude lanza la captura cada mañana

El usuario eligió que Claude lance los workflows con tareas programadas, en lugar del despertador externo.
Claude ya tenía acceso al repositorio de datos con la app de GitHub. La primera prueba funcionó: a las 11:40
de Nueva York del jueves 1 lanzó `historico-alpaca`, para bajar el SIP de lunes a jueves.

**Calendario, de lunes a viernes, en hora de Nueva York:**

| Hora | Qué hace Claude |
|---|---|
| 09:14 | Lanza `captura-0945` y `captura-1000` y comprueba que quedaron en cola. Si falla, reintenta una vez y, si no, avisa al usuario para que las lance a mano. |
| 09:32 | Desde el miércoles 7 de octubre (sección 8): comprueba que las dos corridas tienen máquina. Si alguna sigue en cola sin máquina, terminó sin éxito o no existe, la relanza una vez, cancelando antes la atascada. Avisa al usuario si no puede relanzarla o si el script falló. |
| 10:27 | Lanza `historico-alpaca` y revisa las capturas del día: `revisar_operacion.py` y, si están completas, la elegibilidad con `verificar_alpaca.py`. Actualiza este documento y avisa solo si algo falló. |

- **Margen.** Una corrida lanzada a las 09:14 espera hasta el corte. La preparación tiene que estar lista 6
  minutos antes, y el job tiene un límite de 60 minutos; las dos condiciones se cumplen con margen.
- **Los cron de GitHub siguen activos como respaldo.** Si llegan tarde, la compuerta los descarta. Si alguna
  vez llegan a tiempo, esperan a la corrida en curso y no repiten lo ya capturado.
- **Minutos de Actions.** Al lanzar a las 09:14, las capturas esperan unos 30 y 45 minutos. Con los disparos
  tardíos descartados, la sesión gasta unos 80 minutos: unos 1 650 al mes, por debajo del límite gratuito de
  2 000 para repositorios privados. Si hiciera falta bajar el gasto, se puede lanzar `captura-1000` más
  tarde.
- **La aceptación empieza de nuevo** el viernes 2 de octubre, con 3 a 5 sesiones lanzadas así.

## 6. Viernes 2 de octubre: primera sesión completa

**Cómo se lanzó.** Claude lanzó `captura-0945` y `captura-1000` a las 09:16 de Nueva York y
`historico-alpaca` a las 10:28, todas con `workflow_dispatch`. Las tres corridas terminaron con éxito:

| Workflow | Corrida (Nueva York) | Duración |
|---|---|---|
| `captura-0945` | 09:16–09:45 | 29 min |
| `captura-1000` | 09:16–10:00 | 44 min |
| `historico-alpaca` | 10:28 | 46 s |

**`revisar_operacion.py` del 2**, después del histórico:
- **Estado:** 2 cortes `completa`, con 1 ejecución y 1 intento cada uno. No hubo errores ni recuperaciones.
- **Puntualidad:**
  - la preparación quedó lista 1 699 s antes del corte de las 09:45 y 2 600 s antes del de las 10:00;
  - la ráfaga empezó 5.0 s antes del corte en los dos;
  - no llegó ninguna respuesta después del corte.
- **Retraso respecto del cron:** no aplica, porque las corridas se lanzaron a mano.
- **SIP del objetivo:** completo en los 2 cortes.
- **Dividendos:** 5 versiones de 5 eventos, sin discrepancias.

**Elegibilidad** (`verificar_alpaca.py`, sobre una copia de los datos):
- **Las dos capturas son elegibles** con los controles estrictos: 3 528 filas válidas de 3 808 a las 09:45 y
  3 532 de 3 808 a las 10:00.
- **Cobertura:** los 3 808 contratos tienen cotización y metadatos.
- **Solicitudes:** cada captura recibió 10 respuestas, con 1.8 MB en total, en 0.88 y 0.80 s, sin errores.
- **Medidas:**
  - el nivel implícito de SPX quedó identificado, con 115 y 111 pares del vencimiento del día;
  - la RR25 a 30 días quedó identificada en SPXW y en SPY, en los dos cortes.
- **Feed:** de opciones `indicative`, con cuenta paper.
  - El desfase del reloj fue de 0.09 s.
  - Entre el 8 y el 15 % de los precios de SPXW caen en la grilla de ticks, como en la primera
    verificación, la del cierre del 25 de septiembre. Es lo esperable de ese feed (`docs/fuente_alpaca.md`).
- **Commit fijado:** las capturas y sus registros conservan `4ffde8a`.

**Observaciones.**
- **Los cron del jueves** llegaron entre las 14:51 y las 16:21 de Nueva York, unas 5 horas y 40 minutos tarde.
  La compuerta los descartó. Los del viernes aún no habían llegado a las 10:28.
- **Nombre de los manifiestos del histórico.** Los de hoy se llaman `2026-10-02T0945-2.json` y
  `2026-10-02T1000-2.json`.
  - La causa: `etiqueta_libre` también comprueba el diario de la captura en vivo, que tiene el mismo nombre
    base, y por eso pasa al número siguiente.
  - Solo afecta al nombre: la revisión lee los manifiestos por carpeta.
  - Se puede corregir en el mantenimiento de las plantillas, junto con el nuevo commit fijado.

**Cuenta:** 1 sesión completa de las 3 a 5 que pide la aceptación. Es también la primera sesión real a las
09:45 que sirve para decidir entre `indicative` y OPRA.

## 7. Lunes 5 de octubre: segunda sesión completa

**Cómo se lanzó.** Igual que el viernes: Claude lanzó `captura-0945` y `captura-1000` a las 09:16 de Nueva
York y `historico-alpaca` a las 10:28. Las tres corridas terminaron con éxito:

| Workflow | Corrida (Nueva York) | Duración |
|---|---|---|
| `captura-0945` | 09:16–09:45 | 29 min |
| `captura-1000` | 09:16–10:00 | 44 min |
| `historico-alpaca` | 10:28 | 37 s |

**`revisar_operacion.py` del 2 al 5 de octubre**, después del histórico:
- **Estado:** los 4 cortes de las dos sesiones están `completa`, con 1 ejecución y 1 intento cada uno. No
  hubo errores ni recuperaciones.
- **Puntualidad del lunes:**
  - la preparación quedó lista 1 696 s antes del corte de las 09:45 y 2 596 s antes del de las 10:00;
  - la ráfaga empezó 5.0 s antes del corte en los dos;
  - no llegó ninguna respuesta después del corte.
- **SIP del objetivo:** completo en los 4 cortes.
- **Dividendos:** 5 versiones de 5 eventos, sin discrepancias. Las 2 consultas de eventos del histórico
  quedaron completas.

**Elegibilidad del lunes** (`verificar_alpaca.py`, sobre una copia de los datos):
- **Las dos capturas son elegibles** con los controles estrictos: 2 716 filas válidas de 2 948 a las 09:45 y
  2 717 de 2 948 a las 10:00.
- **Cobertura:** los 2 948 contratos tienen cotización y metadatos.
- **Solicitudes:** cada captura recibió 10 respuestas, con 1.4 MB en total, en 0.45 y 0.59 s, sin errores.
- **Medidas:**
  - el nivel implícito de SPX quedó identificado, con 94 y 96 pares del vencimiento del día;
  - la RR25 a 30 días quedó identificada en SPXW y en SPY, en los dos cortes.
- **Feed:** de opciones `indicative`, con cuenta paper.
  - El desfase del reloj fue de 0.04 y 0.06 s.
  - Entre el 11 y el 17 % de los precios de SPXW caen en la grilla de ticks, como el viernes.
- **Commit fijado:** las capturas, el histórico y sus registros conservan `4ffde8a`.

**Observaciones.**
- **Menos contratos que el viernes** (2 948 frente a 3 808). Es por diseño: la captura pide los vencimientos
  que rodean los 30 días.
  - El viernes, uno de ellos era el de fin de mes de SPXW, el 30 de octubre, con 974 filas.
  - El lunes, los cuatro vencimientos de SPXW cercanos a 30 días tienen unas 240 filas cada uno.
- **Los cron del viernes** llegaron entre las 14:22 y las 15:58 de Nueva York, unas 5 horas y 10 minutos
  tarde. La compuerta los descartó. Los del lunes aún no habían llegado a las 10:28.
- **Los manifiestos del histórico** vuelven a llevar el sufijo `-2`, como se explica en la sección 6.

**Cuenta:** 2 sesiones completas de las 3 a 5 que pide la aceptación.

## 8. Martes 6 de octubre: tercera sesión completa

**Cómo se lanzó.** Igual que los días anteriores: Claude lanzó `captura-0945` y `captura-1000` a las 09:16
de Nueva York y `historico-alpaca` a las 10:28. Las tres corridas terminaron con éxito:

| Workflow | Corrida (Nueva York) | Duración |
|---|---|---|
| `captura-0945` | 09:16–09:45 | 28 min |
| `captura-1000` | 09:16–10:00 | 43 min |
| `historico-alpaca` | 10:28 | 43 s |

**`revisar_operacion.py` del 2 al 6 de octubre**, después del histórico:
- **Estado:** los 6 cortes de las tres sesiones están `completa`, con 1 ejecución y 1 intento cada uno. No
  hubo errores ni recuperaciones.
- **Puntualidad del martes:**
  - la preparación quedó lista 1 658 s antes del corte de las 09:45 y 2 550 s antes del de las 10:00;
  - la ráfaga empezó 5.0 s antes del corte en los dos;
  - no llegó ninguna respuesta después del corte.
- **SIP del objetivo:** completo en los 6 cortes.
- **Dividendos:** 5 versiones de 5 eventos, sin discrepancias. Las 3 consultas de eventos del histórico
  quedaron completas.

**Elegibilidad del martes** (`verificar_alpaca.py`, sobre una copia de los datos):
- **Las dos capturas son elegibles** con los controles estrictos: 2 750 filas válidas de 3 188 a las 09:45 y
  2 834 de 3 188 a las 10:00.
- **Cobertura:** los 3 188 contratos tienen cotización y metadatos.
- **Solicitudes:** cada captura recibió 10 respuestas, con 1.5 MB en total, en 0.39 y 0.56 s, sin errores.
- **Medidas:**
  - el nivel implícito de SPX quedó identificado, con 86 y 94 pares del vencimiento del día;
  - la RR25 a 30 días quedó identificada en SPXW y en SPY, en los dos cortes.
- **Feed:** de opciones `indicative`, con cuenta paper.
  - El desfase del reloj fue de 0.04 y 0.05 s.
  - Entre el 9 y el 15 % de los precios de SPXW caen en la grilla de ticks, como los días anteriores.
- **Commit fijado:** las capturas, el histórico y sus registros conservan `4ffde8a`.

**Observaciones.**
- **Más cotizaciones desfasadas en SPXW.** Se excluyeron 267 a las 09:45 y 232 a las 10:00, frente a 24 y 20
  el lunes.
  - Se concentran en el vencimiento del día: su edad mediana fue de 12 y 17 s, frente a 5 y 6 s el lunes.
  - A las 09:45 también en el del 4 de noviembre, con 16 s.
  - Las capturas siguen siendo elegibles. Es un dato más para decidir entre `indicative` y OPRA.
- **Los cron del lunes** llegaron entre las 17:05 y las 18:02 de Nueva York, unas 7 horas y 55 minutos tarde.
  - GitHub tardó entre 1 y 15 minutos en asignarles máquina.
  - Una corrida de `captura-0945`, la de las 17:05, nunca consiguió máquina. GitHub la canceló a los 15
    minutos con el aviso «The job was not acquired by Runner of type hosted even after multiple attempts»,
    y la marcó como fallida. No llegó a correr ningún paso.
  - La compuerta descartó las demás. No se escribió nada en el repositorio de datos.
- **Riesgo que muestra ese fallo.** Si le pasara a la corrida de las 09:16, la captura podría perderse: la
  comprobación de las 09:14 solo confirma que la corrida quedó en cola.
  - **Aprobado el 6 de octubre:** desde el miércoles 7 hay una segunda comprobación a las 09:32 de Nueva York
    (sección 5). Si alguna corrida sigue sin máquina, se cancela y se vuelve a lanzar.
  - Es seguro por la concurrencia: la nueva espera a la anterior y no repite lo ya capturado.
  - A esa hora GitHub ya habría cancelado la corrida atascada, si tarda los mismos 15 minutos. La nueva
    tendría tiempo de quedar lista antes del límite de las 09:39: desde que se lanza, la preparación tarda
    menos de un minuto.
- **Los manifiestos del histórico** vuelven a llevar el sufijo `-2`, como se explica en la sección 6.

**Cuenta:** 3 sesiones completas: se alcanza el mínimo de la aceptación, que pide de 3 a 5.
- **Aprobado el 6 de octubre:** se sigue el miércoles 7 y el jueves 8 para llegar a 5. La aceptación se
  cierra el jueves a las 10:50 de Nueva York, después de la revisión del día, con un resumen y un veredicto.
- Cuesta poco, porque las capturas ya se lanzan solas. Además, las variaciones del feed y de GitHub de esta
  semana justifican mirar dos sesiones más.

## 9. Miércoles 7 de octubre: cuarta sesión completa

**Cómo se lanzó.** Igual que los días anteriores: Claude lanzó `captura-0945` y `captura-1000` a las 09:16
de Nueva York y `historico-alpaca` a las 10:28. Las tres corridas terminaron con éxito:

| Workflow | Corrida (Nueva York) | Duración |
|---|---|---|
| `captura-0945` | 09:16–09:45 | 29 min |
| `captura-1000` | 09:16–10:00 | 44 min |
| `historico-alpaca` | 10:28 | 44 s |

**Primera comprobación de las 09:32.** Las dos corridas tenían máquina y estaban en el paso «Capturar»,
esperando su corte. No hizo falta relanzar nada.

**`revisar_operacion.py` del 2 al 7 de octubre**, después del histórico:
- **Estado:** los 8 cortes de las cuatro sesiones están `completa`, con 1 ejecución y 1 intento cada uno.
  No hubo errores ni recuperaciones.
- **Puntualidad del miércoles:**
  - la preparación quedó lista 1 703 s antes del corte de las 09:45 y 2 591 s antes del de las 10:00;
  - la ráfaga empezó 5.0 s antes del corte en los dos;
  - no llegó ninguna respuesta después del corte.
- **SIP del objetivo:** completo en los 8 cortes.
- **Dividendos:** 5 versiones de 5 eventos, sin discrepancias. Las 4 consultas de eventos del histórico
  quedaron completas.

**Elegibilidad del miércoles** (`verificar_alpaca.py`, sobre una copia de los datos):
- **Las dos capturas son elegibles** con los controles estrictos: 2 981 filas válidas de 3 242 a las 09:45 y
  2 875 de 3 242 a las 10:00.
- **Cobertura:** los 3 242 contratos tienen cotización y metadatos.
- **Solicitudes:** cada captura recibió 10 respuestas, con 1.5 MB en total, en 0.47 y 0.73 s, sin errores.
- **Medidas:**
  - el nivel implícito de SPX quedó identificado, con 107 y 103 pares del vencimiento del día;
  - la RR25 a 30 días quedó identificada en SPXW y en SPY, en los dos cortes.
- **Feed:** de opciones `indicative`, con cuenta paper.
  - El desfase del reloj fue de 0.09 y 0.08 s.
  - Entre el 11 y el 18 % de los precios de SPXW caen en la grilla de ticks, como los días anteriores.
- **Commit fijado:** las capturas, el histórico y sus registros conservan `4ffde8a`.

**Observaciones.**
- **Cotizaciones desfasadas en SPXW.** A las 09:45 volvieron a lo normal: se excluyeron 63. A las 10:00 se
  excluyeron 215, con una edad mediana de 10 a 12 s en todos los vencimientos de SPXW (de 6 a 7 s a las
  09:45).
  - El martes y el miércoles, la frescura del feed `indicative` cambió de un corte a otro.
  - Las capturas siguen siendo elegibles.
- **Error del forward a las 09:45.** Fue de 0.98 puntos, frente a 0.13–0.38 en los demás cortes de la
  semana. El nivel implícito quedó identificado igual.
- **Los cron del martes** llegaron entre las 14:53 y las 16:21 de Nueva York, unas 5 horas y 40 minutos tarde.
  La compuerta los descartó. Esta vez GitHub les asignó máquina sin demora.
- **Los manifiestos del histórico** vuelven a llevar el sufijo `-2`, como se explica en la sección 6.

**Cuenta:** 4 sesiones completas. La quinta es el jueves 8, y la aceptación se cierra ese día a las 10:50
de Nueva York.
