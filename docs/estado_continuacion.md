# QuantileFlow: estado de la continuación

**Fecha:** 26 de septiembre de 2026
**Rama:** `claude/compassionate-brown-1w9f90`
**Base:** [cómo proseguir](como_proseguir.md)

> Todavía no hay datos de mercado. Todo lo construido en esta etapa se verificó con datos
> **sintéticos**: las pruebas demuestran que el código mide, ingiere y reproduce como se pretende, no
> que exista una señal.

> **Actualización del 26 de septiembre (tarde).** El acceso a Alpaca quedó resuelto: hay claves
> *paper* en el entorno y la red lo permite. SPXW sí está disponible, pero no hay historia de
> cotizaciones ni nivel de SPX, y el feed gratuito modifica las cotizaciones. Se construyó la captura
> diaria hacia adelante. Detalle y primera verificación con datos reales en
> [Alpaca como fuente de datos](fuente_alpaca.md). La sección 1 queda como registro de lo que se sabía
> antes de tener acceso.

> **Actualización del 21 de octubre.** El usuario conectó Robinhood a Claude. Del conector solo se usan
> las herramientas de lectura de datos de mercado, como referencia gratis para las capturas de Alpaca:
> el SPX real, la marca de las opciones cada 15 segundos (solo del día) y el bid y el ask en vivo.
> Resultados en la [comparación con Robinhood](comparacion_robinhood.md). Lo que dice la sección 1 sobre
> Robinhood era de antes del conector.

> **Actualización del 29 de octubre.** Se revisaron todas las ramas del repositorio. El mapa está en la
> sección 6, y la lista de la sección 5 quedó al día.

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

- [x] Resolver el acceso a datos (sección 1): Alpaca funciona y ofrece SPXW, con captura hacia
      adelante ([fuente_alpaca.md](fuente_alpaca.md)).
- [x] Adaptador del proveedor, verificado con respuestas reales (`quantileflow/alpaca.py`).
      Instrumento, sellos, cobertura y costo confirmados.
- [x] Decidir dónde corre la captura diaria: GitHub Actions en el repositorio privado
      `QuantileFlow-datos` (plantilla en `ops/repo_datos/`).
- [x] Crear ese repositorio, subir la plantilla y agregar las dos claves como secretos
      ([instalación del repositorio de datos](instalacion_repo_datos.md)).
- [x] Decidir el feed: `indicative` por ahora; OPRA se decide tras 3–5 sesiones reales.
- [x] Corregir los ocho hallazgos de la revisión de `e2b92f0` (commit `79c1554`;
      [respuesta](respuesta_revision_e2b92f0.md)).
- [x] Decidir el precio objetivo independiente: SPY observado en el SIP histórico, con rendimiento
      total y de precio. El SPX inferido queda como referencia de las opciones
      ([respuesta a la revalidación de `d815bdd`](respuesta_revalidacion_d815bdd.md)).
- [x] Histórico SIP y dividendos de Alpaca; diario de captura con recuperación; plazo absoluto;
      workflows por hora (commits `03f2230`, `79bf8a7`, `3b266a4` y `fcb8637`).
- [x] Revisión de `8c97b2b`: cobertura de dividendos aparte, eventos y etiquetas versionados y plazo
      de preparación del respaldo (`6f0e748`, `f2a5663`; [respuesta](respuesta_revision_8c97b2b.md)).
- [x] Revalidación de `a5e2748`: una ausencia abre una discrepancia pendiente que solo resuelve
      evidencia fechada; solo cuentan las consultas que piden dividendos; tramos con el estado de cada
      instante (provisional, aceptada bajo la política de 60 días, pendiente); se miden las revisiones
      después de aceptarse (`c5aaded`, `8316540`; [respuesta](respuesta_revalidacion_a5e2748.md)).
- [x] Revalidación de `5c15028`: un dividendo recibido sin fecha ex o sin monto es una versión con
      discrepancia y deja pendientes las etiquetas que podría afectar (`7fb0585`;
      [respuesta](respuesta_revalidacion_5c15028.md)).
- [x] Cierre de la revalidación de `b240dc2`: sin defectos nuevos; pasar a la prueba operativa con
      `7fb0585`. Después: registro de la ejecución a prueba de errores y revisión de la operación
      (`7a59d04`, `bbbdc6e`, sin fijar hasta revisarlos; [respuesta](respuesta_cierre_b240dc2.md)).
