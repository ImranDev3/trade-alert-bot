"""Background polling job.

A single recurring job sweeps every alert, fetches the latest price once per
unique symbol (so N alerts on BTCUSDT cost one API call), and sends a Telegram
notification for any alert whose target has been crossed. Fired alerts are
removed (they are one-shot) so the user is not spammed.

Wired up from :mod:`main` via :func:`build_poll_callback`, which closes over the
shared :class:`~bot.alerts.AlertStore`.
"""

from __future__ import annotations

import logging
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes

from bot.alerts import Alert, AlertStore, check
from data.fetcher import fetch_price_or_none
from data.symbols import parse_symbol

log = logging.getLogger(__name__)


def _format_price(symbol: str, price: float) -> str:
    """Pick a sensible number of decimals for display (forex vs crypto)."""
    if price >= 1000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:,.4f}"
    return f"{price:,.8f}".rstrip("0").rstrip(".")


def _alert_message(alert: Alert, price: float) -> str:
    """The Telegram message body sent when an alert fires."""
    sym = parse_symbol(alert.symbol)
    label = sym.display if sym else alert.symbol
    price_str = _format_price(alert.symbol, price)
    target_str = _format_price(alert.symbol, alert.target_price)
    arrow = "⬆️ crossed above" if alert.direction.value == "above" else "⬇️ crossed below"
    return (
        f"🔔 <b>Alert #{alert.id} triggered</b>\n\n"
        f"<b>{label}</b> has {arrow} your target.\n\n"
        f"Current price: <code>{price_str}</code>\n"
        f"Target: <code>{target_str}</code> ({alert.direction.value})\n\n"
        f"Alert removed. Create a new one with /alert."
    )


def build_poll_callback(store: AlertStore):
    """Return an async job callback that checks all alerts on each tick.

    The store is captured in the closure so the callback matches PTB's
    ``async (context) -> None`` job signature.
    """

    async def poll_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
        # Group alerts by symbol so each symbol is fetched at most once per tick.
        alerts = list(store.all())
        if not alerts:
            return

        prices: dict[str, float] = {}
        for alert in alerts:
            if alert.symbol not in prices:
                sym = parse_symbol(alert.symbol)
                prices[alert.symbol] = fetch_price_or_none(sym) if sym else None

        for alert in alerts:
            price = prices.get(alert.symbol)
            if not check(alert, price):
                continue

            try:
                await context.bot.send_message(
                    chat_id=alert.user_id,
                    text=_alert_message(alert, price),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:  # noqa: BLE001 — never let one send kill the loop
                log.warning("Could not notify user %s for alert #%d: %s", alert.user_id, alert.id, exc)
                continue

            # One-shot: remove after firing.
            store.pop(alert.id)
            log.info("Alert #%d fired and removed (%s @ %s)", alert.id, alert.symbol, price)

    return poll_alerts


def schedule_polling(application: Application, store: AlertStore, interval_seconds: int) -> None:
    """Register the alert-polling job on *application*'s job queue."""
    callback = build_poll_callback(store)
    application.job_queue.run_repeating(
        callback,
        interval=interval_seconds,
        first=interval_seconds,
        name="poll_alerts",
    )
    log.info("Scheduled alert polling every %ds", interval_seconds)


# Re-exported so callers can type-hint without importing telegram.ext directly.
__all__ = ["build_poll_callback", "schedule_polling"]
