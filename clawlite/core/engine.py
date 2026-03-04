from __future__ import annotations

import asyncio
import hashlib
import json
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from clawlite.core.memory import MemoryStore
from clawlite.core.prompt import PromptBuilder
from clawlite.core.skills import SkillsLoader
from clawlite.core.subagent import SubagentManager
from clawlite.session.store import SessionStore
from clawlite.utils.logging import bind_event, setup_logging

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


@dataclass(slots=True)
class TurnBudget:
    max_iterations: int | None = None
    max_tool_calls: int | None = None
    max_tool_result_chars: int | None = None
    max_progress_events: int | None = None


@dataclass(slots=True)
class ProgressEvent:
    stage: str
    session_id: str
    iteration: int
    message: str = ""
    tool_name: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class LoopDetectionSettings:
    enabled: bool = False
    history_size: int = 20
    repeat_threshold: int = 3
    critical_threshold: int = 6


@dataclass(slots=True)
class _ToolExecutionRecord:
    signature: str
    tool_name: str
    outcome_hash: str


class AgentLoopError(Exception):
    pass


class AgentCancelledError(AgentLoopError):
    pass


class ProviderAuthError(AgentLoopError):
    pass


class ProviderHttpError(AgentLoopError):
    def __init__(self, *, status_code: int | None, detail: str = "") -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ProviderNetworkError(AgentLoopError):
    pass


class ProviderConfigError(AgentLoopError):
    pass


class ProviderUnknownError(AgentLoopError):
    pass


