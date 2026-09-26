# QuantileFlow

Seguimiento de distribuciones implícitas en opciones y gestión diaria de posiciones.
**Versión de investigación (26 de septiembre de 2026).**

Este repositorio contiene, por ahora, la propuesta técnica del sistema, un núcleo matemático de
referencia con el que se generan sus figuras y el pipeline del piloto de medición (ingesta, controles,
etiquetas, informe y manifiesto). No hay datos de mercado, modelos entrenados ni resultados empíricos:
todas las figuras y la plantilla del informe usan datos **sintéticos** con semillas fijas.

## Documentos

- [`docs/plan_de_trabajo.md`](docs/plan_de_trabajo.md): plan de investigación vigente (26 de septiembre
  de 2026). Pregunta inicial, fases con criterios de salida y correcciones previas del núcleo.
- [`docs/avance_y_pendientes.md`](docs/avance_y_pendientes.md): qué se hizo, hallazgos y qué falta.
- [`docs/como_proseguir.md`](docs/como_proseguir.md): continuación del plan; el siguiente hito es un
  informe reproducible de sesiones reales de apertura (SPXW PM, 09:45, plazo constante de 30 días).
- [`docs/estado_continuacion.md`](docs/estado_continuacion.md): qué se construyó de ese plan sin datos,
  el problema de acceso a datos y lo que falta.
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
tests/                 pruebas de propiedades del núcleo, cuantiles, conformal, cadenas, contrato,
                       calendario, etiquetas, almacenamiento y piloto
configs/piloto.toml    configuración versionada del piloto (umbrales provisionales)
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
