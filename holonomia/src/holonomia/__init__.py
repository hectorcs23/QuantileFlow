"""Geometría de gauge en datos de mercado: holonomía, Hodge y área de Lévy.

Fase 1: holonomía en el grafo de pares cripto. El paquete separa lo que es
matemática verificable (``grafo``, ``hodge``, ``holonomia``) de lo que toca
datos (``datos``, ``limpieza``), para que lo primero se pueda probar sin red.
"""
from . import grafo, hodge, holonomia  # noqa: F401

__all__ = ["grafo", "hodge", "holonomia", "datos", "limpieza"]
__version__ = "0.1.0"
