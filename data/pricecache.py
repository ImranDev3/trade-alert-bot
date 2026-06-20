"""A small in-memory cache of latest market prices.

The realtime Binance WebSocket pushes crypto prices here as they arrive, and
:func:`data.fetcher.fetch_price` reads from the cache first (falling back to
REST when a symbol is stale or missing). Forex is not streamed, so the cache
also stores short-TTL REST results to avoid hammering Yahoo on every poll.

Thread-safety: the bot runs on a single asyncio loop, so a plain dict is fine.
``time.monotonic`` is used so the TTL is immune to wall-clock changes.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)


class PriceCache:
    """Latest-price cache with a per-entry TTL."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._prices: dict[str, tuple[float, float]] = {}  # SYMBOL -> (price, ts)

    def set(self, symbol: str, price: float) -> None:
        """Store *price* for *symbol* with the current monotonic timestamp."""
        self._prices[symbol.upper()] = (float(price), time.monotonic())

    def get(self, symbol: str) -> float | None:
        """Return the cached price if still fresh, else ``None``."""
        entry = self._prices.get(symbol.upper())
        if entry is None:
            return None
        price, ts = entry
        if time.monotonic() - ts > self._ttl:
            return None
        return price

    def age(self, symbol: str) -> float | None:
        """Seconds since *symbol* was last updated (``None`` if unknown)."""
        entry = self._prices.get(symbol.upper())
        if entry is None:
            return None
        return time.monotonic() - entry[1]

    def clear(self) -> None:
        self._prices.clear()

    def __len__(self) -> int:
        return len(self._prices)

    def __contains__(self, symbol: str) -> bool:
        return self.get(symbol) is not None
