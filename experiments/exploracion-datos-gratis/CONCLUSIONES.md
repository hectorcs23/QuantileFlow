# Conclusiones independientes de bt2

Revisión del 2 de octubre de 2026. **La aritmética se reproduce; la evidencia no demuestra todavía una
estrategia rentable ni identifica cuánto de la convergencia es reversión económica.**

## Reproducción

Se descargó la rama privada `exploracion` de `hectorcs23/QuantileFlow-datos`, commit
`660dcdb21b42567dec274db81ccf2fc4089c6280`. Sus 669 hashes SHA-256 coinciden, todos los archivos se
descomprimen y sus fechas coinciden con los nombres. El 2 de febrero de 2024 no contiene opciones.
El manifiesto SHA-256 tiene huella `135676000bf91b86a4d6cfe2f6785aca7c92bc5958c97b26e64fd54c6b19e9fa`.

Se ejecutó el código original de bt2, commit `f49beed4cc33120b115677aad44cbc80b86bbfda`, y se compararon
todos los campos con sus JSON publicados: diferencia numérica máxima 1.887×10⁻¹² en 0DTE y 8.882×10⁻¹⁶
en el estudio diario. Son diferencias de precisión numérica, no cambios materiales.
Entorno: Python 3.12.14 y las versiones de `requirements-bloqueo.txt`. **15 pruebas pasadas**.

Los datos diarios se recuperaron de Cboe y Alpaca; incluyen 2 702 sesiones XNYS. Faltan cuatro datos
SKEW: 2017-09-14, 2018-12-03, 2019-07-05 y 2024-11-29. El código original comprimía esas fechas al
construir objetivos sobre el join; la validación conserva el calendario antes de formar objetivos.
Los datos crudos permanecen fuera del repositorio público.

## Skew 0DTE: lo que sobrevive a las correcciones

| Prueba | Señales observadas | Convergencia, puntos de vol | IC95 por bloques |
|---|---:|---:|---|
| Retrasada original (+5 a +35 min) | 383 | +0.634 | [0.432, 0.878] |
| Retrasada, misma cohorte que la ingenua | 375 | +0.625 | [0.417, 0.872] |
| Ventana de 5 min, señales congeladas para comparar antigüedad | 382 | +0.634 | [0.430, 0.880] |
| Solo minuto anterior, mismas 382 señales y direcciones | 382 | +0.633 | [0.430, 0.879] |

La diferencia de ventanas es +0.00124 puntos, IC95 [−0.00119, +0.00389]. **La antigüedad de las barras
no explica la convergencia en esta muestra.** La medición sigue usando operaciones, no cotizaciones.

Comparando todos los horizontes sobre las mismas 355 señales, las medias son +0.238, +0.455, +0.551
y +0.791 puntos a 10, 20, 30 y 45 minutos. La curva gradual sobrevive a la comparación emparejada.
Sin embargo, solo hay 355 señales completas de 440 elegibles hasta 45 minutos. Las ausencias pueden
depender de la liquidez o del resultado, y el emparejamiento no elimina ese sesgo.

Sobre 17 535 orígenes comunes, las pendientes descriptivas a 5/10/30 minutos son 0.9305/0.9130/0.8539.
No identifican una vida media económica. Se retiran las afirmaciones de «1.4 % de ruido» y «4 horas».

## Qué no queda demostrado

El contraejemplo reproducible mantiene el skew verdadero fijo en 4 y añade exclusivamente error de
medición AR(0.90). Aun así obtiene convergencia retrasada de **+1.0295 puntos**, IC95 [0.9764, 1.0830].
Los mismos datos observados admiten también un skew económico AR sin error. Por tanto, retrasar
cinco minutos no permite distinguir esas explicaciones. Esto refuta el argumento de identificación de
bt2, pero no prueba que su señal de mercado sea enteramente ruido.

Tampoco se midió P&L: el RR25 interpolado cambia de contratos entre tiempos. Bajo el escenario
ilustrativo de SPY=600 y 3.5 horas al vencimiento, +0.625 puntos × 3.811 USD por punto son unos
2.38 USD, frente a 8.60 USD de cuatro ejecuciones bajo las comisiones/spread/deslizamiento supuestos.
Esta cuenta es desfavorable, pero no es un backtest ni un límite del beneficio real.

## SKEW diario: asociación de riesgo sin mejora fiable de pronóstico

Se pronosticó en cada fecha con un ajuste expansivo, usando solamente etiquetas maduras antes de
esa fecha. El objetivo de riesgo comienza en la próxima apertura: excluye el primer overnight que
empezó antes de estar disponible el SKEW final. Es distinto del objetivo original.

| Evaluación | Pronósticos | Reducción MSE al añadir SKEW |
|---|---:|---:|
| Riesgo, 2021–2026 | 1 437 | +1.22 % |
| Riesgo, 2021–2023 | 753 | +5.22 % |
| Riesgo, 2024–2026 | 684 | −1.78 % |
| Dirección próxima apertura-cierre | 1 440 | −0.20 % |

Para riesgo, la diferencia media de pérdidas es +1.017×10⁻⁶, IC95 [−1.678×10⁻⁶, +3.856×10⁻⁶]:
**incluye cero**. Añadir volatilidad pasada al modelo de referencia da una mejora de +1.25 % con
intervalo que también incluye cero. La asociación en muestra persiste, pero su t cae de −3.21 a
−2.77 y −2.40 al ampliar los rezagos HAC de 5 a 10 y 20. Multiplicidad y sensibilidad siguen siendo
relevantes. Esta evaluación es retrospectiva sobre historia ya examinada, no un holdout nuevo.

## Decisión de investigación

bt2 hizo una exploración útil y sus números principales están bien calculados. La convergencia del
indicador sobrevive al emparejamiento y a precios recientes. **Rechazo que estos datos ya demuestren
reversión económica aprovechable; tampoco confirman una mejora estable de gestión de riesgo.**
Mantendría el experimento en investigación. Para avanzar, exigiría un replay con bid/ask histórico,
contratos seleccionados y congelados en la señal, entradas/salidas causales, cobertura y costos
completos; después, confirmación en sesiones nuevas. Con los datos actuales esa prueba sigue pendiente.

Los comandos y las condiciones exactas están en [VALIDACION.md](VALIDACION.md); las cifras y huellas
se encuentran en `resultados/validacion_*.json`.
