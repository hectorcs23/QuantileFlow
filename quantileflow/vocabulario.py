"""Vocabulario de salida: códigos internos (español) -> etiquetas en inglés.

Los códigos de exclusión, los estados de medición y el estilo de ejercicio se
calculan y se prueban en español dentro del paquete. Todo lo que *sale* —el
informe, los CSV, las gráficas y el manifiesto— se traduce aquí, en un único
sitio, para que la interfaz esté en inglés sin renombrar los internos.

Un código sin traducción se devuelve tal cual: así un motivo nuevo aparece en
la salida en lugar de desaparecer.
"""
from __future__ import annotations

#: códigos de ``cadenas.MOTIVOS`` -> etiqueta exportada.
MOTIVOS = {
    "posterior_al_corte": "after_cutoff",
    "sin_sello": "no_timestamp",
    "no_disponible_al_corte": "not_available_at_cutoff",
    "reemplazada": "superseded",
    "antes_de_apertura": "before_open",
    "ventana_de_apertura": "open_window",
    "desfasada": "stale",
    "sin_bid": "no_bid",
    "cruzada": "crossed",
    "bloqueada": "locked",
    "sin_tamano": "below_min_size",
    "spread_ancho": "wide_spread",
    "fuera_de_cotas": "violates_bounds",
}

#: estados de sesión, de medición y de etiqueta.
ESTADOS = {
    "procesada": "processed",
    "no disponible": "not available",
    "identificada": "identified",
    "no identificada": "not identified",
    "ok": "ok",
    "fin fuera del calendario": "end outside the calendar",
    "sin precio inicial": "no initial price",
    "sin precio final": "no final price",
}

#: estilo de ejercicio tal como lo guarda el contrato de datos.
EJERCICIO = {"europeo": "european", "americano": "american"}

#: columnas cuyos valores son códigos de exclusión separados por ``; ``.
COLUMNAS_MOTIVOS = ("exclusiones",)

#: columnas cuyos valores son estados.
COLUMNAS_ESTADO = ("estado_sesion", "rr25_estado", "asim_log_estado", "estado")


def motivo(codigo: str) -> str:
    """Etiqueta en inglés de un código de exclusión."""
    return MOTIVOS.get(codigo, codigo)


def estado(valor: str) -> str:
    """Etiqueta en inglés de un estado."""
    return ESTADOS.get(valor, valor)


def ejercicio(valor: str) -> str:
    """Etiqueta en inglés del estilo de ejercicio."""
    return EJERCICIO.get(valor, valor)


def motivos(texto: str) -> str:
    """Traduce una lista de códigos: ``"desfasada=3; sin_bid=1"`` o ``"desfasada, sin_bid"``."""
    if not isinstance(texto, str) or not texto:
        return texto
    separador = "; " if "; " in texto or "=" in texto else ", "
    partes = []
    for parte in texto.split(separador):
        if "=" in parte:
            codigo, _, cuenta = parte.partition("=")
            partes.append(f"{motivo(codigo)}={cuenta}")
        else:
            partes.append(motivo(parte))
    return separador.join(partes)


def traducir_columna(serie, columna: str):
    """Serie con sus valores traducidos, si la columna lleva códigos o estados."""
    if columna in COLUMNAS_MOTIVOS:
        return serie.map(motivos)
    if columna in COLUMNAS_ESTADO or columna.startswith("estado_ret_"):
        return serie.map(lambda v: estado(v) if isinstance(v, str) else v)
    if columna == "ejercicio":
        return serie.map(lambda v: ejercicio(v) if isinstance(v, str) else v)
    return serie
