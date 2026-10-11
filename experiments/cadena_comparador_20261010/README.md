# Cadena gratuita → comparador europeo: diagnóstico, no operación

10 de octubre de 2026. Seis sesiones: 2, 5, 6, 7, 8 y 9 de octubre.
Presupuesto de datos US$0. Capital ficticio US$10,000 para comparar candidatos
SPXW; no representa capital disponible ni autorización para comprar opciones.

```powershell
python scripts/normalizar_alpaca.py --desde 2026-10-02 --hasta 2026-10-09 --datos ../datos_privados --salida ../tablas_privadas
python experiments/cadena_comparador_20261010/evaluar_cadena.py --tablas ../tablas_privadas --crudo ../datos_privados --salida-privada ../comparador_privado
python experiments/cadena_comparador_20261010/control_numerico.py --privados ../comparador_privado --tablas ../tablas_privadas
python -m pytest tests/test_adaptador_comparador.py experiments/cadena_comparador_20261010/test_evaluar_cadena.py -q
```

Las rutas privadas deben quedar fuera del repositorio público. La primera
normalización verifica el crudo; el experimento vuelve a comprobar las tablas,
manifiestos, páginas comprimidas y cuerpos descomprimidos. No llama a Alpaca
ni usa claves. Solo se publican métricas agregadas, hashes y figuras.

`protocolo.toml` fija parámetros antes de medir los resultados. Se filtran
SPXW europeos PM con reglas del piloto, sellos conocidos y no posteriores al
corte. Cada tercer strike se reserva para validación de ambos lados. En los
restantes, dentro de ±1% log-forward, se ajusta una IV plana por vencimiento
mediante la mediana de IV. La evaluación usa ±3% y no participa del ajuste.

El universo de candidatos toma calls/puts cercanos a tres moneyness por cada
vencimiento disponible de 1–45 días. Se limita cantidad al tamaño del ask
actual; eso no garantiza ejecución ni liquidez futura. Se usa compra a ask
en el nominal. Los casos de compra a mid/bid son cotas optimistas para
sensibilidad, no precios ejecutables prometidos. Se cruzan tres niveles de
IV del ajuste con esas tres entradas. El costo de salida usa la mediana del
semispread actual como supuesto común; no es una cotización futura.

Escenario objetivo: +1% en siete días; controles: sin movimiento con IV −3
puntos y −1% con IV fija. Los escenarios carecen de probabilidades estimadas.
Las perturbaciones de referencia ±un error jackknife no son intervalos de
confianza. Se mantienen fijas IV, universo y cotizaciones al perturbar spot.

Todos los cortes siguen **no aptos para comparación puntual**: feed
`indicative`, SPX inferido y referencia de unos cinco segundos con límite dos.
El modo descriptivo no retira esos bloqueos. [Alpaca](https://docs.alpaca.markets/us/docs/historical-option-data)
documenta que indicative modifica las cotizaciones de opciones.

Resultado: 71/1,642 filas holdout dentro de bid/ask con PDE gruesa, 69 con
PDE fina y 68 con Black–Scholes analítico usando la misma IV plana. En 6/12
cortes el primero cambia entre las nueve variantes. Entre 09:45 y 10:00
cambia en 5/6 sesiones. No equivale a medir rentabilidad realizada.

Los resultados anteriores de `comparador_pdf_20261010`,
`valoracion_consistente_20261010` y del 9 de octubre siguen asociados a sus
commits originales; sus hashes registran esas versiones históricas.
