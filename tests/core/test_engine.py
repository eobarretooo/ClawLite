from __future__ import annotations

from dataclasses import dataclass
import asyncio
import gc
from typing import Any

import clawlite.core.engine as engine_module
from clawlite.config.schema import ToolSafetyPolicyConfig
from clawlite.core.engine import AgentEngine, LoopDetectionSettings, ProviderResult, ToolCall, TurnBudget
from clawlite.core.memory import MemoryRecord
from clawlite.core.subagent import SubagentRun
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


class FakeFixedTextProvider:
    def __init__(self, text: str) -> None:
        self.text = text

    async def complete(self, *, messages, tools):
        del messages, tools
        return ProviderResult(text=self.text, tool_calls=[], model="fake/model")


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


class FakeMemoryWithEmotionGuidance(FakeMemory):
    def emotion_guidance(self, user_text: str, *, session_id: str = "") -> str:
        del user_text, session_id
        return "User seems frustrated. Be more empathetic and brief."


class FakeMemoryWithAsyncMemorize(FakeMemory):
    def __init__(self, rows: list[MemoryRecord] | None = None) -> None:
        super().__init__(rows)
        self.memorize_calls: list[dict[str, Any]] = []
        self.consolidate_calls = 0

    async def memorize(self, *, messages=None, source: str = "session", text: str | None = None):
        self.memorize_calls.append({"messages": messages, "source": source, "text": text})
        return {"status": "ok"}

    def consolidate(self, messages, *, source: str = "session"):
        del messages, source
        self.consolidate_calls += 1
        return None


class FakeMemoryWithContextKwargs(FakeMemory):
    def __init__(self, rows: list[MemoryRecord] | None = None) -> None:
        super().__init__(rows)
        self.search_calls: list[dict[str, Any]] = []
        self.memorize_calls: list[dict[str, Any]] = []

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        user_id: str = "",
        session_id: str = "",
        include_shared: bool = False,
    ) -> list[MemoryRecord]:
        self.search_calls.append(
            {
                "query": query,
                "limit": limit,
                "user_id": user_id,
                "session_id": session_id,
                "include_shared": include_shared,
            }
        )
        return self.rows[:limit]

    async def memorize(
        self,
        *,
        messages=None,
        source: str = "session",
        user_id: str = "",
        shared: bool = False,
    ):
        self.memorize_calls.append(
            {
                "messages": messages,
                "source": source,
                "user_id": user_id,
                "shared": shared,
            }
        )
        return {"status": "ok"}


class FakeMemoryWithWorkingSetCapture(FakeMemory):
    def __init__(self) -> None:
        super().__init__([])
        self.working_set_writes: list[dict[str, Any]] = []
        self.allow_memory_write = True

    def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        del actor, session_id
        return {"allow_memory_write": self.allow_memory_write}

    def remember_working_set(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
        allow_promotion: bool = True,
    ) -> None:
        self.working_set_writes.append(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "user_id": user_id,
                "metadata": dict(metadata or {}),
                "allow_promotion": allow_promotion,
            }
        )


class FakeMemoryWithSubagentDigestPersistence(FakeMemory):
    def __init__(self) -> None:
        super().__init__([])
        self.retrieve_calls: list[dict[str, Any]] = []
        self.memorize_calls: list[dict[str, Any]] = []
        self.allow_memory_write = True

    def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        del actor, session_id
        return {"allow_memory_write": self.allow_memory_write}

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        method: str = "rag",
        user_id: str = "",
        session_id: str = "",
        include_shared: bool = False,
    ) -> dict[str, Any]:
        self.retrieve_calls.append(
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
            "hits": [],
            "episodic_digest": {
                "session_id": session_id,
                "count": 1,
                "summary": f"current:{session_id} -> blocker triaged",
            },
        }

    async def memorize(
        self,
        *,
        messages=None,
        text: str | None = None,
        source: str = "session",
        user_id: str = "",
        shared: bool = False,
        metadata: dict[str, Any] | None = None,
        reasoning_layer: str | None = None,
        memory_type: str | None = None,
        happened_at: str | None = None,
    ) -> dict[str, Any]:
        self.memorize_calls.append(
            {
                "messages": messages,
                "text": text,
                "source": source,
                "user_id": user_id,
                "shared": shared,
                "metadata": dict(metadata or {}),
                "reasoning_layer": reasoning_layer,
                "memory_type": memory_type,
                "happened_at": happened_at,
            }
        )
        return {
            "status": "ok",
            "record": {
                "id": f"rec-{len(self.memorize_calls)}",
                "text": str(text or ""),
                "source": source,
                "created_at": "2026-03-06T00:00:00+00:00",
                "category": "context",
            },
        }


