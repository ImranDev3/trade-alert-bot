"""Alert storage and price-crossing logic.

An :class:`Alert` is a one-shot rule: *"tell me when SYMBOL goes ABOVE/BELOW
TARGET"*. The :class:`AlertStore` keeps alerts in memory (optionally mirrored
to a JSON file) and exposes simple add / list / remove operations plus a
:func:`check` helper that decides whether a given price has crossed an alert.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterator

log = logging.getLogger(__name__)


class Direction(str, Enum):
    """Which side of the target the price must reach to fire the alert."""

    ABOVE = "above"
    BELOW = "below"

    @classmethod
    def parse(cls, text: str) -> "Direction | None":
        """Accept ``above``/``over``/``below``/``under`` case-insensitively."""
        norm = (text or "").strip().lower()
        if norm in ("above", "over", ">", "up"):
            return cls.ABOVE
        if norm in ("below", "under", "<", "down"):
            return cls.BELOW
        return None


class AlertKind(str, Enum):
    """Whether the alert watches an absolute price or a relative move."""

    PRICE = "price"      # fire when price crosses target_price
    PERCENT = "percent"  # fire when price moves pct% from baseline

    @classmethod
    def parse(cls, text: str) -> "AlertKind | None":
        norm = (text or "").strip().lower().rstrip("%")
        if norm in ("percent", "pct", "%", "change"):
            return cls.PERCENT
        if norm in ("price", "level"):
            return cls.PRICE
        return None


@dataclass
class Alert:
    """A single alert owned by one Telegram user.

    Two flavours, selected by :attr:`kind`:

    * **PRICE** — fires when ``price`` crosses ``target_price`` (above/below).
    * **PERCENT** — fires when ``price`` has moved ``pct`` percent from
      ``baseline``; direction ABOVE means "rose by pct%", BELOW means
      "fell by pct%". ``baseline`` is captured when the alert is created.
    """

    id: int
    user_id: int
    symbol: str          # normalized form, e.g. "BTCUSDT" / "EURUSD"
    direction: Direction
    kind: AlertKind = AlertKind.PRICE
    target_price: float = 0.0   # used for PRICE alerts
    pct: float = 0.0            # percent threshold for PERCENT alerts
    baseline: float = 0.0       # reference price captured at creation
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def direction_word(self) -> str:
        return self.direction.value

    @property
    def threshold_price(self) -> float:
        """The absolute price at which a PERCENT alert would fire."""
        if self.kind is AlertKind.PERCENT and self.baseline:
            delta = self.baseline * (self.pct / 100.0)
            if self.direction is Direction.ABOVE:
                return self.baseline + delta
            return self.baseline - delta
        return self.target_price

    def is_crossed_by(self, price: float) -> bool:
        """Whether *price* has reached this alert's target."""
        target = self.threshold_price
        if self.direction is Direction.ABOVE:
            return price >= target
        return price <= target

    def change_percent(self, price: float) -> float:
        """Signed percent change of *price* relative to the baseline (0 if none)."""
        if not self.baseline:
            return 0.0
        return (price - self.baseline) / self.baseline * 100.0


class AlertStore:
    """In-memory alert store with optional JSON persistence.

    Parameters
    ----------
    persist_path:
        If set, alerts are loaded on init and saved on every mutation.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._alerts: dict[int, Alert] = {}
        self._next_id: int = 1
        self._path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load()

    # ---- mutation ----

    def add(
        self,
        user_id: int,
        symbol: str,
        direction: Direction,
        target_price: float = 0.0,
        *,
        kind: AlertKind = AlertKind.PRICE,
        pct: float = 0.0,
        baseline: float = 0.0,
    ) -> Alert:
        """Create, store, and return a new :class:`Alert`.

        For PRICE alerts pass ``target_price``. For PERCENT alerts pass
        ``pct`` and ``baseline`` (the reference price captured at creation).
        """
        alert = Alert(
            id=self._next_id,
            user_id=user_id,
            symbol=symbol,
            direction=direction,
            kind=kind,
            target_price=target_price,
            pct=pct,
            baseline=baseline,
        )
        self._alerts[alert.id] = alert
        self._next_id += 1
        self._save()
        if kind is AlertKind.PERCENT:
            log.info("Alert #%d added: %s %s %.2f%% (base %s)", alert.id, symbol, direction.value, pct, baseline)
        else:
            log.info("Alert #%d added: %s %s %s", alert.id, symbol, direction.value, target_price)
        return alert

    def remove(self, alert_id: int, user_id: int) -> bool:
        """Delete an alert, but only if it belongs to *user_id*.

        Returns ``True`` if an alert was actually removed.
        """
        alert = self._alerts.get(alert_id)
        if alert is None or alert.user_id != user_id:
            return False
        del self._alerts[alert_id]
        self._save()
        log.info("Alert #%d removed", alert_id)
        return True

    def pop(self, alert_id: int) -> Alert | None:
        """Remove and return an alert regardless of owner (used by the poller)."""
        return self._alerts.pop(alert_id, None)

    # ---- queries ----

    def get(self, alert_id: int) -> Alert | None:
        return self._alerts.get(alert_id)

    def list_for(self, user_id: int) -> list[Alert]:
        """All alerts belonging to *user_id*, ordered by id."""
        return [a for a in self._alerts.values() if a.user_id == user_id]

    def all(self) -> Iterator[Alert]:
        """Iterate every alert (used by the background polling job)."""
        return iter(self._alerts.values())

    def __len__(self) -> int:
        return len(self._alerts)

    # ---- persistence ----

    def _save(self) -> None:
        if not self._path:
            return
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        payload = {
            "next_id": self._next_id,
            "alerts": [asdict(a) for a in self._alerts.values()],
        }
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, self._path)  # atomic-ish write

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load alerts from %s: %s", self._path, exc)
            return
        for raw in payload.get("alerts", []):
            try:
                raw["direction"] = Direction(raw["direction"])
                # Tolerate older saved files that predate PERCENT alerts.
                kind_raw = raw.pop("kind", AlertKind.PRICE.value)
                raw["kind"] = AlertKind(kind_raw)
                raw.setdefault("pct", 0.0)
                raw.setdefault("baseline", 0.0)
                alert = Alert(**raw)
            except (TypeError, ValueError, KeyError) as exc:
                log.warning("Skipping malformed alert %r: %s", raw, exc)
                continue
            self._alerts[alert.id] = alert
        self._next_id = max([a.id for a in self._alerts.values()], default=0) + 1
        log.info("Loaded %d alert(s) from %s", len(self._alerts), self._path)


def check(alert: Alert, price: float | None) -> bool:
    """Return True if *price* is valid and has crossed *alert*'s target.

    A ``None`` price (fetch failed) never triggers an alert.
    """
    if price is None:
        return False
    return alert.is_crossed_by(price)
