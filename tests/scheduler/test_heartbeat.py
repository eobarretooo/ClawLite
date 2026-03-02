from __future__ import annotations

import asyncio

from clawlite.scheduler.heartbeat import HeartbeatService


def test_heartbeat_service_ticks() -> None:
    async def _scenario() -> None:
        beats: list[int] = []

        async def _tick() -> str:
            beats.append(1)
            return "ok"

        hb = HeartbeatService(interval_seconds=1)
        await hb.start(_tick)
        await asyncio.sleep(1.2)
        await hb.stop()
        assert beats

    asyncio.run(_scenario())


def test_heartbeat_service_survives_tick_errors() -> None:
    async def _scenario() -> None:
        beats: list[int] = []

        async def _tick() -> str:
            beats.append(1)
            if len(beats) == 1:
                raise RuntimeError("transient failure")
            return "ok"

        hb = HeartbeatService(interval_seconds=5)
        hb.interval_seconds = 0.05
        await hb.start(_tick)
        await asyncio.sleep(0.2)
        await hb.stop()
        assert len(beats) >= 2

    asyncio.run(_scenario())