class FakeMemoryWithPolicySearch(FakeMemory):
    def __init__(self, rows: list[MemoryRecord] | None = None, *, search_limit: int = 6) -> None:
        super().__init__(rows)
        self.search_limit = int(search_limit)
        self.search_calls: list[dict[str, Any]] = []

    def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        del session_id
        return {
            "actor": actor,
            "recommended_search_limit": self.search_limit,
            "allow_memory_write": True,
        }

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        user_id: str = "",
        session_id: str = "",
        include_shared: bool = False,
    ) -> list[MemoryRecord]:
        self.search_calls.append(
            {
                "query": query,
                "limit": limit,
                "user_id": user_id,
                "session_id": session_id,
                "include_shared": include_shared,
            }
        )
        return self.rows[:limit]


class FakeMemoryPolicyBlocksWrite(FakeMemoryWithAsyncMemorize):
    def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        del actor, session_id
        return {"allow_memory_write": False}


class FakeMemoryWithIntegrationHint(FakeMemory):
    def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        del actor, session_id
        return {"mode": "degraded", "allow_memory_write": True}

    def integration_hint(self, actor: str, *, session_id: str = "") -> str:
        del actor, session_id
        return "Memory quality is degraded; keep retrieval focused."


class FakeMemoryWithProfileHint(FakeMemory):
    def profile_prompt_hint(self) -> str:
        return (
            "[User Profile]\n"
            "- Preferred response length: curto\n"
            "- Timezone: America/Sao_Paulo\n"
            "- Recurring interests: viagens\n"
            "- Apply these preferences when relevant, without repeating them unless useful."
        )


class FakeSubagentManagerForDigest:
    def __init__(self) -> None:
        self.list_calls = 0
        self.mark_calls: list[dict[str, Any]] = []

    def list_completed_unsynthesized(self, session_id: str, limit: int = 8) -> list[SubagentRun]:
        self.list_calls += 1
        del limit
        return [
            SubagentRun(
                run_id="run-1234567890",
                session_id=session_id,
                task="collect context",
                status="done",
                result="Collected all required details.",
                finished_at="2026-03-05T12:00:00+00:00",
            )
        ]

    def mark_synthesized(self, run_ids: list[str], *, digest_id: str = "") -> int:
        self.mark_calls.append({"run_ids": list(run_ids), "digest_id": digest_id})
        return len(run_ids)


class FakeSubagentManagerForDigestWithTargetSession(FakeSubagentManagerForDigest):
    def __init__(self) -> None:
        super().__init__()
        self.last_runs: list[SubagentRun] = []

    def list_completed_unsynthesized(self, session_id: str, limit: int = 8) -> list[SubagentRun]:
        self.list_calls += 1
        del limit
        self.last_runs = [
            SubagentRun(
                run_id="run-0987654321",
                session_id=session_id,
                task="collect blocker context",
                status="done",
                result="Triaged blocker details and next actions.",
                finished_at="2026-03-05T12:05:00+00:00",
                metadata={
                    "target_session_id": f"{session_id}:subagent",
                    "target_user_id": "u-1",
                    "share_scope": "family",
                },
            )
        ]
        return self.last_runs


class FakeSubagentSynthesizer:
    def __init__(self) -> None:
        self.calls = 0

    def summarize(self, runs: list[Any]) -> str:
        self.calls += 1
        del runs
        return "- run-1234 [done] task=collect context | excerpt=Collected all required details."


class FakeSubagentSynthesizerWithMemoryContext:
    def __init__(self) -> None:
        self.calls = 0
        self.metadata_snapshots: list[dict[str, Any]] = []

    def summarize(self, runs: list[Any]) -> str:
        self.calls += 1
        run = runs[0]
        self.metadata_snapshots.append(dict(getattr(run, "metadata", {}) or {}))
        target_session = str(getattr(run, "metadata", {}).get("target_session_id", "") or "")
        episodic = str(getattr(run, "metadata", {}).get("episodic_digest_summary", "") or "")
        return f"- {run.run_id[:8]} [{run.status}] session={target_session} | excerpt={episodic or run.result}"


