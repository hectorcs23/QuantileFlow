# Protocolo predictivo

**Versión:** 1, congelada el 6 de noviembre de 2026 en el commit que agrega este archivo.
**Base:** [cómo proseguir](como_proseguir.md), sección 7, y el piloto con `piloto-0.4`
([revisión](revision_piloto.md), sección 0).

Este documento fija la prueba antes de mirar resultados. Nada de lo que sigue cambia sin una versión
nueva, con fecha y motivo, y solo antes de la mirada intermedia (sección 7). Los problemas de datos, como
una hora que no se pudo capturar, no cambian el protocolo: se informan.

## 1. Pregunta

¿El cambio diario de la asimetría de SPXW a la apertura (RR25 a 30 días, a las 09:45 de Nueva York) ayuda
a predecir si SPY sube o baja hasta la apertura siguiente, más allá de lo que ya dicen los precios
pasados, el nivel de volatilidad y el nivel de la asimetría?

## 2. Muestras

| Muestra | Sesiones | Uso |
|---|---|---|
| Desarrollo | Hasta el viernes 6 de noviembre de 2026 | Se vio: el informe piloto muestra el cambio de RR25 junto al rendimiento siguiente de SPY. Sirve como historia para entrenar y para depurar el código. **No se puntúa.** |
| Confirmatoria | Desde el lunes 9 de noviembre de 2026 | Se puntúa. Nadie mira su relación entre señal y rendimiento antes de las miradas de la sección 7. |

Para cuidar la muestra confirmatoria, el informe piloto no se vuelve a correr con sesiones posteriores al
6 de noviembre antes de la mirada intermedia. La calidad de los datos se sigue con
`verificar_alpaca.py` y `revisar_operacion.py`, que no muestran rendimientos.

## 3. Unidad, objetivo y variables

**Unidad.** Una sesión `t` del calendario XNYS. La decisión se toma en el corte de las 09:45 (latencia 0,
como en `piloto-0.4`). Todas las variables usan solo información con evento no posterior al corte.

**Objetivo principal.** `y_t = 1` si el rendimiento total logarítmico de SPY entre las 09:45 de `t` y las
09:45 de la sesión siguiente es mayor que 0; si no, `y_t = 0`. Es `ret_1_objetivo` del piloto: SIP de
Alpaca, mid de la última cotización válida, regla histórica, dividendos en su fecha ex. Para puntuar se usa
la versión aceptada de la etiqueta (política de 60 días).

**Variables**, medidas a las 09:45 de `t` con `piloto-0.4`:

| Variable | Definición | Estado |
|---|---|---|
| `r1` | Rendimiento logarítmico del SPX implícito desde las 09:45 de la sesión anterior (`retorno_previo_referencia`) | Existe |
| `vol10` | Desviación estándar de `r1` en las 10 sesiones anteriores con dato (mínimo 7) | A implementar |
| `lunes` | 1 si pasaron 3 o más días naturales desde la sesión anterior (`dias_naturales_desde_anterior`) | Existe |
| `iv_atm` | Volatilidad implícita en `k = ln(K/F) = 0`, interpolada a 30 días en varianza total, como el RR25 | A implementar |
| `d_iv_atm` | Cambio de `iv_atm` frente a la sesión anterior, a la misma hora y plazo | A implementar |
| `rr25` | RR25 a 30 días | Existe |
| `d_rr25` | Cambio diario del RR25 (`cambio_rr25`) | Existe |
| `res_par` | Residuo de paridad: `paridad_mediana_multiplo` | Existe |

No hay variable de gap: la captura no tiene el cierre anterior. `r1` ya incluye la noche.

## 4. Variantes

Una escalera, con la misma familia de modelo y el mismo ajuste en todos los escalones:

| Variante | Variables |
|---|---|
| Clima | Ninguna: la frecuencia de subidas del entrenamiento |
| A | `r1`, `vol10`, `lunes` |
| B | A + `iv_atm`, `d_iv_atm` |
| C | B + `rr25` |
| D | C + `d_rr25` |
| E | D + `res_par` (secundaria) |

**Comparación principal: D frente a C.** Mide lo que agrega el cambio del RR25 cuando ya están su nivel,
la volatilidad y los precios pasados.

## 5. Modelo y ventana

- **Modelo.** Regresión logística con penalización L2 de fuerza fija (`C = 1` en la convención de
  scikit-learn), sobre variables estandarizadas con la media y la desviación del entrenamiento. El
  intercepto no se penaliza. No hay búsqueda de hiperparámetros.
- **Ventana.** Expansiva, con un ajuste por sesión. Para predecir `t` se entrena con las sesiones `s` que
  tienen todas las variables de la variante y cuya etiqueta estaba disponible en la decisión
  (`label_available_at` ≤ decisión de `t`), con la versión de la etiqueta vigente en ese momento. En la
  práctica, la última sesión de entrenamiento es `t − 2`.
