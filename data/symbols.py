"""Symbol normalization and crypto/forex classification.

A user can type a symbol in many ways — ``btcusdt``, ``BTCUSDT``, ``eurusd``,
``EUR/USD``. This module cleans the input, decides whether it is a **crypto**
pair (traded on Binance, e.g. ``BTCUSDT``) or a **forex** pair (e.g. ``EURUSD``),
and splits it into base/quote currencies when relevant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SymbolKind(str, Enum):
    """What market a symbol belongs to."""

    CRYPTO = "crypto"
    FOREX = "forex"


# ISO 4217 currency codes commonly traded on FX. A 6-letter, all-alpha symbol
# whose two halves are both in this set is treated as a forex pair.
FOREX_CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD",
    "CNY", "INR", "HKD", "SGD", "SEK", "NOK", "DKK", "MXN",
    "ZAR", "TRY", "BRL", "RUB", "PLN", "THB", "KRW", "IDR",
    "AED", "SAR", "MYR", "PHP", "VND", "CZK", "HUF", "ILS",
}


@dataclass(frozen=True)
class Symbol:
    """A cleaned, classified market symbol."""

    raw: str          # the user's original input
    normalized: str   # canonical form used by APIs (e.g. "BTCUSDT", "EURUSD")
    kind: SymbolKind
    base: str         # base currency ("BTC", "EUR"); "" when not splittable
    quote: str        # quote currency ("USDT", "USD"); "" when not splittable

    @property
    def display(self) -> str:
        """A human-friendly label like ``BTC/USDT`` or ``EUR/USD``."""
        if self.base and self.quote:
            return f"{self.base}/{self.quote}"
        return self.normalized


def _strip(raw: str) -> str:
    """Remove spaces, slashes, dashes and uppercase the symbol."""
    return raw.upper().replace(" ", "").replace("/", "").replace("-", "")


def _is_forex_pair(cleaned: str) -> bool:
    """True for a 6-letter, all-alpha symbol whose halves are known FX codes."""
    if len(cleaned) != 6 or not cleaned.isalpha():
        return False
    base, quote = cleaned[:3], cleaned[3:]
    return base in FOREX_CURRENCIES and quote in FOREX_CURRENCIES


def parse_symbol(raw: str) -> Symbol | None:
    """Parse a user string into a :class:`Symbol`, or ``None`` if invalid.

    Examples
    --------
    >>> parse_symbol("btcusdt").normalized
    'BTCUSDT'
    >>> parse_symbol("EUR/USD").kind
    <SymbolKind.FOREX: 'forex'>
    """
    if not raw:
        return None
    cleaned = _strip(raw)
    if not cleaned:
        return None

    if _is_forex_pair(cleaned):
        return Symbol(
            raw=raw,
            normalized=cleaned,
            kind=SymbolKind.FOREX,
            base=cleaned[:3],
            quote=cleaned[3:],
        )

    # Otherwise assume crypto. Binance expects upper-case symbols like BTCUSDT.
    # Split base/quote on the most common quote assets when possible.
    for quote in ("USDT", "USDC", "BUSD", "FDUSD", "BTC", "ETH", "BNB"):
        if cleaned.endswith(quote) and len(cleaned) > len(quote):
            return Symbol(
                raw=raw,
                normalized=cleaned,
                kind=SymbolKind.CRYPTO,
                base=cleaned[: -len(quote)],
                quote=quote,
            )

    # Unknown quote asset — still treat as crypto, just without a split.
    return Symbol(
        raw=raw,
        normalized=cleaned,
        kind=SymbolKind.CRYPTO,
        base="",
        quote="",
    )
