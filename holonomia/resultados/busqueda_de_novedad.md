# Búsqueda de novedad (§6 y §7.1)

Hecha el 18 de noviembre de 2026, antes de medir nada. Cada referencia se
verificó antes de anotarla, como pide la regla 7.

## Lo que ya está hecho

**HodgeRank y el arbitraje triangular en divisas.** La equivalencia «rotacional
cero ⟺ no hay arbitraje triangular» es vieja y está en la base misma de
HodgeRank: Jiang, Lim, Yao y Ye, *Statistical ranking and combinatorial Hodge
theory*, Math. Program. 127 (2011), preprint [arXiv:0811.1067](https://arxiv.org/pdf/0811.1067).
Ahí está también el punto que manda en este proyecto: **en un grafo completo
no hay componente armónica**, así que la consistencia local implica la global.

**Evidencia empírica en divisas.** Fenn, Howison, McDonald, Williams y Johnson,
[*The mirage of triangular arbitrage in the spot foreign exchange market*](https://people.maths.ox.ac.uk/~howison/papers/fenn_fx_arbitrage.pdf),
encuentran que las oportunidades han ido desapareciendo y que el mercado es
internamente consistente. Aiba y otros modelan el arbitraje triangular como
interacción de tres tipos de cambio.

**Hodge en una red cripto.** Ikeda y Chakraborty,
[*Hodge decomposition of the remittance network on the XRP ledger*](https://arxiv.org/abs/2212.02048)
(arXiv:2212.02048), descomponen **flujos de remesas**, no tipos de cambio, y
miden un «flujo de lazo» propio, que no es la parte armónica. Objeto distinto.

**El encuadre de holonomía, ya publicado.** Suyash Mishra,
*Local verification cannot detect non-transportability: a cohomological theory
of context preservation in agentic reasoning*,
[arXiv:2608.11252](https://arxiv.org/abs/2608.11252) (4 de agosto de 2026,
cs.AI). **No es un paper de finanzas**: va de transporte de contexto en
razonamiento con agentes. Pero su sección 7.2 usa divisas como banco de
calibración y dice exactamente lo que este proyecto quería decir: con el nulo
de no-arbitraje la cocadena es un coborde exacto, el arbitraje triangular es la
parte rotacional, y **el arbitraje de lazo sobre ciclos que ningún triángulo
ejecutable rellena es la parte armónica**.

Importa el detalle: ese trabajo **no usa datos de mercado**. Es un complejo
construido de 15 monedas, 400 libros simulados por escenario, ruido de
cotización de 0.35 pb y arbitraje inyectado (escenarios de 4 pb). Los propios
autores dicen que les falta validación con datos reales.

**Área de Lévy y lead-lag.** Está bien establecido: Cartea, Cucuringu y Jin,
[*Detecting lead-lag relationships in stock returns and portfolio strategies*](https://doi.org/10.2139/ssrn.4599565),
construyen un puntaje direccional con firmas de nivel 2 sobre CRSP 1963–2022.
La matriz de áreas de Lévy es densa y antisimétrica. **No se encontró ningún
trabajo que le aplique una descomposición de Hodge.**

## El hueco

1. **La medición empírica no está hecha.** El encuadre de gauge sobre divisas
   existe desde agosto de 2026, pero sobre datos construidos. Nadie ha medido
   holonomía, rotacional y armónico sobre cotizaciones reales con dos puntas y
   costos de ejecución. Eso es la Fase 1.
2. **La persistencia tampoco.** Ni la vida media de la inconsistencia, ni su
   dependencia del régimen.
3. **Hodge sobre la matriz de áreas de Lévy** no aparece en ninguna parte. Es
   lo más original de las tres fases, y también lo más frágil (Fase 3).

## Consecuencia para la pregunta de la Fase 1

La pregunta no puede ser «¿se puede leer el arbitraje como holonomía?»: eso ya
está escrito. Tiene que ser **cuantitativa y empírica**:

> ¿Cuánta curvatura hay en un mercado cripto real, cómo se reparte entre local
> y global, cuánto dura y cuánta sobrevive a los costos?

Y hay un contraste concreto que ofrecer: el preprint de agosto afirma, sobre
datos sintéticos, que vigilar la parte armónica detecta a 1 pb lo que el
residual sólo detecta a 4 pb. Con datos reales eso se puede confrontar.
