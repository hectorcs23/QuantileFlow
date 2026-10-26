# Revisión del experimento de error concentrado (L1)

**Fecha:** 26 de octubre de 2026. **Rama revisada:** `codex/ruido-concentrado-20261022`, commit `f0e578a`,
con el protocolo en `bedbd5b`. **Resultado:** se reproduce exactamente con los datos privados, la matemática
es correcta y las conclusiones están bien acotadas. Robinhood ya permite responder la pregunta que el informe
deja abierta: los conflictos vienen sobre todo del feed `indicative` de Alpaca.

Solo se publican agregados. Las entradas regeneradas y los resultados por contrato quedaron en carpetas
privadas fuera de Git. Los datos de Robinhood siguen en la rama privada `robinhood` de QuantileFlow-datos.

## Resumen

- **Reproducción exacta.**
  - Regeneré desde el crudo, en `43b286c`, las entradas de las dos cohortes y volví a correr la evaluación:
    16,192 LP, igual que el informe.
  - Las 88 reparaciones salen idénticas y las bandas difieren en menos de 3e−15.
  - El caso uniforme reproduce el experimento B sin ninguna diferencia.
  - Pasan las 46 pruebas.
- **Las cifras del informe coinciden** con `resumen.json`, `reparaciones.json` y `verificacion.json`.
  Hay un solo redondeo: el control de soporte en los días nuevos da 0.019 puntos, no 0.020.
- **La matemática está bien.**
  - El conjunto con cap y error medio es exactamente el que se describe.
  - El cambio de variables con D variable es correcto: lo comprobé contra un barrido de D fijos.
  - La cota de paridad es válida: se cumple en las 88 rebanadas y, por sí sola, explica cerca de la mitad del
    error mínimo.
- **Lo nuevo: el conflicto viene del feed.** Con las marcas de Robinhood, el forward que implica cada par
  call/put varía 0.20 puntos entre strikes; con los mids de Alpaca, 2.42 (mediana de 8 cortes). En las fotos
  en vivo, las cotizaciones de Robinhood no necesitan ninguna reparación; las de Alpaca, sí en dos de tres.
- **De acuerdo con la decisión.** L1+cap sirve como diagnóstico y no para sacar probabilidades. Antes de
  buscar cambios entre 09:45 y 10:00 con el feed `indicative`, conviene medir cuánto de la ambigüedad
  desaparece con cotizaciones consolidadas.

## 1. Qué se comprobó

**Contenido de la rama.** Son dos commits sobre el experimento B (`9750a3a`):

- `bedbd5b`, del 22 de octubre a las 17:56 de Nueva York, solo agrega `protocolo.toml`;
- `f0e578a`, del 26 de octubre a las 17:38, agrega el código, los resultados, el informe y una entrada en el
  README. No toca el protocolo, la captura, el simulador A ni los estudios anteriores.

Lo que usa el código sale del protocolo congelado: los márgenes (0.05, 0.1 y 0.5), el cap (mínimo minimax
más 0.5), los umbrales, los controles y la regla de reserva. El código se escribió después del protocolo,
pero las decisiones que importan quedaron fijadas antes. Git muestra el orden de los commits, no qué se
miró antes de cada uno.

**Datos.**

- `43b286c` es el histórico del 22 de octubre de QuantileFlow-datos.
- Las verificaciones del crudo dan lo mismo: 37 manifiestos y 136 páginas únicas.
- La normalización del 12 al 16 de octubre reproduce la huella de `cotizaciones.parquet`.
- No reproduce la huella de `subyacente.parquet` ni las de los Parquet de entrada. Pero los `modelos.json`
  (F, D y plazo de cada vencimiento) coinciden byte a byte, y los resultados también. Las diferencias están
  en columnas que el LP no usa o en el último bit de algún cálculo; correr en otra máquina basta para eso.
- Las 409 filas excluidas por IV no finita son la suma de `iv_no_identificada` de los 10 cortes.

**Cohorte conocida.** Las entradas privadas de `forward_fijo_20261014` no están en este entorno. Las regeneré
desde el crudo con el preparador de la cohorte nueva, cambiando solo las fechas. Salen las mismas 5,912
filas de entrenamiento y los mismos resultados por rebanada. Eso confirma que las dos cohortes se
prepararon igual.

