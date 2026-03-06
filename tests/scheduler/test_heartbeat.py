from __future__ import annotations

import asyncio
import json
from pathlib import Path

import clawlite.scheduler.heartbeat as heartbeat_module
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


def test_loads_legacy_flat_state_schema(tmp_path: Path) -> None:
    state_file = tmp_path / "heartbeat-state.json"
    state_file.write_text(
        json.dumps(
            {
                "version": 0,
                "last_tick_iso": "2026-01-01T00:00:00+00:00",
                "action": "run",
                "reason": "legacy_reason",
                "text": "legacy actionable",
                "ticks": 7,
            }
        ),
        encoding="utf-8",
    )

    hb = HeartbeatService(state_path=state_file)

    assert hb.last_decision.action == "run"
    assert hb.last_decision.reason == "legacy_reason"
    assert hb.last_decision.text == "legacy actionable"
    assert hb._state["last_action"] == "run"
    assert hb._state["last_reason"] == "legacy_reason"
    assert hb._state["last_check_iso"] == "2026-01-01T00:00:00+00:00"


def test_preserves_unknown_state_keys_on_save(tmp_path: Path) -> None:
    async def _scenario(state_file: Path) -> None:
        state_file.write_text(
            json.dumps(
                {
                    "last_decision": {"action": "skip", "reason": "not_started", "text": ""},
                    "external_key": {"keep": True},
                }
            ),
            encoding="utf-8",
        )

        async def _tick() -> HeartbeatDecision:
            return HeartbeatDecision(action="skip", reason="heartbeat_ok")

        hb = HeartbeatService(state_path=state_file)
        await hb.trigger_now(_tick)
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        assert payload["external_key"] == {"keep": True}

    asyncio.run(_scenario(tmp_path / "heartbeat-state.json"))


def test_heartbeat_ok_updates_check_state(tmp_path: Path) -> None:
    async def _scenario(state_file: Path) -> None:
        async def _tick() -> str:
            return "HEARTBEAT_OK all clear"

        hb = HeartbeatService(state_path=state_file)
        decision = await hb.trigger_now(_tick)
        payload = json.loads(state_file.read_text(encoding="utf-8"))

        assert decision.action == "skip"
        assert decision.reason == "heartbeat_ok"
        assert payload["last_action"] == "skip"
        assert payload["last_reason"] == "heartbeat_ok"
        assert payload["last_check_iso"]
        assert payload["last_ok_iso"] == payload["last_check_iso"]

    asyncio.run(_scenario(tmp_path / "heartbeat-state.json"))


def test_actionable_response_updates_check_state(tmp_path: Path) -> None:
    async def _scenario(state_file: Path) -> None:
        async def _tick() -> HeartbeatDecision:
            return HeartbeatDecision(
                action="run",
                reason="actionable_response",
                text="Deploy hotfix and notify operators immediately.",
            )

        hb = HeartbeatService(state_path=state_file, actionable_excerpt_max_chars=12)
        decision = await hb.trigger_now(_tick)
        payload = json.loads(state_file.read_text(encoding="utf-8"))

        assert decision.action == "run"
        assert payload["last_action"] == "run"
        assert payload["last_reason"] == "actionable_response"
        assert payload["last_actionable_iso"] == payload["last_check_iso"]
        assert payload["last_actionable_excerpt"] == "Deploy hotfi"

    asyncio.run(_scenario(tmp_path / "heartbeat-state.json"))


def test_save_state_atomic_replace_fail_soft(tmp_path: Path, monkeypatch) -> None:
    state_file = tmp_path / "heartbeat-state.json"
    state_file.write_text(json.dumps({"external": "original"}), encoding="utf-8")
    hb = HeartbeatService(state_path=state_file)
    hb._state["ticks"] = 42

    calls: list[tuple[str, str]] = []

    def _replace_fail(src: str, dst: str) -> None:
        calls.append((src, dst))
        raise OSError("replace failed")

    monkeypatch.setattr(heartbeat_module.os, "replace", _replace_fail)

    hb._save_state()

    assert calls
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["external"] == "original"
    leftovers = list(state_file.parent.glob(f".{state_file.name}.*.tmp"))
    assert leftovers == []


