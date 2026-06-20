"""Fan large liquidations out to subscribed Telegram users.

The realtime :class:`~data.liquidations.LiquidationWatcher` calls a handler
built here for every forced-close event. The handler formats the event and
sends it only to users whose ``/liqalert`` threshold the event meets.
"""

from __future__ import annotations

import logging

from telegram.constants import ParseMode

from bot.subscribers import SubscriberStore
from bot.util import format_price, symbol_label
from data.liquidations import Liquidation

log = logging.getLogger(__name__)


def build_liquidation_message(liq: Liquidation) -> str:
    """Render one liquidation event as an HTML Telegram message."""
    return (
        f"💥 <b>Large liquidation</b>\n\n"
        f"{liq.direction_word}  <b>{symbol_label(liq.symbol)}</b>\n\n"
        f"Size: <code>${liq.notional:,.0f}</code>\n"
        f"Price: <code>{format_price(liq.price)}</code>\n"
        f"Quantity: <code>{liq.quantity}</code>"
    )


def build_liquidation_handler(bot, subscribers: SubscriberStore):
    """Return an async handler that routes liquidations to matching users.

    *bot* is a ``telegram.Bot`` (or the application's bot, which exposes
    ``send_message``). *subscribers* maps user IDs to their thresholds.
    """

    async def handle_liquidation(liq: Liquidation) -> None:
        subs = subscribers.liq_subscribers()
        if not subs:
            return
        text = build_liquidation_message(liq)
        for user_id, threshold in subs.items():
            if liq.notional >= threshold:
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not send liquidation to %s: %s", user_id, exc)

    return handle_liquidation
