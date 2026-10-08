# Comparación de expiraciones y evaluación de datos

Plan y criterios: [PLAN_DATOS_Y_EXPIRACIONES.md](PLAN_DATOS_Y_EXPIRACIONES.md).
Cobertura actual: [resultados/COBERTURA.md](resultados/COBERTURA.md).

Desde la raíz de QuantileFlow, con las dependencias del proyecto:

```powershell
python experiments/expiraciones_20261008/comparar_expiraciones.py --tablas RUTA_PRIVADA_TABLAS --salida experiments/expiraciones_20261008/resultados --fechas 2026-10-02 2026-10-05 2026-10-06 2026-10-07 2026-10-08
python -m pytest -q tests experiments/expiraciones_20261008/test_expiraciones.py
```

La salida incluye agregados por cadena/plazo, fechas, procedencia y hashes de entradas/configuración/script. No incluye bid/ask por contrato, strikes ni residuos individuales. El analizador actual acepta solo Alpaca/indicative SPXW europeo PM con referencia implícita: rechaza feeds mezclados y datos no disponibles al corte. Una futura comparación pagada requiere otro protocolo y análisis de fuentes explícito.

Para probar la propuesta de captura manualmente, usando credenciales ya configuradas y un directorio privado nuevo:

```powershell
python scripts/capturar_alpaca.py --config experiments/expiraciones_20261008/captura_propuesta.toml --datos RUTA_PRIVADA_NUEVA --ahora
```

No ejecutar contra el almacén diario existente: las etiquetas de captura no deben reutilizarse para dos configuraciones. El workflow sigue fijado a su versión anterior; este archivo no lo cambia. La primera prueba real debe revisar páginas y tiempo antes de activar una captura programada ampliada. No promete que la ráfaga de 5 segundos sea suficiente.

Los cortes actuales identifican 30 días en 10/10 casos; los otros plazos en 0/10. Es una limitación de selección histórica, no de disponibilidad del mercado. 0DTE aparece únicamente en el resumen de calidad y no se usa para interpolar 7 días. `cercano=true` selecciona el más próximo, no garantiza vencimiento en el mismo día.

Las tablas utilizadas pertenecen al snapshot privado `66c969f20be9fd6bc298512105837a0f788dfbf8`, normalizado bajo el mismo código de medición de la revisión previa. Los hashes completos se guardan en `resultados/resumen.json`. Las cifras de 30 días se contrastan con los diagnósticos auditados. El plan de compra tiene un presupuesto máximo de US$250 al mes y no constituye autorización para contratar.
