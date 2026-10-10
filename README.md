# QuantileFlow

Seguimiento de distribuciones implícitas en opciones y gestión diaria de posiciones.
**Versión de investigación; avances experimentales al 10 de octubre de 2026.**

Este repositorio contiene la propuesta técnica del sistema, un núcleo matemático de referencia con el
que se generan sus figuras, el pipeline del piloto de medición (ingesta, controles, etiquetas, informe
y manifiesto) y la captura diaria de cadenas de opciones en Alpaca. Los datos de mercado no están en
Git. Hay revisiones operativas y experimentos descriptivos de capturas reales, pero aún no hay un
predictor validado. Las figuras de la propuesta, la plantilla del informe y los benchmarks PDE
usan datos **sintéticos**.

## Documentos

- [`docs/VALORACION_CONSISTENTE_2026-10-10.md`](docs/VALORACION_CONSISTENTE_2026-10-10.md):
  valoración de calls/puts desde la misma PDF, identidades por strike, sensibilidades y convergencia.

- [`docs/SENSIBILIDAD_DISTRIBUCION_2026-10-09.md`](docs/SENSIBILIDAD_DISTRIBUCION_2026-10-09.md):
  PDF, CDF, cuantiles y colas; tangentes y adjuntos, verificación y gráficos con presupuesto de datos US$0.
- [`docs/AVANCE_PDE_GRATIS_2026-10-09.md`](docs/AVANCE_PDE_GRATIS_2026-10-09.md): primer benchmark
  europeo de precios y sensibilidades, integridad del crudo y prueba aislada de captura ampliada.

- [`docs/plan_de_trabajo.md`](docs/plan_de_trabajo.md): plan de investigación vigente (26 de septiembre
  de 2026). Pregunta inicial, fases con criterios de salida y correcciones previas del núcleo.
- [`docs/avance_y_pendientes.md`](docs/avance_y_pendientes.md): qué se hizo, hallazgos y qué falta.
- [`docs/como_proseguir.md`](docs/como_proseguir.md): continuación del plan; el siguiente hito es un
  informe reproducible de sesiones reales de apertura (SPXW PM, 09:45, plazo constante de 30 días).
- [`docs/estado_continuacion.md`](docs/estado_continuacion.md): qué se construyó de ese plan sin datos,
  el problema de acceso a datos y lo que falta.
- [`docs/resumen_sesion_alpaca.md`](docs/resumen_sesion_alpaca.md): resumen de la sesión con Alpaca y
  mapa de dónde está cada archivo.
- [`docs/respuesta_revision_e2b92f0.md`](docs/respuesta_revision_e2b92f0.md): los ocho hallazgos de la
  revisión del commit `e2b92f0`, sus correcciones y pruebas de regresión, y las decisiones
  metodológicas pendientes.
- [`docs/aceptacion_operacion.md`](docs/aceptacion_operacion.md): la aceptación de la operación, sesión
  por sesión. El lunes 28 GitHub no disparó los workflows programados, y la sesión se perdió.
- [`docs/respuesta_verificacion_instalacion.md`](docs/respuesta_verificacion_instalacion.md): la
  verificación independiente de la instalación y el mantenimiento de las plantillas antes del 19 de
  octubre (`ubuntu-24.04`).
- [`docs/instalacion_repo_datos.md`](docs/instalacion_repo_datos.md): la instalación del repositorio de
  datos y su prueba manual, verificadas, y lo que falta para la aceptación.
- [`docs/respuesta_verificacion_4ffde8a.md`](docs/respuesta_verificacion_4ffde8a.md): la verificación de
  `4ffde8a` (queda fijado en los workflows) y la secuencia para acreditar la captura diaria.
- [`docs/respuesta_cambios_operativos.md`](docs/respuesta_cambios_operativos.md): el registro de la
  captura también cuando falla al iniciar, `--resoluciones` explícito y pruebas portables a Windows.
- [`docs/respuesta_cierre_b240dc2.md`](docs/respuesta_cierre_b240dc2.md): después del cierre de la
  revalidación: el registro de cada ejecución a prueba de errores, la revisión de la operación de las
  primeras sesiones y cómo seguir con la prueba de captura.
- [`docs/respuesta_revalidacion_5c15028.md`](docs/respuesta_revalidacion_5c15028.md): la revalidación
  de `5c15028`: un dividendo recibido sin fecha ex o sin monto deja pendientes las etiquetas que podría
  afectar, hasta que el proveedor lo complete o una resolución dé los datos.
