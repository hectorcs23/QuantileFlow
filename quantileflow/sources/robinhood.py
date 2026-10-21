"""Robinhood option chains -> the normalized data contract.

What this module does
---------------------
Maps the three payloads Robinhood returns for options (chains, instruments and
quotes) plus an underlying quote onto the ``COTIZACIONES`` and ``SUBYACENTE``
schemas of :mod:`quantileflow.contrato`. It is a pure mapping: no sockets, no
credentials, no tokens, no order functions. Fetching is somebody else's job
(see ``scripts/robinhood_ingest.py`` for the file-based entry point), so the
installed library can never authenticate or trade on its own.

Expected input: one *capture* dict, which is what a fetcher writes to disk::

    {"captured_at_utc": "2026-10-21T21:58:00Z",
     "provider": "robinhood", "feed": "robinhood-options-marketdata",
     "chains":      [ ... get_option_chains      -> data.chains  ... ],
     "instruments": [ ... get_option_instruments -> data.instruments ... ],
     "option_quotes": [ ... get_option_quotes    -> data.results[].quote ... ],
     "underlying": {"kind": "index", "symbol": "SPX", "quotes": [ ... ]}}

Fields the mapping relies on
----------------------------
* ``chain.settle_on_open`` -> ``liquidacion``: ``true`` is AM settlement (the
  monthly SPX chain), ``false`` is PM (SPXW). This is the one distinction the
  pilot refuses to mix inside a capture, and Robinhood states it per chain, so
  it is read rather than guessed from the root symbol.
* ``instrument.underlying_type`` -> ``ejercicio``: ``index`` is cash-settled
  European, ``equity`` is American.
* ``chain.trade_value_multiplier`` -> ``multiplicador``.
* ``quote.updated_at`` -> ``sello_snapshot_utc``.

Provenance limits, deliberately not papered over
------------------------------------------------
Robinhood's option quote carries **no exchange/venue timestamp**, so
``sello_evento_utc`` is left null: the age of the quote is unknown, and the
staleness control in :mod:`quantileflow.cadenas` will treat it as such instead
of trusting a fabricated stamp. It also documents no historical availability,
so ``disponible_utc`` is null. ``recibido_utc`` is the capture time, which says
when *we* read the value and nothing about when it was publishable.

There is no intraday snapshot history either: the endpoint answers "now", plus
the previous session's official close. A sample at a fixed cut-off (09:45) can
therefore only be accumulated forward, one session per day; it cannot be
reconstructed backwards from Robinhood.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from .. import contrato
from ..calendario import CALENDARIO, _fecha, es_sesion, instante, instante_liquidacion, plazo_anios

PROVIDER = "robinhood"
FEED = "robinhood-options-marketdata"

#: ``underlying_type`` -> exercise style used by the contract schema.
EXERCISE_BY_UNDERLYING = {"index": "europeo", "equity": "americano"}


class CaptureError(ValueError):
    """The capture is missing something the mapping cannot invent."""


def _instant(value, field: str) -> pd.Timestamp:
    """Parse a provider timestamp into a UTC instant, rejecting naive ones."""
    if value in (None, ""):
        raise CaptureError(f"{field}: missing timestamp")
    stamp = pd.Timestamp(value)
    if stamp.tz is None:
        raise CaptureError(f"{field}: timestamp without timezone: {value!r}")
    return stamp.tz_convert("UTC").as_unit("us")


def _optional_number(value) -> float:
    """Numeric field that the provider may omit; absent means zero size/price."""
    return 0.0 if value in (None, "") else float(value)


def settlement(chain: dict) -> str:
    """``AM`` or ``PM`` from ``settle_on_open``; refuses to guess when absent."""
    if "settle_on_open" not in chain or chain["settle_on_open"] is None:
        raise CaptureError(f"chain {chain.get('symbol')!r}: no settle_on_open, settlement unknown")
    return "AM" if chain["settle_on_open"] else "PM"


def exercise(instrument: dict) -> str:
    """``europeo`` or ``americano`` from ``underlying_type``."""
    kind = instrument.get("underlying_type")
    if kind not in EXERCISE_BY_UNDERLYING:
        raise CaptureError(f"instrument {instrument.get('id')!r}: unknown underlying_type {kind!r}")
    return EXERCISE_BY_UNDERLYING[kind]


def quotes_table(capture: dict) -> pd.DataFrame:
    """``COTIZACIONES`` rows for every instrument in the capture that has a quote.

    One row per contract and snapshot. Instruments without a quote are dropped
    (nothing to price); a quote without its instrument is an error, because the
    strike and expiry would have to be invented.
    """
    chains = {c["id"]: c for c in capture.get("chains", [])}
    instruments = {i["id"]: i for i in capture.get("instruments", [])}
    quotes = capture.get("option_quotes", [])
    if not quotes:
        raise CaptureError("capture has no option_quotes")
    provider = capture.get("provider", PROVIDER)
    feed = capture.get("feed", FEED)
    received = _instant(capture.get("captured_at_utc"), "captured_at_utc")
    underlying = (capture.get("underlying") or {}).get("symbol")
    if not underlying:
        raise CaptureError("capture has no underlying.symbol")

    rows = []
    for quote in quotes:
        ident = quote.get("instrument_id")
        instrument = instruments.get(ident)
        if instrument is None:
            raise CaptureError(f"quote for unknown instrument {ident!r}: no strike or expiry for it")
        chain = chains.get(instrument.get("chain_id"))
        if chain is None:
            raise CaptureError(f"instrument {ident!r}: chain {instrument.get('chain_id')!r} not in capture")
        root = instrument.get("chain_symbol") or chain["symbol"]
        strike = float(instrument["strike_price"])
        kind = "C" if instrument["type"] == "call" else "P"
        expiry = pd.Timestamp(instrument["expiration_date"]).date()
        multiplier = instrument.get("trade_value_multiplier") or chain.get("trade_value_multiplier")
        rows.append({
            "id_contrato": contrato.simbolo_occ(root, expiry, kind, strike),
            "raiz": root,
            "subyacente": underlying,
            "strike": strike,
            "tipo": kind,
            "ejercicio": exercise(instrument),
            "liquidacion": settlement(chain),
            "vencimiento": expiry,
            "multiplicador": float(multiplier),
            "bid": _optional_number(quote.get("bid_price")),
            "ask": _optional_number(quote.get("ask_price")),
            "tam_bid": _optional_number(quote.get("bid_size")),
            "tam_ask": _optional_number(quote.get("ask_size")),
            # Robinhood publishes no venue timestamp for an option quote: the age
            # of the quote is unknown and must stay unknown.
            "sello_evento_utc": pd.NaT,
            "sello_snapshot_utc": _instant(quote.get("updated_at"), f"{ident}.updated_at"),
            "disponible_utc": pd.NaT,
            "recibido_utc": received,
            "proveedor": provider,
            "feed": feed,
        })
    tabla = pd.DataFrame(rows)
    for columna in ("sello_evento_utc", "disponible_utc"):
        tabla[columna] = pd.to_datetime(tabla[columna], utc=True).dt.as_unit("us")
    return tabla.sort_values(["sello_snapshot_utc", "strike", "tipo"], ignore_index=True)


def underlying_table(capture: dict) -> pd.DataFrame:
    """``SUBYACENTE`` rows from the index or equity quotes in the capture.

    An index quote carries ``venue_timestamp`` (when the exchange published the
    level), which is a real event time and is kept as ``sello_evento_utc``.
    """
    block = capture.get("underlying") or {}
    symbol, quotes = block.get("symbol"), block.get("quotes") or []
    if not symbol:
        raise CaptureError("capture has no underlying.symbol")
    if not quotes:
        raise CaptureError(f"capture has no underlying quotes for {symbol}")
    provider = capture.get("provider", PROVIDER)
    feed = capture.get("feed", FEED)
    received = _instant(capture.get("captured_at_utc"), "captured_at_utc")

    rows = []
    for quote in quotes:
        price = quote.get("value", quote.get("last_trade_price"))
        if price in (None, ""):
            raise CaptureError(f"underlying {symbol}: quote with no value")
        event = quote.get("venue_timestamp")
        rows.append({
            "subyacente": symbol,
            "precio": float(price),
            "bid": _optional_number(quote.get("bid_price")) or None,
            "ask": _optional_number(quote.get("ask_price")) or None,
            "sello_evento_utc": _instant(event, "venue_timestamp") if event else pd.NaT,
            "sello_snapshot_utc": _instant(quote.get("updated_at"), "underlying.updated_at"),
            "disponible_utc": pd.NaT,
            "recibido_utc": received,
            "proveedor": provider,
            "feed": feed,
        })
    tabla = pd.DataFrame(rows)
    for columna in ("bid", "ask"):
        tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce").astype(float)
    for columna in ("sello_evento_utc", "disponible_utc"):
        tabla[columna] = pd.to_datetime(tabla[columna], utc=True).dt.as_unit("us")
    return tabla.sort_values("sello_snapshot_utc", ignore_index=True)


def tables(capture: dict, validate: bool = True):
    """Both normalized tables from one capture, validated against their schemas."""
    cotizaciones = quotes_table(capture)
    subyacente = underlying_table(capture)
    if validate:
        for tabla, esquema, nombre in ((cotizaciones, contrato.COTIZACIONES, "cotizaciones"),
                                       (subyacente, contrato.SUBYACENTE, "subyacente")):
            problemas = contrato.validar(tabla, esquema)
            if problemas:
                raise CaptureError(f"{nombre}: " + "; ".join(problemas))
    return cotizaciones, subyacente


def summary(capture: dict) -> dict:
    """What a capture contains, for logs and manifests (no account identifiers)."""
    cotizaciones = quotes_table(capture)
    roots = sorted(cotizaciones["raiz"].unique())
    return {
        "captured_at_utc": str(_instant(capture.get("captured_at_utc"), "captured_at_utc")),
        "provider": capture.get("provider", PROVIDER),
        "feed": capture.get("feed", FEED),
        "roots": roots,
        "settlement": sorted(cotizaciones["liquidacion"].unique()),
        "underlying": (capture.get("underlying") or {}).get("symbol"),
        "expiries": sorted(str(v) for v in cotizaciones["vencimiento"].unique()),
        "contracts": int(len(cotizaciones)),
        "snapshot_span_utc": [str(cotizaciones["sello_snapshot_utc"].min()),
                              str(cotizaciones["sello_snapshot_utc"].max())],
        "event_timestamp": "absent (Robinhood publishes none for option quotes)",
    }


def now_utc() -> str:
    """Timestamp a fetcher can put in ``captured_at_utc``."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Qué vencimientos pedir
