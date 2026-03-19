from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from clawlite.channels.inbound_text import sanitize_inbound_system_tags
from clawlite.core.injection_guard import scan_inbound
from clawlite.utils.logging import bind_event

InboundHandler = Callable[[str, str, str, dict[str, Any]], Awaitable[None]]


class _TokenBucketRateLimiter:
    """
    Per-key token bucket rate limiter.

    Default: 10 messages per 60 seconds per (channel, session_id) key.
    Thread/coroutine safe via monotonic time — no locks needed.
    """

    def __init__(self, *, rate: float = 10.0, per_s: float = 60.0) -> None:
        self._rate = max(1.0, float(rate))
        self._per_s = max(1.0, float(per_s))
        # key → (tokens, last_refill_monotonic)
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (self._rate, now))
        elapsed = now - last
        tokens = min(self._rate, tokens + elapsed * (self._rate / self._per_s))
        if tokens < 1.0:
            return False
        self._buckets[key] = (tokens - 1.0, now)
        return True

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


_CHANNEL_RATE_LIMITER = _TokenBucketRateLimiter(rate=10.0, per_s=60.0)


@dataclass(slots=True)
class ChannelHealth:
    running: bool
    last_error: str


@dataclass(slots=True, frozen=True)
class ChannelCapabilities:
    supports_progress: bool = True
    supports_tool_hints: bool = True
    supports_metadata: bool = True
    supports_retry: bool = True


class BaseChannel(ABC):
    def __init__(
        self,
        *,
        name: str,
        config: dict[str, Any],
        on_message: InboundHandler | None = None,
        capabilities: ChannelCapabilities | None = None,
    ) -> None:
        self.name = name
        self.config = config
        self.on_message = on_message
        self._capabilities = capabilities or ChannelCapabilities()
        self._running = False
        self._last_error = ""

    @property
    def running(self) -> bool:
        return self._running

    def health(self) -> ChannelHealth:
        return ChannelHealth(running=self._running, last_error=self._last_error)

    @property
    def capabilities(self) -> ChannelCapabilities:
        return self._capabilities

    async def emit(self, *, session_id: str, user_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        if self.on_message is None:
            return
        # Rate limit per channel+session before doing any work
        rl_key = f"{self.name}:{session_id}"
        if not _CHANNEL_RATE_LIMITER.allow(rl_key):
            bind_event("rate_limit", channel=self.name).warning(
                "message rate-limited session={} user={}", session_id, user_id
            )
            return
        # Ægishjálmr injection guard
        result = scan_inbound(text, source=self.name)
        if result.blocked:
            bind_event("injection_guard", channel=self.name).warning(
                "inbound message BLOCKED session={} threats={}", session_id, ",".join(result.threats)
            )
            return
        # Upstream: neutralize spoofed system-role markers ([System Message], System: prefix, etc.)
        clean_text = sanitize_inbound_system_tags(result.sanitized_text)
        if clean_text != result.sanitized_text:
            bind_event("system_tag_spoof", channel=self.name).warning(
                "spoofed system tags stripped session={} user={}", session_id, user_id
            )
            try:
                from clawlite.core.runestone import audit as _rs_audit
                _rs_audit(kind="system_tag_spoof", source=self.name, details={"session_id": session_id, "user_id": user_id})
            except Exception:
                pass
        await self.on_message(session_id, user_id, clean_text, metadata or {})

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        raise NotImplementedError


class PassiveChannel(BaseChannel):
    """Base channel for integrations not implemented yet in v2."""

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        del target, text, metadata
        raise RuntimeError(f"{self.name}_not_implemented")


async def cancel_task(task: asyncio.Task[Any] | None) -> None:
    if task is None:
        return
    if task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return
