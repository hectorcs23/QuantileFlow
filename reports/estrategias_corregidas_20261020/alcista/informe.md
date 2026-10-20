# Estrategias con puts: Vista alcista: +1 % sobre el forward, deformación mínima de Q

> **DATOS SINTÉTICOS.** Las cotizaciones las genera el propio código. Este documento es la plantilla del informe: sus cifras no dicen nada sobre ningún activo real, y en ningún caso son una recomendación de inversión.

- Configuración: `estrategias-0.1`; ejecución **adverso**, comisión 0.01 por pata y unidad.
- Vencimiento: 30.0 días; forward 100.2222; descuento 0.996718; 62 de 78 cotizaciones utilizables.
- Rango de strikes respaldado por cotizaciones: [78.00, 108.00], es decir [0.778, 1.078] en unidades del forward.
- `Q`: Q implícita (ajuste SSVI de la rebanada). `P`: tilt de media (+1.00% sobre el forward).

## Dictamen

**OPERAR.** Vender puts: put corto 95. Ventaja esperada +0.3065 por unidad (+0.33% sobre un capital de 93.88); en el peor escenario, +0.1338.

## En qué discrepa la vista del mercado

- Rendimiento esperado sobre el forward: **+1.00%**.
- Desviación típica de `ln(S_T/F)`: vista 0.0536 frente a implícita 0.0628 (factor 0.853).
- Asimetría: vista -1.805 frente a implícita -1.995.
- Probabilidad de caer un 5 %: vista 11.08% frente a implícita 15.71%. De caer un 10 %: 3.86% frente a 6.44%.
- Entropía relativa `KL(P||Q)`: **0.01560** nats (máximo admitido 0.02).

Toda la ventaja de cualquier estructura sale de estas diferencias. Si la vista fuera `P = Q`, la columna de ventaja sería exactamente cero antes de costos y negativa después.

### Ventaja de vender exposición a la caída, por tramo de precio

Cada fila es `D * int (F_Q - F_P) ds` sobre el tramo: positivo significa que el mercado asigna más probabilidad acumulada que la vista a esa zona, de modo que **vender** la caída dentro de ese tramo tiene ventaja. Es la descomposición que decide qué strike expresa la opinión.

| Desde | Hasta | Prob. Q | Prob. P | Ventaja |
|---|---|---|---|---|
| 80.18 | 90.20 | 0.0534 | 0.0338 | +0.14128 |
| 90.20 | 95.21 | 0.0926 | 0.0722 | +0.17742 |
| 95.21 | 97.72 | 0.0920 | 0.0803 | +0.13031 |
| 97.72 | 100.22 | 0.1493 | 0.1415 | +0.15597 |
| 100.22 | 102.73 | 0.2162 | 0.2219 | +0.16103 |
| 102.73 | 105.23 | 0.2315 | 0.2567 | +0.12088 |
| 105.23 | 110.24 | 0.1472 | 0.1790 | +0.07078 |
| 110.24 | 120.27 | 0.0068 | 0.0098 | +0.00487 |

![Distribuciones](distribuciones.png)

La vista frente a la implícita. La banda marca el rango de strikes con cotizaciones utilizables: fuera de ella la forma de ambas distribuciones es extrapolación.

![Ventaja por strike](ventaja_por_strike.png)

Ventaja de vender un put de cada strike. Su máximo señala dónde la discrepancia pesa más en prima; fuera de la banda, la curva depende de lo que nadie cotiza.

## Candidatas

Escenarios de robustez: base, ejecución al mid, convicción a la mitad, dirección con la dispersión de Q, otra estimación de Q. La columna «peor» es la ventaja mínima entre ellos. «No fiable» es la parte de la ventaja que procede de la zona sin cotizaciones utilizables.