- [x] Revisión de esos cambios: registro también al iniciar, `--resoluciones` explícito y pruebas
      portables (`4ffde8a`; [respuesta](respuesta_cambios_operativos.md)).
- [x] Verificación de `4ffde8a`, también en Windows: queda fijado en los workflows
      ([respuesta](respuesta_verificacion_4ffde8a.md)).
- [x] Instalar el repositorio de datos y acreditar la captura: prueba manual, commit usado y crudo
      guardado (`ops/repo_datos/README.md`, «Instalación y aceptación»). Se hizo el 27 por la noche y
      quedó verificado ([instalación del repositorio de datos](instalacion_repo_datos.md)).
- [x] Verificación independiente de la instalación: confirmada, sin defectos que bloqueen la prueba
      programada ([respuesta](respuesta_verificacion_instalacion.md)).
- [x] Prueba operativa de 3–5 sesiones con el repositorio de datos, revisada con
      `scripts/revisar_operacion.py`: puntualidad, estados, respaldo, recuperación y dividendos. Valida la
      operación, no la capacidad predictiva: con 60 días de política, ninguna etiqueta nueva estará
      aceptada al terminarla. Se cerró el 8 de octubre: **aceptada con observaciones**. Fueron cinco
      sesiones completas, del 2 al 8 de octubre, lanzadas por Claude con `workflow_dispatch`, porque los
      cron de GitHub llegan de 5 a 8 horas tarde. El respaldo no hizo falta
      ([aceptación de la operación](aceptacion_operacion.md), sección 11).
- [ ] Mantenimiento de las plantillas antes del lunes 19 de octubre, cuando `ubuntu-latest` empieza a
      pasar a Ubuntu 26.04: `runs-on: ubuntu-24.04` y acciones para Node.js 24. Además: que la compuerta
      registre los disparos descartados, que el histórico acepte disparos tardíos del mismo día y corregir
      el sufijo `-2` de los manifiestos del histórico. Lleva un nuevo commit fijado y se instala con una
      corrida manual de prueba y comprobación de huellas ([respuesta](respuesta_verificacion_instalacion.md);
      [aceptación](aceptacion_operacion.md), sección 11). **Sigue pendiente al 28 de octubre:** el job
      todavía cae en `ubuntu-24.04` por casualidad, cada corrida avisa por Node.js 20 y el histórico sigue
      escribiendo el sufijo `-2`.
- [ ] Decidir entre `indicative` y OPRA con la evidencia de la aceptación y del experimento intradía
      ([aceptación](aceptacion_operacion.md), sección 11; [revisión del experimento](respuesta_experimento_intradia.md)).
      Con el presupuesto en US$0 desde el 9 de octubre, se sigue con `indicative` y OPRA queda en suspenso
      ([revisión del PDE](respuesta_pde_captura_gratis.md), sección 5).
- [ ] Comparación diaria con Robinhood: cuánto se alejan el SPX implícito, los mids y los spreads de
      `indicative` de un dato mejor, sin pagar. Al 30 de octubre, el SPX implícito lleva 41 cortes; las
      opciones, 8 de las unas 20 sesiones que hacen falta para concluir ([comparación](comparacion_robinhood.md)).
- [ ] Margen de minutos de Actions: se gastan unos 85 por sesión, unos 1 870 al mes, cerca de los 2 000
      de GitHub Free. Lanzar `captura-1000` a las 09:35 ahorraría unos 400 al mes; lo decide el usuario
      ([revisión del PDE](respuesta_pde_captura_gratis.md), sección 6). Ya no lo recomiendo: el 27 de
      octubre la comprobación de las 09:32 llegó 33 minutos tarde, y con ese atraso se perdería la de las
      10:00 ([aceptación](aceptacion_operacion.md), sección 12).
- [ ] Captura ampliada (7 a 90 días): falta medir a la hora del corte que las respuestas llegan antes
      de él. Propuesta: el lunes 12 a las 09:50 y 10:05, aislada y sin tocar el piloto
      ([revisión del PDE](respuesta_pde_captura_gratis.md), secciones 3 y 5).
- [x] Piloto real en `reports/piloto/`: 21 sesiones, del 2 al 30 de octubre, con `piloto-0.3`. Dictamen:
      apto con limitaciones ([revisión](revision_piloto.md)).
