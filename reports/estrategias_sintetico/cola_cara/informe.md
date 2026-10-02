# Estrategias con puts: Vista de cola pura: la caída de más del 5 % está sobrevalorada un 20 %, sin opinión sobre la dirección

> **DATOS SINTÉTICOS.** Las cotizaciones las genera el propio código. Este documento es la plantilla del informe: sus cifras no dicen nada sobre ningún activo real, y en ningún caso son una recomendación de inversión.

- Configuración: `estrategias-0.1`; ejecución **adverso**, comisión 0.01 por pata y unidad.
- Vencimiento: 30.0 días; forward 100.2222; descuento 0.996718; 62 de 78 cotizaciones utilizables.
- Rango de strikes respaldado por cotizaciones: [78.00, 108.00], es decir [0.778, 1.078] en unidades del forward.
- `Q`: Q implícita (ajuste SSVI de la rebanada). `P`: cola izquierda reponderada x0.80 más allá de -0.050 en log, con la media de Q.

## Dictamen

**ABSTENERSE.** Abstenerse: ninguna de las 35 candidatas evaluables pasa los filtros.

## En qué discrepa la vista del mercado

- Rendimiento esperado sobre el forward: **+0.00%**.
- Desviación típica de `ln(S_T/F)`: vista 0.0575 frente a implícita 0.0628 (factor 0.915).
- Asimetría: vista -2.099 frente a implícita -1.995.
- Probabilidad de caer un 5 %: vista 12.57% frente a implícita 15.71%. De caer un 10 %: 5.16% frente a 6.44%.
- Entropía relativa `KL(P||Q)`: **0.01261** nats (máximo admitido 0.02).

Toda la ventaja de cualquier estructura sale de estas diferencias. Si la vista fuera `P = Q`, la columna de ventaja sería exactamente cero antes de costos y negativa después.

### Ventaja de vender exposición a la caída, por tramo de precio

Cada fila es `D * int (F_Q - F_P) ds` sobre el tramo: positivo significa que el mercado asigna más probabilidad acumulada que la vista a esa zona, de modo que **vender** la caída dentro de ese tramo tiene ventaja. Es la descomposición que decide qué strike expresa la opinión.

| Desde | Hasta | Prob. Q | Prob. P | Ventaja |
|---|---|---|---|---|
| 80.18 | 90.20 | 0.0534 | 0.0427 | +0.06083 |
| 90.20 | 95.21 | 0.0926 | 0.0741 | +0.10379 |
| 95.21 | 97.72 | 0.0920 | 0.1187 | +0.04781 |
| 97.72 | 100.22 | 0.1493 | 0.1754 | -0.02190 |
| 100.22 | 102.73 | 0.2162 | 0.2285 | -0.07313 |
| 102.73 | 105.23 | 0.2315 | 0.2215 | -0.07596 |
| 105.23 | 110.24 | 0.1472 | 0.1254 | -0.04980 |
| 110.24 | 120.27 | 0.0068 | 0.0048 | -0.00327 |

![Distribuciones](distribuciones.png)

La vista frente a la implícita. La banda marca el rango de strikes con cotizaciones utilizables: fuera de ella la forma de ambas distribuciones es extrapolación.

![Ventaja por strike](ventaja_por_strike.png)

Ventaja de vender un put de cada strike. Su máximo señala dónde la discrepancia pesa más en prima; fuera de la banda, la curva depende de lo que nadie cotiza.

## Candidatas

Escenarios de robustez: base, ejecución al mid, convicción a la mitad, otra estimación de Q. La columna «peor» es la ventaja mínima entre ellos. «No fiable» es la parte de la ventaja que procede de la zona sin cotizaciones utilizables.

