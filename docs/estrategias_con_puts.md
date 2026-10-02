# Estrategias con puts: cuándo venderlos, cuándo comprarlos y cuándo no hacer nada

**Fecha:** 2 de octubre de 2026.
**Alcance:** subproyecto `estrategias/`, construido sobre el núcleo de `quantileflow`.
**Estado:** versión de investigación. No hay datos de mercado, no hay resultados empíricos y
nada de lo que produce es una recomendación de inversión.

## 1. La pregunta

La idea de partida es: *«cuando piense que algo va a subir, vender puts»*. Es una intuición
correcta en su dirección y, como regla, insuficiente. Este documento explica por qué, qué hay que
añadirle para que se sostenga, y cómo el código la convierte en un criterio verificable.

## 2. El principio que lo ordena todo

Sea `Q` la distribución implícita en los precios de las opciones y `D` el factor de descuento.
Por construcción, el precio de cualquier estructura europea es `D * E_Q[pago]`. Por lo tanto:

> **Bajo `Q`, ninguna estructura tiene ventaja esperada.** Vender puts, comprarlos, hacer spreads
> o comprar el subyacente tienen todos valor esperado cero antes de costos, y negativo después.

Esto no es una opinión: es la definición de `Q`. Cualquier afirmación del tipo «vender puts gana el
90 % de las veces» es verdadera y vacía, porque ese 90 % ya está en la prima. La ventaja solo puede
venir de una distribución distinta, `P`, y de la diferencia concreta entre `P` y `Q`.

Por eso el subproyecto no acepta una vista cualquiera: la construye **deformando `Q`** lo menos
posible para que cumpla lo que uno afirma, y mide ese «lo menos posible» con la entropía relativa
`KL(P||Q)`. Si la deformación es grande, la recomendación la produce la opinión, no el dato, y el
programa lo dice y se abstiene.

## 3. La identidad que contesta la pregunta

Para cualquier distribución, `E[(K - S)^+] = int_0^K F(s) ds`. Aplicado a la venta de un put de
strike `K` montado a su precio justo:

```
ventaja(vender un put K) = D * ( E_Q[(K-S)^+] - E_P[(K-S)^+] )
                         = D * int_0^K ( F_Q(s) - F_P(s) ) ds
```

Es decir:

> **Vender un put de strike `K` tiene ventaja si, y solo si, tu función de distribución acumulada
> está por debajo de la del mercado en el tramo que hay bajo `K`.**

No «si crees que sube». Si crees que la probabilidad acumulada de caer por debajo de ese nivel es
menor que la que el precio está cotizando. Comprar el put es la afirmación contraria. Un put spread
mide lo mismo sobre un tramo acotado, `D * int_{K1}^{K2} (F_Q - F_P) ds`, y cualquier pago convexo
es una superposición de esos tramos (Carr y Madan, 2001): la tabla «ventaja por tramos» del informe
reparte el desacuerdo por zonas de precio y dice, antes de elegir estructura, dónde está la opinión
y qué strike la expresa.

## 4. «Creo que va a subir»: qué dice exactamente eso

Afirmar un rendimiento esperado deja indeterminada la forma de la distribución. El código la
resuelve con la deformación de mínima entropía relativa sujeta a esa media, que es un tilt
exponencial `p(s) ∝ q(s) e^{λ ln(s/F)}`. Y ahí aparece el punto que la intuición original se salta:

> **Una vista alcista de mínima entropía adelgaza la cola izquierda por su cuenta.** No es una
> suposición añadida: es la consecuencia de reponderar hacia arriba una distribución asimétrica.

En el mundo sintético del subproyecto (30 días, `sd(ln S_T/F) = 6.3 %`), afirmar «sube un 1 % sobre
el forward» implica, sin decirlo:

