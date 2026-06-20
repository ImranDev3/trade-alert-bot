"""Application configuration.

Loads settings from a local ``.env`` file (via python-dotenv) and exposes
them as module-level constants. The real ``.env`` is git-ignored, so secrets
never enter version control — see ``.env.example`` for the template.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load variables from .env into os.environ (no error if the file is missing).
load_dotenv()


def _get_str(key: str, default: str = "") -> str:
    """Return a trimmed env var or *default* if it is unset/empty."""
    value = os.getenv(key, default) or default
    return value.strip()


def _get_int(key: str, default: int) -> int:
    """Return an env var as int, falling back to *default* on bad/empty input."""
    raw = _get_str(key, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_int_list(key: str) -> list[int]:
    """Parse a comma-separated list of integers (e.g. ``"123,456``)."""
    raw = _get_str(key, "")
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


@dataclass(frozen=True)
class Settings:
    """Immutable bundle of all runtime settings."""

    telegram_bot_token: str
    poll_interval_seconds: int
    allowed_user_ids: list[int] = field(default_factory=list)
    # How often each user's watchlist prices are broadcast (seconds).
    watchlist_update_interval: int = 300
    # When the daily digest fires, as "HH:MM" (24h, local time). Empty = off.
    daily_summary_time: str = ""
    # WebSocket price cache freshness window (seconds).
    cache_ttl_seconds: int = 30

    @property
    def auth_enabled(self) -> bool:
        """True when an allow-list is configured (empty list = open access)."""
        return len(self.allowed_user_ids) > 0

    def is_allowed(self, user_id: int) -> bool:
        """Whether *user_id* may use the bot. Open to all when no list is set."""
        return (not self.auth_enabled) or (user_id in self.allowed_user_ids)


def load_settings() -> Settings:
    """Build and validate a :class:`Settings` instance from the environment."""
    token = _get_str("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing. "
            "Copy .env.example to .env and paste your token from @BotFather."
        )
    return Settings(
        telegram_bot_token=token,
        poll_interval_seconds=_get_int("POLL_INTERVAL_SECONDS", 60),
        allowed_user_ids=_get_int_list("ALLOWED_USER_IDS"),
        watchlist_update_interval=_get_int("WATCHLIST_UPDATE_INTERVAL", 300),
        daily_summary_time=_get_str("DAILY_SUMMARY_TIME", ""),
        cache_ttl_seconds=_get_int("CACHE_TTL_SECONDS", 30),
    )


# Eagerly loaded settings — imported by the rest of the app.
settings = load_settings()
