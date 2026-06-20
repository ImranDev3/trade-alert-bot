"""Crypto news aggregation from free RSS feeds.

No API keys are required — the sources are public RSS 2.0 feeds parsed with
the standard library. :func:`fetch_all` pulls recent articles from every
configured source and returns them sorted newest-first, tagged with the source
name so the bot can credit where each headline came from.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

_TIMEOUT = (5, 12)
_HEADERS = {"User-Agent": "trade-alert-bot/1.0 (github.com/ImranDev3)"}

# Free, key-less RSS feeds. Order roughly by signal quality / update frequency.
DEFAULT_SOURCES: dict[str, str] = {
    "Cointelegraph": "https://cointelegraph.com/rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Decrypt": "https://decrypt.co/feed",
    "Bitcoin News": "https://news.bitcoin.com/feed/",
}


@dataclass(frozen=True)
class Article:
    """One news headline."""

    title: str
    link: str
    source: str
    published: str  # raw pubDate string from the feed


class NewsError(Exception):
    """Raised when a feed cannot be fetched or parsed."""


def _clean(text: str | None) -> str:
    """Strip whitespace and common HTML junk from a headline."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def parse_feed(content: bytes, source: str) -> list[Article]:
    """Parse RSS/Atom XML bytes into :class:`Article` objects for *source*."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise NewsError(f"Could not parse feed from {source}: {exc}") from exc

    articles: list[Article] = []
    # RSS 2.0 wraps items in <item>; Atom uses <entry>.
    items = root.findall(".//item") or root.findall(".//entry")
    for node in items:
        title = _clean(node.findtext("title"))
        link = _clean(node.findtext("link"))
        if not link:
            # Atom puts the URL in a <link href="..."> attribute.
            link_el = node.find("link")
            if link_el is not None:
                link = _clean(link_el.get("href"))
        published = _clean(node.findtext("pubDate")) or _clean(node.findtext("published"))
        if title and link:
            articles.append(Article(title=title, link=link, source=source, published=published))
    return articles


def fetch_feed(name: str, url: str) -> list[Article]:
    """Fetch and parse a single feed, returning [] on failure (logged)."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.info("News feed %s unavailable: %s", name, exc)
        return []
    try:
        return parse_feed(resp.content, name)
    except NewsError as exc:
        log.warning("News feed %s parse error: %s", name, exc)
        return []


def fetch_all(sources: dict[str, str] | None = None, per_source: int = 10) -> list[Article]:
    """Pull recent articles from every source, newest-first, capped per source.

    Parameters
    ----------
    sources:
        Mapping of source name -> feed URL. Defaults to :data:`DEFAULT_SOURCES`.
    per_source:
        Max articles to keep from each source (keeps the digest readable).
    """
    sources = sources or DEFAULT_SOURCES
    all_articles: list[Article] = []
    for name, url in sources.items():
        articles = fetch_feed(name, url)[:per_source]
        all_articles.extend(articles)
        if articles:
            log.debug("News: %d article(s) from %s", len(articles), name)
    return all_articles
