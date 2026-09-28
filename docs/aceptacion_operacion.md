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
| Lunes 28 de septiembre | `perdida` | `perdida` | Sin descargar | No se lanzó: GitHub no disparó ningún cron | Sección 1 |

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
