"""Live price fetchers for crypto and forex markets.

Both data sources are **free and key-less**:

* **Crypto** — Binance public REST API
  ``GET https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT``
* **Forex** — Frankfurter (European Central Bank reference rates)
  ``GET https://api.frankfurter.app/latest?from=EUR&to=USD``

The public entry point is :func:`fetch_price`, which dispatches on the
symbol's :class:`~data.symbols.SymbolKind`.
"""

from __future__ import annotations

import logging

import requests

from data.symbols import Symbol, SymbolKind

log = logging.getLogger(__name__)

# Network timeouts (connect, read) in seconds — keep the bot responsive.
_TIMEOUT = (5, 10)

_BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"
_FRANKFURTER_URL = "https://api.frankfurter.app/latest"


class PriceError(Exception):
    """Raised when a price cannot be fetched (network, bad symbol, etc.)."""


def _fetch_crypto(symbol: Symbol) -> float:
    """Return the latest crypto price from Binance for *symbol*."""
    params = {"symbol": symbol.normalized}
    try:
        resp = requests.get(_BINANCE_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise PriceError(f"Binance request failed for {symbol.normalized}: {exc}") from exc

    data = resp.json()
    price_str = data.get("price")
    if price_str is None:
        raise PriceError(f"Binance returned no price for {symbol.normalized}")
    return float(price_str)


def _fetch_forex(symbol: Symbol) -> float:
    """Return the latest FX rate from Frankfurter for *symbol* (e.g. EUR/USD)."""
    if not symbol.base or not symbol.quote:
        raise PriceError(f"Cannot fetch forex rate for malformed symbol {symbol.normalized}")

    params = {"from": symbol.base, "to": symbol.quote}
    try:
        resp = requests.get(_FRANKFURTER_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise PriceError(f"Frankfurter request failed for {symbol.display}: {exc}") from exc

    data = resp.json()
    rate = data.get("rates", {}).get(symbol.quote)
    if rate is None:
        raise PriceError(f"Frankfurter returned no rate for {symbol.display}")
    return float(rate)


def fetch_price(symbol: Symbol) -> float:
    """Fetch the latest price for a parsed :class:`Symbol`.

    Raises
    ------
    PriceError
        If the network call fails or the API does not recognize the symbol.
    """
    if symbol.kind is SymbolKind.CRYPTO:
        log.debug("Fetching crypto price: %s", symbol.normalized)
        return _fetch_crypto(symbol)
    if symbol.kind is SymbolKind.FOREX:
        log.debug("Fetching forex price: %s", symbol.display)
        return _fetch_forex(symbol)
    raise PriceError(f"Unknown symbol kind: {symbol.kind}")


def fetch_price_or_none(symbol: Symbol) -> float | None:
    """Like :func:`fetch_price` but returns ``None`` instead of raising.

    Handy inside the polling job, where one bad symbol should not abort the
    whole sweep.
    """
    try:
        return fetch_price(symbol)
    except PriceError as exc:
        log.warning("Price fetch failed: %s", exc)
        return None