ProgressHook = Callable[[ProgressEvent], Awaitable[None] | None]


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

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        channel: str = "",
        user_id: str = "",
    ) -> str:  # pragma: no cover
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

    _TOOL_RESULT_TRUNCATED_SUFFIX = "\n...[tool result truncated]"
    _THINK_DIRECTIVE_RE = re.compile(r"(?:^|\s)/(?:thinking|think|t)\s*[:=]?\s*([a-zA-Z][a-zA-Z_\-]*)\b")
    _REASONING_ALIASES: dict[str, str | None] = {
        "off": None,
        "none": None,
        "disable": None,
        "disabled": None,
        "minimal": "minimal",
        "min": "minimal",
        "think": "minimal",
        "low": "low",
        "thinkhard": "low",
        "medium": "medium",
        "med": "medium",
        "mid": "medium",
        "thinkharder": "medium",
        "high": "high",
        "max": "high",
        "highest": "high",
        "ultrathink": "high",
        "xhigh": "high",
        "extrahigh": "high",
    }
    _QUOTA_429_SIGNALS: tuple[str, ...] = (
        "insufficient_quota",
        "quota exceeded",
        "quota_exceeded",
        "exceeded your current quota",
        "billing hard limit",
        "out of credits",
        "billing exhausted",
    )

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
        subagent_state_path: str | Path | None = None,
        subagent_max_concurrent_runs: int = 2,
        subagent_max_queued_runs: int = 32,
        subagent_per_session_quota: int = 4,
        max_iterations: int = 40,
        max_tokens: int = 8192,
        temperature: float = 0.1,
        max_tool_calls_per_turn: int = 80,
        max_tool_result_chars: int = 4000,
        max_progress_events_per_turn: int = 120,
        reasoning_effort_default: str | None = None,
        loop_detection: LoopDetectionSettings | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.sessions = sessions or SessionStore()
        self.memory = memory or MemoryStore()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.skills_loader = skills_loader or SkillsLoader()
        self.subagents = subagents or SubagentManager(
            state_path=subagent_state_path,
            max_concurrent_runs=subagent_max_concurrent_runs,
            max_queued_runs=subagent_max_queued_runs,
            per_session_quota=subagent_per_session_quota,
        )
        self.max_iterations = max(1, int(max_iterations))
        self.max_tokens = max(1, int(max_tokens))
        self.temperature = float(temperature)
        self.max_tool_calls_per_turn = max(1, int(max_tool_calls_per_turn))
        self.max_tool_result_chars = max(32, int(max_tool_result_chars))
        self.max_progress_events_per_turn = max(1, int(max_progress_events_per_turn))
        self.reasoning_effort_default = self._normalize_reasoning_effort(reasoning_effort_default)
        resolved_loop = loop_detection or LoopDetectionSettings()
        critical_threshold = max(1, int(resolved_loop.critical_threshold))
        repeat_threshold = max(1, int(resolved_loop.repeat_threshold))
        if critical_threshold <= repeat_threshold:
            critical_threshold = repeat_threshold + 1
        self.loop_detection = LoopDetectionSettings(
            enabled=bool(resolved_loop.enabled),
            history_size=max(1, int(resolved_loop.history_size)),
            repeat_threshold=repeat_threshold,
            critical_threshold=critical_threshold,
        )
        self._stop_requests: set[str] = set()
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_locks_guard = asyncio.Lock()

    async def _complete_provider(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        reasoning_effort: str | None,
    ) -> ProviderResult:
        complete_sig = inspect.signature(self.provider.complete)
        accepts_max_tokens = "max_tokens" in complete_sig.parameters
        accepts_temperature = "temperature" in complete_sig.parameters
        accepts_reasoning_effort = "reasoning_effort" in complete_sig.parameters
        kwargs: dict[str, Any] = {"messages": messages, "tools": tools}
        if accepts_max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if accepts_temperature:
            kwargs["temperature"] = self.temperature
        if accepts_reasoning_effort and reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        return await self.provider.complete(**kwargs)

    @classmethod
    def _normalize_reasoning_effort(cls, value: str | None) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        collapsed = re.sub(r"[\s_-]+", "", text)
        return cls._REASONING_ALIASES.get(collapsed)

    @classmethod
    def _resolve_reasoning_effort(cls, user_text: str, config_default: str | None) -> str | None:
        inline_match = cls._THINK_DIRECTIVE_RE.search(user_text or "")
        if inline_match:
            raw_value = inline_match.group(1).strip().lower()
            parsed = cls._normalize_reasoning_effort(raw_value)
            if parsed is not None or raw_value in {"off", "none", "disable", "disabled"}:
                return parsed
        return cls._normalize_reasoning_effort(config_default)

    @staticmethod
    def _tool_signature(name: str, arguments: dict[str, Any]) -> str:
        try:
            serialized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            serialized = repr(arguments)
        digest = hashlib.sha256(serialized.encode("utf-8", errors="ignore")).hexdigest()
        return f"{name}:{digest}"

    @staticmethod
    def _tool_outcome_hash(result: Any) -> str:
        text = str(result)
        digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        return digest

    def _detect_tool_loop(self, history: list[_ToolExecutionRecord], signature: str) -> tuple[bool, str, int]:
        streak = 0
        latest_outcome_hash = ""
        for record in reversed(history):
            if record.signature != signature:
                continue
            if not latest_outcome_hash:
                latest_outcome_hash = record.outcome_hash
                streak = 1
                continue
            if record.outcome_hash != latest_outcome_hash:
                break
            streak += 1
        if streak >= self.loop_detection.critical_threshold:
            return True, "critical", streak
        if streak >= self.loop_detection.repeat_threshold:
            return True, "warning", streak
        return False, "", streak

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

    def request_stop(self, session_id: str) -> bool:
        normalized = str(session_id or "").strip()
        if not normalized:
            return False
        self._stop_requests.add(normalized)
        return True

    def clear_stop(self, session_id: str) -> None:
        normalized = str(session_id or "").strip()
        if normalized:
            self._stop_requests.discard(normalized)

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._session_locks_guard:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._session_locks[session_id] = lock
            return lock

    @staticmethod
    def _classify_provider_error(exc: Exception) -> AgentLoopError:
        if isinstance(exc, AgentLoopError):
            return exc

        reason = str(exc or "").strip()
        if reason.startswith("provider_auth_error:missing_api_key:"):
            provider = reason.rsplit(":", 1)[-1]
            return ProviderAuthError(provider)
        if reason.startswith("provider_http_error:"):
            _, _, suffix = reason.partition("provider_http_error:")
            parts = suffix.split(":", 1)
            status_code: int | None = None
            try:
                status_code = int(parts[0])
            except ValueError:
                status_code = None
            detail = parts[1].strip() if len(parts) > 1 else ""
            return ProviderHttpError(status_code=status_code, detail=detail)
        if reason.startswith("provider_network_error:"):
            return ProviderNetworkError(reason.partition(":")[-1].strip())
        if reason.startswith("provider_config_error:"):
            return ProviderConfigError(reason.partition(":")[-1].strip())
        if reason.startswith("codex_http_error:"):
            _, _, status_raw = reason.partition("codex_http_error:")
            status_code: int | None = None
            try:
                status_code = int(status_raw)
            except ValueError:
                status_code = None
            return ProviderHttpError(status_code=status_code, detail="")
        if reason.startswith("codex_network_error:"):
            return ProviderNetworkError(reason.partition(":")[-1].strip())
        if reason in {"provider_429_exhausted", "codex_429_exhausted"}:
            return ProviderHttpError(status_code=429, detail="retry exhausted")
        return ProviderUnknownError(reason or exc.__class__.__name__)

    @staticmethod
    def _is_quota_429_detail(detail: str) -> bool:
        lowered = str(detail or "").strip().lower()
        if not lowered:
            return False
        return any(token in lowered for token in AgentEngine._QUOTA_429_SIGNALS)

    @staticmethod
    def _provider_error_message(error: AgentLoopError) -> str:
        if isinstance(error, ProviderAuthError):
            provider = str(error) or "provider"
            return (
                f"Sorry, I could not call the model because API credentials are missing for {provider}. "
                "Set the provider API key and try again."
            )
        if isinstance(error, ProviderHttpError):
            if error.status_code == 401:
                return (
                    "Sorry, model authentication failed (401). "
                    "Check that your API key matches the selected model/provider."
                )
            if error.status_code == 429:
                if AgentEngine._is_quota_429_detail(error.detail):
                    return (
                        "Sorry, the model provider quota is exhausted right now. "
                        "Please top up billing or switch to a provider/model with available quota."
                    )
                return "Sorry, the model is rate-limited right now. Please try again in a moment."
            if error.status_code == 400:
                return "Sorry, the model request was rejected (400). Check model/provider configuration and try again."
            return "Sorry, I encountered an HTTP error while calling the model. Please try again shortly."
        if isinstance(error, ProviderConfigError):
            return "Sorry, provider configuration is invalid. Check base URL/model settings and try again."
        if isinstance(error, ProviderNetworkError):
            return "Sorry, I could not reach the model provider due to a network error. Please try again shortly."
        return "Sorry, I encountered an error while calling the model. Please try again shortly."

    def _resolve_turn_budget(self, turn_budget: TurnBudget | None = None) -> TurnBudget:
        budget = turn_budget or TurnBudget()
        return TurnBudget(
            max_iterations=max(1, int(budget.max_iterations)) if budget.max_iterations is not None else self.max_iterations,
            max_tool_calls=max(1, int(budget.max_tool_calls)) if budget.max_tool_calls is not None else self.max_tool_calls_per_turn,
            max_tool_result_chars=max(32, int(budget.max_tool_result_chars)) if budget.max_tool_result_chars is not None else self.max_tool_result_chars,
            max_progress_events=max(1, int(budget.max_progress_events)) if budget.max_progress_events is not None else self.max_progress_events_per_turn,
        )

    @classmethod
    def _truncate_tool_result(cls, value: Any, max_chars: int) -> tuple[str, bool]:
        text = str(value)
        limit = max(1, int(max_chars))
        if len(text) <= limit:
            return text, False
        suffix = cls._TOOL_RESULT_TRUNCATED_SUFFIX
        if limit <= len(suffix):
            return suffix[:limit], True
        keep = max(0, limit - len(suffix))
        return f"{text[:keep]}{suffix}", True

    @staticmethod
    def _stop_requested(*, session_id: str, stop_event: asyncio.Event | None, stop_requests: set[str]) -> bool:
        if stop_event is not None and stop_event.is_set():
            return True
        return session_id in stop_requests

    async def _emit_progress(
        self,
        *,
        progress_hook: ProgressHook | None,
        event: ProgressEvent,
        counter: list[int],
        limit: int,
    ) -> None:
        if progress_hook is None:
            return
        if counter[0] >= limit:
            return
        counter[0] += 1
        maybe_awaitable = progress_hook(event)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    async def run(
        self,
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        turn_budget: TurnBudget | None = None,
        progress_hook: ProgressHook | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> ProviderResult:
        session_lock = await self._get_session_lock(session_id)
        async with session_lock:
            return await self._run_serialized(
                session_id=session_id,
                user_text=user_text,
                channel=channel,
                chat_id=chat_id,
                turn_budget=turn_budget,
                progress_hook=progress_hook,
                stop_event=stop_event,
            )

    async def _run_serialized(
        self,
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        turn_budget: TurnBudget | None = None,
        progress_hook: ProgressHook | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> ProviderResult:
        runtime_channel, runtime_chat_id = self._resolve_runtime_context(session_id, channel, chat_id)
        run_log = bind_event("agent.loop", session=session_id, channel=runtime_channel or "-")
        run_log.info("processing message chars={}", len(user_text))
        budget = self._resolve_turn_budget(turn_budget)
        progress_counter = [0]
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
        tool_calls_used = 0
        iteration = 0
        resolved_reasoning_effort = self._resolve_reasoning_effort(user_text, self.reasoning_effort_default)
        tool_history: list[_ToolExecutionRecord] = []

        await self._emit_progress(
            progress_hook=progress_hook,
            event=ProgressEvent(stage="turn_started", session_id=session_id, iteration=0, message="turn started"),
            counter=progress_counter,
            limit=budget.max_progress_events or 1,
        )

        while iteration < (budget.max_iterations or 1):
            iteration += 1
            if self._stop_requested(session_id=session_id, stop_event=stop_event, stop_requests=self._stop_requests):
                final = ProviderResult(text="Stopped current task.", tool_calls=[], model="engine/stop")
                run_log.info("turn cancelled before llm iteration={}", iteration)
                break

            await self._emit_progress(
                progress_hook=progress_hook,
                event=ProgressEvent(stage="llm_request", session_id=session_id, iteration=iteration, message="calling provider"),
                counter=progress_counter,
                limit=budget.max_progress_events or 1,
            )
            try:
                step = await self._complete_provider(
                    messages=messages,
                    tools=self.tools.schema(),
                    reasoning_effort=resolved_reasoning_effort,
                )
            except Exception as exc:
                typed = self._classify_provider_error(exc)
                run_log.error("llm completion failed iteration={} type={} error={}", iteration, typed.__class__.__name__, typed)
                text = self._provider_error_message(typed)
                final = ProviderResult(
                    text=text,
                    tool_calls=[],
                    model="engine/fallback",
                )
                graceful_error = True
                await self._emit_progress(
                    progress_hook=progress_hook,
                    event=ProgressEvent(
                        stage="llm_error",
                        session_id=session_id,
                        iteration=iteration,
                        message=text,
                        metadata={"error_type": typed.__class__.__name__},
                    ),
                    counter=progress_counter,
                    limit=budget.max_progress_events or 1,
                )
                break

            await self._emit_progress(
                progress_hook=progress_hook,
                event=ProgressEvent(
                    stage="llm_response",
                    session_id=session_id,
                    iteration=iteration,
                    message=(step.text or "")[:160],
                    metadata={"tool_calls": len(step.tool_calls)},
                ),
                counter=progress_counter,
                limit=budget.max_progress_events or 1,
            )

            if step.tool_calls:
                run_log.debug("tool calls requested iteration={} count={}", iteration, len(step.tool_calls))
                messages.append(
                    {
                        "role": "assistant",
                        "content": step.text or "",
                        "tool_calls": self._assistant_tool_calls(step.tool_calls),
                    }
                )

                for idx, tool_call in enumerate(step.tool_calls):
                    if self._stop_requested(session_id=session_id, stop_event=stop_event, stop_requests=self._stop_requests):
                        final = ProviderResult(text="Stopped current task.", tool_calls=[], model="engine/stop")
                        run_log.info("turn cancelled during tool execution iteration={} idx={}", iteration, idx)
                        break

                    if tool_calls_used >= (budget.max_tool_calls or 1):
                        final = ProviderResult(
                            text=(
                                f"I reached the tool-call budget ({budget.max_tool_calls}) for this turn "
                                "before completing the task."
                            ),
                            tool_calls=[],
                            model="engine/fallback",
                        )
                        run_log.error("tool-call budget reached iteration={} max_tool_calls={}", iteration, budget.max_tool_calls)
                        break

                    call_id = self._tool_call_id(tool_call, idx)
                    name = self._tool_call_name(tool_call)
                    arguments = self._tool_call_arguments(tool_call)
                    if not name:
                        run_log.error("tool call without name iteration={} idx={}", iteration, idx)
                        continue
                    signature = self._tool_signature(name, arguments)
                    if self.loop_detection.enabled:
                        should_stop, severity, streak = self._detect_tool_loop(tool_history, signature)
                        if should_stop:
                            final = ProviderResult(
                                text=(
                                    "I stopped this turn because loop detection found repeated "
                                    f"non-progress tool calls for `{name}` ({streak} repeats)."
                                ),
                                tool_calls=[],
                                model="engine/loop-detected",
                            )
                            run_log.warning(
                                "tool loop detected iteration={} tool={} streak={} severity={} threshold={} critical_threshold={}",
                                iteration,
                                name,
                                streak,
                                severity,
                                self.loop_detection.repeat_threshold,
                                self.loop_detection.critical_threshold,
                            )
                            await self._emit_progress(
                                progress_hook=progress_hook,
                                event=ProgressEvent(
                                    stage="loop_detected",
                                    session_id=session_id,
                                    iteration=iteration,
                                    message=final.text,
                                    tool_name=name,
                                    metadata={
                                        "detector": "repeating_no_progress",
                                        "severity": severity,
                                        "repeats": streak,
                                        "threshold": self.loop_detection.repeat_threshold,
                                        "critical_threshold": self.loop_detection.critical_threshold,
                                        "history_size": self.loop_detection.history_size,
                                    },
                                ),
                                counter=progress_counter,
                                limit=budget.max_progress_events or 1,
                            )
                            break
                    tool_calls_used += 1
                    await self._emit_progress(
                        progress_hook=progress_hook,
                        event=ProgressEvent(
                            stage="tool_call",
                            session_id=session_id,
                            iteration=iteration,
                            message=f"executing {name}",
                            tool_name=name,
                            metadata={"call_id": call_id},
                        ),
                        counter=progress_counter,
                        limit=budget.max_progress_events or 1,
                    )
                    bind_event("tool.exec", session=session_id, channel=runtime_channel or "-", tool=name).debug("executing call_id={}", call_id)
                    try:
                        tool_result = await self.tools.execute(
                            name,
                            arguments,
                            session_id=session_id,
                            channel=runtime_channel,
                            user_id=runtime_chat_id,
                        )
                    except Exception as exc:
                        bind_event("tool.exec", session=session_id, channel=runtime_channel or "-", tool=name).error("execution failed call_id={} error={}", call_id, exc)
                        tool_result = f"tool_error:{name}:{exc}"

                    normalized_result, was_truncated = self._truncate_tool_result(
                        tool_result,
                        budget.max_tool_result_chars or self.max_tool_result_chars,
                    )
                    if was_truncated:
                        bind_event("tool.exec", session=session_id, channel=runtime_channel or "-", tool=name).info(
                            "tool result truncated call_id={} max_chars={}",
                            call_id,
                            budget.max_tool_result_chars,
                        )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": name,
                            "content": normalized_result,
                        }
                    )

                    await self._emit_progress(
                        progress_hook=progress_hook,
                        event=ProgressEvent(
                            stage="tool_result",
                            session_id=session_id,
                            iteration=iteration,
                            message=f"{name} completed",
                            tool_name=name,
                            metadata={"call_id": call_id, "truncated": was_truncated},
                        ),
                        counter=progress_counter,
                        limit=budget.max_progress_events or 1,
                    )

                    if self.loop_detection.enabled:
                        tool_history.append(
                            _ToolExecutionRecord(
                                signature=signature,
                                tool_name=name,
                                outcome_hash=self._tool_outcome_hash(normalized_result),
                            )
                        )
                        max_history = self.loop_detection.history_size
                        if len(tool_history) > max_history:
                            del tool_history[:-max_history]

                if final.text:
                    break
                continue

            final = ProviderResult(text=step.text, tool_calls=[], model=step.model)
            break

        if not final.text and iteration >= (budget.max_iterations or 1):
            run_log.error("max iterations reached max_iterations={}", budget.max_iterations)
            final = ProviderResult(
                text=f"I reached the maximum number of tool iterations ({budget.max_iterations}) without completing the task.",
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
            run_log.info("skipping assistant persistence after provider failure")
        if final.model == "engine/stop":
            await self._emit_progress(
                progress_hook=progress_hook,
                event=ProgressEvent(stage="turn_cancelled", session_id=session_id, iteration=iteration, message=final.text),
                counter=progress_counter,
                limit=budget.max_progress_events or 1,
            )
        else:
            await self._emit_progress(
                progress_hook=progress_hook,
                event=ProgressEvent(stage="turn_completed", session_id=session_id, iteration=iteration, message=final.text[:200]),
                counter=progress_counter,
                limit=budget.max_progress_events or 1,
            )
        self.clear_stop(session_id)
        run_log.info("response generated model={} chars={}", final.model, len(final.text))
        return final
