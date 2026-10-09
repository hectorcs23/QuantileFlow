# Revisión del PDE, el adjunto y la captura ampliada

**Fecha:** 9 de octubre de 2026. **Rama revisada:** `codex/pde-captura-gratis-20261009`, commit `a5fa04d`,
sobre `fb4db92`. **Resultado:** se reproduce exactamente, la matemática es correcta y no toca la producción.
La primera prueba real de la captura ampliada, el paso 1 del informe, terminó completa.

Solo se publican agregados. El crudo de la prueba real y la copia del repositorio de datos quedaron en una
carpeta temporal fuera de Git y se borraron al terminar. Las claves de Alpaca estaban en el entorno y no se
escribieron en ningún archivo.

## Resumen

- **Reproducción exacta.**
  - Pasan las 270 pruebas.
  - El benchmark de 90 casos da los mismos máximos que el informe.
  - El gradiente del adjunto coincide con las diferencias centrales: error 2.1e-9.
- **Matemática.** Revisé el solver línea por línea.
  - Conserva la masa y no produce masas negativas.
  - El adjunto usa la transpuesta exacta del paso hacia adelante.
  - Las fórmulas de delta, vega, tasa y dividendo son correctas.
- **Producción intacta.**
  - Ningún script de captura, normalización o diagnóstico usa el PDE.
  - La selección de varios plazos solo se activa con `objetivos_dias`, que la configuración vigente no
    tiene.
  - La captura sigue fijada en `4ffde8a`.
- **Auditoría del crudo.** Con el mismo snapshot privado, `8adb35f`, da lo mismo que el informe:
  - 195 páginas únicas, todas con huellas correctas;
  - 15 cadenas SPXW y 12 SPY con los metadatos del viernes.

  Solo cambian las huellas de los manifiestos, por los finales de línea de Windows (sección 4).
- **Prueba real de la captura ampliada (paso 1).** Hoy a las 14:05 de Nueva York, aislada:
  - 36 cadenas, 19 SPXW y 17 SPY, frente a las 9 de hoy;
  - cubre los plazos de 7, 14, 30, 60 y 90 días en las dos raíces;
  - 42 solicitudes HTTP, todas respondidas al primer intento, sin errores ni respuestas 429.

  La ráfaga de cadenas duró 2.3 s; la de producción dura entre 0.4 y 0.9 s. Trae unas 5 veces más
  cotizaciones: 16 910 frente a 3 440.
- **Falta el paso 2.** Una captura inmediata no mide si las respuestas llegan antes del corte. Propongo
  medirlo el lunes a las 09:50 y a las 10:05, sin tocar las capturas del piloto (sección 5).
- **Minutos de Actions.** Al calcular el costo de una captura más, medí el gasto real:
  - unos 85 minutos por sesión;
  - unos 1 870 al mes con 22 sesiones;
  - el límite de GitHub Free para repositorios privados es de 2 000.

  Queda poco margen (sección 6).

## 1. Qué se comprobó

**Contenido de la rama.** Es un solo commit, `a5fa04d`, sobre `fb4db92`, con 17 archivos.

- **Nuevos:**
  - `quantileflow/pde.py`;
  - `tests/test_pde.py`, `tests/test_captura_manual.py` y `tests/test_auditar_crudo.py`;
  - la carpeta `experiments/pde_gratis_20261009/`;
  - `docs/AVANCE_PDE_GRATIS_2026-10-09.md`.
- **Cambiados:**
  - casos nuevos en `tests/test_alpaca.py`;
  - tres archivos de `experiments/expiraciones_20261008/`: la nota del presupuesto en US$0 y una línea de
    comentario de la configuración propuesta.
- **Sin cambios:** `scripts/`, `configs/`, los workflows y los demás módulos de `quantileflow/`.

La selección de varios plazos, `elegir_vencimientos_multiples`, no llega en esta rama. Entró antes, en
`d65623e`, y ya está en `fb4db92`. Frente al código fijado en producción, `4ffde8a`, el código cambia en
cuatro archivos:

