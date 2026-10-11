# Contraste de skew y bandas, 10 de octubre de 2026

IV plana y SSVI sobre el mismo training de ±3% de log-moneyness y el mismo holdout
por strike (call y put juntos), con pérdida por banda y tres inicializaciones.
El protocolo se guarda en `protocolo.toml`. Las doce fotos proceden de seis sesiones
ya inspeccionadas: experimento exploratorio, sin test temporal independiente.

Informe: [SKEW_BANDAS_2026-10-10.md](../../docs/SKEW_BANDAS_2026-10-10.md).

Desde la raíz del repositorio, con Python 3.12 y dependencias instaladas:

```powershell
python -X utf8 experiments/skew_bandas_20261010/evaluar.py --tablas ../tablas_comparador_20261010_privadas --crudo ../datos_20261009_privados --salida-privada ../skew_bandas_20261010_privado
python -X utf8 experiments/skew_bandas_20261010/control_forward.py --privado ../skew_bandas_20261010_privado
python -X utf8 experiments/skew_bandas_20261010/verificar.py --privado ../skew_bandas_20261010_privado --tablas ../tablas_comparador_20261010_privadas
python -X utf8 -m pytest tests experiments/expiraciones_20261008/test_expiraciones.py experiments/intradia_20261007/test_exploracion.py experiments/cadena_comparador_20261010/test_evaluar_cadena.py experiments/skew_bandas_20261010/test_control_forward.py -q
```

La corrida requiere el snapshot privado y las tablas normalizadas cuyas huellas están
en `resultados/resumen.json`. Las pruebas usan datos sintéticos y no requieren red ni
credenciales. El resultado publicado fija versiones del entorno y huellas de fuentes.

En `resultados/` solo se publican resúmenes y gráficos agregados. Los Parquet, parámetros
de mercado y JSON con rankings por contrato deben permanecer **fuera del repositorio**.
El control posterior de forward mide incompatibilidad de bandas, con descuento fijo;
no modifica calibraciones ni selecciona los rankings. El verificador comprueba integridad
y recalcula precios con una fórmula independiente antes de publicar.
