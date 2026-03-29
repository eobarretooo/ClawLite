from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawlite.bus.journal import BusJournal
from clawlite.bus.queue import MessageQueue
from clawlite.bus.redis_queue import RedisMessageQueue
from clawlite.channels.manager import ChannelManager
from clawlite.config.schema import AppConfig
from clawlite.core.engine import AgentEngine, LoopDetectionSettings
from clawlite.core.memory import MemoryStore
from clawlite.core.memory_backend import resolve_memory_backend
from clawlite.core.memory_monitor import MemoryMonitor
from clawlite.core.prompt import PromptBuilder
from clawlite.core.skills import SkillsLoader
from clawlite.jobs.journal import JobJournal
from clawlite.jobs.queue import JobQueue
from clawlite.providers import build_provider, detect_provider_name
from clawlite.providers.discovery import detect_local_runtime, probe_local_provider_runtime
from clawlite.runtime import (
    AutonomyLog,
    AutonomyService,
    AutonomyWakeCoordinator,
    RuntimeSupervisor,
)
from clawlite.runtime.telemetry import configure_observability
from clawlite.gateway.autonomy_notice import send_autonomy_notice
from clawlite.gateway.discord_thread_binding import (
    handle_discord_thread_binding_inbound_action,
)
from clawlite.gateway.self_evolution_approval import handle_self_evolution_inbound_action
from clawlite.gateway.tool_approval import handle_tool_approval_inbound_action
from clawlite.scheduler.cron import CronService
from clawlite.scheduler.heartbeat import HeartbeatService
from clawlite.session.store import SessionStore
from clawlite.tools.agents import AgentsListTool
from clawlite.tools.apply_patch import ApplyPatchTool
from clawlite.tools.browser import BrowserTool
from clawlite.tools.cron import CronTool
from clawlite.tools.discord_admin import DiscordAdminTool
from clawlite.tools.exec import ExecTool
from clawlite.tools.files import EditFileTool, EditTool, ListDirTool, ReadFileTool, ReadTool, WriteFileTool, WriteTool
from clawlite.tools.jobs import JobsTool
from clawlite.tools.mcp import MCPTool
from clawlite.tools.memory import (
    MemoryAnalyzeTool,
    MemoryForgetTool,
    MemoryGetTool,
    MemoryLearnTool,
    MemoryRecallTool,
    MemorySearchTool,
)
from clawlite.tools.message import MessageTool
from clawlite.tools.pdf import PdfReadTool
from clawlite.tools.process import ProcessTool
from clawlite.tools.gateway_admin import GatewayAdminTool
from clawlite.tools.registry import ToolRegistry
from clawlite.tools.sessions import (
    SessionStatusTool,
    SessionsHistoryTool,
    SessionsListTool,
    SessionsSendTool,
    SessionsSpawnTool,
    SubagentsTool,
    build_task_with_continuation_metadata,
)
from clawlite.tools.skill import SkillTool
from clawlite.tools.spawn import SpawnTool
from clawlite.tools.tts import TTSTool
from clawlite.tools.web import WebFetchTool, WebSearchTool
from clawlite.utils.logging import bind_event
from clawlite.workspace.loader import WorkspaceLoader


@dataclass(slots=True)
class RuntimeContainer:
    config: AppConfig
    bus: MessageQueue
    engine: AgentEngine
    channels: ChannelManager
    cron: CronService
    heartbeat: HeartbeatService
    autonomy_wake: AutonomyWakeCoordinator
    autonomy_log: AutonomyLog
    workspace: WorkspaceLoader
    skills_loader: SkillsLoader
    memory_monitor: MemoryMonitor | None = None
    supervisor: RuntimeSupervisor | None = None
    self_evolution: Any | None = None
    autonomy: AutonomyService | None = None
    job_queue: JobQueue | None = None
    telemetry: dict[str, Any] | None = None


