# Correcciones de probabilidad y entropía: 20 de octubre de 2026

Rama `codex/correcciones-entropia-20261020`, sobre `698c66c`.
Se corrigió el subproyecto de estrategias; no se cambió la captura de mercado.

## Correcciones

1. **Media de precio y mínimo KL.** Para imponer E_P[S]=m, la condición óptima
   es p_i proporcional a q_i exp(lambda*S_i/F). Antes se inclinaba log(S/F):
   alcanzaba la media, pero no minimizaba KL bajo esa restricción.
   La normalización ahora usa log-pesos sobre el soporte positivo de Q.
2. **Compensación fuera de una cola fijada.** Se corrigió también el estadístico
   de la compensación para conservar la media con mínimo KL. Se conservan
   exactamente los pesos fijados dentro de la cola.
3. **Probabilidades negativas.** El constructor y su helper rechazan masa negativa
   material antes de recortar o normalizar. Solo se tolera una masa negativa
   total de 1e-12 por redondeo; cualquier corrección se registra y conserva masa.
4. **Identidad de puts.** La ventaja viene del signo de la integral de la diferencia
   de CDF. La dominancia puntual es suficiente, no necesaria: se agregó un ejemplo
   con CDF cruzadas y ventaja positiva.
5. **Límite adicional descubierto.** La vista de media y desviación de log-precio
   no tiene un certificado de mínimo KL. Se conserva como familia paramétrica,
   con `minimo_kl_certificado=False`; sin una petición de dispersión delega en
   el ajuste correcto de media. No se cambió subrepticiamente qué significa
   `factor_vol`. Resolver la optimización global con varianza logarítmica
   sigue pendiente y no es necesario para el comparador condicional de calls.

## Comprobaciones y resultados

Pasaron **46 pruebas**: las 34 existentes de estrategias y 12 regresiones nuevas.
El mínimo KL de media y el de compensación de cola se comparan con optimización
directa en probabilidades mediante SLSQP, sin usar la parametrización tilt.
Se verifican también ceros en el soporte, valores no finitos, rechazo de negativos,
registro del redondeo y el contraejemplo de CDF.

Se regeneraron cinco informes **sintéticos** en
[`reports/estrategias_corregidas_20261020/`](../reports/estrategias_corregidas_20261020/).
Se conservan los informes históricos del 2 de octubre.

| Vista sintética | Candidatas aptas / 35 | Salida del motor del ejemplo |
|---|---:|---|
| Alcista +1% sobre forward | 5 | Put corto 95 |
| Alcista +0.82%, misma dispersión logarítmica | 2 | Reversal −97p/+103c |
| Cola izquierda reponderada ×0.8, misma media | 0 | Abstenerse |
| Bajista −1% | 2 | Put spread bajista 92/97 |
| P=Q | 0 | Abstenerse |

Las etiquetas son salidas del laboratorio, no órdenes ni recomendaciones con
precios de mercado. Las vistas no tienen el mismo KL: no se atribuye toda
diferencia de resultado exclusivamente al tipo de opinión.

En el ejemplo alcista corregido, KL(P||Q)=0.0155962, la desviación logarítmica
pasa de 6.2792% a 5.3567% y P(caída mayor a 5%) pasa de 15.7073% a 11.0774%.
Son consecuencias de la opinión impuesta sobre una Q sintética, no frecuencias
observadas ni una calibración de confianza.

## Reproducción

```text
python -m pytest -p no:cacheprovider tests/test_estrategias.py tests/test_correcciones_entropia.py -q
python scripts/estrategias_sintetico.py --salida reports/estrategias_corregidas_20261020
```

Los manifiestos identifican la base `698c66c` y cambios pendientes durante la
generación. Las fuentes corregidas quedan publicadas en esta rama; no se
presentan los informes como generados por la base sin modificar.
