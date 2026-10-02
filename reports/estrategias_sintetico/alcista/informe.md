# Estrategias con puts: Vista alcista: +1 % sobre el forward, deformación mínima de Q

> **DATOS SINTÉTICOS.** Las cotizaciones las genera el propio código. Este documento es la plantilla del informe: sus cifras no dicen nada sobre ningún activo real, y en ningún caso son una recomendación de inversión.

- Configuración: `estrategias-0.1`; ejecución **adverso**, comisión 0.01 por pata y unidad.
- Vencimiento: 30.0 días; forward 100.2222; descuento 0.996718; 62 de 78 cotizaciones utilizables.
- Rango de strikes respaldado por cotizaciones: [78.00, 108.00], es decir [0.778, 1.078] en unidades del forward.
- `Q`: Q implícita (ajuste SSVI de la rebanada). `P`: tilt de media (+1.00% sobre el forward).

## Dictamen

**OPERAR.** Vender puts: put corto 95. Ventaja esperada +0.3195 por unidad (+0.34% sobre un capital de 93.88); en el peor escenario, +0.1403.

## En qué discrepa la vista del mercado

- Rendimiento esperado sobre el forward: **+1.00%**.
- Desviación típica de `ln(S_T/F)`: vista 0.0530 frente a implícita 0.0628 (factor 0.843).
- Asimetría: vista -1.742 frente a implícita -1.995.
- Probabilidad de caer un 5 %: vista 11.02% frente a implícita 15.71%. De caer un 10 %: 3.77% frente a 6.44%.
- Entropía relativa `KL(P||Q)`: **0.01564** nats (máximo admitido 0.02).

Toda la ventaja de cualquier estructura sale de estas diferencias. Si la vista fuera `P = Q`, la columna de ventaja sería exactamente cero antes de costos y negativa después.

### Ventaja de vender exposición a la caída, por tramo de precio

Cada fila es `D * int (F_Q - F_P) ds` sobre el tramo: positivo significa que el mercado asigna más probabilidad acumulada que la vista a esa zona, de modo que **vender** la caída dentro de ese tramo tiene ventaja. Es la descomposición que decide qué strike expresa la opinión.

| Desde | Hasta | Prob. Q | Prob. P | Ventaja |
|---|---|---|---|---|
| 80.18 | 90.20 | 0.0534 | 0.0333 | +0.14781 |
| 90.20 | 95.21 | 0.0926 | 0.0725 | +0.18126 |
| 95.21 | 97.72 | 0.0920 | 0.0809 | +0.13104 |
| 97.72 | 100.22 | 0.1493 | 0.1424 | +0.15486 |
| 100.22 | 102.73 | 0.2162 | 0.2228 | +0.15756 |
| 102.73 | 105.23 | 0.2315 | 0.2566 | +0.11630 |
| 105.23 | 110.24 | 0.1472 | 0.1776 | +0.06654 |
| 110.24 | 120.27 | 0.0068 | 0.0095 | +0.00439 |

![Distribuciones](distribuciones.png)

La vista frente a la implícita. La banda marca el rango de strikes con cotizaciones utilizables: fuera de ella la forma de ambas distribuciones es extrapolación.

![Ventaja por strike](ventaja_por_strike.png)

Ventaja de vender un put de cada strike. Su máximo señala dónde la discrepancia pesa más en prima; fuera de la banda, la curva depende de lo que nadie cotiza.

## Candidatas

Escenarios de robustez: base, ejecución al mid, convicción a la mitad, dirección con la dispersión de Q, otra estimación de Q. La columna «peor» es la ventaja mínima entre ellos. «No fiable» es la parte de la ventaja que procede de la zona sin cotizaciones utilizables.

