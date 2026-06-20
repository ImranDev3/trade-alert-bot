"""Opt-in subscriptions for auto-drops.

Both the news auto-drop and the large-liquidation alerts only reach users who
have opted in, so the bot never spams people who haven't asked.
:class:`SubscriberStore` tracks:

* **news subscribers** — a set of Telegram user IDs that get new headlines,
* **liquidation thresholds** — per-user USD amount; a liquidation worth at
  least that much triggers a ping.

Everything is persisted to JSON so subscriptions survive restarts.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

# A sane floor for liquidation alerts — anything below is just market noise.
MIN_LIQ_THRESHOLD = 5_000.0


class SubscriberStore:
    """Persistent opt-in state for news and liquidation alerts."""

    def __init__(self, persist_path: str | None = None) -> None:
        self._news: set[int] = set()
        self._liq: dict[int, float] = {}  # user_id -> USD threshold
        self._path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load()

    # ---- news ----

    def subscribe_news(self, user_id: int) -> bool:
        """Opt *user_id* into auto news drops. Returns True if newly added."""
        if user_id in self._news:
            return False
        self._news.add(user_id)
        self._save()
        return True

    def unsubscribe_news(self, user_id: int) -> bool:
        """Opt *user_id* out of news drops. Returns True if it was subscribed."""
        if user_id not in self._news:
            return False
        self._news.discard(user_id)
        self._save()
        return True

    def news_subscribers(self) -> list[int]:
        return sorted(self._news)

    def is_news_subscribed(self, user_id: int) -> bool:
        return user_id in self._news

    # ---- liquidations ----

    def set_liq_threshold(self, user_id: int, usd: float) -> float:
        """Subscribe to liquidation alerts at >= *usd*; clamped to a floor.

        Returns the threshold actually stored.
        """
        threshold = max(float(usd), MIN_LIQ_THRESHOLD)
        self._liq[user_id] = threshold
        self._save()
        return threshold

    def clear_liq_threshold(self, user_id: int) -> bool:
        """Unsubscribe *user_id* from liquidation alerts."""
        if user_id not in self._liq:
            return False
        del self._liq[user_id]
        self._save()
        return True

    def get_liq_threshold(self, user_id: int) -> float | None:
        return self._liq.get(user_id)

    def liq_subscribers(self) -> dict[int, float]:
        """A copy of user_id -> threshold for everyone opted into liquidations."""
        return dict(self._liq)

    # ---- persistence ----

    def _save(self) -> None:
        if not self._path:
            return
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        payload = {
            "news": sorted(self._news),
            "liquidations": {str(k): v for k, v in self._liq.items()},
        }
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, self._path)

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load subscriptions from %s: %s", self._path, exc)
            return
        self._news = {int(x) for x in payload.get("news", []) if str(x).isdigit()}
        for k, v in payload.get("liquidations", {}).items():
            if str(k).isdigit() and isinstance(v, (int, float)):
                self._liq[int(k)] = float(v)
        log.info("Loaded subscriptions: %d news, %d liq", len(self._news), len(self._liq))
