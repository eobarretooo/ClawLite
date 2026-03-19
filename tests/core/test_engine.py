from __future__ import annotations

from dataclasses import dataclass
import asyncio
import copy
import gc
import json
import time
from pathlib import Path
from typing import Any

import clawlite.core.engine as engine_module
from clawlite.config.schema import ToolSafetyPolicyConfig
from clawlite.core.engine import (
    AgentEngine,
    InMemorySessionStore,
    LoopDetectionSettings,
    ProviderChunk,
    ProviderResult,
    ToolCall,
    TurnBudget,
)
from clawlite.core.memory import MemoryRecord
from clawlite.core.subagent import SubagentManager, SubagentRun
from clawlite.core.subagent_synthesizer import SubagentSynthesizer
from clawlite.core.prompt import PromptBuilder
from clawlite.runtime.telemetry import set_test_tracer_factory
from clawlite.session.store import SessionStore
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry
from clawlite.utils.logging import bind_event


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_default_model(self) -> str:
        return "fake/model"

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
    async def execute(
        self,
        name,
        arguments,
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
        requester_id: str = "",
    ) -> str:
        del channel, user_id, requester_id
        return f"{name}:{arguments.get('text', '')}:{session_id}"

    def schema(self):
        return [{"name": "echo", "description": "echo text", "arguments": {"text": "string"}}]


class FakeProviderWithMessageCapture:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
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
        self.snapshots.append(copy.deepcopy(messages))
        return ProviderResult(text="ok", tool_calls=[], model="fake/model")


class FakeStreamingPromptCaptureProvider:
    def __init__(self, text: str = "ok") -> None:
        self.text = text
        self.snapshots: list[list[dict[str, Any]]] = []
        self.stream_calls = 0

    async def stream(self, *, messages, max_tokens=None, temperature=None):
        del max_tokens, temperature
        self.stream_calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        if not self.text:
            yield ProviderChunk(text="", accumulated="", done=True)
            return
        accumulated = ""
        for index, char in enumerate(self.text):
            accumulated += char
            yield ProviderChunk(text=char, accumulated=accumulated, done=index == len(self.text) - 1)


class FakeStreamingErrorProvider:
    async def stream(self, *, messages, max_tokens=None, temperature=None):
        del messages, max_tokens, temperature
        yield ProviderChunk(text="", accumulated="", done=True, error="provider_stream_error:boom")


class FakeStreamingDegradedProvider:
    async def stream(self, *, messages, max_tokens=None, temperature=None):
        del messages, max_tokens, temperature
        yield ProviderChunk(text="o", accumulated="o", done=False)
        yield ProviderChunk(text="k", accumulated="ok", done=True, degraded=True)


class LockTrackingStreamingProvider:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def stream(self, *, messages, max_tokens=None, temperature=None):
        del messages, max_tokens, temperature
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            yield ProviderChunk(text="o", accumulated="o", done=False)
            await asyncio.sleep(0.02)
            yield ProviderChunk(text="k", accumulated="ok", done=True)
        finally:
            self.active -= 1


class StoppableStreamingProvider:
    def __init__(self) -> None:
        self.closed = False
        self.yielded_second = False

    async def stream(self, *, messages, max_tokens=None, temperature=None):
        del messages, max_tokens, temperature
        try:
            yield ProviderChunk(text="o", accumulated="o", done=False)
            await asyncio.sleep(0.05)
            self.yielded_second = True
            yield ProviderChunk(text="k", accumulated="ok", done=True)
        finally:
            self.closed = True


class FakeFixedTextProvider:
    def __init__(self, text: str) -> None:
        self.text = text

    async def complete(self, *, messages, tools):
        del messages, tools
        return ProviderResult(text=self.text, tool_calls=[], model="fake/model")


class FakeSemanticSummaryProvider:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def get_default_model(self) -> str:
        return "fake/model"

    async def complete(self, *, messages, tools=None, max_tokens=None, temperature=None, reasoning_effort=None):
        del tools, max_tokens, temperature, reasoning_effort
        self.calls.append(copy.deepcopy(messages))
        system_text = str(messages[0].get("content", "") or "") if messages else ""
        if system_text.startswith("Compress the provided content for an agent context window."):
            return ProviderResult(text="semantic summary from llm", tool_calls=[], model="fake/model")
        return ProviderResult(text="final answer", tool_calls=[], model="fake/model")


class FakeToolCompactionProvider:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []
        self.main_calls = 0

    def get_default_model(self) -> str:
        return "fake/model"

    async def complete(self, *, messages, tools=None, max_tokens=None, temperature=None, reasoning_effort=None):
        del tools, max_tokens, temperature, reasoning_effort
        self.calls.append(copy.deepcopy(messages))
        system_text = str(messages[0].get("content", "") or "") if messages else ""
        if system_text.startswith("Compress the provided content for an agent context window."):
            return ProviderResult(text="compacted tool output", tool_calls=[], model="fake/model")
        self.main_calls += 1
        if self.main_calls == 1:
            return ProviderResult(
                text="need tools",
                tool_calls=[ToolCall(name="echo", arguments={"text": "ignored"})],
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class FakeWebToolProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, messages, tools):
        del messages, tools
        self.calls += 1
        if self.calls == 1:
            return ProviderResult(
                text="checking the web",
                tool_calls=[ToolCall(name="web_search", arguments={"query": "openclaw"})],
                model="fake/model",
            )
        return ProviderResult(text="OpenClaw is an autonomous assistant stack.", tool_calls=[], model="fake/model")


class FakeStreamingWebToolProvider(FakeWebToolProvider):
    def __init__(self) -> None:
        super().__init__()
        self.stream_calls = 0

    async def stream(self, *, messages, max_tokens=None, temperature=None):
        del messages, max_tokens, temperature
        self.stream_calls += 1
        yield ProviderChunk(text="st", accumulated="st", done=False)
        yield ProviderChunk(text="ream", accumulated="stream", done=True)


class FakeStreamingToolSignalProvider:
    def __init__(self) -> None:
        self.stream_calls = 0
        self.tools_seen: list[dict[str, Any]] | None = None

    async def stream(self, *, messages, tools=None, max_tokens=None, temperature=None):
        del messages, max_tokens, temperature
        self.stream_calls += 1
        self.tools_seen = list(tools or [])
        yield ProviderChunk(text="", accumulated="", done=True, requires_full_run=True)


class FakeWhitespacePreludeToolSignalProvider(FakeStreamingToolSignalProvider):
    async def stream(self, *, messages, tools=None, max_tokens=None, temperature=None):
        del messages, max_tokens, temperature
        self.stream_calls += 1
        self.tools_seen = list(tools or [])
        yield ProviderChunk(text=" \n\t", accumulated=" \n\t", done=False)
        yield ProviderChunk(text="", accumulated=" \n\t", done=True, requires_full_run=True)


class FakeWebSearchTools:
    async def execute(
        self,
        name,
        arguments,
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
        requester_id: str = "",
    ) -> str:
        del arguments, session_id, channel, user_id, requester_id
        if name != "web_search":
            raise AssertionError(f"unexpected tool {name}")
        return json.dumps(
            {
                "ok": True,
                "tool": "web_search",
                "result": {
                    "items": [
                        {"title": "OpenClaw", "url": "https://openclaw.ai/", "snippet": "site"},
                        {"title": "GitHub", "url": "https://github.com/openclaw", "snippet": "repo"},
                    ]
                },
            }
        )

    def schema(self):
        return [{"name": "web_search", "description": "search web", "arguments": {"query": "string"}}]


class FakeLiveLookupRetryProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        if self.calls == 1:
            return ProviderResult(text="Suzano, SP está com 24°C no momento.", tool_calls=[], model="fake/model")
        if self.calls == 2:
            return ProviderResult(
                text="checking live weather",
                tool_calls=[ToolCall(name="web_search", arguments={"query": "Suzano SP weather current"})],
                model="fake/model",
            )
        return ProviderResult(text="Suzano, SP está com 24°C no momento.", tool_calls=[], model="fake/model")


class FakeLiveLookupFailureProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        return ProviderResult(text="Suzano, SP está com 24°C no momento.", tool_calls=[], model="fake/model")


class FakeSkillsLoader:
    def __init__(self, *, names: list[str]) -> None:
        self._names = list(names)

    def render_for_prompt(self, selected=None, *, include_unavailable: bool = False):
        del selected, include_unavailable
        return []

    def always_on(self, *, only_available: bool = True):
        del only_available
        return []

    def load_skills_for_context(self, skill_names):
        del skill_names
        return ""

    def discover(self, include_unavailable: bool = False):
        del include_unavailable
        rows = []
        for name in self._names:
            rows.append(type("Skill", (), {"name": name})())
        return rows


class SessionStoreCapture:
    def __init__(self) -> None:
        self.last_limit: int | None = None

    def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        self.last_limit = limit
        return []


class _FakeSpan:
    def __init__(self, name: str, sink: list[dict[str, Any]]) -> None:
        self._row = {"name": name, "attributes": {}, "exceptions": []}
        self._sink = sink

    def __enter__(self) -> "_FakeSpan":
        self._sink.append(self._row)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def set_attribute(self, name: str, value: Any) -> None:
        self._row["attributes"][name] = value

    def record_exception(self, exc: Exception) -> None:
        self._row["exceptions"].append(type(exc).__name__)


class _FakeTracer:
    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink

    def start_as_current_span(self, name: str) -> _FakeSpan:
        return _FakeSpan(name, self._sink)

    def append(self, session_id: str, role: str, content: str) -> None:
        return None


class SessionStoreRecorder:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        del session_id, limit
        return []

    def append(self, session_id: str, role: str, content: str) -> None:
        self.rows.append({"session_id": session_id, "role": role, "content": content})


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


class FakeMemoryWithAsyncEmotionGuidance(FakeMemory):
    async def emotion_guidance(self, user_text: str, *, session_id: str = "") -> str:
        del user_text, session_id
        await asyncio.sleep(0)
        return "Async guidance: keep the reply calm and direct."


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


