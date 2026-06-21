"""Ack store: track which critical-news articles a user has already seen.

When the bot fires a CRITICAL headline it does so with sound on and an
inline "Got it" button. The repeat-after-send job uses this store to decide
who still needs a reminder. Acknowledging is permanent (per article link) and
persisted across restarts.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)


class AckStore:
    """Persists ``{user_id: {article_link, ...}}`` so acks survive restarts."""

    def __init__(self, persist_path: str | None = None) -> None:
        self._acks: dict[int, set[str]] = {}
        self._path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load()

    def acknowledge(self, user_id: int, link: str) -> bool:
        """Mark *link* as acked for *user_id*. Returns True if the state changed."""
        s = self._acks.setdefault(user_id, set())
        if link in s:
            return False
        s.add(link)
        self._save()
        return True

    def is_acked(self, user_id: int, link: str) -> bool:
        return link in self._acks.get(user_id, set())

    def unacknowledged(self, user_id: int, links: list[str]) -> list[str]:
        """Return the subset of *links* the user has not yet acked."""
        seen = self._acks.get(user_id, set())
        return [l for l in links if l not in seen]

    def _save(self) -> None:
        if not self._path:
            return
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        payload = {str(uid): sorted(s) for uid, s in self._acks.items()}
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, self._path)

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load acks from %s: %s", self._path, exc)
            return
        for k, v in payload.items():
            if k.isdigit() and isinstance(v, list):
                self._acks[int(k)] = {x for x in v if isinstance(x, str)}
        log.info("Loaded acks: %d user(s)", len(self._acks))
