"""Fan large liquidations out to subscribed Telegram users.

The realtime :class:`~data.liquidations.LiquidationWatcher` calls a handler
built here for every forced-close event. By default that handler appends the
event to a :class:`~data.liquidations.LiquidationBuffer`; a separate one-minute
job (:func:`build_liquidation_digest_callback`) drains the buffer and sends
each subscriber a per-minute digest — "how much was liquidated this minute" —
so the user gets a periodic recheck instead of a per-event firehose.
"""

from __future__ import annotations

import logging

from telegram.constants import ParseMode

from bot.subscribers import SubscriberStore
from bot.util import format_price, symbol_label
from data.liquidations import Liquidation, LiquidationBuffer

log = logging.getLogger(__name__)


def build_liquidation_message(liq: Liquidation) -> str:
    """Render one liquidation event as an HTML Telegram message (kept for /liqtest)."""
    return (
        f"💥 <b>Large liquidation</b>\n\n"
        f"{liq.direction_word}  <b>{symbol_label(liq.symbol)}</b>\n\n"
        f"Size: <code>${liq.notional:,.0f}</code>\n"
        f"Price: <code>{format_price(liq.price)}</code>\n"
        f"Quantity: <code>{liq.quantity}</code>"
    )


def build_liquidation_handler(buffer: LiquidationBuffer):
    """Return an async handler that buffers every liquidation for the digest job."""
    async def handle_liquidation(liq: Liquidation) -> None:
        buffer.add(liq)

    return handle_liquidation


def build_liquidation_digest_message(
    events: list[Liquidation], qualifying: list[Liquidation], threshold: float
) -> str:
    """Render a one-minute liquidation digest.

    *events*        — every liquidation in the minute (for the grand total).
    *qualifying*    — the subset that crossed the user's threshold (shown in detail).
    *threshold*     — the user's USD threshold, shown for context.
    """
    total = sum(e.notional for e in events)
    long_total = sum(e.notional for e in events if e.is_long)
    short_total = total - long_total
    header = (
        f"💥 <b>Liquidations — last minute</b>\n\n"
        f"Total liquidated: <code>${total:,.0f}</code> ({len(events)} events)\n"
        f"🔴 longs: <code>${long_total:,.0f}</code>  ·  🟢 shorts: <code>${short_total:,.0f}</code>"
    )
    if not qualifying:
        return f"{header}\n\n<i>Nothing crossed your ${threshold:,.0f} threshold this minute.</i>"

    lines = [header, f"\n<b>Above your ${threshold:,.0f} threshold:</b>"]
    for e in qualifying[:10]:
        lines.append(f"{e.direction_word}  <b>{symbol_label(e.symbol)}</b>  <code>${e.notional:,.0f}</code>")
    if len(qualifying) > 10:
        lines.append(f"…and {len(qualifying) - 10} more.")
    return "\n".join(lines)


def build_liquidation_digest_callback(buffer: LiquidationBuffer, subscribers: SubscriberStore):
    """Return a job callback that drains the buffer and digests it per minute.

    For every liquidation subscriber: send a digest of the last minute's
    liquidations (grand total + the events that crossed their threshold). The
    buffer is drained once per tick regardless, so events never pile up.
    """

    async def digest_liquidations(context) -> None:
        subs = subscribers.liq_subscribers()
        events = buffer.drain()
        if not subs:
            return
        if not events:
            return  # quiet minute — nothing to report, no spam

        for user_id, threshold in subs.items():
            qualifying = [e for e in events if e.notional >= threshold]
            text = build_liquidation_digest_message(events, qualifying, threshold)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not send liquidation digest to %s: %s", user_id, exc)
        log.info(
            "Liquidation digest: %d event(s), $%.0f total, to %d subscriber(s)",
            len(events), sum(e.notional for e in events), len(subs),
        )

    return digest_liquidations
