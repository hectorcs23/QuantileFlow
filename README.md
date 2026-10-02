# QuantileFlow

Seguimiento de distribuciones implícitas en opciones y gestión diaria de posiciones.
**Versión de investigación (26 de septiembre de 2026).**

Este repositorio contiene, por ahora, la propuesta técnica del sistema, un núcleo matemático de
referencia con el que se generan sus figuras, el pipeline del piloto de medición (ingesta, controles,
etiquetas, informe y manifiesto) y un segundo subproyecto, `estrategias/`, que convierte la
distribución implícita en una decisión sobre puts. No hay datos de mercado, modelos entrenados ni
resultados empíricos: todas las figuras y las plantillas de informe usan datos **sintéticos** con
semillas fijas.

## Subproyectos

1. **Medición** (`quantileflow/`): reconstruir `Q` a partir de la cadena y medir su dinámica con
   controles y abstención. Es la base.
2. **Estrategias con puts** (`estrategias/`): dada `Q` y una vista `P` declarada explícitamente,
   decidir si vender puts, comprarlos o no operar, con las mismas reglas de identificación y
   abstención. Ver [`docs/estrategias_con_puts.md`](docs/estrategias_con_puts.md).

## Documentos

- [`docs/plan_de_trabajo.md`](docs/plan_de_trabajo.md): plan de investigación vigente (26 de septiembre
  de 2026). Pregunta inicial, fases con criterios de salida y correcciones previas del núcleo.
- [`docs/avance_y_pendientes.md`](docs/avance_y_pendientes.md): qué se hizo, hallazgos y qué falta.
- [`docs/como_proseguir.md`](docs/como_proseguir.md): continuación del plan; el siguiente hito es un
  informe reproducible de sesiones reales de apertura (SPXW PM, 09:45, plazo constante de 30 días).
- [`docs/estado_continuacion.md`](docs/estado_continuacion.md): qué se construyó de ese plan sin datos,
  el problema de acceso a datos y lo que falta.
- [`docs/estrategias_con_puts.md`](docs/estrategias_con_puts.md): el subproyecto de decisión. Por qué
  bajo `Q` ninguna estructura tiene ventaja, por qué la ventaja de vender un put de strike `K` es
  exactamente `D * int_0^K (F_Q - F_P) ds`, y qué hace falta para que una vista alcista justifique
  vender puts en vez de comprar el subyacente o una call.
- `docs/QuantileFlow_propuesta_tecnica.pdf`: guía técnica del proceso, etapa por etapa, con 64 gráficas
  y 19 diagramas. El PDF y las figuras PNG son artefactos generados: `make figuras && make pdf` los
  regenera.
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
  etiquetas.py         rendimientos a 1 y 5 sesiones con decision_at, label_end_at, label_available_at
  piloto.py            plazo constante de 30 días, tabla diaria, cambios, estabilidad y dictamen
  informe.py           tabla exportable, gráficas e informe Markdown del piloto
  corrida.py           corrida reproducible con manifiesto de hashes
  almacen.py           crudo inmutable, Parquet, manifiestos y huella del entorno
  opciones.py          Black, griegas, árbol binomial con dividendos
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
estrategias/           subproyecto de decisión sobre puts (usa el núcleo anterior)
  distribucion.py      distribución discreta sobre malla logarítmica común, CDF, cuantiles, KL
  vista.py             construcción de P deformando Q: tilt de media y momentos (mínima entropía),
                       desplazamiento, reponderación de cola, mezcla de escenarios, desde cuantiles
  estructuras.py       patas y pagos: put corto y largo, spreads, call, reversal, collar, forward
  precios.py           cotización por pata, paridad para la pata que falta, ejecución adversa
  evaluacion.py        ventaja como D*(E_P - E_Q), identidad por tramos de CDF, CVaR, equilibrio,
                       capital, y la parte de la ventaja que depende de la cola no identificada
  robustez.py          perturbaciones de vista, de Q y de ejecución; ventaja de peor caso
  recomendacion.py     puertas globales, zona de no operación, puntuación y dictamen
  informe.py           tabla de candidatas, gráficas e informe Markdown
  corrida.py           corrida reproducible con manifiesto (la vista entra en el manifiesto)
  sintetico.py         mundo sintético y dos reconstrucciones independientes de Q
tests/                 pruebas de propiedades del núcleo, cuantiles, conformal, cadenas, contrato,
                       calendario, etiquetas, almacenamiento, piloto y estrategias
configs/piloto.toml    configuración versionada del piloto (umbrales provisionales)
configs/estrategias.toml  reglas de decisión versionadas (umbrales provisionales)
scripts/               piloto con datos normalizados, plantilla sintética y registro del entorno
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
make estrategias-sinteticas  # informes de decisión sobre puts en reports/estrategias_sintetico/
```

Con datos reales normalizados (esquemas de `quantileflow/contrato.py`):

```bash
python scripts/piloto.py --cotizaciones data/normalized/cotizaciones.parquet \
    --subyacente data/normalized/subyacente.parquet --desde AAAA-MM-DD --hasta AAAA-MM-DD
```

`data/` queda fuera de Git: `data/raw/` guarda los archivos originales, inmutables y direccionados por
su SHA-256; `data/normalized/`, las tablas Parquet. Cada corrida escribe un `manifiesto.json` con los
hashes de entradas y salidas, la configuración, el commit y las exclusiones.

`make pdf` requiere una distribución de TeX con `latexmk`, `tikz`, `tcolorbox`, `mathpazo` y
`babel-spanish` (por ejemplo, TeX Live con los paquetes `latex-extra`, `fonts-recommended`,
`lang-spanish`, `science` y `pictures`).

## Alcance de las pruebas

Las pruebas usan datos sintéticos. Comprueban propiedades matemáticas y que el procesamiento de cadenas
bid/ask separa efectos de los datos (cotizaciones desfasadas, dividendos, ejercicio anticipado, strikes
ausentes, ventanas de apertura) de una posible señal. No demuestran validez predictiva ni la calidad de
datos reales: eso exige la muestra histórica de la fase 0 del plan de trabajo.

En `estrategias/` comprueban además el invariante que sostiene el subproyecto —con `P = Q` la ventaja
de toda estructura es exactamente cero—, la identidad entre la ventaja de un put y la integral de la
diferencia de distribuciones acumuladas, y que las reglas de abstención se activan cuando la vista se
aparta demasiado de `Q`, cuando la ventaja no cubre la ejecución o cuando procede de strikes sin
cotizaciones utilizables. Que una vista acierte no es comprobable con datos generados por el propio
código, y las pruebas no lo intentan.
