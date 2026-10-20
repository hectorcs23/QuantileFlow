# Estrategias con puts: Vista bajista: -1 % sobre el forward

> **DATOS SINTÉTICOS.** Las cotizaciones las genera el propio código. Este documento es la plantilla del informe: sus cifras no dicen nada sobre ningún activo real, y en ningún caso son una recomendación de inversión.

- Configuración: `estrategias-0.1`; ejecución **adverso**, comisión 0.01 por pata y unidad.
- Vencimiento: 30.0 días; forward 100.2222; descuento 0.996718; 62 de 78 cotizaciones utilizables.
- Rango de strikes respaldado por cotizaciones: [78.00, 108.00], es decir [0.778, 1.078] en unidades del forward.
- `Q`: Q implícita (ajuste SSVI de la rebanada). `P`: tilt de media (-1.00% sobre el forward).

## Dictamen

**OPERAR.** Comprar puts: put spread bajista 92/97. Ventaja esperada +0.1485 por unidad (+18.80% sobre un capital de 0.79); en el peor escenario, +0.0360.

## En qué discrepa la vista del mercado

- Rendimiento esperado sobre el forward: **-1.00%**.
- Desviación típica de `ln(S_T/F)`: vista 0.0729 frente a implícita 0.0628 (factor 1.160).
- Asimetría: vista -2.077 frente a implícita -1.995.
- Probabilidad de caer un 5 %: vista 20.47% frente a implícita 15.71%. De caer un 10 %: 9.52% frente a 6.44%.
- Entropía relativa `KL(P||Q)`: **0.01308** nats (máximo admitido 0.02).

Toda la ventaja de cualquier estructura sale de estas diferencias. Si la vista fuera `P = Q`, la columna de ventaja sería exactamente cero antes de costos y negativa después.

### Ventaja de vender exposición a la caída, por tramo de precio

Cada fila es `D * int (F_Q - F_P) ds` sobre el tramo: positivo significa que el mercado asigna más probabilidad acumulada que la vista a esa zona, de modo que **vender** la caída dentro de ese tramo tiene ventaja. Es la descomposición que decide qué strike expresa la opinión.

| Desde | Hasta | Prob. Q | Prob. P | Ventaja |
|---|---|---|---|---|
| 80.18 | 90.20 | 0.0534 | 0.0745 | -0.18706 |
| 90.20 | 95.21 | 0.0926 | 0.1095 | -0.19516 |
| 95.21 | 97.72 | 0.0920 | 0.0996 | -0.12901 |
| 97.72 | 100.22 | 0.1493 | 0.1518 | -0.14281 |
| 100.22 | 102.73 | 0.2162 | 0.2067 | -0.13555 |
| 102.73 | 105.23 | 0.2315 | 0.2086 | -0.09292 |
| 105.23 | 110.24 | 0.1472 | 0.1236 | -0.04844 |
| 110.24 | 120.27 | 0.0068 | 0.0051 | -0.00276 |

![Distribuciones](distribuciones.png)

La vista frente a la implícita. La banda marca el rango de strikes con cotizaciones utilizables: fuera de ella la forma de ambas distribuciones es extrapolación.

![Ventaja por strike](ventaja_por_strike.png)

Ventaja de vender un put de cada strike. Su máximo señala dónde la discrepancia pesa más en prima; fuera de la banda, la curva depende de lo que nadie cotiza.

## Candidatas

Escenarios de robustez: base, ejecución al mid, convicción a la mitad, dirección con la dispersión de Q, otra estimación de Q. La columna «peor» es la ventaja mínima entre ellos. «No fiable» es la parte de la ventaja que procede de la zona sin cotizaciones utilizables.

