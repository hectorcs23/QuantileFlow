# Comparación histórica por presupuesto

Caso descriptivo del 6 de noviembre: US$300, +3% en siete días desde el
22 de octubre de 2026 a las 09:45 ET. La foto se eligió por ser el primer corte
de la última sesión de las tablas locales verificadas, no por su resultado.
Los filtros y supuestos son los de `quantileflow.observadas.REGLAS`.

```text
python experiments/observadas_20261106/evaluar.py --tablas RUTA_TABLAS --crudo RUTA_REPO_DATOS --privado RUTA_SALIDA_PRIVADA
```

La salida privada debe estar fuera del repositorio y separada de las entradas.
Contiene `analisis.json` y `mapa_posicion.png`. `resultados/` sólo contiene
`resumen.json` y `diagnostico.png`, ambos agregados. La huella del análisis
privado queda en el resumen. El experimento verifica la cadena de huellas y
recalcula todas las celdas con una fórmula independiente.

Regresiones:

```text
python -m pytest tests/test_observadas.py tests/test_duelo.py tests/test_simulador.py tests/test_escenarios.py tests/test_posiciones.py tests/test_comparador_pdf.py -q
```

La comprobación en Edge está en `apps/simulador/verificar_observadas.cjs`;
requiere el servidor configurado con esta captura. Sus capturas de pantalla y
descargas son privadas. El simulador sintético tiene su propia prueba de UI.

Alcance y resultados: [informe](../../docs/CONTRATOS_OBSERVADOS_2026-11-06.md).
