from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any

import clawlite.core.engine as engine_module
from clawlite.config.schema import ToolSafetyPolicyConfig
from clawlite.core.engine import AgentEngine, LoopDetectionSettings, ProviderResult, ToolCall, TurnBudget
from clawlite.core.memory import MemoryRecord
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry
from clawlite.utils.logging import bind_event


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return ProviderResult(
                text="tool please",
                tool_calls=[ToolCall(name="echo", arguments={"text": "hello"})],
                model="fake/model",
            )
        return ProviderResult(text="final answer", tool_calls=[], model="fake/model")


@dataclass
class FakeTools:
    async def execute(self, name, arguments, *, session_id: str, channel: str = "", user_id: str = "") -> str:
        return f"{name}:{arguments.get('text', '')}:{session_id}"

    def schema(self):
        return [{"name": "echo", "description": "echo text", "arguments": {"text": "string"}}]


class FakeProviderWithMessageCapture:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        self.calls += 1
        self.snapshots.append(messages)
        if self.calls == 1:
            return ProviderResult(
                text="need tools",
                tool_calls=[
                    ToolCall(name="echo", arguments={"text": "one"}),
                    ToolCall(name="echo", arguments={"text": "two"}),
                ],
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class FakeProviderWithSamplingCapture:
    def __init__(self) -> None:
        self.last_max_tokens: int | None = None
        self.last_temperature: float | None = None

    async def complete(self, *, messages, tools, max_tokens=None, temperature=None):
        self.last_max_tokens = max_tokens
        self.last_temperature = temperature
        return ProviderResult(text="ok", tool_calls=[], model="fake/model")


class FakePromptCaptureProvider:
    def __init__(self) -> None:
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.snapshots.append(messages)
        return ProviderResult(text="ok", tool_calls=[], model="fake/model")


class SessionStoreCapture:
    def __init__(self) -> None:
        self.last_limit: int | None = None

    def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        self.last_limit = limit
        return []

    def append(self, session_id: str, role: str, content: str) -> None:
        return None


class FakeMemory:
    def __init__(self, rows: list[MemoryRecord] | None = None) -> None:
        self.rows = rows or []

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        del query
        return self.rows[:limit]

    def consolidate(self, messages, *, source: str = "session"):
        del messages, source
        return None


class FakePlannerMemory:
    def __init__(
        self,
        routes: dict[str, list[MemoryRecord]] | None = None,
        recovered: list[str] | None = None,
        recover_error: Exception | None = None,
    ) -> None:
        self.routes = routes or {}
        self.recovered = recovered or []
        self.recover_error = recover_error
        self.search_calls: list[str] = []
        self.recovery_calls: list[tuple[str, int]] = []

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        del limit
        self.search_calls.append(query)
        return self.routes.get(query, [])

    def consolidate(self, messages, *, source: str = "session"):
        del messages, source
        return None

    def recover_session_context(self, session_id: str, *, limit: int = 4) -> list[str]:
        self.recovery_calls.append((session_id, limit))
        if self.recover_error is not None:
            raise self.recover_error
        return self.recovered[:limit]


class FakeProviderWithReasoningCapture:
    def __init__(self) -> None:
        self.last_reasoning_effort: str | None = None

    async def complete(self, *, messages, tools, reasoning_effort=None):
        self.last_reasoning_effort = reasoning_effort
        return ProviderResult(text="ok", tool_calls=[], model="fake/model")


class FakeLongToolProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        self.calls += 1
        self.snapshots.append(messages)
        if self.calls == 1:
            return ProviderResult(
                text="calling tool",
                tool_calls=[ToolCall(name="echo", arguments={"text": ""})],
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class FakeBurstToolProvider:
    async def complete(self, *, messages, tools):
        return ProviderResult(
            text="needs many tools",
            tool_calls=[
                ToolCall(name="echo", arguments={"text": "one"}),
                ToolCall(name="echo", arguments={"text": "two"}),
            ],
            model="fake/model",
        )


class FakeLoopingToolProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, messages, tools):
        self.calls += 1
        return ProviderResult(
            text="keep trying",
            tool_calls=[ToolCall(name="echo", arguments={"text": "same"})],
            model="fake/model",
        )


class FakeNeverCalledProvider:
    def __init__(self) -> None:
        self.called = False

    async def complete(self, *, messages, tools):
        self.called = True
        return ProviderResult(text="unexpected", tool_calls=[], model="fake/model")


class FakeErrorProvider:
    def __init__(self, message: str) -> None:
        self.message = message

    async def complete(self, *, messages, tools):
        raise RuntimeError(self.message)


class FakeBlockedToolProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        self.calls += 1
        self.snapshots.append(messages)
        if self.calls == 1:
            return ProviderResult(
                text="use risky tool",
                tool_calls=[ToolCall(name="exec", arguments={"command": "id"})],
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class ContextCaptureTools:
    def __init__(self) -> None:
        self.last_channel = ""
        self.last_user_id = ""

    async def execute(self, name, arguments, *, session_id: str, channel: str = "", user_id: str = "") -> str:
        self.last_channel = str(channel)
        self.last_user_id = str(user_id)
        return f"{name}:ok:{session_id}"

    def schema(self):
        return [{"name": "echo", "description": "echo text", "arguments": {"text": "string"}}]


class ExecNoopTool(Tool):
    name = "exec"
    description = "exec noop"

    def args_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        return "ok"


class BlockingConcurrencyProvider:
    def __init__(self) -> None:
        self.active_calls = 0
        self.max_active_calls = 0
        self.call_count = 0
        self.first_call_started = asyncio.Event()
        self.release_first_call = asyncio.Event()

    async def complete(self, *, messages, tools):
        self.call_count += 1
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            if self.call_count == 1:
                self.first_call_started.set()
                await self.release_first_call.wait()
            return ProviderResult(text="ok", tool_calls=[], model="fake/model")
        finally:
            self.active_calls -= 1


def test_engine_runs_tool_roundtrip() -> None:
    async def _scenario() -> None:
        engine = AgentEngine(
            provider=FakeProvider(),
            tools=FakeTools(),
        )
        out = await engine.run(session_id="abc", user_text="say hi")
        assert out.text == "final answer"
        metrics = engine.turn_metrics_snapshot()
        assert metrics["turns_total"] == 1
        assert metrics["turns_success"] == 1
        assert metrics["turns_provider_errors"] == 0
        assert metrics["turns_cancelled"] == 0
        assert metrics["last_outcome"] == "success"
        assert metrics["last_model"] == "fake/model"

    asyncio.run(_scenario())


def test_engine_uses_tool_message_protocol_and_processes_all_calls() -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithMessageCapture()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
        )
        out = await engine.run(session_id="telegram:42", user_text="run two tools")
        assert out.text == "done"
        assert provider.calls == 2

        second_round = provider.snapshots[1]
        tool_messages = [row for row in second_round if row.get("role") == "tool"]
        assert len(tool_messages) == 2
        assert {row.get("name") for row in tool_messages} == {"echo"}
        assert all(str(row.get("content", "")).startswith("echo:") for row in tool_messages)

    asyncio.run(_scenario())


def test_engine_passes_channel_and_user_to_tool_registry() -> None:
    async def _scenario() -> None:
        tools = ContextCaptureTools()
        engine = AgentEngine(
            provider=FakeProvider(),
            tools=tools,
        )
        out = await engine.run(session_id="telegram:42", user_text="run")
        assert out.text == "final answer"
        assert tools.last_channel == "telegram"
        assert tools.last_user_id == "42"

    asyncio.run(_scenario())


def test_engine_surfaces_tool_safety_block_as_safe_tool_result() -> None:
    async def _scenario() -> None:
        provider = FakeBlockedToolProvider()
        registry = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        registry.register(ExecNoopTool())
        engine = AgentEngine(provider=provider, tools=registry)

        out = await engine.run(session_id="telegram:9001", user_text="run")
        assert out.text == "done"
        assert provider.calls == 2
        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert len(tool_rows) == 1
        content = str(tool_rows[0].get("content", ""))
        assert "tool_error:exec:tool_blocked_by_safety_policy:exec:telegram" in content

    asyncio.run(_scenario())


def test_engine_passes_max_tokens_and_temperature_when_supported() -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithSamplingCapture()
        engine = AgentEngine(provider=provider, tools=FakeTools(), max_tokens=2048, temperature=0.25)
        out = await engine.run(session_id="cli:1", user_text="hello")
        assert out.text == "ok"
        assert provider.last_max_tokens == 2048
        assert provider.last_temperature == 0.25

    asyncio.run(_scenario())


def test_engine_uses_configured_memory_window_for_session_history() -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithSamplingCapture()
        sessions = SessionStoreCapture()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory_window=7,
        )
        out = await engine.run(session_id="cli:memory-window", user_text="hello")
        assert out.text == "ok"
        assert sessions.last_limit == 7

    asyncio.run(_scenario())