- **Mínimo.** 20 sesiones de entrenamiento. Con menos, la sesión no se puntúa en ninguna variante.
- **Misma muestra.** Todas las variantes se puntúan en las mismas sesiones: las confirmatorias con todas
  las variables de D, entrenamiento suficiente y etiqueta aceptada. La variante E se informa en su propia
  muestra.

## 6. Métrica e inferencia

- **Métrica principal.** Puntaje de Brier, `(p − y)²`. Por sesión, `d_t = Brier_C − Brier_D`: positivo
  significa que D predijo mejor.
- **Inferencia.** Bootstrap por bloques circulares de la media de `d_t`: bloques de 5 sesiones, 10 000
  réplicas, semilla `20261106`.

## 7. Miradas

Solo dos, contadas en sesiones confirmatorias puntuables:

| Mirada | Cuándo | Se concluye «mejora direccional» si |
|---|---|---|
| Intermedia | Con 125 sesiones | La cota inferior unilateral al 99.9 % de la media de `d_t` es mayor que 0. Si no, se sigue sin mirar más |
| Final | Con 250 sesiones | La cota inferior unilateral al 95 % es mayor que 0 |

Con unas 21 sesiones por mes y 60 días para aceptar las etiquetas, la mirada intermedia caería hacia julio
de 2027 y la final hacia enero de 2028. Cada hora perdida las corre.

**Resultados posibles en la mirada final:**

1. **Mejora direccional:** la cota de la tabla es mayor que 0.
2. **Ausencia de mejora detectable:** el intervalo bilateral al 90 % queda entero por debajo de 0.002. Ese
   umbral se fija ahora: equivale, por ejemplo, a probabilidades que se mueven 5 puntos alrededor del 50 %
   y aciertan la dirección el 55 % de las veces.
3. **Mejora exclusiva de riesgo:** sin mejora direccional, pero con mejora en el objetivo de riesgo
   (sección 8), con cota inferior unilateral al 99 % mayor que 0.
4. **Evidencia insuficiente:** ninguno de los anteriores.

**Lo que se puede detectar.** Si las probabilidades de C y D difieren unos ±0.03 por sesión, la
desviación de `d_t` es del orden de 0.03 y el error estándar de su media con 250 sesiones, de unos 0.002.
La prueba ve mejoras de unas 0.004 o más. Una señal más débil terminará, casi seguro, en «evidencia
insuficiente». Ningún resultado obliga a adoptar otro modelo.

## 8. Análisis secundarios

Exploratorios: se informan todos, con sus intervalos, y ninguno cambia el resultado de la sección 7.

- La escalera completa: clima → A → B → C → D → E, cada paso con su intervalo.
- **Objetivo de riesgo:** `y = 1` si el rendimiento siguiente cae por debajo del percentil 20 de los
  rendimientos del entrenamiento. Misma comparación D frente a C.
- Horizonte de 5 sesiones, con etiquetas solapadas y bloques de 10.
- El corte de las 10:00 en lugar del de las 09:45.
- Rendimiento de precio en lugar del total.
- Pérdida logarítmica, calibración por deciles y acierto de la dirección.
- Por régimen: `vol10` arriba y abajo de su mediana de entrenamiento.

## 9. Registro

Cada corrida, de desarrollo o confirmatoria, se anota en `reports/protocolo/registro.md`: fecha, commit,
muestra y variantes. Las de desarrollo no publican métricas de desempeño; las confirmatorias publican
todo lo de las secciones 7 y 8.

## 10. Pendiente antes de la mirada intermedia

1. Medir `iv_atm` y su cambio en el piloto, como columnas nuevas que no tocan las medidas existentes, con
   pruebas.
2. `scripts/protocolo.py`: arma las variables, entrena y puntúa según las secciones 3 a 7. Pruebas con
   datos sintéticos, entre ellas una que verifique que ninguna variable usa información posterior a la
   decisión.
3. Una corrida de desarrollo con la muestra hasta el 6 de noviembre, solo para depurar.
4. Congelar el código en un commit antes de la mirada intermedia.

## 11. Límites

- **Medición indicativa.** El feed gratis de Alpaca modifica las cotizaciones. Incluso una mejora
  direccional no sería evidencia de algo operable con precios de mercado.
- **Otro instrumento.** La señal es de SPXW y el objetivo, SPY, con sus dividendos y gastos.
- **Un solo plazo.** RR25 a 30 días, de un vencimiento interpolado entre dos.
- **Muestra corta.** Una observación por día: hacen falta muchos meses para ver efectos chicos.
