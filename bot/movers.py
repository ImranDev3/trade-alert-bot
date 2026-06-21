"""Pretty formatting for the /top movers message.

Splits the message into two blockquote "cards" — one for the gainers, one for
the losers — using the same Mac-style helpers as the news digest so the
visual language is consistent across bot features.
"""

from __future__ import annotations

from bot.pretty import RULE_THIN, card, pill, stack
from bot.util import format_percent, format_price
from data.movers import Mover

_GAINER_ACCENT = "🟩"
_LOSER_ACCENT = "🟥"


def _format_row(m: Mover) -> str:
    """One row in the gainers/losers list."""
    arrow = "🟢" if m.percent >= 0 else "🔴"
    return stack(
        f"{arrow}  <b>{m.symbol}</b>  <code>{format_percent(m.percent)}</code>",
        f"   {pill('$' + format_price(m.price))}  ·  <i>vol ${m.volume / 1_000_000:,.1f}M</i>",
        sep="\n",
    )


def build_top_movers_message(gainers: list[Mover], losers: list[Mover]) -> tuple[str, str]:
    """Return ``(gainer_card, loser_card)`` — two HTML strings for the chat."""
    if gainers:
        gainer_lines = [f"<b>Top {len(gainers)} gainers · 24h</b>"] + [
            _format_row(m) for m in gainers
        ]
        gainer_body = "\n\n" + RULE_THIN + "\n\n" + "\n\n".join(gainer_lines)
    else:
        gainer_body = "<i>No gainers right now.</i>"
    gainer_card = card(
        "🚀 Gainers",
        gainer_body,
        accent=_GAINER_ACCENT,
    )

    if losers:
        loser_lines = [f"<b>Top {len(losers)} losers · 24h</b>"] + [
            _format_row(m) for m in losers
        ]
        loser_body = "\n\n" + RULE_THIN + "\n\n" + "\n\n".join(loser_lines)
    else:
        loser_body = "<i>No losers right now.</i>"
    loser_card = card(
        "📉 Losers",
        loser_body,
        accent=_LOSER_ACCENT,
    )

    return gainer_card, loser_card