def test_engine_formats_memory_snippets_with_ref_and_source_marker() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemory(
            [
                MemoryRecord(
                    id="a1b2c3d4e5f6",
                    text="Remember to ship daily status.",
                    source="session:telegram:42",
                    created_at="2026-03-04T12:00:00+00:00",
                )
            ]
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)
        out = await engine.run(session_id="telegram:42", user_text="status")
        assert out.text == "ok"

        first_prompt = provider.snapshots[0]
        memory_sections = [row for row in first_prompt if row.get("role") == "system" and "[Memory]" in str(row.get("content", ""))]
        assert memory_sections
        section = str(memory_sections[0].get("content", ""))
        assert "mem:a1b2c3d4" in section
        assert "[src:session:telegram:42]" in section

    asyncio.run(_scenario())


def test_engine_memory_planner_no_retrieve_skips_lookup_for_trivial_input() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakePlannerMemory()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:no-retrieve", user_text="ok")
        assert out.text == "ok"
        assert memory.search_calls == []

        first_prompt = provider.snapshots[0]
        memory_sections = [row for row in first_prompt if row.get("role") == "system" and "[Memory]" in str(row.get("content", ""))]
        assert memory_sections == []

    asyncio.run(_scenario())


def test_engine_memory_planner_retrieve_uses_original_query() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        query = "what is my timezone preference"
        memory = FakePlannerMemory(
            {
                query: [
                    MemoryRecord(
                        id="abc123456789",
                        text="User timezone is America/Sao_Paulo.",
                        source="session:cli:tz",
                        created_at="2026-03-04T12:00:00+00:00",
                    )
                ]
            }
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:retrieve", user_text=query)
        assert out.text == "ok"
        assert memory.search_calls == [query]

    asyncio.run(_scenario())


def test_engine_memory_planner_next_query_rewrites_after_insufficient_first_hit() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        original_query = "what did we decide about deployment schedule yesterday"
        rewritten_query = "did decide about deployment schedule yesterday"
        memory = FakePlannerMemory(
            {
                original_query: [
                    MemoryRecord(
                        id="insuff000000",
                        text="Random reminder unrelated to request.",
                        source="session:cli:x",
                        created_at="2026-03-04T12:00:00+00:00",
                    )
                ],
                rewritten_query: [
                    MemoryRecord(
                        id="suff00000001",
                        text="We decided to deploy on Fridays at 17:00 UTC.",
                        source="session:cli:deploy",
                        created_at="2026-03-04T12:05:00+00:00",
                    )
                ],
            }
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:next-query", user_text=original_query)
        assert out.text == "ok"
        assert memory.search_calls == [original_query, rewritten_query]

    asyncio.run(_scenario())


def test_engine_memory_planner_next_query_rewrites_when_temporal_intent_lacks_temporal_hit() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        original_query = "what is the deployment schedule today"
        rewritten_query = "deployment schedule today"
        memory = FakePlannerMemory(
            {
                original_query: [
                    MemoryRecord(
                        id="insuff-temporal",
                        text="Deployment schedule discussion and tooling notes.",
                        source="session:cli:ops",
                        created_at="2025-01-01T00:00:00+00:00",
                    )
                ],
                rewritten_query: [
                    MemoryRecord(
                        id="suff-temporal",
                        text="Deployment is today at 17:00 UTC.",
                        source="session:cli:ops",
                        created_at="2026-03-04T12:05:00+00:00",
                    )
                ],
            }
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:temporal-next-query", user_text=original_query)
        assert out.text == "ok"
        assert memory.search_calls == [original_query, rewritten_query]

    asyncio.run(_scenario())


def test_engine_memory_planner_uses_session_recovery_when_retrieval_has_no_hits() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        query = "what is my timezone preference"
        memory = FakePlannerMemory(
            routes={},
            recovered=["User timezone is America/Sao_Paulo."],
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text=query)
        assert out.text == "ok"
        assert memory.search_calls[0] == query
        assert len(memory.search_calls) >= 1
        assert memory.recovery_calls == [("telegram:42", 4)]

        first_prompt = provider.snapshots[0]
        memory_sections = [row for row in first_prompt if row.get("role") == "system" and "[Memory]" in str(row.get("content", ""))]
        assert memory_sections
        section = str(memory_sections[0].get("content", ""))
        assert "[src:session-recovery:telegram:42] User timezone is America/Sao_Paulo." in section

    asyncio.run(_scenario())


def test_engine_memory_planner_skips_session_recovery_when_retrieval_has_hits() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        query = "what is my timezone preference"
        memory = FakePlannerMemory(
            routes={
                query: [
                    MemoryRecord(
                        id="hit000001",
                        text="Timezone is America/Sao_Paulo.",
                        source="session:telegram:42",
                        created_at="2026-03-04T12:00:00+00:00",
                    )
                ]
            },
            recovered=["fallback should not be used"],
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text=query)
        assert out.text == "ok"
        assert memory.search_calls == [query]
        assert memory.recovery_calls == []

    asyncio.run(_scenario())


def test_engine_memory_planner_session_recovery_exception_is_fail_soft() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        query = "what is my timezone preference"
        memory = FakePlannerMemory(
            routes={},
            recover_error=RuntimeError("boom"),
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text=query)
        assert out.text == "ok"
        assert memory.search_calls[0] == query
        assert len(memory.search_calls) >= 1
        assert memory.recovery_calls == [("telegram:42", 4)]

    asyncio.run(_scenario())


def test_engine_retrieval_metrics_counts_routes_attempts_hits_and_rewrites() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        retrieve_query = "what is my timezone preference"
        original_next_query = "what did we decide about deployment schedule yesterday"
        rewritten_next_query = "did decide about deployment schedule yesterday"
        memory = FakePlannerMemory(
            {
                retrieve_query: [
                    MemoryRecord(
                        id="route-retrieve-1",
                        text="Timezone is America/Sao_Paulo.",
                        source="session:cli:tz",
                        created_at="2026-03-04T12:00:00+00:00",
                    )
                ],
                original_next_query: [
                    MemoryRecord(
                        id="route-next-a",
                        text="Unrelated reminder.",
                        source="session:cli:ops",
                        created_at="2026-03-04T12:01:00+00:00",
                    )
                ],
                rewritten_next_query: [
                    MemoryRecord(
                        id="route-next-b",
                        text="Deployment schedule: Friday 17:00 UTC.",
                        source="session:cli:ops",
                        created_at="2026-03-04T12:02:00+00:00",
                    )
                ],
            }
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out_no_retrieve = await engine.run(session_id="cli:metrics:no", user_text="ok")
        out_retrieve = await engine.run(session_id="cli:metrics:retrieve", user_text=retrieve_query)
        out_next_query = await engine.run(session_id="cli:metrics:next", user_text=original_next_query)

        assert out_no_retrieve.text == "ok"
        assert out_retrieve.text == "ok"
        assert out_next_query.text == "ok"

        snapshot = engine.retrieval_metrics_snapshot()
        assert snapshot["route_counts"] == {
            "NO_RETRIEVE": 1,
            "RETRIEVE": 1,
            "NEXT_QUERY": 1,
        }
        assert snapshot["retrieval_attempts"] == 3
        assert snapshot["retrieval_hits"] == 3
        assert snapshot["retrieval_rewrites"] == 1
        assert snapshot["last_route"] == "NEXT_QUERY"
        assert snapshot["last_query"] == rewritten_next_query

    asyncio.run(_scenario())


def test_engine_retrieval_metrics_latency_buckets_accounting(monkeypatch) -> None:
    provider = FakePromptCaptureProvider()
    queries = {
        "what is my timezone preference": "lat-1",
        "when is deployment schedule today?": "lat-2",
        "what stack does project use?": "lat-3",
        "remember grocery list details": "lat-4",
    }
    memory = FakePlannerMemory(
        {
            query: [
                MemoryRecord(
                    id=row_id,
                    text=f"Row for {query}",
                    source="session:cli:latency",
                    created_at="2026-03-04T12:00:00+00:00",
                )
            ]
            for query, row_id in queries.items()
        }
    )
    engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

    sequence = iter([0.0, 0.005, 1.0, 1.02, 2.0, 2.12, 3.0, 3.25])

    def _fake_perf_counter() -> float:
        return float(next(sequence))

    monkeypatch.setattr(engine_module.time, "perf_counter", _fake_perf_counter)

    run_log = bind_event("tests.engine.latency")
    for query in queries:
        snippets = engine._plan_memory_snippets(user_text=query, run_log=run_log)
        assert snippets

    snapshot = engine.retrieval_metrics_snapshot()
    assert snapshot["retrieval_attempts"] == 4
    assert snapshot["latency_buckets"] == {
        "lt_10ms": 1,
        "10_50ms": 1,
        "50_200ms": 1,
        "gte_200ms": 1,
    }


def test_engine_respects_stop_event_before_provider_call() -> None:
    async def _scenario() -> None:
        provider = FakeNeverCalledProvider()
        engine = AgentEngine(provider=provider, tools=FakeTools())
        stop_event = asyncio.Event()
        stop_event.set()
        out = await engine.run(session_id="cli:stop", user_text="hello", stop_event=stop_event)
        assert out.model == "engine/stop"
        assert "stopped" in out.text.lower()
        assert provider.called is False
        metrics = engine.turn_metrics_snapshot()
        assert metrics["turns_total"] == 1
        assert metrics["turns_cancelled"] == 1
        assert metrics["turns_provider_errors"] == 0
        assert metrics["turns_success"] == 0
        assert metrics["last_outcome"] == "cancelled"
        assert metrics["last_model"] == "engine/stop"

    asyncio.run(_scenario())


def test_engine_truncates_tool_result_payload() -> None:
    async def _scenario() -> None:
        provider = FakeLongToolProvider()
        tools = FakeTools()
        async def _long_execute(name, arguments, *, session_id: str, channel: str = "", user_id: str = "") -> str:
            return "x" * 200

        tools.execute = _long_execute  # type: ignore[method-assign]
        engine = AgentEngine(provider=provider, tools=tools, max_tool_result_chars=32)
        await engine.run(session_id="cli:truncate", user_text="hello")
        assert provider.calls == 2
        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert len(tool_rows) == 1
        content = str(tool_rows[0].get("content", ""))
        assert len(content) <= 32
        assert "truncated" in content.lower()

    asyncio.run(_scenario())


def test_engine_enforces_per_turn_tool_budget() -> None:
    async def _scenario() -> None:
        engine = AgentEngine(provider=FakeBurstToolProvider(), tools=FakeTools())
        out = await engine.run(
            session_id="cli:budget",
            user_text="run",
            turn_budget=TurnBudget(max_tool_calls=1),
        )
        assert "tool-call budget" in out.text

    asyncio.run(_scenario())


def test_engine_emits_progress_events() -> None:
    async def _scenario() -> None:
        provider = FakeLongToolProvider()
        engine = AgentEngine(provider=provider, tools=FakeTools())
        stages: list[str] = []

        def _hook(event) -> None:
            stages.append(event.stage)

        out = await engine.run(session_id="cli:progress", user_text="run", progress_hook=_hook)
        assert out.text == "done"
        assert "turn_started" in stages
        assert "llm_request" in stages
        assert "tool_call" in stages
        assert "tool_result" in stages
        assert "turn_completed" in stages

    asyncio.run(_scenario())


def test_engine_handles_typed_provider_errors() -> None:
    async def _scenario() -> None:
        engine = AgentEngine(provider=FakeErrorProvider("provider_network_error:timeout"), tools=FakeTools())
        out = await engine.run(session_id="cli:error", user_text="hello")
        text = out.text.lower()
        assert "sorry" in text
        assert "network" in text
        metrics = engine.turn_metrics_snapshot()
        assert metrics["turns_total"] == 1
        assert metrics["turns_provider_errors"] == 1
        assert metrics["turns_success"] == 0
        assert metrics["turns_cancelled"] == 0
        assert metrics["last_outcome"] == "provider_error"
        assert metrics["last_model"] == "engine/fallback"

    asyncio.run(_scenario())


def test_engine_turn_metrics_counts_executed_tool_calls() -> None:
    async def _scenario() -> None:
        engine = AgentEngine(provider=FakeProvider(), tools=FakeTools())
        out = await engine.run(session_id="cli:tool-metrics", user_text="hello")
        assert out.text == "final answer"
        metrics = engine.turn_metrics_snapshot()
        assert metrics["tool_calls_executed"] == 1

    asyncio.run(_scenario())


def test_engine_returns_quota_specific_message_for_quota_429() -> None:
    async def _scenario() -> None:
        engine = AgentEngine(
            provider=FakeErrorProvider("provider_http_error:429:insufficient_quota: billing exhausted"),
            tools=FakeTools(),
        )
        out = await engine.run(session_id="cli:error-quota", user_text="hello")
        text = out.text.lower()
        assert "quota" in text
        assert "billing" in text or "provider" in text

    asyncio.run(_scenario())


def test_engine_reasoning_effort_uses_config_default() -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithReasoningCapture()
        engine = AgentEngine(provider=provider, tools=FakeTools(), reasoning_effort_default="medium")
        out = await engine.run(session_id="cli:reasoning-default", user_text="hello")
        assert out.text == "ok"
        assert provider.last_reasoning_effort == "medium"

    asyncio.run(_scenario())


def test_engine_reasoning_effort_inline_overrides_config() -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithReasoningCapture()
        engine = AgentEngine(provider=provider, tools=FakeTools(), reasoning_effort_default="low")
        out = await engine.run(session_id="cli:reasoning-inline", user_text="/think:high summarize")
        assert out.text == "ok"
        assert provider.last_reasoning_effort == "high"

    asyncio.run(_scenario())


def test_engine_reasoning_effort_inline_off_disables_default() -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithReasoningCapture()
        engine = AgentEngine(provider=provider, tools=FakeTools(), reasoning_effort_default="high")
        out = await engine.run(session_id="cli:reasoning-off", user_text="/t off do this")
        assert out.text == "ok"
        assert provider.last_reasoning_effort is None

    asyncio.run(_scenario())


def test_engine_detects_repeated_non_progress_tool_loops() -> None:
    async def _scenario() -> None:
        provider = FakeLoopingToolProvider()
        stages: list[str] = []

        def _hook(event) -> None:
            stages.append(event.stage)

        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            max_iterations=20,
            loop_detection=LoopDetectionSettings(
                enabled=True,
                history_size=10,
                repeat_threshold=2,
                critical_threshold=3,
            ),
        )
        out = await engine.run(session_id="cli:loop-detect", user_text="run", progress_hook=_hook)
        assert out.model == "engine/loop-detected"
        assert "loop detection" in out.text.lower()
        assert provider.calls < 20
        assert "loop_detected" in stages

    asyncio.run(_scenario())


def test_engine_serializes_concurrent_runs_for_same_session() -> None:
    async def _scenario() -> None:
        provider = BlockingConcurrencyProvider()
        engine = AgentEngine(provider=provider, tools=FakeTools())

        first = asyncio.create_task(engine.run(session_id="cli:same", user_text="one"))
        await asyncio.wait_for(provider.first_call_started.wait(), timeout=1.0)
        second = asyncio.create_task(engine.run(session_id="cli:same", user_text="two"))

        await asyncio.sleep(0.05)
        provider.release_first_call.set()

        first_result, second_result = await asyncio.gather(first, second)
        assert first_result.text == "ok"
        assert second_result.text == "ok"
        assert provider.max_active_calls == 1

    asyncio.run(_scenario())


def test_engine_keeps_parallelism_for_different_sessions() -> None:
    async def _scenario() -> None:
        provider = BlockingConcurrencyProvider()
        engine = AgentEngine(provider=provider, tools=FakeTools())

        first = asyncio.create_task(engine.run(session_id="cli:a", user_text="one"))
        await asyncio.wait_for(provider.first_call_started.wait(), timeout=1.0)
        second = asyncio.create_task(engine.run(session_id="cli:b", user_text="two"))

        await asyncio.sleep(0.05)
        provider.release_first_call.set()

        first_result, second_result = await asyncio.gather(first, second)
        assert first_result.text == "ok"
        assert second_result.text == "ok"
        assert provider.max_active_calls >= 2

    asyncio.run(_scenario())
