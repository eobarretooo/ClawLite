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
    id: str = ""


@dataclass(slots=True)
class ProviderResult:
    text: str
    tool_calls: list[ToolCall]
    model: str


class ProviderProtocol:
    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
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
        max_iterations: int = 40,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.sessions = sessions or SessionStore()
        self.memory = memory or MemoryStore()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.skills_loader = skills_loader or SkillsLoader()
        self.subagents = subagents or SubagentManager()
        self.max_iterations = max(1, int(max_iterations))

    @staticmethod
    def _tool_call_id(tool_call: Any, idx: int) -> str:
        raw = str(getattr(tool_call, "id", "") or "").strip()
        return raw or f"call_{idx}"

    @staticmethod
    def _tool_call_name(tool_call: Any) -> str:
        return str(getattr(tool_call, "name", "") or "").strip()

    @staticmethod
    def _tool_call_arguments(tool_call: Any) -> dict[str, Any]:
        raw = getattr(tool_call, "arguments", {})
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _assistant_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for idx, tool_call in enumerate(tool_calls):
            name = AgentEngine._tool_call_name(tool_call)
            if not name:
                continue
            rows.append(
                {
                    "id": AgentEngine._tool_call_id(tool_call, idx),
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(AgentEngine._tool_call_arguments(tool_call), ensure_ascii=False),
                    },
                }
            )
        return rows

    @staticmethod
    def _resolve_runtime_context(session_id: str, channel: str | None, chat_id: str | None) -> tuple[str, str]:
        runtime_channel = str(channel or "").strip()
        runtime_chat_id = str(chat_id or "").strip()

        if not runtime_channel and ":" in session_id:
            runtime_channel = session_id.split(":", 1)[0].strip()
        if not runtime_chat_id and ":" in session_id:
            runtime_chat_id = session_id.split(":", 1)[1].strip()

        return runtime_channel, runtime_chat_id

    async def run(
        self,
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> ProviderResult:
        logger.info("processing message session={} chars={}", session_id, len(user_text))
        history = self.sessions.read(session_id, limit=20)
        memories = [row.text for row in self.memory.search(user_text, limit=6)]
        skills = self.skills_loader.render_for_prompt()
        always_names = [item.name for item in self.skills_loader.always_on()]
        skills_context = self.skills_loader.load_skills_for_context(always_names)
        runtime_channel, runtime_chat_id = self._resolve_runtime_context(session_id, channel, chat_id)

        prompt = self.prompt_builder.build(
            user_text=user_text,
            history=history,
            memory_snippets=memories,
            skills_for_prompt=skills,
            skills_context=skills_context,
            channel=runtime_channel,
            chat_id=runtime_chat_id,
        )

        messages: list[dict[str, Any]] = []
        if prompt.system_prompt:
            messages.append({"role": "system", "content": prompt.system_prompt})
        if prompt.memory_section:
            messages.append({"role": "system", "content": prompt.memory_section})
        if prompt.skills_context:
            messages.append({"role": "system", "content": f"[Skill Guides]\n{prompt.skills_context}"})
        if prompt.history_messages:
            messages.extend(prompt.history_messages)
        if prompt.runtime_context:
            messages.append({"role": "user", "content": prompt.runtime_context})
        messages.append({"role": "user", "content": user_text})

        final = ProviderResult(text="", tool_calls=[], model="engine/fallback")
        graceful_error = False
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            try:
                step = await self.provider.complete(messages=messages, tools=self.tools.schema())
            except Exception as exc:
                logger.error("llm completion failed session={} iteration={} error={}", session_id, iteration, exc)
                final = ProviderResult(
                    text="Sorry, I encountered an error while calling the model. Please try again shortly.",
                    tool_calls=[],
                    model="engine/fallback",
                )
                graceful_error = True
                break

            if step.tool_calls:
                logger.debug("tool calls requested session={} iteration={} count={}", session_id, iteration, len(step.tool_calls))
                messages.append(
                    {
                        "role": "assistant",
                        "content": step.text or "",
                        "tool_calls": self._assistant_tool_calls(step.tool_calls),
                    }
                )

                for idx, tool_call in enumerate(step.tool_calls):
                    call_id = self._tool_call_id(tool_call, idx)
                    name = self._tool_call_name(tool_call)
                    arguments = self._tool_call_arguments(tool_call)
                    if not name:
                        logger.error("tool call without name session={} iteration={} idx={}", session_id, iteration, idx)
                        continue
                    logger.debug("executing tool session={} tool={} call_id={}", session_id, name, call_id)
                    try:
                        tool_result = await self.tools.execute(name, arguments, session_id=session_id)
                    except Exception as exc:
                        logger.error("tool execution failed session={} tool={} call_id={} error={}", session_id, name, call_id, exc)
                        tool_result = f"tool_error:{name}:{exc}"
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": name,
                            "content": str(tool_result),
                        }
                    )
                continue

            final = ProviderResult(text=step.text, tool_calls=[], model=step.model)
            break

        if not final.text and iteration >= self.max_iterations:
            logger.error("max iterations reached session={} max_iterations={}", session_id, self.max_iterations)
            final = ProviderResult(
                text=f"I reached the maximum number of tool iterations ({self.max_iterations}) without completing the task.",
                tool_calls=[],
                model="engine/fallback",
            )

        self.sessions.append(session_id, "user", user_text)
        if not graceful_error:
            self.sessions.append(session_id, "assistant", final.text)
            self.memory.consolidate(
                [{"role": "user", "content": user_text}, {"role": "assistant", "content": final.text}],
                source=f"session:{session_id}",
            )
        else:
            logger.info("skipping assistant persistence after provider failure session={}", session_id)
        logger.info("response generated session={} model={} chars={}", session_id, final.model, len(final.text))
        return final
