"""Small shared helpers for bot message formatting.

Kept separate from :mod:`bot.jobs` and :mod:`bot.handlers` so both can reuse
the same price/label formatting without duplicating logic.
"""

from __future__ import annotations

from data.symbols import parse_symbol


def format_price(price: float) -> str:
    """Format a price with sensible precision (more decimals for small values)."""
    if price >= 1000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:,.4f}"
    # Sub-1 prices (e.g. SOL/BTC ~0.0011) need many decimals; trim trailing zeros.
    return f"{price:,.8f}".rstrip("0").rstrip(".")


def symbol_label(symbol: str) -> str:
    """Return a friendly label like ``BTC/USDT`` for a normalized symbol."""
    sym = parse_symbol(symbol)
    return sym.display if sym else symbol


def kind_emoji(symbol: str) -> str:
    """A small market-type marker: 🪙 crypto, 💱 forex."""
    sym = parse_symbol(symbol)
    if sym is None:
        return "📈"
    return "🪙" if sym.kind.value == "crypto" else "💱"