class FakeMemoryWithDeferredTurnPersistence(FakeMemory):
    supports_deferred_turn_persistence = True

    def __init__(self, rows: list[MemoryRecord] | None = None) -> None:
        super().__init__(rows)
        self.memorize_calls: list[dict[str, Any]] = []
        self.working_set_writes: list[dict[str, Any]] = []
        self.allow_memorize = asyncio.Event()
        self.memorize_started = asyncio.Event()

    def remember_working_set(
        self,
        *,
        role: str,
        content: str,
        session_id: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
        allow_promotion: bool = True,
    ) -> None:
        self.working_set_writes.append(
            {
                "session_id": session_id,
                "role": str(role or ""),
                "content": str(content or ""),
                "user_id": user_id,
                "metadata": dict(metadata or {}),
                "allow_promotion": bool(allow_promotion),
            }
        )

    async def memorize(
        self,
        *,
        messages=None,
        source: str = "session",
        text: str | None = None,
        user_id: str = "",
        shared: bool = False,
        metadata: dict[str, Any] | None = None,
        reasoning_layer: str | None = None,
        memory_type: str | None = None,
        happened_at: str | None = None,
    ) -> dict[str, Any]:
        self.memorize_started.set()
        await self.allow_memorize.wait()
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
        return {"status": "ok"}


class FakeMemoryWithSlowDeferredWorkingSet(FakeMemory):
    supports_deferred_turn_persistence = True

    def __init__(self, *, delay_s: float = 0.3) -> None:
        super().__init__([])
        self.delay_s = max(0.0, float(delay_s))
        self.batch_calls: list[dict[str, Any]] = []
        self.memorize_calls: list[dict[str, Any]] = []

    def remember_working_messages(
        self,
        *,
        session_id: str,
        messages: list[dict[str, Any]],
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
        allow_promotion: bool = True,
    ) -> None:
        time.sleep(self.delay_s)
        self.batch_calls.append(
            {
                "session_id": session_id,
                "messages": [dict(item) for item in messages],
                "user_id": user_id,
                "metadata": dict(metadata or {}),
                "allow_promotion": allow_promotion,
            }
        )

    async def memorize(
        self,
        *,
        messages=None,
        source: str = "session",
        user_id: str = "",
        shared: bool = False,
    ) -> dict[str, Any]:
        self.memorize_calls.append(
            {
                "messages": [dict(item) for item in messages or []],
                "source": source,
                "user_id": user_id,
                "shared": shared,
            }
        )
        return {"status": "ok"}


class FakeMemoryWithWorkingSetBatchCapture(FakeMemory):
    def __init__(self) -> None:
        super().__init__([])
        self.working_set_writes: list[dict[str, Any]] = []
        self.batch_calls: list[dict[str, Any]] = []

    def remember_working_messages(
        self,
        *,
        session_id: str,
        messages: list[dict[str, Any]],
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
        allow_promotion: bool = True,
    ) -> None:
        self.batch_calls.append(
            {
                "session_id": session_id,
                "messages": [dict(item) for item in messages],
                "user_id": user_id,
                "metadata": dict(metadata or {}),
                "allow_promotion": allow_promotion,
            }
        )
        for item in messages:
            self.working_set_writes.append(
                {
                    "session_id": session_id,
                    "role": str(item.get("role", "") or ""),
                    "content": str(item.get("content", "") or ""),
                    "user_id": user_id,
                    "metadata": dict(metadata or {}),
                    "allow_promotion": allow_promotion,
                }
            )

    def remember_working_set(self, *args, **kwargs) -> None:
        raise AssertionError("remember_working_set fallback should not be used when batch API is available")


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


class FakeMemoryWithAsyncPolicySearch(FakeMemoryWithContextKwargs):
    def __init__(self, rows: list[MemoryRecord] | None = None, *, search_limit: int = 6) -> None:
        super().__init__(rows)
        self.search_limit = int(search_limit)
        self.policy_calls: list[dict[str, Any]] = []

    async def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        self.policy_calls.append({"actor": actor, "session_id": session_id})
        await asyncio.sleep(0)
        return {
            "actor": actor,
            "recommended_search_limit": self.search_limit,
            "allow_memory_write": True,
        }


class FakeMemoryWithAsyncWriteBlock(FakeMemoryWithAsyncMemorize):
    async def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        del actor, session_id
        await asyncio.sleep(0)
        return {"allow_memory_write": False}


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


class FakeSubagentManagerEmpty:
    def list_completed_unsynthesized(self, session_id: str, limit: int = 8) -> list[SubagentRun]:
        del session_id, limit
        return []


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


class FakeSubagentManagerForDigestWithContinuation(FakeSubagentManagerForDigest):
    def list_completed_unsynthesized(self, session_id: str, limit: int = 8) -> list[SubagentRun]:
        self.list_calls += 1
        del limit
        return [
            SubagentRun(
                run_id="run-cont-1234",
                session_id=session_id,
                task="continue blocker triage",
                status="done",
                result="Confirmed owner and next action.",
                finished_at="2026-03-05T12:10:00+00:00",
                metadata={
                    "target_session_id": f"{session_id}:subagent",
                    "continuation_context_applied": True,
                    "continuation_digest_summary": f"current:{session_id}:subagent -> blocker triaged",
                    "continuation_digest_session_id": f"{session_id}:subagent",
                    "continuation_digest_count": 1,
                },
            )
        ]


class FakeSubagentManagerForParallelDigest(FakeSubagentManagerForDigest):
    def list_completed_unsynthesized(self, session_id: str, limit: int = 8) -> list[SubagentRun]:
        self.list_calls += 1
        del limit
        return [
            SubagentRun(
                run_id="run-par-1111",
                session_id=session_id,
                task="collect api signals",
                status="done",
                result="Collected API signals.",
                finished_at="2026-03-05T12:15:00+00:00",
                metadata={
                    "target_session_id": f"{session_id}:subagent:1",
                    "parallel_group_id": "grp123456789",
                    "parallel_group_index": 1,
                    "parallel_group_size": 2,
                },
            ),
            SubagentRun(
                run_id="run-par-2222",
                session_id=session_id,
                task="collect db signals",
                status="done",
                result="Collected DB signals.",
                finished_at="2026-03-05T12:16:00+00:00",
                metadata={
                    "target_session_id": f"{session_id}:subagent:2",
                    "parallel_group_id": "grp123456789",
                    "parallel_group_index": 2,
                    "parallel_group_size": 2,
                },
            ),
        ]


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
        search_limit: int | None = None,
    ) -> None:
        self.routes = routes or {}
        self.recovered = recovered or []
        self.working_rows = working_rows or []
        self.recover_error = recover_error
        self.search_limit = search_limit
        self.search_calls: list[str] = []
        self.search_call_details: list[dict[str, Any]] = []
        self.working_calls: list[dict[str, Any]] = []
        self.recovery_calls: list[tuple[str, int]] = []

    def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        del actor, session_id
        payload = {"allow_memory_write": True}
        if self.search_limit is not None:
            payload["recommended_search_limit"] = int(self.search_limit)
        return payload

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        user_id: str = "",
        session_id: str = "",
        include_shared: bool = False,
    ) -> list[MemoryRecord]:
        self.search_calls.append(query)
        self.search_call_details.append(
            {
                "query": query,
                "limit": limit,
                "user_id": user_id,
                "session_id": session_id,
                "include_shared": include_shared,
            }
        )
        return self.routes.get(query, [])[:limit]

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
        self.snapshots.append(copy.deepcopy(messages))
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


class FakeRepeatedPlanProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, messages, tools):
        del messages, tools
        self.calls += 1
        return ProviderResult(
            text="keep using the same plan",
            tool_calls=[ToolCall(name="echo", arguments={"text": "loop"})],
            model="fake/model",
        )


class FakeLoopRecoveryProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        recovery_notice = any(
            row.get("role") == "system" and "Do not repeat the same action unchanged" in str(row.get("content", ""))
            for row in messages
            if isinstance(row, dict)
        )
        if recovery_notice:
            return ProviderResult(
                text="I changed strategy and will answer directly.",
                tool_calls=[],
                model="fake/model",
            )
        return ProviderResult(
            text="keep using the same plan",
            tool_calls=[ToolCall(name="echo", arguments={"text": "loop"})],
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

    async def execute(
        self,
        name,
        arguments,
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
        requester_id: str = "",
    ) -> str:
        del name, arguments, session_id, channel, user_id, requester_id
        message = self._errors[min(self.calls, len(self._errors) - 1)]
        self.calls += 1
        raise RuntimeError(message)

    def schema(self):
        return [{"name": "echo", "description": "echo text", "arguments": {"text": "string"}}]


class FakePingPongTools:
    async def execute(
        self,
        name,
        arguments,
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
        requester_id: str = "",
    ) -> str:
        del arguments, session_id, channel, user_id, requester_id
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


class FakeChangingResultTools:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        name,
        arguments,
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
        requester_id: str = "",
    ) -> str:
        del channel, user_id, requester_id
        self.calls += 1
        return f"{name}:{arguments.get('text', '')}:{session_id}:{self.calls}"

    def schema(self):
        return [{"name": "echo", "description": "echo text", "arguments": {"text": "string"}}]


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
        self.snapshots.append(copy.deepcopy(messages))
        if self.calls == 1:
            return ProviderResult(
                text="use risky tool",
                tool_calls=[ToolCall(name="exec", arguments={"command": "id"})],
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class FakeJsonStringToolProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        if self.calls == 1:
            return ProviderResult(
                text="use tool with json string args",
                tool_calls=[ToolCall(name="echo", arguments='{"text":"hello"}')],  # type: ignore[arg-type]
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class FakeInvalidToolArgumentsProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        if self.calls == 1:
            return ProviderResult(
                text="use tool with broken args",
                tool_calls=[ToolCall(name="echo", arguments='{"text":hello}')],  # type: ignore[arg-type]
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class FakeUnknownToolNameProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        if self.calls == 1:
            return ProviderResult(
                text="use unknown tool",
                tool_calls=[ToolCall(name="ghost", arguments={"text": "hello"})],
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class FakeInvalidToolNameProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        if self.calls == 1:
            return ProviderResult(
                text="use malformed tool name",
                tool_calls=[ToolCall(name="echo bad", arguments={"text": "hello"})],
                model="fake/model",
            )
        return ProviderResult(text="done", tool_calls=[], model="fake/model")


class FakeDictProviderPayloadProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        if self.calls == 1:
            return {
                "text": "use dict payload",
                "tool_calls": (
                    {
                        "name": "echo",
                        "arguments": {"text": "hello"},
                        "id": "dict-call-1",
                    },
                ),
                "model": 123,
            }
        return {
            "text": "done",
            "tool_calls": [],
            "model": "fake/model",
        }


class FakeInvalidToolCallsContainerProvider:
    async def complete(self, *, messages, tools):
        del messages, tools
        return {
            "text": "done",
            "tool_calls": "broken-container",
            "model": "fake/model",
        }


class FakeDuplicateAndInvalidToolIdProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools):
        del tools
        self.calls += 1
        self.snapshots.append(copy.deepcopy(messages))
        if self.calls == 1:
            return {
                "text": "use duplicate ids",
                "tool_calls": [
                    {"name": "echo", "arguments": {"text": "first"}, "id": "dup"},
                    {"name": "echo", "arguments": {"text": "second"}, "id": "dup"},
                    {"name": "echo", "arguments": {"text": "third"}, "id": "bad id!"},
                ],
                "model": "fake/model",
            }
        return {
            "text": "done",
            "tool_calls": [],
            "model": "fake/model",
        }


class ContextCaptureTools:
    def __init__(self) -> None:
        self.last_channel = ""
        self.last_user_id = ""

    async def execute(
        self,
        name,
        arguments,
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
        requester_id: str = "",
    ) -> str:
        del requester_id
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


class ExecuteCaptureTools:
    def __init__(self) -> None:
        self.execute_calls: list[dict[str, Any]] = []

    async def execute(
        self,
        name,
        arguments,
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
        requester_id: str = "",
    ) -> str:
        self.execute_calls.append(
            {
                "name": name,
                "arguments": dict(arguments),
                "session_id": session_id,
                "channel": channel,
                "user_id": user_id,
                "requester_id": requester_id,
            }
        )
        return f"{name}:{arguments.get('text', '')}:{session_id}"

    def schema(self):
        return [{"name": "echo", "description": "echo text", "arguments": {"text": "string"}}]


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


def test_engine_run_emits_engine_and_provider_spans() -> None:
    async def _scenario() -> None:
        spans: list[dict[str, Any]] = []
        set_test_tracer_factory(lambda _name: _FakeTracer(spans))
        try:
            engine = AgentEngine(
                provider=FakeProvider(),
                tools=FakeTools(),
                memory=FakeMemory(),
                sessions=InMemorySessionStore(),
            )
            out = await engine.run(session_id="abc", user_text="say hi")
        finally:
            set_test_tracer_factory(None)

        assert out.text == "final answer"
        span_names = [row["name"] for row in spans]
        assert "engine.run" in span_names
        assert "provider.complete" in span_names
        engine_span = next(row for row in spans if row["name"] == "engine.run")
        provider_span = next(row for row in spans if row["name"] == "provider.complete")
        assert engine_span["attributes"]["session.id"] == "abc"
        assert engine_span["attributes"]["result.model"] == "fake/model"
        assert int(engine_span["attributes"]["result.tool_calls"]) == 0
        assert provider_span["attributes"]["provider.model_hint"] == "fake/model"
        assert int(provider_span["attributes"]["tools.count"]) >= 1

    asyncio.run(_scenario())


def test_engine_runs_tool_roundtrip() -> None:
    async def _scenario() -> None:
        engine = AgentEngine(
            provider=FakeProvider(),
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
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


def test_engine_accepts_tool_arguments_from_json_string_payload() -> None:
    async def _scenario() -> None:
        provider = FakeJsonStringToolProvider()
        tools = ExecuteCaptureTools()
        engine = AgentEngine(provider=provider, tools=tools, memory=FakeMemory(), sessions=InMemorySessionStore())

        out = await engine.run(session_id="cli:json-args", user_text="say hi")
        assert out.text == "done"
        assert tools.execute_calls == [
            {
                "name": "echo",
                "arguments": {"text": "hello"},
                "session_id": "cli:json-args",
                "channel": "cli",
                "user_id": "json-args",
                "requester_id": "",
            }
        ]
        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert len(tool_rows) == 1
        assert tool_rows[0]["content"] == "echo:hello:cli:json-args"

    asyncio.run(_scenario())


def test_engine_rejects_invalid_tool_argument_payloads_before_dispatch() -> None:
    async def _scenario() -> None:
        provider = FakeInvalidToolArgumentsProvider()
        tools = ExecuteCaptureTools()
        engine = AgentEngine(
            provider=provider,
            tools=tools,
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
        )

        out = await engine.run(session_id="cli:bad-args", user_text="say hi")
        assert out.text == "done"
        assert tools.execute_calls == []
        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert len(tool_rows) == 1
        assert "tool_error:echo:tool_call_arguments_invalid_json" in str(tool_rows[0]["content"])

    asyncio.run(_scenario())


def test_engine_rejects_unknown_tool_names_before_dispatch() -> None:
    async def _scenario() -> None:
        provider = FakeUnknownToolNameProvider()
        tools = ExecuteCaptureTools()
        engine = AgentEngine(provider=provider, tools=tools, memory=FakeMemory(), sessions=InMemorySessionStore())

        out = await engine.run(session_id="cli:unknown-tool", user_text="say hi")
        assert out.text == "done"
        assert tools.execute_calls == []
        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert len(tool_rows) == 1
        assert "tool_error:ghost:tool_call_name_unknown" in str(tool_rows[0]["content"])
        metrics = engine.turn_metrics_snapshot()
        assert metrics["tool_calls_executed"] == 0

    asyncio.run(_scenario())


def test_engine_rejects_invalid_tool_names_before_dispatch() -> None:
    async def _scenario() -> None:
        provider = FakeInvalidToolNameProvider()
        tools = ExecuteCaptureTools()
        engine = AgentEngine(provider=provider, tools=tools, memory=FakeMemory(), sessions=InMemorySessionStore())

        out = await engine.run(session_id="cli:invalid-tool-name", user_text="say hi")
        assert out.text == "done"
        assert tools.execute_calls == []
        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert len(tool_rows) == 1
        assert "tool_error:echo_bad:tool_call_name_invalid_format" in str(tool_rows[0]["content"])
        metrics = engine.turn_metrics_snapshot()
        assert metrics["tool_calls_executed"] == 0

    asyncio.run(_scenario())


def test_engine_normalizes_dict_provider_payloads_and_tuple_tool_calls() -> None:
    async def _scenario() -> None:
        provider = FakeDictProviderPayloadProvider()
        tools = ExecuteCaptureTools()
        engine = AgentEngine(provider=provider, tools=tools)

        out = await engine.run(session_id="cli:dict-provider", user_text="say hi")
        assert out.text == "done"
        assert tools.execute_calls == [
            {
                "name": "echo",
                "arguments": {"text": "hello"},
                "session_id": "cli:dict-provider",
                "channel": "cli",
                "user_id": "dict-provider",
                "requester_id": "",
            }
        ]
        metrics = engine.turn_metrics_snapshot()
        assert metrics["last_model"] == "fake/model"

    asyncio.run(_scenario())


def test_engine_ignores_invalid_tool_call_containers_from_provider() -> None:
    async def _scenario() -> None:
        tools = ExecuteCaptureTools()
        engine = AgentEngine(provider=FakeInvalidToolCallsContainerProvider(), tools=tools)

        out = await engine.run(session_id="cli:bad-tool-calls", user_text="say hi")
        assert out.text == "done"
        assert tools.execute_calls == []
        metrics = engine.turn_metrics_snapshot()
        assert metrics["tool_calls_executed"] == 0
        assert metrics["last_model"] == "fake/model"

    asyncio.run(_scenario())


def test_engine_normalizes_duplicate_and_invalid_tool_call_ids() -> None:
    async def _scenario() -> None:
        provider = FakeDuplicateAndInvalidToolIdProvider()
        tools = ExecuteCaptureTools()
        engine = AgentEngine(
            provider=provider,
            tools=tools,
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            subagents=FakeSubagentManagerEmpty(),
        )

        out = await engine.run(session_id="cli:dup-tool-id", user_text="say hi")
        assert out.text == "done"
        assert [call["arguments"]["text"] for call in tools.execute_calls] == ["first", "second", "third"]

        assistant_rows = [
            row
            for row in provider.snapshots[1]
            if row.get("role") == "assistant" and isinstance(row.get("tool_calls"), list)
        ]
        assert len(assistant_rows) == 1
        assistant_tool_calls = assistant_rows[0]["tool_calls"]
        assert [item["id"] for item in assistant_tool_calls] == ["dup", "call_1", "call_2"]

        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert [row["tool_call_id"] for row in tool_rows] == ["dup", "call_1", "call_2"]

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


def test_engine_identity_enforcer_blocks_persistence_on_residual_vendor_contamination(tmp_path: Path) -> None:
    async def _scenario() -> None:
        workspace = tmp_path / "ws"
        prompt_builder = PromptBuilder(workspace)
        prompt_builder.workspace_loader.bootstrap()
        memory = FakeMemoryWithAsyncMemorize()
        sessions = SessionStoreRecorder()
        provider_text = "Deployment summary ready. Generated by OpenAI for review."
        engine = AgentEngine(
            provider=FakeFixedTextProvider(provider_text),
            tools=FakeTools(),
            memory=memory,
            sessions=sessions,
            prompt_builder=prompt_builder,
        )

        out = await engine.run(session_id="cli:identity-enforcer", user_text="Summarize deployment notes")
        assert "Generated by OpenAI" in out.text
        assert memory.memorize_calls == []
        assert sessions.rows == [
            {
                "session_id": "cli:identity-enforcer",
                "role": "user",
                "content": "Summarize deployment notes",
            }
        ]

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


def test_engine_subagent_digest_mentions_continuation_context_between_executions() -> None:
    async def _scenario() -> None:
        subagents = FakeSubagentManagerForDigestWithContinuation()
        engine = AgentEngine(
            provider=FakePromptCaptureProvider(),
            tools=FakeTools(),
            memory=FakeMemory([]),
            subagents=subagents,
            synthesizer=SubagentSynthesizer(),
        )

        out = await engine.run(session_id="cli:owner", user_text="hello")
        assert out.text.count("[Subagent Digest]") == 1
        assert "session=cli:owner:subagent" in out.text
        assert "continued from current:cli:owner:subagent -> blocker triaged" in out.text
        assert "result=Confirmed owner and next action." in out.text

    asyncio.run(_scenario())


def test_engine_subagent_digest_mentions_parallel_group_metadata() -> None:
    async def _scenario() -> None:
        subagents = FakeSubagentManagerForParallelDigest()
        engine = AgentEngine(
            provider=FakePromptCaptureProvider(),
            tools=FakeTools(),
            memory=FakeMemory([]),
            subagents=subagents,
            synthesizer=SubagentSynthesizer(),
        )

        out = await engine.run(session_id="cli:owner", user_text="hello")
        assert out.text.count("[Subagent Digest]") == 1
        assert "parallel grp123456789 [2/2 branches]" in out.text
        assert "session=cli:owner:subagent:1" in out.text
        assert "session=cli:owner:subagent:2" in out.text
        assert "group=grp123456789#1/2" in out.text
        assert "group=grp123456789#2/2" in out.text

    asyncio.run(_scenario())


def test_engine_persists_parallel_group_summary_in_subagent_digest_memory() -> None:
    async def _scenario() -> None:
        subagents = FakeSubagentManagerForParallelDigest()
        memory = FakeMemoryWithSubagentDigestPersistence()
        engine = AgentEngine(
            provider=FakePromptCaptureProvider(),
            tools=FakeTools(),
            memory=memory,
            subagents=subagents,
            synthesizer=SubagentSynthesizer(),
        )

        out = await engine.run(session_id="cli:owner", user_text="hello")
        assert out.text.count("[Subagent Digest]") == 1
        digest_rows = [row for row in memory.memorize_calls if row["source"] == "subagent-digest:cli:owner"]
        assert len(digest_rows) == 1
        digest_row = digest_rows[0]
        assert "Parallel group grp123456789: 2/2 sessions" in str(digest_row["text"])
        assert digest_row["metadata"]["subagent_parallel_group_count"] == 1
        assert digest_row["metadata"]["subagent_parallel_groups"][0]["group_id"] == "grp123456789"
        assert digest_row["metadata"]["subagent_parallel_groups"][0]["group_size"] == 2
        assert digest_row["metadata"]["subagent_parallel_groups"][0]["target_sessions"] == [
            "cli:owner:subagent:1",
            "cli:owner:subagent:2",
        ]

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
        engine = AgentEngine(provider=provider, tools=registry, sessions=InMemorySessionStore())

        out = await engine.run(session_id="telegram:tool-safety-block", user_text="run")
        assert out.text == "done"
        assert provider.calls == 2
        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert len(tool_rows) == 1
        content = str(tool_rows[0].get("content", ""))
        assert "tool_error:exec:tool_blocked_by_safety_policy:exec:telegram" in content

    asyncio.run(_scenario())


def test_engine_surfaces_tool_approval_requirement_as_safe_tool_result() -> None:
    async def _scenario() -> None:
        provider = FakeBlockedToolProvider()
        registry = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                approval_specifiers=["exec"],
                approval_channels=["telegram"],
                blocked_channels=[],
                allowed_channels=[],
            )
        )
        registry.register(ExecNoopTool())
        engine = AgentEngine(provider=provider, tools=registry, sessions=InMemorySessionStore())

        out = await engine.run(session_id="telegram:tool-approval-required", user_text="run")
        assert out.text == "done"
        assert provider.calls == 2
        tool_rows = [row for row in provider.snapshots[1] if row.get("role") == "tool"]
        assert len(tool_rows) == 1
        content = str(tool_rows[0].get("content", ""))
        assert "tool_error:exec:tool_requires_approval:exec:telegram" in content

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


def test_engine_injects_compressed_history_summary_before_recent_turns() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        prompt_builder = PromptBuilder(context_token_budget=220)

        class _Sessions:
            def __init__(self) -> None:
                self.rows = {
                    "cli:compressed-history": [
                        {"role": "user", "content": "older request " * 35},
                        {"role": "assistant", "content": "older answer " * 35},
                        {"role": "user", "content": "recent request " * 35},
                        {"role": "assistant", "content": "recent answer " * 35},
                    ]
                }

            def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
                return list(self.rows.get(session_id, []))[-limit:]

            def append(self, session_id: str, role: str, content: str) -> None:
                self.rows.setdefault(session_id, []).append({"role": role, "content": content})

        sessions = _Sessions()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            prompt_builder=prompt_builder,
        )

        out = await engine.run(session_id="cli:compressed-history", user_text="continue")

        assert out.text == "ok"
        snapshot = provider.snapshots[0]
        summary_index = next(
            idx for idx, row in enumerate(snapshot) if row["role"] == "system" and "[Compressed Session History]" in row["content"]
        )
        recent_index = next(
            idx for idx, row in enumerate(snapshot) if row["role"] == "assistant" and "recent answer" in row["content"]
        )
        assert summary_index < recent_index

    asyncio.run(_scenario())


def test_engine_injects_allowlisted_runtime_metadata_into_prompt_context() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=InMemorySessionStore(),
            memory=FakeMemory(),
        )

        out = await engine.run(
            session_id="telegram:42",
            user_text="continue",
            channel="telegram",
            chat_id="42",
            runtime_metadata={
                "message_id": "m-42",
                "message_thread_id": 13,
                "thread_ts": "1700.3",
                "reply_to_text": "parent context",
                "command": "focus",
                "command_args": "session-1",
                "is_dm": True,
                "is_forum": True,
                "callback_signed": True,
                "custom_id": "approve:123",
                "media_type": "voice",
                "bridge_payload": {"raw": "ignore me"},
            },
        )

        assert out.text == "ok"
        final_user_message = provider.snapshots[0][-1]
        assert final_user_message["role"] == "user"
        runtime_context = str(final_user_message.get("content", ""))
        assert runtime_context.endswith("continue")
        assert "[Runtime Context" in runtime_context
        assert "Message ID: m-42" in runtime_context
        assert "Thread ID: 13" in runtime_context
        assert "Thread TS: 1700.3" in runtime_context
        assert "Reply-To Text: parent context" in runtime_context
        assert "Command: focus" in runtime_context
        assert "Command Args: session-1" in runtime_context
        assert "Is DM: true" in runtime_context
        assert "Is Forum: true" in runtime_context
        assert "Callback Signed: true" in runtime_context
        assert "Custom ID: approve:123" in runtime_context
        assert "Media Type: voice" in runtime_context
        assert "bridge_payload" not in runtime_context
        assert "ignore me" not in runtime_context

    asyncio.run(_scenario())