class FakePlannerMemory:
    def __init__(
        self,
        routes: dict[str, list[MemoryRecord]] | None = None,
        recovered: list[str] | None = None,
        working_rows: list[dict[str, Any]] | None = None,
        recover_error: Exception | None = None,
    ) -> None:
        self.routes = routes or {}
        self.recovered = recovered or []
        self.working_rows = working_rows or []
        self.recover_error = recover_error
        self.search_calls: list[str] = []
        self.working_calls: list[dict[str, Any]] = []
        self.recovery_calls: list[tuple[str, int]] = []

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        del limit
        self.search_calls.append(query)
        return self.routes.get(query, [])

    def consolidate(self, messages, *, source: str = "session"):
        del messages, source
        return None

    def get_working_set(
        self,
        session_id: str,
        *,
        limit: int = 8,
        include_shared_subagents: bool = True,
    ) -> list[dict[str, Any]]:
        self.working_calls.append(
            {
                "session_id": session_id,
                "limit": limit,
                "include_shared_subagents": include_shared_subagents,
            }
        )
        return self.working_rows[:limit]

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


class FakeProviderWithSamplingAndReasoningCapture:
    def __init__(self) -> None:
        self.calls = 0
        self.kwargs_history: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        messages,
        tools,
        max_tokens=None,
        temperature=None,
        reasoning_effort=None,
    ):
        del messages, tools
        self.calls += 1
        self.kwargs_history.append(
            {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "reasoning_effort": reasoning_effort,
            }
        )
        if self.calls == 1:
            return ProviderResult(
                text="needs tool",
                tool_calls=[ToolCall(name="echo", arguments={"text": "hello"})],
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


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


class FakeManyToolTurnsProvider:
    def __init__(self, *, tool_turns: int) -> None:
        self.tool_turns = max(1, int(tool_turns))
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(list(messages))
        if self.calls <= self.tool_turns:
            return ProviderResult(
                text="looping tool",
                tool_calls=[ToolCall(name="echo", arguments={"text": "x"})],
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


class FakePingPongToolProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, messages, tools):
        del messages, tools
        self.calls += 1
        if self.calls % 2 == 1:
            return ProviderResult(
                text="try alpha",
                tool_calls=[ToolCall(name="alpha", arguments={"value": "x"})],
                model="fake/model",
            )
        return ProviderResult(
            text="try beta",
            tool_calls=[ToolCall(name="beta", arguments={"value": "y"})],
            model="fake/model",
        )


class FakeDiagnosticSwitchProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(list(messages))
        if self.calls == 1:
            return ProviderResult(
                text="try tool repeatedly",
                tool_calls=[
                    ToolCall(name="echo", arguments={"text": "same"}),
                    ToolCall(name="echo", arguments={"text": "same"}),
                    ToolCall(name="echo", arguments={"text": "same"}),
                ],
                model="fake/model",
            )
        return ProviderResult(text="final after diagnostic", tool_calls=[], model="fake/model")


class FakeWhitespaceVariantFailTools:
    def __init__(self) -> None:
        self.calls = 0
        self._errors = [
            "boom   failed",
            "boom failed",
            "  boom failed   ",
        ]

    async def execute(self, name, arguments, *, session_id: str, channel: str = "", user_id: str = "") -> str:
        del name, arguments, session_id, channel, user_id
        message = self._errors[min(self.calls, len(self._errors) - 1)]
        self.calls += 1
        raise RuntimeError(message)

    def schema(self):
        return [{"name": "echo", "description": "echo text", "arguments": {"text": "string"}}]


class FakePingPongTools:
    async def execute(self, name, arguments, *, session_id: str, channel: str = "", user_id: str = "") -> str:
        del arguments, session_id, channel, user_id
        if name == "alpha":
            return "alpha:still waiting"
        if name == "beta":
            return "beta:still waiting"
        return f"{name}:unknown"

    def schema(self):
        return [
            {"name": "alpha", "description": "alpha tool", "arguments": {"value": "string"}},
            {"name": "beta", "description": "beta tool", "arguments": {"value": "string"}},
        ]


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


def test_engine_module_does_not_export_setup_logging_helper() -> None:
    assert hasattr(engine_module, "bind_event")
    assert not hasattr(engine_module, "setup_logging")


def test_engine_identity_guard_normalizes_provider_intro_on_identity_question() -> None:
    async def _scenario() -> None:
        memory = FakeMemoryWithAsyncMemorize()
        provider_text = "I am a language model trained by OpenAI. I can help debug your deployment by checking logs and config drift."
        engine = AgentEngine(
            provider=FakeFixedTextProvider(provider_text),
            tools=FakeTools(),
            memory=memory,
        )
        out = await engine.run(session_id="cli:identity-q", user_text="Who are you?")
        assert out.text == (
            "I am ClawLite, a self-hosted autonomous AI agent. "
            "I can help debug your deployment by checking logs and config drift."
        )
        assert memory.memorize_calls
        persisted = memory.memorize_calls[0]["messages"][1]["content"]
        assert persisted == out.text

    asyncio.run(_scenario())


def test_engine_identity_guard_prepends_identity_on_question_when_no_provider_intro() -> None:
    async def _scenario() -> None:
        provider_text = "To set this up, define the environment variables and run the migration command once."
        engine = AgentEngine(
            provider=FakeFixedTextProvider(provider_text),
            tools=FakeTools(),
        )
        out = await engine.run(session_id="cli:identity-prepend", user_text="What are you?")
        assert out.text == (
            "I am ClawLite, a self-hosted autonomous AI agent. "
            "To set this up, define the environment variables and run the migration command once."
        )

    asyncio.run(_scenario())


def test_engine_identity_guard_keeps_identity_question_output_when_clawlite_already_present() -> None:
    async def _scenario() -> None:
        provider_text = "I am ClawLite, your self-hosted agent. I can also troubleshoot webhook retries."
        engine = AgentEngine(
            provider=FakeFixedTextProvider(provider_text),
            tools=FakeTools(),
        )
        out = await engine.run(session_id="cli:identity-already", user_text="Who are you?")
        assert out.text == provider_text

    asyncio.run(_scenario())


def test_engine_identity_guard_rewrites_provider_intro_without_identity_question() -> None:
    async def _scenario() -> None:
        provider_text = "As an AI language model trained by Anthropic, I can help with this summary."
        engine = AgentEngine(
            provider=FakeFixedTextProvider(provider_text),
            tools=FakeTools(),
        )
        out = await engine.run(session_id="cli:identity-intro", user_text="Summarize deployment notes")
        assert out.text == "I am ClawLite, a self-hosted autonomous AI agent. I can help with this summary."

    asyncio.run(_scenario())


def test_engine_identity_guard_rewrites_embedded_provider_clause_and_persists_clean_text() -> None:
    async def _scenario() -> None:
        memory = FakeMemoryWithAsyncMemorize()
        provider_text = "Summary ready. As an AI language model trained by OpenAI, I can suggest next steps."
        engine = AgentEngine(
            provider=FakeFixedTextProvider(provider_text),
            tools=FakeTools(),
            memory=memory,
        )
        out = await engine.run(session_id="cli:identity-embedded", user_text="Summarize deployment notes")
        assert out.text == (
            "I am ClawLite, a self-hosted autonomous AI agent. "
            "Summary ready. I can suggest next steps."
        )
        assert memory.memorize_calls
        persisted = memory.memorize_calls[0]["messages"][1]["content"]
        assert persisted == out.text

    asyncio.run(_scenario())


def test_engine_identity_guard_rewrites_provider_self_sentence_before_persisting() -> None:
    async def _scenario() -> None:
        memory = FakeMemoryWithAsyncMemorize()
        provider_text = "Deployment summary: shipped and stable. I am a language model trained by OpenAI."
        engine = AgentEngine(
            provider=FakeFixedTextProvider(provider_text),
            tools=FakeTools(),
            memory=memory,
        )
        out = await engine.run(session_id="cli:identity-sentence", user_text="Summarize deployment notes")
        assert out.text == (
            "I am ClawLite, a self-hosted autonomous AI agent. "
            "Deployment summary: shipped and stable."
        )
        assert memory.memorize_calls
        persisted = memory.memorize_calls[0]["messages"][1]["content"]
        assert persisted == out.text

    asyncio.run(_scenario())


def test_engine_identity_guard_keeps_normal_output_unchanged() -> None:
    async def _scenario() -> None:
        text = "Deployment summary: shipped, monitored, and stable."
        engine = AgentEngine(
            provider=FakeFixedTextProvider(text),
            tools=FakeTools(),
        )
        out = await engine.run(session_id="cli:identity-clean", user_text="Summarize deployment notes")
        assert out.text == text

    asyncio.run(_scenario())


def test_engine_injects_subagent_digest_once_and_marks_synthesized() -> None:
    async def _scenario() -> None:
        subagents = FakeSubagentManagerForDigest()
        synthesizer = FakeSubagentSynthesizer()
        engine = AgentEngine(
            provider=FakePromptCaptureProvider(),
            tools=FakeTools(),
            subagents=subagents,
            synthesizer=synthesizer,
        )

        out = await engine.run(session_id="cli:subagent-digest", user_text="hello")
        assert out.text.count("[Subagent Digest]") == 1
        assert "run-1234 [done]" in out.text
        assert subagents.list_calls == 1
        assert len(subagents.mark_calls) == 1
        assert subagents.mark_calls[0]["run_ids"] == ["run-1234567890"]
        assert subagents.mark_calls[0]["digest_id"]
        assert synthesizer.calls == 1

    asyncio.run(_scenario())


def test_engine_enriches_subagent_digest_with_target_session_memory() -> None:
    async def _scenario() -> None:
        subagents = FakeSubagentManagerForDigestWithTargetSession()
        synthesizer = FakeSubagentSynthesizerWithMemoryContext()
        memory = FakeMemoryWithSubagentDigestPersistence()
        engine = AgentEngine(
            provider=FakePromptCaptureProvider(),
            tools=FakeTools(),
            memory=memory,
            subagents=subagents,
            synthesizer=synthesizer,
        )

        out = await engine.run(session_id="cli:owner", user_text="hello")
        assert out.text.count("[Subagent Digest]") == 1
        assert "session=cli:owner:subagent" in out.text
        assert "current:cli:owner:subagent -> blocker triaged" in out.text
        assert memory.retrieve_calls
        assert memory.retrieve_calls[0]["method"] == "rag"
        assert memory.retrieve_calls[0]["limit"] == 3
        assert memory.retrieve_calls[0]["user_id"] == "u-1"
        assert memory.retrieve_calls[0]["session_id"] == "cli:owner:subagent"
        assert memory.retrieve_calls[0]["include_shared"] is True
        assert "collect" in str(memory.retrieve_calls[0]["query"])
        digest_rows = [row for row in memory.memorize_calls if row["source"] == "subagent-digest:cli:owner"]
        assert len(digest_rows) == 1
        digest_row = digest_rows[0]
        assert digest_row["user_id"] == "u-1"
        assert digest_row["shared"] is False
        assert digest_row["reasoning_layer"] == "outcome"
        assert digest_row["memory_type"] == "event"
        assert digest_row["happened_at"] == "2026-03-05T12:05:00+00:00"
        assert "Subagent execution digest for session cli:owner." in str(digest_row["text"])
        assert "Delegated sessions: cli:owner:subagent." in str(digest_row["text"])
        assert digest_row["metadata"]["subagent_digest"] is True
        assert digest_row["metadata"]["subagent_parent_session_id"] == "cli:owner"
        assert digest_row["metadata"]["subagent_target_sessions"] == ["cli:owner:subagent"]
        assert digest_row["metadata"]["subagent_run_ids"] == ["run-0987654321"]
        assert digest_row["metadata"]["skip_profile_sync"] is True
        assert synthesizer.calls == 1
        assert synthesizer.metadata_snapshots[0]["episodic_digest_summary"] == "current:cli:owner:subagent -> blocker triaged"
        assert subagents.last_runs[0].metadata["digest_memory_persisted"] is True
        assert subagents.last_runs[0].metadata["digest_memory_source"] == "subagent-digest:cli:owner"

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


def test_engine_injects_emotional_guidance_as_system_message() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithEmotionGuidance()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:emotion", user_text="I am blocked")
        assert out.text == "ok"

        first_prompt = provider.snapshots[0]
        guidance_rows = [
            row
            for row in first_prompt
            if row.get("role") == "system"
            and "User seems frustrated. Be more empathetic and brief." in str(row.get("content", ""))
        ]
        assert guidance_rows

    asyncio.run(_scenario())


def test_engine_prefers_async_memorize_over_consolidate() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithAsyncMemorize()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:memorize", user_text="remember this")
        assert out.text == "ok"
        assert len(memory.memorize_calls) == 1
        call = memory.memorize_calls[0]
        assert call["source"] == "session:cli:memorize"
        assert isinstance(call["messages"], list)
        assert memory.consolidate_calls == 0

    asyncio.run(_scenario())


def test_engine_passes_runtime_user_context_to_memory_search_and_memorize() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithContextKwargs(
            [
                MemoryRecord(
                    id="ctx11112222",
                    text="User timezone is America/Sao_Paulo.",
                    source="session:telegram:42",
                    created_at="2026-03-04T12:00:00+00:00",
                )
            ]
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text="what is my timezone preference")
        assert out.text == "ok"
        assert memory.search_calls
        assert memory.search_calls[0]["user_id"] == "42"
        assert memory.search_calls[0]["session_id"] == "telegram:42"
        assert memory.search_calls[0]["include_shared"] is True
        assert memory.memorize_calls
        assert memory.memorize_calls[0]["user_id"] == "42"
        assert memory.memorize_calls[0]["shared"] is False

    asyncio.run(_scenario())


def test_engine_records_working_memory_for_user_and_assistant_turns() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithWorkingSetCapture()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text="hello there")
        assert out.text == "ok"
        assert memory.working_set_writes == [
            {
                "session_id": "telegram:42",
                "role": "user",
                "content": "hello there",
                "user_id": "42",
                "metadata": {"channel": "telegram"},
                "allow_promotion": True,
            },
            {
                "session_id": "telegram:42",
                "role": "assistant",
                "content": "ok",
                "user_id": "42",
                "metadata": {"channel": "telegram"},
                "allow_promotion": True,
            },
        ]

    asyncio.run(_scenario())


