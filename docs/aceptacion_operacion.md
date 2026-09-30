# QuantileFlow: aceptación de la operación

**Periodo previsto:** del 28 de septiembre al 2 de octubre de 2026, de 3 a 5 sesiones.
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
