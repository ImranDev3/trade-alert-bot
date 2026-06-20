"""trade-alert-bot — entry point.

Wires together the configuration, shared stores, realtime WebSocket layer,
Telegram handlers, and the background jobs (alert polling, watchlist updates,
daily summary), then starts long-polling.

Usage:
    python main.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from telegram.ext import ApplicationBuilder

# config.load_settings() runs at import time and raises RuntimeError if the
# token is missing — so wrap the imports that pull it in to print a clean
# message instead of an import traceback.
try:
    from bot.alerts import AlertStore
    from bot.handlers import build_handlers
    from bot.jobs import (
        schedule_daily_summary,
        schedule_liquidation_digest,
        schedule_news_drops,
        schedule_polling,
        schedule_watchlist_updates,
    )
    from bot.liquidations import build_liquidation_handler
    from bot.news import NewsStore
    from bot.subscribers import SubscriberStore
    from bot.watchlist import WatchlistStore
    from config import settings
    from data import fetcher
    from data.liquidations import LiquidationBuffer, LiquidationWatcher
    from data.pricecache import PriceCache
    from data.realtime import BinanceRealtimeManager
except RuntimeError as exc:
    print(f"Configuration error: {exc}", file=sys.stderr)
    sys.exit(2)

# Persistence files live next to this script; the gitignore keeps them local.
_STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store")
_ALERTS_FILE = os.path.join(_STORE_DIR, "alerts.json")
_WATCHLIST_FILE = os.path.join(_STORE_DIR, "watchlists.json")
_SUBS_FILE = os.path.join(_STORE_DIR, "subscribers.json")
_NEWS_SEEN_FILE = os.path.join(_STORE_DIR, "seen_news.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("trade-alert-bot")


def main() -> int:
    """Build the application, wire stores + realtime + jobs, start polling."""
    log.info("Starting trade-alert-bot…")
    log.info(
        "Auth: %s | Poll: %ds | WL: %ds | News: %ds | Daily: %r",
        settings.auth_enabled,
        settings.poll_interval_seconds,
        settings.watchlist_update_interval,
        settings.news_drop_interval,
        settings.daily_summary_time or "(off)",
    )

    os.makedirs(_STORE_DIR, exist_ok=True)

    # ---- shared mutable state ----
    store = AlertStore(persist_path=_ALERTS_FILE)
    watchlist = WatchlistStore(persist_path=_WATCHLIST_FILE)
    subscribers = SubscriberStore(persist_path=_SUBS_FILE)
    news_store = NewsStore(persist_path=_NEWS_SEEN_FILE)

    # ---- realtime layer (Binance WS feeding a price cache) ----
    cache = PriceCache(ttl_seconds=settings.cache_ttl_seconds)
    fetcher.set_cache(cache)  # fetch_price reads the cache first, REST otherwise
    realtime = BinanceRealtimeManager(cache)
    # Whenever watchlists change, the WS subscribes to the new crypto set.
    watchlist.set_on_change(realtime.set_symbols)

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .build()
    )

    # ---- Telegram command handlers ----
    for handler in build_handlers(store, watchlist, subscribers):
        application.add_handler(handler)

    # ---- background jobs ----
    schedule_polling(application, store, settings.poll_interval_seconds)
    schedule_watchlist_updates(application, watchlist, settings.watchlist_update_interval)
    schedule_news_drops(
        application, news_store, subscribers,
        settings.news_drop_interval, watchlist=watchlist,
    )
    if settings.daily_summary_time:
        schedule_daily_summary(application, watchlist, settings.daily_summary_time)

    # ---- large-liquidation watcher (separate Binance WS stream) ----
    # Events stream into a buffer; a per-minute digest job drains it and sends
    # each subscriber a "how much was liquidated this minute" summary.
    liq_buffer = LiquidationBuffer(window_seconds=settings.liquidation_digest_interval)
    liq_handler = build_liquidation_handler(liq_buffer)
    liq_watcher = LiquidationWatcher(liq_handler)
    schedule_liquidation_digest(
        application, liq_buffer, subscribers, settings.liquidation_digest_interval
    )

    # ---- start the realtime WebSockets on the bot's event loop ----
    # run_polling manages its own loop, so we hook post_init to start WS once
    # the loop is running, and post_shutdown to stop them cleanly.
    async def _post_init(_app) -> None:
        realtime.start()
        liq_watcher.start()
        log.info("Realtime price + liquidation WebSocket managers started")

    async def _post_shutdown(_app) -> None:
        await realtime.stop()
        await liq_watcher.stop()
        log.info("Realtime price + liquidation WebSocket managers stopped")

    application.post_init = _post_init
    application.post_shutdown = _post_shutdown

    log.info("Bot is up — press Ctrl+C to stop.")
    try:
        application.run_polling(allowed_updates=["message"])
    finally:
        # Best-effort cleanup if the loop is still running (e.g. KeyboardInterrupt).
        try:
            asyncio.get_event_loop().create_task(realtime.stop())
            asyncio.get_event_loop().create_task(liq_watcher.stop())
        except RuntimeError:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)
