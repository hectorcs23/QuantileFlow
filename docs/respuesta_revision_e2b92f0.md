# QuantileFlow: respuesta a la revisión del commit `e2b92f0`

**Fecha:** 26 de septiembre de 2026.
**Revisión recibida:** «revisión del código y próximos pasos», sobre `e2b92f07de958d1363267746007933c785304368`.
**Correcciones:** commit [`79c1554`](https://github.com/hectorcs23/QuantileFlow/commit/79c15549bacd71cec2bd60f1ac0888e9162019b3)
en la rama `claude/lucid-hamilton-hz8l80`.
**Registro de verificación:** [`reports/verificacion/79c15549bacd.json`](../reports/verificacion/79c15549bacd.json).
Árbol limpio, 167 pruebas pasadas.

> Coincido con la evaluación: se conserva la arquitectura y se corrige la medición antes de agregar
> modelos. Esta entrega cubre los pasos 1 y 2 del plan de continuación. El paso 3, qué precio
> independiente vamos a predecir, es una decisión pendiente (sección 3).

---

## 1. Método

1. Reproduje los ocho hallazgos contra `e2b92f0`, sin red ni credenciales. H2 dio exactamente el
   `cambio_rr25=-0.0013780205` de la revisión; H8 se confirmó por lectura del código, y quedó como
   prueba al refactorizar la planificación.
2. Convertí cada reproducción en una prueba de regresión y comprobé que fallaba con el código de
   `e2b92f0`.
3. Corregí el código y la batería pasa de 153 a 167 pruebas. Las reproducciones ya no se dan.
4. Regeneré todo lo que depende del código:
   - la plantilla sintética del piloto;
   - el diagnóstico del 25 de septiembre;
   - las 64 figuras de la propuesta, que salen idénticas byte a byte (el PDF sigue siendo coherente).

---

## 2. Hallazgos

| # | Qué cambió | Dónde | Pruebas |
|---|---|---|---|
| H1 · P1 | La elegibilidad al corte usa siempre los controles estrictos. El modo descriptivo del cierre ya no se activa por recibir tarde. Exige `--cierre-descriptivo`, una captura **inmediata**, la sesión cerrada según el calendario y el corte en su cierre, y se declara «no elegible para el piloto». Una captura programada tardía conserva 0 filas válidas aunque se pida el modo descriptivo. | `quantileflow/diagnostico.py` (nuevo, con la lógica que antes estaba en el script), `scripts/verificar_alpaca.py` | `test_diagnostico_no_relaja_sellos_de_una_captura_programada_tardia`, `test_modo_descriptivo_del_cierre_solo_si_se_pide_y_corresponde` |
| H2 · P1 | Una captura rechaza mezclas de proveedor o de feed. El piloto exige elegir las fuentes (`proveedor/feed`) cuando hay más de una. Una sesión con varias fuentes queda «no disponible». La tabla diaria guarda `fuente_opciones`, `fuente_subyacente`, `tipo_precio_subyacente` y `segmento`, y el cambio diario queda ausente al cambiar de segmento (fuente y versión de la configuración). El dictamen añade un **alcance** separado de la aptitud de los datos: medición sintética, indicativa o de mercado; precio objetivo observado o inferido; evaluación con precios de mercado permitida o no, y por qué. | `contrato._plazo_de_filas`, `piloto.ejecutar`, `piloto.medir`, `piloto._cambios`, `piloto.alcance`, `informe.py`, `corrida.py`, `scripts/piloto.py` (`--fuente-opciones`, `--fuente-subyacente`) | `test_mezcla_de_feeds_en_una_captura_se_rechaza`, `test_fuentes_explicitas_y_cambio_ausente_en_la_transicion`, `test_procedencia_en_la_tabla_diaria` |
| H3 · P1 | `precio_al_corte` descarta los precios con disponibilidad documentada posterior al corte y devuelve la procedencia. Si varias fuentes dan el mismo símbolo, exige elegir una. El precio objetivo también debe estar fresco (`edad_maxima_precio_s = 60`). Las etiquetas maduran cuando el precio se publicó y guardan el motivo de cada ausencia. | `contrato.precio_al_corte`, `piloto._precios_subyacente`, `etiquetas.etiquetas_retorno`, `configs/piloto.toml` | `test_subyacente_disponible_despues_del_corte_no_se_usa`, `test_subyacente_de_varias_fuentes_exige_elegir_y_tipo_valido`, `test_precio_objetivo_desfasado_o_tardio_deja_la_etiqueta_ausente`, `test_etiqueta_madura_cuando_el_precio_final_esta_disponible` |
| H4 · P2 | EWMA y persistencia devuelven NaN hasta la primera observación y aceptan una serie vacía. Desde la primera observación, la salida es la misma que antes. | `filtrado.ewma`, `filtrado.persistencia` | `test_filtros_causales_no_rellenan_con_datos_futuros` (con invariancia a datos futuros) |
| H5 · P2 | Cada página se guarda en cuanto llega. Una solicitud interrumpida queda `parcial` con sus páginas y la causa; el total de páginas es desconocido porque la paginación es por cursor. | `alpaca.ClienteAlpaca.paginas(al_recibir=…)`, `alpaca.Registro`, `alpaca.ejecutar` | `test_pagina_recibida_se_guarda_aunque_falle_la_siguiente` |
| H6 · P2 | Inversa generalizada por tramos: devuelve el extremo izquierdo en la meseta e interpola en el tramo que sube por encima de ella. | `distribuciones._inversa_generalizada` | `test_inversa_generalizada_con_mesetas` (en la meseta, justo antes y después, meseta inicial y dos mesetas) |
| H7 · P2 | Sin raíz en `[vol_min, vol_max]` o con parámetros no finitos o no positivos, devuelve NaN con motivo (`con_motivo=True`), y el resto del lote se calcula. | `opciones.vol_implicita_black` | `test_iv_sin_raiz_en_el_intervalo_devuelve_ausencia_sin_abortar` |
| H8 · P2 | Cada captura termina `completa`, `parcial` o `fallida`, y cada hora además puede quedar `perdida`. Tener archivo no cuenta como éxito. Un fallo después del corte se conserva, sin reemplazarlo con datos posteriores. El código de salida es 0 solo si todas las horas están completas. Cada ejecución deja un registro con el disparo, el margen hasta cada corte y el estado de cada hora. | `alpaca.estado_captura`, `alpaca.planificar`, `alpaca.codigo_salida`, `alpaca.escribir_ejecucion`, `scripts/capturar_alpaca.py` | `test_estados_de_cada_hora_y_codigo_de_salida` |

Otros cambios que salieron de la revisión:

- **Datos sintéticos.** El alcance declara «datos sintéticos» y nunca permite evaluar con precios de
  mercado. Sin esto, la plantilla sintética habría dicho «permitida».
- **Informe del 25 de septiembre.** Se regeneró con `--cierre-descriptivo` y ahora dice
  explícitamente «descriptivo del cierre, no elegible». Con los controles estrictos tiene
  0 filas válidas de 3 250. Las cifras descriptivas no cambian.
- **Pruebas en Windows.** `tests/conftest.py` fija el backend `Agg` de matplotlib: no dependen de Tk.

---

## 3. Decisiones metodológicas (sección 4 de la revisión)

**4.1 · El SPX inferido sigue identificado como inferido.**

Hecho:
- `SUBYACENTE` tiene la columna obligatoria `tipo_precio` (`observado` o `implicito`).
- El nivel por paridad se registra como `implicito`.
- Una corrida usa una sola fuente de precio objetivo.
- Tabla diaria, etiquetas, informe, gráficas y manifiesto dicen de dónde sale el precio. El texto ya
  no habla de «rendimientos de SPX» cuando el nivel es implícito.
- El alcance declara «precio objetivo inferido de las mismas opciones: no es independiente de las
  señales» y no permite evaluar con él.

Pendiente, y es decisión tuya: **qué precio independiente se predice**. Opciones:

| Opción | Ventaja | Costo o riesgo |
|---|---|---|
| SPY observado (SIP de Alpaca, consultable pasados 15 minutos) | Disponible ya, gratis e independiente del feed de opciones | Cambia el instrumento: dividendos trimestrales y diferencia de seguimiento frente a SPX. Hay que declararlo y evaluarlo. |
| SPX observado a las 09:45, de un proveedor externo | El objetivo natural de SPXW | Costo y licencia por confirmar; hoy no hay fuente en el entorno |
| Cierre oficial de SPX (FRED) | Gratis y público | Solo cierres: cambia el diseño 09:45→09:45 a cierre→cierre |

Mi recomendación: SPY observado como objetivo independiente del piloto, con etiquetas separadas
`retorno_spy_observado` y `retorno_spx_implicito`, y comparar las dos antes de cualquier evaluación.
La plomería de fuentes ya lo permite; faltan la captura del SIP a las 09:45 y la segunda serie de
etiquetas.

**4.2 · Hipótesis call/put.** De acuerdo: RR25 y la asimetría a distancia logarítmica simétrica
(`F·1.03`, `F/1.03`) son medidas de asimetría, no pares de paridad. El experimento es si su
**cambio** agrega información después de controlar movimiento previo, volatilidad y calidad. La
referencia externa del forward (curva de tasas con fuente) sigue pendiente. FRED y el Tesoro
responden desde el entorno.

**4.3 · Distribuciones y ruido.** De acuerdo, sin cambios de código en esta entrega: primero la
fuente validada, después cuantiles sobre soporte común, desplazamientos y Wasserstein frente a
baselines. La derivada debe quedar ausente cuando cambian el soporte identificado o el segmento de
medición (el piloto ya lo hace con el segmento).

**4.4 · Puntualidad.** Cambios en la plantilla del workflow (`ops/repo_datos/`):
- El código queda fijado al commit revisado `79c15549bacd71cec2bd60f1ac0888e9162019b3`.
- Cada paso de preparación tiene su límite (5 a 8 minutos), para que un primer disparo atascado
  libere al respaldo antes del corte. El trabajo completo tiene un límite de 75 minutos.
- Cada ejecución guarda en `raw/alpaca/ejecuciones/` el cron que la disparó, la hora de arranque, el
  margen hasta cada corte y el estado de cada hora.

Una corrida en verde no basta: la puntualidad se medirá con esos registros durante la prueba
operativa.

---

## 4. Estado del plan de continuación

| Orden | Trabajo | Estado |
|---|---|---|
| 1 | H1–H3, H5 y H8, con regresiones | Hecho (`79c1554`) |
| 2 | H4, H6 y H7 en el núcleo | Hecho (`79c1554`) |
| 3 | Precio objetivo y fuente independiente | Decisión pendiente (sección 3) |
| 4 | Prueba operativa de 3–5 sesiones | Espera el repositorio privado de datos con sus secretos. La revisión no pudo verlo (404) y la integración de Claude no puede crearlo. |
| 5 | Aptitud del feed | Sin OPRA, el sesgo de `indicative` queda declarado como desconocido; el alcance lo marca en cada informe |
| 6–8 | Piloto de medición, experimento predictivo y política simulada | Después de 3–5 |