| Estructura | Papel | Ventaja | Peor | Capital | Sobre capital | CVaR | No fiable |
|---|---|---|---|---|---|---|---|
| put corto 95 | vender puts | +0.3065 | +0.1338 | 93.88 | +0.326% | 7.55 | +32% |
| put corto 97 | vender puts | +0.4028 | +0.1803 | 95.51 | +0.422% | 9.19 | +27% |
| reversal de riesgo -97p/+103c | vender puts | +0.5442 | +0.2314 | 96.37 | +0.565% | 10.05 | +32% |
| put spread alcista 92/97 | vender puts | +0.1318 | +0.0241 | 4.35 | +3.027% | 4.37 | +17% |
| put spread alcista 90/95 | vender puts | +0.1037 | +0.0173 | 4.55 | +2.277% | 4.38 | +21% |
| collar 97/103 | comprar puts | +0.2248 | +0.0381 | 100.43 | +0.224% | 3.76 | +273% |
| put protectora 97 | comprar puts | +0.4462 | +0.1693 | 101.21 | +0.441% | 4.55 | +153% |
| put protectora 95 | comprar puts | +0.5525 | +0.2257 | 100.84 | +0.548% | 6.18 | +125% |
| collar 95/105 | comprar puts | +0.4365 | +0.1517 | 100.57 | +0.434% | 5.90 | +147% |
| put protectora 92 | comprar puts | +0.6680 | +0.2834 | 100.49 | +0.665% | 8.82 | +105% |
| collar 92/108 | comprar puts | +0.6146 | +0.2390 | 100.48 | +0.612% | 8.81 | +112% |
| put corto 92 | vender puts | +0.2010 | +0.0590 | 91.23 | +0.220% | 4.89 | +43% |
| reversal de riesgo -92p/+108c | vender puts | +0.1944 | +0.0664 | 91.30 | +0.213% | 4.96 | +54% |
| reversal de riesgo -95p/+105c | vender puts | +0.3625 | +0.1478 | 94.21 | +0.385% | 7.88 | +41% |
| forward largo | sin puts | +0.9390 | +0.4396 | 99.95 | +0.939% | 13.64 | +84% |
| call largo 103 | sin puts | +0.1414 | +0.0512 | 0.86 | +16.447% | 0.86 | +48% |
| call largo 105 | sin puts | +0.0560 | +0.0140 | 0.33 | +16.976% | 0.33 | +86% |
| put spread alcista 87/92 | vender puts | +0.0555 | -0.0044 | 4.75 | +1.168% | 3.24 | +40% |
| call spread alcista 103/108 | sin puts | +0.0881 | +0.0068 | 0.85 | +10.360% | 0.85 | +57% |
| put spread alcista 89/92 | vender puts | +0.0248 | -0.0157 | 2.84 | +0.873% | 2.33 | +53% |
| put spread alcista 94/97 | vender puts | +0.0712 | -0.0001 | 2.56 | +2.780% | 2.57 | +19% |
| put spread alcista 92/95 | vender puts | +0.0355 | -0.0223 | 2.72 | +1.304% | 2.73 | +37% |
| call spread alcista 103/106 | sin puts | +0.0519 | -0.0121 | 0.73 | +7.114% | 0.73 | +58% |
| call spread alcista 105/108 | sin puts | +0.0026 | -0.0304 | 0.32 | +0.823% | 0.32 | +1150% |
| call largo 108 | sin puts | -0.0066 | -0.0156 | 0.07 | -9.447% | 0.07 | — |
| put spread bajista 92/97 | comprar puts | -0.2918 | -0.2918 | 0.79 | -36.933% | 0.79 | — |
| put largo 97 | comprar puts | -0.4928 | -0.4928 | 1.26 | -39.110% | 1.26 | — |
| put spread bajista 94/97 | comprar puts | -0.2412 | -0.2412 | 0.60 | -40.194% | 0.60 | — |
| put largo 95 | comprar puts | -0.3865 | -0.3865 | 0.89 | -43.426% | 0.89 | — |
| put spread bajista 90/95 | comprar puts | -0.2537 | -0.2537 | 0.58 | -43.742% | 0.58 | — |
| put spread bajista 92/95 | comprar puts | -0.1855 | -0.1855 | 0.42 | -44.162% | 0.42 | — |
| put largo 92 | comprar puts | -0.2710 | -0.2710 | 0.54 | -50.188% | 0.54 | — |
| put spread bajista 87/92 | comprar puts | -0.1855 | -0.1855 | 0.36 | -51.529% | 0.36 | — |
| put spread bajista 89/92 | comprar puts | -0.1548 | -0.1548 | 0.28 | -55.282% | 0.28 | — |
| forward corto | sin puts | -1.0589 | -1.0589 | no acotado | — | 9.08 | — |

![Perfiles](perfiles.png)

Resultado al vencimiento de las candidatas principales, neto de la prima capitalizada.

![Ventaja y riesgo](ventaja_riesgo.png)

Ventaja esperada frente al CVaR de la pérdida. Las estructuras con más ventaja suelen ser también las de más cola: la puntuación penaliza el CVaR para no confundirlas.

## Vender o comprar puts

- Mejor forma de **vender** puts: `put corto 95` (alcista), ventaja +0.3065; pasa los filtros.
- Mejor forma de **comprar** puts: `collar 97/103` (cobertura), ventaja +0.2248; descartada (el 273% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%)).
- Mejor alternativa **sin** puts: `forward largo` (alcista), ventaja +0.9390; descartada (el 84% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%)).

## Descartes