def test_engine_disables_working_memory_promotion_when_memory_write_policy_blocks_persistence() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithWorkingSetCapture()
        memory.allow_memory_write = False
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text="hello there")
        assert out.text == "ok"
        assert [row["allow_promotion"] for row in memory.working_set_writes] == [False, False]

    asyncio.run(_scenario())


def test_engine_memory_planner_uses_recommended_search_limit_from_integration_policy() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithPolicySearch(
            rows=[
                MemoryRecord(
                    id="ctx-limit-1",
                    text="Timezone is America/Sao_Paulo.",
                    source="session:telegram:42",
                    created_at="2026-03-04T12:00:00+00:00",
                )
            ],
            search_limit=3,
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text="what is my timezone preference")
        assert out.text == "ok"
        assert memory.search_calls
        assert memory.search_calls[0]["limit"] == 3

    asyncio.run(_scenario())


def test_engine_skips_memory_persistence_when_integration_policy_blocks_write() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryPolicyBlocksWrite()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:write-blocked", user_text="remember this")
        assert out.text == "ok"
        assert memory.memorize_calls == []
        assert memory.consolidate_calls == 0

    asyncio.run(_scenario())


def test_engine_skips_subagent_digest_memory_promotion_when_policy_blocks_write() -> None:
    async def _scenario() -> None:
        subagents = FakeSubagentManagerForDigestWithTargetSession()
        synthesizer = FakeSubagentSynthesizerWithMemoryContext()
        memory = FakeMemoryWithSubagentDigestPersistence()
        memory.allow_memory_write = False
        engine = AgentEngine(
            provider=FakePromptCaptureProvider(),
            tools=FakeTools(),
            memory=memory,
            subagents=subagents,
            synthesizer=synthesizer,
        )

        out = await engine.run(session_id="cli:owner", user_text="hello")
        assert out.text.count("[Subagent Digest]") == 1
        assert "current:cli:owner:subagent -> blocker triaged" in out.text
        assert memory.retrieve_calls
        digest_rows = [row for row in memory.memorize_calls if row["source"] == "subagent-digest:cli:owner"]
        assert digest_rows == []
        assert subagents.last_runs[0].metadata["digest_memory_persisted"] is False
        assert subagents.last_runs[0].metadata["digest_memory_source"] == "subagent-digest:cli:owner"
        assert subagents.last_runs[0].metadata["digest_memory_error"] == "blocked_by_memory_policy"

    asyncio.run(_scenario())


