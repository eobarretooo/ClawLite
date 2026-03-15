from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from clawlite.config.schema import AppConfig

_MAX_ENTRIES = 5


class ConfigAudit:
    """Ring buffer of the last N loaded configs with timestamps.

    Useful for ``config diff`` tooling and debugging hot-reload behaviour.
    """

    def __init__(self, maxlen: int = _MAX_ENTRIES) -> None:
        self._entries: deque[tuple[str, AppConfig]] = deque(maxlen=max(1, maxlen))

    def record(self, config: AppConfig) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self._entries.append((ts, config))

    def history(self) -> list[dict[str, Any]]:
        """Return list of {timestamp, config_dict} entries, oldest first."""
        return [
            {"timestamp": ts, "config": cfg.to_dict()}
            for ts, cfg in self._entries
        ]

    def diff(self) -> dict[str, Any] | None:
        """Return a shallow diff between the two most recent configs.

        Returns ``None`` if fewer than two entries are recorded.
        Keys present in the diff map to ``{"before": ..., "after": ...}``.
        """
        if len(self._entries) < 2:
            return None
        entries = list(self._entries)
        before_ts, before_cfg = entries[-2]
        after_ts, after_cfg = entries[-1]
        before = before_cfg.to_dict()
        after = after_cfg.to_dict()
        changes: dict[str, Any] = {}
        all_keys = set(before) | set(after)
        for key in sorted(all_keys):
            b = before.get(key)
            a = after.get(key)
            if b != a:
                changes[key] = {"before": b, "after": a}
        return {
            "before_timestamp": before_ts,
            "after_timestamp": after_ts,
            "changes": changes,
        }

    def latest(self) -> AppConfig | None:
        if not self._entries:
            return None
        return self._entries[-1][1]
