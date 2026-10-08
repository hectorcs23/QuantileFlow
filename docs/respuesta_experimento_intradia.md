# Revisión del experimento intradía de calls y puts

**Fecha:** 7 de octubre de 2026. **Rama revisada:** `codex/intradia-20261007`, commit `ff4ff96`, carpeta
`experiments/intradia_20261007/`. **Resultado:** se reproduce exactamente, y sus conclusiones se sostienen al
agregar una cuarta sesión.

Solo se publican agregados. Las tablas de entrada y el detalle por par quedaron en una carpeta temporal fuera
de Git.

## Resumen

- **Reproducción exacta.** Con el mismo snapshot de datos (`66ccade`) y el mismo código de captura, todos los
  conteos y fracciones del informe salen idénticos. Los números con decimales difieren a lo sumo en 2e-13,
  que es redondeo de máquina entre Windows y Linux.
- **Pruebas.** Las 9 pruebas pasan.
- **Réplica con cuatro sesiones.** Al agregar el 7 de octubre, sin cambiar ninguna regla, las conclusiones
  no cambian:
  - de los residuos fuera de banda a las 09:45 en vencimientos de un mes, el 19.1 % sigue fuera con el mismo
    signo a las 10:00 (antes, 19.2 %);
  - con los pares recientes, la fracción fuera de banda pasa de 37.0 % a 36.8 %, igual que antes.
- **Observaciones menores.** Falta documentar el comando exacto que generó las tablas de entrada, y los CSV
  usan finales de línea de Windows (sección 3). Ninguna cambia los resultados.
- **Réplica con cinco sesiones** (sección 6). Hecha el jueves 8: las conclusiones no cambian. Persiste el
  19.3 % de los residuos fuera de banda. Recalcular la referencia con pares recientes explica una parte de
  ellos algunos días, como el 8 de octubre.

## 1. Qué se comprobó

**Integridad de la entrega.**
- Las huellas SHA-256 de los 16 archivos del manifiesto (`MANIFIESTO_ENTREGA.json`) coinciden.
- La rama solo agrega archivos dentro de `experiments/intradia_20261007/`, sobre `e20bded`.
- El commit de código que pide el README, `56cad99`, no cambia nada en `quantileflow/`, `scripts/` ni
  `configs/` respecto de `4ffde8a`, el código fijado de la captura.
- El residuo de cada par se calcula con una referencia estimada sin ese par: `cadenas.residuos_paridad`
  saca los pares de uno en uno.

**Entorno.** Python 3.11.15, numpy 2.4.6, pandas 3.0.6 y pyarrow 25.0.1, las versiones fijadas en
`requirements-bloqueo.txt`. La entrega se hizo con Python 3.12.14 y las mismas versiones de numpy y pandas.

**Tablas de entrada.** Se rehicieron desde el crudo del snapshot `66ccade` con `scripts/normalizar_alpaca.py`,
probando varios rangos de fechas:

| Tabla | ¿Misma huella que la entrega? |
|---|---|
| `cotizaciones.parquet` | Sí, con los rangos que empiezan el 25 de septiembre o antes |
| `dividendos.parquet` | Sí |
| `cobertura_dividendos.parquet` | Sí |
| `subyacente.parquet` | No, con ninguno de los 13 rangos probados |

`subyacente.parquet` cambia con el rango porque guarda los precios SIP de SPY de cada sesión incluida. El
experimento no usa esas filas: solo usa las 6 del nivel implícito de SPX, que salen de las capturas y son
las mismas en todos los rangos. Como todos los resultados coinciden, la diferencia está en filas que el
experimento no lee.

**Diagnósticos.** Se generaron con `scripts/verificar_alpaca.py` para el 2, el 5 y el 6, sobre una copia
del mismo snapshot. Sus RR25 a 30 días son los mismos que dieron las verificaciones diarias de cada sesión.

**Resultados.** Las cifras del informe, frente a la reproducción:

| Cifra | Informe | Reproducción |
|---|---|---|
| Cadenas de SPXW / pares cerca del forward | 30 / 2 215 | 30 / 2 215 |
| Un mes: fuera a las 09:45 / persisten / vuelven / cambian de signo | 292 / 56 / 187 / 49 | 292 / 56 / 187 / 49 |
| 0DTE: fuera a las 09:45 / persisten / vuelven / cambian de signo | 128 / 40 / 61 / 27 | 128 / 40 / 61 / 27 |
| Un mes: base / recientes con referencia base / recalculada | 575/1 624 · 451/1 219 · 449/1 219 | Iguales |
| 0DTE: base / recientes con referencia base / recalculada | 260/591 · 239/502 · 243/502 | Iguales |
| Un mes con tasa fija al 3 / 4 / 5 % | 629 / 619 / 612 de 1 624 | Iguales |
| Medianas de correlación: edad / ancho / residuo relativo y ancho | 0.215 / 0.208 / −0.578 | Iguales |
| Tasas implícitas mensuales | −9.85 % a 15.99 % | Iguales |
| Cambios de RR25 (los ocho valores) | Tabla de su sección 2 | Iguales |

En el JSON, las únicas diferencias que no son de redondeo son la huella de `subyacente.parquet` y la versión
de Python. Los CSV tienen el mismo contenido. Sus bytes difieren solo por los finales de línea.

## 2. Réplica con cuatro sesiones: 2, 5, 6 y 7 de octubre

Mismo código, mismas reglas y la opción `--fechas`, sobre el snapshot de datos `625ee09`. Con ese snapshot,
las tres sesiones originales dan los mismos CSV que con `66ccade`: agregar datos no cambia lo anterior.

**¿Persisten los residuos?** Vencimientos de un mes, pares válidos y cerca del forward en los dos cortes:

| Sesión | Pares comunes | Fuera a las 09:45 | Persisten, mismo signo | Vuelven a banda | Cambian de signo |
|---|---:|---:|---:|---:|---:|
| 2 de octubre | 319 | 132 | 35 (26.5 %) | 72 | 25 |
| 5 de octubre | 216 | 62 | 8 (12.9 %) | 47 | 7 |
| 6 de octubre | 270 | 98 | 13 (13.3 %) | 68 | 17 |
| 7 de octubre | 288 | 95 | 18 (18.9 %) | 59 | 18 |
| Total de cuatro sesiones | 1 093 | 387 | **74 (19.1 %)** | **246 (63.6 %)** | **67 (17.3 %)** |

En 0DTE, de 186 pares fuera a las 09:45, persisten 62 (33.3 %), vuelven 86 y cambian de signo 38. Con tres
sesiones eran 40 de 128 (31 %).

**¿Los explica la antigüedad?** Cohorte fija de pares recientes (edad de hasta 10 s y desfase entre patas de
hasta 2 s):

| Segmento | Todos, referencia base | Recientes, referencia base | Mismos recientes, referencia recalculada |
|---|---:|---:|---:|
| 0DTE | 365/801 = 45.6 % | 336/652 = 51.5 % | 340/652 = 52.1 % |
| Un mes | 785/2 207 = 35.6 % | 577/1 560 = 37.0 % | 574/1 560 = 36.8 % |

Con tasa fija al 3, 4 y 5 %, la fracción fuera de banda en un mes es 38.3, 37.9 y 37.3 %. Las medianas de las
40 correlaciones por cadena son 0.215 (edad), 0.194 (ancho) y −0.590 (residuo relativo y ancho).

**RR25 a 30 días, de 09:45 a 10:00**, en puntos de volatilidad, con la banda bid–ask del cambio:

| Sesión | SPXW | SPY |
|---|---|---|
| 2 de octubre | +0.004 [−0.185, +0.193] | +0.109 [−0.017, +0.235] |
| 5 de octubre | +0.052 [−0.352, +0.456] | +0.307 [+0.043, +0.571], excluye cero |
| 6 de octubre | +0.057 [−0.195, +0.308] | +0.170 [−0.035, +0.374] |
| 7 de octubre | −0.139 [−0.486, +0.209] | −0.167 [−0.406, +0.072] |

El 7 de octubre el RR25 bajó en las dos raíces, y los dos cambios caben en sus bandas. El único caso fuera de
banda sigue siendo el de SPY del 5: 1 de 8. No hay una dirección que se repita.

**Lectura.** Las conclusiones del informe se sostienen con la cuarta sesión. La medida agregada se mueve poco
en 15 minutos frente a su banda, y los residuos de paridad por par cambian mucho. Quitar las cotizaciones
viejas no los elimina. Sigue sin haber base para entrenar un predictor con esos residuos.