def test_engine_stream_run_uses_shaped_prompt_memory_history_and_runtime_context() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingPromptCaptureProvider("ok")
        memory = FakeMemory(
            [
                MemoryRecord(
                    id="a1b2c3d4e5f6",
                    text="Remember the thread context.",
                    source="session:telegram:42",
                    created_at="2026-03-04T12:00:00+00:00",
                )
            ]
        )
        sessions = InMemorySessionStore()
        sessions.append("telegram:42", "user", "older request")
        sessions.append("telegram:42", "assistant", "older answer")
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory=memory,
        )

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="telegram:42",
                user_text="continue",
                channel="telegram",
                chat_id="42",
                runtime_metadata={
                    "message_thread_id": 13,
                    "reply_to_text": "parent context",
                },
            )
        ]

        assert "".join(chunk.text for chunk in chunks) == "ok"
        assert provider.stream_calls == 1
        snapshot = provider.snapshots[0]
        memory_sections = [row for row in snapshot if row.get("role") == "system" and "[Memory]" in str(row.get("content", ""))]
        assert memory_sections
        assert any(row.get("role") == "assistant" and "older answer" in str(row.get("content", "")) for row in snapshot)
        final_user_message = snapshot[-1]
        assert final_user_message["role"] == "user"
        merged_content = str(final_user_message.get("content", ""))
        assert merged_content.endswith("continue")
        assert "[Runtime Context" in merged_content
        assert "Thread ID: 13" in merged_content
        assert "Reply-To Text: parent context" in merged_content

    asyncio.run(_scenario())


def test_engine_run_merges_runtime_context_into_single_current_user_message() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
        )

        out = await engine.run(
            session_id="telegram:42",
            user_text="hello",
            channel="telegram",
            chat_id="42",
            runtime_metadata={"reply_to_message_id": "7"},
        )

        assert out.text == "ok"
        snapshot = provider.snapshots[0]
        user_rows = [row for row in snapshot if row.get("role") == "user"]
        assert user_rows
        final_user_message = user_rows[-1]
        content = str(final_user_message.get("content", ""))
        assert content.endswith("hello")
        assert "[Runtime Context" in content
        assert "Reply-To Message ID: 7" in content
        if len(user_rows) >= 2:
            assert "[Runtime Context" not in str(user_rows[-2].get("content", ""))

    asyncio.run(_scenario())


def test_engine_stream_run_persists_user_and_assistant_messages_after_completion() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingPromptCaptureProvider("pong")
        sessions = SessionStoreRecorder()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory=FakeMemory(),
        )

        chunks = [chunk async for chunk in await engine.stream_run(session_id="cli:stream", user_text="ping")]

        assert "".join(chunk.text for chunk in chunks) == "pong"
        assert sessions.rows == [
            {"session_id": "cli:stream", "role": "user", "content": "ping"},
            {"session_id": "cli:stream", "role": "assistant", "content": "pong"},
        ]

    asyncio.run(_scenario())


def test_engine_stream_run_persists_empty_completion_turn() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingPromptCaptureProvider("")
        sessions = SessionStoreRecorder()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory=FakeMemory(),
        )

        chunks = [chunk async for chunk in await engine.stream_run(session_id="cli:stream-empty", user_text="ping")]

        assert chunks == [ProviderChunk(text="", accumulated="", done=True)]
        assert sessions.rows == [
            {"session_id": "cli:stream-empty", "role": "user", "content": "ping"},
            {"session_id": "cli:stream-empty", "role": "assistant", "content": ""},
        ]

    asyncio.run(_scenario())


def test_engine_stream_run_records_working_memory_for_completed_turns() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingPromptCaptureProvider("ok")
        memory = FakeMemoryWithWorkingSetCapture()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=InMemorySessionStore(),
            memory=memory,
        )

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="telegram:42",
                user_text="hello there",
                channel="telegram",
                chat_id="42",
            )
        ]

        assert "".join(chunk.text for chunk in chunks) == "ok"
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


