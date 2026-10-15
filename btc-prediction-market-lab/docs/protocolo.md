# Protocolo de evidencia (Pasos 8 y 10)

**Fechado: 2026-10-15.** Escrito **antes** de cualquier prueba final. Lo que sigue se congela; si
cambia, la fecha y el motivo se registran y el test final pasa a desarrollo.

La hipótesis que debe poder rechazarse: **«La información disponible en el momento de decidir
permite obtener una ventaja sobre el precio ejecutable, después de costes y retrasos.»**

No hay metas de acierto, beneficio diario ni ingresos. El resultado admisible incluye `FAIL`.

---

## 1. Estados

| Estado | Significado |
| --- | --- |
| `DATA_ONLY` | **vigente.** Capacidades auditadas y capturador funcionando. Sin ventaja medida. |
| `RESEARCH` | hay datos suficientes y evaluación cronológica reproducible |
| `INCONCLUSIVE` | el resultado no permite afirmar ni descartar |
| `FAIL` | incumple criterios |
| `PAPER_VALIDATED` | superó la prueba final y el paper trading prospectivo |

Un resultado incierto se etiqueta `INCONCLUSIVE`; uno que incumple, `FAIL`. **Ninguno se convierte
en aprobación**, y no se buscan variantes indefinidamente.

## 2. Separación de datos

Los cortes se fijan **según cobertura y regímenes disponibles, antes de ajustar candidatos**, y se
registran aquí con su fecha. Las filas **no** se reparten al azar.

| Tramo | Uso |
| --- | --- |
| Entrenamiento | ajustar modelos y escaladores |
| Calibración | ajustar el calibrador; posterior al entrenamiento y anterior a validación |
| Validación | **seleccionar** entre candidatos |
| Final | **intacto**; se abre una sola vez |

Reglas que el código hace cumplir (`btclab/evaluacion.py`):

- **Purga por disponibilidad.** Una observación cuya etiqueta se publica dentro del tramo siguiente
  (o a menos de la separación temporal de su inicio) se marca `purgada` y no entra en ninguno.
- **Separación temporal** según horizonte y publicación de etiquetas. Valor inicial: **1800 s**.
- **Un contrato, un solo grupo.** `comprobar_sin_solapamiento` falla si un contrato aparece en dos
  tramos.
- **Walk-forward** durante el desarrollo: entrenar con pasado, calibrar con el pasado más reciente,
  evaluar el bloque siguiente.

## 3. Candidatos y control de selección

Máximo de candidatos antes del test final: **4**.

1. Referencia de mercado (punto medio de YES) — referencia de evaluación, no probabilidad.
2. No operar — referencia económica.
3. Modelo del subyacente (simulación de trayectorias, sin drift).
4. Logística regularizada.

Extensión admitida **solo si la validación demuestra una carencia concreta**: corrección
`logit(p) = logit(p_market) + g(features)`, comparada contra usar el mercado sin corregir sobre las
mismas observaciones. Cada variante probada se registra, incluidas las descartadas.

El ajuste por selección múltiple se declara con `ajuste_por_seleccion` y la cota se recalcula al
nivel ajustado.

## 4. Lo que se congela antes de abrir el tramo final

Modelo, variables, calibrador, momento de entrada, filtros de calidad, umbral de ventaja y límites.

| Parámetro | Valor inicial |
| --- | --- |
| Momento de decisión | 60 s después de abrir; una entrada máxima por contrato |
| Mantener hasta | liquidación |
| Margen operativo (EV conservador por contrato) | `0.02` |
| Antigüedad máxima del libro | `3.0 s` |
| Antigüedad máxima del spot | `10.0 s` |
| Spread máximo | `60` mils |
| Certeza máxima admitida | `0.995` |
| Extrapolación máxima (horizonte / ventana observada) | `3.0×` |
| Nivel de la banda | `0.90` |
| `alpha` de Kelly | `0.25` |
| Longitud de bloque | según dependencia **en entrenamiento** |