## 3. Observaciones sobre la entrega

1. **Falta el comando exacto de normalización.** El README dice que las tablas se reconstruyen con
   `scripts/normalizar_alpaca.py`, pero no con qué rango. Con un rango distinto, la huella de las tablas
   cambia aunque el experimento dé lo mismo. Conviene anotar el comando usado y, además de la huella del
   archivo, el número de filas de cada tabla o una huella de las filas que el experimento lee.
2. **Finales de línea de Windows en los CSV.** `to_csv` escribe CRLF en Windows, y `.gitattributes` conserva
   esos bytes. Por eso los CSV no coinciden byte a byte entre sistemas. Con `lineterminator="\n"` coincidirían.
3. **La base de 60 s es la configuración de producción.** `configs/piloto.toml` fija `edad_maxima_s = 60` y
   `tasa = 0.04`. El informe lo describe como «base», pero no dice que es lo mismo que usa el piloto. Vale la
   pena aclararlo, porque refuerza la lectura: es el escenario que de verdad ve el piloto.
4. **El código exige el feed `indicative`.** Para el contraste con OPRA, el cuarto paso de su propuesta, habrá
   que aceptar ese feed sin mezclar las series.
5. **Redondeo.** En 0DTE, 40 de 128 es 31.25 %. El informe lo escribe 31.3 % y Python lo redondea a 31.2 %.
   No cambia nada.

## 4. Sobre la siguiente prueba que propone

1. **Repetir sin cambiar reglas.** Hecho con cuatro y con cinco sesiones (secciones 2 y 6).
2. **Una curva de tasas documentada.** Una opción gratuita es la tasa de las letras del Tesoro a un mes
   publicada por la Fed de San Luis (FRED). Tiene fuente y fecha, a diferencia de las tasas fijas del 3, 4 y
   5 %.
3. **Capturas cada 30–60 s durante 10–15 minutos.** Se puede hacer sin gastar más minutos de GitHub Actions.
   - La corrida de las 10:00 ya espera sin hacer nada desde las 09:16. Podría tomar esas fotos entre las 09:45
     y las 10:00.
   - Cada foto son unas 10 solicitudes. Una cada 30 s son unas 20 por minuto, muy por debajo del límite de 200
     por minuto del plan gratuito.
   - Hay que dejar libres los segundos de la ráfaga de cada corte.
   - Cambia el código de captura, así que entraría en el mantenimiento previsto antes del 19 de octubre, con un
     nuevo commit fijado y la reinstalación con comprobación de huellas.
4. **Contraste con OPRA.** Es la única forma de saber cuánto de los residuos viene de que el feed gratuito
   modifica las cotizaciones. La decisión de pagar OPRA es del usuario.
5. **Volver al transporte de cuantiles.** Es la línea principal del proyecto. Este experimento respalda
   trabajar con medidas agregadas, como RR25 y los cuantiles, y no con residuos sueltos.

## 5. Cómo repetir esta revisión

Desde la raíz de QuantileFlow, con el repositorio de datos en `RUTA_DATOS`:

```bash
git worktree add ../intradia origin/codex/intradia-20261007
python scripts/normalizar_alpaca.py --desde 2026-09-21 --hasta 2026-10-07 --datos RUTA_DATOS --salida PRIVADO/tablas
for d in 2026-10-02 2026-10-05 2026-10-06 2026-10-07; do
  python scripts/verificar_alpaca.py --fecha $d --datos COPIA_DE_RUTA_DATOS --salida PRIVADO/diagnosticos/diagnostico_$d
done
cd ../intradia/experiments/intradia_20261007
python explorar_intradia.py --codigo RUTA_QUANTILEFLOW --tablas PRIVADO/tablas --diagnosticos PRIVADO/diagnosticos \
  --salida PRIVADO/agregados_4s --privado PRIVADO/pares_4s --fechas 2026-10-02 2026-10-05 2026-10-06 2026-10-07
QF_CODE=RUTA_QUANTILEFLOW python -m pytest --rootdir=. -q -p no:cacheprovider test_exploracion.py
```

Para la reproducción exacta de las tres sesiones originales, usar el snapshot de datos `66ccade` y omitir
`--fechas`.

