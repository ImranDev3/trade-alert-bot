"""Realtime crypto prices via the Binance WebSocket stream.

:class:`BinanceRealtimeManager` keeps a single WebSocket connection to Binance's
combined ``miniTicker`` stream for the set of crypto symbols currently being
tracked, and writes every tick into a :class:`~data.pricecache.PriceCache`.

* **Port 443** endpoints are tried first (firewall-friendly), with 9443 as a
  fallback.
* When the tracked set changes (:meth:`set_symbols`), the live connection is
  cancelled and re-opened with the new subscriptions.
* The manager is async and meant to run on the bot's event loop via
  :meth:`start` (called from ``main.py``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable

import websockets

from data.pricecache import PriceCache

log = logging.getLogger(__name__)

# Combined-stream endpoint templates (tried in order). Port 443 first.
_ENDPOINTS = (
    "wss://stream.binance.com:443/stream?streams={streams}",
    "wss://data-stream.binance.vision:443/stream?streams={streams}",
    "wss://stream.binance.com:9443/stream?streams={streams}",
)


class BinanceRealtimeManager:
    """Manages a Binance miniTicker WebSocket that feeds a price cache."""

    def __init__(self, cache: PriceCache, ping_interval: int = 20) -> None:
        self._cache = cache
        self._ping_interval = ping_interval
        self._desired: set[str] = set()  # lowercase symbols, e.g. "btcusdt"
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    @property
    def tracked(self) -> set[str]:
        """A copy of the currently-tracked (lowercase) symbol set."""
        return set(self._desired)

    def start(self) -> None:
        """Start the background connection loop (idempotent)."""
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name="binance_realtime")

    async def stop(self) -> None:
        """Cancel the background loop and wait for it to settle."""
        self._stopping = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def set_symbols(self, symbols: Iterable[str]) -> None:
        """Update the tracked crypto symbols; reconnects if the set changed."""
        desired = {s.lower() for s in symbols if s}
        if desired == self._desired:
            return
        self._desired = desired
        log.info("Realtime tracking updated: %d symbol(s): %s", len(desired), sorted(desired))
        # Cancel the current connection so _run reconnects with new streams.
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        """Outer loop: connect, read, reconnect on change or error."""
        while not self._stopping:
            if not self._desired:
                try:
                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    if self._stopping:
                        return
                continue
            try:
                await self._connect_and_read()
                # Clean close (server dropped) — pause before reconnecting.
                if not self._stopping:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                if self._stopping:
                    return
                # set_symbols changed the set (or a transient cancel) -> reconnect
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("Binance WS loop error: %s; reconnecting in 2s", exc)
                await asyncio.sleep(2.0)

    async def _connect_and_read(self) -> None:
        """Open a WS to the first reachable endpoint and pump ticks into the cache."""
        streams = "/".join(f"{s}@miniTicker" for s in self._desired)
        for template in _ENDPOINTS:
            uri = template.format(streams=streams)
            host = uri.split("//", 1)[1].split("/", 1)[0]
            try:
                log.info("Connecting Binance WS (%s) for %d stream(s)", host, len(self._desired))
                async with websockets.connect(
                    uri, ping_interval=self._ping_interval, open_timeout=15
                ) as ws:
                    async for raw in ws:
                        self._handle_message(raw)
                # Clean close — loop back and reconnect.
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.info("WS endpoint %s failed (%s); trying next", host, exc)
                continue
        log.warning("All Binance WS endpoints failed; pausing 5s before retry")
        await asyncio.sleep(5.0)

    def _handle_message(self, raw: str) -> None:
        """Parse one WS frame and update the cache with the close price."""
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            log.debug("Unparseable WS frame: %s", exc)
            return
        # Combined-stream responses wrap the payload under "data".
        payload = msg.get("data", msg)
        symbol = payload.get("s")
        price = payload.get("c")  # close price
        if symbol and price:
            self._cache.set(symbol, float(price))