El momento de entrada es una elección para reducir grados de libertad, **no una señal validada**.
**No se escoge retrospectivamente el mejor minuto.** Una estrategia dinámica exige otro experimento,
con evaluación agrupada por contrato y control del riesgo acumulado de entradas sucesivas.

La sensibilidad al margen operativo se reporta; **la variante ganadora no se elige a posteriori**.

## 5. Criterios de avance

Para pasar de `RESEARCH`, **todos**:

1. **Reglas, costes y datos críticos verificados; replay reproducible.** Hoy falla: el estado es
   `COSTS_UNVERIFIED`.
2. **Cobertura suficiente** según los mínimos de `configs/captura.toml`, declarados antes de mirar
   los datos: 2000 observaciones por flujo y 200 contratos con resultado.
3. **Calibración y cobertura dentro de tolerancias**, con muestra suficiente por región usada:
   - ECE ≤ `0.03` sobre validación;
   - cobertura empírica de los intervalos al 50/80/95 % dentro de ±`0.07` del nominal;
   - ningún tramo con `n < 20` presentado como evidencia.
4. **Ventaja económica fuera de muestra, con costes y retraso.** Para afirmar evidencia de ventaja:
   **la cota inferior unilateral al 95 %, predefinida, del beneficio medio neto por día debe ser
   positiva**, calculada por bloques sobre la serie **diaria** y ajustada por selección.
5. **Estabilidad frente a estrés** y sin dependencia excesiva de un día, horario o régimen:
   - ningún día aporta más del `25 %` del beneficio neto total;
   - la cota sigue siendo positiva al excluir el mejor día;
   - la cota sigue siendo positiva en el escenario de retraso pesimista y con profundidad al `50 %`.
6. **Drawdown y exposición dentro de los límites configurados**, y todos los flujos de caja
   conciliados (incluidos cancelaciones y pagos especiales).

**Los días malos no se excluyen a posteriori.**

## 6. Estrés predefinido

| Escenario | Parámetros |
| --- | --- |
| Retraso optimista | datos 0.3 s, cálculo 0.2 s, acción humana 2 s |
| Retraso central | 1.0 / 0.5 / 8 s |
| Retraso pesimista | 3.0 / 1.0 / 25 s |
| Profundidad reducida | factor `0.5` y factor `0.2` |
| Costes superiores | constante de comisión ×`1.5` |
| Alta volatilidad | subconjunto del cuartil superior de volatilidad realizada |

Ninguno de los perfiles de retraso **está medido** (`medido = False`). Mientras no exista la
distribución de retrasos del flujo real, toda conclusión que dependa del retraso es **provisional**
y se etiqueta así. Las latencias de una API no sustituyen a las de un flujo manual.

## 7. Paper trading prospectivo

Se ejecuta **después** de congelar la estrategia. Su duración y muestra objetivo se calculan
**antes** de empezar, a partir de una ventaja mínima económicamente relevante, la variabilidad
observada y la dependencia entre contratos del mismo día. Un piloto corto solo verifica operación,
no valida ventaja.

**No se elige el día de parada cuando el P&L se vuelve positivo.** Si se desea revisión secuencial,
el método que controla ese seguimiento se define antes.

## 8. Degradación

La validez histórica puede degradarse. Se **suspenden nuevas señales** ante:

- datos roto: huecos, secuencias rotas, libro sin snapshot válido;
- desviación persistente de calibración (ECE por encima de la tolerancia en dos bloques seguidos);
- costes fuera del rango validado;
- observaciones fuera del dominio validado (extrapolación por encima del factor fijado);
- límites de riesgo agotados.

**La ejecución real queda fuera de este encargo.**

## 9. Registro de cambios del protocolo

| Fecha | Cambio | Motivo |
| --- | --- | --- |
| 2026-10-15 | versión inicial | creación del proyecto |