| Estructura | Papel | Ventaja | Peor | Capital | Sobre capital | CVaR | No fiable |
|---|---|---|---|---|---|---|---|
| put spread bajista 92/97 | comprar puts | +0.1485 | +0.0360 | 0.79 | +18.801% | 0.79 | +24% |
| put spread bajista 90/95 | comprar puts | +0.1105 | +0.0148 | 0.58 | +19.048% | 0.58 | +33% |
| collar 97/103 | comprar puts | -0.4784 | -0.6132 | 100.43 | -0.476% | 3.76 | — |
| put protectora 97 | comprar puts | -0.5688 | -0.7994 | 101.21 | -0.562% | 4.55 | — |
| collar 95/105 | comprar puts | -0.6371 | -0.8331 | 100.57 | -0.633% | 5.90 | — |
| put protectora 95 | comprar puts | -0.6624 | -0.9045 | 100.84 | -0.657% | 6.18 | — |
| put protectora 92 | comprar puts | -0.7874 | -1.0190 | 100.49 | -0.784% | 8.82 | — |
| collar 92/108 | comprar puts | -0.8117 | -1.0336 | 100.48 | -0.808% | 8.81 | — |
| put corto 92 | vender puts | -0.3415 | -0.3415 | 91.23 | -0.374% | 11.92 | — |
| reversal de riesgo -92p/+108c | vender puts | -0.3771 | -0.3771 | 91.30 | -0.413% | 11.99 | — |
| put corto 95 | vender puts | -0.4764 | -0.4764 | 93.88 | -0.508% | 14.58 | — |
| reversal de riesgo -95p/+105c | vender puts | -0.5618 | -0.5618 | 94.21 | -0.596% | 14.91 | — |
| put corto 97 | vender puts | -0.5800 | -0.5800 | 95.51 | -0.607% | 16.22 | — |
| reversal de riesgo -97p/+103c | vender puts | -0.7505 | -0.7505 | 96.37 | -0.779% | 17.08 | — |
| forward largo | sin puts | -1.0589 | -1.0589 | 99.95 | -1.059% | 20.67 | — |
| put largo 97 | comprar puts | +0.4900 | +0.2211 | 1.26 | +38.891% | 1.26 | +38% |
| put largo 95 | comprar puts | +0.3964 | +0.1544 | 0.89 | +44.544% | 0.89 | +43% |
| put largo 92 | comprar puts | +0.2715 | +0.0399 | 0.54 | +50.278% | 0.54 | +55% |
| put spread bajista 87/92 | comprar puts | +0.0784 | +0.0064 | 0.36 | +21.787% | 0.36 | +46% |
| put spread bajista 92/95 | comprar puts | +0.0549 | -0.0075 | 0.42 | +13.082% | 0.42 | +40% |
| put spread bajista 94/97 | comprar puts | +0.0467 | -0.0260 | 0.60 | +7.776% | 0.60 | +47% |
| put spread alcista 87/92 | vender puts | -0.2084 | -0.2084 | 4.75 | -4.385% | 4.77 | — |
| put spread alcista 89/92 | vender puts | -0.1513 | -0.1513 | 2.84 | -5.326% | 2.85 | — |
| put spread alcista 90/95 | vender puts | -0.2605 | -0.2605 | 4.55 | -5.720% | 4.57 | — |
| put spread alcista 92/97 | vender puts | -0.3085 | -0.3095 | 4.35 | -7.087% | 4.37 | — |
| put spread alcista 92/95 | vender puts | -0.2049 | -0.2049 | 2.72 | -7.534% | 2.73 | — |
| put spread alcista 94/97 | vender puts | -0.2167 | -0.2278 | 2.56 | -8.463% | 2.57 | — |
| put spread bajista 89/92 | comprar puts | +0.0213 | -0.0263 | 0.28 | +7.591% | 0.28 | +102% |
| call largo 103 | sin puts | -0.1704 | -0.2663 | 0.86 | -19.816% | 0.86 | — |
| call spread alcista 103/106 | sin puts | -0.1729 | -0.2399 | 0.73 | -23.686% | 0.73 | — |
| call spread alcista 103/108 | sin puts | -0.1948 | -0.2809 | 0.85 | -22.914% | 0.85 | — |
| call largo 105 | sin puts | -0.0854 | -0.1314 | 0.33 | -25.865% | 0.33 | — |
| call spread alcista 105/108 | sin puts | -0.1097 | -0.1460 | 0.32 | -34.283% | 0.32 | — |
| call largo 108 | sin puts | -0.0356 | -0.0454 | 0.07 | -50.926% | 0.07 | — |
| forward corto | sin puts | +0.9390 | +0.4395 | no acotado | — | 8.21 | +22% |

![Perfiles](perfiles.png)

Resultado al vencimiento de las candidatas principales, neto de la prima capitalizada.

![Ventaja y riesgo](ventaja_riesgo.png)

Ventaja esperada frente al CVaR de la pérdida. Las estructuras con más ventaja suelen ser también las de más cola: la puntuación penaliza el CVaR para no confundirlas.

