# Validación corregida de bt2

Fecha: 2 de octubre de 2026. Estudio retrospectivo, no confirmación prospectiva ni backtest de ejecución.
Los resultados de bt2 en `resultados/skew_*.json` se mantienen como referencia histórica.

## Qué se corrigió

- La convergencia llamada antes «operable» ahora se interpreta como **convergencia retrasada del
  indicador VWAP**. La clave JSON histórica se conserva por compatibilidad.
- La comparación ingenua/retrasada y la curva 10/20/30/45 minutos usan cohortes emparejadas. Se
  reportan las salidas ausentes y un escenario de sensibilidad con resultado cero en esas salidas;
  este escenario no es una imputación de mercado ni un límite conservador garantizado.
- La persistencia usa los mismos orígenes para todos los rezagos. No estima fracción de ruido ni
  vida media latente: los datos no identifican esos componentes sin supuestos adicionales.
- La ventana de fechas y el calendario XNYS son explícitos; las sesiones ausentes siguen ocupando
  su lugar en la base de 60 sesiones. Los cierres tempranos se respetan.
- El pronóstico diario usa objetivos que comienzan después de la disponibilidad de la señal. Las
  etiquetas del ajuste deben haber madurado antes de cada fecha de pronóstico; se evalúa riesgo
  incremental frente a VIX y retorno absoluto, sobre las mismas fechas.
- Se guardan SHA-256 de entradas y código, versiones, parámetros, archivos por sesión y registros
  de señales/pronósticos. Los datos y registros individuales quedan fuera del Git público.
- El corte de 2021 es histórico y ya fue examinado. Las especificaciones de esta validación se
  eligieron antes de recalcular sus resultados, pero eso no las convierte en preregistro ni holdout nuevo.

## Cómo repetir

Desde la raíz del repositorio, con las dependencias de `requirements-bloqueo.txt`:

```bash
python -m pytest -q tests/test_exploracion_datos_gratis.py tests/test_validacion_skew.py
python experiments/exploracion-datos-gratis/validar_ruido.py
# Copiar la rama privada exploracion a data/exploracion/0dte/, o indicar --datos.
python experiments/exploracion-datos-gratis/validar_0dte.py --desde 2024-02-01 --hasta 2026-10-01
python experiments/exploracion-datos-gratis/validar_0dte.py --antiguedad-maxima 1 --salida experiments/exploracion-datos-gratis/resultados/validacion_0dte_edad1.json
python experiments/exploracion-datos-gratis/comparar_antiguedad.py
# skew_cboe.py obtiene la caché diaria; validar_cboe.py lee esos mismos archivos.
python experiments/exploracion-datos-gratis/skew_cboe.py
python experiments/exploracion-datos-gratis/validar_cboe.py
```

La sensibilidad de antigüedad usa únicamente barras del minuto inmediatamente anterior, para reducir
la asincronía; conserva el precio de operaciones y reduce cobertura. Un resultado menor tampoco probaría
que todo sea ruido: cambia la muestra y los contratos disponibles.
`comparar_antiguedad.py` congela las señales y direcciones de la ventana de cinco minutos y compara
ambas medidas sobre las mismas entradas/salidas observadas, evitando reseleccionar señales.

Los archivos SHA-256 permiten identificar las entradas. Una nueva descarga puede cambiar por revisiones
del proveedor; conservar las fechas y la semilla no basta para garantizar igualdad byte a byte.

## Criterio de interpretación

Una asociación significativa en muestra puede coexistir con una mejora de pronóstico incierta o inestable.
Para la métrica primaria diaria se compara el MSE de dos modelos OLS expansivos, con y sin `zskew`,
pronosticando la raíz de la suma de cinco retornos al cuadrado: el primero de la próxima apertura al
cierre, y los cuatro siguientes de cierre a cierre. No es el objetivo `rv5` original, que incluye el
primer overnight. El bootstrap usa bloques de 10 sesiones y conserva la pareja de pérdidas.

Una convergencia positiva del RR25 interpolado tampoco es beneficio de un risk reversal: las patas y
sus vegas pueden cambiar entre observaciones. Para identificar rentabilidad hacen falta cotizaciones
históricas, contratos fijos, ejecución con bid/ask, cobertura causal y costos completos.

El contraejemplo `validacion_ruido.json` usa un skew verdadero constante y error AR(0.90). Su convergencia
retrasada es +1.0295 puntos, IC95 [0.9764, 1.0830]. Una serie observada idéntica también admite un skew
económico AR(0.90) sin error de medida. Esa equivalencia impide identificar reversión económica con
este estimador solamente.

## Resultados y conclusión

Las cifras independientes y el estado de reproducción se documentan en [CONCLUSIONES.md](CONCLUSIONES.md).
Las limitaciones forman parte del resultado; no se deben sustituir por una vida media o P&L inferidos.
