"""Adaptadores de proveedores externos al contrato de datos de ``quantileflow.contrato``.

Cada adaptador es una función pura: recibe los payloads que entrega el
proveedor y devuelve las tablas ``COTIZACIONES`` y ``SUBYACENTE``. Ninguno abre
conexiones de red ni maneja credenciales; eso queda fuera del paquete, para que
la librería no pueda, por construcción, autenticarse ni operar una cuenta.
"""
