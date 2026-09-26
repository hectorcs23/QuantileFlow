# QuantileFlow: avance, hallazgos y pendientes

**Fecha:** 26 de septiembre de 2026
**Rama:** `claude/compassionate-brown-1w9f90`
**Commits:** `e242668` (propuesta técnica y núcleo) y `0ad6e2b` (correcciones del plan de trabajo)

> Todo lo que sigue se obtuvo con datos **sintéticos**. Todavía no hay datos de mercado, evidencia
> predictiva ni resultados de rentabilidad. Las pruebas verifican que el código hace lo que dice; no
> que la señal exista.

---

## 1. Qué se hizo

### 1.1 Propuesta técnica y núcleo de referencia

- [Documento técnico](QuantileFlow_propuesta_tecnica.pdf): 76 páginas, 64 gráficas y 19 diagramas.
  Recorre el proceso etapa por etapa: datos y reconstrucción de Q, transporte, pronóstico, regímenes y
  confianza, decisión, evidencia, arquitectura y prioridades. La fuente LaTeX está en `propuesta/`.
- Paquete `quantileflow/` (numpy/scipy): SSVI con restricciones, Breeden–Litzenberger, Wasserstein,
  PCA funcional, Kalman, BOCPD, calibración, conformal adaptativo, regresión cuantílica, CVaR, Sharpe
  deflactado y walk-forward con purga.
- Figuras reproducibles con semillas fijas: `make figuras && make pdf`.

### 1.2 Plan de trabajo

- [plan_de_trabajo.md](plan_de_trabajo.md), agregado tal como se recibió.

### 1.3 Correcciones de la sección 6 del plan

| # | Lo que pedía el plan | Lo que se hizo | Dónde |
|---|---|---|---|
| 1 | No normalizar masa faltante ni silenciar densidades negativas; marcar colas «no identificadas». | La CDF se ancla con la pendiente del precio, sin normalizar ni recortar. Cada nivel devuelve «identificada», «no identificada» (sin valor) o «densidad inválida». | `quantileflow/distribuciones.py`, `superficies.cdf_logmoneyness` |
| 2 | Corregir `alfa >= 1` en el conformal adaptativo y comprobar la cota con secuencias límite. | Conjunto vacío con α_t ≥ 1 y completo con α_t ≤ 0. Estadístico de orden exacto. Un dato ausente no cuenta como error. Cota con retraso documentada y comprobada en cada prefijo. | `quantileflow/calibracion.py` |
| 3 | Pruebas de cadenas bid/ask con cotizaciones desfasadas, dividendos, strikes ausentes y ventanas de apertura. | Módulo nuevo de cadena cruda y 17 pruebas que cubren esos casos, además de opciones americanas y el corte. | `quantileflow/cadenas.py`, `tests/test_cadenas.py` |
| 4 | Series separadas de residuos observados y superficies ajustadas; documentar exclusiones. | El informe separa `obs_*` (crudo) de `aj_*` (ajustado). Cada fila excluida conserva todos sus motivos. | `cadenas.fila_informe`, `cadenas.ajustar_captura` |

Qué hace el módulo `cadenas.py`:

- **Captura inmutable.** Guarda una fila por actualización con bid, ask, tamaños y sello de tiempo, más
  subyacente sincronizado, tasa, dividendos, estilo de ejercicio, corte y fecha. Es la versión mínima
  del contrato de datos.
- **Controles por fila con motivo de exclusión.** Cotizaciones posteriores al corte, reemplazadas,
  anteriores a la apertura, dentro de la ventana de apertura, desfasadas, sin bid, cruzadas o
  bloqueadas, sin tamaño, con spread ancho y fuera de cotas.
- **Paridad del mismo strike.** El forward y el descuento de cada par se estiman sin ese par (mínimos
  cuadrados ponderados con recorte robusto). El residuo se da en precio y en múltiplos del ancho
  bid/ask, con su banda.
- **Ejercicio anticipado.** Desamericanización con árbol binomial y dividendo *escrowed*. El residuo de
  una americana solo se interpreta si supera la banda más las primas de ejercicio.
- **Asimetría call/put.** Strikes simétricos en logaritmo (F·e^{±ln 1.03}), con banda de sensibilidad
  bid/ask y razón de primas corregida por simetría put–call. Además, delta 25 y pendiente local de la
  sonrisa.
- **Cambios entre sesiones.** Registran días naturales, sesiones y tipo de comparación
  (apertura–apertura o cierre–apertura).

### 1.4 Documento actualizado

- §2.3, nueva: cadena cruda, con controles, tabla de motivos, paridad fuera de muestra, dividendos,
  ejercicio anticipado, asimetría y series separadas. Tiene dos figuras nuevas.
