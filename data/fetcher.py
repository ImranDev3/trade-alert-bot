"""Live price fetchers for crypto and forex markets.

Both data sources are **free and key-less**:

* **Crypto** — Binance public REST API
  ``GET https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT``
* **Forex** — Yahoo Finance (near-realtime intraday quotes)
  ``GET https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X``
  Frankfurter (ECB daily reference rates) is kept as a fallback so the bot
  still works if Yahoo rate-limits or is unreachable from a network.

The public entry point is :func:`fetch_price`, which dispatches on the
symbol's :class:`~data.symbols.SymbolKind`.
"""

from __future__ import annotations

import logging

import requests

from data.pricecache import PriceCache
from data.symbols import Symbol, SymbolKind

log = logging.getLogger(__name__)

# Network timeouts (connect, read) in seconds — keep the bot responsive.
_TIMEOUT = (5, 10)

_BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
_FRANKFURTER_URL = "https://api.frankfurter.app/latest"

# A browser-like User-Agent avoids Yahoo's blank-response filter for scripts.
_YAHOO_HEADERS = {"User-Agent": "trade-alert-bot/1.0 (github.com/ImranDev3)"}

# Optional shared cache. When set (by main.py via set_cache()), the realtime
# Binance WebSocket fills it and fetch_price reads it first — giving live
# crypto prices without a REST round-trip.
_cache: PriceCache | None = None


class PriceError(Exception):
    """Raised when a price cannot be fetched (network, bad symbol, etc.)."""


def set_cache(cache: PriceCache | None) -> None:
    """Inject the shared :class:`PriceCache` used by realtime reads."""
    global _cache
    _cache = cache


def _fetch_crypto_rest(symbol: Symbol) -> float:
    """Return the latest crypto price from Binance REST for *symbol*."""
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


def _fetch_crypto(symbol: Symbol) -> float:
    """Return the latest crypto price: cache first, REST as fallback."""
    if _cache is not None:
        cached = _cache.get(symbol.normalized)
        if cached is not None:
            return cached
    return _fetch_crypto_rest(symbol)


def _yahoo_symbol(symbol: Symbol) -> str:
    """Map a forex pair to Yahoo's symbol form (``EURUSD`` -> ``EURUSD=X``)."""
    return f"{symbol.normalized}=X"


def _fetch_forex_yahoo(symbol: Symbol) -> float:
    """Return the latest FX rate from Yahoo Finance for *symbol*."""
    url = f"{_YAHOO_CHART_URL}/{_yahoo_symbol(symbol)}"
    try:
        resp = requests.get(url, headers=_YAHOO_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise PriceError(f"Yahoo request failed for {symbol.display}: {exc}") from exc

    result = resp.json().get("chart", {}).get("result")
    if not result:
        raise PriceError(f"Yahoo returned no data for {symbol.display}")
    price = result[0].get("meta", {}).get("regularMarketPrice")
    if price is None:
        raise PriceError(f"Yahoo returned no price for {symbol.display}")
    return float(price)


def _fetch_forex_frankfurter(symbol: Symbol) -> float:
    """Return the daily FX reference rate from Frankfurter (fallback only)."""
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


def _fetch_forex(symbol: Symbol) -> float:
    """Fetch the latest FX rate: Yahoo first, Frankfurter as fallback."""
    try:
        return _fetch_forex_yahoo(symbol)
    except PriceError as exc:
        log.info("Yahoo forex failed (%s); falling back to Frankfurter", exc)
        return _fetch_forex_frankfurter(symbol)


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
