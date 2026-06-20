"""Telegram command handlers.

All bot behaviour lives here as async handler functions. They are built by
:func:`build_handlers`, which closes over the shared
:class:`~bot.alerts.AlertStore` so handlers stay pure with respect to global
state. An :func:`_auth_only` guard enforces the optional allow-list from
:mod:`config` on every command.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from bot.alerts import AlertKind, AlertStore, Direction
from bot.util import format_price, kind_emoji, symbol_label
from bot.watchlist import WatchlistStore
from config import settings
from data.fetcher import PriceError, fetch_price, fetch_price_or_none
from data.symbols import parse_symbol

log = logging.getLogger(__name__)

# Type alias for an async handler callable.
Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]

HELP_TEXT = (
    "🤖 <b>trade-alert-bot</b>\n"
    "Realtime crypto &amp; forex alerts, straight to your chat.\n\n"
    "<b>Commands</b>\n"
    "/price &lt;SYMBOL&gt; — current price  (e.g. /price BTCUSDT)\n"
    "/alert &lt;SYMBOL&gt; &lt;above|below&gt; &lt;PRICE&gt; — price-level alert\n"
    "/alerts — list your active alerts\n"
    "/remove &lt;ID&gt; — remove an alert\n\n"
    "/watch &lt;SYMBOL&gt; — add a symbol to your watchlist\n"
    "/unwatch &lt;SYMBOL&gt; — remove from watchlist\n"
    "/watchlist — show your watchlist with live prices\n"
    "/clearwatch — empty your watchlist\n"
    "/summary — send your watchlist summary now\n"
    "/help — show this message\n\n"
    "<b>Supported markets</b>\n"
    "🪙 Crypto via Binance (e.g. BTCUSDT, ETHUSDT, SOLBTC)\n"
    "💱 Forex via Yahoo (e.g. EURUSD, GBPJPY, USDINR)\n\n"
    "<b>Examples</b>\n"
    "<code>/alert BTCUSDT above 70000</code>\n"
    "<code>/alert EURUSD below 1.10</code>\n"
    "<code>/watch BTCUSDT ETHUSDT EURUSD</code>"
)

START_TEXT = (
    "👋 Welcome to <b>trade-alert-bot</b>!\n\n"
    "I watch crypto and forex markets and ping you when a price crosses a "
    "level you set. Use /help to see everything I can do.\n\n"
    + HELP_TEXT
)


def _reply(update: Update, text: str) -> Awaitable[None]:
    """Reply using HTML parse mode; safe no-op if there is no message."""
    msg = update.effective_message
    if msg is None:
        log.debug("No message to reply to on update %s", update.update_id)
        return _noop()
    return msg.reply_text(text, parse_mode=ParseMode.HTML)


async def _noop() -> None:
    """Awaitable that does nothing (lets _reply stay uniform)."""
    return None


def _auth_only(func: Handler) -> Handler:
    """Decorator that blocks users outside the configured allow-list."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or not settings.is_allowed(user.id):
            await _reply(update, "🚫 You are not authorized to use this bot.")
            return
        await func(update, context)

    return wrapper