def test_engine_stream_run_prefers_batch_working_memory_persistence_when_available() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingPromptCaptureProvider("ok")
        memory = FakeMemoryWithWorkingSetBatchCapture()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=InMemorySessionStore(),
            memory=memory,
        )

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="telegram:42",
                user_text="hello there",
                channel="telegram",
                chat_id="42",
            )
        ]

        assert "".join(chunk.text for chunk in chunks) == "ok"
        assert memory.batch_calls == [
            {
                "session_id": "telegram:42",
                "messages": [
                    {"role": "user", "content": "hello there"},
                    {"role": "assistant", "content": "ok"},
                ],
                "user_id": "42",
                "metadata": {"channel": "telegram"},
                "allow_promotion": True,
            }
        ]
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


def test_engine_stream_run_memorizes_completed_turn_with_runtime_user_context() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingPromptCaptureProvider("ok")
        memory = FakeMemoryWithContextKwargs()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=InMemorySessionStore(),
            memory=memory,
        )

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="telegram:42",
                user_text="remember this",
                channel="telegram",
                chat_id="42",
            )
        ]

        assert "".join(chunk.text for chunk in chunks) == "ok"
        assert memory.memorize_calls == [
            {
                "messages": [
                    {"role": "user", "content": "remember this"},
                    {"role": "assistant", "content": "ok"},
                ],
                "source": "session:telegram:42",
                "user_id": "42",
                "shared": False,
            }
        ]

    asyncio.run(_scenario())


def test_engine_stream_run_skips_assistant_persistence_after_provider_error_chunk() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingErrorProvider()
        memory = FakeMemoryWithAsyncMemorize()
        sessions = SessionStoreRecorder()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory=memory,
        )

        chunks = [chunk async for chunk in await engine.stream_run(session_id="cli:stream-error", user_text="ping")]

        assert chunks == [ProviderChunk(text="", accumulated="", done=True, error="provider_stream_error:boom")]
        assert sessions.rows == [
            {"session_id": "cli:stream-error", "role": "user", "content": "ping"},
        ]
        assert memory.memorize_calls == []
        assert memory.consolidate_calls == 0

    asyncio.run(_scenario())


def test_engine_stream_run_persists_degraded_completion_turn() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingDegradedProvider()
        sessions = SessionStoreRecorder()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory=FakeMemory(),
        )

        chunks = [chunk async for chunk in await engine.stream_run(session_id="cli:stream-degraded", user_text="ping")]

        assert chunks == [
            ProviderChunk(text="o", accumulated="o", done=False),
            ProviderChunk(text="k", accumulated="ok", done=True, degraded=True),
        ]
        assert sessions.rows == [
            {"session_id": "cli:stream-degraded", "role": "user", "content": "ping"},
            {"session_id": "cli:stream-degraded", "role": "assistant", "content": "ok"},
        ]

    asyncio.run(_scenario())


def test_engine_run_defers_memory_persistence_until_after_transcript_write() -> None:
    async def _scenario() -> None:
        provider = FakeFixedTextProvider("pong")
        memory = FakeMemoryWithDeferredTurnPersistence()
        sessions = SessionStoreRecorder()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory=memory,
        )

        first = await engine.run(session_id="cli:deferred", user_text="ping")
        assert first.text == "pong"
        assert sessions.rows == [
            {"session_id": "cli:deferred", "role": "user", "content": "ping"},
            {"session_id": "cli:deferred", "role": "assistant", "content": "pong"},
        ]
        assert memory.memorize_calls == []
        await asyncio.wait_for(memory.memorize_started.wait(), timeout=1.0)

        second_started = asyncio.Event()

        class _SecondProvider(FakeFixedTextProvider):
            async def complete(self, *, messages, tools):
                second_started.set()
                return await super().complete(messages=messages, tools=tools)

        engine.provider = _SecondProvider("second")
        second_task = asyncio.create_task(engine.run(session_id="cli:deferred", user_text="again"))
        await asyncio.sleep(0.05)
        assert second_started.is_set() is False

        memory.allow_memorize.set()
        second = await asyncio.wait_for(second_task, timeout=1.0)
        assert second.text == "second"
        assert second_started.is_set() is True
        assert memory.memorize_calls[0] == {
            "messages": [
                {"role": "user", "content": "ping"},
                {"role": "assistant", "content": "pong"},
            ],
            "text": None,
            "source": "session:cli:deferred",
            "user_id": "deferred",
            "shared": False,
            "metadata": {},
            "reasoning_layer": None,
            "memory_type": None,
            "happened_at": None,
        }
        assert len(memory.memorize_calls) >= 1
        assert memory.working_set_writes[:2] == [
            {
                "session_id": "cli:deferred",
                "role": "user",
                "content": "ping",
                "user_id": "deferred",
                "metadata": {"channel": "cli"},
                "allow_promotion": True,
            },
            {
                "session_id": "cli:deferred",
                "role": "assistant",
                "content": "pong",
                "user_id": "deferred",
                "metadata": {"channel": "cli"},
                "allow_promotion": True,
            },
        ]
        await engine.drain_turn_persistence()

    asyncio.run(_scenario())


def test_engine_deferred_working_memory_does_not_block_other_sessions() -> None:
    async def _scenario() -> None:
        provider = FakeFixedTextProvider("pong")
        memory = FakeMemoryWithSlowDeferredWorkingSet(delay_s=0.35)
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=InMemorySessionStore(),
            memory=memory,
        )

        first = await engine.run(session_id="cli:one", user_text="first")
        assert first.text == "pong"

        started_at = time.perf_counter()
        await asyncio.sleep(0)
        second = await asyncio.wait_for(engine.run(session_id="cli:two", user_text="second"), timeout=1.0)
        elapsed = time.perf_counter() - started_at

        assert second.text == "pong"
        assert elapsed < 0.25

        await engine.drain_turn_persistence()
        assert [row["session_id"] for row in memory.batch_calls] == ["cli:one", "cli:two"]
        assert memory.memorize_calls[0]["source"] == "session:cli:one"
        assert memory.memorize_calls[1]["source"] == "session:cli:two"

    asyncio.run(_scenario())


def test_engine_stream_run_serializes_same_session_streams_with_lock() -> None:
    async def _scenario() -> None:
        provider = LockTrackingStreamingProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=InMemorySessionStore(),
            memory=FakeMemory(),
        )

        async def _consume() -> str:
            parts: list[str] = []
            async for chunk in await engine.stream_run(
                session_id="telegram:42",
                user_text="go",
                channel="telegram",
                chat_id="42",
            ):
                parts.append(chunk.text)
            return "".join(parts)

        first, second = await asyncio.gather(_consume(), _consume())
        assert first == "ok"
        assert second == "ok"
        assert provider.max_active == 1

    asyncio.run(_scenario())


def test_engine_stream_run_stops_mid_stream_and_skips_assistant_persistence() -> None:
    async def _scenario() -> None:
        provider = StoppableStreamingProvider()
        memory = FakeMemoryWithAsyncMemorize()
        sessions = SessionStoreRecorder()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory=memory,
        )

        chunks: list[ProviderChunk] = []
        async for chunk in await engine.stream_run(session_id="cli:stream-stop", user_text="ping"):
            chunks.append(chunk)
            if len(chunks) == 1:
                assert engine.request_stop("cli:stream-stop") is True

        assert chunks == [
            ProviderChunk(text="o", accumulated="o", done=False),
            ProviderChunk(text="", accumulated="o", done=True, error="engine_stop_requested"),
        ]
        assert provider.closed is True
        assert provider.yielded_second is False
        assert sessions.rows == [
            {"session_id": "cli:stream-stop", "role": "user", "content": "ping"},
        ]
        assert memory.memorize_calls == []
        assert memory.consolidate_calls == 0
        assert engine._stop_requested(session_id="cli:stream-stop", stop_event=None) is False

    asyncio.run(_scenario())


def test_engine_stream_run_falls_back_to_full_run_for_live_lookup_turns() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingWebToolProvider()
        sessions = SessionStoreRecorder()
        engine = AgentEngine(
            provider=provider,
            tools=FakeWebSearchTools(),
            sessions=sessions,
            memory=FakeMemory(),
        )

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="cli:stream",
                user_text="Pesquise na internet sobre OpenClaw",
            )
        ]

        final_text = "".join(chunk.text for chunk in chunks)
        assert final_text.startswith("OpenClaw is an autonomous assistant stack.")
        assert "Sources:" in final_text
        assert provider.stream_calls == 0
        assert provider.calls == 2
        assert chunks == [
            ProviderChunk(
                text=final_text,
                accumulated=final_text,
                done=True,
            )
        ]
        assert sessions.rows == [
            {"session_id": "cli:stream", "role": "user", "content": "Pesquise na internet sobre OpenClaw"},
            {
                "session_id": "cli:stream",
                "role": "assistant",
                "content": final_text,
            },
        ]

    asyncio.run(_scenario())


def test_engine_stream_run_falls_back_to_full_run_for_explicit_github_skill_turns() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingPromptCaptureProvider("stream")
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["github"]),
        )
        seen: list[dict[str, Any]] = []

        async def _fallback_run(
            *,
            session_id: str,
            user_text: str,
            channel: str | None = None,
            chat_id: str | None = None,
            runtime_metadata: dict[str, Any] | None = None,
        ) -> ProviderResult:
            seen.append(
                {
                    "session_id": session_id,
                    "user_text": user_text,
                    "channel": channel,
                    "chat_id": chat_id,
                    "runtime_metadata": runtime_metadata,
                }
            )
            return ProviderResult(text="github-result", tool_calls=[], model="fake/model")

        engine.run = _fallback_run  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="cli:stream-gh",
                user_text="check the GitHub issue status for this repo",
                channel="telegram",
                chat_id="42",
                runtime_metadata={"reply_to_message_id": "7"},
            )
        ]

        assert provider.stream_calls == 0
        assert chunks == [
            ProviderChunk(text="github-result", accumulated="github-result", done=True)
        ]
        assert seen == [
            {
                "session_id": "cli:stream-gh",
                "user_text": "check the GitHub issue status for this repo",
                "channel": "telegram",
                "chat_id": "42",
                "runtime_metadata": {"reply_to_message_id": "7"},
            }
        ]

    asyncio.run(_scenario())


