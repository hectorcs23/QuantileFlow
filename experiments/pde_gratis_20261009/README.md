# Primer PDE y prueba de captura gratuita

Presupuesto vigente: **US$0**. Implementación y límites en
[el informe](../../docs/AVANCE_PDE_GRATIS_2026-10-09.md).
Datos privados y credenciales se mantienen fuera de este checkout.

Desde la raíz del repo, con las dependencias de `pyproject.toml`:

```powershell
python experiments/pde_gratis_20261009/benchmark.py
python -m pytest -q tests experiments/expiraciones_20261008/test_expiraciones.py experiments/intradia_20261007/test_exploracion.py
python experiments/pde_gratis_20261009/captura_manual.py
```

El último comando solo presenta el plan; no llama a ninguna API. Para una única
prueba real con claves ya configuradas como variables de entorno:

```powershell
python experiments/pde_gratis_20261009/captura_manual.py --ejecutar --datos C:/ruta/privada/prueba_nueva
```

El destino debe ser nuevo y estar fuera de cualquier checkout Git. El runner
admite solamente `indicative`/`iex`, copia la configuración validada al destino
privado y limita el proceso a 180 segundos. No configura secretos, no programa
jobs y no modifica la captura diaria. Una prueba inmediata es diagnóstica;
no reemplaza la medición de elegibilidad a las 09:45/10:00.

Para comprobar las huellas de una copia del repo privado:

```powershell
python experiments/pde_gratis_20261009/auditar_crudo.py --datos RUTA_PRIVADA --snapshot SHA_DEL_SNAPSHOT --fecha 2026-10-09 --salida RUTA_INFORME_AGREGADO.json
```

`--snapshot` registra la procedencia declarada por quien ejecuta; no comprueba
por sí mismo el commit Git. La auditoría revisa las referencias de capturas,
histórico y eventos y las huellas gzip/contenido JSON. No evalúa licencias,
cotizaciones huérfanas, secretos de Actions ni la exactitud económica de precios.
El informe público contiene agregados y hashes, sin precios de contratos reales.

El PDE produce precios y masas terminales compatibles, además de delta, vega,
sensibilidades a tasa y rendimiento continuo, y un gradiente espacial de sigma.
El benchmark incluye 90 calls/puts sintéticos con 7/14/30/60/90 días, tres
volatilidades y tres strikes. Comprueba contra BS, diferencias centrales,
restos de Taylor, masa, positividad, dualidad y refinamiento de dominio/tiempo/malla.
La volatilidad espacial es un coeficiente estático en log-precio relativo,
**no una superficie IV calibrada**. No usar este benchmark europeo para
recomendar opciones americanas de SPY ni como predicción de dirección.

El refinamiento espacial con tiempo fijo puede mostrar cancelación de errores
frente a BS; el JSON conserva esas cifras, además del refinamiento conjunto.
El solver almacena todas las masas intermedias: memoria O(nodos × pasos).
No se ha medido ventaja de velocidad frente a otros métodos de sensibilidades.