# ---------------------------------------------------------------------------
#
# El piloto mide a plazo constante interpolando entre los dos vencimientos que
# encierran el objetivo, así que una captura con un solo vencimiento deja la
# sesión «no disponible». Qué par encierra los 30 días cambia cada sesión, de
# modo que el par se calcula antes de pedir contratos, con la misma regla que
# usará el piloto después (``piloto.elegir_vencimientos``).


def maturity_days(expirations, settlement: str, session, cutoff: str = "09:45",
                  basis: float = 365.0, calendar: str = CALENDARIO) -> dict:
    """Días naturales del corte al instante contractual de liquidación, por vencimiento.

    Descarta los vencimientos que no son sesión del calendario y los que ya
    liquidaron antes del corte.
    """
    corte = instante(session, cutoff, calendar)
    dias = {}
    for expiration in expirations:
        fecha = _fecha(expiration)
        if not es_sesion(fecha, calendar):
            continue
        liquida = instante_liquidacion(fecha, settlement, calendar)
        plazo = plazo_anios(corte, liquida, basis) * basis
        if plazo > 0:
            dias[fecha] = plazo
    return dias


def bracketing_expirations(chain: dict, expirations, session, cfg, cutoff=None):
    """Los vencimientos que el piloto usaría en esa sesión, y el motivo si no hay.

    ``cfg`` es un ``piloto.ConfigPiloto``: de ahí salen el plazo objetivo, el
    mínimo y la separación máxima, para que la captura y la medición no puedan
    discrepar.
    """
    from ..piloto import elegir_vencimientos

    dias = maturity_days(expirations, settlement(chain), session,
                         cutoff or cfg.hora_principal, cfg.base_dias, cfg.calendario)
    if not dias:
        return [], "no expirations left at the cut-off"
    return elegir_vencimientos(dias, cfg)
