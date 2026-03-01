from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class OutboundSendResult:
    ok: bool
    attempts: int
    idempotency_key: str
    error: dict[str, Any] | None = None


class OutboundResilience:
    """
    Utilitário de envio outbound com retry exponencial, timeout e dedupe básico.
    """

    def __init__(
        self,
        channel: str,
        *,
        timeout_s: float,
        max_attempts: int = 3,
        base_backoff_s: float = 0.25,
        dedupe_ttl_s: float = 8.0,
        dedupe_max_entries: int = 512,
        breaker_failure_threshold: int = 5,
        breaker_cooldown_s: float = 30.0,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.channel = str(channel or "").strip() or "unknown"
        self.timeout_s = max(0.1, float(timeout_s))
        self.max_attempts = max(1, min(int(max_attempts), 3))
        self.base_backoff_s = max(0.0, float(base_backoff_s))
        self.dedupe_ttl_s = max(1.0, float(dedupe_ttl_s))
        self.dedupe_max_entries = max(32, int(dedupe_max_entries))
        self.breaker_failure_threshold = max(1, int(breaker_failure_threshold))
        self.breaker_cooldown_s = max(0.1, float(breaker_cooldown_s))
        self._sleep_fn = sleep_fn
        self._recent_sent: dict[str, float] = {}
        self._metrics: dict[str, int] = {
            "sent_ok": 0,
            "retry_count": 0,
            "timeout_count": 0,
            "fallback_count": 0,
            "send_fail_count": 0,
            "dedupe_hits": 0,
            "circuit_open_count": 0,
            "circuit_half_open_count": 0,
            "circuit_blocked_count": 0,
        }
        self._last_error: dict[str, Any] | None = None
        self._last_success_at: str | None = None
        self._breaker_state = "closed"
        self._breaker_consecutive_failures = 0
        self._breaker_open_until_monotonic: float | None = None
        self._breaker_open_until_iso: str | None = None
        self._breaker_probe_in_flight = False

    def make_idempotency_key(self, target: str, text: str) -> str:
        raw = f"{self.channel}\n{str(target)}\n{str(text)}".encode("utf-8", errors="ignore")
        return hashlib.sha256(raw).hexdigest()[:32]

    def _prune_recent(self, now_ts: float) -> None:
        expired = [key for key, ts in self._recent_sent.items() if now_ts - ts > self.dedupe_ttl_s]
        for key in expired:
            self._recent_sent.pop(key, None)

        if len(self._recent_sent) <= self.dedupe_max_entries:
            return

        overflow = len(self._recent_sent) - self.dedupe_max_entries
        for key, _ in sorted(self._recent_sent.items(), key=lambda item: item[1])[:overflow]:
            self._recent_sent.pop(key, None)

    def _build_error(
        self,
        *,
        provider: str,
        code: str,
        attempts: int,
        reason: str,
        fallback: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        severity = self._severity_for_code(code)
        return {
            "channel": self.channel,
            "provider": str(provider),
            "code": str(code),
            "severity": severity,
            "category": "outbound_operational",
            "policy_version": "outbound-v1",
            "attempts": int(attempts),
            "reason": str(reason),
            "fallback": str(fallback),
            "idempotency_key": str(idempotency_key),
        }

    def _log_failure(self, logger: logging.Logger, error: dict[str, Any]) -> None:
        logger.error(
            "Outbound falhou channel=%s provider=%s code=%s attempts=%s reason=%s fallback=%s",
            error["channel"],
            error["provider"],
            error["code"],
            error["attempts"],
            error["reason"],
            error["fallback"],
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _severity_for_code(code: str) -> str:
        normalized = str(code or "").strip().lower()
        if normalized in {"provider_timeout", "provider_circuit_open", "provider_circuit_half_open"}:
            return "warning"
        return "error"

    def _inc(self, metric: str, value: int = 1) -> None:
        self._metrics[metric] = int(self._metrics.get(metric, 0)) + int(value)

    def _record_error(self, error: dict[str, Any]) -> None:
        self._last_error = {
            "provider": str(error.get("provider", "")),
            "code": str(error.get("code", "")),
            "severity": str(error.get("severity", "")),
            "category": str(error.get("category", "")),
            "policy_version": str(error.get("policy_version", "")),
            "reason": str(error.get("reason", "")),
            "attempts": int(error.get("attempts", 0)),
            "at": self._now_iso(),
        }

    def _breaker_cooldown_remaining_s(self) -> float:
        if self._breaker_state != "open" or self._breaker_open_until_monotonic is None:
            return 0.0
        return max(0.0, self._breaker_open_until_monotonic - time.monotonic())

    def _open_circuit(self) -> None:
        self._breaker_state = "open"
        self._breaker_probe_in_flight = False
        self._breaker_open_until_monotonic = time.monotonic() + self.breaker_cooldown_s
        self._breaker_open_until_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=self.breaker_cooldown_s)
        ).isoformat()
        self._inc("circuit_open_count")

    def _on_delivery_success(self) -> None:
        self._breaker_state = "closed"
        self._breaker_consecutive_failures = 0
        self._breaker_open_until_monotonic = None
        self._breaker_open_until_iso = None
        self._breaker_probe_in_flight = False

    def _on_delivery_failure(self) -> None:
        if self._breaker_state == "half_open":
            self._breaker_consecutive_failures = self.breaker_failure_threshold
            self._open_circuit()
            return
        self._breaker_consecutive_failures += 1
        if self._breaker_consecutive_failures >= self.breaker_failure_threshold:
            self._open_circuit()

    def _build_circuit_block_result(
        self,
        *,
        logger: logging.Logger,
        provider: str,
        target: str,
        text: str,
        code: str,
        reason: str,
        fallback: str,
    ) -> OutboundSendResult:
        key = self.make_idempotency_key(target, text)
        error = self._build_error(
            provider=provider,
            code=code,
            attempts=0,
            reason=reason,
            fallback=fallback,
            idempotency_key=key,
        )
        self._inc("send_fail_count")
        self._inc("fallback_count")
        self._inc("circuit_blocked_count")
        self._record_error(error)
        self._log_failure(logger, error)
        return OutboundSendResult(ok=False, attempts=0, idempotency_key=key, error=error)

    def _guard_circuit(
        self,
        *,
        logger: logging.Logger,
        provider: str,
        target: str,
        text: str,
        fallback: str,
    ) -> OutboundSendResult | None:
        if self._breaker_state == "open":
            remaining = self._breaker_cooldown_remaining_s()
            if remaining > 0:
                return self._build_circuit_block_result(
                    logger=logger,
                    provider=provider,
                    target=target,
                    text=text,
                    code="provider_circuit_open",
                    reason=f"circuit-open cooldown={remaining:.2f}s",
                    fallback=fallback,
                )
            self._breaker_state = "half_open"
            self._breaker_probe_in_flight = False
            self._inc("circuit_half_open_count")

        if self._breaker_state == "half_open":
            if self._breaker_probe_in_flight:
                return self._build_circuit_block_result(
                    logger=logger,
                    provider=provider,
                    target=target,
                    text=text,
                    code="provider_circuit_half_open",
                    reason="probe-in-flight",
                    fallback=fallback,
                )
            self._breaker_probe_in_flight = True
        return None

    def metrics_snapshot(self) -> dict[str, Any]:
        row = {
            "sent_ok": int(self._metrics.get("sent_ok", 0)),
            "retry_count": int(self._metrics.get("retry_count", 0)),
            "timeout_count": int(self._metrics.get("timeout_count", 0)),
            "fallback_count": int(self._metrics.get("fallback_count", 0)),
            "send_fail_count": int(self._metrics.get("send_fail_count", 0)),
            "dedupe_hits": int(self._metrics.get("dedupe_hits", 0)),
            "circuit_open_count": int(self._metrics.get("circuit_open_count", 0)),
            "circuit_half_open_count": int(self._metrics.get("circuit_half_open_count", 0)),
            "circuit_blocked_count": int(self._metrics.get("circuit_blocked_count", 0)),
            "circuit_state": self._breaker_state,
            "circuit_failure_threshold": self.breaker_failure_threshold,
            "circuit_cooldown_seconds": self.breaker_cooldown_s,
            "circuit_consecutive_failures": self._breaker_consecutive_failures,
            "circuit_open_until": self._breaker_open_until_iso,
            "circuit_cooldown_remaining_s": round(self._breaker_cooldown_remaining_s(), 3),
            "last_success_at": self._last_success_at,
        }
        if self._last_error:
            row["last_error"] = dict(self._last_error)
        return row

    def unavailable(
        self,
        *,
        logger: logging.Logger,
        provider: str,
        target: str,
        text: str,
        reason: str,
        fallback: str,
    ) -> OutboundSendResult:
        key = self.make_idempotency_key(target, text)
        error = self._build_error(
            provider=provider,
            code="channel_unavailable",
            attempts=0,
            reason=reason,
            fallback=fallback,
            idempotency_key=key,
        )
        self._inc("send_fail_count")
        self._inc("fallback_count")
        self._record_error(error)
        self._log_failure(logger, error)
        return OutboundSendResult(ok=False, attempts=0, idempotency_key=key, error=error)

    async def deliver(
        self,
        *,
        logger: logging.Logger,
        provider: str,
        target: str,
        text: str,
        operation: Callable[[], Awaitable[None]],
        fallback: str,
        idempotency_key: str | None = None,
    ) -> OutboundSendResult:
        key = str(idempotency_key or self.make_idempotency_key(target, text))
        now_ts = time.monotonic()
        self._prune_recent(now_ts)
        if key in self._recent_sent:
            logger.info("Outbound deduplicado channel=%s provider=%s key=%s", self.channel, provider, key)
            self._inc("dedupe_hits")
            return OutboundSendResult(ok=True, attempts=0, idempotency_key=key)

        blocked = self._guard_circuit(
            logger=logger,
            provider=provider,
            target=target,
            text=text,
            fallback=fallback,
        )
        if blocked is not None:
            return blocked

        last_error: dict[str, Any] | None = None
        try:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    await asyncio.wait_for(operation(), timeout=self.timeout_s)
                    self._recent_sent[key] = time.monotonic()
                    self._inc("sent_ok")
                    self._last_success_at = self._now_iso()
                    self._on_delivery_success()
                    return OutboundSendResult(ok=True, attempts=attempt, idempotency_key=key)
                except asyncio.TimeoutError:
                    self._inc("timeout_count")
                    last_error = self._build_error(
                        provider=provider,
                        code="provider_timeout",
                        attempts=attempt,
                        reason=f"timeout>{self.timeout_s:.2f}s",
                        fallback=fallback,
                        idempotency_key=key,
                    )
                except Exception as exc:
                    last_error = self._build_error(
                        provider=provider,
                        code="provider_send_failed",
                        attempts=attempt,
                        reason=str(exc),
                        fallback=fallback,
                        idempotency_key=key,
                    )

                if attempt < self.max_attempts:
                    self._inc("retry_count")
                    delay = self.base_backoff_s * (2 ** (attempt - 1))
                    if delay > 0:
                        await self._sleep_fn(delay)

            if last_error is None:
                last_error = self._build_error(
                    provider=provider,
                    code="provider_send_failed",
                    attempts=self.max_attempts,
                    reason="erro desconhecido",
                    fallback=fallback,
                    idempotency_key=key,
                )
            self._inc("send_fail_count")
            self._inc("fallback_count")
            self._record_error(last_error)
            self._on_delivery_failure()
            self._log_failure(logger, last_error)
            return OutboundSendResult(
                ok=False,
                attempts=int(last_error.get("attempts", self.max_attempts)),
                idempotency_key=key,
                error=last_error,
            )
        finally:
            self._breaker_probe_in_flight = False
