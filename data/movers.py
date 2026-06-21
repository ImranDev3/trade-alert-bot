"""Top market movers from the Binance 24h ticker.

The :func:`fetch_top_movers` helper pulls the full 24h ticker from Binance's
free REST API and returns the top N gainers and top N losers by percent change.
The endpoint requires no API key.

Only USDT-quoted pairs are considered, so the resulting list is comparable
in scale (no BTC-quoted "altcoin +5%" mixed with USDT-quoted "BTC +0.5%").
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

_TIMEOUT = (5, 15)
_URL = "https://api.binance.com/api/v3/ticker/24hr"


class Mover:
    """A single market mover."""

    __slots__ = ("symbol", "price", "percent", "volume")

    def __init__(self, symbol: str, price: float, percent: float, volume: float) -> None:
        self.symbol = symbol
        self.price = price
        self.percent = percent
        self.volume = volume  # quote volume in USDT

    def __repr__(self) -> str:
        return f"Mover({self.symbol} {self.percent:+.2f}%)"


class MoverError(Exception):
    """Raised when the movers endpoint can't be fetched."""


def fetch_top_movers(limit: int = 10, quote: str = "USDT", min_volume: float = 1_000_000.0) -> tuple[list[Mover], list[Mover]]:
    """Return ``(top_gainers, top_losers)`` by 24h percent change.

    Parameters
    ----------
    limit:
        How many entries to return per side.
    quote:
        Quote currency to filter on (default ``USDT``). Pairs that don't end
        in this suffix are dropped, so the list compares apples to apples.
    min_volume:
        Skip pairs with 24h quote volume below this (in USDT) — keeps ultra-low
        float coins that pump +2000% on no volume from dominating the list.
    """
    try:
        resp = requests.get(_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise MoverError(f"Binance 24h ticker request failed: {exc}") from exc

    rows = resp.json()
    movers: list[Mover] = []
    for row in rows:
        symbol = row.get("symbol", "")
        if not symbol.endswith(quote) or symbol == f"BUSD{quote}":
            continue
        try:
            price = float(row.get("lastPrice") or 0)
            pct = float(row.get("priceChangePercent") or 0)
            vol = float(row.get("quoteVolume") or 0)
        except (TypeError, ValueError):
            continue
        if vol < min_volume or price <= 0:
            continue
        # Symbol like BTCUSDT -> base "BTC" for the human label.
        movers.append(Mover(symbol=symbol[: -len(quote)], price=price, percent=pct, volume=vol))

    movers.sort(key=lambda m: m.percent, reverse=True)
    gainers = movers[:limit]
    losers = movers[-limit:][::-1]  # most negative first
    return gainers, losers
