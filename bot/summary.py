"""Build watchlist-summary message blocks.

A single :func:`build_price_block` is reused by three callers so the formatting
stays identical everywhere: the watchlist auto-update job, the daily summary
job, and the on-demand ``/summary`` command.
"""

from __future__ import annotations

import logging

from bot.util import format_price, kind_emoji, symbol_label
from data.fetcher import fetch_price_or_none
from data.symbols import parse_symbol

log = logging.getLogger(__name__)


def build_price_block(symbols: list[str], header: str) -> str:
    """Return an HTML price-list block for *symbols* under *header*.

    Symbols whose price can't be fetched are shown with an em dash so the user
    sees the gap rather than a silently shortened list.
    """
    if not symbols:
        return f"{header}\n<i>— no symbols —</i>"

    lines = [header]
    fetched = 0
    for sym in symbols:
        parsed = parse_symbol(sym)
        if parsed is None:
            lines.append(f"❌ <code>{sym}</code> (invalid)")
            continue
        price = fetch_price_or_none(parsed)
        if price is None:
            lines.append(f"{kind_emoji(sym)} <b>{symbol_label(sym)}</b>  <i>unavailable</i>")
        else:
            fetched += 1
            lines.append(f"{kind_emoji(sym)} <b>{symbol_label(sym)}</b>  <code>{format_price(price)}</code>")
    lines.append(f"\n<i>{fetched}/{len(symbols)} prices fetched</i>")
    return "\n".join(lines)
