# Estrategias con puts: Vista alcista con la dispersión del mercado: solo dirección, al mismo presupuesto de información

> **DATOS SINTÉTICOS.** Las cotizaciones las genera el propio código. Este documento es la plantilla del informe: sus cifras no dicen nada sobre ningún activo real, y en ningún caso son una recomendación de inversión.

- Configuración: `estrategias-0.1`; ejecución **adverso**, comisión 0.01 por pata y unidad.
- Vencimiento: 30.0 días; forward 100.2222; descuento 0.996718; 62 de 78 cotizaciones utilizables.
- Rango de strikes respaldado por cotizaciones: [78.00, 108.00], es decir [0.778, 1.078] en unidades del forward.
- `Q`: Q implícita (ajuste SSVI de la rebanada). `P`: tilt de momentos (+0.82% sobre el forward, volatilidad x1.00).

## Dictamen

**OPERAR.** Vender puts: reversal de riesgo -97p/+103c. Ventaja esperada +0.3742 por unidad (+0.39% sobre un capital de 96.37); en el peor escenario, +0.1464.

## En qué discrepa la vista del mercado

- Rendimiento esperado sobre el forward: **+0.82%**.
- Desviación típica de `ln(S_T/F)`: vista 0.0628 frente a implícita 0.0628 (factor 1.000).
- Asimetría: vista -2.831 frente a implícita -1.995.
- Probabilidad de caer un 5 %: vista 12.00% frente a implícita 15.71%. De caer un 10 %: 4.85% frente a 6.44%.
- Entropía relativa `KL(P||Q)`: **0.01536** nats (máximo admitido 0.02).

Toda la ventaja de cualquier estructura sale de estas diferencias. Si la vista fuera `P = Q`, la columna de ventaja sería exactamente cero antes de costos y negativa después.

### Ventaja de vender exposición a la caída, por tramo de precio

Cada fila es `D * int (F_Q - F_P) ds` sobre el tramo: positivo significa que el mercado asigna más probabilidad acumulada que la vista a esa zona, de modo que **vender** la caída dentro de ese tramo tiene ventaja. Es la descomposición que decide qué strike expresa la opinión.

| Desde | Hasta | Prob. Q | Prob. P | Ventaja |
|---|---|---|---|---|
| 80.18 | 90.20 | 0.0534 | 0.0380 | +0.06172 |
| 90.20 | 95.21 | 0.0926 | 0.0715 | +0.12761 |
| 95.21 | 97.72 | 0.0920 | 0.0775 | +0.11024 |
| 97.72 | 100.22 | 0.1493 | 0.1364 | +0.14566 |
| 100.22 | 102.73 | 0.2162 | 0.2160 | +0.16526 |
| 102.73 | 105.23 | 0.2315 | 0.2548 | +0.13615 |
| 105.23 | 110.24 | 0.1472 | 0.1843 | +0.08925 |
| 110.24 | 120.27 | 0.0068 | 0.0110 | +0.00734 |

![Distribuciones](distribuciones.png)

La vista frente a la implícita. La banda marca el rango de strikes con cotizaciones utilizables: fuera de ella la forma de ambas distribuciones es extrapolación.

![Ventaja por strike](ventaja_por_strike.png)

Ventaja de vender un put de cada strike. Su máximo señala dónde la discrepancia pesa más en prima; fuera de la banda, la curva depende de lo que nadie cotiza.

## Candidatas

Escenarios de robustez: base, ejecución al mid, convicción a la mitad, dirección con la dispersión de Q, otra estimación de Q. La columna «peor» es la ventaja mínima entre ellos. «No fiable» es la parte de la ventaja que procede de la zona sin cotizaciones utilizables.