| Estructura | Papel | Ventaja | Peor | Capital | Sobre capital | CVaR | No fiable |
|---|---|---|---|---|---|---|---|
| put corto 95 | vender puts | +0.3195 | +0.1403 | 93.88 | +0.340% | 7.34 | +33% |
| put corto 97 | vender puts | +0.4166 | +0.1872 | 95.51 | +0.436% | 8.98 | +28% |
| reversal de riesgo -97p/+103c | vender puts | +0.5492 | +0.2340 | 96.37 | +0.570% | 9.84 | +33% |
| put spread alcista 92/97 | vender puts | +0.1348 | +0.0256 | 4.35 | +3.095% | 4.37 | +17% |
| put spread alcista 90/95 | vender puts | +0.1076 | +0.0192 | 4.55 | +2.363% | 4.35 | +22% |
| collar 97/103 | comprar puts | +0.2197 | +0.0356 | 100.43 | +0.219% | 3.76 | +233% |
| put protectora 97 | comprar puts | +0.4324 | +0.1624 | 101.21 | +0.427% | 4.55 | +133% |
| put protectora 95 | comprar puts | +0.5395 | +0.2192 | 100.84 | +0.535% | 6.18 | +108% |
| collar 95/105 | comprar puts | +0.4285 | +0.1478 | 100.57 | +0.426% | 5.90 | +126% |
| put protectora 92 | comprar puts | +0.6571 | +0.2780 | 100.49 | +0.654% | 8.82 | +91% |
| collar 92/108 | comprar puts | +0.6052 | +0.2344 | 100.48 | +0.602% | 8.81 | +96% |
| put corto 92 | vender puts | +0.2118 | +0.0590 | 91.23 | +0.232% | 4.68 | +44% |
| reversal de riesgo -92p/+108c | vender puts | +0.2038 | +0.0664 | 91.30 | +0.223% | 4.75 | +54% |
| reversal de riesgo -95p/+105c | vender puts | +0.3704 | +0.1518 | 94.21 | +0.393% | 7.67 | +41% |
| forward largo | sin puts | +0.9390 | +0.4396 | 99.95 | +0.939% | 13.44 | +74% |
| call largo 103 | sin puts | +0.1326 | +0.0468 | 0.86 | +15.424% | 0.86 | +48% |
| put spread alcista 87/92 | vender puts | +0.0596 | -0.0023 | 4.75 | +1.254% | 3.16 | +39% |
| call largo 105 | sin puts | +0.0509 | +0.0114 | 0.33 | +15.428% | 0.33 | +88% |
| put spread alcista 89/92 | vender puts | +0.0273 | -0.0144 | 2.84 | +0.962% | 2.29 | +52% |
| call spread alcista 103/108 | sin puts | +0.0807 | +0.0031 | 0.85 | +9.497% | 0.85 | +58% |
| put spread alcista 94/97 | vender puts | +0.0726 | +0.0006 | 2.56 | +2.836% | 2.57 | +19% |
| put spread alcista 92/95 | vender puts | +0.0377 | -0.0212 | 2.72 | +1.385% | 2.73 | +37% |
| call spread alcista 103/106 | sin puts | +0.0467 | -0.0147 | 0.73 | +6.393% | 0.73 | +60% |
| call spread alcista 105/108 | sin puts | -0.0010 | -0.0322 | 0.32 | -0.314% | 0.32 | — |
| call largo 108 | sin puts | -0.0081 | -0.0163 | 0.07 | -11.548% | 0.07 | — |
| put spread bajista 92/97 | comprar puts | -0.2948 | -0.2948 | 0.79 | -37.311% | 0.79 | — |
| put largo 97 | comprar puts | -0.5066 | -0.5066 | 1.26 | -40.207% | 1.26 | — |
| put spread bajista 94/97 | comprar puts | -0.2426 | -0.2426 | 0.60 | -40.433% | 0.60 | — |
| put spread bajista 90/95 | comprar puts | -0.2576 | -0.2576 | 0.58 | -44.412% | 0.58 | — |
| put spread bajista 92/95 | comprar puts | -0.1877 | -0.1877 | 0.42 | -44.685% | 0.42 | — |
| put largo 95 | comprar puts | -0.3995 | -0.3995 | 0.89 | -44.890% | 0.89 | — |
| put largo 92 | comprar puts | -0.2818 | -0.2818 | 0.54 | -52.194% | 0.54 | — |
| put spread bajista 87/92 | comprar puts | -0.1896 | -0.1896 | 0.36 | -52.671% | 0.36 | — |
| put spread bajista 89/92 | comprar puts | -0.1573 | -0.1573 | 0.28 | -56.185% | 0.28 | — |
| forward corto | sin puts | -1.0589 | -1.0589 | no acotado | — | 9.05 | — |

![Perfiles](perfiles.png)

Resultado al vencimiento de las candidatas principales, neto de la prima capitalizada.

![Ventaja y riesgo](ventaja_riesgo.png)

Ventaja esperada frente al CVaR de la pérdida. Las estructuras con más ventaja suelen ser también las de más cola: la puntuación penaliza el CVaR para no confundirlas.

## Vender o comprar puts

- Mejor forma de **vender** puts: `put corto 95` (alcista), ventaja +0.3195; pasa los filtros.
- Mejor forma de **comprar** puts: `collar 97/103` (cobertura), ventaja +0.2197; descartada (el 233% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%)).
- Mejor alternativa **sin** puts: `forward largo` (alcista), ventaja +0.9390; descartada (el 74% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%)).

## Descartes

