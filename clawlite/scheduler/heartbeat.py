from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger

from clawlite.utils.logging import bind_event, setup_logging

TickHandler = Callable[[], Awaitable[str | None]]

setup_logging()


class HeartbeatService:
    def __init__(self, interval_seconds: int = 1800) -> None:
        self.interval_seconds = max(5, int(interval_seconds))
        self._task: asyncio.Task[Any] | None = None
        self._running = False

    async def start(self, on_tick: TickHandler) -> None:
        if self._task is not None:
            return
        self._running = True
        bind_event("heartbeat.lifecycle").info("heartbeat started interval_seconds={}", self.interval_seconds)

        async def _loop() -> None:
            while self._running:
                try:
                    bind_event("heartbeat.tick").debug("heartbeat tick")
                    result = await on_tick()
                    if result is None or not str(result).strip() or str(result).strip().lower().startswith("skip"):
                        bind_event("heartbeat.tick").debug("heartbeat skip")
                    else:
                        bind_event("heartbeat.tick").info("heartbeat run")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # Heartbeat failures must not crash the background loop.
                    bind_event("heartbeat.tick").error("heartbeat error={}", exc)
                await asyncio.sleep(self.interval_seconds)

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        bind_event("heartbeat.lifecycle").info("heartbeat stopping")
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            # Ignore background exceptions during shutdown.
            bind_event("heartbeat.lifecycle").error("heartbeat stop error={}", exc)
        self._task = None
        bind_event("heartbeat.lifecycle").info("heartbeat stopped")