def build_handlers(store: AlertStore, watchlist: WatchlistStore) -> list:
    """Return the list of handlers to register, closing over *store* and *watchlist*."""

    @_auth_only
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply(update, START_TEXT)

    @_auth_only
    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply(update, HELP_TEXT)

    @_auth_only
    async def price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if len(args) != 1:
            await _reply(update, "Usage: <code>/price &lt;SYMBOL&gt;</code>\nExample: <code>/price BTCUSDT</code>")
            return
        sym = parse_symbol(args[0])
        if sym is None:
            await _reply(update, f"❌ Invalid symbol: <code>{args[0]}</code>\nTry BTCUSDT or EURUSD.")
            return
        try:
            current = fetch_price(sym)
        except PriceError as exc:
            await _reply(update, f"❌ Couldn't fetch {sym.display}: {exc}")
            return
        await _reply(
            update,
            f"{kind_emoji(sym.normalized)} <b>{sym.display}</b>\n"
            f"Current price: <code>{format_price(current)}</code>",
        )

    @_auth_only
    async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if len(args) != 3:
            await _reply(
                update,
                "Usage:\n"
                "<code>/alert &lt;SYMBOL&gt; &lt;above|below&gt; &lt;PRICE&gt;</code>  (price level)\n"
                "<code>/alert &lt;SYMBOL&gt; &lt;up|down|change&gt; &lt;PERCENT%&gt;</code>  (move alert)\n\n"
                "Examples:\n"
                "<code>/alert BTCUSDT above 70000</code>\n"
                "<code>/alert BTCUSDT up 5%</code>",
            )
            return

        sym = parse_symbol(args[0])
        direction = Direction.parse(args[1])
        kind = AlertKind.parse(args[1])

        # A trailing '%' on the value also implies a percent alert, even when
        # the direction word is a plain up/down/above/below (e.g. "up 5%").
        if kind is None and "%" in args[2]:
            kind = AlertKind.PERCENT

        if sym is None:
            await _reply(update, f"❌ Invalid symbol: <code>{args[0]}</code>")
            return
        if direction is None:
            await _reply(update, f"❌ Direction must be <b>above/below</b> or <b>up/down/change</b>, got <code>{args[1]}</code>")
            return

        value_text = args[2].replace("%", "")
        try:
            value = float(value_text)
        except ValueError:
            await _reply(update, f"❌ Value must be a number, got <code>{args[2]}</code>")
            return

        if kind is AlertKind.PERCENT:
            if value <= 0:
                await _reply(update, f"❌ Percentage must be positive, got <code>{args[2]}</code>")
                return
            # 'change' means either direction; default to ABOVE and watch abs move.
            move_dir = direction if direction in (Direction.ABOVE, Direction.BELOW) else Direction.ABOVE
            baseline = fetch_price_or_none(sym)
            if baseline is None:
                await _reply(update, f"❌ Couldn't fetch current {sym.display} price to set a baseline.")
                return
            created = store.add(
                update.effective_user.id, sym.normalized, move_dir,
                kind=AlertKind.PERCENT, pct=value, baseline=baseline,
            )
            await _reply(
                update,
                f"✅ Alert #{created.id} created\n"
                f"{kind_emoji(sym.normalized)} <b>{sym.display}</b> {move_dir.value} "
                f"<code>{value:.2f}%</code> from <code>{format_price(baseline)}</code>\n\n"
                f"I'll ping you when the price moves that much.",
            )
        else:
            if value <= 0:
                await _reply(update, f"❌ Price must be a positive number, got <code>{args[2]}</code>")
                return
            created = store.add(update.effective_user.id, sym.normalized, direction, value)
            await _reply(
                update,
                f"✅ Alert #{created.id} created\n"
                f"{kind_emoji(sym.normalized)} <b>{sym.display}</b> {direction.value} "
                f"<code>{format_price(value)}</code>\n\n"
                f"I'll ping you when the price crosses this level.",
            )

    @_auth_only
    async def alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_alerts = store.list_for(update.effective_user.id)
        if not user_alerts:
            await _reply(update, "📭 You have no active alerts.\nCreate one with /alert")
            return
        lines = [f"📋 <b>Your alerts ({len(user_alerts)})</b>"]
        for a in user_alerts:
            if a.kind is AlertKind.PERCENT:
                lines.append(
                    f"#{a.id}  {kind_emoji(a.symbol)} <b>{symbol_label(a.symbol)}</b> "
                    f"{a.direction.value} <code>{a.pct:.2f}%</code> from "
                    f"<code>{format_price(a.baseline)}</code>"
                )
            else:
                lines.append(
                    f"#{a.id}  {kind_emoji(a.symbol)} <b>{symbol_label(a.symbol)}</b> "
                    f"{a.direction.value} <code>{format_price(a.target_price)}</code>"
                )
        await _reply(update, "\n".join(lines))

    @_auth_only
    async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if len(args) != 1:
            await _reply(update, "Usage: <code>/remove &lt;ID&gt;</code>\nExample: <code>/remove 3</code>")
            return
        try:
            alert_id = int(args[0])
        except ValueError:
            await _reply(update, f"❌ ID must be a number, got <code>{args[0]}</code>")
            return
        if store.remove(alert_id, update.effective_user.id):
            await _reply(update, f"🗑️ Alert #{alert_id} removed.")
        else:
            await _reply(update, f"❌ No alert #{alert_id} found that belongs to you.")

    @_auth_only
    async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await _reply(update, "Usage: <code>/watch &lt;SYMBOL&gt; [SYMBOL ...]</code>\nExample: <code>/watch BTCUSDT ETHUSDT EURUSD</code>")
            return
        added, skipped = [], []
        for raw in context.args:
            ok, msg = watchlist.add(update.effective_user.id, raw)
            (added if ok else skipped).append(msg)
        lines = ["\n".join(added)] if added else []
        if skipped:
            lines.append("\n".join(skipped))
        await _reply(update, "\n".join(lines))

    @_auth_only
    async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await _reply(update, "Usage: <code>/unwatch &lt;SYMBOL&gt;</code>")
            return
        ok, msg = watchlist.remove(update.effective_user.id, context.args[0])
        await _reply(update, msg)

    @_auth_only
    async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        symbols = watchlist.get(update.effective_user.id)
        if not symbols:
            await _reply(update, "📭 Your watchlist is empty.\nAdd symbols with /watch")
            return
        lines = [f"👀 <b>Your watchlist ({len(symbols)})</b>"]
        for sym in symbols:
            price = fetch_price_or_none(parse_symbol(sym))
            price_str = format_price(price) if price is not None else "—"
            lines.append(f"{kind_emoji(sym)} <b>{symbol_label(sym)}</b>  <code>{price_str}</code>")
        await _reply(update, "\n".join(lines))

    @_auth_only
    async def clearwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        n = watchlist.clear(update.effective_user.id)
        if n:
            await _reply(update, f"🗑️ Cleared your watchlist ({n} symbol removed).")
        else:
            await _reply(update, "📭 Your watchlist was already empty.")

    @_auth_only
    async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply(update, "🤔 I didn't understand that. Send /help to see what I can do.")

    return [
        CommandHandler("start", start),
        CommandHandler("help", help_cmd),
        CommandHandler("price", price),
        CommandHandler("alert", alert),
        CommandHandler("alerts", alerts),
        CommandHandler("remove", remove),
        CommandHandler("watch", watch),
        CommandHandler("unwatch", unwatch),
        CommandHandler("watchlist", watchlist_cmd),
        CommandHandler("clearwatch", clearwatch),
        MessageHandler(filters.COMMAND, unknown),
    ]
