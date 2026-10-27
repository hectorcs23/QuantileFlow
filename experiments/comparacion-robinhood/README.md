# Comparación con Robinhood

**Fecha:** 21 de octubre de 2026. **Estado:** en curso, un día más por sesión. No cambia el piloto ni la
captura: solo mide qué tan lejos están las capturas gratis de Alpaca de un dato mejor.

Resultados: [`docs/comparacion_robinhood.md`](../../docs/comparacion_robinhood.md).

## Para qué existe

La captura usa el feed gratis `indicative` de Alpaca, que no es el NBBO de OPRA, y saca el nivel del SPX
de la paridad put-call porque Alpaca no da el índice. El usuario conectó Robinhood a Claude el 21 de
octubre. Su conector da gratis tres cosas que sirven de referencia:

1. el índice SPX real, en barras de un minuto (hay al menos un año hacia atrás);
2. el precio marca de cada opción (punto medio de su bid y ask), en barras de 15 segundos, **solo del día**;
3. el bid y el ask de cada opción, **solo en vivo**.

Por eso la parte de opciones se hace el mismo día, en la revisión de las 10:27.

## Datos y licencias

| Fuente | Qué se usa | Dónde queda |
|---|---|---|
| Robinhood, conector de Claude (solo herramientas de lectura de datos de mercado) | SPX por minuto; 14 opciones SPXW por día | Rama privada `robinhood` de QuantileFlow-datos |
| Alpaca, plan gratuito | Las capturas de 09:45 y 10:00 y una foto en vivo de las mismas 14 opciones | La foto, en la misma rama privada |

Los datos de Robinhood son para uso personal y no se publican; las cotizaciones de Alpaca tampoco. Aquí
solo llegan agregados. El conector nunca se usa para órdenes ni para ver la cuenta.

## Muestra de cada día

`comparar.py plan` la saca del `resumen.json` de `scripts/verificar_alpaca.py`:

- vencimiento: de los dos de SPXW que usa el plazo constante de 30 días, el más cercano a 30 días (si
  empatan, el más lejano);
- strikes: el múltiplo de 25 más cercano al nivel implícito de las 09:45, ±100, ±200 y ±300 puntos;
- call y put de cada strike: 14 contratos;
- ventanas en UTC sacadas de `corte_utc`, así que siguen el cambio de horario del 1 de noviembre.

## Pasos de cada día

Van dentro de la revisión de las 10:27, después de `scripts/verificar_alpaca.py`. `V` es su carpeta de
salida, `P=/home/user/quantileflow-datos-robinhood` (la rama `robinhood`) y `F` la fecha de hoy en Nueva
York. Si `P` no existe:
`git -C /home/user/quantileflow-datos fetch origin robinhood && git -C /home/user/quantileflow-datos worktree add $P robinhood`.

Las respuestas del conector se copian tal cual, sin el texto `guide`, como una lista JSON. Para
instrumentos y cotizaciones se pueden omitir los campos que no se usan, pero nunca se cambia un valor.

1. `git -C $P pull` y `python experiments/comparacion-robinhood/comparar.py plan --verificacion $V`.
   Si responde con `motivo`, no hay nada que pedir.
2. `get_option_instruments` por cada elemento de `instrumentos` del plan, en paralelo. Los
   `data.instruments` juntos van a `$P/$F/crudo/instrumentos.json` (al menos `id`, `chain_symbol`,
   `expiration_date`, `strike_price`, `type`). Luego `comparar.py importar --verificacion $V --privado $P`:
   tiene que decir `instrumentos.json`.
3. `comparar.py plan --verificacion $V --privado $P` ahora trae `lotes` (hasta 10 ids).
4. Foto en vivo, en un mismo mensaje y en paralelo: `get_option_quotes` con los 14 ids y
   `python experiments/comparacion-robinhood/foto_alpaca.py --instrumentos $P/$F/instrumentos.json --salida $P/$F/crudo/alpaca_vivo.json`.
   Los `data.results` van a `$P/$F/crudo/cotizaciones.json` (de cada `quote`, al menos `instrument_id`,
   `bid_price`, `ask_price`, `bid_size`, `ask_size`, `mark_price`, `implied_volatility`, `delta`, `vega`,
   `updated_at`). Después de las 16:00 de Nueva York no se toma.

   `importar` exige que la foto de Alpaca salga a menos de 5 s del `updated_at` más reciente de Robinhood
   (antes del 27 de octubre quedaban a 1.3–1.4 s). Si no, los dos archivos van a `crudo/descartadas/` y se
   repite así: en segundo plano, fotos de Alpaca en bucle en una carpeta temporal `T`,

   ```bash
   fin=$((SECONDS + 150)); i=0
   while [ $SECONDS -lt $fin ]; do i=$((i + 1))
     python experiments/comparacion-robinhood/foto_alpaca.py --instrumentos $P/$F/instrumentos.json \
       --salida $T/alpaca_$(printf %03d $i).json > /dev/null
     sleep 0.7
   done
   ```

   y, mientras corre, `get_option_quotes`. A `crudo/alpaca_vivo.json` se copia la primera foto de `T` con
   `enviado_utc` posterior a ese `updated_at`. El 27 de octubre hizo falta: las dos primeras respuestas de
   Robinhood llegaron con unos 6 y 4 minutos de atraso, y la tercera salió 34 s antes que la foto de Alpaca.
5. `get_option_historicals` con cada lote y los parámetros de cada corte de `barras`; los `data.results`
   de un corte, juntos, van a `$P/$F/crudo/barras_0945.json` o `barras_1000.json`. `get_index_historicals`
   con los parámetros de `spx`; sus `data.results` van a `$P/$F/crudo/spx.json`.
6. `comparar.py importar --verificacion $V --privado $P`, luego
   `comparar.py dia --verificacion $V --privado $P --datos /home/user/quantileflow-datos` y
   `comparar.py acumulado --privado $P`.
7. Commit y push de `$P` (solo la rama `robinhood`; `main` no se toca).
8. Una fila en el registro diario de `docs/comparacion_robinhood.md` (sección 6), solo agregados. Los
   viernes, también el resumen y las secciones 2 a 4 con lo que da `comparar.py acumulado`.

`importar` rechaza lo que no cuadra: un id que no corresponde a su símbolo, una barra con el cierre fuera de
su máximo y mínimo, una marca que no es el punto medio o un contrato que falta. Si algo falla, se vuelve a
pedir y a copiar; no se corrige a mano.

## Cómo validar

```bash
python -m pytest -q tests/test_comparacion_robinhood.py
```

Las pruebas no usan red: el plan (también con el horario de invierno), la importación con sus rechazos y las
tres comparaciones. Para revisar un día hace falta acceso a la rama privada: `comparar.py dia` reproduce
`resultados.json` a partir de lo importado y de las capturas de Alpaca.
