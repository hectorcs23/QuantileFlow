# QuantileFlow: estado de la continuación

**Fecha:** 26 de septiembre de 2026
**Rama:** `claude/compassionate-brown-1w9f90`
**Base:** [cómo proseguir](como_proseguir.md)

> Todavía no hay datos de mercado. Todo lo construido en esta etapa se verificó con datos
> **sintéticos**: las pruebas demuestran que el código mide, ingiere y reproduce como se pretende, no
> que exista una señal.

---

## 1. Acceso a datos: problema bloqueante

Qué se comprobó desde el entorno de trabajo:

| Comprobación | Resultado |
|---|---|
| Credenciales de Alpaca o Robinhood en el entorno | No hay ninguna |
| Conectores de Alpaca o Robinhood | No hay ninguno |
| `data.alpaca.markets`, `paper-api.alpaca.markets`, `docs.alpaca.markets`, `api.robinhood.com` | El proxy de red del entorno rechaza la conexión (403) |
| `pypi.org` (control) | Responde |

Qué hace falta para usar Alpaca:

1. En la configuración del entorno (menú del entorno en la barra de título de la sesión, **Edit**),
   permitir los dominios `data.alpaca.markets` y `paper-api.alpaca.markets` (y `docs.alpaca.markets`
   para consultar la documentación), o elegir un nivel de acceso de red más amplio.
2. En esa misma configuración, agregar como variables de entorno `APCA_API_KEY_ID` y
   `APCA_API_SECRET_KEY`. Conviene que sean de una cuenta *paper*: las claves de Alpaca no son de solo
   lectura. Las claves no deben pegarse en el chat.
3. Abrir una sesión nueva para que tome los cambios.

Riesgos que habrá que verificar en cuanto haya acceso. Hoy no pudieron comprobarse: la documentación
también está bloqueada. Lo que sigue es lo que conozco de Alpaca:

- **SPXW:** Alpaca ofrece opciones sobre acciones y ETF, no sobre índices. Con Alpaca, el piloto sería
  sobre **SPY**. Como prevé el plan, entonces los dividendos, el ejercicio anticipado y la sensibilidad
  de la conversión americana pasan a ser requisitos de medición; el núcleo ya los trata.
- **Historia a las 09:45:** Alpaca da barras y operaciones históricas de opciones, pero cotizaciones
  solo recientes. Si se confirma, no se podría reconstruir el bid/ask de las 09:45 de sesiones pasadas.
  Las alternativas son capturar la cadena cada día desde ahora (20–40 sesiones son de 4 a 8 semanas) o
  comprar una muestra histórica, por ejemplo en Cboe DataShop.
- **Feed:** el feed gratuito de opciones es indicativo y no el NBBO de OPRA; para medir paridad dentro
  de bid/ask hace falta el feed OPRA, que requiere suscripción.
- **Subyacente:** Alpaca no da el nivel del índice SPX. Con SPY, el subyacente es la propia acción.

**Robinhood** no ofrece una API oficial de datos de opciones: su API oficial es de criptomonedas. Las
librerías no oficiales usan el usuario, la contraseña y el segundo factor de la cuenta. No lo recomiendo.

---

## 2. Qué se construyó del plan sin datos

