from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from clawlite.core.subagent import SubagentManager, SubagentRun
from clawlite.tools.agents import AgentsListTool
from clawlite.tools.base import ToolContext


class FakeProvider:
    def get_default_model(self) -> str:
        return "fake/agent-model"


class FakeTools:
    def schema(self) -> list[dict[str, object]]:
        return [
            {"name": "read", "description": "read file", "parameters": {}},
            {"name": "spawn", "description": "spawn agent", "parameters": {}},
            {"name": "agents_list", "description": "list agents", "parameters": {}},
        ]


class FakeMemory:
    def __init__(self, verdict) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, str]] = []

    def integration_policy(self, kind: str, *, session_id: str):
        self.calls.append((kind, session_id))
        return self.verdict


def test_agents_list_returns_primary_and_subagent_inventory(tmp_path) -> None:
    async def _scenario() -> None:
        manager = SubagentManager(state_path=tmp_path / "subagents", max_concurrent_runs=3, max_queued_runs=9, per_session_quota=4)
        manager._runs["run-active"] = SubagentRun(
            run_id="run-active",
            session_id="cli:a",
            task="inspect repo",
            status="running",
            started_at="2030-03-06T10:00:00+00:00",
            updated_at="2030-03-06T10:00:01+00:00",
            metadata={
                "target_session_id": "cli:a:subagent",
                "target_user_id": "u-a",
            },
        )
        manager._runs["run-retry"] = SubagentRun(
            run_id="run-retry",
            session_id="cli:b",
            task="retry deploy",
            status="interrupted",
            started_at="2030-03-06T10:00:00+00:00",
            updated_at="2030-03-06T10:00:02+00:00",
            metadata={
                "target_session_id": "cli:b:subagent",
                "target_user_id": "u-b",
                "resumable": True,
                "retry_budget_remaining": 1,
            },
        )
        manager._save_state()

        engine = SimpleNamespace(
            provider=FakeProvider(),
            tools=FakeTools(),
            max_iterations=24,
            max_tokens=4096,
            temperature=0.2,
            memory_window=18,
            reasoning_effort_default="medium",
        )
        memory = FakeMemory({"allowed": False, "reason": "memory_degraded"})
        tool = AgentsListTool(engine, manager, memory=memory)

        payload = json.loads(await tool.run({"limit": 10}, ToolContext(session_id="cli:owner")))

        assert payload["status"] == "ok"
        assert payload["scope"] == "global"
        assert payload["run_count"] == 2
        assert payload["maintenance"] == {
            "expired": 0,
            "orphaned_running": 0,
            "orphaned_queued": 0,
        }
        primary = [row for row in payload["agents"] if row["id"] == "primary"][0]
        delegated = [row for row in payload["agents"] if row["id"] == "subagent_manager"][0]
        assert primary["provider_model"] == "fake/agent-model"
        assert primary["tool_count"] == 3
        assert primary["max_iterations"] == 24
        assert delegated["spawn_allowed"] is False
        assert delegated["spawn_block_reason"] == "memory_degraded"
        assert delegated["status_counts"] == {
            "running": 1,
            "interrupted": 1,
        }
        assert delegated["resumable_subagents"] == 1
        assert set(delegated["active_sessions"]) == {"cli:a"}
        assert payload["runs"][0]["target_user_id"] in {"u-a", "u-b"}
        assert payload["session_inventory_count"] == 2
        assert {row["session_id"] for row in payload["session_inventory"]} == {"cli:a", "cli:b"}
        assert memory.calls == [("subagent", "cli:owner")]

    asyncio.run(_scenario())


def test_agents_list_filters_session_and_active_only(tmp_path) -> None:
    async def _scenario() -> None:
        manager = SubagentManager(state_path=tmp_path / "subagents", max_concurrent_runs=2)
        manager._runs["run-a"] = SubagentRun(
            run_id="run-a",
            session_id="cli:a",
            task="task a",
            status="running",
            started_at="2030-03-06T10:00:00+00:00",
            updated_at="2030-03-06T10:00:03+00:00",
            metadata={"target_session_id": "cli:a:subagent"},
        )
        manager._runs["run-b"] = SubagentRun(
            run_id="run-b",
            session_id="cli:a",
            task="task b",
            status="done",
            started_at="2030-03-06T10:00:00+00:00",
            finished_at="2030-03-06T10:00:04+00:00",
            updated_at="2030-03-06T10:00:04+00:00",
            metadata={"target_session_id": "cli:a:subagent:2"},
        )
        manager._runs["run-c"] = SubagentRun(
            run_id="run-c",
            session_id="cli:b",
            task="task c",
            status="queued",
            started_at="2030-03-06T10:00:00+00:00",
            updated_at="2030-03-06T10:00:01+00:00",
            metadata={"target_session_id": "cli:b:subagent"},
        )
        manager._save_state()

        engine = SimpleNamespace(
            provider=FakeProvider(),
            tools=FakeTools(),
            max_iterations=24,
            max_tokens=4096,
            temperature=0.2,
            memory_window=18,
            reasoning_effort_default="medium",
        )
        tool = AgentsListTool(engine, manager)

        payload = json.loads(
            await tool.run(
                {
                    "sessionId": "cli:a",
                    "activeOnly": True,
                    "includeRuns": False,
                    "limit": 5,
                },
                ToolContext(session_id="cli:owner"),
            )
        )

        assert payload["status"] == "ok"
        assert payload["scope"] == "session"
        assert payload["session_id"] == "cli:a"
        assert payload["active_only"] is True
        assert payload["run_count"] == 1
        assert payload["runs"] == []
        assert payload["session_inventory_count"] == 1
        assert payload["session_inventory"][0]["session_id"] == "cli:a"
        assert payload["session_inventory"][0]["run_count"] == 1
        delegated = [row for row in payload["agents"] if row["id"] == "subagent_manager"][0]
        assert delegated["active_subagents"] == 1
        assert delegated["queued_subagents"] == 0
        assert delegated["active_sessions"] == ["cli:a"]

    asyncio.run(_scenario())
