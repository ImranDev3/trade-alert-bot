"""Seen-news tracking + message formatting for the news auto-drop.

The :class:`NewsStore` remembers which article links have already been pushed
so the periodic job only ever broadcasts *new* headlines, even across restarts.
"""

from __future__ import annotations

import json
import logging
import os

from data.news import Article

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


def build_news_digest(articles: list[Article], header: str, limit: int = 5) -> str:
    """Render up to *limit* articles as an HTML digest under *header*."""
    if not articles:
        return f"{header}\n<i>No new headlines right now.</i>"
    lines = [header]
    for a in articles[:limit]:
        # Escape nothing fancy — titles are plain text; keep links raw.
        lines.append(f"📰 <b>{a.title}</b>\n   <a href=\"{a.link}\">{a.source}</a>")
    if len(articles) > limit:
        lines.append(f"\n…and {len(articles) - limit} more.")
    return "\n\n".join(lines)
