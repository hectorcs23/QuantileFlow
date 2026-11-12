# Distribuciones bajo cotizaciones ruidosas — camino B

Experimento del 22 de octubre de 2026, presupuesto de datos USD 0.
[Informe y conclusiones](../../docs/DISTRIBUCIONES_RUIDOSAS_2026-10-22.md).

## Reproducir

Con las dependencias del repositorio y el snapshot privado original:

    python -m pytest experiments/distribuciones_ruido_20261022/test_metodo.py experiments/factibilidad_20261020/test_factibilidad.py -q -p no:cacheprovider
    python experiments/distribuciones_ruido_20261022/evaluar.py --origen ../forward_fijo_20261014_privado --privado ../distribuciones_ruido_20261022_privado
    python experiments/distribuciones_ruido_20261022/verificar.py --origen ../forward_fijo_20261014_privado --privado ../distribuciones_ruido_20261022_privado
    python experiments/distribuciones_ruido_20261022/graficas.py --privado ../distribuciones_ruido_20261022_privado

Los paths privados deben quedar fuera de Git. La evaluación comprueba los SHA-256
del snapshot anterior antes de usarlo. No cambia capturas ni tablas existentes.
Para reproducir solo las pruebas sintéticas no se necesitan datos privados.

## Qué significan las salidas

- resumen.json: medianas y controles por escenario; código e inputs trazables.
- por_rebanada.json: agregados por foto/vencimiento y bandas de CDF.
- reparaciones.json: mínimo error compatible y número de filas por filtro.
- perfil.json: primera foto y vencimiento, con envolvente y dos medidas admisibles.
- verificacion.json: reconstrucción independiente de todas las medidas guardadas.
- controles.json: diferencia alcanzada por dos medidas y sensibilidad de las cotas.
- PNG: comparaciones de filtros y curvas acumuladas.

Las soluciones completas, las anclas, IDs y precios permanecen en la salida
privada. En Git solo se guardan código, agregados, CDF y figuras.

## Cotas exteriores frente a diferencias alcanzables

Las rampas continuas por debajo/encima del indicador de CDF dan cotas exteriores
para todas las distribuciones de soporte declarado. Incluyendo sus quiebres y
los strikes, un LP finito resuelve exactamente esas esperanzas.

Para no confundir una cota conservadora con ambigüedad demostrada, otro LP
optimiza el indicador exacto sobre esos estados y guarda dos medidas. Sus CDF
difieren una cantidad efectivamente alcanzada. Es un intervalo interior de
posibilidades, no prueba de extremos globales de la CDF continua.

Ninguna salida es un intervalo de confianza estadística, una PDF suavizada ni
una probabilidad física de ganar. Cada vencimiento se resuelve por separado.
Los márgenes de ruido y límites de soporte son supuestos explícitos del protocolo.
