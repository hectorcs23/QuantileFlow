"""btclab: laboratorio de investigacion para mercados de prediccion de BTC.

Version de investigacion. No emite ordenes reales y no produce recomendaciones
de inversion. Todo importe expuesto declara si es ficticio, simulado o real.
"""

__version__ = "0.1.0"

ESTADOS = (
    "DATA_ONLY",
    "RESEARCH",
    "INCONCLUSIVE",
    "FAIL",
    "PAPER_VALIDATED",
)

#: Estado vigente del proyecto. Solo se cambia con evidencia segun docs/protocolo.md.
ESTADO_ACTUAL = "DATA_ONLY"
