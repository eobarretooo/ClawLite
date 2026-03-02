from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from loguru import logger

from clawlite.core.memory import MemoryStore
from clawlite.core.prompt import PromptBuilder
from clawlite.core.skills import SkillsLoader
from clawlite.core.subagent import SubagentManager
from clawlite.session.store import SessionStore
from clawlite.utils.logging import setup_logging

setup_logging()


@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ProviderResult:
    text: str
    tool_calls: list[ToolCall]
    model: str


class ProviderProtocol:
    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> ProviderResult:  # pragma: no cover - protocol
        raise NotImplementedError


class SessionStoreProtocol:
    def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:  # pragma: no cover
        raise NotImplementedError

    def append(self, session_id: str, role: str, content: str) -> None:  # pragma: no cover
        raise NotImplementedError


class ToolRegistryProtocol:
    def schema(self) -> list[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    async def execute(self, name: str, arguments: dict[str, Any], *, session_id: str) -> str:  # pragma: no cover
        raise NotImplementedError


class InMemorySessionStore(SessionStoreProtocol):
    def __init__(self) -> None:
        self._rows: dict[str, list[dict[str, str]]] = {}

    def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        return self._rows.get(session_id, [])[-limit:]

    def append(self, session_id: str, role: str, content: str) -> None:
        self._rows.setdefault(session_id, []).append({"role": role, "content": content})


class AgentEngine:
    """Core autonomous loop used by channels, cron and CLI."""

    def __init__(
        self,
        *,
        provider: ProviderProtocol,
        tools: ToolRegistryProtocol,
        sessions: SessionStoreProtocol | None = None,
        memory: MemoryStore | None = None,
        prompt_builder: PromptBuilder | None = None,
        skills_loader: SkillsLoader | None = None,
        subagents: SubagentManager | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.sessions = sessions or SessionStore()
        self.memory = memory or MemoryStore()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.skills_loader = skills_loader or SkillsLoader()
        self.subagents = subagents or SubagentManager()

    @staticmethod
    def _tool_json(name: str, arguments: dict[str, Any], result: str) -> str:
        return json.dumps(
            {
                "tool": name,
                "arguments": arguments,
                "result": result,
            },
            ensure_ascii=False,
        )

    async def run(self, *, session_id: str, user_text: str) -> ProviderResult:
        logger.info("processing message session={} chars={}", session_id, len(user_text))
        history = self.sessions.read(session_id, limit=20)
        memories = [row.text for row in self.memory.search(user_text, limit=6)]
        skills = self.skills_loader.render_for_prompt()
        always_names = [item.name for item in self.skills_loader.always_on()]
        skills_context = self.skills_loader.load_skills_for_context(always_names)

        prompt = self.prompt_builder.build(
            user_text=user_text,
            history=history,
            memory_snippets=memories,
            skills_for_prompt=skills,
            skills_context=skills_context,
        )

        messages = []
        if prompt.system_prompt:
            messages.append({"role": "system", "content": prompt.system_prompt})
        if prompt.memory_section:
            messages.append({"role": "system", "content": prompt.memory_section})
        if prompt.history_section:
            messages.append({"role": "system", "content": prompt.history_section})
        if prompt.skills_context:
            messages.append({"role": "system", "content": f"[Skill Guides]\n{prompt.skills_context}"})
        messages.append({"role": "user", "content": user_text})

        try:
            first = await self.provider.complete(messages=messages, tools=self.tools.schema())
        except Exception as exc:
            logger.error("llm completion failed session={} stage=first error={}", session_id, exc)
            raise

        if first.tool_calls:
            logger.debug("tool calls requested session={} count={}", session_id, len(first.tool_calls))
            for tool_call in first.tool_calls[:3]:
                logger.debug("executing tool session={} tool={}", session_id, tool_call.name)
                tool_result = await self.tools.execute(tool_call.name, tool_call.arguments, session_id=session_id)
                messages.append({"role": "assistant", "content": self._tool_json(tool_call.name, tool_call.arguments, tool_result)})
            try:
                second = await self.provider.complete(messages=messages, tools=self.tools.schema())
            except Exception as exc:
                logger.error("llm completion failed session={} stage=second error={}", session_id, exc)
                raise
            final = second
        else:
            final = first

        self.sessions.append(session_id, "user", user_text)
        self.sessions.append(session_id, "assistant", final.text)
        self.memory.consolidate([{"role": "user", "content": user_text}, {"role": "assistant", "content": final.text}], source=f"session:{session_id}")
        logger.info("response generated session={} model={} chars={}", session_id, final.model, len(final.text))
        return final