def test_engine_stream_run_falls_back_to_full_run_for_summarize_sources() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingPromptCaptureProvider("stream-summary")
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["summarize"]),
        )
        seen: list[dict[str, Any]] = []

        async def _fallback_run(
            *,
            session_id: str,
            user_text: str,
            channel: str | None = None,
            chat_id: str | None = None,
            runtime_metadata: dict[str, Any] | None = None,
        ) -> ProviderResult:
            seen.append(
                {
                    "session_id": session_id,
                    "user_text": user_text,
                    "channel": channel,
                    "chat_id": chat_id,
                    "runtime_metadata": runtime_metadata,
                }
            )
            return ProviderResult(text="summary-result", tool_calls=[], model="fake/model")

        engine.run = _fallback_run  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="cli:stream-summary",
                user_text="summarize docs/architecture.pdf",
                channel="telegram",
                chat_id="42",
                runtime_metadata={"reply_to_message_id": "8"},
            )
        ]

        assert provider.stream_calls == 0
        assert chunks == [
            ProviderChunk(text="summary-result", accumulated="summary-result", done=True)
        ]
        assert seen == [
            {
                "session_id": "cli:stream-summary",
                "user_text": "summarize docs/architecture.pdf",
                "channel": "telegram",
                "chat_id": "42",
                "runtime_metadata": {"reply_to_message_id": "8"},
            }
        ]

        provider_url = FakeStreamingPromptCaptureProvider("stream-summary-url")
        engine_url = AgentEngine(
            provider=provider_url,
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["summarize"]),
        )
        seen_url: list[str] = []

        async def _fallback_run_url(
            *,
            session_id: str,
            user_text: str,
            channel: str | None = None,
            chat_id: str | None = None,
            runtime_metadata: dict[str, Any] | None = None,
        ) -> ProviderResult:
            del session_id, channel, chat_id, runtime_metadata
            seen_url.append(user_text)
            return ProviderResult(text="summary-url-result", tool_calls=[], model="fake/model")

        engine_url.run = _fallback_run_url  # type: ignore[method-assign]

        url_chunks = [
            chunk
            async for chunk in await engine_url.stream_run(
                session_id="cli:stream-summary-url",
                user_text="summarize https://example.com/article",
            )
        ]

        assert provider_url.stream_calls == 0
        assert "".join(chunk.text for chunk in url_chunks) == "summary-url-result"
        assert seen_url == ["summarize https://example.com/article"]

    asyncio.run(_scenario())


def test_engine_stream_run_falls_back_to_full_run_for_explicit_web_search_requests() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingWebToolProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeWebSearchTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["web-search"]),
        )
        seen: list[dict[str, Any]] = []

        async def _fallback_run(
            *,
            session_id: str,
            user_text: str,
            channel: str | None = None,
            chat_id: str | None = None,
            runtime_metadata: dict[str, Any] | None = None,
        ) -> ProviderResult:
            seen.append(
                {
                    "session_id": session_id,
                    "user_text": user_text,
                    "channel": channel,
                    "chat_id": chat_id,
                    "runtime_metadata": runtime_metadata,
                }
            )
            return ProviderResult(text="web-search-result", tool_calls=[], model="fake/model")

        engine.run = _fallback_run  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="cli:stream-web-search",
                user_text="use the web-search skill to find current docs",
                channel="telegram",
                chat_id="42",
                runtime_metadata={"reply_to_message_id": "9"},
            )
        ]

        assert provider.stream_calls == 0
        assert chunks == [ProviderChunk(text="web-search-result", accumulated="web-search-result", done=True)]
        assert seen == [
            {
                "session_id": "cli:stream-web-search",
                "user_text": "use the web-search skill to find current docs",
                "channel": "telegram",
                "chat_id": "42",
                "runtime_metadata": {"reply_to_message_id": "9"},
            }
        ]

    asyncio.run(_scenario())


def test_engine_stream_run_falls_back_when_provider_stream_requires_full_run_before_text() -> None:
    async def _scenario() -> None:
        provider = FakeStreamingToolSignalProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeWebSearchTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
        )
        seen: list[dict[str, Any]] = []

        async def _fallback_run(
            *,
            session_id: str,
            user_text: str,
            channel: str | None = None,
            chat_id: str | None = None,
            runtime_metadata: dict[str, Any] | None = None,
        ) -> ProviderResult:
            seen.append(
                {
                    "session_id": session_id,
                    "user_text": user_text,
                    "channel": channel,
                    "chat_id": chat_id,
                    "runtime_metadata": runtime_metadata,
                }
            )
            return ProviderResult(text="tool-result", tool_calls=[], model="fake/model")

        engine.run = _fallback_run  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="cli:stream-tools",
                user_text="search for OpenClaw docs",
                channel="telegram",
                chat_id="42",
                runtime_metadata={"reply_to_message_id": "10"},
            )
        ]

        assert provider.stream_calls == 1
        assert provider.tools_seen == FakeWebSearchTools().schema()
        assert chunks == [ProviderChunk(text="tool-result", accumulated="tool-result", done=True)]
        assert seen == [
            {
                "session_id": "cli:stream-tools",
                "user_text": "search for OpenClaw docs",
                "channel": "telegram",
                "chat_id": "42",
                "runtime_metadata": {"reply_to_message_id": "10"},
            }
        ]

    asyncio.run(_scenario())


def test_engine_stream_run_falls_back_after_whitespace_only_prelude() -> None:
    async def _scenario() -> None:
        provider = FakeWhitespacePreludeToolSignalProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeWebSearchTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
        )
        seen: list[dict[str, Any]] = []

        async def _fallback_run(
            *,
            session_id: str,
            user_text: str,
            channel: str | None = None,
            chat_id: str | None = None,
            runtime_metadata: dict[str, Any] | None = None,
        ) -> ProviderResult:
            seen.append(
                {
                    "session_id": session_id,
                    "user_text": user_text,
                    "channel": channel,
                    "chat_id": chat_id,
                    "runtime_metadata": runtime_metadata,
                }
            )
            return ProviderResult(text="tool-result", tool_calls=[], model="fake/model")

        engine.run = _fallback_run  # type: ignore[method-assign]

        chunks = [
            chunk
            async for chunk in await engine.stream_run(
                session_id="cli:stream-tools-whitespace",
                user_text="search for OpenClaw docs",
                channel="telegram",
                chat_id="42",
                runtime_metadata={"reply_to_message_id": "11"},
            )
        ]

        assert provider.stream_calls == 1
        assert provider.tools_seen == FakeWebSearchTools().schema()
        assert chunks == [
            ProviderChunk(text=" \n\t", accumulated=" \n\t", done=False),
            ProviderChunk(text="tool-result", accumulated="tool-result", done=True),
        ]
        assert seen == [
            {
                "session_id": "cli:stream-tools-whitespace",
                "user_text": "search for OpenClaw docs",
                "channel": "telegram",
                "chat_id": "42",
                "runtime_metadata": {"reply_to_message_id": "11"},
            }
        ]

    asyncio.run(_scenario())


def test_engine_stream_run_keeps_provider_stream_for_explanatory_github_and_docker_prompts() -> None:
    async def _scenario() -> None:
        github_provider = FakeStreamingPromptCaptureProvider("stream-gh")
        github_engine = AgentEngine(
            provider=github_provider,
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["github"]),
        )

        github_chunks = [
            chunk
            async for chunk in await github_engine.stream_run(
                session_id="cli:stream-gh-topic",
                user_text="how do GitHub workflows work?",
            )
        ]

        docker_provider = FakeStreamingPromptCaptureProvider("stream-docker")
        docker_engine = AgentEngine(
            provider=docker_provider,
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["docker"]),
        )

        docker_chunks = [
            chunk
            async for chunk in await docker_engine.stream_run(
                session_id="cli:stream-docker-topic",
                user_text="what is a Docker image?",
            )
        ]

        summarize_provider = FakeStreamingPromptCaptureProvider("stream-summary")
        summarize_engine = AgentEngine(
            provider=summarize_provider,
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["summarize"]),
        )

        summarize_chunks = [
            chunk
            async for chunk in await summarize_engine.stream_run(
                session_id="cli:stream-summary-topic",
                user_text="resuma isso em 3 linhas",
            )
        ]

        summarize_repo_chunks = [
            chunk
            async for chunk in await summarize_engine.stream_run(
                session_id="cli:stream-summary-repo",
                user_text="summarize owner/repo in 3 bullet points",
            )
        ]

        assert "".join(chunk.text for chunk in github_chunks) == "stream-gh"
        assert github_provider.stream_calls == 1
        assert "".join(chunk.text for chunk in docker_chunks) == "stream-docker"
        assert docker_provider.stream_calls == 1
        assert "".join(chunk.text for chunk in summarize_chunks) == "stream-summary"
        assert "".join(chunk.text for chunk in summarize_repo_chunks) == "stream-summary"
        assert summarize_provider.stream_calls == 2

        web_search_provider = FakeStreamingPromptCaptureProvider("stream-web")
        web_search_engine = AgentEngine(
            provider=web_search_provider,
            tools=FakeWebSearchTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["web-search"]),
        )
        web_search_chunks = [
            chunk
            async for chunk in await web_search_engine.stream_run(
                session_id="cli:stream-web-search-topic",
                user_text="explain how the web-search skill works",
            )
        ]

        assert "".join(chunk.text for chunk in web_search_chunks) == "stream-web"
        assert web_search_provider.stream_calls == 1

    asyncio.run(_scenario())


