from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass


DEFAULT_DASHBOARD_SESSION_TTL_SECONDS = 8 * 60 * 60
DEFAULT_DASHBOARD_SESSION_HEADER_NAME = "X-ClawLite-Dashboard-Session"
DEFAULT_DASHBOARD_SESSION_QUERY_PARAM = "dashboard_session"
DEFAULT_DASHBOARD_CLIENT_HEADER_NAME = "X-ClawLite-Dashboard-Client"
DEFAULT_DASHBOARD_CLIENT_QUERY_PARAM = "dashboard_client"
DEFAULT_DASHBOARD_HANDOFF_TTL_SECONDS = 5 * 60
DEFAULT_DASHBOARD_HANDOFF_HEADER_NAME = "X-ClawLite-Dashboard-Handoff"
DEFAULT_DASHBOARD_HANDOFF_QUERY_PARAM = "dashboard_handoff"


@dataclass(slots=True)
class DashboardSessionRecord:
    token: str
    client_id: str
    issued_at: float
    expires_at: float


@dataclass(slots=True)
class DashboardHandoffRecord:
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

    @staticmethod
    def _normalize_client_id(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if len(raw) > 128:
            return ""
        return raw

    def issue(self, *, client_id: str) -> DashboardSessionRecord:
        now = time.time()
        normalized_client_id = self._normalize_client_id(client_id)
        if not normalized_client_id:
            raise ValueError("dashboard_client_required")
        token = f"dshs1.{secrets.token_urlsafe(24)}"
        record = DashboardSessionRecord(
            token=token,
            client_id=normalized_client_id,
            issued_at=now,
            expires_at=now + self.ttl_seconds,
        )
        with self._lock:
            self._purge_expired_locked(now=now)
            self._sessions[token] = record
        return record

    def verify(self, token: str, *, client_id: str) -> bool:
        raw = str(token or "").strip()
        normalized_client_id = self._normalize_client_id(client_id)
        if not raw or not normalized_client_id:
            return False
        now = time.time()
        with self._lock:
            self._purge_expired_locked(now=now)
            row = self._sessions.get(raw)
            if row is None or row.expires_at <= now:
                self._sessions.pop(raw, None)
                return False
            return hmac.compare_digest(str(row.client_id), normalized_client_id)


def dashboard_session_expiry_iso(record: DashboardSessionRecord) -> str:
    return dt.datetime.fromtimestamp(record.expires_at, tz=dt.timezone.utc).isoformat(timespec="seconds")


def dashboard_handoff_expiry_iso(record: DashboardHandoffRecord) -> str:
    return dt.datetime.fromtimestamp(record.expires_at, tz=dt.timezone.utc).isoformat(timespec="seconds")


def _urlsafe_b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _urlsafe_b64_decode(raw: str) -> bytes:
    text = str(raw or "").strip()
    if not text:
        return b""
    padding = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(f"{text}{padding}")


def issue_dashboard_handoff(
    *,
    gateway_token: str,
    ttl_seconds: int = DEFAULT_DASHBOARD_HANDOFF_TTL_SECONDS,
) -> DashboardHandoffRecord:
    clean_token = str(gateway_token or "").strip()
    if not clean_token:
        raise ValueError("dashboard_handoff_disabled")
    now = time.time()
    effective_ttl = max(30, int(ttl_seconds or DEFAULT_DASHBOARD_HANDOFF_TTL_SECONDS))
    expires_at = now + effective_ttl
    nonce = secrets.token_urlsafe(12)
    payload = f"{int(expires_at)}:{nonce}"
    signature = hmac.new(
        clean_token.encode("utf-8"),
        f"dashboard-handoff:{payload}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    token = f"dshh1.{_urlsafe_b64_encode(payload.encode('utf-8'))}.{_urlsafe_b64_encode(signature)}"
    return DashboardHandoffRecord(
        token=token,
        issued_at=now,
        expires_at=expires_at,
    )


def verify_dashboard_handoff(token: str, *, gateway_token: str) -> bool:
    clean_token = str(token or "").strip()
    signing_key = str(gateway_token or "").strip()
    if not clean_token or not signing_key:
        return False
    if not clean_token.startswith("dshh1."):
        return False
    try:
        _, payload_b64, signature_b64 = clean_token.split(".", 2)
        payload = _urlsafe_b64_decode(payload_b64).decode("utf-8")
        expected_signature = hmac.new(
            signing_key.encode("utf-8"),
            f"dashboard-handoff:{payload}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        supplied_signature = _urlsafe_b64_decode(signature_b64)
    except Exception:
        return False
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return False
    try:
        expires_raw, _nonce = payload.split(":", 1)
        expires_at = float(expires_raw)
    except Exception:
        return False
    return expires_at > time.time()


__all__ = [
    "DEFAULT_DASHBOARD_CLIENT_HEADER_NAME",
    "DEFAULT_DASHBOARD_CLIENT_QUERY_PARAM",
    "DEFAULT_DASHBOARD_HANDOFF_HEADER_NAME",
    "DEFAULT_DASHBOARD_HANDOFF_QUERY_PARAM",
    "DEFAULT_DASHBOARD_HANDOFF_TTL_SECONDS",
    "DEFAULT_DASHBOARD_SESSION_HEADER_NAME",
    "DEFAULT_DASHBOARD_SESSION_QUERY_PARAM",
    "DEFAULT_DASHBOARD_SESSION_TTL_SECONDS",
    "DashboardHandoffRecord",
    "DashboardSessionRecord",
    "DashboardSessionRegistry",
    "dashboard_handoff_expiry_iso",
    "dashboard_session_expiry_iso",
    "issue_dashboard_handoff",
    "verify_dashboard_handoff",
]