- [`docs/respuesta_revalidacion_a5e2748.md`](docs/respuesta_revalidacion_a5e2748.md): la revalidación
  de `a5e2748`: discrepancias de dividendos que solo resuelve evidencia fechada, cobertura con los
  filtros de cada consulta, tramos de etiqueta con el estado de cada instante (provisional, aceptada
  bajo la política de 60 días, pendiente) y el respaldo como escenario favorable.
- [`docs/respuesta_revision_8c97b2b.md`](docs/respuesta_revision_8c97b2b.md): la revisión de `8c97b2b`:
  cobertura de dividendos aparte, eventos y etiquetas versionados, plazo de preparación del respaldo y
  correcciones a la entrega anterior.
- [`docs/respuesta_revalidacion_d815bdd.md`](docs/respuesta_revalidacion_d815bdd.md): la entrega que
  pidió la revalidación de `d815bdd`: señal, referencia y objetivo separados; SPY del SIP histórico
  con dividendos; recuperación de capturas interrumpidas y workflows por hora.
- [`docs/fuente_alpaca.md`](docs/fuente_alpaca.md): qué ofrece Alpaca (verificado el 26 de septiembre
  de 2026), la captura diaria hacia adelante, la primera verificación con datos reales y las decisiones
  pendientes (dónde corre la captura y qué feed usar).
- `docs/QuantileFlow_propuesta_tecnica.pdf`: guía técnica del proceso, etapa por etapa, con 64 gráficas
  y 21 diagramas. Su sección 11 resume el estado del proyecto al 28 de septiembre de 2026: qué se
  construyó, la captura diaria instalada, las revisiones y lo que falta. El PDF y las figuras PNG son
  artefactos generados: `make figuras && make pdf` los regenera.
- Fuente LaTeX en [`docs/propuesta/`](docs/propuesta/): `main.tex`, `preambulo.tex`, una sección por
  archivo en `secciones/` y los diagramas TikZ en `diagramas/`.

Contenido: producto e hipótesis; datos y reconstrucción de Q (cadena cruda con controles, paridad y
asimetría call/put; SSVI, desamericanización, Breeden–Litzenberger, bandas); transporte, dinámica e
innovación (W1/W2, PCA funcional, Kalman); de Q a P (regresión cuantílica, combinación); regímenes y
confianza (BOCPD, calibración, conformal adaptativo, abstención); decisión (escenarios conjuntos, CVaR,
zona de no operación, robustez, MPC); protocolo de evidencia; arquitectura y operación diaria; secuencia
de construcción y prioridades.

## Estructura

```
quantileflow/          núcleo de referencia (numpy, scipy, pandas)
  calendario.py        calendario bursátil real (XNYS), instantes UTC, liquidación AM/PM, plazo ACT/365
  contrato.py          esquema normalizado de cotizaciones y subyacente, validador, símbolos OCC,
                       adaptador de tablas a capturas
  cadenas.py           captura cruda inmutable, controles con motivos de exclusión, paridad del
                       mismo strike con forward fuera de muestra, desamericanización, asimetría
                       call − put (distancia logarítmica, RR25, pendiente), métricas de calidad
  etiquetas.py         rendimientos a 1 y 5 sesiones con decision_at, label_end_at, label_available_at;
                       rendimiento total (dividendos en su fecha ex) y de precio
  piloto.py            plazo constante de 30 días, tabla diaria, cambios, estabilidad y dictamen;
                       señal (SPXW), referencia de las opciones (regla puntual) y objetivo (regla histórica)
  informe.py           tabla exportable, gráficas e informe Markdown del piloto
  corrida.py           corrida reproducible con manifiesto de hashes
  almacen.py           crudo inmutable, Parquet, manifiestos y huella del entorno
  alpaca.py            adaptador de Alpaca: cliente, crudo inmutable por respuesta, diario y manifiesto por
                       captura, recuperación, plazo absoluto, histórico SIP, dividendos, elección de
                       vencimientos y normalización al contrato
  implicito.py         nivel implícito del subyacente por paridad (Alpaca no da el nivel de SPX)
  diagnostico.py       diagnóstico de capturas: elegibilidad estricta al corte y calidad del feed
  operacion.py         revisión de la operación: estado de cada corte, puntualidad, respaldo, SIP y dividendos
  opciones.py          Black, griegas, árbol binomial con dividendos
  pde.py               difusión europea de referencia y adjunto discreto de precios
  distribucion_pde.py  PDF/CDF reconstruidas, cuantiles, colas y sensibilidades de distribuciones Q
  superficies.py       SSVI con restricciones, función g, CDF anclada, ajuste convexo en precios
  distribuciones.py    Breeden–Litzenberger, controles, cuantiles con estado de identificación
  transporte.py        Wasserstein en 1-D, cambios firmados, PCA funcional, reordenamiento
  filtrado.py          Kalman con ruido de observación variable, EWMA, persistencia
  regimenes.py         BOCPD y detector por umbral
  calibracion.py       pinball, CRPS, Brier, fiabilidad, conformal adaptativo con cota verificada
  pronostico.py        regresión cuantílica regularizada (programa lineal)
  decision.py          programa lineal con CVaR, costos y presupuesto de riesgo
  evidencia.py         Sharpe deflactado, bootstrap por bloques, walk-forward con purga
  sintetico.py         generadores del mundo sintético de las figuras
tests/                 pruebas de propiedades del núcleo, cuantiles, conformal, cadenas, contrato,
                       calendario, etiquetas, almacenamiento, piloto y adaptador de Alpaca (sin red)
configs/piloto.toml    configuración versionada del piloto (umbrales provisionales)
configs/captura_alpaca.toml  qué, cuándo y con qué feed se captura en Alpaca
ops/repo_datos/        plantilla del repositorio privado de datos: workflows por hora de captura, histórico
                       SIP y README
scripts/               piloto con datos normalizados, plantilla sintética, registro del entorno, captura,
                       histórico, normalización, verificación y revisión de la operación de Alpaca
reports/               informes generados (no se editan a mano) y registros de verificación
docs/propuesta/        fuente LaTeX, diagramas, scripts de figuras y figuras PNG
```