- `collar 97/103`: el 273% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.224% por debajo de 0.300%.
- `put protectora 97`: el 153% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put protectora 95`: el 125% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `collar 95/105`: el 147% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put protectora 92`: el 105% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `collar 92/108`: el 112% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put corto 92`: el 43% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.220% por debajo de 0.300%.
- `reversal de riesgo -92p/+108c`: el 54% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.213% por debajo de 0.300%.
- `reversal de riesgo -95p/+105c`: el 41% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `forward largo`: el 84% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 103`: el 48% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 105`: el 86% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 87/92`: zona de no operación: la ventaja (+0.0555) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0044); el signo de la ventaja no es estable entre escenarios; el 40% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call spread alcista 103/108`: el 57% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 89/92`: zona de no operación: la ventaja (+0.0248) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0157); el signo de la ventaja no es estable entre escenarios; el 53% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 94/97`: zona de no operación: la ventaja (+0.0712) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0001); el signo de la ventaja no es estable entre escenarios.
- `put spread alcista 92/95`: zona de no operación: la ventaja (+0.0355) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0223); el signo de la ventaja no es estable entre escenarios; el 37% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call spread alcista 103/106`: zona de no operación: la ventaja (+0.0519) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0761 = 0.0700 + 0.0061); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0121); el signo de la ventaja no es estable entre escenarios; el 58% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call spread alcista 105/108`: zona de no operación: la ventaja (+0.0026) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0634 = 0.0600 + 0.0034); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0304); el signo de la ventaja no es estable entre escenarios; el 1150% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 108`: ventaja esperada no positiva (-0.0066); zona de no operación: la ventaja (-0.0066) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0354 = 0.0300 + 0.0054); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0156); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital -9.447% por debajo de 0.300%.
- `put spread bajista 92/97`: ventaja esperada no positiva (-0.2918); zona de no operación: la ventaja (-0.2918) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0836 = 0.0800 + 0.0036); la ventaja desaparece en el escenario «base» (-0.2918); rendimiento esperado sobre capital -36.933% por debajo de 0.300%.
- `put largo 97`: ventaja esperada no positiva (-0.4928); zona de no operación: la ventaja (-0.4928) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0477 = 0.0450 + 0.0027); la ventaja desaparece en el escenario «base» (-0.4928); rendimiento esperado sobre capital -39.110% por debajo de 0.300%.
- `put spread bajista 94/97`: ventaja esperada no positiva (-0.2412); zona de no operación: la ventaja (-0.2412) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «base» (-0.2412); rendimiento esperado sobre capital -40.194% por debajo de 0.300%.
- `put largo 95`: ventaja esperada no positiva (-0.3865); zona de no operación: la ventaja (-0.3865) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0412 = 0.0400 + 0.0012); la ventaja desaparece en el escenario «base» (-0.3865); rendimiento esperado sobre capital -43.426% por debajo de 0.300%.
- `put spread bajista 90/95`: ventaja esperada no positiva (-0.2537); zona de no operación: la ventaja (-0.2537) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0808 = 0.0750 + 0.0058); la ventaja desaparece en el escenario «base» (-0.2537); rendimiento esperado sobre capital -43.742% por debajo de 0.300%.
- `put spread bajista 92/95`: ventaja esperada no positiva (-0.1855); zona de no operación: la ventaja (-0.1855) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «base» (-0.1855); rendimiento esperado sobre capital -44.162% por debajo de 0.300%.
- `put largo 92`: ventaja esperada no positiva (-0.2710); zona de no operación: la ventaja (-0.2710) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0413 = 0.0350 + 0.0063); la ventaja desaparece en el escenario «base» (-0.2710); rendimiento esperado sobre capital -50.188% por debajo de 0.300%.
- `put spread bajista 87/92`: ventaja esperada no positiva (-0.1855); zona de no operación: la ventaja (-0.1855) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «base» (-0.1855); rendimiento esperado sobre capital -51.529% por debajo de 0.300%.
- `put spread bajista 89/92`: ventaja esperada no positiva (-0.1548); zona de no operación: la ventaja (-0.1548) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «base» (-0.1548); rendimiento esperado sobre capital -55.282% por debajo de 0.300%.
- `forward corto`: ventaja esperada no positiva (-1.0589); zona de no operación: la ventaja (-1.0589) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0601 = 0.0599 + 0.0001); la ventaja desaparece en el escenario «dirección con la dispersión de Q» (-1.0589); pérdida no acotada por arriba; capital inmovilizado no acotado: hace falta un margen declarado.

## Lo que este informe no dice

- **No hay evidencia de que la vista acierte.** La ventaja es una resta entre lo que dice la vista y lo que dice el precio; si la vista está mal, el signo se invierte.
- **El CVaR y la pérdida máxima se calculan bajo la vista**, que es justamente la parte optimista del cálculo. La pérdida real de un put vendido llega cuando la vista falla.
- **El capital es una regla propia** (peor caso en valor presente), no el margen que exigiría un intermediario, que depende de su propio modelo y puede cambiar intradía.
- **La probabilidad de ganar no es un criterio.** Un put muy fuera del dinero gana casi siempre y eso ya está en su precio; se reporta porque se suele mirar.
- No hay ejecución, ni gestión de la posición antes del vencimiento, ni asignación anticipada, ni dividendos, ni impuestos, ni límite de concentración entre vencimientos.