def test_execute_tick_state_mutation_waits_for_tick_lock(tmp_path: Path) -> None:
    async def _scenario(state_file: Path) -> None:
        hb = HeartbeatService(state_path=state_file)
        initial_ticks = int(hb._state.get("ticks", 0) or 0)

        await hb._tick_lock.acquire()

        async def _tick() -> HeartbeatDecision:
            return HeartbeatDecision(action="skip", reason="heartbeat_ok")

        task = asyncio.create_task(hb._execute_tick(_tick, trigger="now"))
        await asyncio.sleep(0.02)

        assert int(hb._state.get("ticks", 0) or 0) == initial_ticks
        assert hb._state.get("last_trigger", "") != "now"

        hb._tick_lock.release()
        decision = await task

        assert decision.reason == "heartbeat_ok"
        assert int(hb._state.get("ticks", 0) or 0) == initial_ticks + 1

    asyncio.run(_scenario(tmp_path / "heartbeat-state.json"))


def test_execute_tick_uses_async_state_save_wrapper(tmp_path: Path, monkeypatch) -> None:
    async def _scenario(state_file: Path) -> None:
        hb = HeartbeatService(state_path=state_file)
        calls: list[str] = []

        async def _save_state_async() -> None:
            calls.append("async")

        def _save_state_sync() -> None:
            calls.append("sync")
            raise AssertionError("_save_state should not be called directly from _execute_tick")

        monkeypatch.setattr(hb, "_save_state_async", _save_state_async)
        monkeypatch.setattr(hb, "_save_state", _save_state_sync)

        async def _tick() -> HeartbeatDecision:
            return HeartbeatDecision(action="skip", reason="heartbeat_ok")

        decision = await hb._execute_tick(_tick, trigger="now")

        assert decision.reason == "heartbeat_ok"
        assert calls == ["async"]

    asyncio.run(_scenario(tmp_path / "heartbeat-state.json"))


def test_heartbeat_loop_supervisor_recovers_from_outer_exceptions() -> None:
    async def _scenario() -> None:
        hb = HeartbeatService(interval_seconds=9999)
        beats: list[int] = []

        async def _tick() -> HeartbeatDecision:
            beats.append(1)
            return HeartbeatDecision(action="skip", reason="heartbeat_ok")

        original_next_trigger_source = hb._next_trigger_source
        calls = 0

        async def _flaky_next_trigger_source() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("loop source failure")
            return await original_next_trigger_source()

        hb._next_trigger_source = _flaky_next_trigger_source  # type: ignore[method-assign]
        hb.interval_seconds = 0.01

        await hb.start(_tick)
        await asyncio.sleep(0.25)
        await hb.stop()

        assert calls >= 1
        assert len(beats) >= 2

    asyncio.run(_scenario())


def test_heartbeat_start_restarts_when_previous_task_crashed() -> None:
    async def _scenario() -> None:
        hb = HeartbeatService(interval_seconds=60)

        async def _crash() -> None:
            raise RuntimeError("heartbeat_worker_crash")

        async def _tick() -> HeartbeatDecision:
            return HeartbeatDecision(action="skip", reason="heartbeat_ok")

        crashed_task = asyncio.create_task(_crash())
        try:
            await crashed_task
        except RuntimeError:
            pass

        hb._task = crashed_task
        hb._running = True

        crashed_status = hb.status()
        assert crashed_status["running"] is False
        assert crashed_status["worker_state"] == "failed"
        assert "heartbeat_worker_crash" in crashed_status["last_error"]

        await hb.start(_tick)
        replacement_task = hb._task

        assert replacement_task is not None
        assert replacement_task is not crashed_task
        assert not replacement_task.done()
        assert hb.status()["worker_state"] == "running"

        await hb.stop()

    asyncio.run(_scenario())
