# Verificación de esta entrega

8 de octubre de 2026, Windows, Python 3.12, entorno del proyecto previamente auditado.

- Suite del proyecto y primeras 13 pruebas del experimento: **223 pasadas**; incluye captura multiplazo de punta a punta con API sintética. Log: `VERIFICACION.txt`.
- Comprobación posterior que añade cobertura explícita de 60/90 días y ventana de 120 días: **14/14 pruebas del experimento pasadas**. No hubo cambios posteriores al código de captura.
- Experimento intradía publicado anteriormente: **9/9 pasadas**.
- Diez medidas a 30 días (valor y ambos extremos de la banda) contrastadas con los diez diagnósticos auditados de las cinco sesiones: **error absoluto máximo 0** en este entorno.
- Para 7/14/60/90 días, **0/10 identificadas** bajo las reglas del protocolo. Son ausencias de la muestra capturada, no un resultado predictivo ni una conclusión sobre el catálogo del proveedor.
- Selección múltiple equivalente al selector anterior cuando hay un solo objetivo; unión deduplicada; objetivos inválidos rechazados; medios días y feriados; prohibición de usar 0DTE, extrapolar o interpolar a través de huecos excesivos; interpolación de varianza total por pata.
- `git diff --check` sin defectos. Agregados públicos revisados sin cotizaciones/strikes/residuos individuales. Los archivos de entrada privados permanecen fuera del repositorio público.

La muestra se reconstruyó desde el snapshot privado `66c969f20be9fd6bc298512105837a0f788dfbf8`. El informe incluye hashes de entradas, configuración y script. El código base de medición es el de `e20bded6f76760f0f8a2d49970f083f1cd29f61a`; las novedades de Claude hasta `8131a76` se revisaron y afectan documentación/aceptación, no los módulos de medición utilizados.

Pendiente: latencia y paginación **reales** de la captura ampliada; cobertura prospectiva de los nuevos vencimientos; acceso OPRA, derechos/costo final y fuente independiente de SPX. Las pruebas sintéticas no demuestran esas propiedades. La configuración experimental no se desplegó en el repositorio privado de datos.