## Vender o comprar puts

- Mejor forma de **vender** puts: `put corto 92` (alcista), ventaja -0.3415; descartada (ventaja esperada no positiva (-0.3415)).
- Mejor forma de **comprar** puts: `put spread bajista 92/97` (bajista), ventaja +0.1485; pasa los filtros.
- Mejor alternativa **sin** puts: `forward largo` (alcista), ventaja -1.0589; descartada (ventaja esperada no positiva (-1.0589)).

## Descartes

- `collar 97/103`: ventaja esperada no positiva (-0.4784); zona de no operación: la ventaja (-0.4784) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1485 = 0.1449 + 0.0035); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.6132); rendimiento esperado sobre capital -0.476% por debajo de 0.300%.
- `put protectora 97`: ventaja esperada no positiva (-0.5688); zona de no operación: la ventaja (-0.5688) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1076 = 0.1049 + 0.0026); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.7994); rendimiento esperado sobre capital -0.562% por debajo de 0.300%.
- `collar 95/105`: ventaja esperada no positiva (-0.6371); zona de no operación: la ventaja (-0.6371) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1330 = 0.1299 + 0.0030); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.8331); rendimiento esperado sobre capital -0.633% por debajo de 0.300%.
- `put protectora 95`: ventaja esperada no positiva (-0.6624); zona de no operación: la ventaja (-0.6624) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1010 = 0.0999 + 0.0010); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.9045); rendimiento esperado sobre capital -0.657% por debajo de 0.300%.
- `put protectora 92`: ventaja esperada no positiva (-0.7874); zona de no operación: la ventaja (-0.7874) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1011 = 0.0949 + 0.0062); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-1.0190); rendimiento esperado sobre capital -0.784% por debajo de 0.300%.
- `collar 92/108`: ventaja esperada no positiva (-0.8117); zona de no operación: la ventaja (-0.8117) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1365 = 0.1249 + 0.0116); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-1.0336); rendimiento esperado sobre capital -0.808% por debajo de 0.300%.
- `put corto 92`: ventaja esperada no positiva (-0.3415); zona de no operación: la ventaja (-0.3415) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0413 = 0.0350 + 0.0063); la ventaja desaparece en el escenario «base» (-0.3415); rendimiento esperado sobre capital -0.374% por debajo de 0.300%.
- `reversal de riesgo -92p/+108c`: ventaja esperada no positiva (-0.3771); zona de no operación: la ventaja (-0.3771) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0767 = 0.0650 + 0.0117); la ventaja desaparece en el escenario «base» (-0.3771); rendimiento esperado sobre capital -0.413% por debajo de 0.300%.
- `put corto 95`: ventaja esperada no positiva (-0.4764); zona de no operación: la ventaja (-0.4764) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0412 = 0.0400 + 0.0012); la ventaja desaparece en el escenario «base» (-0.4764); rendimiento esperado sobre capital -0.508% por debajo de 0.300%.
- `reversal de riesgo -95p/+105c`: ventaja esperada no positiva (-0.5618); zona de no operación: la ventaja (-0.5618) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0731 = 0.0700 + 0.0031); la ventaja desaparece en el escenario «base» (-0.5618); rendimiento esperado sobre capital -0.596% por debajo de 0.300%.
- `put corto 97`: ventaja esperada no positiva (-0.5800); zona de no operación: la ventaja (-0.5800) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0477 = 0.0450 + 0.0027); la ventaja desaparece en el escenario «base» (-0.5800); rendimiento esperado sobre capital -0.607% por debajo de 0.300%.
- `reversal de riesgo -97p/+103c`: ventaja esperada no positiva (-0.7505); zona de no operación: la ventaja (-0.7505) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0887 = 0.0850 + 0.0037); la ventaja desaparece en el escenario «base» (-0.7505); rendimiento esperado sobre capital -0.779% por debajo de 0.300%.
- `forward largo`: ventaja esperada no positiva (-1.0589); zona de no operación: la ventaja (-1.0589) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0601 = 0.0599 + 0.0001); la ventaja desaparece en el escenario «base» (-1.0589); rendimiento esperado sobre capital -1.059% por debajo de 0.300%.
- `put largo 97`: el 38% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put largo 95`: el 43% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put largo 92`: el 55% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread bajista 87/92`: el 46% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread bajista 92/95`: zona de no operación: la ventaja (+0.0549) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0075); el signo de la ventaja no es estable entre escenarios; el 40% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread bajista 94/97`: zona de no operación: la ventaja (+0.0467) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0260); el signo de la ventaja no es estable entre escenarios; el 47% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 87/92`: ventaja esperada no positiva (-0.2084); zona de no operación: la ventaja (-0.2084) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «base» (-0.2084); rendimiento esperado sobre capital -4.385% por debajo de 0.300%.
- `put spread alcista 89/92`: ventaja esperada no positiva (-0.1513); zona de no operación: la ventaja (-0.1513) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «base» (-0.1513); rendimiento esperado sobre capital -5.326% por debajo de 0.300%.
- `put spread alcista 90/95`: ventaja esperada no positiva (-0.2605); zona de no operación: la ventaja (-0.2605) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0808 = 0.0750 + 0.0058); la ventaja desaparece en el escenario «base» (-0.2605); rendimiento esperado sobre capital -5.720% por debajo de 0.300%.
- `put spread alcista 92/97`: ventaja esperada no positiva (-0.3085); zona de no operación: la ventaja (-0.3085) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0836 = 0.0800 + 0.0036); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.3095); rendimiento esperado sobre capital -7.087% por debajo de 0.300%.
- `put spread alcista 92/95`: ventaja esperada no positiva (-0.2049); zona de no operación: la ventaja (-0.2049) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «base» (-0.2049); rendimiento esperado sobre capital -7.534% por debajo de 0.300%.
- `put spread alcista 94/97`: ventaja esperada no positiva (-0.2167); zona de no operación: la ventaja (-0.2167) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.2278); rendimiento esperado sobre capital -8.463% por debajo de 0.300%.
- `put spread bajista 89/92`: zona de no operación: la ventaja (+0.0213) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0263); el signo de la ventaja no es estable entre escenarios; el 102% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 103`: ventaja esperada no positiva (-0.1704); zona de no operación: la ventaja (-0.1704) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0409 = 0.0400 + 0.0009); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.2663); rendimiento esperado sobre capital -19.816% por debajo de 0.300%.
- `call spread alcista 103/106`: ventaja esperada no positiva (-0.1729); zona de no operación: la ventaja (-0.1729) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0761 = 0.0700 + 0.0061); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.2399); rendimiento esperado sobre capital -23.686% por debajo de 0.300%.
- `call spread alcista 103/108`: ventaja esperada no positiva (-0.1948); zona de no operación: la ventaja (-0.1948) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0745 = 0.0700 + 0.0045); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.2809); rendimiento esperado sobre capital -22.914% por debajo de 0.300%.
- `call largo 105`: ventaja esperada no positiva (-0.0854); zona de no operación: la ventaja (-0.0854) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0320 = 0.0300 + 0.0020); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.1314); rendimiento esperado sobre capital -25.865% por debajo de 0.300%.
- `call spread alcista 105/108`: ventaja esperada no positiva (-0.1097); zona de no operación: la ventaja (-0.1097) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0634 = 0.0600 + 0.0034); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.1460); rendimiento esperado sobre capital -34.283% por debajo de 0.300%.
- `call largo 108`: ventaja esperada no positiva (-0.0356); zona de no operación: la ventaja (-0.0356) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0354 = 0.0300 + 0.0054); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-0.0454); rendimiento esperado sobre capital -50.926% por debajo de 0.300%.
- `forward corto`: pérdida no acotada por arriba; capital inmovilizado no acotado: hace falta un margen declarado.

## Lo que este informe no dice

- **No hay evidencia de que la vista acierte.** La ventaja es una resta entre lo que dice la vista y lo que dice el precio; si la vista está mal, el signo se invierte.
- **El CVaR y la pérdida máxima se calculan bajo la vista**, que es justamente la parte optimista del cálculo. La pérdida real de un put vendido llega cuando la vista falla.
- **El capital es una regla propia** (peor caso en valor presente), no el margen que exigiría un intermediario, que depende de su propio modelo y puede cambiar intradía.
- **La probabilidad de ganar no es un criterio.** Un put muy fuera del dinero gana casi siempre y eso ya está en su precio; se reporta porque se suele mirar.
- No hay ejecución, ni gestión de la posición antes del vencimiento, ni asignación anticipada, ni dividendos, ni impuestos, ni límite de concentración entre vencimientos.