| Estructura | Papel | Ventaja | Peor | Capital | Sobre capital | CVaR | No fiable |
|---|---|---|---|---|---|---|---|
| collar 97/103 | comprar puts | -0.2463 | -0.2463 | 100.43 | -0.245% | 3.76 | — |
| put protectora 97 | comprar puts | -0.3253 | -0.3253 | 101.21 | -0.321% | 4.55 | — |
| collar 95/105 | comprar puts | -0.2440 | -0.2440 | 100.57 | -0.243% | 5.90 | — |
| put protectora 95 | comprar puts | -0.2708 | -0.2708 | 100.84 | -0.268% | 6.18 | — |
| put corto 92 | vender puts | +0.0710 | +0.0212 | 91.23 | +0.078% | 7.14 | +40% |
| reversal de riesgo -92p/+108c | vender puts | +0.0339 | -0.0097 | 91.30 | +0.037% | 7.21 | +47% |
| put protectora 92 | comprar puts | -0.2009 | -0.2009 | 100.49 | -0.200% | 8.82 | — |
| collar 92/108 | comprar puts | -0.2237 | -0.2237 | 100.48 | -0.223% | 8.81 | — |
| put corto 95 | vender puts | +0.1309 | +0.0461 | 93.88 | +0.139% | 9.80 | +25% |
| reversal de riesgo -95p/+105c | vender puts | +0.0441 | -0.0114 | 94.21 | +0.047% | 10.13 | -3% |
| put corto 97 | vender puts | +0.1755 | +0.0666 | 95.51 | +0.184% | 11.44 | +20% |
| reversal de riesgo -97p/+103c | vender puts | +0.0165 | -0.0324 | 96.37 | +0.017% | 12.30 | -77% |
| forward largo | sin puts | -0.0598 | -0.0598 | 99.95 | -0.060% | 15.90 | — |
| put spread alcista 87/92 | vender puts | -0.0054 | -0.0349 | 4.75 | -0.114% | 4.10 | — |
| put spread alcista 90/95 | vender puts | +0.0307 | -0.0193 | 4.55 | +0.673% | 4.57 | +24% |
| put spread alcista 92/97 | vender puts | +0.0344 | -0.0246 | 4.35 | +0.790% | 4.37 | +22% |
| put spread alcista 89/92 | vender puts | -0.0149 | -0.0355 | 2.84 | -0.525% | 2.77 | — |
| put spread alcista 94/97 | vender puts | +0.0041 | -0.0337 | 2.56 | +0.161% | 2.57 | +108% |
| put spread alcista 92/95 | vender puts | -0.0101 | -0.0451 | 2.72 | -0.371% | 2.73 | — |
| call largo 103 | sin puts | -0.1589 | -0.1589 | 0.86 | -18.481% | 0.86 | — |
| put largo 97 | comprar puts | -0.2655 | -0.2655 | 1.26 | -21.068% | 1.26 | — |
| call spread alcista 103/108 | sin puts | -0.1818 | -0.1818 | 0.85 | -21.383% | 0.85 | — |
| call spread alcista 103/106 | sin puts | -0.1590 | -0.1590 | 0.73 | -21.777% | 0.73 | — |
| put largo 95 | comprar puts | -0.2109 | -0.2109 | 0.89 | -23.701% | 0.89 | — |
| put spread bajista 92/97 | comprar puts | -0.1944 | -0.1944 | 0.79 | -24.609% | 0.79 | — |
| put largo 92 | comprar puts | -0.1410 | -0.1410 | 0.54 | -26.118% | 0.54 | — |
| call largo 105 | sin puts | -0.0868 | -0.0868 | 0.33 | -26.304% | 0.33 | — |
| put spread bajista 94/97 | comprar puts | -0.1741 | -0.1741 | 0.60 | -29.018% | 0.60 | — |
| put spread bajista 90/95 | comprar puts | -0.1807 | -0.1807 | 0.58 | -31.147% | 0.58 | — |
| put spread bajista 92/95 | comprar puts | -0.1399 | -0.1399 | 0.42 | -33.309% | 0.42 | — |
| call spread alcista 105/108 | sin puts | -0.1096 | -0.1096 | 0.32 | -34.257% | 0.32 | — |
| put spread bajista 87/92 | comprar puts | -0.1246 | -0.1246 | 0.36 | -34.600% | 0.36 | — |
| put spread bajista 89/92 | comprar puts | -0.1151 | -0.1151 | 0.28 | -41.103% | 0.28 | — |
| call largo 108 | sin puts | -0.0372 | -0.0372 | 0.07 | -53.119% | 0.07 | — |
| forward corto | sin puts | -0.0601 | -0.0601 | no acotado | — | 8.16 | — |

![Perfiles](perfiles.png)

Resultado al vencimiento de las candidatas principales, neto de la prima capitalizada.

![Ventaja y riesgo](ventaja_riesgo.png)

Ventaja esperada frente al CVaR de la pérdida. Las estructuras con más ventaja suelen ser también las de más cola: la puntuación penaliza el CVaR para no confundirlas.

## Vender o comprar puts

- Mejor forma de **vender** puts: `put corto 92` (alcista), ventaja +0.0710; descartada (el 40% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%)).
- Mejor forma de **comprar** puts: `collar 97/103` (cobertura), ventaja -0.2463; descartada (ventaja esperada no positiva (-0.2463)).
- Mejor alternativa **sin** puts: `forward largo` (alcista), ventaja -0.0598; descartada (ventaja esperada no positiva (-0.0598)).

## Descartes