| Estructura | Papel | Ventaja | Peor | Capital | Sobre capital | CVaR | No fiable |
|---|---|---|---|---|---|---|---|
| reversal de riesgo -97p/+103c | vender puts | +0.3742 | +0.1464 | 96.37 | +0.388% | 13.01 | +16% |
| put spread alcista 92/97 | vender puts | +0.0850 | +0.0007 | 4.35 | +1.953% | 4.37 | -3% |
| collar 97/103 | comprar puts | +0.2150 | +0.0333 | 100.43 | +0.214% | 3.76 | +657% |
| put protectora 97 | comprar puts | +0.4714 | +0.1819 | 101.21 | +0.466% | 4.55 | +319% |
| put protectora 95 | comprar puts | +0.5606 | +0.2298 | 100.84 | +0.556% | 6.18 | +268% |
| collar 95/105 | comprar puts | +0.4221 | +0.1446 | 100.57 | +0.420% | 5.90 | +341% |
| put protectora 92 | comprar puts | +0.6464 | +0.2726 | 100.49 | +0.643% | 8.82 | +232% |
| collar 92/108 | comprar puts | +0.5858 | +0.2246 | 100.48 | +0.583% | 8.81 | +252% |
| put corto 92 | vender puts | +0.0428 | +0.0071 | 91.23 | +0.047% | 7.84 | -71% |
| reversal de riesgo -92p/+108c | vender puts | +0.0434 | -0.0050 | 91.30 | +0.048% | 7.91 | -12% |
| put corto 95 | vender puts | +0.1186 | +0.0399 | 93.88 | +0.126% | 10.50 | -27% |
| reversal de riesgo -95p/+105c | vender puts | +0.1971 | +0.0651 | 94.21 | +0.209% | 10.83 | +17% |
| put corto 97 | vender puts | +0.1978 | +0.0778 | 95.51 | +0.207% | 12.14 | -16% |
| forward largo | sin puts | +0.7592 | +0.3497 | 99.95 | +0.760% | 16.60 | +194% |
| call largo 103 | sin puts | +0.1764 | +0.0686 | 0.86 | +20.506% | 0.86 | +52% |
| call largo 105 | sin puts | +0.0785 | +0.0252 | 0.33 | +23.789% | 0.33 | +83% |
| call spread alcista 103/108 | sin puts | +0.1158 | +0.0206 | 0.85 | +13.620% | 0.85 | +57% |
| put spread alcista 87/92 | vender puts | +0.0073 | -0.0285 | 4.75 | +0.153% | 3.98 | -30% |
| put spread alcista 90/95 | vender puts | +0.0539 | -0.0077 | 4.55 | +1.183% | 4.56 | -4% |
| call spread alcista 103/106 | sin puts | +0.0706 | -0.0028 | 0.73 | +9.672% | 0.73 | +57% |
| put spread alcista 94/97 | vender puts | +0.0445 | -0.0135 | 2.56 | +1.739% | 2.57 | -3% |
| put spread alcista 89/92 | vender puts | -0.0050 | -0.0306 | 2.84 | -0.178% | 2.70 | — |
| put spread alcista 92/95 | vender puts | +0.0058 | -0.0372 | 2.72 | +0.211% | 2.73 | -23% |
| call spread alcista 105/108 | sin puts | +0.0179 | -0.0227 | 0.32 | +5.600% | 0.32 | +223% |
| call largo 108 | sin puts | +0.0006 | -0.0120 | 0.07 | +0.834% | 0.07 | +4315% |
| put largo 92 | comprar puts | -0.1128 | -0.1128 | 0.54 | -20.891% | 0.54 | — |
| put largo 95 | comprar puts | -0.1986 | -0.1986 | 0.89 | -22.310% | 0.89 | — |
| put largo 97 | comprar puts | -0.2878 | -0.2878 | 1.26 | -22.843% | 1.26 | — |
| put spread bajista 92/97 | comprar puts | -0.2450 | -0.2450 | 0.79 | -31.014% | 0.79 | — |
| put spread bajista 90/95 | comprar puts | -0.2039 | -0.2039 | 0.58 | -35.149% | 0.58 | — |
| put spread bajista 94/97 | comprar puts | -0.2145 | -0.2145 | 0.60 | -35.755% | 0.60 | — |
| put spread bajista 92/95 | comprar puts | -0.1558 | -0.1558 | 0.42 | -37.084% | 0.42 | — |
| put spread bajista 87/92 | comprar puts | -0.1373 | -0.1373 | 0.36 | -38.127% | 0.36 | — |
| put spread bajista 89/92 | comprar puts | -0.1250 | -0.1250 | 0.28 | -44.625% | 0.28 | — |
| forward corto | sin puts | -0.8791 | -0.8791 | no acotado | — | 9.24 | — |