- `quantileflow/pde.py` y `quantileflow/escenarios.py`: son nuevos y ningún script de producción los
  importa;
- `quantileflow/alpaca.py`: agrega esa función, en 25 líneas;
- `scripts/capturar_alpaca.py`: agrega, en 13 líneas, la rama que la usa. Solo corre si la configuración
  trae `objetivos_dias`.

`configs/` y los workflows no cambian. `configs/captura_alpaca.toml` sigue con `objetivo_dias = 30` y una
ventana de contratos de 50 días.

**Pruebas.** Con el comando del README pasan las 270 pruebas, en 75 s. Solo las de `tests/` son 247.

**Benchmark.** Se volvió a correr `benchmark.py` con la misma malla: 1 601 nodos, 2 400 pasos e
`y ∈ [−1.5, 1.5]`.

| Cifra máxima | Informe | Reproducción |
|---|---:|---:|
| Error de prima frente a BS | 0.000464786 | 0.000464786 |
| Error de delta | 3.53222e-05 | 3.53222e-05 |
| Error de vega | 0.00176767 | 0.00176767 |
| Error de conservación de masa | 8.11795e-13 | 8.11795e-13 |
| Precio hacia adelante frente a hacia atrás | 3.90799e-14 | 3.90799e-14 |
| Masa en los nodos de frontera | 2.72362e-12 | 2.72362e-12 |
| Residuo del paso hacia adelante | 2.22045e-16 | 2.22045e-16 |
| Residuo del adjunto | 9.09495e-13 | 9.09495e-13 |
| Gradiente espacial frente a diferencias centrales | 2.13058e-09 | 2.13058e-09 |
| Cocientes de Taylor | 3.988, 3.994, 3.997 | 3.988, 3.994, 3.997 |

**Refinamiento.** `verificacion.json` respalda lo que dice el informe:

- **Refinamiento conjunto.** Al duplicar los nodos y cuadruplicar los pasos, el error baja 4 veces en cada
  paso: 0.005495, 0.001373, 0.000343 y 0.0000858. Es lo esperado con primer orden en el tiempo y segundo en
  el espacio.
- **Solo el espacio.** Si se refina solo el espacio, el error no baja siempre: 0.000449, 0.0000431,
  0.0000599 y 0.0000858. Los errores de espacio y de tiempo se compensan en parte.
- **Dominio corto.** Con medio ancho 0.5, la prima es 8.916; con 1.0 y 1.5, es 9.172. Un dominio corto
  conserva la masa y aun así sesga el precio, como advierte el informe.

**Huellas de las fuentes.** `verificacion.json` guarda las huellas de tres archivos.

- `pde.py` y `benchmark.py` coinciden.
- `opciones.py` coincide solo con finales de línea de Windows (CRLF). El contenido es el mismo.

**Auditoría.** Se repitió `auditar_crudo.py` sobre una copia del snapshot privado `8adb35f`. Coinciden:

- los conteos: 13 manifiestos de capturas, 30 del histórico y 8 de eventos;
- las 195 páginas únicas;
- las filas del día;
- la selección con los metadatos del viernes: de 30 vencimientos SPXW y 16 SPY en los metadatos, elige 15
  y 12, y solo rodea los plazos de 7, 14 y 30 días.

Solo difieren las cinco huellas de los manifiestos (sección 4).

## 2. Revisión matemática

- **Malla.** Es una malla en `y = log(S/S₀)`.
  - La tasa de salto hacia arriba es `D/h² + μ/(2h)` y hacia abajo `D/h² − μ/(2h)`.
  - Si alguna sale negativa, el solver rechaza la malla.
  - Así, el paso implícito nunca produce masas negativas.
- **Fronteras reflectantes.** Cada columna de `A` suma 1, así que la masa total se conserva exacta. El error
  de 8e-13 es redondeo.