def test_engine_injects_memory_integration_hint_as_system_message() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithIntegrationHint()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:integration-hint", user_text="hello")
        assert out.text == "ok"

        first_prompt = provider.snapshots[0]
        hint_rows = [
            row
            for row in first_prompt
            if row.get("role") == "system"
            and "Memory quality is degraded; keep retrieval focused." in str(row.get("content", ""))
        ]
        assert hint_rows

    asyncio.run(_scenario())


def test_engine_injects_memory_profile_hint_as_system_message() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithProfileHint()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:profile-hint", user_text="hello")
        assert out.text == "ok"

        first_prompt = provider.snapshots[0]
        profile_rows = [
            row
            for row in first_prompt
            if row.get("role") == "system"
            and "[User Profile]" in str(row.get("content", ""))
        ]
        assert profile_rows
        content = str(profile_rows[0].get("content", ""))
        assert "Preferred response length: curto" in content
        assert "Timezone: America/Sao_Paulo" in content

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
        assert memory.working_calls == [
            {
                "session_id": "telegram:42",
                "limit": 4,
                "include_shared_subagents": True,
            }
        ]
        assert memory.recovery_calls == [("telegram:42", 4)]

        first_prompt = provider.snapshots[0]
        memory_sections = [row for row in first_prompt if row.get("role") == "system" and "[Memory]" in str(row.get("content", ""))]
        assert memory_sections
        section = str(memory_sections[0].get("content", ""))
        assert "[src:session-recovery:telegram:42] User timezone is America/Sao_Paulo." in section

    asyncio.run(_scenario())


