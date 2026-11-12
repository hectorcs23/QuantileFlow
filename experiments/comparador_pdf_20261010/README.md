# Comparador de contratos desde una PDF consistente

10 de octubre de 2026. Cotizaciones y resultados **sintéticos**; gasto en datos US$0.
El capital ficticio de US$500 del ejemplo no es un presupuesto autorizado para operar.

```powershell
python experiments/comparador_pdf_20261010/demo.py --presupuesto 500 --movimiento .03 --dias 7
python -m pytest tests/test_comparador_pdf.py tests/test_escenarios.py -q
```

`--salida` permite guardar otro experimento sin sobrescribir el ejemplo de referencia.
Los plazos se miden en días naturales desde la entrada; .03 significa +3% de spot.
La demo cambia movimiento, horizonte y presupuesto. La biblioteca permite especificar
otros strikes, DTE, calls/puts, IV, multiplicador, cotizaciones y escenarios.

Se compara compra a ask, cantidad entera máxima permitida y salida a precio del
modelo menos un semispread supuesto, reservando comisión de entrada y cierre.
Al vencimiento se usa payoff, sin semispread, con comisión conservadora de cierre.
No se simulan entrega física, impuestos, interés de la caja ni financiación.

Los tres rankings son ganancia del escenario objetivo, retorno sobre capital
reservado y mínimo PnL de los escenarios. El ranking robusto incluye efectivo
con PnL cero. Las listas de contratos incluyen también candidatos con pérdidas;
el primero de una lista no implica que convenga operar.

La PDF, sus cuantiles y la probabilidad ITM son Q **al vencimiento restante**
condicionadas al spot/IV del escenario. No son probabilidades físicas de acertar
el escenario ni probabilidades de tener PnL positivo al salir.

Se compara con una malla más fina y se guardan las diferencias de PnL y ranking.
Las tolerancias de frontera/momento no prueban por sí solas convergencia del ranking.
Cada candidato es una serie de opciones largas por separado, no una cartera.

Archivos: `entrada.json`, `comparacion.json`, `pnl_escenarios.csv`,
`sensibilidad_spot_iv.csv`, `sensibilidad_plazo_costos_presupuesto.csv`,
`verificacion.json` y `comparador_sensibilidad.png`. Todos contienen solo datos
sintéticos; el JSON registra parámetros, entorno y hashes de fuentes con LF.

En el mapa se permite una elección diferente por celda para ilustrar cambios de
preferencia. No representa una estrategia que conoce el resultado por adelantado.
El PnL de un contrato elegido inicialmente se muestra por separado.
