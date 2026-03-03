from __future__ import annotations

import asyncio
import json
from pathlib import Path

from clawlite.scheduler.heartbeat import HeartbeatDecision, HeartbeatService


def test_heartbeat_service_ticks_and_persists_state(tmp_path: Path) -> None:
    async def _scenario(state_file: Path) -> None:
        beats: list[HeartbeatDecision] = []

        async def _tick() -> HeartbeatDecision:
            decision = HeartbeatDecision(action="run", reason="task_pending", text="alert")
            beats.append(decision)
            return decision

        hb = HeartbeatService(interval_seconds=5, state_path=state_file)
        hb.interval_seconds = 0.05
        await hb.start(_tick)
        await asyncio.sleep(0.2)
        await hb.stop()
        assert beats

        payload = json.loads(state_file.read_text(encoding="utf-8"))
        assert payload["last_decision"]["action"] == "run"
        assert payload["last_decision"]["reason"] == "task_pending"
        assert int(payload["run_count"]) >= 1
        assert payload["last_run_iso"]
        assert payload["last_trigger"] in {"startup", "interval", "now"}

    asyncio.run(_scenario(tmp_path / "heartbeat-state.json"))


def test_heartbeat_service_survives_tick_errors() -> None:
    async def _scenario() -> None:
        beats: list[int] = []

        async def _tick() -> HeartbeatDecision:
            beats.append(1)
            if len(beats) == 1:
                raise RuntimeError("transient failure")
            return HeartbeatDecision(action="skip", reason="heartbeat_ok")

        hb = HeartbeatService(interval_seconds=5)
        hb.interval_seconds = 0.05
        await hb.start(_tick)
        await asyncio.sleep(0.2)
        await hb.stop()
        assert len(beats) >= 2
        assert hb.last_decision.action == "skip"

    asyncio.run(_scenario())


def test_heartbeat_service_trigger_now() -> None:
    async def _scenario() -> None:
        beats: list[str] = []

        async def _tick() -> dict[str, str]:
            beats.append("tick")
            return {"action": "skip", "reason": "manual_check"}

        hb = HeartbeatService(interval_seconds=9999)
        await hb.start(_tick)
        await asyncio.sleep(0.05)
        before = len(beats)
        decision = await hb.trigger_now(_tick)
        await hb.stop()

        assert decision.action == "skip"
        assert decision.reason == "manual_check"
        assert len(beats) == before + 1

    asyncio.run(_scenario())


def test_heartbeat_ok_token_semantics() -> None:
    assert HeartbeatDecision.from_result("HEARTBEAT_OK").action == "skip"
    assert HeartbeatDecision.from_result("HEARTBEAT_OK all good").action == "skip"
    assert HeartbeatDecision.from_result("all good HEARTBEAT_OK").action == "skip"
    assert HeartbeatDecision.from_result("prefix HEARTBEAT_OK suffix").action == "run"


def test_next_trigger_source_handles_asyncio_timeout(monkeypatch) -> None:
    async def _scenario() -> None:
        hb = HeartbeatService(interval_seconds=5)
        hb.interval_seconds = 0.01

        async def _raise_timeout(awaitable, *_args, **_kwargs):
            awaitable.close()
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", _raise_timeout)
        trigger = await hb._next_trigger_source()
        assert trigger == "interval"

    asyncio.run(_scenario())


def test_next_trigger_source_handles_builtin_timeout(monkeypatch) -> None:
    async def _scenario() -> None:
        hb = HeartbeatService(interval_seconds=5)
        hb.interval_seconds = 0.01

        async def _raise_timeout(awaitable, *_args, **_kwargs):
            awaitable.close()
            raise TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", _raise_timeout)
        trigger = await hb._next_trigger_source()
        assert trigger == "interval"

    asyncio.run(_scenario())


def test_heartbeat_save_transient_failure_retries_and_service_continues(tmp_path: Path, monkeypatch) -> None:
    async def _scenario(state_file: Path) -> None:
        hb = HeartbeatService(interval_seconds=5, state_path=state_file)
        hb.interval_seconds = 0.03
        tick_count = 0
        reached = asyncio.Event()

        async def _tick() -> HeartbeatDecision:
            nonlocal tick_count
            tick_count += 1
            if tick_count >= 2:
                reached.set()
            return HeartbeatDecision(action="skip", reason="heartbeat_ok")

        original_replace = Path.replace
        calls = {"count": 0}

        def _flaky_replace(self: Path, target: Path) -> Path:
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("replace failed once")
            return original_replace(self, target)

        monkeypatch.setattr(Path, "replace", _flaky_replace)

        await hb.start(_tick)
        await asyncio.wait_for(reached.wait(), timeout=1.0)
        await hb.stop()

        status = hb.status()
        assert tick_count >= 2
        assert status["state_save_retries"] >= 1
        assert status["state_save_failures"] >= 1
        assert status["state_save_success"] >= 1
        assert status["running"] is False
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        assert int(payload["ticks"]) >= 1

    asyncio.run(_scenario(tmp_path / "heartbeat-state.json"))


def test_heartbeat_status_trigger_reason_and_consecutive_error_behavior(tmp_path: Path) -> None:
    async def _scenario(state_file: Path) -> None:
        hb = HeartbeatService(interval_seconds=5, state_path=state_file)
        hb.interval_seconds = 0.04
        calls = 0
        recovered = asyncio.Event()

        async def _tick() -> HeartbeatDecision:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("first failure")
            if calls >= 2:
                recovered.set()
            return HeartbeatDecision(action="skip", reason="heartbeat_ok")

        await hb.start(_tick)
        await asyncio.wait_for(recovered.wait(), timeout=1.0)
        decision = await hb.trigger_now(_tick)
        await hb.stop()

        status = hb.status()
        assert decision.reason == "heartbeat_ok"
        assert status["trigger_counts"]["startup"] >= 1
        assert status["trigger_counts"]["interval"] >= 1
        assert status["trigger_counts"]["now"] >= 1
        assert status["reason_counts"]["tick_error"] >= 1
        assert status["reason_counts"]["heartbeat_ok"] >= 2
        assert status["consecutive_error_count"] == 0

    asyncio.run(_scenario(tmp_path / "heartbeat-status.json"))
