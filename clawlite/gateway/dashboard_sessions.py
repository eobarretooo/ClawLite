from __future__ import annotations

import datetime as dt
import secrets
import threading
import time
from dataclasses import dataclass


DEFAULT_DASHBOARD_SESSION_TTL_SECONDS = 8 * 60 * 60
DEFAULT_DASHBOARD_SESSION_HEADER_NAME = "X-ClawLite-Dashboard-Session"
DEFAULT_DASHBOARD_SESSION_QUERY_PARAM = "dashboard_session"


@dataclass(slots=True)
class DashboardSessionRecord:
    token: str
    issued_at: float
    expires_at: float


class DashboardSessionRegistry:
    def __init__(self, *, ttl_seconds: int = DEFAULT_DASHBOARD_SESSION_TTL_SECONDS) -> None:
        self.ttl_seconds = max(60, int(ttl_seconds or DEFAULT_DASHBOARD_SESSION_TTL_SECONDS))
        self._lock = threading.RLock()
        self._sessions: dict[str, DashboardSessionRecord] = {}

    def _purge_expired_locked(self, *, now: float) -> None:
        expired = [token for token, row in self._sessions.items() if row.expires_at <= now]
        for token in expired:
            self._sessions.pop(token, None)

    def issue(self) -> DashboardSessionRecord:
        now = time.time()
        token = f"dshs1.{secrets.token_urlsafe(24)}"
        record = DashboardSessionRecord(
            token=token,
            issued_at=now,
            expires_at=now + self.ttl_seconds,
        )
        with self._lock:
            self._purge_expired_locked(now=now)
            self._sessions[token] = record
        return record

    def verify(self, token: str) -> bool:
        raw = str(token or "").strip()
        if not raw:
            return False
        now = time.time()
        with self._lock:
            self._purge_expired_locked(now=now)
            row = self._sessions.get(raw)
            if row is None or row.expires_at <= now:
                self._sessions.pop(raw, None)
                return False
            return True


def dashboard_session_expiry_iso(record: DashboardSessionRecord) -> str:
    return dt.datetime.fromtimestamp(record.expires_at, tz=dt.timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "DEFAULT_DASHBOARD_SESSION_HEADER_NAME",
    "DEFAULT_DASHBOARD_SESSION_QUERY_PARAM",
    "DEFAULT_DASHBOARD_SESSION_TTL_SECONDS",
    "DashboardSessionRecord",
    "DashboardSessionRegistry",
    "dashboard_session_expiry_iso",
]
