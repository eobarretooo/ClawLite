from __future__ import annotations

import asyncio
import hashlib
import logging
import time
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
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.channel = str(channel or "").strip() or "unknown"
        self.timeout_s = max(0.1, float(timeout_s))
        self.max_attempts = max(1, min(int(max_attempts), 3))
        self.base_backoff_s = max(0.0, float(base_backoff_s))
        self.dedupe_ttl_s = max(1.0, float(dedupe_ttl_s))
        self.dedupe_max_entries = max(32, int(dedupe_max_entries))
        self._sleep_fn = sleep_fn
        self._recent_sent: dict[str, float] = {}

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
        return {
            "channel": self.channel,
            "provider": str(provider),
            "code": str(code),
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
            return OutboundSendResult(ok=True, attempts=0, idempotency_key=key)

        last_error: dict[str, Any] | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                await asyncio.wait_for(operation(), timeout=self.timeout_s)
                self._recent_sent[key] = time.monotonic()
                return OutboundSendResult(ok=True, attempts=attempt, idempotency_key=key)
            except asyncio.TimeoutError:
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
        self._log_failure(logger, last_error)
        return OutboundSendResult(
            ok=False,
            attempts=int(last_error.get("attempts", self.max_attempts)),
            idempotency_key=key,
            error=last_error,
        )