def test_engine_memory_planner_uses_working_set_before_legacy_session_recovery() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        query = "what is my timezone preference"
        memory = FakePlannerMemory(
            routes={},
            working_rows=[
                {
                    "session_id": "telegram:42:subagent",
                    "role": "assistant",
                    "content": "Subagent confirmed timezone is America/Sao_Paulo.",
                }
            ],
            recovered=["legacy fallback should not run"],
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text=query)
        assert out.text == "ok"
        assert memory.working_calls == [
            {
                "session_id": "telegram:42",
                "limit": 4,
                "include_shared_subagents": True,
            }
        ]
        assert memory.recovery_calls == []

        first_prompt = provider.snapshots[0]
        memory_sections = [row for row in first_prompt if row.get("role") == "system" and "[Memory]" in str(row.get("content", ""))]
        assert memory_sections
        section = str(memory_sections[0].get("content", ""))
        assert "[src:session-recovery:telegram:42:subagent] Subagent confirmed timezone is America/Sao_Paulo." in section

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
        assert memory.working_calls == []
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


def test_engine_prunes_message_growth_in_long_tool_loops() -> None:
    async def _scenario() -> None:
        provider = FakeManyToolTurnsProvider(tool_turns=120)
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            max_iterations=220,
            max_tool_calls_per_turn=500,
        )
        out = await engine.run(
            session_id="cli:message-prune",
            user_text="run",
            turn_budget=TurnBudget(max_iterations=220, max_tool_calls=500),
        )
        assert out.text == "done"
        assert provider.calls == 121
        assert provider.snapshots

        base_message_count = len(provider.snapshots[0])
        expected_dynamic_cap = min(
            engine._MAX_DYNAMIC_MESSAGES_PER_TURN,
            500 * 2 + engine._MESSAGE_PRUNE_PADDING,
        )
        expected_total_cap = base_message_count + expected_dynamic_cap
        max_snapshot_size = max(len(snapshot) for snapshot in provider.snapshots)

        assert max_snapshot_size <= expected_total_cap

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