| Bloque | Qué pedía el plan | Qué se hizo | Dónde |
|---|---|---|---|
| A1 | Versión de referencia registrada | Registro del commit, del entorno y del resultado de las pruebas. Versiones exactas de las dependencias. Configuración del piloto versionada, con huella. | `scripts/verificar_entorno.py`, `reports/verificacion/`, `requirements-bloqueo.txt`, `configs/piloto.toml` |
| A2 | Contrato de datos y adaptador | Esquema de cotizaciones con raíz, strike, tipo, ejercicio, liquidación, vencimiento, multiplicador, bid/ask, tamaños y cuatro sellos UTC. Validador, símbolos OCC y adaptador a capturas. Detalles: <ul><li>si falta la hora del evento, la edad queda «desconocida», con una alerta, y no se inventa;</li><li>una disponibilidad posterior al corte excluye la fila;</li><li>no se mezclan estilos de liquidación.</li></ul> | `quantileflow/contrato.py`, `quantileflow/cadenas.py` |
| A3 | Almacenamiento y replay | Crudo inmutable direccionado por SHA-256, tablas Parquet y manifiesto por corrida. Pruebas de que reprocesar da los mismos bytes y de que los datos posteriores al corte no cambian nada. | `quantileflow/almacen.py`, `quantileflow/corrida.py` |
| B1 | Revisar controles; medir calidad | Métricas por sesión: filas, válidas, exclusiones por motivo, pares, cobertura, ancho en precio, relativo y en ticks, edad, sincronía y señales disponibles. Tolerancia en ticks para el spread relativo. Conjunto «solo cota» (bid nulo). | `cadenas.metricas_calidad`, `cadenas.ReglasCalidad` |
| B2 | Convenciones y signos | RR25 = IV call − IV put, con delta forward sin descuento. Strikes `F·1.03` y `F/1.03` (distancia logarítmica simétrica). Razón de primas con el mismo signo. La referencia de primas simétricas se documenta como hipótesis de sonrisa simétrica y se prueba. | `cadenas.asimetria_delta`, `cadenas.asimetria_simetrica` |
| B3 | Discrepancias locales frente a comunes | Forward con error jackknife, tasa implícita con su error, `ln(F/S)` y discrepancia frente al forward contractual. Una prueba muestra que un desplazamiento común lo absorbe el forward. | `cadenas.residuos_paridad`, `cadenas.fila_informe` |
| B4 | Ajuste robusto | No hecho (prioridad P1). | — |
| C | Etiquetas e informe | Calendario XNYS real (feriados, cierres anticipados y cierres extraordinarios). Etiquetas con `decision_at`, `label_end_at` y `label_available_at`, y filtro de madurez. Plazo constante de 30 días con vencimientos que lo encierran e interpolación en varianza total. Tabla diaria exportable, cuatro gráficas, estabilidad 09:45–10:00, ejemplos y dictamen con criterios. | `quantileflow/calendario.py`, `etiquetas.py`, `piloto.py`, `informe.py` |

La batería de pruebas pasa de 114 a 142.

---

## 3. Plantilla del informe con datos sintéticos

[`reports/piloto_sintetico/informe.md`](../reports/piloto_sintetico/informe.md) recorre el mismo camino
que recorrerán los datos reales: archivo crudo, normalización, validación, medición, informe y
manifiesto. Cubre 30 sesiones, del 20 de octubre al 1 de diciembre de 2025, con Acción de Gracias y un
cierre anticipado, y seis días degradados a propósito:

| Escenario | Qué produjo |
|---|---|
| Cotizaciones desfasadas cerca de delta 25 | Se excluyen; RR25 «no identificada» |
| Hueco de strikes call | RR25 y asimetría «no identificadas» |
| Spreads anchos | RR25 identificada con banda más ancha |
| Snapshot sin hora de evento | Alerta de edad desconocida |
| Subyacente desfasado | Alerta de sincronía |
| Subyacente ausente | Sesión no disponible y etiquetas vecinas ausentes |

- **Dictamen:** «apto con limitaciones». Solo el cambio diario de RR25 queda por debajo de su umbral
  (0.79 frente a 0.80).
- **Estabilidad 09:45–10:00:** 0.04 veces el ancho de banda.
- Son cifras sintéticas: no dicen nada sobre SPX.

---

## 4. Hallazgos de esta etapa

- **Hueco de interpolación demasiado laxo.** Por delta se interpolaba sobre huecos de hasta 0.05 en `k`.
  Al excluir puts desfasados, el RR25 salía de cruzar el hueco (0.069 frente a 0.066 verdadero). El
  límite baja a 0.02, igual que en la medida logarítmica.
- **Cambio de signo.** La convención anterior era put − call; ahora es call − put en todas las
  medidas, la figura y el documento. Las cifras de asimetría de entregas anteriores cambian de signo.
- **Desplazamientos comunes invisibles en el residuo local.** Encarecer 0.10 todos los puts no deja
  residuos locales fuera de banda; se ve solo en la discrepancia del forward frente a la referencia.
- **Filas de horas anteriores.** En la captura de las 10:00, las filas de las 09:45 salen como
  reemplazadas y además desfasadas. Es lo esperado y queda registrado.

---

## 5. Qué falta

- [ ] Resolver el acceso a datos (sección 1) y elegir la fuente: Alpaca (SPY, captura hacia adelante)
      o una muestra histórica de SPXW.
- [ ] Adaptador del proveedor elegido, verificado con respuestas reales. Confirmar instrumento, sellos
      de tiempo, cobertura y costo.
- [ ] Piloto real de 20–40 sesiones en `reports/piloto/`.
- [ ] Revisar los umbrales de calidad y del dictamen con el piloto y congelarlos en una nueva versión de
      `configs/piloto.toml`.
- [ ] Referencia externa del forward: curva de tasas y dividendos con fuente.
- [ ] B4: pérdida robusta en el ajuste de superficie (P1).
- [ ] Protocolo predictivo pequeño (sección 7 del plan), después del piloto.