def test_engine_stream_requires_full_run_for_live_lookup_and_explicit_skill_routes() -> None:
    assert AgentEngine._stream_requires_full_run(
        user_text="Qual a temperatura em Suzano, SP?",
        live_lookup_required=True,
    )
    assert AgentEngine._stream_requires_full_run(
        user_text="check GitHub issue #42 for this repo",
        live_lookup_required=False,
        available_skill_names={"github"},
    )
    assert AgentEngine._stream_requires_full_run(
        user_text="restart the docker compose stack",
        live_lookup_required=False,
        available_skill_names={"docker"},
    )
    assert AgentEngine._stream_requires_full_run(
        user_text="summarize docs/architecture.pdf",
        live_lookup_required=False,
        available_skill_names={"summarize"},
    )
    assert AgentEngine._stream_requires_full_run(
        user_text="summarize https://example.com/article",
        live_lookup_required=False,
        available_skill_names={"summarize"},
    )
    assert AgentEngine._stream_requires_full_run(
        user_text="use the summarize skill on https://example.com",
        live_lookup_required=False,
        available_skill_names={"summarize"},
    )
    assert AgentEngine._stream_requires_full_run(
        user_text="use the web-search skill to find docs",
        live_lookup_required=False,
        available_tool_names={"web_search"},
        available_skill_names={"web-search"},
    )
    assert not AgentEngine._stream_requires_full_run(
        user_text="how do GitHub workflows work?",
        live_lookup_required=False,
        available_skill_names={"github"},
    )
    assert not AgentEngine._stream_requires_full_run(
        user_text="what is a Docker image?",
        live_lookup_required=False,
        available_skill_names={"docker"},
    )
    assert not AgentEngine._stream_requires_full_run(
        user_text="Resume isso em 3 linhas",
        live_lookup_required=False,
        available_skill_names={"summarize"},
    )
    assert not AgentEngine._stream_requires_full_run(
        user_text="summarize owner/repo in 3 bullet points",
        live_lookup_required=False,
        available_skill_names={"summarize"},
    )
    assert not AgentEngine._stream_requires_full_run(
        user_text="explain how the web-search skill works",
        live_lookup_required=False,
        available_tool_names={"web_search"},
        available_skill_names={"web-search"},
    )


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


def test_engine_injects_async_emotional_guidance_as_system_message() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithAsyncEmotionGuidance()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:emotion-async", user_text="I am blocked")
        assert out.text == "ok"

        first_prompt = provider.snapshots[0]
        guidance_rows = [
            row
            for row in first_prompt
            if row.get("role") == "system"
            and "Async guidance: keep the reply calm and direct." in str(row.get("content", ""))
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


def test_engine_memory_planner_uses_async_recommended_search_limit_from_integration_policy() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithAsyncPolicySearch(
            rows=[
                MemoryRecord(
                    id="ctx-limit-async-1",
                    text="Timezone is America/Sao_Paulo.",
                    source="session:telegram:42",
                    created_at="2026-03-04T12:00:00+00:00",
                )
            ],
            search_limit=4,
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="telegram:42", user_text="what is my timezone preference")
        assert out.text == "ok"
        assert memory.policy_calls == [{"actor": "agent", "session_id": "telegram:42"}]
        assert memory.search_calls
        assert memory.search_calls[0]["limit"] == 4

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


def test_engine_skips_memory_persistence_when_async_integration_policy_blocks_write() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        memory = FakeMemoryWithAsyncWriteBlock()
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:async-write-blocked", user_text="remember this")
        assert out.text == "ok"
        assert memory.memorize_calls == []

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


def test_engine_memory_planner_expands_same_query_after_probe_when_no_rewrite_applies() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        query = "deployment blockers timeline"
        memory = FakePlannerMemory(
            {
                query: [
                    MemoryRecord(
                        id=f"probe-{idx}",
                        text=text,
                        source="session:cli:ops",
                        created_at=f"2026-03-04T12:0{idx}:00+00:00",
                    )
                    for idx, text in enumerate(
                        [
                            "Unrelated note one.",
                            "Unrelated note two.",
                            "Unrelated note three.",
                            "Unrelated note four.",
                            "Deployment blockers are database migration lag and API timeout budgets.",
                            "Deployment blockers also include missing rollback rehearsal.",
                        ],
                        start=1,
                    )
                ]
            }
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)

        out = await engine.run(session_id="cli:memory-probe-expand", user_text=query)
        assert out.text == "ok"
        assert memory.search_calls == [query, query, query]
        assert memory.search_call_details == [
            {
                "query": query,
                "limit": 4,
                "user_id": "memory-probe-expand",
                "session_id": "cli:memory-probe-expand",
                "include_shared": True,
            },
            {
                "query": query,
                "limit": 6,
                "user_id": "memory-probe-expand",
                "session_id": "cli:memory-probe-expand",
                "include_shared": True,
            },
            {
                "query": query,
                "limit": 12,
                "user_id": "memory-probe-expand",
                "session_id": "cli:memory-probe-expand",
                "include_shared": True,
            },
        ]

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
        assert memory.search_calls == [original_query, rewritten_query, rewritten_query]
        assert memory.search_call_details == [
            {
                "query": original_query,
                "limit": 4,
                "user_id": "next-query",
                "session_id": "cli:next-query",
                "include_shared": True,
            },
            {
                "query": rewritten_query,
                "limit": 6,
                "user_id": "next-query",
                "session_id": "cli:next-query",
                "include_shared": True,
            },
            {
                "query": rewritten_query,
                "limit": 12,
                "user_id": "next-query",
                "session_id": "cli:next-query",
                "include_shared": True,
            },
        ]

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


def test_engine_planner_merges_parent_subagent_digest_when_primary_memory_is_weak() -> None:
    provider = FakePromptCaptureProvider()
    query = "blocker timeline owner actions"
    memory = FakePlannerMemory(
        routes={
            query: [
                MemoryRecord(
                    id="plain-1",
                    text="blocker pending",
                    source="session:cli:owner",
                    created_at="2026-03-05T12:00:00+00:00",
                ),
                MemoryRecord(
                    id="digest-1",
                    text="blocker timeline owner next actions confirmed by delegated worker",
                    source="subagent-digest:cli:owner",
                    created_at="2026-03-05T12:05:00+00:00",
                    metadata={
                        "subagent_digest": True,
                        "subagent_parent_session_id": "cli:owner",
                    },
                ),
            ]
        },
        search_limit=1,
    )
    engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)
    run_log = bind_event("tests.engine.subagent-digest-planner")

    snippets = engine._plan_memory_snippets(
        session_id="cli:owner",
        user_id="u-1",
        user_text=query,
        run_log=run_log,
    )

    assert len(snippets) == 2
    assert "[src:subagent-digest:cli:owner]" in snippets[0]
    assert "[src:session:cli:owner]" in snippets[1]
    assert memory.search_call_details == [
        {
            "query": query,
            "limit": 1,
            "user_id": "u-1",
            "session_id": "cli:owner",
            "include_shared": True,
        },
        {
            "query": query,
            "limit": 3,
            "user_id": "u-1",
            "session_id": "cli:owner",
            "include_shared": True,
        },
    ]


def test_engine_planner_filters_foreign_subagent_digests_by_parent_session() -> None:
    provider = FakePromptCaptureProvider()
    query = "blocker timeline owner actions"
    memory = FakePlannerMemory(
        routes={
            query: [
                MemoryRecord(
                    id="plain-1",
                    text="blocker pending",
                    source="session:cli:owner",
                    created_at="2026-03-05T12:00:00+00:00",
                ),
                MemoryRecord(
                    id="foreign-digest",
                    text="blocker timeline owner actions from another parent",
                    source="subagent-digest:cli:other",
                    created_at="2026-03-05T12:04:00+00:00",
                    metadata={
                        "subagent_digest": True,
                        "subagent_parent_session_id": "cli:other",
                    },
                ),
                MemoryRecord(
                    id="local-digest",
                    text="blocker timeline owner next actions confirmed by delegated worker",
                    source="subagent-digest:cli:owner",
                    created_at="2026-03-05T12:05:00+00:00",
                    metadata={
                        "subagent_digest": True,
                        "subagent_parent_session_id": "cli:owner",
                    },
                ),
            ]
        },
        search_limit=1,
    )
    engine = AgentEngine(provider=provider, tools=FakeTools(), memory=memory)
    run_log = bind_event("tests.engine.subagent-digest-scope")

    snippets = engine._plan_memory_snippets(
        session_id="cli:owner",
        user_id="u-1",
        user_text=query,
        run_log=run_log,
    )

    assert any("[src:subagent-digest:cli:owner]" in item for item in snippets)
    assert all("[src:subagent-digest:cli:other]" not in item for item in snippets)


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
        engine = AgentEngine(
            provider=provider,
            tools=tools,
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            subagents=FakeSubagentManagerEmpty(),
            max_tool_result_chars=32,
        )
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


def test_engine_sync_progress_hook_failures_do_not_abort_turn() -> None:
    async def _scenario() -> None:
        provider = FakeLongToolProvider()
        engine = AgentEngine(provider=provider, tools=FakeTools())
        stages: list[str] = []

        def _hook(event) -> None:
            stages.append(event.stage)
            if event.stage == "tool_call":
                raise RuntimeError("typing offline")

        out = await engine.run(session_id="cli:progress-sync-fail", user_text="run", progress_hook=_hook)
        assert out.text == "done"
        assert "tool_call" in stages
        assert "turn_completed" not in stages

    asyncio.run(_scenario())


def test_engine_async_progress_hook_failures_do_not_abort_turn() -> None:
    async def _scenario() -> None:
        provider = FakeLongToolProvider()
        engine = AgentEngine(provider=provider, tools=FakeTools())
        stages: list[str] = []

        async def _hook(event) -> None:
            stages.append(event.stage)
            if event.stage == "llm_request":
                raise RuntimeError("typing offline")

        out = await engine.run(session_id="cli:progress-async-fail", user_text="run", progress_hook=_hook)
        assert out.text == "done"
        assert stages == ["turn_started", "llm_request"]

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
        assert "no-progress" in out.text.lower()
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
        assert "loop detection found" in out.text.lower()
        assert provider.calls < 20
        assert loop_events
        assert loop_events[0]["detector"] == "ping_pong_no_progress"
        assert loop_events[0]["other_tool"] in {"alpha", "beta"}

    asyncio.run(_scenario())


def test_engine_detects_repeated_provider_plans_before_extra_tool_execution() -> None:
    async def _scenario() -> None:
        provider = FakeRepeatedPlanProvider()
        tools = FakeChangingResultTools()
        loop_events: list[dict[str, Any]] = []

        def _hook(event) -> None:
            if event.stage == "loop_detected":
                loop_events.append(event.metadata or {})

        engine = AgentEngine(
            provider=provider,
            tools=tools,
            max_iterations=20,
            loop_detection=LoopDetectionSettings(
                enabled=True,
                history_size=10,
                repeat_threshold=1,
                critical_threshold=2,
            ),
        )
        out = await engine.run(session_id="cli:provider-plan-detect", user_text="run", progress_hook=_hook)
        assert out.model == "engine/loop-detected"
        assert "same no-progress tool plan" in out.text.lower()
        assert provider.calls == 3
        assert tools.calls == 1
        assert loop_events
        assert loop_events[0]["detector"] == "provider_plan_no_progress"

    asyncio.run(_scenario())