| Magnitud | Implícita `Q` | Vista `P` (+1 %) |
|---|---|---|
| Desviación típica de `ln(S_T/F)` | 6.28 % | 5.30 % (factor 0.84) |
| Probabilidad de caer un 5 % | 15.7 % | 11.0 % |
| Probabilidad de caer un 10 % | 6.4 % | 3.8 % |

Buena parte de la ventaja de vender el put sale de ese adelgazamiento, no de la subida. El
subproyecto lo mide con un escenario de robustez que mantiene la dirección y le impone la
dispersión del mercado: en el ejemplo, la ventaja del put corto cae de `+0.32` a `+0.15`,
aproximadamente a la mitad.

**Conclusión operativa:** si uno quiere afirmar solo la dirección, debe decirlo explícitamente
(`tilt_momentos` con `factor_vol = 1`), y entonces la recomendación cambia: el dictamen pasa del put
vendido a un reversal de riesgo, y sobreviven dos candidatas en vez de cinco. Vender puts es la
expresión adecuada de una vista alcista **cuando la vista incluye que la caída está sobrevalorada**.
Si no la incluye, hay formas mejores.

## 5. Qué estructura expresa cada desacuerdo

| Desacuerdo con el mercado | La afirmación, dicha con precisión | Estructura natural | Lo que la estropea |
|---|---|---|---|
| Media | «el valor esperado está por encima del forward» | forward o futuro largo | la ventaja se reparte por toda la distribución, incluidas las colas que nadie cotiza |
| Cola izquierda | «la caída por debajo de X está sobrevalorada» | put corto, put spread alcista | el capital inmovilizado; en el spread, el coste de dos patas |
| Dispersión | «la volatilidad implícita está cara» | venta de convexidad | la pérdida no acotada y el riesgo de cola |
| Asimetría | «el skew está caro respecto de lo que creo» | reversal de riesgo | combina dos opiniones; si una falla, puede perder igual |
| Cobertura | «quiero acotar la caída», sin predecir nada | put protectora, collar | no busca ventaja: busca un suelo, y eso se paga |

La última fila importa: **el motivo habitual y correcto para comprar puts no es predecir la caída,
sino acotarla.** Una put protectora con ventaja esperada negativa puede ser una decisión acertada si
lo que compra es un límite a la pérdida. Ese juicio no lo hace este programa, que solo compara
ventajas esperadas y riesgo de cola bajo la vista declarada.

## 6. Cuándo vender puts, en una frase

Vender puts tiene ventaja cuando se puede sostener, con algo más que una corazonada, que la
probabilidad acumulada de caer por debajo del strike es menor que la que paga el mercado, **y** esa
diferencia sobrevive a cuatro restas: el deslizamiento de ejecución, el residuo del ajuste de `Q`,
la parte de la ventaja que proviene de strikes sin cotizaciones utilizables, y la reducción de la
ventaja cuando se supone que la convicción vale la mitad.

En el ejemplo sintético, con una vista de `+1 %`, las cinco candidatas que pasan los filtros son
todas vendedoras de puts, y la elegida es un put corto a un 5 % por debajo del forward. El forward
largo tiene más ventaja absoluta (`+0.94` frente a `+0.32`) y se descarta porque el 74 % de esa
ventaja procede de la zona sin cotizaciones utilizables. Comprar puts con esa vista da ventaja
negativa, como debe ser.

## 7. Las cuatro restas, en detalle

1. **Ejecución.** Comprar al ask y vender al bid, más comisión por pata. En el ejemplo, un put corto
   cuesta `0.040` y un spread de dos patas `0.080`: para un spread con ventaja bruta de `0.034`, la
   operación pierde dinero aunque la vista acierte. Es la razón por la que la vista de cola pura no
   produce ninguna recomendación en el informe `cola_cara`.
2. **Residuo del ajuste.** `Q` sale de un ajuste y el ajuste tiene residuo: la diferencia entre el
   valor del modelo y el mid cotizado es error de modelo, no ventaja. La regla exige que la ventaja
   supere la suma de ejecución y residuo.
