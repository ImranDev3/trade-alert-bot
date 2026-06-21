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
    """Persistent opt-in state for news and liquidation alerts.

    News operates in two modes, selected at construction time via
    *auto_subscribe_all*:

    * **opt-in** (default, ``auto_subscribe_all=False``) — only users who
      explicitly ran ``/newsauto on`` get the auto-drops.
    * **opt-out** (``auto_subscribe_all=True``) — every user the bot has
      ever seen gets auto-drops by default; running ``/newsauto off``
      removes them. This is the user-friendly default once the bot is
      deployed to a small, known audience.
    """

    def __init__(self, persist_path: str | None = None, auto_subscribe_all: bool = False) -> None:
        self._news_opt_in: set[int] = set()      # explicit opt-ins (used in opt-in mode)
        self._news_opt_out: set[int] = set()     # explicit opt-outs (used in opt-out mode)
        self._known_users: set[int] = set()      # anyone who has ever messaged
        self._liq: dict[int, float] = {}         # user_id -> USD threshold
        self._path = persist_path
        self._auto_all = auto_subscribe_all
        if persist_path and os.path.exists(persist_path):
            self._load()

    # ---- user tracking (for opt-out mode) ----

    def remember_user(self, user_id: int) -> None:
        """Note that *user_id* has interacted with the bot.

        In opt-out mode this is what makes them eligible for the news drop.
        Always persisted so a restart doesn't drop them from the next tick.
        """
        if user_id in self._known_users:
            return
        self._known_users.add(user_id)
        self._save()

    def known_users(self) -> list[int]:
        return sorted(self._known_users)

    # ---- news ----

    def subscribe_news(self, user_id: int) -> bool:
        """Opt *user_id* in (opt-in mode) or back in (opt-out mode)."""
        if self._auto_all:
            # In opt-out mode "subscribe" really means "remove from opt-outs",
            # so the user is again eligible for the auto-drop.
            if user_id not in self._news_opt_out:
                return False
            self._news_opt_out.discard(user_id)
            self._save()
            return True
        if user_id in self._news_opt_in:
            return False
        self._news_opt_in.add(user_id)
        self._save()
        return True

    def unsubscribe_news(self, user_id: int) -> bool:
        """Opt *user_id* out of news drops. Returns True if the state changed."""
        if self._auto_all:
            if user_id in self._news_opt_out:
                return False
            self._news_opt_out.add(user_id)
            self._save()
            return True
        if user_id not in self._news_opt_in:
            return False
        self._news_opt_in.discard(user_id)
        self._save()
        return True

    def news_subscribers(self) -> list[int]:
        """List of user IDs that should receive the next auto-drop.

        In opt-in mode: just the explicit opt-ins.
        In opt-out mode: every known user, minus the opt-outs.
        """
        if self._auto_all:
            return sorted(self._known_users - self._news_opt_out)
        return sorted(self._news_opt_in)

    def is_news_subscribed(self, user_id: int) -> bool:
        return user_id in self.news_subscribers()

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
            "auto_subscribe_all": self._auto_all,
            # Backwards-compat alias — old single "news" list is treated as opt-in.
            "news": sorted(self._news_opt_in),
            "news_opt_out": sorted(self._news_opt_out),
            "known_users": sorted(self._known_users),
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
        # Older single "news" list -> opt-in. Newer file has separate opt_out/known.
        self._news_opt_in = {int(x) for x in payload.get("news", []) if str(x).isdigit()}
        self._news_opt_out = {int(x) for x in payload.get("news_opt_out", []) if str(x).isdigit()}
        self._known_users = {int(x) for x in payload.get("known_users", []) if str(x).isdigit()}
        for k, v in payload.get("liquidations", {}).items():
            if str(k).isdigit() and isinstance(v, (int, float)):
                self._liq[int(k)] = float(v)
        log.info(
            "Loaded subscriptions: opt-in=%d opt-out=%d known=%d liq=%d (auto_all=%s)",
            len(self._news_opt_in), len(self._news_opt_out), len(self._known_users),
            len(self._liq), self._auto_all,
        )
