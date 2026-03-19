from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from clawlite.core.injection_guard import scan_inbound
from clawlite.utils.logger import bind_event

InboundHandler = Callable[[str, str, str, dict[str, Any]], Awaitable[None]]


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
        result = scan_inbound(text, source=self.name)
        if result.blocked:
            bind_event("injection_guard", channel=self.name).warning(
                "inbound message BLOCKED session={} threats={}", session_id, ",".join(result.threats)
            )
            return
        await self.on_message(session_id, user_id, result.sanitized_text, metadata or {})

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
