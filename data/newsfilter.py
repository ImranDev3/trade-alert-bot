"""Importance filtering for crypto news headlines.

A headline is considered "important" when it mentions a high-signal topic
(regulatory action, big money, hacks, market shocks, key events) **or** a
symbol the user is actively watching. :func:`filter_important` keeps only the
articles that score above a configurable threshold for a given user's
watchlist, so the auto-drop only surfaces headlines that actually matter.

Both signals are free and key-less — pure keyword/symbol matching.
"""

from __future__ import annotations

import re

from data.news import Article

# High-signal topic keywords. Matched case-insensitively as whole words.
# Each tuple is (regex pattern, weight). Weights make rare/blocker words score
# higher so a headline like "SEC approves Bitcoin ETF" outranks "small dip".
_IMPORTANT_KEYWORDS: list[tuple[str, int]] = [
    # Regulation / legal (blockers — usually move markets hard)
    (r"\bSEC\b", 3), (r"\bregulat", 2), (r"\bban\b", 3), (r"\blawsuit\b", 2),
    (r"\bsanction", 3), (r"\bapprov", 3), (r"\bruling\b", 2), (r"\bDOJ\b", 2),
    # Big money / milestones
    (r"\bbillion\b", 2), (r"\btrillion\b", 3), (r"\ball[-\s]?time high\b", 3),
    (r"\bATH\b", 2), (r"\brecord\b", 1), (r"\binflow", 2), (r"\boutflow", 2),
    # Market shocks
    (r"\bcrash", 3), (r"\bplunge", 3), (r"\bsurge", 2), (r"\brally\b", 2),
    (r"\bpump\b", 1), (r"\bdump\b", 2), (r"\bselloff\b", 2), (r"\bliquidat", 2),
    # Security
    (r"\bhack", 3), (r"\bexploit\b", 3), (r"\bbreach\b", 2), (r"\bdrain", 3),
    (r"\bdefect\b", 1), (r"\bvulnerab", 2), (r"\battack\b", 2), (r"\bstolen\b", 2),
    # Key events
    (r"\bETF\b", 3), (r"\bhalving\b", 3), (r"\bairdrop\b", 2),
    (r"\bpartnership\b", 2), (r"\blisting\b", 2), (r"\blaunch", 2),
    (r"\bupgrade\b", 2), (r"\bfork\b", 2), (r"\bintegrat", 2),
    (r"\bacquisit", 2), (r"\bmerger\b", 2),
]

# Default minimum score for a headline to be "important" via keywords alone.
DEFAULT_KEYWORD_THRESHOLD = 2

_COMPILED = [(re.compile(pat, re.IGNORECASE), w) for pat, w in _IMPORTANT_KEYWORDS]


def _symbol_terms(symbols: list[str]) -> list[str]:
    """Turn normalized symbols (BTCUSDT, EURUSD) into matchable base terms.

    BTCUSDT -> "BTC", ETHUSDT -> "ETH", EURUSD -> "EUR", SOLBTC -> "SOL".
    Only the base currency is kept — that's what news headlines actually print.
    """
    from data.symbols import parse_symbol

    terms: list[str] = []
    for sym in symbols:
        parsed = parse_symbol(sym)
        if parsed and parsed.base:
            terms.append(parsed.base.upper())
    return terms


def keyword_score(title: str) -> int:
    """Sum of matched important-keyword weights in *title*."""
    if not title:
        return 0
    score = 0
    for pattern, weight in _COMPILED:
        if pattern.search(title):
            score += weight
    return score


# Category emoji per topic. The first matching category in order wins, so
# we put the most specific/important categories first (regulation, hacks) and
# the generic crypto marker last as a fallback.
_CATEGORY_EMOJI: list[tuple[str, str]] = [
    (r"\bSEC\b|\bregulat|\bban\b|\blawsuit\b|\bsanction|\bapprov|\bruling\b|\bDOJ\b", "⚖️"),
    (r"\bETF\b|\bhalving\b", "🏛️"),
    (r"\bhack\b|\bexploit\b|\bbreach\b|\bdrain\b|\bvulnerab", "🔓"),
    (r"\bcrash\b|\bplunge\b|\bselloff\b|\bliquidat", "📉"),
    (r"\bsurge\b|\brally\b|\bpump\b|\ball[-\s]?time high\b|\bATH\b", "🚀"),
    (r"\bbillion\b|\btrillion\b|\binflow|\boutflow", "💰"),
    (r"\bpartnership\b|\blaunch\b|\bintegrat|\blisting\b|\bacquisit|\bmerger", "🤝"),
    (r"\bairdrop\b|\bupgrade\b|\bfork\b", "🧬"),
    (r"\brecord\b|\bcrash\b", "🔔"),
    (r"\bBitcoin\b|\bBTC\b|\bEthereum\b|\bETH\b|\bSolana\b|\bSOL\b", "🪙"),
]
_COMPILED_CATEGORIES = [(re.compile(pat, re.IGNORECASE), emoji) for pat, emoji in _CATEGORY_EMOJI]