- **Adjunto.** Resuelve con `Aᵀ`, la transpuesta del mismo paso. Por eso el precio por masas y el precio
  hacia atrás coinciden hasta 3.9e-14.
- **Gradiente en σ.**
  - La derivada de las tasas es `σ/h² − σ/(2h)` hacia arriba y `σ/h² + σ/(2h)` hacia abajo.
  - En las fronteras no se suma, porque allí esas tasas valen cero.
  - La suma del gradiente por nodo es la vega de un aumento parejo de σ.
- **Tasa y dividendo.**
  - La sensibilidad a la tasa es la derivada respecto de `μ` menos `T` por el precio: la segunda parte
    viene del descuento.
  - La sensibilidad al dividendo continuo es menos la derivada respecto de `μ`.
- **Delta.** Se calcula con σ fija en coordenadas relativas al spot, como dice el informe.
- **Notación.** En el informe, `G` actúa sobre las masas: es la transpuesta del generador que actúa sobre
  funciones. El código es consistente; basta una frase para aclararlo.

Los límites que el informe declara son correctos:

- σ(y) no cambia con el tiempo;
- las masas son de la medida Q, no probabilidades reales;
- SPY es americana y no queda cubierta;
- la memoria crece con nodos × pasos: unos 31 MB con 1 601 × 2 400.

## 3. Prueba real de la captura ampliada (paso 1 del informe)

**Cómo se hizo.**

- Se corrió `captura_manual.py --ejecutar` desde la rama, a una carpeta temporal nueva fuera de Git.
- Fue el viernes 9 a las 14:05 de Nueva York, en modo inmediato.
- Se usó la configuración propuesta: indicative/IEX, 12 hilos, 2 reintentos y una ventana de contratos de
  120 días.

| Medida | Producción hoy, 09:45 y 10:00 | Ampliada, 14:05 |
|---|---|---|
| Cadenas | 9: 5 SPXW y 4 SPY | 36: 19 SPXW y 17 SPY |
| Páginas de cadenas | 9 | 37: una cadena SPXW, la del 31 de diciembre, tuvo dos |
| Plazos | SPXW: el del día y de 27 a 32 días; SPY: de 21 a 42 días | SPXW: el del día y de 5 a 112 días; SPY: de 5 a 112 |
| Plazos objetivo con dos vencimientos a cada lado | 30 días | 7, 14, 30, 60 y 90 días, en las dos raíces |
| Cotizaciones | 3 440 | 16 910 |
| Contenido de las cadenas, sin comprimir | 1.67 MB | 8.0 MB |
| Duración de la ráfaga | 0.69 y 0.75 s; entre 0.39 y 0.88 s en las 12 capturas del 2 al 9 | 2.29 s |
| Solicitudes HTTP, una por página | 14 | 42: todas 200, al primer intento, sin 429 ni errores |
| Mínimo restante del límite de 200 por minuto | 190 | 167 |
| Crudo comprimido guardado por sesión | unos 1.3 MB | unos 3.9 MB |

- **Detalle de la ráfaga.** Las cadenas tardaron 2.26 s: la mediana de cada página fue 0.59 s y la más lenta,
  1.07 s.
- **Crudo por sesión.**
  - Los contratos se guardan una vez por sesión, porque los dos cortes comparten las mismas páginas: 0.70 MB
    hoy y 0.97 MB en la ampliada.
  - Las cadenas se guardan en cada corte: 0.31 MB hoy y 1.47 MB en la ampliada.

**Lectura.**

- **Holgura antes del corte.** La ráfaga empieza 5 s antes del corte.
  - En la apertura, las 10 páginas de producción tardan entre 0.4 y 0.9 s.
  - Con 12 hilos, 38 páginas son unas 3 o 4 tandas, así que en la apertura la ráfaga podría tardar de 1.5 a
    3.5 s.
  - Cabría, pero con menos margen. Bastaría una página lenta o un reintento, con espera de hasta 1 s y hasta
    2 por solicitud, para que una cadena llegue después del corte y ese corte quede `parcial`.