- `collar 97/103`: ventaja esperada no positiva (-0.2463); zona de no operación: la ventaja (-0.2463) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1485 = 0.1449 + 0.0035); la ventaja desaparece en el escenario «base» (-0.2463); rendimiento esperado sobre capital -0.245% por debajo de 0.300%.
- `put protectora 97`: ventaja esperada no positiva (-0.3253); zona de no operación: la ventaja (-0.3253) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1076 = 0.1049 + 0.0026); la ventaja desaparece en el escenario «base» (-0.3253); rendimiento esperado sobre capital -0.321% por debajo de 0.300%.
- `collar 95/105`: ventaja esperada no positiva (-0.2440); zona de no operación: la ventaja (-0.2440) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1330 = 0.1299 + 0.0030); la ventaja desaparece en el escenario «base» (-0.2440); rendimiento esperado sobre capital -0.243% por debajo de 0.300%.
- `put protectora 95`: ventaja esperada no positiva (-0.2708); zona de no operación: la ventaja (-0.2708) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1010 = 0.0999 + 0.0010); la ventaja desaparece en el escenario «base» (-0.2708); rendimiento esperado sobre capital -0.268% por debajo de 0.300%.
- `put corto 92`: el 40% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.078% por debajo de 0.300%.
- `reversal de riesgo -92p/+108c`: zona de no operación: la ventaja (+0.0339) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0767 = 0.0650 + 0.0117); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0097); el signo de la ventaja no es estable entre escenarios; el 47% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.037% por debajo de 0.300%.
- `put protectora 92`: ventaja esperada no positiva (-0.2009); zona de no operación: la ventaja (-0.2009) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1011 = 0.0949 + 0.0062); la ventaja desaparece en el escenario «base» (-0.2009); rendimiento esperado sobre capital -0.200% por debajo de 0.300%.
- `collar 92/108`: ventaja esperada no positiva (-0.2237); zona de no operación: la ventaja (-0.2237) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.1365 = 0.1249 + 0.0116); la ventaja desaparece en el escenario «base» (-0.2237); rendimiento esperado sobre capital -0.223% por debajo de 0.300%.
- `put corto 95`: rendimiento esperado sobre capital 0.139% por debajo de 0.300%.
- `reversal de riesgo -95p/+105c`: zona de no operación: la ventaja (+0.0441) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0731 = 0.0700 + 0.0031); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0114); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital 0.047% por debajo de 0.300%.
- `put corto 97`: rendimiento esperado sobre capital 0.184% por debajo de 0.300%.
- `reversal de riesgo -97p/+103c`: zona de no operación: la ventaja (+0.0165) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0887 = 0.0850 + 0.0037); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0324); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital 0.017% por debajo de 0.300%.
- `forward largo`: ventaja esperada no positiva (-0.0598); zona de no operación: la ventaja (-0.0598) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0601 = 0.0599 + 0.0001); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0598); rendimiento esperado sobre capital -0.060% por debajo de 0.300%.
- `put spread alcista 87/92`: ventaja esperada no positiva (-0.0054); zona de no operación: la ventaja (-0.0054) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0349); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital -0.114% por debajo de 0.300%.
- `put spread alcista 90/95`: zona de no operación: la ventaja (+0.0307) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0808 = 0.0750 + 0.0058); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0193); el signo de la ventaja no es estable entre escenarios.
- `put spread alcista 92/97`: zona de no operación: la ventaja (+0.0344) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0836 = 0.0800 + 0.0036); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0246); el signo de la ventaja no es estable entre escenarios.
- `put spread alcista 89/92`: ventaja esperada no positiva (-0.0149); zona de no operación: la ventaja (-0.0149) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0355); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital -0.525% por debajo de 0.300%.
- `put spread alcista 94/97`: zona de no operación: la ventaja (+0.0041) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0337); el signo de la ventaja no es estable entre escenarios; el 108% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.161% por debajo de 0.300%.
- `put spread alcista 92/95`: ventaja esperada no positiva (-0.0101); zona de no operación: la ventaja (-0.0101) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0451); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital -0.371% por debajo de 0.300%.
- `call largo 103`: ventaja esperada no positiva (-0.1589); zona de no operación: la ventaja (-0.1589) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0409 = 0.0400 + 0.0009); la ventaja desaparece en el escenario «base» (-0.1589); rendimiento esperado sobre capital -18.481% por debajo de 0.300%.
- `put largo 97`: ventaja esperada no positiva (-0.2655); zona de no operación: la ventaja (-0.2655) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0477 = 0.0450 + 0.0027); la ventaja desaparece en el escenario «base» (-0.2655); rendimiento esperado sobre capital -21.068% por debajo de 0.300%.
- `call spread alcista 103/108`: ventaja esperada no positiva (-0.1818); zona de no operación: la ventaja (-0.1818) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0745 = 0.0700 + 0.0045); la ventaja desaparece en el escenario «base» (-0.1818); rendimiento esperado sobre capital -21.383% por debajo de 0.300%.
- `call spread alcista 103/106`: ventaja esperada no positiva (-0.1590); zona de no operación: la ventaja (-0.1590) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0761 = 0.0700 + 0.0061); la ventaja desaparece en el escenario «base» (-0.1590); rendimiento esperado sobre capital -21.777% por debajo de 0.300%.
- `put largo 95`: ventaja esperada no positiva (-0.2109); zona de no operación: la ventaja (-0.2109) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0412 = 0.0400 + 0.0012); la ventaja desaparece en el escenario «base» (-0.2109); rendimiento esperado sobre capital -23.701% por debajo de 0.300%.
- `put spread bajista 92/97`: ventaja esperada no positiva (-0.1944); zona de no operación: la ventaja (-0.1944) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0836 = 0.0800 + 0.0036); la ventaja desaparece en el escenario «base» (-0.1944); rendimiento esperado sobre capital -24.609% por debajo de 0.300%.
- `put largo 92`: ventaja esperada no positiva (-0.1410); zona de no operación: la ventaja (-0.1410) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0413 = 0.0350 + 0.0063); la ventaja desaparece en el escenario «base» (-0.1410); rendimiento esperado sobre capital -26.118% por debajo de 0.300%.
- `call largo 105`: ventaja esperada no positiva (-0.0868); zona de no operación: la ventaja (-0.0868) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0320 = 0.0300 + 0.0020); la ventaja desaparece en el escenario «base» (-0.0868); rendimiento esperado sobre capital -26.304% por debajo de 0.300%.
- `put spread bajista 94/97`: ventaja esperada no positiva (-0.1741); zona de no operación: la ventaja (-0.1741) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «base» (-0.1741); rendimiento esperado sobre capital -29.018% por debajo de 0.300%.
- `put spread bajista 90/95`: ventaja esperada no positiva (-0.1807); zona de no operación: la ventaja (-0.1807) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0808 = 0.0750 + 0.0058); la ventaja desaparece en el escenario «base» (-0.1807); rendimiento esperado sobre capital -31.147% por debajo de 0.300%.
- `put spread bajista 92/95`: ventaja esperada no positiva (-0.1399); zona de no operación: la ventaja (-0.1399) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «base» (-0.1399); rendimiento esperado sobre capital -33.309% por debajo de 0.300%.
- `call spread alcista 105/108`: ventaja esperada no positiva (-0.1096); zona de no operación: la ventaja (-0.1096) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0634 = 0.0600 + 0.0034); la ventaja desaparece en el escenario «base» (-0.1096); rendimiento esperado sobre capital -34.257% por debajo de 0.300%.
- `put spread bajista 87/92`: ventaja esperada no positiva (-0.1246); zona de no operación: la ventaja (-0.1246) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «base» (-0.1246); rendimiento esperado sobre capital -34.600% por debajo de 0.300%.
- `put spread bajista 89/92`: ventaja esperada no positiva (-0.1151); zona de no operación: la ventaja (-0.1151) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «base» (-0.1151); rendimiento esperado sobre capital -41.103% por debajo de 0.300%.
- `call largo 108`: ventaja esperada no positiva (-0.0372); zona de no operación: la ventaja (-0.0372) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0354 = 0.0300 + 0.0054); la ventaja desaparece en el escenario «base» (-0.0372); rendimiento esperado sobre capital -53.119% por debajo de 0.300%.
- `forward corto`: ventaja esperada no positiva (-0.0601); zona de no operación: la ventaja (-0.0601) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0601 = 0.0599 + 0.0001); la ventaja desaparece en el escenario «base» (-0.0601); pérdida no acotada por arriba; capital inmovilizado no acotado: hace falta un margen declarado.

## Lo que este informe no dice

- **No hay evidencia de que la vista acierte.** La ventaja es una resta entre lo que dice la vista y lo que dice el precio; si la vista está mal, el signo se invierte.
- **El CVaR y la pérdida máxima se calculan bajo la vista**, que es justamente la parte optimista del cálculo. La pérdida real de un put vendido llega cuando la vista falla.
- **El capital es una regla propia** (peor caso en valor presente), no el margen que exigiría un intermediario, que depende de su propio modelo y puede cambiar intradía.
- **La probabilidad de ganar no es un criterio.** Un put muy fuera del dinero gana casi siempre y eso ya está en su precio; se reporta porque se suele mirar.
- No hay ejecución, ni gestión de la posición antes del vencimiento, ni asignación anticipada, ni dividendos, ni impuestos, ni límite de concentración entre vencimientos.
