from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from clawlite.core.subagent import SubagentManager, SubagentRun
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


def test_sessions_send_applies_continuation_context_from_memory() -> None:
    async def _scenario() -> None:
        calls: list[tuple[str, str]] = []

        class MemoryStub:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def retrieve(
                self,
                query: str,
                *,
                limit: int = 5,
                method: str = "rag",
                user_id: str = "",
                session_id: str = "",
                include_shared: bool = False,
            ) -> dict[str, object]:
                self.calls.append(
                    {
                        "query": query,
                        "limit": limit,
                        "method": method,
                        "user_id": user_id,
                        "session_id": session_id,
                        "include_shared": include_shared,
                    }
                )
                return {
                    "status": "ok",
                    "episodic_digest": {
                        "session_id": session_id,
                        "count": 2,
                        "summary": f"current:{session_id} -> blocker triaged",
                    },
                }

        async def _runner(session_id: str, task: str):
            calls.append((session_id, task))
            return SimpleNamespace(text="ok:contextualized", model="fake/model")

        memory = MemoryStub()
        tool = SessionsSendTool(_runner, memory=memory)
        payload = json.loads(
            await tool.run(
                {
                    "sessionId": "cli:target",
                    "message": "ping",
                },
                ToolContext(session_id="cli:caller", user_id="u-1"),
            )
        )

        assert payload["status"] == "ok"
        assert payload["continuation_context_applied"] is True
        assert payload["continuation_digest_summary"] == "current:cli:target -> blocker triaged"
        assert payload["continuation_digest_session_id"] == "cli:target"
        assert payload["continuation_digest_count"] == 2
        assert memory.calls == [
            {
                "query": "ping",
                "limit": 3,
                "method": "rag",
                "user_id": "u-1",
                "session_id": "cli:target",
                "include_shared": True,
            }
        ]
        assert calls == [
            (
                "cli:target",
                "[Continuation Context]\n"
                "Session: cli:target\n"
                "Summary: current:cli:target -> blocker triaged\n\n"
                "[Task]\n"
                "ping",
            )
        ]

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
        matching = [row for row in listed["runs"] if row["run_id"] == run_id]
        assert matching
        assert matching[0]["target_session_id"] == "cli:owner:subagent"

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


def test_sessions_spawn_applies_continuation_context_and_persists_metadata(tmp_path) -> None:
    async def _scenario() -> None:
        calls: list[tuple[str, str]] = []

        class MemoryStub:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def retrieve(
                self,
                query: str,
                *,
                limit: int = 5,
                method: str = "rag",
                user_id: str = "",
                session_id: str = "",
                include_shared: bool = False,
            ) -> dict[str, object]:
                self.calls.append(
                    {
                        "query": query,
                        "limit": limit,
                        "method": method,
                        "user_id": user_id,
                        "session_id": session_id,
                        "include_shared": include_shared,
                    }
                )
                return {
                    "status": "ok",
                    "episodic_digest": {
                        "session_id": session_id,
                        "count": 1,
                        "summary": f"current:{session_id} -> blocker triaged",
                    },
                }

        async def _runner(session_id: str, task: str):
            calls.append((session_id, task))
            return SimpleNamespace(text=f"{session_id}:{task}", model="spawn/model")

        memory = MemoryStub()
        manager = SubagentManager(state_path=tmp_path / "subagents", max_concurrent_runs=1, max_queued_runs=8, per_session_quota=4)
        spawn_tool = SessionsSpawnTool(manager, _runner, memory=memory)

        payload = json.loads(
            await spawn_tool.run(
                {"task": "delegate task"},
                ToolContext(session_id="cli:owner", user_id="u-1"),
            )
        )
        await asyncio.sleep(0)

        assert payload["status"] == "ok"
        assert payload["target_session_id"] == "cli:owner:subagent"
        assert payload["continuation_context_applied"] is True
        assert payload["continuation_digest_summary"] == "current:cli:owner:subagent -> blocker triaged"
        assert payload["continuation_digest_session_id"] == "cli:owner:subagent"
        assert payload["continuation_digest_count"] == 1
        assert memory.calls == [
            {
                "query": "delegate task",
                "limit": 3,
                "method": "rag",
                "user_id": "u-1",
                "session_id": "cli:owner:subagent",
                "include_shared": True,
            }
        ]
        assert calls == [
            (
                "cli:owner:subagent",
                "[Continuation Context]\n"
                "Session: cli:owner:subagent\n"
                "Summary: current:cli:owner:subagent -> blocker triaged\n\n"
                "[Task]\n"
                "delegate task",
            )
        ]
        runs = manager.list_runs(session_id="cli:owner")
        assert runs
        assert runs[0].task == "delegate task"
        assert runs[0].metadata["continuation_context_applied"] is True
        assert runs[0].metadata["continuation_digest_summary"] == "current:cli:owner:subagent -> blocker triaged"
        assert runs[0].metadata["continuation_digest_session_id"] == "cli:owner:subagent"
        assert runs[0].metadata["continuation_digest_count"] == 1

    asyncio.run(_scenario())


