# QuantileFlow-datos (privado)

Crudo de las capturas diarias de QuantileFlow en Alpaca. El repositorio es **privado** porque los
datos de mercado de Alpaca y OPRA no se pueden redistribuir. El código, los documentos y los informes
agregados están en el repositorio público
[hectorcs23/QuantileFlow](https://github.com/hectorcs23/QuantileFlow); ver `docs/fuente_alpaca.md`.

## Configuración (una sola vez)

1. En **Settings → Secrets and variables → Actions → New repository secret**, crear:
   - `APCA_API_KEY_ID`
   - `APCA_API_SECRET_KEY`

   Deben ser las claves de la cuenta *paper* de Alpaca. Los workflows las pasan a los scripts como
   variables de entorno y nunca se escriben en ningún archivo.
2. Para probar, ir a **Actions → captura-0945 → Run workflow** y marcar «ahora». Fuera de sesión,
   la prueba usa las últimas cotizaciones de la sesión anterior. **Actions → historico-alpaca → Run
   workflow** descarga el precio del objetivo de la última semana y los dividendos.

## Qué hacen los workflows

Todos descargan el código de captura del repositorio público en el commit fijado en `REF_CODIGO`
(revisado y verificado en `reports/verificacion/`). Cambiarlo es cambiar la versión de medición, y
cada manifiesto registra el commit usado.

**`captura-0945` y `captura-1000`** (con `captura-hora`, reutilizable): una hora de corte cada uno, en
su propia máquina y su propio proceso. Un fallo o un cuelgue en las 09:45 no toca a las 10:00.

- Cada uno tiene un disparo y un respaldo por horario (EDT y EST). Una compuerta deja pasar solo los
  que arrancan entre las 09:00 y las 09:43 (09:45) o las 09:58 (10:00) de Nueva York, y la
  concurrencia por hora hace que el respaldo espere a la corrida en curso.
- El script espera hasta 5 s antes del corte y captura en una ráfaga paralela:
  - SPXW: dos vencimientos a cada lado de 30 días y el más cercano (nivel implícito de SPX);
  - SPY: dos vencimientos a cada lado de 30 días;
  - la cotización IEX de SPY (diagnóstico).
- Cada página se guarda en cuanto llega y queda anotada en el **diario** de la captura, sincronizado
  en disco. El manifiesto final se escribe de forma atómica: está completo o no existe.
- **Plazo de preparación**: si los contratos y los vencimientos no están listos 6 minutos antes del
  corte, el proceso termina con código 4 y deja su registro. Así el respaldo, en cola en el mismo
  grupo, puede arrancar antes de la compuerta y llegar al corte. Un respaldo que arranca tarde tiene
  al menos 2 minutos. Es un escenario favorable, no una garantía. Depende de:
  - el retraso de los cron de GitHub, que pueden llegar muchos minutos tarde o no dispararse;
  - la cola;
  - la recuperación y el commit del titular;
  - el checkout y la instalación.

  Los registros de `ejecuciones/` miden si llegó.
- **Plazo absoluto**: 60 s después del corte, el proceso termina solo, con código 3, aunque una
  solicitud siga colgada. Un cuelgue durante la ráfaga no se rescata: se conserva lo que llegó, pero
  ese instante de mercado se pierde y queda registrado.
- El paso «Recuperar capturas interrumpidas» corre siempre. Convierte el diario de una captura
  cortada (por el plazo, el límite de tiempo del paso o una cancelación) en un manifiesto `parcial` o
  `fallida` con lo que llegó, marcado como interrumpido. La próxima ejecución también lo haría.
- «Guardar el crudo» hace commit de `raw/` aunque la captura haya sido parcial. Cada hora escribe
  archivos propios, así que los empujes paralelos no chocan.

Cada hora termina en uno de estos estados:

- `completa`;
- `parcial`: alguna solicitud falló, llegó después del corte o se interrumpió;
- `fallida`: ninguna cadena llegó a tiempo;
- `perdida`: sin captura y con el corte ya pasado.

La corrida queda en rojo en **Actions** si la hora no quedó completa. Los feriados no capturan: el
script consulta el calendario XNYS. Una hora con una captura completa no se repite, y un fallo después
del corte no se reemplaza con datos posteriores. Un respaldo que llega antes del corte sí repite una
captura interrumpida, con otra etiqueta (`-2`), y conserva la primera.

**`historico-alpaca`** (hacia las 10:21 de Nueva York): el precio del **objetivo**.

- Sin suscripción, Alpaca solo deja consultar el SIP pasados 15 minutos. Por eso, pasados 15 minutos
  y un margen de cada corte, pide las 1000 cotizaciones más recientes del NBBO consolidado de SPY
  hasta el corte (una sola página).
- Esa disponibilidad (el corte más 15 minutos) es la que fija la madurez de las etiquetas. El dato
  nunca entra en una medida del corte.
- Consulta los eventos corporativos de SPY (dividendos).
- Completa lo que falte de la última semana; un intento fallido se repite, porque el dato histórico no
  cambia.
- Anota el estado de cada hora de captura de esos días: un corte perdido queda registrado aunque no
  haya corrido ninguna captura.
- Guarda la cobertura de cada consulta de eventos, aunque venga vacía o falle. Alpaca no garantiza
  cuándo publica un evento, así que las etiquetas del objetivo pasan por tres estados:
  - **provisionales**: maduran con la primera consulta completa posterior a su fin;
  - **aceptadas**: bajo la política de 60 días, con una consulta recibida después de ese margen y sin
    discrepancias abiertas. Es una regla, no una garantía;
  - **pendientes**: mientras un dividendo que dejó de aparecer, o que llegó sin fecha ex o sin monto y
    podría caer en su periodo, no se resuelva con evidencia fechada.

## Estructura

```
raw/alpaca/<hash[:2]>/<sha256>_<nombre>.json.gz        cuerpos de respuesta, inmutables (gzip)
raw/alpaca/capturas/<fecha>/<fecha>T<HHMM>.json         manifiesto de cada captura (con su estado)
raw/alpaca/capturas/<fecha>/<fecha>T<HHMM>.diario.jsonl diario de la captura: una línea por página
raw/alpaca/historico/<fecha>/<fecha>T<HHMM>.json        manifiesto del SIP de cada corte
raw/alpaca/eventos/<fecha>/eventos-<instante>.json      manifiesto de cada consulta de eventos
raw/alpaca/ejecuciones/<fecha>/<inicio>[_sufijo].json   registro de cada ejecución: disparo, plazo y estados
resoluciones_dividendos.csv                             evidencia registrada a mano sobre dividendos (opcional)
```

**Resoluciones de dividendos.** Si un dividendo deja de aparecer en una consulta comparable, o llega
sin fecha ex o sin monto, sus etiquetas quedan pendientes. Solo lo resuelve que reaparezca, que el
proveedor lo corrija o complete, o una resolución registrada con evidencia, por ejemplo el aviso de
distribución del emisor. Se registra en `resoluciones_dividendos.csv` con las columnas:

| Columna | Qué lleva |
|---|---|
| `id_evento` | El `id` del evento en Alpaca |
| `simbolo` | El símbolo |
| `resolucion` | `vigente` o `cancelado` |
| `conocido_utc` | Cuándo se conoció la evidencia, con zona (`2026-11-20T15:00:00Z`); nunca antes de su publicación |
| `fuente` | De dónde sale la evidencia |
| `nota` | Opcional |
| `fecha_ex`, `monto` | Con `vigente`, los que el proveedor no dio (obligatorios entonces). Completan; no corrigen un valor ya dado. |

La normalización lo lee, lo valida y registra su hash. Cada línea es un cambio de medición: se
registra con commit, como el crudo.

Los registros de `ejecuciones/` son los que miden la puntualidad real: con qué retraso arrancó cada
disparo y cuánto margen quedó hasta cada corte. Una corrida en verde no la demuestra.

Cada manifiesto registra, por solicitud:

- la ruta, los parámetros y el estado;
- las cabeceras y las horas de envío y recepción;
- los hashes del archivo y del contenido.

También guarda el desfase del reloj, los vencimientos elegidos, la configuración y el commit del
código. El de una captura recuperada añade `interrumpida`, el motivo y el hash del diario. Las
credenciales no aparecen.

## Usar los datos

```bash
git clone https://github.com/hectorcs23/QuantileFlow.git
git clone https://github.com/hectorcs23/QuantileFlow-datos.git
cd QuantileFlow
python scripts/verificar_alpaca.py --datos ../QuantileFlow-datos --fecha 2026-09-28
# El rango de la normalización cubre también las sesiones finales de las etiquetas (cinco sesiones más).
python scripts/normalizar_alpaca.py --datos ../QuantileFlow-datos --desde 2026-09-28 --hasta 2026-11-13
N=../QuantileFlow-datos/normalized/alpaca
python scripts/piloto.py --cotizaciones $N/cotizaciones.parquet --subyacente $N/subyacente.parquet \
    --dividendos $N/dividendos.parquet --cobertura-dividendos $N/cobertura_dividendos.parquet \
    --fuente-objetivo alpaca/sip --desde 2026-09-28 --hasta 2026-11-06
```

Los papeles, sin mezclarlos:

- las **señales** salen de SPXW;
- la **referencia** de las opciones es el nivel de SPX inferido por paridad (`implicito`);
- el **objetivo** es SPY del SIP (`--fuente-objetivo alpaca/sip`), con rendimiento total (dividendos
  en su fecha ex) y de precio por separado.

La normalización lee solo el crudo, comprueba sus hashes y aplica `resoluciones_dividendos.csv` si
existe: reprocesar da los mismos bytes. Su manifiesto resume las versiones de los dividendos, los
retiros, las discrepancias abiertas y las contradicciones con las resoluciones, para medir cuánto
revisa Alpaca lo que ya había publicado.
