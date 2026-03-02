from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any

from clawlite.core.engine import AgentEngine, ProviderResult, ToolCall


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