def test_sessions_spawn_applies_explicit_working_memory_share_scope(tmp_path) -> None:
    async def _scenario() -> None:
        class MemoryStub:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def set_working_memory_share_scope(self, session_id: str, share_scope: str) -> dict[str, str]:
                self.calls.append((session_id, share_scope))
                return {"session_id": session_id, "share_scope": share_scope}

        async def _runner(session_id: str, task: str):
            return SimpleNamespace(text=f"{session_id}:{task}", model="spawn/model")

        memory = MemoryStub()
        manager = SubagentManager(state_path=tmp_path / "subagents", max_concurrent_runs=1, max_queued_runs=8, per_session_quota=4)
        spawn_tool = SessionsSpawnTool(manager, _runner, memory=memory)

        spawned = json.loads(
            await spawn_tool.run(
                {"task": "delegate task", "share_scope": "family"},
                ToolContext(session_id="cli:owner", user_id="u-1"),
            )
        )

        assert spawned["status"] == "ok"
        assert spawned["target_session_id"] == "cli:owner:subagent"
        assert spawned["share_scope"] == "family"
        assert memory.calls == [("cli:owner:subagent", "family")]
        runs = manager.list_runs(session_id="cli:owner")
        assert runs
        assert runs[0].metadata["target_session_id"] == "cli:owner:subagent"
        assert runs[0].metadata["target_user_id"] == "u-1"
        assert runs[0].metadata["share_scope"] == "family"

    asyncio.run(_scenario())


def test_sessions_spawn_fails_closed_when_share_scope_is_requested_without_memory_support(tmp_path) -> None:
    async def _scenario() -> None:
        async def _runner(session_id: str, task: str):
            return SimpleNamespace(text=f"{session_id}:{task}", model="spawn/model")

        manager = SubagentManager(state_path=tmp_path / "subagents", max_concurrent_runs=1, max_queued_runs=8, per_session_quota=4)
        spawn_tool = SessionsSpawnTool(manager, _runner)

        payload = json.loads(
            await spawn_tool.run(
                {"task": "delegate task", "share_scope": "family"},
                ToolContext(session_id="cli:owner"),
            )
        )

        assert payload["status"] == "failed"
        assert payload["error"] == "share_scope_unsupported"

    asyncio.run(_scenario())


def test_subagents_list_and_sweep_surface_lifecycle_metadata(tmp_path) -> None:
    async def _scenario() -> None:
        sessions = SessionStore(root=tmp_path / "sessions")
        manager = SubagentManager(state_path=tmp_path / "subagents", zombie_grace_seconds=0.0)
        stale_run = SubagentRun(
            run_id="run-zombie",
            session_id="cli:owner",
            task="retry task",
            status="queued",
            updated_at="2026-03-05T10:00:00+00:00",
            queued_at="2026-03-05T10:00:00+00:00",
            metadata={
                "target_session_id": "cli:owner:subagent",
                "resume_attempts": 1,
                "resume_attempts_max": 3,
                "retry_budget_remaining": 2,
                "expires_at": "2030-03-06T10:05:00+00:00",
                "resumable": False,
            },
        )
        manager._runs[stale_run.run_id] = stale_run
        manager._save_state()

        subagents_tool = SubagentsTool(manager)
        listed = json.loads(await subagents_tool.run({"action": "list"}, ToolContext(session_id="cli:owner")))
        assert listed["status"] == "ok"
        assert listed["maintenance"]["orphaned_queued"] == 1
        assert listed["count"] == 1
        assert listed["runs"][0]["run_id"] == "run-zombie"
        assert listed["runs"][0]["status"] == "interrupted"
        assert listed["runs"][0]["resumable"] is True
        assert listed["runs"][0]["resume_attempts"] == 1
        assert listed["runs"][0]["resume_attempts_max"] == 3
        assert listed["runs"][0]["retry_budget_remaining"] == 2
        assert listed["runs"][0]["last_status_reason"] == "orphaned_queue_entry"

        swept = json.loads(await subagents_tool.run({"action": "sweep"}, ToolContext(session_id="cli:owner")))
        assert swept["status"] == "ok"
        assert swept["action"] == "sweep"
        assert swept["maintenance"] == {
            "expired": 0,
            "orphaned_running": 0,
            "orphaned_queued": 0,
        }

        del sessions

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
        assert payload["subagent_counts"] == {}
        assert payload["resumable_subagents"] == 0
        assert payload["exhausted_retry_budget"] == 0
        assert payload["maintenance"] == {
            "expired": 0,
            "orphaned_running": 0,
            "orphaned_queued": 0,
        }

    asyncio.run(_scenario())


def test_session_status_sweeps_expired_subagents_and_reports_counts(tmp_path) -> None:
    async def _scenario() -> None:
        sessions = SessionStore(root=tmp_path / "sessions")
        sessions.append("cli:status", "user", "hello")
        manager = SubagentManager(
            state_path=tmp_path / "subagents",
            max_concurrent_runs=1,
            max_resume_attempts=0,
            run_ttl_seconds=0.01,
            zombie_grace_seconds=0.0,
        )
        blocker = asyncio.Event()

        async def _slow_runner(_session_id: str, task: str):
            await blocker.wait()
            return f"done:{task}"

        await manager.spawn(session_id="cli:status", task="long task", runner=_slow_runner)
        await asyncio.sleep(0.02)

        tool = SessionStatusTool(sessions, manager)
        payload = json.loads(await tool.run({}, ToolContext(session_id="cli:status")))
        await asyncio.sleep(0)

        assert payload["status"] == "ok"
        assert payload["active_subagents"] == 0
        assert payload["subagent_counts"]["expired"] == 1
        assert payload["resumable_subagents"] == 0
        assert payload["exhausted_retry_budget"] == 1
        assert payload["maintenance"]["expired"] == 1

    asyncio.run(_scenario())
