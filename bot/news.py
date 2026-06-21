"""Seen-news tracking + message formatting for the news auto-drop.

The :class:`NewsStore` remembers which article links have already been pushed
so the periodic job only ever broadcasts *new* headlines, even across restarts.

:func:`build_news_digest` renders the digest as a "Mac-style" notification
card: an accent line, a thick divider, a blockquote-wrapped body, and one
tight block per article. The title is translated to Bangla and the article
URL is hidden — the digest body shows only a `[more]` tag, and a per-article
inline keyboard button is returned alongside the text so the bot can attach
a real "more" button that opens the article without ever exposing the URL
in the message itself.
"""

from __future__ import annotations

import json
import logging
import os

from bot.pretty import RULE_THIN, card, pill, stack
from data.news import Article
from data.newsfilter import category_emoji
from data.translate import Translator

log = logging.getLogger(__name__)

# Shared translator instance (its cache survives across ticks).
_translator = Translator()


class NewsStore:
    """Persists the set of already-pushed article links."""

    def __init__(self, persist_path: str | None = None, max_seen: int = 1000) -> None:
        self._seen: set[str] = set()
        self._path = persist_path
        self._max_seen = max_seen
        if persist_path and os.path.exists(persist_path):
            self._load()

    def is_seen(self, article: Article) -> bool:
        return article.link in self._seen

    def filter_unseen(self, articles: list[Article]) -> list[Article]:
        """Return only the articles whose link we have not pushed yet."""
        return [a for a in articles if a.link not in self._seen]

    def mark_seen(self, articles: list[Article]) -> None:
        """Record *articles* as pushed, trimming the set when it grows too big."""
        for a in articles:
            self._seen.add(a.link)
        if len(self._seen) > self._max_seen:
            # Drop the oldest entries arbitrarily — a bounded set is enough for
            # dedup; we don't need strict ordering here.
            self._seen = set(list(self._seen)[-self._max_seen :])
        self._save()

    def _save(self) -> None:
        if not self._path:
            return
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sorted(self._seen), fh)
        os.replace(tmp, self._path)

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                self._seen = set(json.load(fh))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load seen-news from %s: %s", self._path, exc)

    def __len__(self) -> int:
        return len(self._seen)


def _format_article(a: Article, bn_title: str) -> str:
    """Render a single article as a tight Bangla blockquote block.

    The article URL is intentionally hidden — the body shows only a tiny
    ``[more]`` tag, and the caller is expected to attach a real inline button
    built from :func:`build_inline_keyboard` so the reader can still open it.
    """
    emoji = category_emoji(a.title)
    return stack(
        f"{emoji}  <b>{bn_title}</b>",
        f"{pill(a.source)}  ·  <i>[more]</i>",
        sep="\n",
    )


def build_inline_keyboard(articles: list[Article], limit: int = 5) -> "InlineKeyboardMarkup | None":
    """Build a vertical stack of "[more]" inline buttons, one per article.

    Returns ``None`` if the list is empty so the caller can skip attaching
    ``reply_markup`` when there's nothing to link to. Each button is a
    ``url_button`` that opens the original article in Telegram's in-app
    browser, so the user never has to copy/paste a raw URL.
    """
    if not articles:
        return None
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    except ImportError:
        return None
    buttons = [
        [InlineKeyboardButton(text=f"📖 {a.source} — more", url=a.link)]
        for a in articles[:limit]
    ]
    return InlineKeyboardMarkup(buttons)


def build_news_digest(
    articles: list[Article],
    header: str = "📰  গুরুত্বপূর্ণ ক্রিপ্টো খবর",
    limit: int = 5,
    *,
    accent: str = "🟦",
    subtitle: str = "অটো-ফিল্টারড · কীওয়ার্ড + ওয়াচলিস্ট সিগন্যাল",
) -> tuple[str, "InlineKeyboardMarkup | None"]:
    """Render up to *limit* articles as a Bangla Mac-style Telegram card.

    Returns ``(text, reply_markup)`` so the caller can attach the per-article
    inline keyboard with one line. Each article's URL is hidden in the text
    and exposed only as a labeled inline button — the user clicks "more" to
    open the article in Telegram's browser without seeing the raw URL.
    """
    if not articles:
        body = "<i>এই মুহূর্তে কোনো নতুন শিরোনাম নেই।</i>"
        return card(header, body, accent=accent), None

    items = articles[:limit]
    blocks = [_format_article(a, _translator.translate(a.title)) for a in items]
    if len(articles) > limit:
        blocks.append(f"<i>…এবং আরও {len(articles) - limit}টি</i>")
    if subtitle:
        blocks.insert(0, f"<i>{subtitle}</i>")

    body = "\n\n" + RULE_THIN + "\n\n" + "\n\n".join(blocks)
    return card(header, body, accent=accent), build_inline_keyboard(items, limit)



