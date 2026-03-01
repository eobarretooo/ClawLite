from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from clawlite.channels.manager import ChannelManager, manager as default_channel_manager
from clawlite.config.settings import load_config
from clawlite.core.heartbeat import AsyncHeartbeatLoop
from clawlite.runtime.conversation_cron import AsyncConversationCronScheduler

logger = logging.getLogger(__name__)


@dataclass
class AutonomyStatus:
    running: bool
    heartbeat_running: bool
    cron_running: bool
    active_channels: int


class AutonomyRuntime:
    """Orquestra canais + heartbeat + cron como um runtime único de autonomia."""

    def __init__(self, channel_manager: ChannelManager | None = None) -> None:
        self._manager = channel_manager or default_channel_manager
        self._heartbeat: AsyncHeartbeatLoop | None = None
        self._cron: AsyncConversationCronScheduler | None = None
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return

            cfg = load_config()
            gateway_cfg = cfg.get("gateway", {}) if isinstance(cfg.get("gateway"), dict) else {}
            hb_interval = int(gateway_cfg.get("heartbeat_interval_s", 1800))
            cron_poll_interval = float(gateway_cfg.get("cron_poll_interval_s", 5.0))

            loop = asyncio.get_running_loop()

            def _heartbeat_proactive_dispatch(message: str) -> None:
                async def _send() -> None:
                    await self._manager.broadcast_proactive(message, prefix="[heartbeat]")

                loop.call_soon_threadsafe(asyncio.create_task, _send())

            self._heartbeat = AsyncHeartbeatLoop(
                interval_s=hb_interval,
                proactive_callback=_heartbeat_proactive_dispatch,
            )
            self._cron = AsyncConversationCronScheduler(poll_interval_s=cron_poll_interval)

            await self._manager.start_all()
            await self._heartbeat.start()
            await self._cron.start()
            self._running = True
            logger.info("autonomy-runtime: started")

    async def stop(self) -> None:
        async with self._lock:
            if not self._running:
                return

            cron = self._cron
            heartbeat = self._heartbeat
            self._cron = None
            self._heartbeat = None

            if cron is not None:
                try:
                    await cron.stop()
                except Exception as exc:
                    logger.warning("autonomy-runtime: failed stopping cron: %s", exc)
            if heartbeat is not None:
                try:
                    await heartbeat.stop()
                except Exception as exc:
                    logger.warning("autonomy-runtime: failed stopping heartbeat: %s", exc)

            await self._manager.stop_all()
            self._running = False
            logger.info("autonomy-runtime: stopped")

    def status(self) -> AutonomyStatus:
        heartbeat_running = bool(self._heartbeat and getattr(self._heartbeat, "_task", None))
        cron_running = bool(self._cron and getattr(self._cron, "_task", None))
        return AutonomyStatus(
            running=self._running,
            heartbeat_running=heartbeat_running,
            cron_running=cron_running,
            active_channels=len(self._manager.active_channels),
        )


runtime = AutonomyRuntime()

