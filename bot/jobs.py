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

from bot.alerts import Alert, AlertKind, AlertStore, check
from bot.news import build_news_digest
from bot.summary import build_price_block
from bot.util import format_percent, format_price, pct_emoji, symbol_label
from data.fetcher import fetch_price_or_none
from data.news import fetch_all
from data.newsfilter import DEFAULT_KEYWORD_THRESHOLD, filter_important
from data.symbols import parse_symbol

log = logging.getLogger(__name__)


def _alert_message(alert: Alert, price: float) -> str:
    """The Telegram message body sent when an alert fires."""
    label = symbol_label(alert.symbol)
    price_str = format_price(price)
    arrow = "⬆️ crossed above" if alert.direction.value == "above" else "⬇️ crossed below"

    if alert.kind is AlertKind.PERCENT:
        change = alert.change_percent(price)
        base_str = format_price(alert.baseline)
        return (
            f"🔔 <b>Alert #{alert.id} triggered</b>\n\n"
            f"<b>{label}</b> has moved {pct_emoji(change)} <b>{format_percent(change)}</b> "
            f"from your baseline.\n\n"
            f"Baseline: <code>{base_str}</code>\n"
            f"Current price: <code>{price_str}</code>\n"
            f"Threshold: <b>{alert.pct:.2f}%</b> {alert.direction.value}\n\n"
            f"Alert removed. Create a new one with /alert."
        )

    target_str = format_price(alert.target_price)
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


def build_watchlist_update_callback(watchlist):
    """Return a job callback that broadcasts live watchlist prices to each user.

    Runs on a separate (typically slower) cadence than alert polling, since a
    watchlist snapshot is bulkier than a single crossing event.
    """

    async def update_watchlists(context: ContextTypes.DEFAULT_TYPE) -> None:
        for user_id in watchlist.all_user_ids():
            symbols = watchlist.get(user_id)
            if not symbols:
                continue
            text = build_price_block(symbols, "🔄 <b>Watchlist update</b>")
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not send watchlist update to %s: %s", user_id, exc)

    return update_watchlists


def schedule_watchlist_updates(application, watchlist, interval_seconds: int) -> None:
    """Register the periodic watchlist-broadcast job."""
    callback = build_watchlist_update_callback(watchlist)
    application.job_queue.run_repeating(
        callback,
        interval=interval_seconds,
        first=interval_seconds,
        name="watchlist_updates",
    )
    log.info("Scheduled watchlist updates every %ds", interval_seconds)


def build_daily_summary_callback(watchlist):
    """Return a job callback that sends a daily watchlist summary to each user.

    Reuses :func:`build_price_block` so the daily digest looks just like the
    periodic update, only with a different header.
    """

    async def daily_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
        for user_id in watchlist.all_user_ids():
            symbols = watchlist.get(user_id)
            if not symbols:
                continue
            text = build_price_block(symbols, "🗓️ <b>Daily market summary</b>")
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not send daily summary to %s: %s", user_id, exc)

    return daily_summary


def schedule_daily_summary(application, watchlist, time_str: str) -> None:
    """Register a once-daily summary job at *time_str* (``"HH:MM``", 24h, local)."""
    import datetime as _dt

    parts = time_str.split(":")
    if len(parts) != 2:
        log.warning("Invalid DAILY_SUMMARY_TIME %r; skipping daily summary job", time_str)
        return
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        log.warning("Invalid DAILY_SUMMARY_TIME %r; skipping daily summary job", time_str)
        return

    callback = build_daily_summary_callback(watchlist)
    application.job_queue.run_daily(
        callback,
        time=_dt.time(hour=hour, minute=minute),
        name="daily_summary",
    )
    log.info("Scheduled daily summary at %s local time", time_str)


def build_news_drop_callback(news_store, subscribers, watchlist=None, sources=None,
                             per_drop: int = 5, keyword_threshold: int = DEFAULT_KEYWORD_THRESHOLD):
    """Return a job callback that pushes *new, important* headlines to subscribers.

    For each subscriber the job:
    1. fetches every source,
    2. drops articles already seen,
    3. keeps only the articles :func:`is_important` flags for that user's
       watchlist (high-signal keywords OR a watched symbol's base currency),
    4. sends a per-user digest, and
    5. marks everything seen so no headline is re-sent next tick.

    A user with no matching headlines gets nothing that tick (no spam). If there
    are no subscribers or no new articles at all, the tick is a no-op.
    """

    async def drop_news(context: ContextTypes.DEFAULT_TYPE) -> None:
        subs = subscribers.news_subscribers()
        if not subs:
            return
        articles = fetch_all(sources) if sources else fetch_all()
        new_articles = news_store.filter_unseen(articles)
        if not new_articles:
            return

        sent_total = 0
        for user_id in subs:
            wl = watchlist.get(user_id) if watchlist is not None else []
            important = filter_important(new_articles, wl, keyword_threshold=keyword_threshold)
            if not important:
                continue
            digest = build_news_digest(
                important, "📰 <b>Important crypto news</b>", limit=per_drop
            )
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=digest,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                sent_total += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not send news to %s: %s", user_id, exc)

        # Mark all new articles seen regardless of who received them, so a
        # stale headline never re-surfaces on a later tick.
        news_store.mark_seen(new_articles)
        log.info(
            "News drop: %d new article(s); important digests sent to %d/%d subscriber(s)",
            len(new_articles), sent_total, len(subs),
        )

    return drop_news


def schedule_news_drops(application, news_store, subscribers, interval_seconds: int, **kwargs) -> None:
    """Register the periodic news auto-drop job (importance-filtered)."""
    callback = build_news_drop_callback(news_store, subscribers, **kwargs)
    application.job_queue.run_repeating(
        callback,
        interval=interval_seconds,
        first=interval_seconds,
        name="news_drops",
    )
    log.info("Scheduled news auto-drop every %ds (importance-filtered)", interval_seconds)


# Re-exported so callers can type-hint without importing telegram.ext directly.
__all__ = [
    "build_poll_callback",
    "schedule_polling",
    "build_watchlist_update_callback",
    "schedule_watchlist_updates",
    "build_daily_summary_callback",
    "schedule_daily_summary",
    "build_news_drop_callback",
    "schedule_news_drops",
]
