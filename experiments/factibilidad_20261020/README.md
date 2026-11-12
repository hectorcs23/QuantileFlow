# ¿Las bandas admiten precios coherentes antes de elegir una superficie?

Diagnóstico mediante programación lineal. No altera cotizaciones, reservas,
capturas ni las salidas históricas. Presupuesto de datos: USD 0.

Informe: [resultado y decisión pendiente](../../docs/FACTIBILIDAD_Y_DECISION_2026-10-20.md).

```text
python -m pytest -p no:cacheprovider experiments/factibilidad_20261020/test_factibilidad.py -q
python experiments/factibilidad_20261020/evaluar.py --origen ../forward_fijo_20261014_privado --privado ../factibilidad_20261020_privado
python experiments/factibilidad_20261020/verificar.py --origen ../forward_fijo_20261014_privado --privado ../factibilidad_20261020_privado
python experiments/factibilidad_20261020/graficas.py
```

Se requieren los archivos privados originales con sus hashes. La carpeta
`resultados/` contiene agregados y diagnósticos por foto/vencimiento, nunca
precios de contratos ni las curvas reparadas. Esas soluciones permanecen fuera
del repositorio. El LP de holdout es un diagnóstico posterior de compatibilidad,
no un modelo ajustado con training y evaluado fuera de muestra.
