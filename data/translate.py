"""English -> Bangla translation with a small in-process cache.

Wraps :mod:`deep_translator.GoogleTranslator` so the rest of the bot doesn't
have to know about the API. The cache keeps things fast and protects us from
Google's free-tier rate limits when the same headline gets re-checked in
successive ticks.
"""

from __future__ import annotations

import logging

from deep_translator import GoogleTranslator

log = logging.getLogger(__name__)

# How many translations to remember. Plenty for one session's news cycle.
_CACHE_LIMIT = 512
_DEFAULT_TARGET = "bn"  # ISO 639-1 for Bangla


class Translator:
    """A tiny cached English -> target-language translator."""

    def __init__(self, target: str = _DEFAULT_TARGET) -> None:
        self._target = target
        self._cache: dict[str, str] = {}
        # Translator objects are cheap to build, but a single instance is even
        # cheaper; create one lazily on first call.
        self._backend: GoogleTranslator | None = None

    def _backend_get(self) -> GoogleTranslator:
        if self._backend is None:
            self._backend = GoogleTranslator(source="auto", target=self._target)
        return self._backend

    def translate(self, text: str) -> str:
        """Translate *text*. Empty/whitespace input is returned unchanged.

        On any error (network, rate-limit, garbage from the source) the
        original text is returned so the digest still ships — just not
        translated, never crashes.
        """
        if not text or not text.strip():
            return text
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        try:
            out = self._backend_get().translate(text)
        except Exception as exc:  # noqa: BLE001 — many transient failures
            log.info("Translate failed (%s); falling back to source", type(exc).__name__)
            return text
        if not out:
            return text
        # Bound the cache so a long-lived bot doesn't grow it forever.
        if len(self._cache) >= _CACHE_LIMIT:
            self._cache.pop(next(iter(self._cache)))
        self._cache[text] = out
        return out

    def cache_size(self) -> int:
        return len(self._cache)