## 6. Réplica con cinco sesiones: 2, 5, 6, 7 y 8 de octubre

Hecha el 8 de octubre, después del cierre de la aceptación. Mismo código (la rama sigue en `ff4ff96`), mismas
reglas y `--fechas` con los cinco días, sobre el snapshot de datos `66c969f`. Las 9 pruebas pasan. Las filas
de los cuatro primeros días salen idénticas a las de la réplica de cuatro sesiones.

**¿Persisten los residuos?** Vencimientos de un mes, pares válidos y cerca del forward en los dos cortes:

| Sesión | Pares comunes | Fuera a las 09:45 | Persisten, mismo signo | Vuelven a banda | Cambian de signo |
|---|---:|---:|---:|---:|---:|
| 2 de octubre | 319 | 132 | 35 (26.5 %) | 72 | 25 |
| 5 de octubre | 216 | 62 | 8 (12.9 %) | 47 | 7 |
| 6 de octubre | 270 | 98 | 13 (13.3 %) | 68 | 17 |
| 7 de octubre | 288 | 95 | 18 (18.9 %) | 59 | 18 |
| 8 de octubre | 280 | 101 | 20 (19.8 %) | 60 | 21 |
| Total de cinco sesiones | 1 373 | 488 | **94 (19.3 %)** | **306 (62.7 %)** | **88 (18.0 %)** |

En 0DTE, de 223 pares fuera a las 09:45, persisten 66 (29.6 %), vuelven 113 y cambian de signo 44. El 8 de
octubre fueron 37 fuera, de los que persistieron 4.

**¿Los explica la antigüedad?** Cohorte fija de pares recientes (edad de hasta 10 s y desfase entre patas de
hasta 2 s):

| Segmento | Todos, referencia base | Recientes, referencia base | Mismos recientes, referencia recalculada |
|---|---:|---:|---:|
| 0DTE | 435/989 = 44.0 % | 394/798 = 49.4 % | 399/798 = 50.0 % |
| Un mes | 1 001/2 772 = 36.1 % | 749/1 993 = 37.6 % | 722/1 993 = 36.2 % |

**Un matiz nuevo.** El 8 de octubre, en vencimientos de un mes, recalcular la referencia solo con pares
recientes bajó la fracción fuera de banda de 39.7 % (172/433) a 34.2 % (148/433). En los otros días el efecto
fue casi nulo. La antigüedad explica una parte de los residuos algunos días, pero la mayoría sigue ahí.

Con tasa fija al 3, 4 y 5 %, la fracción fuera de banda en un mes es 38.1, 37.9 y 37.6 %. Las medianas de las
50 correlaciones por cadena son 0.205 (edad), 0.180 (ancho) y −0.579 (residuo relativo y ancho). Las tasas
implícitas mensuales siguen entre −9.85 % y 15.99 %.

**RR25 a 30 días, de 09:45 a 10:00**, en puntos de volatilidad, con la banda bid–ask del cambio:

| Sesión | SPXW | SPY |
|---|---|---|
| 2 de octubre | +0.004 [−0.185, +0.193] | +0.109 [−0.017, +0.235] |
| 5 de octubre | +0.052 [−0.352, +0.456] | +0.307 [+0.043, +0.571], excluye cero |
| 6 de octubre | +0.057 [−0.195, +0.308] | +0.170 [−0.035, +0.374] |
| 7 de octubre | −0.139 [−0.486, +0.209] | −0.167 [−0.406, +0.072] |
| 8 de octubre | −0.023 [−0.247, +0.201] | +0.024 [−0.157, +0.204] |

El 8 de octubre la RR25 casi no se movió en ninguna de las dos raíces. Sigue habiendo un solo caso fuera de
banda de 10: el de SPY del 5.

**¿Cambian las conclusiones?** No.
- La medida agregada se mueve poco en 15 minutos frente a su banda, y no tiene una dirección que se repita.
- Los residuos de paridad por par cambian mucho: solo el 19.3 % de los que estaban fuera sigue fuera con el
  mismo signo, un porcentaje muy parecido al de tres (19.2 %) y cuatro sesiones (19.1 %).
- Quitar las cotizaciones viejas no elimina los residuos, aunque algunos días, como el 8, explica una parte.
- Sigue sin haber base para entrenar un predictor con esos residuos.