- **El modo inmediato no mide elegibilidad.** En esta prueba el corte es el instante de inicio.
  - Las 38 respuestas de cadenas y acciones figuran «después del corte».
  - El nivel implícito no se identifica.
  - En modo inmediato, el estado `completa` no considera la llegada tardía.

  Esta prueba mide la carga, no la elegibilidad, como dice el informe.
- **Almacenamiento.** La ampliada guarda unos 3.9 MB por sesión, frente a 1.3 MB.
  - Son cerca de 1 GB por año de sesiones, frente a unos 0.33 GB.
  - GitHub recomienda repositorios de menos de 1 GB.
  - No es urgente, pero convendría decidir antes de un año cómo partir el repositorio de datos.

## 4. Observaciones menores

1. **Huellas que dependen de Windows.**
   - Las cinco huellas de los manifiestos de `integridad_privada.json` son de copias con finales de línea
     CRLF. También lo es la huella de `opciones.py` en `verificacion.json`.
   - En Linux y en GitHub, donde los archivos tienen LF, no coinciden. Las páginas del crudo, que son gzip,
     no se ven afectadas.
   - Conviene calcular las huellas sobre el contenido con LF, o usar el identificador de Git del archivo.
   - Una opción es agregar un `.gitattributes` con `* text=auto eol=lf`. En QuantileFlow puede entrar en el
     mantenimiento; en QuantileFlow-datos requiere la aprobación del usuario.
2. **Finales de línea mezclados en la configuración propuesta.**
   - `captura_propuesta.toml` tiene 67 líneas CRLF y una LF, la que se editó.
   - Cada manifiesto guarda la huella de la configuración, así que conviene normalizarla a LF antes de
     desplegarla.