def test_engine_injects_loop_recovery_notice_once_before_stopping() -> None:
    async def _scenario() -> None:
        provider = FakeLoopRecoveryProvider()
        tools = FakeChangingResultTools()
        diagnostic_events: list[dict[str, Any]] = []

        def _hook(event) -> None:
            if event.stage == "diagnostic_switch":
                diagnostic_events.append(event.metadata or {})

        engine = AgentEngine(
            provider=provider,
            tools=tools,
            max_iterations=20,
            loop_detection=LoopDetectionSettings(
                enabled=True,
                history_size=10,
                repeat_threshold=1,
                critical_threshold=2,
            ),
        )
        out = await engine.run(session_id="cli:loop-recovery", user_text="run", progress_hook=_hook)
        assert out.text == "I changed strategy and will answer directly."
        assert provider.calls == 3
        assert tools.calls == 1
        assert diagnostic_events
        assert diagnostic_events[0]["detector"] == "provider_plan_no_progress"
        assert diagnostic_events[0]["loop_recovery"] is True

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


def test_engine_softens_unverified_web_claims_without_web_tools() -> None:
    async def _scenario() -> None:
        provider = FakeFixedTextProvider(
            "Pesquisei na internet e aqui vai o resumo objetivo: OpenClaw e um projeto de agentes."
        )
        engine = AgentEngine(provider=provider, tools=FakeTools(), memory=FakeMemory(), sessions=InMemorySessionStore())

        out = await engine.run(session_id="cli:web-claim", user_text="o que e openclaw?")
        assert "Pesquisei na internet" not in out.text
        assert "Com base no contexto disponível" in out.text

    asyncio.run(_scenario())


def test_engine_injects_web_research_notice_for_explicit_internet_requests() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        engine = AgentEngine(provider=provider, tools=FakeWebSearchTools(), memory=FakeMemory(), sessions=InMemorySessionStore())

        out = await engine.run(session_id="cli:web-intent", user_text="pesquise na internet sobre openclaw")
        assert "verified result" in out.text
        assert provider.snapshots
        system_messages = [row["content"] for row in provider.snapshots[0] if row.get("role") == "system"]
        assert any("[Web Research Requirement]" in str(item) for item in system_messages)

    asyncio.run(_scenario())


def test_engine_skips_web_research_notice_for_normal_requests() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        engine = AgentEngine(provider=provider, tools=FakeWebSearchTools(), memory=FakeMemory(), sessions=InMemorySessionStore())

        out = await engine.run(session_id="cli:no-web-intent", user_text="explique o que e openclaw")
        assert out.text == "ok"
        assert provider.snapshots
        system_messages = [row["content"] for row in provider.snapshots[0] if row.get("role") == "system"]
        assert not any("[Web Research Requirement]" in str(item) for item in system_messages)

    asyncio.run(_scenario())


def test_engine_injects_routing_hint_for_weather_skill() -> None:
    async def _scenario() -> None:
        provider = FakePromptCaptureProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["weather"]),
        )

        out = await engine.run(session_id="cli:weather-routing", user_text="qual o clima em sao paulo?")
        assert "verified result" in out.text
        system_messages = [row["content"] for row in provider.snapshots[0] if row.get("role") == "system"]
        assert any("[Routing Hint]" in str(item) for item in system_messages)
        assert any("weather skill" in str(item) for item in system_messages)

    asyncio.run(_scenario())


def test_engine_appends_sources_after_real_web_tool_usage() -> None:
    async def _scenario() -> None:
        provider = FakeWebToolProvider()
        engine = AgentEngine(provider=provider, tools=FakeWebSearchTools(), memory=FakeMemory(), sessions=InMemorySessionStore())

        out = await engine.run(session_id="cli:web-sources", user_text="pesquise openclaw")
        assert out.text.startswith("OpenClaw is an autonomous assistant stack.")
        assert "Sources:" in out.text
        assert "https://openclaw.ai/" in out.text
        assert "https://github.com/openclaw" in out.text

    asyncio.run(_scenario())


def test_engine_retries_live_lookup_requests_when_provider_answers_without_tool_use() -> None:
    async def _scenario() -> None:
        provider = FakeLiveLookupRetryProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeWebSearchTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["weather"]),
        )

        out = await engine.run(
            session_id="cli:live-lookup-retry",
            user_text="qual a temperatura em Suzano, SP agora?",
        )

        assert provider.calls == 3
        assert out.text.startswith("Suzano, SP está com 24°C")
        assert "Sources:" in out.text
        retry_system_messages = [
            row["content"]
            for row in provider.snapshots[1]
            if row.get("role") == "system"
        ]
        assert any("[Verification Required]" in str(item) for item in retry_system_messages)

    asyncio.run(_scenario())


def test_engine_fails_closed_when_live_lookup_request_still_has_no_tool_evidence() -> None:
    async def _scenario() -> None:
        provider = FakeLiveLookupFailureProvider()
        engine = AgentEngine(
            provider=provider,
            tools=FakeWebSearchTools(),
            memory=FakeMemory(),
            sessions=InMemorySessionStore(),
            skills_loader=FakeSkillsLoader(names=["weather"]),
        )

        out = await engine.run(
            session_id="cli:live-lookup-fail",
            user_text="qual a temperatura em Suzano, SP agora?",
        )

        assert provider.calls == 2
        assert "verified result" in out.text
        assert "24°C" not in out.text

    asyncio.run(_scenario())


def test_engine_persists_and_replays_legal_tool_history_from_session_store(tmp_path: Path) -> None:
    async def _scenario() -> None:
        sessions = SessionStore(root=tmp_path / "sessions")
        first_engine = AgentEngine(
            provider=FakeProvider(),
            tools=FakeTools(),
            sessions=sessions,
            memory=FakeMemory(),
        )
        first = await first_engine.run(session_id="cli:history-tools", user_text="say hi")
        assert first.text == "final answer"

        capture = FakePromptCaptureProvider()
        second_engine = AgentEngine(
            provider=capture,
            tools=FakeTools(),
            sessions=sessions,
            memory=FakeMemory(),
        )
        second = await second_engine.run(session_id="cli:history-tools", user_text="continue")
        assert second.text == "ok"

        assert capture.snapshots
        history_assistant_rows = [
            row
            for row in capture.snapshots[0]
            if row.get("role") == "assistant" and isinstance(row.get("tool_calls"), list)
        ]
        history_tool_rows = [
            row
            for row in capture.snapshots[0]
            if row.get("role") == "tool" and row.get("tool_call_id")
        ]
        assert history_assistant_rows
        assert history_tool_rows
        assert history_assistant_rows[0]["tool_calls"][0]["function"]["name"] == "echo"
        assert history_tool_rows[0]["name"] == "echo"

    asyncio.run(_scenario())


def test_engine_uses_semantic_history_summary_when_enabled() -> None:
    async def _scenario() -> None:
        provider = FakeSemanticSummaryProvider()
        sessions = InMemorySessionStore()
        for idx in range(6):
            sessions.append("s1", "user" if idx % 2 == 0 else "assistant", f"history-message-{idx}-" * 40)

        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=sessions,
            memory=FakeMemory(),
            subagents=FakeSubagentManagerEmpty(),
            prompt_builder=PromptBuilder(context_token_budget=220),
            semantic_history_summary_enabled=True,
        )

        result = await engine.run(session_id="s1", user_text="hello")

        assert result.text == "final answer"
        assert any(
            str(call[0].get("content", "")).startswith("Compress the provided content for an agent context window.")
            for call in provider.calls
        )
        final_calls = [
            call
            for call in provider.calls
            if not str(call[0].get("content", "")).startswith("Compress the provided content for an agent context window.")
        ]
        assert any(
            any("semantic summary from llm" in str(msg.get("content", "")) for msg in snapshot)
            for snapshot in final_calls
        )

    asyncio.run(_scenario())


def test_engine_compacts_large_tool_results_before_history_injection() -> None:
    async def _scenario() -> None:
        provider = FakeToolCompactionProvider()

        class LargeToolResultTools(FakeTools):
            async def execute(
                self,
                name,
                arguments,
                *,
                session_id: str,
                channel: str = "",
                user_id: str = "",
                requester_id: str = "",
            ) -> str:
                del name, arguments, session_id, channel, user_id, requester_id
                return "LARGE-RESULT-" * 400

        engine = AgentEngine(
            provider=provider,
            tools=LargeToolResultTools(),
            sessions=InMemorySessionStore(),
            memory=FakeMemory(),
            subagents=FakeSubagentManagerEmpty(),
            tool_result_compaction_enabled=True,
            tool_result_compaction_threshold_chars=200,
            max_tool_result_chars=400,
        )

        result = await engine.run(session_id="s1", user_text="do it")

        assert result.text == "done"
        assert any(
            str(call[0].get("content", "")).startswith("Compress the provided content for an agent context window.")
            for call in provider.calls
        )
        non_compaction_calls = [
            call
            for call in provider.calls
            if not str(call[0].get("content", "")).startswith("Compress the provided content for an agent context window.")
        ]
        assert any(
            any(msg.get("role") == "tool" and msg.get("content") == "compacted tool output" for msg in snapshot)
            for snapshot in non_compaction_calls
        )

    asyncio.run(_scenario())


def test_engine_marks_real_subagent_digest_async_and_does_not_repeat_it(tmp_path: Path) -> None:
    async def _scenario() -> None:
        manager = SubagentManager(state_path=tmp_path / "subagents")
        run = SubagentRun(
            run_id="run-digest-1",
            session_id="s1",
            task="collect context",
            status="done",
            result="Collected all required details.",
            finished_at="2026-03-05T12:00:00+00:00",
        )
        manager._runs[run.run_id] = run
        manager._save_state()

        provider = FakeFixedTextProvider("final answer")
        engine = AgentEngine(
            provider=provider,
            tools=FakeTools(),
            sessions=InMemorySessionStore(),
            memory=FakeMemory(),
            subagents=manager,
        )

        first = await engine.run(session_id="s1", user_text="hello")
        second = await engine.run(session_id="s1", user_text="hello again")

        assert first.text.startswith("final answer")
        assert "[Subagent Digest]" in first.text
        assert second.text == "final answer"
        assert manager.list_completed_unsynthesized("s1") == []

    asyncio.run(_scenario())
