# Sensibilidad, escenarios y comparación de contratos

8 de octubre de 2026. Primera versión experimental de QuantileFlow.

La entrada que buscamos es: «Espero que el subyacente se mueva X% en H días, tengo un presupuesto B y quiero comparar strikes y vencimientos». La salida debe mostrar cantidades enteras, desembolso, ganancia/pérdida condicional, costos, sensibilidad y resultados si el movimiento no llega, llega tarde o cambia la volatilidad.

La ganancia del escenario esperado no es ganancia esperada estadística. Hace falta asignar y validar probabilidades para calcular esta última. Un contrato con más retorno si aciertas puede perder mucho más si no aciertas. El presupuesto de operaciones es distinto del presupuesto mensual de datos de US$250.

## Sensibilidad del contrato

Para movimientos pequeños:

`cambio de valor ≈ delta·cambio de spot + ½·gamma·(cambio de spot)² + vega·cambio de IV + theta·tiempo transcurrido`.

Delta responde a cuánto cambia el subyacente; gamma, a cómo cambia esa sensibilidad; theta, al paso del tiempo; vega, a la volatilidad implícita. El motor utiliza repricing completo para escenarios: la aproximación local no sustituye el cálculo para movimientos grandes o cerca de liquidación. [OIC: Greeks](https://www.optionseducation.org/advancedconcepts/understanding-options-greeks).

`quantileflow/escenarios.py` incluye:

- Sensibilidades Black–Scholes europeas con unidades explícitas: delta por US$1, gamma por US$1², vega por punto de IV y theta por día natural. No son las griegas de una opción americana con dividendos discretos.
- Reprecio europeo y árbol CRR para ejercicio americano o dividendos en efectivo. Los dividendos se desplazan al nuevo instante de valoración y se retiran los ya pasados. El árbol reutiliza el modelo de dividendos escrowed existente: requiere comprobar convergencia y calibración antes de ranking con datos reales.
- Compra a ask, comisión por contrato en ambos lados, reserva para comisión de cierre, multiplicador y presupuesto. Salida teórica menos un semispread configurable; el spread futuro es un supuesto, no una cotización conocida.
- Exclusión de vencimientos anteriores a cualquier escenario evaluado. No usa el spot posterior al vencimiento como si hubiera ocurrido antes. Escenarios exactamente al vencimiento usan payoff intrínseco, sin simular entrega de acciones ni ejercicio operativo. Para opciones con entrega física, el software de operación tendrá que cerrar antes del vencimiento o modelar explícitamente esa entrega.
- PnL por escenario y mínimo de los escenarios proporcionados. Sin probabilidades inventadas, órdenes ni recomendación de un contrato real.

## Qué cambia en la PDF implícita

La PDF es una **densidad de probabilidad**, no un archivo PDF. La distribución se infiere de precios por strike y vencimiento. Para calls europeos y descuento determinista `D`, la identidad de Breeden–Litzenberger es `densidad(K) = (1/D)·∂²C/∂K²`. Esa curvatura respecto del **strike** es distinta de gamma, que deriva el precio respecto del **subyacente**. La densidad es neutral al riesgo, no directamente una probabilidad real de ganar. [Banco Central de Irlanda: metodología](https://www.centralbank.ie/docs/default-source/publications/quarterly-bulletins/quarterly-bulletin-signed-articles/option-implied-probability-density-functions.pdf?sfvrsn=c313a61d_8).

Una subida del subyacente no determina por sí sola cómo cambiará toda la distribución. Necesitamos una hipótesis sobre la respuesta de la superficie de IV y luego comprobarla con nuevas cadenas. En el ejemplo lognormal:

1. Cambiar solo spot, conservando plazo e IV, cambia ubicación y escala en precios absolutos. Al normalizar por forward, la distribución de rendimientos logarítmicos conserva su forma.
2. Avanzar el reloj conservando la fecha final reduce el plazo restante; en este modelo, con IV constante, reduce la dispersión relativa. La varianza observada no tiene por qué disminuir si la IV sube.
3. Cambiar IV ensancha o estrecha la distribución. Una superficie con skew añade cambios de asimetría y colas que el ejemplo de IV plana no representa.

La demostración separa esos tres efectos con curvas sintéticas. No reconstruye una densidad empírica de la cadena ni demuestra causalidad. La implementación futura comparará superficies sin arbitraje bajo hipótesis de IV fija por strike, fija por delta y desplazamientos de nivel/skew/curvatura, manteniendo la misma fecha final o un plazo constante de forma explícita.

## Cómo lo conectamos con el plan anterior

1. Ejecutar escenarios sintéticos y controles de valoración ahora, sin pagar datos.
2. Añadir adaptador de cadena real para el símbolo elegido, con calidad, tick, bid/ask, tamaño, multiplicador, ejercicio, calendario, dividendos y sello de spot. No asumir que el piloto SPXW contiene ya acciones individuales.
3. Calibrar IV por contrato y una superficie sin arbitraje, con bandas; para acciones americanas ajustar ejercicio anticipado antes de extraer densidades. No aplicar directamente la identidad europea a sus precios crudos.
4. Comparar strikes y DTE al horizonte de salida esperado, y a horizontes más tardíos. Antes de ordenar, filtrar liquidez, antigüedad, presupuesto y pérdida tolerable. Presentar rankings por ganancia condicional, retorno sobre capital y robustez; no mezclarlos en un score arbitrario.
5. Con cadenas sucesivas estudiar cambios de distribución en precios y en log-precio relativo al forward. Separar movimiento mecánico, menor tiempo restante y variación de IV/skew. El transporte por cuantiles del proyecto permitirá resumir estos cambios de forma.
6. Validar fuera de muestra si las variaciones aportan información para retornos observados. Solo después estimar probabilidades físicas/confianza y tomar decisiones de posición.

## Ejecutar

```powershell
python experiments/sensibilidad_20261008/demo.py --presupuesto 500 --movimiento .05 --dias 14 --cambio-iv 0
python -m pytest -q tests/test_escenarios.py
```

La demostración compara calls europeos sintéticos, sin dividendos, con spot US$100, IV 25%, tasa 4%, semispread US$0.04 y comisión US$0.65 por contrato y lado. El motor general admite calls/puts y ejercicio americano. El segundo escenario es explícitamente adverso: −2% de spot, siete días más tarde y −5 puntos de IV. No se asignan probabilidades ni se afirma que esa lista cubra todos los posibles resultados.

Pruebas: 8 pasadas; aproximación local contra repricing, relación de deltas call/put, vencimiento y prohibición de horizonte posterior, presupuesto y reserva de costos, ejercicio anticipado/convergencia de call americano sin dividendos, desplazamiento de dividendos y caso en que una subida de spot no compensa tiempo/caída de IV. La demostración interactiva se revisó en escritorio y móvil; controles de precio/IV y presupuesto actualizan resultados sin errores.
