"""Seen-news tracking + message formatting for the news auto-drop.

The :class:`NewsStore` remembers which article links have already been pushed
so the periodic job only ever broadcasts *new* headlines, even across restarts.

:func:`build_news_digest` renders the digest as a "Mac-style" notification
card: an accent line, a thick divider, a blockquote-wrapped body, and one
tight block per article with a category emoji, bolded title, italic source
pill, and a compact "read" link. The result reads like a native card inside
Telegram rather than plain text.
"""

from __future__ import annotations

import json
import logging
import os

from bot.pretty import RULE_THIN, card, pill, stack
from data.news import Article
from data.newsfilter import category_emoji

log = logging.getLogger(__name__)


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


def _format_article(a: Article) -> str:
    """Render a single article as a tight, scannable blockquote block.

    Layout:
        <emoji>  <b>Title</b>
        <i>Source</i>  ·  <a href="…">read</a>
    """
    emoji = category_emoji(a.title)
    return stack(
        f"{emoji}  <b>{a.title}</b>",
        f"{pill(a.source)}  ·  <a href=\"{a.link}\">read →</a>",
        sep="\n",
    )


def build_news_digest(
    articles: list[Article],
    header: str = "📰  Important crypto news",
    limit: int = 5,
    *,
    accent: str = "🟦",
    subtitle: str = "Auto-filtered · keyword + watchlist signals",
) -> str:
    """Render up to *limit* articles as a Mac-style Telegram notification card.

    The output is a single blockquoted card with a thick divider under the
    title, one block per article inside, and an optional footer with the
    count when there are more than *limit* items. The *header* argument is
    kept for backwards compatibility — it's used as the card title.
    """
    if not articles:
        body = "<i>No new headlines right now.</i>"
        return card(header, body, accent=accent)

    blocks = [_format_article(a) for a in articles[:limit]]
    if len(articles) > limit:
        blocks.append(f"<i>…and {len(articles) - limit} more</i>")
    if subtitle:
        blocks.insert(0, f"<i>{subtitle}</i>")

    body = "\n\n" + RULE_THIN + "\n\n" + "\n\n".join(blocks)
    return card(header, body, accent=accent)