class _CronAPI:
    def __init__(self, service: CronService) -> None:
        self.service = service

    async def add_job(
        self,
        *,
        session_id: str,
        expression: str,
        prompt: str,
        name: str = "",
        timezone_name: str | None = None,
        channel: str = "",
        target: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return await self.service.add_job(
            session_id=session_id,
            expression=expression,
            prompt=prompt,
            name=name,
            timezone_name=timezone_name,
            channel=channel,
            target=target,
            metadata=metadata,
        )

    def list_jobs(self, *, session_id: str) -> list[dict[str, Any]]:
        return self.service.list_jobs(session_id=session_id)

    def remove_job(self, job_id: str, *, session_id: str | None = None) -> bool:
        return self.service.remove_job(job_id, session_id=session_id)

    def enable_job(self, job_id: str, *, enabled: bool, session_id: str | None = None) -> bool:
        return self.service.enable_job(job_id, enabled=enabled, session_id=session_id)

    async def run_job(self, job_id: str, *, force: bool = True, session_id: str | None = None) -> str | None:
        return await self.service.run_job(job_id, force=force, session_id=session_id)


class _MessageAPI:
    def __init__(self, manager: ChannelManager) -> None:
        self.manager = manager

    async def send(
        self,
        *,
        channel: str,
        target: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return await self.manager.send(channel=channel, target=target, text=text, metadata=metadata)


def _provider_config(config: AppConfig) -> dict[str, Any]:
    active_model = str(config.agents.defaults.model or config.provider.model).strip() or config.provider.model
    model_hint_name = detect_provider_name(active_model)
    hint_selected = config.providers.get(model_hint_name)
    hint_api_key = str(getattr(hint_selected, "api_key", "") or "").strip()
    hint_api_base = str(getattr(hint_selected, "api_base", "") or "").strip()
    local_base_hint = ""
    for local_name in ("ollama", "vllm"):
        local_selected = config.providers.get(local_name)
        local_candidate = str(getattr(local_selected, "api_base", "") or "").strip()
        if local_candidate:
            local_base_hint = local_candidate
            break
    provider_name = detect_provider_name(
        active_model,
        api_key=hint_api_key or str(config.provider.litellm_api_key or "").strip(),
        base_url=hint_api_base or str(config.provider.litellm_base_url or "").strip() or local_base_hint,
    )
    selected = config.providers.get(provider_name) or hint_selected
    selected_api_key = selected.api_key if selected is not None else ""
    selected_api_base = selected.api_base if selected is not None else ""
    providers_payload = config.providers.to_dict()
    providers_payload["litellm"] = {
        "base_url": selected_api_base or config.provider.litellm_base_url,
        "api_key": selected_api_key or config.provider.litellm_api_key,
        "extra_headers": dict(selected.extra_headers) if selected is not None else {},
    }

    return {
        "model": active_model,
        "fallback_model": str(config.provider.fallback_model or "").strip(),
        "retry_max_attempts": int(config.provider.retry_max_attempts),
        "retry_initial_backoff_s": float(config.provider.retry_initial_backoff_s),
        "retry_max_backoff_s": float(config.provider.retry_max_backoff_s),
        "retry_jitter_s": float(config.provider.retry_jitter_s),
        "circuit_failure_threshold": int(config.provider.circuit_failure_threshold),
        "circuit_cooldown_s": float(config.provider.circuit_cooldown_s),
        "auth": {
            "providers": {
                "openai_codex": {
                    "access_token": config.auth.providers.openai_codex.access_token,
                    "account_id": config.auth.providers.openai_codex.account_id,
                    "source": config.auth.providers.openai_codex.source,
                }
            }
        },
        "providers": providers_payload,
    }


def _provider_probe_candidates(provider: Any) -> list[dict[str, str]]:
    raw_candidates = getattr(provider, "_candidates", None)
    rows: list[dict[str, str]] = []
    if isinstance(raw_candidates, list) and raw_candidates:
        for candidate in raw_candidates:
            candidate_provider = getattr(candidate, "provider", None)
            if candidate_provider is None:
                continue
            model_name = str(getattr(candidate, "model", "") or "").strip()
            if not model_name:
                get_default_model = getattr(candidate_provider, "get_default_model", None)
                if callable(get_default_model):
                    model_name = str(get_default_model() or "").strip()
            base_url = str(getattr(candidate_provider, "base_url", "") or "").strip()
            rows.append(
                {
                    "model": model_name,
                    "base_url": base_url,
                    "runtime": detect_local_runtime(base_url),
                }
            )
        if rows:
            return rows

    provider_runtime = getattr(provider, "primary", provider)
    get_default_model = getattr(provider, "get_default_model", None)
    model_name = str(get_default_model() or "").strip() if callable(get_default_model) else ""
    base_url = str(getattr(provider_runtime, "base_url", "") or "").strip()
    return [
        {
            "model": model_name,
            "base_url": base_url,
            "runtime": detect_local_runtime(base_url),
        }
    ]


def _validate_local_provider_runtime(provider: Any) -> None:
    candidates = _provider_probe_candidates(provider)
    local_candidates = [row for row in candidates if row["runtime"]]
    if not local_candidates:
        return

    has_non_local_candidate = len(local_candidates) < len(candidates)
    failures: list[dict[str, Any]] = []
    successes = 0
    for candidate in local_candidates:
        payload = probe_local_provider_runtime(model=candidate["model"], base_url=candidate["base_url"])
        if payload["checked"] and payload["ok"]:
            successes += 1
            continue
        if payload["checked"]:
            failures.append(payload)

    if not failures:
        return

    can_continue = successes > 0 or has_non_local_candidate
    for payload in failures:
        bind_event("gateway.runtime").warning(
            "local runtime probe failed model={} base_url={} error={} detail={} startup_continues={}",
            payload.get("model", ""),
            payload.get("base_url", ""),
            payload.get("error", ""),
            payload.get("detail", ""),
            can_continue,
        )

    if can_continue:
        return

    raise RuntimeError(str(failures[0].get("error") or "provider_config_error:local_runtime_unavailable"))


def build_runtime(
    config: AppConfig,
    *,
    config_path: str | Path | None = None,
    config_profile: str | None = None,
) -> RuntimeContainer:
    bind_event("gateway.runtime").info("building runtime workspace={} state={}", config.workspace_path, config.state_path)
    telemetry = configure_observability(
        enabled=bool(getattr(config.observability, "enabled", False)),
        endpoint=str(getattr(config.observability, "otlp_endpoint", "") or "").strip(),
        service_name=str(getattr(config.observability, "service_name", "") or "clawlite"),
        service_namespace=str(getattr(config.observability, "service_namespace", "") or "").strip(),
    )
    workspace = WorkspaceLoader(workspace_path=config.workspace_path)
    workspace.ensure_runtime_files()
    workspace.bootstrap()
    workspace_path = Path(config.workspace_path).expanduser().resolve()

    provider = build_provider(_provider_config(config))
    _validate_local_provider_runtime(provider)
    cron = CronService(
        store_path=Path(config.state_path) / "cron_jobs.json",
        default_timezone=config.scheduler.timezone,
        max_concurrent_jobs=config.scheduler.cron_max_concurrent_jobs,
        completed_job_retention_seconds=config.scheduler.cron_completed_job_retention_seconds,
    )
    heartbeat_interval = int(config.gateway.heartbeat.interval_s or 1800)
    scheduler_interval = int(getattr(config.scheduler, "heartbeat_interval_seconds", heartbeat_interval) or heartbeat_interval)
    if heartbeat_interval == 1800 and scheduler_interval != 1800:
        heartbeat_interval = scheduler_interval
    heartbeat = HeartbeatService(
        interval_seconds=heartbeat_interval,
        state_path=workspace_path / "memory" / "heartbeat-state.json",
    )
    wake_backlog = int(getattr(config.gateway.autonomy, "max_queue_backlog", 200) or 200)
    if wake_backlog <= 0:
        wake_backlog = 200
    autonomy_wake = AutonomyWakeCoordinator(
        max_pending=wake_backlog,
        journal_path=Path(config.state_path) / "autonomy-wake.json",
    )

    tools = ToolRegistry(
        safety=config.tools.safety,
        default_timeout_s=config.tools.default_timeout_s,
        tool_timeouts=config.tools.timeouts,
    )
    tools.register(
        ExecTool(
            workspace_path=workspace_path,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            path_append=config.tools.exec.path_append,
            timeout_seconds=config.tools.exec.timeout,
            deny_patterns=config.tools.exec.deny_patterns,
            allow_patterns=config.tools.exec.allow_patterns,
            deny_path_patterns=config.tools.exec.deny_path_patterns,
            allow_path_patterns=config.tools.exec.allow_path_patterns,
        )
    )
    tools.register(
        ApplyPatchTool(
            workspace_path=workspace_path,
            restrict_to_workspace=config.tools.restrict_to_workspace,
        )
    )
    tools.register(
        ProcessTool(
            workspace_path=workspace_path,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            path_append=config.tools.exec.path_append,
            deny_patterns=config.tools.exec.deny_patterns,
            allow_patterns=config.tools.exec.allow_patterns,
            deny_path_patterns=config.tools.exec.deny_path_patterns,
            allow_path_patterns=config.tools.exec.allow_path_patterns,
        )
    )
    tools.register(ReadFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(WriteFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(EditFileTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(ReadTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(WriteTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(EditTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(ListDirTool(workspace_path=workspace_path, restrict_to_workspace=config.tools.restrict_to_workspace))
    tools.register(
        WebFetchTool(
            proxy=config.tools.web.proxy,
            max_redirects=config.tools.web.max_redirects,
            timeout=config.tools.web.timeout,
            max_chars=config.tools.web.max_chars,
            allowlist=config.tools.web.allowlist,
            denylist=config.tools.web.denylist,
            block_private_addresses=config.tools.web.block_private_addresses,
        )
    )
    tools.register(
        WebSearchTool(
            proxy=config.tools.web.proxy,
            timeout=config.tools.web.search_timeout,
            brave_api_key=config.tools.web.brave_api_key,
            brave_base_url=config.tools.web.brave_base_url,
            searxng_base_url=config.tools.web.searxng_base_url,
        )
    )
    tools.register(CronTool(_CronAPI(cron)))
    tools.register(MCPTool(config.tools.mcp))
    skills = SkillsLoader(
        state_path=Path(config.state_path) / "skills-state.json",
        config_path=config_path,
        config_profile=config_profile,
    )

    sessions = SessionStore(
        root=Path(config.state_path) / "sessions",
        max_messages_per_session=config.agents.defaults.session_retention_messages,
        session_retention_ttl_s=config.agents.defaults.session_retention_ttl_s,
    )
    memory_backend = resolve_memory_backend(
        backend_name=str(config.agents.defaults.memory.backend or "sqlite"),
        pgvector_url=str(config.agents.defaults.memory.pgvector_url or ""),
    )
    if memory_backend.name == "pgvector" and not memory_backend.is_supported():
        diagnostics_fn = getattr(memory_backend, "diagnostics", None)
        details = diagnostics_fn() if callable(diagnostics_fn) else {}
        detail_text = str(details.get("last_error", "") or "").strip() if isinstance(details, dict) else ""
        raise RuntimeError(
            "memory backend 'pgvector' is not supported in this runtime: configure "
            "agents.defaults.memory.pgvector_url with postgres:// or postgresql://, "
            "or use backend=sqlite"
            + (f" ({detail_text})" if detail_text else "")
        )

    memory = MemoryStore(
        db_path=Path(config.state_path) / "memory.jsonl",
        semantic_enabled=bool(
            getattr(config.agents.defaults.memory, "semantic_search", config.agents.defaults.semantic_memory)
        ),
        memory_auto_categorize=bool(
            getattr(config.agents.defaults.memory, "auto_categorize", config.agents.defaults.memory_auto_categorize)
        ),
        emotional_tracking=bool(
            getattr(config.agents.defaults.memory, "emotional_tracking", False)
        ),
        memory_backend_name=str(config.agents.defaults.memory.backend or "sqlite"),
        memory_backend_url=str(config.agents.defaults.memory.pgvector_url or ""),
    )
    memory.supports_deferred_turn_persistence = True
    tools.register(SkillTool(loader=skills, registry=tools, memory=memory, provider=provider))
    memory_monitor = (
        MemoryMonitor(
            memory,
            retry_backoff_seconds=float(getattr(config.agents.defaults.memory, "proactive_retry_backoff_s", 300.0) or 300.0),
            max_retry_attempts=int(getattr(config.agents.defaults.memory, "proactive_max_retry_attempts", 3) or 3),
        )
        if bool(getattr(config.agents.defaults.memory, "proactive", False))
        else None
    )
    tools.register(MemoryRecallTool(memory))
    tools.register(MemorySearchTool(memory))
    tools.register(MemoryGetTool(workspace_path=workspace_path))
    tools.register(MemoryLearnTool(memory))
    tools.register(MemoryForgetTool(memory))
    tools.register(MemoryAnalyzeTool(memory))
    tools.register(BrowserTool())
    tools.register(TTSTool())
    tools.register(PdfReadTool())
    prompt = PromptBuilder(
        workspace_path=config.workspace_path,
        context_token_budget=config.agents.defaults.context_token_budget,
        workspace_prompt_file_max_bytes=config.agents.defaults.workspace_prompt_file_max_bytes,
    )

    engine = AgentEngine(
        provider=provider,
        tools=tools,
        sessions=sessions,
        memory=memory,
        prompt_builder=prompt,
        skills_loader=skills,
        subagent_state_path=Path(config.state_path) / "subagents",
        max_iterations=config.agents.defaults.max_tool_iterations,
        max_tokens=config.agents.defaults.max_tokens,
        temperature=config.agents.defaults.temperature,
        memory_window=config.agents.defaults.memory_window,
        semantic_history_summary_enabled=config.agents.defaults.semantic_history_summary_enabled,
        tool_result_compaction_enabled=config.agents.defaults.tool_result_compaction_enabled,
        tool_result_compaction_threshold_chars=config.agents.defaults.tool_result_compaction_threshold_chars,
        reasoning_effort_default=config.agents.defaults.reasoning_effort,
        loop_detection=LoopDetectionSettings(
            enabled=config.tools.loop_detection.enabled,
            history_size=config.tools.loop_detection.history_size,
            repeat_threshold=config.tools.loop_detection.repeat_threshold,
            critical_threshold=config.tools.loop_detection.critical_threshold,
        ),
    )

    async def _subagent_runner(session_id: str, task: str) -> str:
        result = await engine.run(session_id=session_id, user_text=task)
        return result.text

    async def _session_runner(session_id: str, task: str):
        return await engine.run(session_id=session_id, user_text=task)

    def _resume_runner_factory(run: Any) -> Any:
        metadata = dict(getattr(run, "metadata", {}) or {})
        target_session_id = str(metadata.get("target_session_id", "") or "").strip() or str(
            getattr(run, "session_id", "") or ""
        ).strip()

        async def _resume_runner(_owner_session_id: str, delegated_task: str) -> str:
            resumed_task = build_task_with_continuation_metadata(delegated_task, metadata)
            result = await engine.run(session_id=target_session_id, user_text=resumed_task)
            return result.text

        return _resume_runner

    setattr(engine, "_subagent_resume_runner_factory", _resume_runner_factory)

    tools.register(SpawnTool(engine.subagents, _subagent_runner, memory=memory))
    tools.register(AgentsListTool(engine, engine.subagents, memory=memory))
    tools.register(SessionsListTool(sessions, manager=engine.subagents))
    tools.register(SessionsHistoryTool(sessions, manager=engine.subagents))
    tools.register(SessionsSendTool(_session_runner, memory=memory))
    tools.register(SessionsSpawnTool(engine.subagents, _session_runner, memory=memory))
    tools.register(SubagentsTool(engine.subagents, resume_runner_factory=_resume_runner_factory))
    tools.register(SessionStatusTool(sessions, engine.subagents))

    jobs_concurrency = int(getattr(config.jobs, "worker_concurrency", 2) if hasattr(config, "jobs") else 2)
    job_queue = JobQueue(concurrency=jobs_concurrency)
    if hasattr(config, "jobs") and getattr(config.jobs, "persist_enabled", False):
        jobs_persist_path = str(getattr(config.jobs, "persist_path", "") or "").strip()
        if not jobs_persist_path:
            jobs_persist_path = str(Path(config.state_path) / "jobs.db")
        jobs_journal = JobJournal(jobs_persist_path)
        jobs_journal.open()
        job_queue.set_journal(jobs_journal)
        job_queue.restore_from_journal()
    tools.register(JobsTool(job_queue))
    tools.register(
        GatewayAdminTool(
            config_path=config_path,
            config_profile=config_profile,
            state_path=config.state_path,
        )
    )

    bus_journal: BusJournal | None = None
    if bool(getattr(config.bus, "journal_enabled", False)):
        journal_path = str(getattr(config.bus, "journal_path", "") or "").strip()
        if not journal_path:
            journal_path = str(Path(config.state_path) / "bus.db")
        bus_journal = BusJournal(journal_path)
        bus_journal.open()

    if str(getattr(config.bus, "backend", "inprocess") or "inprocess").strip().lower() == "redis":
        bus = RedisMessageQueue(
            redis_url=str(getattr(config.bus, "redis_url", "") or "").strip() or "redis://127.0.0.1:6379/0",
            prefix=str(getattr(config.bus, "redis_prefix", "") or "").strip() or "clawlite:bus",
            journal=bus_journal,
        )
    else:
        bus = MessageQueue(journal=bus_journal)
    engine._bus = bus
    channels = ChannelManager(bus=bus, engine=engine)
    autonomy_log = AutonomyLog(path=Path(config.state_path) / "autonomy-events.json")
    tools.register(MessageTool(_MessageAPI(channels)))
    tools.register(
        DiscordAdminTool(
            token=config.channels.discord.token,
            api_base=config.channels.discord.api_base,
            timeout_s=config.channels.discord.timeout_s,
        )
    )

    from clawlite.runtime.self_evolution import SelfEvolutionEngine

    async def _evo_run_llm(prompt: str) -> str:
        provider = engine.provider
        complete_fn = provider.complete
        complete_spec = engine._callable_parameter_spec(complete_fn)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ClawLite's restricted self-evolution patch assistant. "
                    "Never call tools or make unrelated changes. "
                    "Reply only in the exact patch format requested by the user prompt."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        kwargs: dict[str, Any] = {"messages": messages, "tools": []}
        if complete_spec is not None and ("max_tokens" in complete_spec.names or complete_spec.accepts_kwargs):
            kwargs["max_tokens"] = min(int(engine.max_tokens), 1200)
        if complete_spec is not None and ("temperature" in complete_spec.names or complete_spec.accepts_kwargs):
            kwargs["temperature"] = 0.0
        if complete_spec is not None and ("reasoning_effort" in complete_spec.names or complete_spec.accepts_kwargs):
            kwargs["reasoning_effort"] = "low"
        result = await complete_fn(**kwargs)
        normalized = engine._normalize_provider_result(result)
        return str(normalized.text or "")

    async def _evo_notify(source: str, payload: dict[str, Any]) -> bool:
        notice_text = str(payload.get("text", "") or "").strip()
        if not notice_text:
            return False
        action = str(payload.get("action", "") or source or "self_evolution").strip() or "self_evolution"
        status = str(payload.get("status", "") or "info").strip() or "info"
        summary = str(payload.get("summary", "") or f"{action} operator notice").strip()
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return await send_autonomy_notice(
            source=source,
            action=action,
            status=status,
            text=notice_text,
            memory_store=getattr(engine, "memory", None),
            channels=channels,
            autonomy_log=autonomy_log,
            metadata=metadata,
            summary=summary,
        )

    project_root = Path(__file__).resolve().parent.parent.parent
    self_evolution = SelfEvolutionEngine(
        project_root=project_root,
        run_llm=_evo_run_llm,
        notify=_evo_notify,
        cooldown_s=float(config.gateway.autonomy.self_evolution_cooldown_s),
        enabled=bool(config.gateway.autonomy.self_evolution_enabled),
        branch_prefix=str(config.gateway.autonomy.self_evolution_branch_prefix or "self-evolution"),
        require_approval=bool(config.gateway.autonomy.self_evolution_require_approval),
        enabled_for_sessions=list(config.gateway.autonomy.self_evolution_enabled_for_sessions),
        autonomy_session_id=str(config.gateway.autonomy.session_id or "autonomy:system"),
        log_path=Path(config.state_path) / "evolution-log.json",
    )

    async def _channel_inbound_interceptor(event) -> bool:
        handled = await handle_tool_approval_inbound_action(
            event,
            tools=tools,
            channels=channels,
        )
        if handled:
            return True
        handled = await handle_self_evolution_inbound_action(
            event,
            self_evolution=self_evolution,
            channels=channels,
        )
        if handled:
            return True
        return await handle_discord_thread_binding_inbound_action(
            event,
            channels=channels,
        )

    channels.set_inbound_interceptor(_channel_inbound_interceptor)

    bind_event("gateway.runtime").info("runtime ready provider_model={} tools={}", config.agents.defaults.model, len(tools.schema()))
    return RuntimeContainer(
        config=config,
        bus=bus,
        engine=engine,
        channels=channels,
        cron=cron,
        heartbeat=heartbeat,
        autonomy_wake=autonomy_wake,
        autonomy_log=autonomy_log,
        workspace=workspace,
        skills_loader=skills,
        memory_monitor=memory_monitor,
        self_evolution=self_evolution,
        job_queue=job_queue,
        telemetry=telemetry,
    )


__all__ = ["RuntimeContainer", "build_runtime", "_provider_config"]
