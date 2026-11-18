"""Fijaciones comunes y el inventario real de pares de Alpaca.

La lista de símbolos es metadato del mercado (qué se cotiza), no datos de
mercado (a cuánto): va en Git a propósito, para que los tests de topología
corran sin red y sin credenciales. Capturada el 18 de noviembre de 2026 con
``GET /v2/assets?asset_class=crypto&status=active``.
"""
from __future__ import annotations

import pytest

SIMBOLOS_ALPACA_20261118 = (
    "AAVE/USD", "AAVE/USDC", "AAVE/USDT", "ADA/USD", "ARB/USD", "AVAX/USD",
    "AVAX/USDC", "AVAX/USDT", "BAT/USD", "BAT/USDC", "BCH/BTC", "BCH/USD",
    "BCH/USDC", "BCH/USDT", "BONK/USD", "BTC/USD", "BTC/USDC", "BTC/USDT",
    "CRV/USD", "CRV/USDC", "DOGE/USD", "DOGE/USDC", "DOGE/USDT", "DOT/USD",
    "DOT/USDC", "ETH/BTC", "ETH/USD", "ETH/USDC", "ETH/USDT", "FIL/USD",
    "GRT/USD", "GRT/USDC", "HYPE/USD", "LDO/USD", "LINK/BTC", "LINK/USD",
    "LINK/USDC", "LINK/USDT", "LTC/BTC", "LTC/USD", "LTC/USDC", "LTC/USDT",
    "ONDO/USD", "PAXG/USD", "PEPE/USD", "POL/USD", "RENDER/USD", "SHIB/USD",
    "SHIB/USDC", "SHIB/USDT", "SKY/USD", "SOL/USD", "SOL/USDC", "SOL/USDT",
    "SUSHI/USD", "SUSHI/USDC", "SUSHI/USDT", "TRUMP/USD", "UNI/BTC", "UNI/USD",
    "UNI/USDC", "UNI/USDT", "USDC/USD", "USDG/USD", "USDT/USD", "USDT/USDC",
    "WIF/USD", "XRP/USD", "XTZ/USD", "XTZ/USDC", "YFI/USD", "YFI/USDC",
    "YFI/USDT",
)

# Subgrafo chico pero con la misma forma que el real: dos stablecoins como
# centros, BTC con cruces propios y una moneda colgando de un solo par.
SIMBOLOS_JUGUETE = ("BTC/USD", "ETH/USD", "ETH/BTC", "BTC/USDT", "ETH/USDT",
                    "USDT/USD", "XRP/USD")


@pytest.fixture
def simbolos_alpaca():
    return SIMBOLOS_ALPACA_20261118


@pytest.fixture
def simbolos_juguete():
    return SIMBOLOS_JUGUETE
