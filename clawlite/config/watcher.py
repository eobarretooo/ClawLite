from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable

from clawlite.config.loader import load_config
from clawlite.config.schema import AppConfig

logger = logging.getLogger(__name__)

_DEBOUNCE_S = 0.5


class ConfigWatcher:
    """Watches a config file for changes and calls a callback with the new config.

    Opt-in: only active when ``watch_interval_s > 0`` in the config (checked
    by the caller). Debounced by 500 ms to avoid rapid-fire reloads on editors
    that write files in multiple steps.
    """

    def __init__(
        self,
        path: Path,
        callback: Callable[[AppConfig], None],
        *,
        debounce_s: float = _DEBOUNCE_S,
    ) -> None:
        self._path = path
        self._callback = callback
        self._debounce_s = max(0.0, debounce_s)
        self._task: asyncio.Task | None = None
        self._current_config: AppConfig | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._watch_loop(), name="config-watcher")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _watch_loop(self) -> None:
        try:
            from watchfiles import awatch  # type: ignore
        except ImportError:
            logger.warning("watchfiles not installed — config hot-reload disabled")
            return

        logger.info("ConfigWatcher: watching %s", self._path)
        async for _ in awatch(str(self._path)):
            await asyncio.sleep(self._debounce_s)
            try:
                new_config = load_config(self._path)
            except Exception as exc:
                logger.warning("ConfigWatcher: reload failed (%s), keeping old config", exc)
                # Emit a bus event if available (best-effort, no hard dep on bus)
                try:
                    from clawlite.bus.events import InboundEvent
                    _bus = _get_bus()
                    if _bus is not None:
                        await _bus.publish_inbound(InboundEvent(
                            channel="system",
                            session_id="config-watcher",
                            user_id="system",
                            text="config.reload_failed",
                            metadata={"error": str(exc)},
                        ))
                except Exception:
                    pass
                continue
            self._current_config = new_config
            logger.info("ConfigWatcher: config reloaded from %s", self._path)
            try:
                self._callback(new_config)
            except Exception as exc:
                logger.warning("ConfigWatcher: callback raised %s", exc)


def _get_bus():
    """Return the global bus if available (avoids circular import)."""
    try:
        from clawlite.bus import get_bus
        return get_bus()
    except Exception:
        return None