3. **Cola no identificada.** Más allá del strike fiable más extremo, la forma de `P` y de `Q` es
   extrapolación. El programa mide qué parte de la ventaja procede de esa zona y descarta la
   candidata si pasa de un umbral. Esto excluye precisamente las estructuras cuya ventaja aparente
   vive donde nadie cotiza.
4. **Robustez.** La ventaja se recalcula con la convicción a la mitad, con otra estimación de `Q`
   (ajuste convexo no paramétrico en lugar de SSVI) y, si la vista es direccional, con la dispersión
   del mercado. Se conserva la peor. Si el signo cambia en algún escenario, no se recomienda.

## 8. Lo que el programa no sabe

- **Si la vista acierta.** La ventaja es una resta entre lo que dice la vista y lo que dice el
  precio. El programa comprueba que la resta está bien hecha; no que el minuendo sea cierto.
- **El margen real.** El capital que se reporta es una regla propia (la peor pérdida en valor
  presente), no el margen que exigiría un intermediario.
- **La gestión de la posición.** No hay cierre anticipado, ni rolo, ni asignación anticipada, ni
  dividendos, ni impuestos, ni límites de concentración entre vencimientos.
- **La cola bajo la vista.** El CVaR y la pérdida máxima se calculan con `P`, que es justamente la
  parte optimista del cálculo. La pérdida de verdad de un put vendido llega cuando `P` falla.

## 9. Cómo se usa

```bash
make estrategias-sinteticas   # informes con datos sintéticos en reports/estrategias_sintetico/
```

El guion genera un informe por vista y la comparación entre ellos es el objetivo: el mercado es el
mismo en los cinco, así que las diferencias las produce únicamente la opinión. Las cinco vistas
gastan un presupuesto de información parecido (`KL` entre 0.013 y 0.016, salvo la neutral), de modo
que lo que se compara es el **tipo** de opinión, no su intensidad.

| Informe | Vista | Resultado |
|---|---|---|
| `sin_opinion` | `P = Q` | abstenerse: el control negativo del método |
| `alcista` | `+1 %` con deformación mínima | vender puts (put corto a `0.95 F`) |
| `alcista_misma_vol` | `+0.82 %` con la dispersión del mercado | reversal de riesgo; solo dos candidatas |
| `cola_cara` | caída de más del 5 % un 20 % sobrevalorada, sin dirección | abstenerse: la ventaja no cubre la ejecución |
| `bajista` | `-1 %` | comprar puts, en forma de spread bajista |

Con cotizaciones reales, el camino es el mismo: construir la rebanada del vencimiento, obtener `Q`
con `estrategias.sintetico.q_desde_rebanada_ssvi` (o el ajuste convexo), declarar la vista y llamar
a `estrategias.corrida.correr`.

## 10. Qué falta antes de que esto sirva para decidir

1. **Datos.** Vale lo del plan de trabajo principal: hace falta la muestra histórica de la fase 0 y
   un contrato de datos con horas de disponibilidad documentadas.
2. **Validar la vista.** Hoy la vista la declara el usuario. La vía prevista para que la produzca el
   dato es `quantileflow.pronostico` (regresión cuantílica sobre variables derivadas de `Q`) a
   través de `vista.desde_cuantiles`, y antes de usarla hay que evaluarla con las herramientas de
   `calibracion` y `evidencia`: pinball, CRPS, fiabilidad y Sharpe deflactado sobre un periodo
   distinto del de ajuste.
3. **Congelar los umbrales.** Los de `configs/estrategias.toml` salen de razonar sobre órdenes de
   magnitud, no de ninguna medición. Hay que revisarlos con datos y fijarlos, con una versión nueva,
   antes del periodo de evaluación.
4. **Costos y límites reales.** Comisiones, margen del intermediario y límite de riesgo propio.
   Mientras no estén, los números de capital y de rendimiento sobre capital son ilustrativos.
