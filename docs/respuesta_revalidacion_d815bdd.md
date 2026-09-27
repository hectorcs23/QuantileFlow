# QuantileFlow: respuesta a la revalidación de `d815bdd`

**Fecha:** 27 de septiembre de 2026.
**Revalidación recibida:** «revalidación y decisión sobre SPY», sobre `d815bdd`.
**Commits:** en la rama `claude/lucid-hamilton-hz8l80`:
- [`03f2230`](https://github.com/hectorcs23/QuantileFlow/commit/03f2230): señal, referencia y objetivo;
- [`79bf8a7`](https://github.com/hectorcs23/QuantileFlow/commit/79bf8a7): SIP histórico y dividendos;
- [`3b266a4`](https://github.com/hectorcs23/QuantileFlow/commit/3b266a4): recuperación operativa;
- [`fcb8637`](https://github.com/hectorcs23/QuantileFlow/commit/fcb863782508706d94f001f091e23551ec16baac):
  rastro de las cotizaciones repetidas;
- la documentación.

**Commit fijado en los workflows:** `fcb8637`.
**Registro de verificación:** [`reports/verificacion/fcb863782508.json`](../reports/verificacion/fcb863782508.json).
Árbol limpio, 186 pruebas pasadas (167 en `d815bdd`).

> De acuerdo con la decisión: **SPY observado es el primer objetivo de investigación**. Esta entrega
> cubre los puntos 1 a 4 de la entrega sugerida. El 5 (repositorio privado) y el 6 (prueba de 3–5
> sesiones) dependen de tu parte, que se describe en la sección 5.
>
> **Corrección (revisión de `8c97b2b`):** la cobertura de dividendos de la sección 2 partía de una
> premisa falsa. Alpaca no garantiza cuándo publica un evento, y además la madurez no incluía la
> consulta que habilitaba la etiqueta. Quedó rediseñada: cobertura aparte, versiones de eventos y
> etiquetas provisional, reconciliada y revisada. Ver
> [respuesta a la revisión de `8c97b2b`](respuesta_revision_8c97b2b.md). La captura se fija ahora en
> `f2a5663`.
>
> **Corrección (revalidación de `a5e2748`):** los estados pasan a ser provisional, aceptada (bajo la
> política de 60 días, una regla y no una garantía) y pendiente. Una ausencia abre una discrepancia en
> vez de retirar el dividendo. Ver [respuesta a la revalidación de `a5e2748`](respuesta_revalidacion_a5e2748.md).
> La captura se fija en `8316540`.

---

## 1. La entrega, punto por punto

| # | Pedido | Qué se hizo | Dónde | Pruebas |
|---|---|---|---|---|
| 1 | Separar la referencia de SPXW del objetivo SPY: medidas de SPXW iguales al añadir SPY; etiquetas de SPY separadas y con procedencia | Tres papeles que no se mezclan: **señal** (opciones SPXW), **referencia de las opciones** (SPX implícito, regla puntual) y **objetivo** (SPY observado, regla histórica). El objetivo se declara en `[objetivo]` y debe ser `observado`; cada serie usa una sola fuente, elegida cuando hay varias. La tabla de etiquetas separa las series `objetivo` y `referencia` y guarda en cada fila símbolo, fuente y tipo de precio. En la plantilla sintética, todas las medidas de SPXW (RR25, asimetría, forward, filas y exclusiones, en las dos horas) son idénticas a las de `d815bdd`. | `piloto.py`, `contrato.py`, `configs/piloto.toml` (`piloto-0.3`), `informe.py`, `corrida.py`, `scripts/piloto.py` | `test_medidas_de_las_opciones_no_cambian_al_anadir_el_objetivo`, `test_objetivo_observado_y_de_una_fuente_elegida`, `test_procedencia_en_la_tabla_diaria` |
| 2 | Adaptador SIP histórico para etiquetas: evento a las 09:45, descarga posterior, madurez correcta y ninguna influencia sobre señales anteriores | `scripts/historico_alpaca.py` pide a `/v2/stocks/quotes` (feed SIP) las 1 000 cotizaciones más recientes de SPY hasta cada corte, en una sola página y pasados 15 minutos y un margen. Nunca consulta antes: el planificador espera y la descarga lo rechaza. La normalización fija el snapshot en el corte y la disponibilidad documentada en el corte más 15 minutos, y comprueba que la descarga fue posterior. Esa disponibilidad es la madurez; además, el objetivo tiene un piso de publicación de 15 minutos, también para una etiqueta ausente. Sin el histórico, las medidas de SPXW no cambian (prueba de punta a punta). | `alpaca.pedir_historico`, `planificar_historico`, `descargar_historico`, `normalizar_historico`, `configs/captura_alpaca.toml` (`[historico]`) | `test_historico_sip_una_pagina_despues_del_retraso`, `test_historico_no_se_consulta_antes_y_un_fallo_se_reintenta`, `test_objetivo_del_sip_historico_de_punta_a_punta`, `test_etiqueta_del_objetivo_madura_con_su_publicacion`, `test_objetivo_con_la_regla_historica` |
| 3 | Convenciones de precio y dividendos, con ejemplos: ex-dividendo, ausencia de cotización y spread anormal | Precio del objetivo, rendimiento total y de precio, y cobertura de dividendos (sección 2). Los ejemplos corren en el mercado sintético: un viernes antes de la fecha ex, un día sin cotización de SPY y otro cuya única cotización al corte tiene spread anormal. Los dividendos salen de `/v1/corporate-actions`. | `contrato.precio_para_etiqueta`, `contrato.DIVIDENDOS`, `etiquetas.etiquetas_retorno`, `alpaca.normalizar_eventos` | `test_dividendo_ausencia_y_spread_anormal_del_objetivo`, `test_precio_para_etiqueta_usa_la_ultima_cotizacion_valida`, `test_dividendo_en_el_rendimiento_total_y_en_la_madurez`, `test_rendimiento_total_exige_una_consulta_de_dividendos_posterior_al_fin`, `test_rendimiento_total_sin_dividendos_queda_ausente`, `test_dividendos_de_los_eventos_corporativos`, `test_validacion_de_dividendos` |
| 4 | Recuperación operativa: interrupción tras una página, timeout antes de un corte y respaldo con estado verificable | Cada captura lleva un **diario** por página, sincronizado en disco, y un manifiesto final **atómico**. Un diario sin manifiesto se recupera como `parcial` o `fallida`, marcado como interrumpido y con el hash del diario. Un **plazo absoluto** (60 s después del corte) termina el proceso aunque una solicitud siga colgada. Cada hora corre en su propio **workflow**, con su compuerta y su respaldo; el histórico tiene el suyo. Un respaldo que llega antes del corte repite la captura interrumpida con otra etiqueta; si una hora queda capturada dos veces, el control de cadenas marca la cotización vieja como `reemplazada`. | `alpaca.Diario`, `recuperar`, `Vigilante`, `almacen.crear_nuevo`, `scripts/capturar_alpaca.py` (`--recuperar`, `--plazo-s`), `ops/repo_datos/.github/workflows/` | `test_corte_brusco_tras_una_pagina_se_recupera_como_parcial` (SIGKILL en otro proceso), `test_plazo_absoluto_termina_una_solicitud_colgada`, `test_diario_con_la_ultima_linea_truncada_o_roto_en_medio`, `test_escritura_atomica_que_no_sobrescribe`, `test_dos_capturas_de_la_misma_hora_marcan_la_vieja_como_reemplazada` |
| 5 | Verificar el repositorio privado y el despliegue | Pendiente de tu parte. `hectorcs23/QuantileFlow-datos` sigue sin existir para esta integración, que no puede crearlo. La plantilla está lista. | [`ops/repo_datos/`](../ops/repo_datos/) | — |
| 6 | Prueba de 3–5 sesiones | Empieza cuando el repositorio tenga los secretos (sección 5). | — | — |

La prueba de aceptación de la recuperación es la que pedía la revalidación. Un proceso real captura
con un transporte cuya segunda página se cuelga; se lo mata con SIGKILL en cuanto la primera página
aparece en el diario. La recuperación produce un manifiesto `parcial`, con esa página verificada por
su hash, que se normaliza como cualquier otro. Con el plazo absoluto, el mismo proceso termina solo, con
código 3, y el diario registra la interrupción.

---

## 2. Convenciones

**Dos relojes, sin relajar H3.**
- La **regla puntual** (`precio_al_corte`) exige que el precio estuviera disponible en el corte y no
  desfasado. La usan las señales, los controles, la referencia de las opciones, el movimiento previo y
  las etiquetas auxiliares `*_referencia`.
- La **regla histórica** (`precio_para_etiqueta`) toma el precio vigente en el corte, aunque se
  publique después. Solo la usa el objetivo, y su publicación fija la madurez de la etiqueta.

**Precio del objetivo a las 09:45.** Es el mid de la **última cotización válida** con evento no
posterior al corte y no más vieja que 60 s:
- es válida si `bid > 0`, `ask ≥ bid` y su spread relativo no supera 5 pb;
- una cruzada, sin bid o con spread anormal se descarta y se usa la anterior válida;
- si no queda ninguna, la etiqueta queda ausente con su motivo;
- con dos cotizaciones del mismo microsegundo, vale la última en el orden de la tabla, que la
  normalización ordena por la hora del evento en nanosegundos.

Una barra con sello 09:45 no sirve: abarca operaciones posteriores.

**Madurez.** `label_available_at` es el máximo de:
- el fin más el retraso de publicación (0 en general; al menos 15 minutos para el objetivo);
- la disponibilidad de los precios inicial y final;
- la primera recepción de los dividendos que se suman.

**Rendimiento total y de precio.**
- `retorno_log = log((P1 + D) / P0)`, donde `D` es la suma de los dividendos en efectivo cuya
  apertura ex cae en `(inicio, fin]`: quien tenía el activo al inicio los cobra.
- Una etiqueta que empieza a las 09:45 del día ex ya no lo cobra. Una que termina ese día, sí.
- `retorno_precio_log = log(P1 / P0)` va aparte, y `dividendos` guarda `D` para auditar la
  diferencia.
- La convención se declara en `[objetivo] rendimiento` (`total` o `precio`) y el informe la publica en
  el alcance.
- La referencia, un índice de precio, no suma dividendos.

**Cobertura de los dividendos** (*corregida después; ver la nota inicial*). Esta entrega suponía que
un dividendo aparece en Alpaca desde que se anuncia y que una consulta completa posterior al fin
incluye todos los que le tocan. Alpaca no lo garantiza. La política vigente está en
[respuesta a la revisión de `8c97b2b`](respuesta_revision_8c97b2b.md), sección 3.

Alpaca no da la hora del anuncio. Un dividendo cuenta como conocido desde la primera consulta que lo
trajo. Si sus datos cambian, cuenta desde la primera que trajo la versión vigente.

**Otros eventos corporativos.** Un split, una fusión o cualquier evento distinto de un dividendo en
efectivo dentro del rango normalizado **detiene** la normalización: cambiaría los precios sin que las
etiquetas lo traten. Fuera del rango solo se informa.

**Procedencia.** Cada serie se identifica como `proveedor/feed`. SPY llega de dos fuentes: IEX en vivo
(diagnóstico) y el SIP histórico (objetivo). Por eso el piloto exige `--fuente-objetivo alpaca/sip`.

**El SPX implícito sigue** como referencia de las opciones y como serie auxiliar, claramente separada.
Sus etiquetas (`ret_*_referencia`) son diagnóstico de medición y nunca sirven para evaluar: comparten
fuente y errores con las señales.

---

## 3. Verificación con la cuenta de Alpaca

El 27 de septiembre, con la cuenta *paper* y el script de producción, sobre 10 cortes (09:45 y 10:00
del 21 al 25 de septiembre). Solo se publican agregados:

| Medida | Resultado |
|---|---|
| Qué es el SIP de Alpaca | NBBO consolidado: el bid y el ask vienen de bolsas distintas, con hora en nanosegundos. |
| Cobertura de una página | Las 1 000 cotizaciones más recientes abarcan de 6 a 19 s antes del corte, dentro de los 60 s de la regla. |
| Última cotización | A menos de 10 ms del corte en los 10 casos. |
| Spread relativo | Mediana 0.26 pb, máximo 1.2 pb. Ninguna cotización supera los 5 pb ni se descarta. |
| Tamaño | Unos 27 KB comprimidos por corte (268 KB la semana, con los eventos). |
| Consulta prematura | Alpaca responde 403 si la ventana termina hace menos de 15 minutos. El script no consulta antes. |
| Idempotencia | La segunda ejecución no descargó nada: los 10 cortes ya estaban completos. |
| Dividendos de SPY | 5 en la ventana (fechas ex del 19/09/2025 al 18/09/2026). El del 18 de septiembre ya figura aunque se paga el 30 de octubre. No hay otros eventos. |

Además, una captura inmediata real con el script nuevo dejó:
- un diario con una línea por solicitud, por página y por fin;
- un manifiesto atómico, en solo lectura;
- ningún temporal y ninguna clave en el crudo.

El diagnóstico del 25 de septiembre, regenerado con el código nuevo, sale **idéntico byte a byte**.

---

## 4. Cambios que afectan a resultados o nombres previos

- **Columnas de la tabla diaria.**
  - `ret_{h}` pasa a ser `ret_{h}_objetivo` (total), con `ret_precio_{h}_objetivo`, `div_{h}_objetivo` y
    `estado_ret_{h}_objetivo`, y `ret_{h}_referencia`.
  - `retorno_previo` pasa a ser `retorno_previo_referencia`.
  - `fuente_subyacente` y `tipo_precio_subyacente` pasan a ser `fuente_referencia` y
    `tipo_precio_referencia`, y se añaden `fuente_objetivo` y `tipo_precio_objetivo`.
- **Opciones de la línea de comandos.** `--fuente-subyacente` pasa a ser `--fuente-referencia`, y se
  añaden `--fuente-objetivo` y `--dividendos`.
- **Prueba renombrada.** `test_precio_objetivo_desfasado_o_tardio_deja_la_etiqueta_ausente` pasa a ser
  `test_referencia_desfasada_o_tardia_deja_ausentes_sus_etiquetas`. H3 se aplica ahora a la
  referencia; el objetivo usa la regla histórica y tiene sus propias pruebas.
- **Versiones.**
  - Configuración: `piloto-0.2` → `piloto-0.3` (`[objetivo]`).
  - Captura: `captura-alpaca-0.1` → `captura-alpaca-0.2` (`[historico]`, `[eventos]`, `plazo_s`).
  - `REF_CODIGO` pasa de `79c1554` a `fcb8637`: es otra versión de medición.
- **Plantilla sintética.**
  - Incluye un SPY publicado 15 minutos después del corte, con un dividendo (fecha ex 10/11/2025) y un
    día con spread anormal (25/11/2025).
  - El dictamen sigue «apto con limitaciones».
  - La etiqueta del objetivo a 1 sesión está disponible en el 93 % de las sesiones.
  - El 20 de noviembre, sin precio de SPX, el objetivo sí tiene etiquetas: los papeles son
    independientes.
- **Workflow.** `captura.yml` se reemplaza por `captura-0945.yml` y `captura-1000.yml` (sobre
  `captura-hora.yml`) y por `historico.yml`.
- **Sin cambios.** Las 64 figuras de la propuesta no cambian: de lo modificado solo usan funciones de
  `sintetico.py` que no se tocaron (la superficie, las cadenas y el panel), no el mercado del piloto.

---

## 5. Qué falta y de quién

**Tu parte, para la prueba de 3–5 sesiones:**

1. Crear el repositorio privado `hectorcs23/QuantileFlow-datos` y copiar ahí `ops/repo_datos/`. Otra
   opción es dar a la aplicación de GitHub de Claude acceso a ese repositorio para que lo suba Claude.
2. Crear los secretos de Actions `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY`.
3. Probar **captura-0945 → Run workflow** con «ahora» y **historico-alpaca → Run workflow**.

**Qué mirar en esas sesiones**, en los registros de `raw/alpaca/ejecuciones/`:

- el retraso de cada disparo y el margen hasta cada corte;
- el estado de cada hora y si hubo recuperaciones (no debería haber ninguna);
- que cada corte tenga su histórico SIP, descargado después de su disponibilidad;
- que las etiquetas del objetivo maduren a la hora esperada;
- la coherencia amplia entre el SPX implícito y SPY del SIP (*corregido*: no mide el sesgo de RR25
  del feed indicativo; para eso hace falta una referencia de opciones comparable, como OPRA);
- con esos datos, `desfase_spot_max_s` y `edad_maxima_s`, sin tocarlos antes.

**Decisiones que siguen abiertas:**
- OPRA, tras esas sesiones.
- La curva de tasas con fuente para el forward.
- El ajuste robusto de la superficie (B4).

**Limitaciones que quedan declaradas:**
- Alpaca no da la hora del anuncio de un dividendo: la madurez usa la primera recepción.
- El precio del objetivo sale de la primera página del SIP. Si sus 1 000 cotizaciones fueran todas
  anómalas, la etiqueta quedaría ausente, aunque hubiera una válida más atrás dentro de los 60 s.
- Una captura recuperada nunca queda `completa`, aunque su diario muestre que llegó todo.
