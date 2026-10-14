# QuantileFlow: dónde aportaría machine learning y cómo decidir si funciona

Fecha: 14 de octubre de 2026. **Diseño inicial; el primer contraste ya se ejecutó.**

Actualización posterior del mismo día: ejecutamos el primer contraste. La red pequeña
no superó a SSVI y falló el control de densidad en dos fotos. Véase
[el resultado y sus límites](RESULTADO_ML_SUPERFICIE_2026-10-14.md).
Este documento conserva el diseño previo; el informe enlazado contiene el estado posterior.

Sí conviene investigarlo, distinguiendo tres problemas. Una superficie más flexible,
la dinámica de esa superficie y una predicción física de precio requieren objetivos y
validaciones diferentes. No llamaremos éxito predictivo a reproducir precios de opciones.

## Primer candidato: una corrección pequeña de la superficie

La referencia será **SSVI + forward estimado únicamente con entrenamiento**. Su cobertura
reservada es 45.31% en las seis sesiones conocidas. Una red pequeña podría representar
desviaciones de la forma SSVI sin necesitar reconstruir la solución completa desde cero.
Esta idea tiene antecedentes en [Deep Smoothing of the Implied Volatility Surface,
Ackerer, Tagasovska y Vatter](https://arxiv.org/abs/1906.05065): combinan redes con modelos
financieros y penalizaciones de arbitraje. Es un antecedente metodológico, no evidencia
de que funcionará con nuestro feed ni de rentabilidad.

**Diseño propuesto, aún sin ejecutar:**

- Entradas de la corrección: log-moneyness k, plazo T y varianza ATM de la base SSVI.
  Una red pequeña y regularizada produce una corrección multiplicativa positiva de w.
- Pérdida: exactamente las mismas bandas de precios y peso hacia mid que SSVI.
  Estimar F con el procedimiento actual, sin permitir que la red lo cambie silenciosamente.
- Regularizar tamaño y derivadas de la corrección; penalizar mariposa/calendario y verificar
  cotas de precios, paridad, densidad, masa y momento. **Una penalización finita o un barrido
  de malla no es una garantía global de ausencia de arbitraje**. Se rechazan salidas que
  fallen; si no podemos certificar/proyectar una solución admisible, se marca como no viable.
- Comparar antes con una alternativa no neuronal de precios convexos. Esto permite ver
  si lo que falta es flexibilidad funcional y no una red profunda. El ajuste convexo ya
  presente en el núcleo usa penalizaciones de masa/momento: no asumir que son igualdades
  exactas sin verificar su error o sustituirlas por restricciones exactas.
- Seleccionar arquitectura/regularización solo con entrenamiento y validación interna.
  No usar los strikes finales reservados ni días finales para elegir el modelo.
- Reportar cobertura y distancia fuera de banda, costo computacional, estabilidad de
  PDF/CDF/cuántiles, arbitraje y extrapolación. Comparar por foto y vencimiento; agrupar
  incertidumbre por sesión, no por cada contrato como si fuera independiente.
- El resultado solo sería prometedor si mejora en sesiones nuevas sin empeorar coherencia,
  sensibilidad ni estabilidad. Reducir error de entrenamiento no basta.

Los días 2–9 octubre sirven para diseñar/probar. Las cinco sesiones futuras servirán como
primer control; no se usarán una y otra vez para modificar el modelo y seguir llamándolas test.
Si las usamos para seleccionar, reservaremos un conjunto final posterior distinto.
Con tan poca diversidad temporal no elegiría hoy una arquitectura grande ni un operador
preentrenado desde cero. Todos los experimentos deben respetar presupuesto de datos US$0.

## Segundo candidato: aprender cambios de la superficie

Con más historia, usar factores interpretables: ATM, skew, curvatura y su estructura temporal.
Predecir sus cambios con modelos lineales regularizados como referencia, y después un modelo
de árboles como competidor. Reconstruir una superficie admisible al salir del predictor.
Primero distinguir cambios por spot/tiempo/carry de cambios residuales; de otro modo, la red
aprenderá desplazamientos de la referencia o ruido del proveedor.

Objetivo: cambio observado de parámetros/precios o distribución Q en la siguiente foto/sesión.
Referencias: no cambia la superficie, varianza por plazo congelada y regla simple dependiente de spot.
Medir error en días posteriores y estabilidad, no ganancias inferidas usando Q como si fuera P.

## Tercer candidato: información predictiva física

Modelos iniciales: regresión logística regularizada para dirección, regresión cuantílica
para colas y, con suficiente historia, árboles de boosting como competidor. Entradas por
capas: precio/volatilidad realizados; después RR25; después cambios de factores, cuantiles
y Wasserstein. Solo conservar capas que añadan información fuera de muestra.

Validar en orden temporal, con purga/embargo por etiquetas superpuestas. Comparar Brier,
log loss, pérdida cuantílica y calibración, además de una eventual política neta de costos.
Las etiquetas mantienen sus reglas de disponibilidad/madurez. Seis sesiones y cientos de
strikes no permiten una evaluación seria de regímenes, colas y una red que decida compras.

## Decisiones que pueden terminar en «no viable»

| Evidencia | Decisión |
|---|---|
| Solo mejora dentro de entrenamiento | Rechazar como mejora generalizable |
| Mejora fit, pero genera PDF negativa o calendario inconsistente | Rechazar sin reparación certificada |
| Mejora en bandas, pero PDF/cuántiles cambian mucho al perturbar entradas | Mantener como ajuste descriptivo; no usar para posición |
| No mejora frente a SSVI/convexo con los mismos datos | Conservar el modelo sencillo |
| Ajusta Q, pero no añade información frente a controles de precio/IV para P | No usar como predictor físico |
| No hay etiquetas maduras/días suficientes | Resultado no identificado; no presentar confianza inventada |

El orden recomendado es: referencia/SSVI → competidor flexible pequeño → dinámica de
factores → señal física. El comparador condicionado a una tesis del usuario puede avanzar
en paralelo, manteniendo sus supuestos de IV, costos y ejercicio separados de cualquier predictor.
