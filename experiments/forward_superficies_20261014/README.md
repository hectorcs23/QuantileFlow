# Forward y construcción de superficies: 14 de octubre de 2026

Experimento exploratorio 2x2 sobre las **mismas seis sesiones conocidas** del 2–9 de octubre.
No se añadió una muestra nueva ni se modificó la captura operativa.

- F declarado / estimado exclusivamente con pares call-put de entrenamiento.
- IV plana / SSVI, mismos strikes reservados y pérdida de precios en bandas.
- Universo congelado antes de cambiar F: no se refiltra ni se invierten IV para seleccionar filas de nuevo.
- El ajuste de F minimiza una pérdida convexa de bandas de paridad, con peso 0.02 hacia su midpoint.
  No maximiza el número de bandas satisfechas, no estima el spot físico futuro y no optimiza descuento.
- Los parámetros de mercado y las figuras con cotizaciones individuales se guardan **fuera de Git**.

Resultado: cobertura reservada **6.52%, 21.74%, 7.67%, 45.31%**, en ese orden del 2x2.
Informe y explicación: [FORWARD_SUPERFICIES_2026-10-14.md](../../docs/FORWARD_SUPERFICIES_2026-10-14.md).

## Reproducción

Requiere las tablas privadas, el crudo y las salidas de `skew_bandas_20261010` con las huellas
registradas en su resumen. No requiere nuevas consultas de mercado ni credenciales.

```powershell
python -X utf8 experiments/forward_superficies_20261014/evaluar.py --tablas ../tablas_comparador_20261010_privadas --crudo ../datos_20261009_privados --origen-privado ../skew_bandas_20261010_privado --salida-privada ../forward_superficies_20261014_privado
python -X utf8 experiments/forward_superficies_20261014/verificar.py --privado ../forward_superficies_20261014_privado
python -X utf8 experiments/forward_superficies_20261014/control_pdf.py --privado ../forward_superficies_20261014_privado
python -X utf8 experiments/forward_superficies_20261014/graficas.py --privado ../forward_superficies_20261014_privado
python -X utf8 -m pytest tests experiments/forward_superficies_20261014/test_metodo.py experiments/skew_bandas_20261010/test_control_forward.py -q
python -X utf8 -m pytest experiments/expiraciones_20261008/test_expiraciones.py experiments/intradia_20261007/test_exploracion.py experiments/cadena_comparador_20261010/test_evaluar_cadena.py -q
```

`resultados/` contiene agregados, huellas y gráficos de conteos. **No copiar** allí
`*_evaluacion.parquet`, `*_parametros.json` o `construccion_superficie.*`.
La figura de construcción contiene cotizaciones y parámetros derivados; se conserva solo localmente.

El protocolo es previo a esta ejecución, pero fue motivado por una discrepancia observada
en estos mismos días. Congelarlo ahora no convierte la muestra conocida en una evaluación prospectiva.
