from __future__ import annotations

import json
import time

import pytest

from clawlite.core.agent import _execute_local_tool
from clawlite.runtime import subagents as sub_mod


def test_subagent_runtime_spawn_and_complete(monkeypatch) -> None:
    sub_mod.reset_subagent_runtime_for_tests()
    runtime = sub_mod.get_subagent_runtime()

    captured: list[tuple[str, str]] = []
    runtime.set_notifier(lambda session_id, message: captured.append((session_id, message)))

    monkeypatch.setattr(
        sub_mod.SubagentRuntime,
        "_execute_subagent",
        staticmethod(lambda session_id, run_id, task: f"done:{task}:{run_id}:{session_id}"),
    )

    spawned = runtime.spawn(session_id="tg_123", task="gerar relatorio", label="relatorio")
    run_id = spawned["run_id"]
    assert spawned["status"] in {"running", "done"}

    timeout_at = time.time() + 1.0
    while time.time() < timeout_at:
        rows = runtime.list_runs(session_id="tg_123")
        if rows and rows[0]["status"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(0.01)

    rows = runtime.list_runs(session_id="tg_123")
    assert rows
    assert rows[0]["run_id"] == run_id
    assert rows[0]["status"] == "done"
    assert captured and captured[0][0] == "tg_123"

    sub_mod.reset_subagent_runtime_for_tests()


def test_execute_local_tool_subagents_dispatch(monkeypatch) -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.spawn_calls: list[dict[str, str]] = []
            self.cancel_session_calls: list[str] = []

        def spawn(self, *, session_id: str, task: str, label: str = "") -> dict[str, str]:
            self.spawn_calls.append({"session_id": session_id, "task": task, "label": label})
            return {"run_id": "abc12345", "status": "running", "label": label or "auto"}

        def list_runs(self, *, session_id: str | None = None, only_active: bool = False):
            return [{"run_id": "abc12345", "session_id": session_id, "status": "running", "only_active": only_active}]

        def cancel_run(self, run_id: str) -> bool:
            return run_id == "abc12345"

        def cancel_session(self, session_id: str) -> int:
            self.cancel_session_calls.append(session_id)
            return 1

    fake = FakeRuntime()
    monkeypatch.setattr(sub_mod, "get_subagent_runtime", lambda: fake)

    spawn_raw = _execute_local_tool(
        "spawn_subagent",
        {"task": "resolver incidente", "label": "incidente"},
        session_id="sl_canal",
    )
    spawn_payload = json.loads(spawn_raw)
    assert spawn_payload["ok"] is True
    assert spawn_payload["subagent"]["run_id"] == "abc12345"
    assert fake.spawn_calls and fake.spawn_calls[0]["session_id"] == "sl_canal"

    list_raw = _execute_local_tool("subagents_list", {"active_only": True}, session_id="sl_canal")
    list_payload = json.loads(list_raw)
    assert list_payload["ok"] is True
    assert list_payload["runs"][0]["session_id"] == "sl_canal"

    kill_raw = _execute_local_tool("subagents_kill", {}, session_id="sl_canal")
    kill_payload = json.loads(kill_raw)
    assert kill_payload["ok"] is True
    assert kill_payload["cancelled"] == 1
    assert fake.cancel_session_calls == ["sl_canal"]