- [ ] Atraso de las rutinas de Claude: 28, 24, 35 y 45 minutos del 27 al 30 de octubre. El 29 se perdió por
      primera vez una hora (las 09:45), y el 30 la de las 09:45 quedó lista solo 84 s antes del corte. Las
      rutinas de entre las 9 y el mediodía de Nueva York pueden atrasarse; lanzar antes de las 9 cuesta
      minutos de Actions, porque los jobs esperan el corte en la máquina. Lo decide el usuario
      ([aceptación](aceptacion_operacion.md), sección 12).
- [ ] Revisar los umbrales de calidad y del dictamen con el piloto y congelarlos en una nueva versión de
      `configs/piloto.toml`. Propuesta de `piloto-0.4`, pendiente de aprobar: `desfase_spot_max_s` de 2 a
      10 s ([revisión del piloto](revision_piloto.md), sección 4).
- [ ] Referencia externa del forward: curva de tasas y dividendos con fuente.
- [ ] B4: pérdida robusta en el ajuste de superficie (P1).
- [ ] Protocolo predictivo pequeño (sección 7 del plan), después del piloto.
- [ ] Siguiente paso de la investigación de Codex después del ruido concentrado. Codex propone medir
      bandas del cambio de la CDF entre las 09:45 y las 10:00. La revisión propone, antes, ver con Robinhood
      cuánto se estrechan las bandas con cotizaciones consolidadas
      ([revisión](respuesta_ruido_concentrado.md), sección 4).
- [ ] Ordenar las ramas: la predeterminada de GitHub, los PR abiertos y las líneas paralelas (sección 6).
- [ ] Primer lunes con horario de invierno, el 2 de noviembre. Las rutinas van en hora de Nueva York y
      los cron de GitHub tienen entradas para EDT y EST. Hay que comprobar que el corte de las 09:45 caiga a
      las 14:45 UTC.
- [ ] Decisiones para la fase de posición: posiciones actuales, moneda, costos y límites de riesgo
      ([plan de trabajo](plan_de_trabajo.md), sección 7). No hacen falta hasta después del protocolo
      predictivo.

---

## 6. Mapa del repositorio al 29 de octubre

La línea principal es `claude/lucid-hamilton-hz8l80`: captura, revisión diaria y comparación con
Robinhood. Ahí está el commit que fijan los workflows (`4ffde8a`), así que esta rama no se puede borrar.

La rama predeterminada de GitHub sigue siendo `claude/compassionate-brown-1w9f90`, del 26 de septiembre.
Quien entra al repositorio ve el README de esa fecha, 64 commits atrás.

Las demás líneas no están fusionadas:

| Línea | Ramas | Último cambio | Estado | Qué falta decidir |
|---|---|---|---|---|
| Investigación de Codex | 14 ramas `codex/*` encadenadas; la punta, `codex/ruido-concentrado-20261022`, contiene a las otras | 26 oct | El 20 de octubre Codex mostró que las bandas de `indicative` no admiten precios coherentes en ninguna de 48 combinaciones. Propuso tres caminos: A, un simulador (hecho el 21); B, distribuciones con ruido (22 y 26); C, una muestra real, que Robinhood ya da en parte. Aquí hay revisión escrita del intradía, del PDE y del ruido concentrado; de lo demás, del 10 al 22 de octubre, no | Qué camino sigue y si algo pasa a la línea principal |
| Estrategias con puts | `claude/beautiful-darwin-v0oyon` y `codex/correcciones-entropia-20261020` | 20 oct | Solo datos sintéticos. Codex corrigió la inclinación de mínimo KL y el rechazo de probabilidades negativas | Si sigue, y con qué datos |
| Laboratorio de BTC | `claude/hopeful-mendel-vxf3vv` (`btc-prediction-market-lab/`) | 21 oct | Proyecto aparte sobre los contratos de BTC a 15 minutos de Kalshi. Estado `DATA_ONLY`, sin ventaja medida | Si sigue en este repositorio |
| Interfaz en inglés e ingesta de Robinhood | `claude/eloquent-mendel-aux9xy` | 21 oct | Sale del 26 de septiembre: no tiene la captura de Alpaca. Pasa nombres y archivos a inglés, así que choca con la línea principal. Aporta `quantileflow/sources/robinhood.py` | Adoptar la parte de Robinhood o descartarla |
| Exploración con datos gratis | PR 1 (`codex/0dte-skew-reversion`) y PR 2 (`codex/validate-free-skew`), abiertos desde el 2 de octubre | 2 oct | PR 1: protocolo del skew 0DTE de SPY, sin datos. PR 2: reproduce bt2, pero la convergencia no distingue reversión de error de medición, y el SKEW diario no mejora el pronóstico | Cerrarlos o fusionarlos |