- `collar 97/103`: el 233% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.219% por debajo de 0.300%.
- `put protectora 97`: el 133% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put protectora 95`: el 108% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `collar 95/105`: el 126% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put protectora 92`: el 91% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `collar 92/108`: el 96% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put corto 92`: el 44% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.232% por debajo de 0.300%.
- `reversal de riesgo -92p/+108c`: el 54% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.223% por debajo de 0.300%.
- `reversal de riesgo -95p/+105c`: el 41% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `forward largo`: el 74% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 103`: el 48% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 87/92`: zona de no operación: la ventaja (+0.0596) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0023); el signo de la ventaja no es estable entre escenarios; el 39% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 105`: el 88% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 89/92`: zona de no operación: la ventaja (+0.0273) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0144); el signo de la ventaja no es estable entre escenarios; el 52% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call spread alcista 103/108`: el 58% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 94/97`: zona de no operación: la ventaja (+0.0726) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136).
- `put spread alcista 92/95`: zona de no operación: la ventaja (+0.0377) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0212); el signo de la ventaja no es estable entre escenarios; el 37% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call spread alcista 103/106`: zona de no operación: la ventaja (+0.0467) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0761 = 0.0700 + 0.0061); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0147); el signo de la ventaja no es estable entre escenarios; el 60% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call spread alcista 105/108`: ventaja esperada no positiva (-0.0010); zona de no operación: la ventaja (-0.0010) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0634 = 0.0600 + 0.0034); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0322); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital -0.314% por debajo de 0.300%.
- `call largo 108`: ventaja esperada no positiva (-0.0081); zona de no operación: la ventaja (-0.0081) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0354 = 0.0300 + 0.0054); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0163); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital -11.548% por debajo de 0.300%.
- `put spread bajista 92/97`: ventaja esperada no positiva (-0.2948); zona de no operación: la ventaja (-0.2948) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0836 = 0.0800 + 0.0036); la ventaja desaparece en el escenario «base» (-0.2948); rendimiento esperado sobre capital -37.311% por debajo de 0.300%.
- `put largo 97`: ventaja esperada no positiva (-0.5066); zona de no operación: la ventaja (-0.5066) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0477 = 0.0450 + 0.0027); la ventaja desaparece en el escenario «base» (-0.5066); rendimiento esperado sobre capital -40.207% por debajo de 0.300%.
- `put spread bajista 94/97`: ventaja esperada no positiva (-0.2426); zona de no operación: la ventaja (-0.2426) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «base» (-0.2426); rendimiento esperado sobre capital -40.433% por debajo de 0.300%.
- `put spread bajista 90/95`: ventaja esperada no positiva (-0.2576); zona de no operación: la ventaja (-0.2576) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0808 = 0.0750 + 0.0058); la ventaja desaparece en el escenario «base» (-0.2576); rendimiento esperado sobre capital -44.412% por debajo de 0.300%.
- `put spread bajista 92/95`: ventaja esperada no positiva (-0.1877); zona de no operación: la ventaja (-0.1877) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «base» (-0.1877); rendimiento esperado sobre capital -44.685% por debajo de 0.300%.
- `put largo 95`: ventaja esperada no positiva (-0.3995); zona de no operación: la ventaja (-0.3995) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0412 = 0.0400 + 0.0012); la ventaja desaparece en el escenario «base» (-0.3995); rendimiento esperado sobre capital -44.890% por debajo de 0.300%.
- `put largo 92`: ventaja esperada no positiva (-0.2818); zona de no operación: la ventaja (-0.2818) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0413 = 0.0350 + 0.0063); la ventaja desaparece en el escenario «base» (-0.2818); rendimiento esperado sobre capital -52.194% por debajo de 0.300%.
- `put spread bajista 87/92`: ventaja esperada no positiva (-0.1896); zona de no operación: la ventaja (-0.1896) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «base» (-0.1896); rendimiento esperado sobre capital -52.671% por debajo de 0.300%.
- `put spread bajista 89/92`: ventaja esperada no positiva (-0.1573); zona de no operación: la ventaja (-0.1573) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «base» (-0.1573); rendimiento esperado sobre capital -56.185% por debajo de 0.300%.
- `forward corto`: ventaja esperada no positiva (-1.0589); zona de no operación: la ventaja (-1.0589) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0601 = 0.0599 + 0.0001); la ventaja desaparece en el escenario «base» (-1.0589); pérdida no acotada por arriba; capital inmovilizado no acotado: hace falta un margen declarado.

## Lo que este informe no dice

- **No hay evidencia de que la vista acierte.** La ventaja es una resta entre lo que dice la vista y lo que dice el precio; si la vista está mal, el signo se invierte.
- **El CVaR y la pérdida máxima se calculan bajo la vista**, que es justamente la parte optimista del cálculo. La pérdida real de un put vendido llega cuando la vista falla.
- **El capital es una regla propia** (peor caso en valor presente), no el margen que exigiría un intermediario, que depende de su propio modelo y puede cambiar intradía.
- **La probabilidad de ganar no es un criterio.** Un put muy fuera del dinero gana casi siempre y eso ya está en su precio; se reporta porque se suele mirar.
- No hay ejecución, ni gestión de la posición antes del vencimiento, ni asignación anticipada, ni dividendos, ni impuestos, ni límite de concentración entre vencimientos.
