"""Configuración común de las pruebas: gráficas sin interfaz, para no depender de Tk (p. ej., en Windows)."""
import matplotlib

matplotlib.use("Agg")
