"""Realtime large-liquidation detection from the Binance WebSocket.

Binance exposes the ``!forceOrder@arr`` all-market liquidation stream — every
forced-close that happens on any symbol arrives here, no API key required. Each
event carries the side (BUY = a short got liquidated, SELL = a long got
liquidated), the symbol, the fill price, and the total quantity.

:class:`LiquidationWatcher` connects to the stream, parses each event into a
:class:`Liquidation` dataclass, and hands it to a callback (the bot uses this
to fan the alert out to every user whose threshold it meets).

Resilience mirrors :class:`~data.realtime.BinanceRealtimeManager`: port-443
endpoints first, reconnect with backoff, never crash the loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import websockets

log = logging.getLogger(__name__)

_ENDPOINTS = (
    "wss://stream.binance.com:443/stream?streams=!forceOrder@arr",
    "wss://data-stream.binance.vision/stream?streams=!forceOrder@arr",
    "wss://stream.binance.com:9443/stream?streams=!forceOrder@arr",
)

# Called for every parsed liquidation; awaitable so the bot can await sends.
LiquidationHandler = Callable[["Liquidation"], Awaitable[None]]


@dataclass(frozen=True)
class Liquidation:
    """One forced-close event.

    ``side`` is the order side of the *liquidation order* (what the exchange
    did to close the position): ``SELL`` means a long was liquidated, ``BUY``
    means a short was liquidated. ``notional`` is the total USD value moved.
    """

    symbol: str
    side: str        # "SELL" (long liq) or "BUY" (short liq)
    price: float
    quantity: float
    notional: float
    time: int        # ms epoch from the event

    @property
    def is_long(self) -> bool:
        """True when this was a long position getting liquidated."""
        return self.side.upper() == "SELL"

    @property
    def direction_word(self) -> str:
        return "long 🔴" if self.is_long else "short 🟢"


def parse_liquidation(data: dict) -> Liquidation | None:
    """Build a :class:`Liquidation` from a raw ``o`` payload, or ``None``.

    Exposed for unit testing without a live WebSocket connection.
    """
    if not isinstance(data, dict):
        return None
    o = data.get("o", data) if "o" in data else data
    try:
        symbol = o["s"]
        side = o["S"]
        price = float(o["ap"])   # average fill price
        quantity = float(o["z"])  # total filled quantity
        time = int(o.get("T", 0))
    except (KeyError, TypeError, ValueError) as exc:
        log.debug("Skipping malformed liquidation event: %s", exc)
        return None
    return Liquidation(
        symbol=symbol,
        side=side,
        price=price,
        quantity=quantity,
        notional=price * quantity,
        time=time,
    )


class LiquidationWatcher:
    """Connects to Binance's all-market liquidation stream."""

    def __init__(self, handler: LiquidationHandler, ping_interval: int = 20) -> None:
        self._handler = handler
        self._ping_interval = ping_interval
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    def start(self) -> None:
        """Start the background connection loop (idempotent)."""
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name="liq_watcher")

    async def stop(self) -> None:
        """Cancel the background loop and wait for it to settle."""
        self._stopping = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        """Outer reconnect loop."""
        while not self._stopping:
            try:
                await self._connect_and_read()
                if not self._stopping:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                if self._stopping:
                    return
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("Liquidation WS loop error: %s; reconnecting in 3s", exc)
                await asyncio.sleep(3.0)

    async def _connect_and_read(self) -> None:
        """Open the first reachable endpoint and pump events to the handler."""
        for uri in _ENDPOINTS:
            host = uri.split("//", 1)[1].split("/", 1)[0]
            try:
                log.info("Connecting liquidation WS (%s)", host)
                async with websockets.connect(
                    uri, ping_interval=self._ping_interval, open_timeout=15
                ) as ws:
                    async for raw in ws:
                        liq = self._parse_frame(raw)
                        if liq is not None:
                            try:
                                await self._handler(liq)
                            except Exception as exc:  # noqa: BLE001
                                log.warning("Liquidation handler error: %s", exc)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.info("Liquidation WS %s failed (%s); trying next", host, exc)
                continue
        log.warning("All liquidation WS endpoints failed; pausing 5s before retry")
        await asyncio.sleep(5.0)

    @staticmethod
    def _parse_frame(raw: str | bytes) -> Liquidation | None:
        """Parse one combined-stream frame into a Liquidation, if valid."""
        import json

        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        # Combined-stream responses wrap the payload under "data".
        payload = msg.get("data", msg)
        return parse_liquidation(payload)