## Reproducir

```bash
pip install -r requirements.txt   # o requirements-bloqueo.txt para las versiones exactas verificadas
make test               # pruebas
make figuras            # regenera las figuras PNG (matplotlib, estilo por defecto)
make pdf                # compila el documento y lo copia a docs/QuantileFlow_propuesta_tecnica.pdf
make verificar          # registra commit, entorno y resultado de las pruebas en reports/verificacion/
make piloto-sintetico   # plantilla del informe piloto con datos sintéticos en reports/piloto_sintetico/
```

Captura en Alpaca (requiere `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY` en el entorno; ver
[`docs/fuente_alpaca.md`](docs/fuente_alpaca.md)):

```bash
make captura-prueba                                   # captura inmediata de prueba
make captura                                          # día hábil: espera y captura a las 09:45 y 10:00 ET
make historico-alpaca                                 # SIP de SPY en cada corte (pasados 15 min) y dividendos
make verificar-alpaca FECHA=2026-09-28                # elegibilidad y calidad en reports/verificacion_alpaca/
make normalizar-alpaca DESDE=2026-09-28 HASTA=2026-11-13   # tablas para el piloto desde el crudo
```

Con datos reales normalizados (esquemas de `quantileflow/contrato.py`). El objetivo es SPY del SIP
histórico, con dividendos:

```bash
N=data/normalized/alpaca
python scripts/piloto.py --cotizaciones $N/cotizaciones.parquet --subyacente $N/subyacente.parquet \
    --dividendos $N/dividendos.parquet --cobertura-dividendos $N/cobertura_dividendos.parquet \
    --fuente-objetivo alpaca/sip --desde AAAA-MM-DD --hasta AAAA-MM-DD
```

`data/` queda fuera de Git (licencias y tamaño; este repositorio es público): `data/raw/` guarda los
archivos originales, inmutables y direccionados por su SHA-256; `data/normalized/`, las tablas Parquet. Cada corrida escribe un `manifiesto.json` con los
hashes de entradas y salidas, la configuración, el commit y las exclusiones.

`make pdf` requiere una distribución de TeX con `latexmk`, `tikz`, `tcolorbox`, `mathpazo` y
`babel-spanish` (por ejemplo, TeX Live con los paquetes `latex-extra`, `fonts-recommended`,
`lang-spanish`, `science` y `pictures`).

## Alcance de las pruebas

Las pruebas usan datos sintéticos. Comprueban propiedades matemáticas y que el procesamiento de cadenas
bid/ask separa efectos de los datos (cotizaciones desfasadas, dividendos, ejercicio anticipado, strikes
ausentes, ventanas de apertura) de una posible señal. No demuestran validez predictiva ni la calidad de
datos reales: eso exige la muestra histórica de la fase 0 del plan de trabajo.
