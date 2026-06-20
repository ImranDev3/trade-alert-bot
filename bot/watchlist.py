"""Per-user watchlists.

A watchlist is the set of symbols a user wants the bot to track and report on
automatically. :class:`WatchlistStore` keeps them in memory (optionally
mirrored to JSON) and exposes a callback hook so the realtime WebSocket can be
told which crypto symbols to subscribe to.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable

from data.symbols import parse_symbol

log = logging.getLogger(__name__)

# Called with the union of all tracked crypto symbols whenever watchlists
# change, so the realtime layer can re-subscribe. Set via :func:`set_on_change`.
OnChangeListener = Callable[[set[str]], None]


@dataclass
class _WatchlistRow:
    """One row of the persisted JSON file."""

    user_id: int
    symbols: list[str]
    updated_at: str


class WatchlistStore:
    """In-memory watchlists keyed by Telegram user id, optional JSON persist."""

    MAX_PER_USER = 25  # keep the WS subscription list sane

    def __init__(self, persist_path: str | None = None) -> None:
        self._by_user: dict[int, set[str]] = {}
        self._path = persist_path
        self._on_change: OnChangeListener | None = None
        if persist_path and os.path.exists(persist_path):
            self._load()

    def set_on_change(self, callback: OnChangeListener) -> None:
        """Register a listener fired with the full crypto symbol set on changes."""
        self._on_change = callback
        # Fire once with the current set so subscribers stay in sync.
        if callback is not None:
            callback(self._crypto_symbols())

    # ---- mutation ----

    def add(self, user_id: int, symbol_raw: str) -> tuple[bool, str]:
        """Add *symbol* to a user's watchlist. Returns (ok, message)."""
        sym = parse_symbol(symbol_raw)
        if sym is None:
            return False, f"Invalid symbol: {symbol_raw!r}"
        user_set = self._by_user.setdefault(user_id, set())
        if sym.normalized in user_set:
            return False, f"{sym.display} is already on your watchlist."
        if len(user_set) >= self.MAX_PER_USER:
            return False, f"Watchlist full (max {self.MAX_PER_USER}). Remove one first."
        user_set.add(sym.normalized)
        self._save()
        self._notify()
        return True, f"✅ Added {sym.display} to your watchlist."

    def remove(self, user_id: int, symbol_raw: str) -> tuple[bool, str]:
        """Remove *symbol* from a user's watchlist. Returns (ok, message)."""
        sym = parse_symbol(symbol_raw)
        if sym is None:
            return False, f"Invalid symbol: {symbol_raw!r}"
        user_set = self._by_user.get(user_id)
        if not user_set or sym.normalized not in user_set:
            return False, f"{sym.display} is not on your watchlist."
        user_set.discard(sym.normalized)
        if not user_set:
            self._by_user.pop(user_id, None)
        self._save()
        self._notify()
        return True, f"🗑️ Removed {sym.display} from your watchlist."

    def clear(self, user_id: int) -> int:
        """Clear a user's watchlist; returns how many were removed."""
        removed = len(self._by_user.get(user_id, set()))
        if removed:
            self._by_user.pop(user_id, None)
            self._save()
            self._notify()
        return removed

    # ---- queries ----

    def get(self, user_id: int) -> list[str]:
        """A user's tracked symbols (normalized), sorted."""
        return sorted(self._by_user.get(user_id, set()))

    def all_user_ids(self) -> list[int]:
        """Users that currently have a non-empty watchlist."""
        return [uid for uid, s in self._by_user.items() if s]

    def _crypto_symbols(self) -> set[str]:
        """Union of every user's *crypto* symbols (what the WS should stream)."""
        out: set[str] = set()
        for syms in self._by_user.values():
            for s in syms:
                parsed = parse_symbol(s)
                if parsed and parsed.kind.value == "crypto":
                    out.add(parsed.normalized)
        return out

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change(self._crypto_symbols())

    # ---- persistence ----

    def _save(self) -> None:
        if not self._path:
            return
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        rows = [
            _WatchlistRow(uid, sorted(syms), datetime.now(timezone.utc).isoformat())
            for uid, syms in self._by_user.items()
        ]
        payload = {"watchlists": [asdict(r) for r in rows]}
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, self._path)

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load watchlists from %s: %s", self._path, exc)
            return
        for row in payload.get("watchlists", []):
            uid = row.get("user_id")
            syms = row.get("symbols", [])
            if isinstance(uid, int) and isinstance(syms, list):
                self._by_user[uid] = {s for s in syms if isinstance(s, str)}
        log.info("Loaded %d watchlist(s) from %s", len(self._by_user), self._path)
