# Experimento de calls y puts — muestra hasta el 6 de octubre de 2026

Resultados: `RESULTADOS_Y_SIGUIENTE_PRUEBA.md`. Análisis terminado el 7 de octubre.

Este directorio contiene código y agregados. El detalle de cotizaciones y pares permanece fuera del repositorio de código. No es un backtest de una estrategia ni una prueba de rentabilidad.

## Reproducción

Se necesita el entorno Python del proyecto QuantileFlow, un checkout de `56cad99db55475fc243b3672f8243ef287432114` (mismo código de ejecución que `4ffde8a`), las cuatro tablas de la normalización auditada y los diagnósticos estrictos de los días 2, 5 y 6.

```powershell
python explorar_intradia.py `
  --codigo 'RUTA_CHECKOUT_QUANTILEFLOW' `
  --tablas 'RUTA_TABLAS_NORMALIZADAS' `
  --diagnosticos 'RUTA_AUDITORIA_20261006' `
  --salida '.\resultados' `
  --privado 'RUTA_PRIVADA_FUERA_DEL_REPO'

python presentar_resultados.py

$env:QF_CODE = 'RUTA_CHECKOUT_QUANTILEFLOW'
python -m pytest --rootdir=. -q -p no:cacheprovider test_exploracion.py
```

`--diagnosticos` debe contener `diagnostico_2026-10-02/resumen.json`, `diagnostico_2026-10-05/resumen.json` y `diagnostico_2026-10-06/resumen.json`. RR25 se toma de esos diagnósticos; los residuos nuevos se calculan desde `cotizaciones.parquet` y `subyacente.parquet`.

Los datos fuente originales permanecen en el snapshot privado `66ccade52501c2e6dbbd70e6834969684147c9b3`. No se incluyen las tablas de entrada ni el detalle por contrato. Los scripts existentes `scripts/normalizar_alpaca.py` y `scripts/verificar_alpaca.py` permiten reconstruir las entradas; consultar su `--help` para indicar las rutas privadas. Ningún secreto se requiere para ejecutar este experimento sobre archivos locales.

## Repetir con cinco sesiones

`--fechas` acepta fechas explícitas, únicas y ordenadas. Si se omite, conserva la muestra original del 2, 5 y 6. Requiere los dos cortes completos y un diagnóstico estricto de cada día seleccionado. Usar una salida nueva para conservar los agregados originales:

```bash
python explorar_intradia.py \
  --codigo /ruta/QuantileFlow \
  --tablas /ruta/privada/tablas \
  --diagnosticos /ruta/privada/diagnosticos \
  --salida ./resultados_5sesiones \
  --privado /ruta/privada/pares_5sesiones \
  --fechas 2026-10-02 2026-10-05 2026-10-06 2026-10-07 2026-10-08

python presentar_resultados.py \
  --resultados ./resultados_5sesiones \
  --figura ./HALLAZGOS_5SESIONES.png

python -m pytest --rootdir=. -q -p no:cacheprovider test_exploracion.py
```

El último comando detecta por defecto el checkout que contiene `experiments/intradia_20261007`; `QF_CODE` permite elegir otro. Esta publicación añade cuatro casos de prueba de selección de fechas a los cinco controles originales: **nueve pruebas** en total. La extensión no cambia las reglas de pares, filtros, referencia, bandas ni persistencia. Los resultados guardados siguen siendo los de las tres sesiones originales; la réplica de cinco no se ejecutó en esta publicación.

Los hashes de las cuatro entradas se guardan en `resultados/resultados.json`. Para comparar huellas exactas de Parquet, usar la misma versión de normalización y dependencias; una diferencia de bytes requiere también comparar esquemas, filas y valores antes de concluir que el contenido cambió.

## Parámetros fijados antes de leer los resultados

- Fechas: 2, 5 y 6 de octubre; horarios 09:45 y 10:00 ET.
- Residuos: SPXW europeo, por vencimiento y strike; 0DTE separado del resto.
- Zona de resumen: valor absoluto de log(K/F) ≤0.05; pares válidos en ambos cortes para persistencia.
- Tres sensibilidades de frescura: 60 s sin límite adicional entre patas; 30 s / 5 s; 10 s / 2 s.
- Fuera de banda: residuo absoluto mayor que la suma de semispreads de las dos patas.
- Sin entrenamiento, optimización de umbrales, p-valores ni predicción de retornos.

Después de la primera corrida se agregó la descomposición selección/reajuste para evitar confundir cambios de muestra con cambios de referencia. Ese control adicional conserva la cohorte de evaluación definida con la referencia base. No se ajustaron umbrales al observar los resultados.

Después de revisar las tasas implícitas extremas se agregó sensibilidad de descuento al 3%, 4% y 5%, evaluada sobre los mismos pares de la cohorte base. Es un diagnóstico posterior al primer resultado, no una hipótesis predictiva preespecificada. La curva de tasas observada queda pendiente.