def category_emoji(title: str) -> str:
    """Return a topic-matched emoji for *title*, or a generic 🪙 fallback."""
    if not title:
        return "🪙"
    for pattern, emoji in _COMPILED_CATEGORIES:
        if pattern.search(title):
            return emoji
    return "🪙"



def matches_watchlist(title: str, symbols: list[str]) -> bool:
    """True when *title* mentions the base of any of *symbols* as a word."""
    terms = _symbol_terms(symbols)
    if not terms:
        return False
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", title, re.IGNORECASE):
            return True
    return False


def is_important(
    article: Article,
    watchlist_symbols: list[str] | None = None,
    keyword_threshold: int = DEFAULT_KEYWORD_THRESHOLD,
) -> bool:
    """Decide if *article* is important for a user with the given watchlist.

    Important when either:
    * its keyword score meets *keyword_threshold*, **or**
    * it mentions one of the user's watched symbols' base currency.
    """
    title = article.title or ""
    if keyword_score(title) >= keyword_threshold:
        return True
    if watchlist_symbols and matches_watchlist(title, watchlist_symbols):
        return True
    return False


def filter_important(
    articles: list[Article],
    watchlist_symbols: list[str] | None = None,
    keyword_threshold: int = DEFAULT_KEYWORD_THRESHOLD,
) -> list[Article]:
    """Keep only the articles :func:`is_important` flags for this watchlist."""
    return [
        a for a in articles
        if is_important(a, watchlist_symbols, keyword_threshold)
    ]


# Critical-tier keywords: a headline that mentions *any* of these (with the
# matching weight summed) is treated as a "block-level" event that the user
# almost certainly wants to know about immediately — ETF approvals, hacks,
# regulator action, market shocks. These are stricter than the "important"
# tier on purpose: we'd rather over-page on a real event than miss it.
_CRITICAL_KEYWORDS: list[tuple[str, int]] = [
    # Regulation / legal (hard blocks)
    (r"\bSEC\b.*(approv|reject|charge|file)", 4),
    (r"\bSEC\b", 3),
    (r"\bETF\b.*(approv|reject|launch|delay)", 4),
    (r"\bETF\b", 3),
    (r"\bban\b", 4),
    (r"\bsanction", 4),
    (r"\bDOJ\b", 3),
    (r"\blawsuit\b.*(SEC|crypto|Bitcoin|Ethereum)", 3),
    # Security
    (r"\bhack\b.*\$\d", 4),  # "$X hack"
    (r"\bexploit\b.*\$\d", 4),
    (r"\bbreach\b.*\$\d", 4),
    (r"\bdrain", 4),
    (r"\b(hack|exploit|breach|attack)\b.*\b(user|wallet|customer|funds?|million|billion)", 4),
    (r"\b(vulnerab|exploit|attack).*found", 3),
    # Market shocks
    (r"\bcrash", 4),
    (r"\bplunge", 4),
    (r"\bselloff\b.*(market|wall|street|bitcoin|crypto)", 3),
    (r"\bliquidat", 3),
    # Major milestones
    (r"\bATH\b", 3),
    (r"all[-\s]?time high", 2),
    (r"\btrillion\b", 4),
]
_COMPILED_CRITICAL = [(re.compile(pat, re.IGNORECASE), w) for pat, w in _CRITICAL_KEYWORDS]

# Minimum score to be classified as critical. Picked so simple mentions of
# "ETF" alone still hit the important tier, but a "SEC approves ETF" pairing
# (4 + 3 = 7) blows past it.
CRITICAL_THRESHOLD = 4


def is_critical(article: Article) -> bool:
    """Return True if *article* is a block-level headline the user must see.

    Used to flag stories that get an extra-loud delivery (sound on, repeated
    if unacknowledged) in addition to the regular important digest.
    """
    title = article.title or ""
    score = 0
    for pattern, weight in _COMPILED_CRITICAL:
        if pattern.search(title):
            score += weight
    return score >= CRITICAL_THRESHOLD


def filter_critical(articles: list[Article]) -> list[Article]:
    """Keep only the critical headlines from *articles*."""
    return [a for a in articles if is_critical(a)]