![Perfiles](perfiles.png)

Resultado al vencimiento de las candidatas principales, neto de la prima capitalizada.

![Ventaja y riesgo](ventaja_riesgo.png)

Ventaja esperada frente al CVaR de la pérdida. Las estructuras con más ventaja suelen ser también las de más cola: la puntuación penaliza el CVaR para no confundirlas.

## Vender o comprar puts

- Mejor forma de **vender** puts: `reversal de riesgo -97p/+103c` (alcista), ventaja +0.3742; pasa los filtros.
- Mejor forma de **comprar** puts: `collar 97/103` (cobertura), ventaja +0.2150; descartada (el 657% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%)).
- Mejor alternativa **sin** puts: `forward largo` (alcista), ventaja +0.7592; descartada (el 194% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%)).

## Descartes

- `collar 97/103`: el 657% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%); rendimiento esperado sobre capital 0.214% por debajo de 0.300%.
- `put protectora 97`: el 319% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put protectora 95`: el 268% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `collar 95/105`: el 341% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put protectora 92`: el 232% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `collar 92/108`: el 252% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put corto 92`: rendimiento esperado sobre capital 0.047% por debajo de 0.300%.
- `reversal de riesgo -92p/+108c`: zona de no operación: la ventaja (+0.0434) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0767 = 0.0650 + 0.0117); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0050); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital 0.048% por debajo de 0.300%.
- `put corto 95`: rendimiento esperado sobre capital 0.126% por debajo de 0.300%.
- `reversal de riesgo -95p/+105c`: rendimiento esperado sobre capital 0.209% por debajo de 0.300%.
- `put corto 97`: rendimiento esperado sobre capital 0.207% por debajo de 0.300%.
- `forward largo`: el 194% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 103`: el 52% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 105`: el 83% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call spread alcista 103/108`: el 57% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 87/92`: zona de no operación: la ventaja (+0.0073) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0285); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital 0.153% por debajo de 0.300%.
- `put spread alcista 90/95`: zona de no operación: la ventaja (+0.0539) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0808 = 0.0750 + 0.0058); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0077); el signo de la ventaja no es estable entre escenarios.
- `call spread alcista 103/106`: zona de no operación: la ventaja (+0.0706) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0761 = 0.0700 + 0.0061); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0028); el signo de la ventaja no es estable entre escenarios; el 57% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put spread alcista 94/97`: zona de no operación: la ventaja (+0.0445) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0135); el signo de la ventaja no es estable entre escenarios.
- `put spread alcista 89/92`: ventaja esperada no positiva (-0.0050); zona de no operación: la ventaja (-0.0050) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0306); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital -0.178% por debajo de 0.300%.
- `put spread alcista 92/95`: zona de no operación: la ventaja (+0.0058) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0372); el signo de la ventaja no es estable entre escenarios; rendimiento esperado sobre capital 0.211% por debajo de 0.300%.
- `call spread alcista 105/108`: zona de no operación: la ventaja (+0.0179) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0634 = 0.0600 + 0.0034); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0227); el signo de la ventaja no es estable entre escenarios; el 223% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `call largo 108`: zona de no operación: la ventaja (+0.0006) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0354 = 0.0300 + 0.0054); la ventaja desaparece en el escenario «convicción a la mitad» (-0.0120); el signo de la ventaja no es estable entre escenarios; el 4315% de la ventaja procede de la zona sin cotizaciones utilizables (máximo 35%).
- `put largo 92`: ventaja esperada no positiva (-0.1128); zona de no operación: la ventaja (-0.1128) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0413 = 0.0350 + 0.0063); la ventaja desaparece en el escenario «base» (-0.1128); rendimiento esperado sobre capital -20.891% por debajo de 0.300%.
- `put largo 95`: ventaja esperada no positiva (-0.1986); zona de no operación: la ventaja (-0.1986) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0412 = 0.0400 + 0.0012); la ventaja desaparece en el escenario «base» (-0.1986); rendimiento esperado sobre capital -22.310% por debajo de 0.300%.
- `put largo 97`: ventaja esperada no positiva (-0.2878); zona de no operación: la ventaja (-0.2878) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0477 = 0.0450 + 0.0027); la ventaja desaparece en el escenario «base» (-0.2878); rendimiento esperado sobre capital -22.843% por debajo de 0.300%.
- `put spread bajista 92/97`: ventaja esperada no positiva (-0.2450); zona de no operación: la ventaja (-0.2450) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0836 = 0.0800 + 0.0036); la ventaja desaparece en el escenario «base» (-0.2450); rendimiento esperado sobre capital -31.014% por debajo de 0.300%.
- `put spread bajista 90/95`: ventaja esperada no positiva (-0.2039); zona de no operación: la ventaja (-0.2039) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0808 = 0.0750 + 0.0058); la ventaja desaparece en el escenario «base» (-0.2039); rendimiento esperado sobre capital -35.149% por debajo de 0.300%.
- `put spread bajista 94/97`: ventaja esperada no positiva (-0.2145); zona de no operación: la ventaja (-0.2145) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0986 = 0.0850 + 0.0136); la ventaja desaparece en el escenario «base» (-0.2145); rendimiento esperado sobre capital -35.755% por debajo de 0.300%.
- `put spread bajista 92/95`: ventaja esperada no positiva (-0.1558); zona de no operación: la ventaja (-0.1558) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0801 = 0.0750 + 0.0051); la ventaja desaparece en el escenario «base» (-0.1558); rendimiento esperado sobre capital -37.084% por debajo de 0.300%.
- `put spread bajista 87/92`: ventaja esperada no positiva (-0.1373); zona de no operación: la ventaja (-0.1373) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0657 = 0.0650 + 0.0007); la ventaja desaparece en el escenario «base» (-0.1373); rendimiento esperado sobre capital -38.127% por debajo de 0.300%.
- `put spread bajista 89/92`: ventaja esperada no positiva (-0.1250); zona de no operación: la ventaja (-0.1250) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0739 = 0.0650 + 0.0089); la ventaja desaparece en el escenario «base» (-0.1250); rendimiento esperado sobre capital -44.625% por debajo de 0.300%.
- `forward corto`: ventaja esperada no positiva (-0.8791); zona de no operación: la ventaja (-0.8791) no supera 1 veces el coste de ejecución más el residuo del ajuste (0.0601 = 0.0599 + 0.0001); la ventaja desaparece en el escenario «base» (-0.8791); pérdida no acotada por arriba; capital inmovilizado no acotado: hace falta un margen declarado.

## Lo que este informe no dice

- **No hay evidencia de que la vista acierte.** La ventaja es una resta entre lo que dice la vista y lo que dice el precio; si la vista está mal, el signo se invierte.
- **El CVaR y la pérdida máxima se calculan bajo la vista**, que es justamente la parte optimista del cálculo. La pérdida real de un put vendido llega cuando la vista falla.
- **El capital es una regla propia** (peor caso en valor presente), no el margen que exigiría un intermediario, que depende de su propio modelo y puede cambiar intradía.
- **La probabilidad de ganar no es un criterio.** Un put muy fuera del dinero gana casi siempre y eso ya está en su precio; se reporta porque se suele mirar.
- No hay ejecución, ni gestión de la posición antes del vencimiento, ni asignación anticipada, ni dividendos, ni impuestos, ni límite de concentración entre vencimientos.