**Evaluación.**

| Comprobación | Resultado |
|---|---|
| LP resueltos | 8,832 + 7,360 = 16,192 |
| Reparaciones: ρ, b\*, filas cambiadas, 10 % mayor y paridad | Idénticas en las 88 rebanadas |
| Bandas de CDF, exteriores y alcanzables | Diferencia máxima de 2.8e−15 |
| Reserva | Mismos solapamientos; ancho con diferencia máxima de 7.5e−14 |
| Caso uniforme frente al experimento B | Idéntico en las 48 rebanadas conocidas |
| Pruebas del README | Pasan las 46 |

**Cifras del informe.** Todas las de las tablas y del texto coinciden con los resultados publicados: anchos,
máximos, diferencias alcanzables, solapamientos, error mínimo, concentración, paridad, controles y errores
de reconstrucción. El único detalle: dice que duplicar el soporte cambia los extremos «como máximo 0.020
puntos» en los días nuevos, y el valor es 0.0194, o sea 0.019.

## 2. Revisión matemática

- **Error y presupuesto.**
  - El LP usa una variable e_i por cotización, con e_i ≥ desviación y e_i ≤ cap.
  - El conjunto factible es exactamente el de las medidas cuya desviación no pasa el cap en ninguna fila y
    cuya media no pasa el presupuesto.
  - Al minimizar la media, e coincide con la desviación, y el código lo comprueba.
- **D variable.**
  - Con p = w/Σw, t = 1/Σw y z = e·t, todo queda lineal: A·p ≤ t·ask + spread·z, A·p ≥ t·bid − spread·z,
    z ≤ cap·t, media(z) ≤ b·t y Σp = 1.
  - Es correcto. Comprobación independiente: con D entre 0.98 y 1.02, la banda conjunta,
    [0.48714, 0.51235], coincide con la envolvente de 161 LP con D fijo.
- **Cota de paridad.**
  - Con F y D fijos, el modelo impone exactamente C − P = D(F − K). Si las cotizaciones no lo permiten, al
    menos una de las dos filas sale de su bid/ask, y las dos si el cap no alcanza en un solo lado.
  - Los pares son disjuntos, así que las cotas se suman. Es válida: en las 88 rebanadas, el óptimo L1 cambia
    al menos esas filas.
  - El error que exige la paridad sola es, en mediana, el 47 % del error medio mínimo b\*.
- **Anidamientos.** Se cumplen las 528 inclusiones: uniforme ⊇ L1+0.5 ⊇ L1+0.1 ⊇ L1+0.05, más los controles.

Tres puntos a precisar; no son errores:

1. **«No borramos cotizaciones».** El modelo no elige outliers, pero el preprocesamiento heredado sí quita las
   filas con IV no finita: 409 en la cohorte nueva, el 5.6 % de la ventana. Suelen ser precios fuera de las
   cotas de no arbitraje, justo los que más reparación pedirían. Los conflictos medidos son entonces un piso.
2. **Huellas de Parquet.** No sirven para comparar entre máquinas. Para auditar conviene registrar también una
   huella del contenido que se usa (strike, tipo, bid, ask, plazo y partición), que no depende del formato.
3. **Independencia.** El informe lo dice: 09:45 y 10:00 del mismo día comparten casi todo. En la práctica son
   5 o 6 días por cohorte.

## 3. ¿El conflicto viene del feed? Lo que agrega Robinhood

El informe deja abierta esta pregunta: haría falta una referencia externa, sujeta a encontrar acceso
gratuito. Desde el 21 de octubre hay una: el conector de Robinhood del usuario, con bid y ask consolidados en
vivo y la marca de cada opción cada 15 segundos del día ([comparación con Robinhood](comparacion_robinhood.md)).

Usé la muestra diaria de esa comparación: 14 contratos SPXW a unos 30 días, siete strikes con su call y su
put. Cada par implica un forward, K + (C − P)/D. Con cotizaciones coherentes, todos los pares dan casi el
mismo.