- §2.7: cuantiles con CDF anclada y estados de identificación.
- §5.4: la cota del conformal con retraso, las convenciones que la sostienen y el defecto corregido.
- Figuras de §3 y §5 regeneradas. Los cambios en §3 solo se notan a nivel de píxel.

### 1.5 Pruebas (114, todas pasan)

| Archivo | Pruebas | Qué cubre |
|---|---|---|
| `tests/test_nucleo.py` | 17 | SSVI, Breeden–Litzenberger, Wasserstein, FPCA, Kalman, BOCPD, CVaR, Sharpe, walk-forward, binomial |
| `tests/test_distribuciones.py` | 7 | Masa faltante con y sin ancla, densidad negativa, rango identificado, CDF analítica de SSVI |
| `tests/test_calibracion.py` | 73 | Cota del conformal en cada prefijo: empates, puntajes crecientes, alternancias, adversario, huecos y datos aleatorios |
| `tests/test_cadenas.py` | 17 | Desfasadas, dividendos, americanas, strikes ausentes, apertura y corte, estabilidad bid/ask, series separadas, calendario |

---

## 2. Hallazgos

### 2.1 Defectos del núcleo anterior (ya corregidos)

- **El conformal adaptativo no cumplía la cota que anunciaba.** Con α_t ≥ 1 devolvía un intervalo de
  ancho cero, que "cubre" cuando el puntaje es cero. Con `y = predicción`, α_t llegó a 3.07 y la tasa de
  error quedó en 0 en lugar de 0.10: desviación 0.10 frente a una cota de 0.031. Corregido, la tasa es
  0.070 y la desviación, 0.030, dentro de la cota.
- **Las pruebas aleatorias no lo detectaban.** El código anterior falla 14 de las 73 pruebas nuevas; las
  de datos aleatorios pasan con ambas versiones. Hacen falta secuencias límite.
- **El cuantil conformal tenía un desfase de un puesto.** Usaba el estadístico k+1 en vez del k. Con
  n = 20 y α = 0.10 cubría 95.2 % en lugar de 90.5 %. En la figura del §5.4, la cobertura de largo plazo
  del nivel fijo pasa de 89.8 % a 88.9 %.
- **Normalizar escondía masa faltante.** A una normal a la que le falta el 2.3 % de la masa izquierda,
  normalizar le desplaza la mediana 0.029 desviaciones típicas. El generador sintético ignoraba una masa
  izquierda de hasta 1.2e-5, con un efecto máximo de 2.2e-4 en log-moneyness: despreciable en las
  figuras, pero conceptualmente incorrecto.
- **El documento y el código se contradecían.** El documento decía que la masa faltante "no se
  redistribuye en silencio", y el código sí la redistribuía.

### 2.2 Lo que muestran las cadenas sintéticas

- **Una cotización desfasada parece una señal.** Tres puts de hace 5 minutos, con el subyacente 1 % más
  bajo, dan residuos de paridad de −0.6, −1.9 y −3.2 anchos bid/ask. Sin control de edad pasarían por
  señales. El forward fuera de muestra evita que contaminen a los demás pares, que quedan como máximo
  en 0.07 anchos.
- **Un dividendo omitido fabrica un residuo.** Un forward contractual sin el dividendo de 1.2 da un
  residuo de −1.2 en todos los strikes. El forward implícito de la paridad lo absorbe sin declararlo.
- **Tratar americanas como europeas sesga el forward sin que se note.** Con un dividendo, el forward sale
  en 99.03 frente a 98.83 (sesgo de 0.2), y ningún residuo sale de su banda (máximo 0.46 anchos): el
  error no se ve en los residuos. Desamericanizando, el forward sale en 98.8245 frente a 98.8260. Las
  primas de ejercicio quedan a menos de 0.02 de las verdaderas y llegan a 0.92 en el call de strike 90,
  antes del ex-dividendo.
- **La asimetría se recupera bien si hay strikes.** En ±ln 1.03, 5.79 puntos de volatilidad frente a
  5.76 verdaderos; en delta 25, 7.2 puntos; la pendiente local es −0.95. Sin los puts de 96 y 97, el
  tramo alrededor del objetivo de −3 % es demasiado ancho y la medida queda «no identificada» en lugar
  de extrapolarse.
- **Las primas brutas engañan si se comparan con 1.** Sin asimetría, P(F·e^{−d}) = e^{−d}·C(F·e^{d}).
  En el mundo sintético, el put a −3 % cuesta 78 % más que el call simétrico equivalente.
- **El ajuste borra el residuo de paridad.** En la superficie ajustada el residuo es 2e-14; en la serie
  observada, −1.12 anchos. Además, una sola cotización desviada deja 14 cotizaciones del ajuste fuera
  de bid/ask, porque la pérdida L2 no es robusta.
- **El historial no se filtra.** Las filas de preapertura, de la ventana de apertura y posteriores al
  corte no cambian ningún resultado.
