"""trade-alert-bot — entry point.

Wires together the configuration, alert store, Telegram handlers, and the
background polling job, then starts long-polling.

Usage:
    python main.py
"""

from __future__ import annotations

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
    from bot.jobs import schedule_polling
    from config import settings
except RuntimeError as exc:
    print(f"Configuration error: {exc}", file=sys.stderr)
    sys.exit(2)

# Persistence file lives next to this script; the gitignore keeps it local.
_ALERTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store", "alerts.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("trade-alert-bot")


def main() -> int:
    """Build the application, register handlers + jobs, and start polling."""
    log.info("Starting trade-alert-bot…")
    log.info("Auth enabled: %s | Poll interval: %ds", settings.auth_enabled, settings.poll_interval_seconds)

    # Shared mutable store, optionally persisted to disk.
    store = AlertStore(persist_path=_ALERTS_FILE)

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .build()
    )

    # Telegram command handlers (close over `store`).
    for handler in build_handlers(store):
        application.add_handler(handler)

    # Recurring background job that checks every alert against live prices.
    schedule_polling(application, store, settings.poll_interval_seconds)

    log.info("Bot is up — press Ctrl+C to stop.")
    application.run_polling(allowed_updates=["message"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)