| | Robinhood | Alpaca (`indicative`) |
|---|---:|---:|
| Forward implícito al corte: desviación entre strikes, mediana de 8 cortes | 0.20 puntos | 2.42 puntos |
| Rango entre strikes, mediana | 0.59 | 7.52 |
| Fotos en vivo con un forward común a los 7 pares | 3 de 3 | 1 de 3 |
| Pares fuera del mejor forward común, en vivo | 0, 0 y 0 | 1, 2 y 0 |
| Reparación mínima en vivo, ρ en spreads (forward libre ±0.25 %) | 0, 0 y 0 | 0.56, 0.41 y 0 |

- **Al corte:** marca de Robinhood (cierre de la barra de 15 segundos anterior) frente al mid de la captura de
  Alpaca. Son cuatro sesiones, del 21 al 26 de octubre.
- **En vivo:** bid y ask de las dos fuentes en el mismo instante, el 22, el 23 y el 26 de octubre.
- **Descuento:** D sale de la tasa de 4 % del piloto, la misma para las dos fuentes.
- **Reparación:** es la de la rama, `MercadoL1.reparar`, sobre los 14 contratos.

Con cotizaciones consolidadas, la paridad se cumple dentro de unos 0.2 puntos. Con el feed `indicative`, los
mismos contratos se dispersan diez veces más. Eso apunta a que la mayor parte de los conflictos de paridad del
informe, y buena parte del ancho de las bandas, viene del feed y no de F ni de D.

Límites:

- es una muestra de 14 contratos de un vencimiento por día, en cuatro sesiones;
- la marca de Robinhood es el punto medio de su bid y ask, y suponemos que son las cotizaciones consolidadas
  del mercado.

## 4. Sobre la decisión y el siguiente paso

- **De acuerdo con la decisión:** L1+cap como diagnóstico, sin promoverlo a probabilidades ni a decisiones de
  compra.
- **El estudio de cambios entre 09:45 y 10:00 está bien planteado:** mismo vencimiento, umbrales absolutos y
  referencia común. Pero el feed mete unos 2.4 puntos de ruido en el forward implícito. Es probable que muchas
  bandas de cambio incluyan cero por culpa del feed y no del mercado.
- **Propuesta barata antes de eso:** medir con Robinhood cuánto se estrechan las bandas con cotizaciones
  consolidadas.
  - Por ejemplo, correr el mismo LP con el bid y el ask en vivo de Robinhood y de Alpaca para los mismos
    contratos, en la foto diaria.
  - Para que la banda de la CDF diga algo hacen falta más strikes que los 14 de hoy. Ampliar la muestra
    cuesta más llamadas al conector y más transcripción. Los datos de Robinhood seguirían siendo privados.

## 5. Cómo repetir esta revisión

Desde la raíz de QuantileFlow, con un clon de QuantileFlow-datos en `DATOS` y la rama `robinhood` en
`ROBINHOOD`. `PRIVADO` es una ruta absoluta fuera de cualquier checkout de Git.

```bash
git worktree add --detach ../rc origin/codex/ruido-concentrado-20261022
git -C DATOS worktree add --detach "$PWD/../datos_43b286c" 43b286c0df2de41d63d0475260517c01d6f36f54
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
(cd ../rc && python -m pytest -q -p no:cacheprovider experiments/ruido_concentrado_20261022/test_metodo_l1.py \
  experiments/distribuciones_ruido_20261022/test_metodo.py experiments/factibilidad_20261020/test_factibilidad.py)
R=experiments/revision-ruido-concentrado
for c in "nuevas 2026-10-12 2026-10-16" "conocidas 2026-10-02 2026-10-09"; do
  set -- $c
  (cd ../rc && python scripts/normalizar_alpaca.py --desde $2 --hasta $3 --datos ../datos_43b286c \
    --salida PRIVADO/tablas_$1)
  python $R/preparar_cohorte.py --rama ../rc --tablas PRIVADO/tablas_$1 --crudo ../datos_43b286c \
    --privado PRIVADO/entradas_$1 --resumen PRIVADO/entradas_$1.json --desde $2 --hasta $3
  python $R/reproducir.py --rama ../rc --cohorte $1 --entradas PRIVADO/entradas_$1 \
    --cortes PRIVADO/entradas_$1.json --salida PRIVADO/reproduccion   # unos 3 minutos por cohorte
done
python $R/paridad_robinhood.py --privado ROBINHOOD --datos DATOS --rama ../rc
```

`reproducir.py` imprime las diferencias máximas con lo publicado por la rama. `paridad_robinhood.py` solo
imprime agregados.
