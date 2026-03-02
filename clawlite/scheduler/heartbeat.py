from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

TickHandler = Callable[[], Awaitable[str | None]]


class HeartbeatService:
    def __init__(self, interval_seconds: int = 1800) -> None:
        self.interval_seconds = max(5, int(interval_seconds))
        self._task: asyncio.Task[Any] | None = None
        self._running = False

    async def start(self, on_tick: TickHandler) -> None:
        if self._task is not None:
            return
        self._running = True

        async def _loop() -> None:
            while self._running:
                try:
                    await on_tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Heartbeat failures must not crash the background loop.
                    pass
                await asyncio.sleep(self.interval_seconds)

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception:
            # Ignore background exceptions during shutdown.
            pass
        self._task = None
