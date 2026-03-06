from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from clawlite.core.subagent import SubagentManager
from clawlite.session.store import SessionStore
from clawlite.tools.base import ToolContext
from clawlite.tools.sessions import (
    SessionStatusTool,
    SessionsHistoryTool,
    SessionsListTool,
    SessionsSendTool,
    SessionsSpawnTool,
    SubagentsTool,
)


def test_sessions_list(tmp_path) -> None:
    async def _scenario() -> None:
        sessions = SessionStore(root=tmp_path / "sessions")
        sessions.append("cli:a", "user", "hello from alpha")
        sessions.append("cli:a", "assistant", "done alpha")
        sessions.append("cli:b", "user", "hello from beta")

        tool = SessionsListTool(sessions)
        payload = json.loads(await tool.run({"limit": 10}, ToolContext(session_id="cli:a")))

        assert payload["status"] == "ok"
        assert payload["count"] == 2
        session_ids = {row["session_id"] for row in payload["sessions"]}
        assert session_ids == {"cli:a", "cli:b"}
        row_a = [row for row in payload["sessions"] if row["session_id"] == "cli:a"][0]
        assert row_a["last_message"]["role"] == "assistant"
        assert "done alpha" in row_a["last_message"]["preview"]

    asyncio.run(_scenario())


def test_sessions_history_include_and_exclude_tool_messages(tmp_path) -> None:
    async def _scenario() -> None:
        sessions = SessionStore(root=tmp_path / "sessions")
        sessions.append("cli:h", "user", "u1")
        sessions.append("cli:h", "tool", "t1")
        sessions.append("cli:h", "assistant", "a1")

        tool = SessionsHistoryTool(sessions)

        excluded = json.loads(
            await tool.run(
                {
                    "sessionKey": "cli:h",
                    "limit": 10,
                    "include_tools": False,
                },
                ToolContext(session_id="cli:caller"),
            )
        )
        assert excluded["status"] == "ok"
        assert excluded["count"] == 2
        assert [row["role"] for row in excluded["messages"]] == ["user", "assistant"]

        included = json.loads(
            await tool.run(
                {
                    "sessionId": "cli:h",
                    "limit": 10,
                    "includeTools": True,
                },
                ToolContext(session_id="cli:caller"),
            )
        )
        assert included["status"] == "ok"
        assert included["count"] == 3
        assert [row["role"] for row in included["messages"]] == ["user", "tool", "assistant"]

    asyncio.run(_scenario())


def test_sessions_send_success_and_same_session_failure() -> None:
    async def _scenario() -> None:
        calls: list[tuple[str, str]] = []

        async def _runner(session_id: str, task: str):
            calls.append((session_id, task))
            return SimpleNamespace(text=f"ok:{task}", model="fake/model")

        tool = SessionsSendTool(_runner)

        success = json.loads(
            await tool.run(
                {
                    "sessionId": "cli:target",
                    "message": "ping",
                },
                ToolContext(session_id="cli:caller"),
            )
        )
        assert success == {
            "status": "ok",
            "session_id": "cli:target",
            "text": "ok:ping",
            "model": "fake/model",
        }
        assert calls == [("cli:target", "ping")]

        same = json.loads(
            await tool.run(
                {
                    "session_id": "cli:caller",
                    "message": "ping",
                },
                ToolContext(session_id="cli:caller"),
            )
        )
        assert same["status"] == "failed"
        assert same["error"] == "same_session_not_allowed"

    asyncio.run(_scenario())


def test_sessions_send_timeout_returns_deterministic_failed_json() -> None:
    async def _scenario() -> None:
        gate = asyncio.Event()

        async def _runner(_session_id: str, _task: str):
            await gate.wait()
            return SimpleNamespace(text="never", model="never")

        tool = SessionsSendTool(_runner)
        timeout_payload = json.loads(
            await tool.run(
                {
                    "session_id": "cli:target",
                    "message": "ping",
                    "timeout_s": 0.01,
                },
                ToolContext(session_id="cli:caller"),
            )
        )
        assert timeout_payload == {
            "status": "failed",
            "session_id": "cli:target",
            "error": "runner_timeout",
        }

    asyncio.run(_scenario())


def test_sessions_spawn_success_and_subagents_list_kill(tmp_path) -> None:
    async def _scenario() -> None:
        gate = asyncio.Event()

        async def _runner(session_id: str, task: str):
            await gate.wait()
            return SimpleNamespace(text=f"{session_id}:{task}", model="spawn/model")

        manager = SubagentManager(state_path=tmp_path / "subagents", max_concurrent_runs=1, max_queued_runs=8, per_session_quota=4)
        spawn_tool = SessionsSpawnTool(manager, _runner)
        subagents_tool = SubagentsTool(manager)

        spawned = json.loads(
            await spawn_tool.run(
                {"task": "analyze task"},
                ToolContext(session_id="cli:owner"),
            )
        )
        assert spawned["status"] == "ok"
        assert spawned["session_id"] == "cli:owner"
        assert spawned["target_session_id"] == "cli:owner:subagent"
        run_id = spawned["run_id"]

        listed = json.loads(await subagents_tool.run({"action": "list"}, ToolContext(session_id="cli:owner")))
        assert listed["status"] == "ok"
        assert listed["action"] == "list"
        assert listed["count"] >= 1
        assert any(row["run_id"] == run_id for row in listed["runs"])

        killed = json.loads(
            await subagents_tool.run(
                {"action": "kill", "run_id": run_id},
                ToolContext(session_id="cli:owner"),
            )
        )
        assert killed["action"] == "kill"
        assert killed["run_id"] == run_id
        assert killed["cancelled"] is True

        gate.set()
        await asyncio.sleep(0)

    asyncio.run(_scenario())


def test_session_status_fields(tmp_path) -> None:
    async def _scenario() -> None:
        sessions = SessionStore(root=tmp_path / "sessions")
        sessions.append("cli:status", "user", "hello")
        sessions.append("cli:status", "assistant", "world")

        manager = SubagentManager(state_path=tmp_path / "subagents")
        tool = SessionStatusTool(sessions, manager)
        payload = json.loads(await tool.run({}, ToolContext(session_id="cli:status")))

        assert payload["status"] == "ok"
        assert payload["session_id"] == "cli:status"
        assert payload["exists"] is True
        assert payload["message_count"] == 2
        assert payload["last_message"]["role"] == "assistant"
        assert payload["active_subagents"] == 0

    asyncio.run(_scenario())