def test_engine_detects_ping_pong_non_progress_tool_loops() -> None:
    async def _scenario() -> None:
        provider = FakePingPongToolProvider()
        loop_events: list[dict[str, Any]] = []

        def _hook(event) -> None:
            if event.stage == "loop_detected":
                loop_events.append(event.metadata or {})

        engine = AgentEngine(
            provider=provider,
            tools=FakePingPongTools(),
            max_iterations=20,
            loop_detection=LoopDetectionSettings(
                enabled=True,
                history_size=10,
                repeat_threshold=2,
                critical_threshold=3,
            ),
        )
        out = await engine.run(session_id="cli:ping-pong-detect", user_text="run", progress_hook=_hook)
        assert out.model == "engine/loop-detected"
        assert "alternating" in out.text.lower()
        assert provider.calls < 20
        assert loop_events
        assert loop_events[0]["detector"] == "ping_pong_no_progress"
        assert loop_events[0]["other_tool"] in {"alpha", "beta"}

    asyncio.run(_scenario())


def test_engine_switches_to_diagnostic_mode_after_repeated_identical_tool_failures() -> None:
    async def _scenario() -> None:
        provider = FakeDiagnosticSwitchProvider()
        tools = FakeWhitespaceVariantFailTools()
        diagnostic_events: list[dict[str, Any]] = []

        def _hook(event) -> None:
            if event.stage == "diagnostic_switch":
                diagnostic_events.append(event.metadata or {})

        engine = AgentEngine(provider=provider, tools=tools)
        out = await engine.run(session_id="cli:diagnostic-switch", user_text="run", progress_hook=_hook)
        assert out.text == "final after diagnostic"
        assert provider.calls == 2
        assert len(diagnostic_events) == 1
        assert diagnostic_events[0]["tool"] == "echo"
        assert diagnostic_events[0]["repeats"] == 3
        assert diagnostic_events[0]["threshold"] == 3

        second_round = provider.snapshots[1]
        diagnostic_rows = [
            row
            for row in second_round
            if row.get("role") == "system" and "Repeated identical tool failure detected" in str(row.get("content", ""))
        ]
        assert diagnostic_rows

        metrics = engine.turn_metrics_snapshot()
        assert metrics["diagnostic_switches"] > 0

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


