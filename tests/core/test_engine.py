from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any

from clawlite.core.engine import AgentEngine, LoopDetectionSettings, ProviderResult, ToolCall, TurnBudget


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
    async def execute(self, name, arguments, *, session_id: str) -> str:
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


class FakeOneShotProvider:
    async def complete(self, *, messages, tools):
        return ProviderResult(text="ok", tool_calls=[], model="fake/model")


class FakeSessionStore:
    def __init__(self, *, fail_role: str | None = None) -> None:
        self.fail_role = fail_role
        self.rows: dict[str, list[dict[str, str]]] = {}

    def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        return self.rows.get(session_id, [])[-limit:]

    def append(self, session_id: str, role: str, content: str) -> None:
        if role == self.fail_role:
            raise RuntimeError(f"append failed for {role}")
        self.rows.setdefault(session_id, []).append({"role": role, "content": content})


class _MemoryRow:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeMemoryStore:
    def __init__(self, *, fail_consolidate: bool = False) -> None:
        self.fail_consolidate = fail_consolidate

    def search(self, query: str, limit: int = 6) -> list[_MemoryRow]:
        return []

    def consolidate(self, messages: list[dict[str, str]], *, source: str) -> None:
        if self.fail_consolidate:
            raise RuntimeError("consolidate failed")


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


def test_engine_passes_max_tokens_and_temperature_when_supported() -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithSamplingCapture()
        engine = AgentEngine(provider=provider, tools=FakeTools(), max_tokens=2048, temperature=0.25)
        out = await engine.run(session_id="cli:1", user_text="hello")
        assert out.text == "ok"
        assert provider.last_max_tokens == 2048
        assert provider.last_temperature == 0.25

    asyncio.run(_scenario())


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

    asyncio.run(_scenario())


def test_engine_truncates_tool_result_payload() -> None:
    async def _scenario() -> None:
        provider = FakeLongToolProvider()
        tools = FakeTools()
        async def _long_execute(name, arguments, *, session_id: str) -> str:
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


def test_engine_returns_response_when_user_session_append_fails() -> None:
    async def _scenario() -> None:
        sessions = FakeSessionStore(fail_role="user")
        memory = FakeMemoryStore()
        engine = AgentEngine(provider=FakeOneShotProvider(), tools=FakeTools(), sessions=sessions, memory=memory)

        out = await engine.run(session_id="cli:persist-user-fail", user_text="hello")

        assert out.text == "ok"
        assert out.model == "fake/model"

    asyncio.run(_scenario())


def test_engine_returns_response_when_assistant_session_append_fails() -> None:
    async def _scenario() -> None:
        sessions = FakeSessionStore(fail_role="assistant")
        memory = FakeMemoryStore()
        engine = AgentEngine(provider=FakeOneShotProvider(), tools=FakeTools(), sessions=sessions, memory=memory)

        out = await engine.run(session_id="cli:persist-assistant-fail", user_text="hello")

        assert out.text == "ok"
        assert out.model == "fake/model"

    asyncio.run(_scenario())


def test_engine_returns_response_when_memory_consolidate_fails() -> None:
    async def _scenario() -> None:
        sessions = FakeSessionStore()
        memory = FakeMemoryStore(fail_consolidate=True)
        engine = AgentEngine(provider=FakeOneShotProvider(), tools=FakeTools(), sessions=sessions, memory=memory)

        out = await engine.run(session_id="cli:persist-memory-fail", user_text="hello")

        assert out.text == "ok"
        assert out.model == "fake/model"

    asyncio.run(_scenario())


def test_engine_persistence_failures_still_emit_turn_completed() -> None:
    async def _scenario() -> None:
        sessions = FakeSessionStore(fail_role="user")
        memory = FakeMemoryStore()
        engine = AgentEngine(provider=FakeOneShotProvider(), tools=FakeTools(), sessions=sessions, memory=memory)
        stages: list[str] = []

        def _hook(event) -> None:
            stages.append(event.stage)

        out = await engine.run(
            session_id="cli:persist-progress",
            user_text="hello",
            progress_hook=_hook,
        )

        assert out.text == "ok"
        assert "turn_completed" in stages

    asyncio.run(_scenario())
