# QuantileFlow-datos (privado)

Crudo de las capturas diarias de QuantileFlow en Alpaca. El repositorio es **privado** porque los
datos de mercado de Alpaca y OPRA no se pueden redistribuir. El código, los documentos y los informes
agregados están en el repositorio público
[hectorcs23/QuantileFlow](https://github.com/hectorcs23/QuantileFlow); ver `docs/fuente_alpaca.md`.

## Configuración (una sola vez)

1. En **Settings → Secrets and variables → Actions → New repository secret**, crear:
   - `APCA_API_KEY_ID`
   - `APCA_API_SECRET_KEY`

   Deben ser las claves de la cuenta *paper* de Alpaca. El workflow las pasa al script como variables
   de entorno y nunca se escriben en ningún archivo.
2. Para probar, ir a **Actions → captura-alpaca → Run workflow** y marcar «ahora». Fuera de sesión,
   la prueba usa las últimas cotizaciones de la sesión anterior.

## Qué hace el workflow

- Arranca cada día hábil hacia las 09:17 de Nueva York; si ese disparo falla, hay un respaldo a las
  09:32. Una compuerta horaria resuelve el cambio entre EDT y EST.
- Descarga el código de captura del repositorio público en el commit fijado en `REF_CODIGO`
  (`79c1554`, revisado y verificado). Cambiarlo es cambiar la versión de medición. Cada manifiesto
  registra el commit usado.
- Espera hasta 5 s antes de las 09:45 y de las 10:00 y captura en una ráfaga paralela:
  - SPXW: dos vencimientos a cada lado de 30 días y el más cercano (nivel implícito de SPX);
  - SPY: dos vencimientos a cada lado de 30 días;
  - la cotización IEX de SPY.
- Hace commit de `raw/` aunque la captura haya sido parcial.

Cada hora termina en uno de estos estados:

- `completa`;
- `parcial`: alguna solicitud falló o llegó después del corte;
- `fallida`: ninguna cadena llegó a tiempo;
- `perdida`: sin captura y con el corte ya pasado.

La corrida queda en rojo en **Actions** si alguna hora no quedó completa. Los feriados no capturan:
el script consulta el calendario XNYS. Una hora con una captura completa no se repite, y un fallo
después del corte no se reemplaza con datos posteriores.

Cada paso de preparación tiene un límite de 5 a 8 minutos. Así, un primer disparo atascado libera al
respaldo antes del corte.

## Estructura

```
raw/alpaca/<hash[:2]>/<sha256>_<nombre>.json.gz   cuerpos de respuesta, inmutables (gzip)
raw/alpaca/capturas/<fecha>/<fecha>T<HHMM>.json   manifiesto de cada captura (con su estado)
raw/alpaca/ejecuciones/<fecha>/<inicio>.json      registro de cada ejecución: disparo, margen y estados
```

Los registros de `ejecuciones/` son los que miden la puntualidad real: con qué retraso arrancó cada
disparo y cuánto margen quedó hasta cada corte. Una corrida en verde no la demuestra.

Cada manifiesto registra, por solicitud, la ruta, los parámetros, el estado, las cabeceras, las horas
de envío y recepción y los hashes del archivo y del contenido. También guarda el desfase del reloj, los
vencimientos elegidos, la configuración y el commit del código. Las credenciales no aparecen.

## Usar los datos

```bash
git clone https://github.com/hectorcs23/QuantileFlow.git
git clone https://github.com/hectorcs23/QuantileFlow-datos.git
cd QuantileFlow
python scripts/verificar_alpaca.py --datos ../QuantileFlow-datos --fecha 2026-09-28
python scripts/normalizar_alpaca.py --datos ../QuantileFlow-datos --desde 2026-09-28 --hasta 2026-11-06
python scripts/piloto.py --cotizaciones ../QuantileFlow-datos/normalized/alpaca/cotizaciones.parquet \
    --subyacente ../QuantileFlow-datos/normalized/alpaca/subyacente.parquet --desde 2026-09-28 --hasta 2026-11-06
```

La normalización lee solo el crudo y comprueba sus hashes: reprocesar da los mismos bytes.