- **Rendimiento.** Con la CDF normal de `scipy.special.ndtr` se obtienen los mismos resultados, y
  procesar una captura europea baja de 0.24 s a 0.015 s. Una cadena americana de 42 opciones tarda unos
  2 s por el árbol binomial.

### 2.3 Observaciones sobre el plan

- **Los strikes a ±3 % en términos simples no son simétricos en logaritmo.** Se usaron strikes
  F·e^{±ln 1.03}, y las primas se comparan contra e^{−d}, no contra 1.
- **El residuo de paridad en un índice probablemente sirva más como control de calidad que como
  señal.** La evidencia de Cremers y Weinbaum es de sección cruzada en acciones individuales. Conviene
  fijar expectativas antes de mirar datos.
- **La potencia estadística es baja.** Con un subyacente, un año aporta unas 50 observaciones
  independientes a 5 sesiones. Es poco para detectar mejoras pequeñas en Brier o pérdida cuantílica.
- **A la apertura, el spot de SPX es menos fiable que el forward implícito.** En los primeros minutos,
  el valor del índice puede incluir componentes que aún no han abierto.

---

## 3. Qué falta

### 3.1 Decisiones del usuario (bloquean la fase 0)

- [ ] Proveedor y presupuesto de datos, con la latencia adecuada para decidir a las 09:45.
- [ ] Instrumento: SPX (europeo) o SPY (americano con dividendos). Si es SPX, elegir entre SPX (AM) y
      SPXW (PM) y medir el plazo en horas.
- [ ] Posiciones actuales y moneda del capital de referencia.
- [ ] Costos de negociación y límites de riesgo.

### 3.2 Fase 0: datos

- [ ] Obtener una muestra histórica de cadenas de apertura con bid/ask, tamaños, sellos, subyacente
      sincronizado, tasas y dividendos.
- [ ] Auditar cobertura, latencia, huecos y costo de la fuente.
- [ ] Ingesta: convertir la hora a Nueva York con horario de verano y guardar snapshots inmutables
      (definir formato y almacenamiento).
- [ ] Fijar los umbrales de `ReglasCalidad` con la muestra. Hoy son provisionales: 60 s de edad máxima,
      5 min de ventana de apertura y spread de hasta el 50 % del mid.
- [ ] Definir fuentes de calendario de feriados, curva de tasas (o tasa implícita de la paridad) y
      calendario de dividendos (SPY).

### 3.3 Primer entregable: informe de sesiones de apertura

Ya existe:

- El cálculo por sesión: primas y volatilidades call/put comparables, residuo de paridad con banda,
  exclusiones y alertas (`procesar_captura`, `fila_informe`).
- Los cambios entre sesiones con calendario (`diferencia_diaria`).

Falta:

- [ ] Conectar la ingesta de datos reales.
- [ ] Construir las etiquetas de rendimiento a 1 y 5 sesiones, usadas solo después de madurar.
- [ ] Generar el informe reproducible (tabla diaria y gráficas).
- [ ] Revisar la muestra y congelar el protocolo del backtest amplio.

### 3.4 Mejoras técnicas del núcleo

- [ ] Pérdida robusta en el ajuste de superficie (por ejemplo, `soft_l1`): hoy una cotización desviada
      desplaza a muchas.
- [ ] Acelerar la desamericanización (vectorizar el árbol o reutilizar volatilidades) para cadenas SPY
      completas.
- [ ] Calibrar con SPY real el umbral de interpretación de americanas (banda más ambas primas de
      ejercicio), que es conservador.
- [ ] Fijar la convención de delta (forward o spot, con o sin descuento) según el instrumento.
- [ ] Cuando se use el conformal, reportar la fracción de intervalos vacíos o infinitos: cumplen la cota
      pero no informan.
- [ ] Agregar pruebas de regresión con cadenas reales guardadas cuando exista la muestra.

### 3.5 Fases siguientes del plan

- [ ] **Fase 2, prueba predictiva:** escalera A → E, walk-forward con purga, bootstrap por bloques y
      Brier, log loss, pérdida cuantílica y CRPS. Los bloques existen en `pronostico.py`,
      `calibracion.py` y `evidencia.py`; falta el flujo completo.
- [ ] **Fase 3:** comparar distribuciones y transporte contra las señales simples.
- [ ] **Fase 4:** traducir los pronósticos a mantener, reducir o aumentar, con costos y límites
      (`decision.py`), frente a mantener y a control de volatilidad.
- [ ] **Fase 5:** operación simulada con informe diario y registro reproducible.

---

## 4. Cómo reproducir

```bash
pip install -r requirements.txt
make test      # 114 pruebas
make figuras   # 64 figuras PNG
make pdf       # docs/QuantileFlow_propuesta_tecnica.pdf
```
