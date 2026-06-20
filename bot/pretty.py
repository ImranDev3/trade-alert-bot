"""Mac-style HTML message helpers for the bot.

Telegram renders a few HTML tags in distinctive ways we use to get a clean,
notification-card feel:

* ``<blockquote>…</blockquote>`` adds a left vertical bar and indented block —
  the closest thing to a Mac "card" border inside a chat message.
* ``<code>…</code>`` and ``<pre>…</pre>`` give a monospaced, slightly inset
  look that reads as a "ticker pill" or footnote.

We avoid fancy custom HTML (which Telegram strips) and rely only on tags the
client actually styles. The result is messages that look like a native
notification card rather than plain text.
"""

from __future__ import annotations

# Three small Unicode rules that read as "thin dividers" without any rendering
# tricks. A full-width box-drawing rule works well as a header/footer line.
RULE_THICK = "━" * 24
RULE_THIN = "─" * 24
DOTS = "·" * 5


def card(title: str, body: str, *, accent: str = "🟦") -> str:
    """Wrap *body* in a blockquote "card" with a *title* line on top.

    Layout:
        <accent> <title>
        ━━━━━━━━━━━━━━━━━━━━━━━━
        <blockquote expandable>
          body
        </blockquote>
    """
    rule = RULE_THICK
    return (
        f"{accent}  <b>{title}</b>\n"
        f"<code>{rule}</code>\n"
        f"<blockquote>{body}</blockquote>"
    )


def pill(text: str) -> str:
    """Render a short string as a small monospaced "ticker pill"."""
    return f"<code>{text}</code>"


def stack(*lines: str, sep: str = "\n") -> str:
    """Join *lines* with *sep*, skipping empty ones — useful inside cards."""
    return sep.join(line for line in lines if line)
