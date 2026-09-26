# QuantileFlow

Seguimiento de distribuciones implícitas en opciones y gestión diaria de posiciones.
**Versión de investigación (26 de septiembre de 2026).**

Este repositorio contiene, por ahora, la propuesta técnica del sistema y un núcleo matemático de
referencia con el que se generan sus figuras. No hay datos de mercado, modelos entrenados ni
resultados empíricos: todas las figuras usan datos **sintéticos** con semillas fijas.

## Documentos

- [`docs/plan_de_trabajo.md`](docs/plan_de_trabajo.md): plan de investigación vigente (26 de septiembre
  de 2026). Pregunta inicial, fases con criterios de salida y correcciones previas del núcleo.
- [`docs/avance_y_pendientes.md`](docs/avance_y_pendientes.md): qué se hizo, hallazgos y qué falta.
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
quantileflow/          núcleo matemático de referencia (numpy/scipy)
  cadenas.py           captura cruda inmutable, controles con motivos de exclusión, paridad del
                       mismo strike con forward fuera de muestra, desamericanización, asimetría
                       call/put (±k log-simétrico, delta 25, pendiente), informe observado/ajustado
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
tests/                 pruebas de propiedades del núcleo, cuantiles, conformal y cadenas bid/ask
docs/propuesta/        fuente LaTeX, diagramas, scripts de figuras y figuras PNG
```

## Reproducir

```bash
pip install -r requirements.txt
make test      # pruebas del núcleo
make figuras   # regenera las figuras PNG (matplotlib, estilo por defecto)
make pdf       # compila el documento y lo copia a docs/QuantileFlow_propuesta_tecnica.pdf
```

`make pdf` requiere una distribución de TeX con `latexmk`, `tikz`, `tcolorbox`, `mathpazo` y
`babel-spanish` (por ejemplo, TeX Live con los paquetes `latex-extra`, `fonts-recommended`,
`lang-spanish`, `science` y `pictures`).

## Alcance de las pruebas

Las pruebas usan datos sintéticos. Comprueban propiedades matemáticas y que el procesamiento de cadenas
bid/ask separa efectos de los datos (cotizaciones desfasadas, dividendos, ejercicio anticipado, strikes
ausentes, ventanas de apertura) de una posible señal. No demuestran validez predictiva ni la calidad de
datos reales: eso exige la muestra histórica de la fase 0 del plan de trabajo.
