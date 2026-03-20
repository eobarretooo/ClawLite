from __future__ import annotations

import hashlib
import ipaddress
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True, frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_s: float = 0.0


@dataclass(slots=True)
class _FixedWindow:
    started_at: float
    count: int = 0


def normalize_client_ip(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "unknown"
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError:
        return raw.lower()
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        return str(parsed.ipv4_mapped)
    return parsed.compressed.lower()


def is_loopback_client_ip(value: str | None) -> bool:
    normalized = normalize_client_ip(value)
    if normalized == "unknown":
        return False
    try:
        return bool(ipaddress.ip_address(normalized).is_loopback)
    except ValueError:
        return normalized in {"localhost"} or normalized.startswith("127.")


def fingerprint_credential(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


class GatewayRateLimiter:
    def __init__(
        self,
        *,
        enabled: bool = True,
        window_s: float = 60.0,
        chat_requests_per_window: int = 60,
        ws_chat_requests_per_window: int = 60,
        exempt_loopback: bool = False,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.window_s = max(1.0, float(window_s))
        self.chat_requests_per_window = max(0, int(chat_requests_per_window))
        self.ws_chat_requests_per_window = max(0, int(ws_chat_requests_per_window))
        self.exempt_loopback = bool(exempt_loopback)
        self._now_fn = now_fn or time.monotonic
        self._lock = threading.Lock()
        self._windows: dict[str, _FixedWindow] = {}

    def _now(self) -> float:
        return float(self._now_fn())

    def _resolve_window(self, *, bucket: str, now: float) -> _FixedWindow:
        current = self._windows.get(bucket)
        if current is None or (now - current.started_at) >= self.window_s:
            current = _FixedWindow(started_at=now)
            self._windows[bucket] = current
        return current

    def _prune(self, *, now: float) -> None:
        stale = [bucket for bucket, window in self._windows.items() if (now - window.started_at) >= self.window_s]
        for bucket in stale:
            self._windows.pop(bucket, None)

    def _consume(self, *, scope: str, client_ip: str | None, credential: str, limit: int) -> RateLimitDecision:
        if not self.enabled or limit <= 0:
            return RateLimitDecision(allowed=True, remaining=max(0, int(limit)))
        normalized_ip = normalize_client_ip(client_ip)
        if self.exempt_loopback and is_loopback_client_ip(normalized_ip):
            return RateLimitDecision(allowed=True, remaining=max(0, int(limit)))

        buckets = [f"{scope}:ip:{normalized_ip}"]
        if str(credential or "").strip():
            buckets.append(f"{scope}:cred:{fingerprint_credential(credential)}")

        now = self._now()
        with self._lock:
            self._prune(now=now)
            windows = [self._resolve_window(bucket=bucket, now=now) for bucket in buckets]
            blocked_retry_after = 0.0
            for window in windows:
                if window.count >= limit:
                    blocked_retry_after = max(blocked_retry_after, max(0.0, self.window_s - (now - window.started_at)))
            if blocked_retry_after > 0:
                return RateLimitDecision(allowed=False, remaining=0, retry_after_s=round(blocked_retry_after, 3))
            for window in windows:
                window.count += 1
            remaining = min(max(0, limit - window.count) for window in windows)
            return RateLimitDecision(allowed=True, remaining=remaining, retry_after_s=0.0)

    def consume_http_chat(self, *, client_ip: str | None, credential: str = "") -> RateLimitDecision:
        return self._consume(
            scope="http:chat",
            client_ip=client_ip,
            credential=credential,
            limit=self.chat_requests_per_window,
        )

    def consume_ws_chat(self, *, client_ip: str | None, credential: str = "") -> RateLimitDecision:
        return self._consume(
            scope="ws:chat",
            client_ip=client_ip,
            credential=credential,
            limit=self.ws_chat_requests_per_window,
        )