3. **Rutas con barra invertida.** `sha256_fuentes` escribe las rutas con `\`. Es solo estético.
4. **El estado «correcta» de la auditoría.** `integridad_huellas` es texto fijo, pero está bien así:
   `leer_crudo` falla ante cualquier huella distinta, y el JSON solo se escribe si pasan las 195 páginas.

## 5. Sobre los próximos pasos del informe

1. **Medir una captura ampliada real aislada.** Hecho (sección 3).
2. **Comprobar el horario causal.** Propongo, para el lunes 12 de octubre:
   - **Cuándo:** capturas programadas a las 09:50 y a las 10:05 de Nueva York.
   - **Cómo:** con la configuración propuesta y una carpeta privada temporal, lanzadas desde esta sesión. Las
     claves ya están en el entorno.
   - **Por qué a esas horas:** no a las 09:45 ni a las 10:00, para no compartir con las ráfagas del piloto el
     límite de solicitudes de la cuenta ni la red.
   - **Qué medir:** las respuestas después del corte, el estado de cada corte y las filas válidas al corte por
     raíz y plazo, incluidas las de 60 y 90 días. Todavía no se sabe cómo es indicative a esos plazos.

   Si cabe, la ruta más segura no es cambiar la captura del piloto, que ya está aceptada. Hay dos opciones:
   - **Una captura aparte.** Cuesta minutos de Actions (sección 6).
   - **Dentro del job de las 10:00.** Ese job ya espera sin hacer nada desde las 09:16, así que no cuesta
     minutos. Cambia el código de captura: entraría en el mantenimiento, con un nuevo commit fijado.
3. **Sensibilidad de la distribución.** De acuerdo.
   - La función de distribución en un punto es lineal en las masas finales. Su adjunto es el mismo del
     precio, con un pago indicador promediado por celda.
   - La derivada de un cuantil divide por la densidad en ese cuantil, así que es ruidosa en las colas y no
     está definida en las mesetas.
   - Conviene usar la convención de mesetas que el proyecto ya tiene, la de los cuantiles con mesetas (H6).
4. **Calibración controlada.** De acuerdo con el orden: primero recuperar una σ conocida desde precios
   sintéticos.
   - Una σ(y) que no cambia con el tiempo no puede ajustar a la vez cinco plazos, porque no tiene estructura
     temporal.
   - Hará falta una σ por tramo de tiempo. El adjunto se extiende directo: un gradiente por tramo y por nodo.
5. **Selector de contratos.** Lo dejaría para después del piloto y del protocolo predictivo.
   - Las masas son de Q.
   - Elegir contratos según el movimiento esperado requiere evidencia sobre la probabilidad real, que el
     proyecto todavía no tiene.
   - Como herramienta de escenarios condicionales, tal como lo plantea el informe, sí sirve.

**Presupuesto.** Con el presupuesto en US$0 desde el 9 de octubre, el contraste con OPRA queda en suspenso
y se sigue con indicative.

## 6. Minutos de GitHub Actions

Se midió desde los tiempos de cada job del repositorio de datos. Cada job se redondea al minuto, como
factura GitHub.

| Sesión | Minutos |
|---|---:|
| Viernes 2 de octubre | 85 |
| Lunes 5 | 99, con 16 de un job que nunca consiguió runner; probablemente no se factura |
| Martes 6 | 84 |
| Miércoles 7 | 85 |
| Jueves 8 | 84 |
| Viernes 9 | 74 hasta ahora; faltan los cron tardíos que llegan por la tarde |

**Por sesión** son unos 85 minutos:

| Concepto | Minutos |
|---|---:|
| `captura-0945` | unos 29 |
| `captura-1000` | unos 44 |
| `historico` | 1 |
| Unos 9 cron tardíos que la compuerta descarta | 1 cada uno |

**Al mes**, con 22 sesiones, son unos 1 870 minutos.

- GitHub Free incluye 2 000 minutos al mes para repositorios privados; GitHub Pro, 3 000.
- Desde aquí no se puede leer el plan de la cuenta. Se ve en GitHub, en *Settings → Billing and plans*.
- Si se agotan los minutos y no hay medio de pago, GitHub deja de correr los jobs hasta el siguiente ciclo,
  y se perderían sesiones.
- La estimación anterior era de 80 minutos por sesión y 1 650 al mes ([aceptación](aceptacion_operacion.md),
  sección 5). Lo medido es algo más.

**Cómo ganar margen sin cambiar código.** Se puede lanzar `captura-1000` a las 09:35 en lugar de a las 09:14.

- Esperaría unos 25 minutos en lugar de 44.
- Ahorra unos 18 minutos por sesión y unos 400 al mes, con lo que quedarían unos 1 470.
- La revisión de runners de ese job pasaría a las 09:42. Un relanzamiento llegaría con margen, porque la
  preparación tiene que estar lista 6 minutos antes del corte.

Esto cambia la rutina que aprobó el usuario, así que la decisión es suya.

## 7. Cómo repetir esta revisión

Desde la raíz de QuantileFlow, con una copia del repositorio de datos en `COPIA_DATOS`:

```bash
git worktree add ../pde origin/codex/pde-captura-gratis-20261009
cd ../pde
python -m pytest -q tests experiments/expiraciones_20261008/test_expiraciones.py \
  experiments/intradia_20261007/test_exploracion.py      # el comando del README: 270 pruebas
python experiments/pde_gratis_20261009/benchmark.py      # reescribe resultados/; comparar verificacion.json
python experiments/pde_gratis_20261009/auditar_crudo.py --datos COPIA_DATOS --fecha 2026-10-09 \
  --snapshot 8adb35f6abcaaa238c2bca48169d4a23dc9c99b1 --salida PRIVADO/auditoria.json
python experiments/pde_gratis_20261009/captura_manual.py # solo muestra el plan, sin red
# Con claves en el entorno, la prueba aislada:
python experiments/pde_gratis_20261009/captura_manual.py --ejecutar --datos PRIVADO/captura-ampliada
```

`PRIVADO` es una carpeta fuera de cualquier checkout de Git. Las huellas de los manifiestos solo coinciden
con las del informe si los archivos tienen finales de línea CRLF (sección 4).