def test_engine_session_locks_are_memory_safe_after_sessions_finish() -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithSamplingCapture()
        engine = AgentEngine(provider=provider, tools=FakeTools())

        for idx in range(40):
            out = await engine.run(session_id=f"cli:lock:{idx}", user_text="hello")
            assert out.text == "ok"

        await asyncio.sleep(0)
        gc.collect()
        assert len(engine._session_locks) == 0

    asyncio.run(_scenario())


def test_engine_caches_provider_complete_signature_and_preserves_kwargs(monkeypatch) -> None:
    async def _scenario() -> None:
        provider = FakeProviderWithSamplingAndReasoningCapture()
        complete_func = provider.complete.__func__
        original_signature = engine_module.inspect.signature
        counts = {"provider_complete": 0}

        def _signature_spy(obj):
            target = getattr(obj, "__func__", obj)
            if target is complete_func:
                counts["provider_complete"] += 1
            return original_signature(obj)

        monkeypatch.setattr(engine_module.inspect, "signature", _signature_spy)

        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            max_tokens=321,
            temperature=0.33,
            reasoning_effort_default="medium",
        )
        out = await engine.run(session_id="cli:signature-cache", user_text="run")
        assert out.text == "done"
        assert provider.calls == 2
        assert counts["provider_complete"] == 1
        assert provider.kwargs_history == [
            {"max_tokens": 321, "temperature": 0.33, "reasoning_effort": "medium"},
            {"max_tokens": 321, "temperature": 0.33, "reasoning_effort": "medium"},
        ]

    asyncio.run(_scenario())


def test_engine_caches_memory_callable_signatures(monkeypatch) -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithContextKwargs(
            [
                MemoryRecord(
                    id="ctxcache0001",
                    text="User timezone is America/Sao_Paulo.",
                    source="session:telegram:42",
                    created_at="2026-03-04T12:00:00+00:00",
                )
            ]
        )
        search_func = memory.search.__func__
        memorize_func = memory.memorize.__func__
        original_signature = engine_module.inspect.signature
        counts = {"search": 0, "memorize": 0}

        def _signature_spy(obj):
            target = getattr(obj, "__func__", obj)
            if target is search_func:
                counts["search"] += 1
            if target is memorize_func:
                counts["memorize"] += 1
            return original_signature(obj)

        monkeypatch.setattr(engine_module.inspect, "signature", _signature_spy)

        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)
        out_one = await engine.run(session_id="telegram:42", user_text="what is my timezone preference")
        out_two = await engine.run(session_id="telegram:42", user_text="what is my timezone preference")
        assert out_one.text == "ok"
        assert out_two.text == "ok"
        assert counts["search"] == 1
        assert counts["memorize"] == 1

    asyncio.run(_scenario())


def test_engine_stop_requests_expire_by_ttl_and_cleanup() -> None:
    provider = FakeProviderWithSamplingCapture()
    engine = AgentEngine(provider=provider, tools=FakeTools())
    now = {"value": 1000.0}

    def _fake_monotonic() -> float:
        return float(now["value"])

    original_monotonic = engine_module.time.monotonic
    engine_module.time.monotonic = _fake_monotonic
    try:
        assert engine.request_stop("cli:stale-stop") is True
        assert "cli:stale-stop" in engine._stop_requests

        now["value"] += engine._stop_request_ttl_seconds + 1.0
        assert engine._stop_requested(session_id="cli:stale-stop", stop_event=None) is False
        assert "cli:stale-stop" not in engine._stop_requests

        assert engine.request_stop("cli:active-stop") is True
        assert engine._stop_requested(session_id="cli:active-stop", stop_event=None) is True
        engine.clear_stop("cli:active-stop")
        assert engine._stop_requested(session_id="cli:active-stop", stop_event=None) is False
    finally:
        engine_module.time.monotonic = original_monotonic
