from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Iterator

from clawlite.config import settings as app_settings
from clawlite.config.settings import load_config
from clawlite.core.bootstrap import BootstrapManager
from clawlite.core.context_manager import build_context_with_budget
from clawlite.core.model_catalog import estimate_cost_usd, estimate_tokens, get_model_or_default
from clawlite.core.plugin_sdk import HookPhase
from clawlite.core.plugins import PluginManager
from clawlite.core.rbac import Identity, ROLE_SCOPES, Role
from clawlite.core.vector_memory import search_memory as vector_search_memory
from clawlite.core.vector_memory import store_memory as vector_store_memory
from clawlite.runtime.learning import get_retry_strategy, record_task
from clawlite.runtime.notifications import create_notification
from clawlite.runtime.preferences import build_preference_prefix
from clawlite.runtime.session_memory import (
    append_daily_log,
    compact_daily_memory,
    read_recent_session_messages,
    semantic_search_memory,
    startup_context_text,
)
from clawlite.runtime.system_prompt import build_system_prompt

MAX_RETRIES = 3
ATTEMPT_TIMEOUT_S = float(os.getenv("CLAWLITE_ATTEMPT_TIMEOUT_S", "90"))
RETRY_BACKOFF_BASE_S = 0.5
MAX_TOOL_STEPS = 3

_PLUGIN_MANAGER: PluginManager | None = None
_PLUGINS_LOADED = False


def _get_plugin_manager() -> PluginManager:
    global _PLUGIN_MANAGER, _PLUGINS_LOADED
    if _PLUGIN_MANAGER is None:
        _PLUGIN_MANAGER = PluginManager.get()
    if not _PLUGINS_LOADED:
        try:
            _PLUGIN_MANAGER.load_all()
        except Exception:
            pass
        _PLUGINS_LOADED = True
    return _PLUGIN_MANAGER


def _default_identity() -> Identity:
    return Identity(
        name="agent-core",
        role=Role.AGENT,
        scopes=set(ROLE_SCOPES[Role.AGENT]),
    )


def _recent_history_messages(session_id: str, limit: int = 8) -> list[dict[str, Any]]:
    if not session_id:
        return []
    out: list[dict[str, Any]] = []
    for row in read_recent_session_messages(session_id, limit=limit):
        role = str(row.get("role", "")).strip().lower()
        text = str(row.get("text", "")).strip()
        if not text or role not in {"system", "user", "assistant"}:
            continue
        out.append({"role": role, "text": text})
    return out


def _history_to_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for msg in messages:
        role = str(msg.get("role", "info")).strip()
        text = str(msg.get("text", "")).strip()
        if text:
            parts.append(f"{role}: {text}")
    return "\n".join(parts)


def _safe_vector_search(query: str, max_results: int = 3) -> list[str]:
    try:
        results = vector_search_memory(query, max_results=max_results, min_score=0.15)
    except Exception:
        return []
    snippets: list[str] = []
    for item in results:
        text = str(item.text).strip()
        if not text:
            continue
        snippets.append(f"[{item.source}] {text[:220]}")
    return snippets


def _safe_vector_store(text: str, session_id: str, skill: str, model: str) -> None:
    content = text.strip()
    if not content:
        return
    try:
        source = f"session:{session_id or 'default'}"
        vector_store_memory(
            content,
            source=source,
            metadata={"session_id": session_id, "skill": skill, "model": model},
        )
    except Exception:
        return


def _normalize_meta(meta: dict[str, Any], *, prompt: str, output: str, requested_model: str) -> dict[str, Any]:
    normalized = dict(meta or {})
    model_key = str(normalized.get("model") or requested_model or "openai/gpt-4o-mini")
    entry = get_model_or_default(model_key)
    prompt_tokens = int(normalized.get("prompt_tokens", 0) or 0) or estimate_tokens(prompt)
    completion_tokens = int(normalized.get("completion_tokens", 0) or 0) or (estimate_tokens(output) if output else 0)
    total_tokens = int(normalized.get("tokens", 0) or 0) or (prompt_tokens + completion_tokens)

    normalized["mode"] = str(normalized.get("mode", "unknown"))
    normalized["reason"] = str(normalized.get("reason", "unknown"))
    normalized["model"] = model_key
    normalized["requested_model"] = requested_model
    normalized["model_provider"] = entry.provider
    normalized["model_display_name"] = entry.display_name
    normalized["context_window"] = entry.context_window
    normalized["max_output_tokens"] = entry.max_output_tokens
    normalized["prompt_tokens"] = prompt_tokens
    normalized["completion_tokens"] = completion_tokens
    normalized["tokens"] = total_tokens
    normalized["estimated_cost_usd"] = estimate_cost_usd(model_key, prompt_tokens, completion_tokens)
    return normalized


def _maybe_tool_call(raw_output: str) -> dict[str, Any] | None:
    text = raw_output.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    tool_call = payload.get("tool_call")
    if not isinstance(tool_call, dict):
        return None
    name = str(tool_call.get("name", "")).strip()
    args = tool_call.get("arguments", {})
    if not name:
        return None
    if not isinstance(args, dict):
        args = {}
    return {"name": name, "arguments": args}


def _fire_hook(
    plugin_manager: PluginManager,
    phase: HookPhase,
    *,
    session_id: str,
    prompt: str = "",
    response: str = "",
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str]:
    try:
        ctx = plugin_manager.fire_hooks(
            phase,
            session_id=session_id,
            prompt=prompt,
            response=response,
            metadata=metadata or {},
        )
        return (ctx.prompt or prompt, ctx.response or response)
    except Exception:
        return (prompt, response)


def _build_tools_prompt(plugin_tools: list[dict[str, Any]] | None = None) -> str:
    base_tools: list[dict[str, Any]] = [
        {
            "name": "exec_cmd",
            "description": "Executa um comando no terminal",
            "arguments": {"command": "string"},
        },
        {
            "name": "read_file",
            "description": "Le um arquivo do disco",
            "arguments": {"path": "string"},
        },
        {
            "name": "write_file",
            "description": "Escreve conteudo em um arquivo",
            "arguments": {"path": "string", "content": "string"},
        },
        {
            "name": "browser_goto",
            "description": "Abre uma URL no navegador e retorna um snapshot (texto + IDs)",
            "arguments": {"url": "string"},
        },
        {
            "name": "browser_click",
            "description": "Clica em um elemento pelo seu claw-id",
            "arguments": {"cid": "string"},
        },
        {
            "name": "browser_fill",
            "description": "Preenche um elemento com texto pelo seu claw-id",
            "arguments": {"cid": "string", "text": "string"},
        },
        {
            "name": "browser_read",
            "description": "Tira um novo snapshot da DOM atual mostrando IDs atualizados",
            "arguments": {},
        },
        {
            "name": "browser_press",
            "description": "Pressiona uma tecla especial (ex: Enter, Escape, Tab)",
            "arguments": {"key": "string"},
        },
        {
            "name": "spawn_subagent",
            "description": "Delega tarefa longa para um subagente em background",
            "arguments": {"task": "string", "label": "string(opcional)"},
        },
        {
            "name": "subagents_list",
            "description": "Lista subagentes da sessao atual",
            "arguments": {"active_only": "boolean(opcional)"},
        },
        {
            "name": "subagents_kill",
            "description": "Cancela subagente por run_id ou todos da sessao",
            "arguments": {"run_id": "string(opcional)"},
        },
    ]

    # Skills executaveis (registry + SKILL.md dinamico) viram tools automaticamente no prompt.
    skill_tools: list[dict[str, Any]] = []
    try:
        from clawlite.mcp import mcp_tools_from_skills

        for item in mcp_tools_from_skills()[:60]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name.startswith("skill."):
                continue
            skill_tools.append(
                {
                    "name": name,
                    "description": str(item.get("description", "")).strip(),
                    "arguments": {"command": "string"},
                }
            )
    except Exception:
        # Mantem o fallback minimo mesmo se o catalogo dinamico falhar.
        skill_tools = [
            {"name": "skill.cron", "description": "Agenda tarefas e lembretes", "arguments": {"command": "string"}},
            {
                "name": "skill.web-search",
                "description": "Busca na web com snippets",
                "arguments": {"command": "string"},
            },
            {
                "name": "skill.web-fetch",
                "description": "Extrai conteudo legivel de URL",
                "arguments": {"command": "string"},
            },
        ]

    lines = [
        "[Ferramentas Disponiveis]",
        "Voce possui acesso as ferramentas abaixo.",
        'Se precisar usa-las, responda APENAS com JSON: {"tool_call":{"name":"...","arguments":{...}}}',
        "",
        "Ferramentas locais:",
    ]

    idx = 1
    for item in base_tools:
        lines.append(f"{idx}. {json.dumps(item, ensure_ascii=False)}")
        idx += 1

    lines.append("")
    lines.append("Skills executaveis:")
    for item in skill_tools:
        lines.append(f"{idx}. {json.dumps(item, ensure_ascii=False)}")
        idx += 1

    if not plugin_tools:
        return "\n".join(lines) + "\n"

    lines.extend(["", "Ferramentas de plugins carregados:"])
    for item in plugin_tools:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        payload = {
            "name": name,
            "description": str(item.get("description", "")).strip(),
            "arguments": item.get("parameters") if isinstance(item.get("parameters"), dict) else {},
        }
        lines.append(f"{idx}. {json.dumps(payload, ensure_ascii=False)}")
        idx += 1
    return "\n".join(lines) + "\n"


def _execute_local_tool(
    name: str,
    args: dict[str, Any],
    *,
    identity: Identity | None = None,
    plugin_manager: PluginManager | None = None,
    session_id: str = "",
) -> str:
    from clawlite.agent.execution.tools import get_tool_execution

    return get_tool_execution().execute_local_tool(
        name,
        args,
        identity=identity,
        plugin_manager=plugin_manager,
        session_id=session_id,
    )


def _run_model_with_meta(prompt: str) -> tuple[str, dict[str, Any]]:
    from clawlite.agent.execution.provider import get_provider_execution

    return get_provider_execution().run_model_with_meta(prompt)


def _run_model_stream_with_meta(prompt: str) -> tuple[Iterator[str], dict[str, Any]]:
    from clawlite.agent.execution.provider import get_provider_execution

    return get_provider_execution().run_model_stream_with_meta(prompt)


def _run_task_with_timeout(prompt: str, timeout_s: float) -> tuple[str, dict[str, Any]]:
    from clawlite.agent.execution.provider import get_provider_execution

    return get_provider_execution().run_task_with_timeout(prompt, timeout_s)


def _run_task_with_meta_impl(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> tuple[str, dict[str, Any]]:
    requested_model = str(load_config().get("model", "openai/gpt-4o-mini"))
    identity = _default_identity()
    plugin_manager = _get_plugin_manager()

    enriched_prompt, _, context_meta = _prepare_context(
        prompt=prompt,
        session_id=session_id,
        model_key=requested_model,
        plugin_manager=plugin_manager,
        workspace_path=workspace_path,
    )

    current_prompt = enriched_prompt
    last_output = ""
    last_meta: dict[str, Any] = {}
    tool_steps = 0

    while tool_steps <= MAX_TOOL_STEPS:
        output, meta = _run_model_with_meta(current_prompt)
        meta.update(context_meta)
        meta["tool_steps"] = tool_steps

        if meta.get("mode") == "error":
            return output, meta

        tool_call = _maybe_tool_call(output)
        if tool_call is None or tool_steps >= MAX_TOOL_STEPS:
            return output, meta

        tool_name = str(tool_call.get("name", "")).strip()
        tool_args = tool_call.get("arguments", {}) if isinstance(tool_call.get("arguments"), dict) else {}
        tool_res = _execute_local_tool(
            tool_name,
            tool_args,
            identity=identity,
            plugin_manager=plugin_manager,
            session_id=session_id,
        )
        tool_steps += 1
        current_prompt = (
            f"{current_prompt}\n\n[Sua resposta anterior]\n{output}\n\n"
            f"[Resultado da Ferramenta]\n{tool_res}"
        )
        last_output = output
        last_meta = meta

    return last_output, last_meta


async def _run_task_with_meta_async_impl(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Wrapper oficial async para o fluxo unificado de produção."""
    return await asyncio.to_thread(
        _run_task_with_meta_impl,
        prompt,
        skill,
        session_id,
        workspace_path,
    )


def _run_task_stream_with_meta_impl(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> tuple[Iterator[str], dict[str, Any]]:
    """API de stream compatível: executa fluxo unificado e retorna um único chunk."""
    output, meta = _run_task_with_meta_impl(
        prompt=prompt,
        skill=skill,
        session_id=session_id,
        workspace_path=workspace_path,
    )

    def _single_chunk() -> Iterator[str]:
        if output:
            yield output

    return _single_chunk(), meta


def _prepare_context(
    *,
    prompt: str,
    session_id: str,
    model_key: str,
    plugin_manager: PluginManager,
    workspace_path: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    base_system = build_system_prompt(workspace_path)
    prefix = build_preference_prefix()
    startup_ctx = startup_context_text(workspace_path)
    bootstrap_mgr = BootstrapManager(workspace_path)
    bootstrap_txt = bootstrap_mgr.get_prompt() if bootstrap_mgr.should_run() else ""

    keyword_hits = semantic_search_memory(prompt, max_results=3, path=workspace_path)
    keyword_snippets = [f"- {h.snippet}" for h in keyword_hits if h.snippet]
    vector_snippets = [f"- {s}" for s in _safe_vector_search(prompt, max_results=3)]

    plugin_tools = plugin_manager.get_all_tool_definitions()

    system_parts: list[str] = []
    if base_system.strip():
        system_parts.append("[System Prompt]\n" + base_system[:3200])
    if bootstrap_txt.strip():
        system_parts.append("[Bootstrap Inicial]\n" + bootstrap_txt[:2000])
    if startup_ctx.strip():
        system_parts.append("[Contexto de Sessao]\n" + startup_ctx[:2200])
    if prefix.strip():
        system_parts.append(prefix)

    system_parts.append(_build_tools_prompt(plugin_tools))
    context_prefix = "\n\n".join(system_parts).strip()

    memory_snippets = ""
    merged_snippets = keyword_snippets + vector_snippets
    if merged_snippets:
        memory_snippets = "[Memoria Relevante]\n" + "\n".join(merged_snippets[:12])

    history_messages = _recent_history_messages(session_id, limit=10)
    full_prompt, compacted_history = build_context_with_budget(
        prompt=prompt,
        system_prompt=context_prefix,
        history_messages=history_messages,
        model_key=model_key,
        memory_snippets=memory_snippets,
    )

    history_block = _history_to_text(compacted_history)
    if history_block:
        full_prompt = f"{full_prompt}\n\n[Historico Recente da Conversa Atual]\n{history_block}"

    context_meta = {
        "keyword_memory_hits": len(keyword_hits),
        "vector_memory_hits": len(vector_snippets),
        "history_messages": len(history_messages),
        "history_compacted": len(compacted_history) < len(history_messages),
        "bootstrap_used": bool(bootstrap_txt.strip()),
    }
    return full_prompt, context_prefix, context_meta


def run_task(prompt: str) -> str:
    return run_task_with_learning(prompt)


def _run_task_with_learning_impl(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> str:
    """Executa task com aprendizado continuo: preferencias, memoria, plugins e retry."""
    cfg = app_settings.load_config()
    requested_model = str(cfg.get("model", "openai/gpt-4o-mini"))
    identity = _default_identity()
    plugin_manager = _get_plugin_manager()

    prompt, _ = _fire_hook(
        plugin_manager,
        HookPhase.BEFORE_AGENT_START,
        session_id=session_id,
        prompt=prompt,
        metadata={"skill": skill, "model": requested_model},
    )
    prompt, _ = _fire_hook(
        plugin_manager,
        HookPhase.BEFORE_PROMPT_BUILD,
        session_id=session_id,
        prompt=prompt,
        metadata={"skill": skill, "model": requested_model},
    )

    enriched_prompt, context_prefix, context_meta = _prepare_context(
        prompt=prompt,
        session_id=session_id,
        model_key=requested_model,
        plugin_manager=plugin_manager,
        workspace_path=workspace_path,
    )

    append_daily_log(f"Task iniciada (skill={skill or 'n/a'}): {prompt[:220]}", category="task-start")

    attempt = 0
    current_prompt = enriched_prompt
    last_output = ""
    last_meta: dict[str, Any] = {}
    tool_steps = 0

    while attempt <= MAX_RETRIES:
        t0 = time.time()
        output, meta = _run_task_with_timeout(current_prompt, ATTEMPT_TIMEOUT_S)
        duration = time.time() - t0

        meta = _normalize_meta(meta, prompt=current_prompt, output=output, requested_model=requested_model)
        meta.update(context_meta)
        meta["tool_steps"] = tool_steps

        is_error = meta.get("mode") == "error"
        err_reason = str(meta.get("reason") or meta.get("error_type") or "")

        tool_call = None if is_error else _maybe_tool_call(output)
        if tool_call is not None and tool_steps < MAX_TOOL_STEPS:
            tool_name = str(tool_call.get("name", "")).strip()
            tool_args = tool_call.get("arguments", {}) if isinstance(tool_call.get("arguments"), dict) else {}
            tool_res = _execute_local_tool(
                tool_name,
                tool_args,
                identity=identity,
                plugin_manager=plugin_manager,
                session_id=session_id,
            )
            tool_steps += 1
            current_prompt = (
                f"{current_prompt}\n\n[Sua resposta anterior]\n{output}\n\n"
                f"[Resultado da Ferramenta]\n{tool_res}"
            )
            continue

        result = "fail" if is_error else "success"
        record_task(
            prompt=prompt,
            result=result,
            duration_s=duration,
            model=meta.get("model", ""),
            tokens=meta.get("tokens", 0),
            skill=skill,
            retry_count=attempt,
            error_type=err_reason,
            error_message=str(meta.get("error") or "") or output[:240],
        )

        append_daily_log(
            (
                f"Task {result} (tentativa={attempt + 1}/{MAX_RETRIES + 1}, skill={skill or 'n/a'}, "
                f"duracao={duration:.2f}s, motivo={err_reason or 'n/a'}): {prompt[:140]}"
            ),
            category="task-result",
        )

        if not is_error:
            compact_daily_memory()
            BootstrapManager(workspace_path).complete()
            _safe_vector_store(
                text=f"user: {prompt}\nassistant: {output}",
                session_id=session_id,
                skill=skill,
                model=str(meta.get("model", requested_model)),
            )

            _, hooked_output = _fire_hook(
                plugin_manager,
                HookPhase.AFTER_RESPONSE,
                session_id=session_id,
                prompt=prompt,
                response=output,
                metadata={"meta": meta, "skill": skill},
            )
            output = hooked_output
            meta = _normalize_meta(meta, prompt=current_prompt, output=output, requested_model=requested_model)

            if meta.get("mode") == "offline-fallback":
                return f"[offline:{meta.get('reason')} -> {meta.get('model')}]\n{output}"
            return output

        _fire_hook(
            plugin_manager,
            HookPhase.ON_ERROR,
            session_id=session_id,
            prompt=prompt,
            response=output,
            metadata={"meta": meta, "skill": skill, "attempt": attempt},
        )

        last_output = output
        last_meta = meta
        attempt += 1

        retry_prompt = get_retry_strategy(prompt, attempt)
        if retry_prompt is None:
            break

        create_notification(
            event="task_retry",
            message=f"Retry {attempt}/{MAX_RETRIES} para task (skill={skill or 'n/a'})",
            priority="normal",
            dedupe_key=f"task_retry:{skill}:{err_reason}:{attempt}",
            dedupe_window_seconds=30,
            metadata={"attempt": attempt, "reason": err_reason, "skill": skill},
        )

        time.sleep(RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)))
        current_prompt = f"{context_prefix}\n\n[Pedido]\n{retry_prompt}" if context_prefix else retry_prompt

    compact_daily_memory()
    create_notification(
        event="task_retry_exhausted",
        message=f"Task falhou apos {MAX_RETRIES + 1} tentativas (skill={skill or 'n/a'})",
        priority="high",
        dedupe_key=f"task_retry_exhausted:{skill}:{str(last_meta.get('reason', ''))[:40]}",
        dedupe_window_seconds=120,
        metadata={"skill": skill, "last_reason": last_meta.get("reason", "")},
    )

    if last_meta.get("mode") == "offline-fallback":
        return f"[offline:{last_meta.get('reason')} -> {last_meta.get('model')}]\n{last_output}"
    return last_output


async def _run_task_with_learning_async_impl(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> str:
    """Wrapper async do fluxo com aprendizado contínuo."""
    return await asyncio.to_thread(
        _run_task_with_learning_impl,
        prompt,
        skill,
        session_id,
        workspace_path,
    )


def _run_task_stream_with_learning_impl(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> Iterator[str]:
    """Executa task e faz yield de chunks. Ideal para websockets/dashboard."""
    cfg = app_settings.load_config()
    requested_model = str(cfg.get("model", "openai/gpt-4o-mini"))
    identity = _default_identity()
    plugin_manager = _get_plugin_manager()

    prompt, _ = _fire_hook(
        plugin_manager,
        HookPhase.BEFORE_AGENT_START,
        session_id=session_id,
        prompt=prompt,
        metadata={"skill": skill, "model": requested_model},
    )
    prompt, _ = _fire_hook(
        plugin_manager,
        HookPhase.BEFORE_PROMPT_BUILD,
        session_id=session_id,
        prompt=prompt,
        metadata={"skill": skill, "model": requested_model},
    )

    enriched_prompt, _, context_meta = _prepare_context(
        prompt=prompt,
        session_id=session_id,
        model_key=requested_model,
        plugin_manager=plugin_manager,
        workspace_path=workspace_path,
    )

    append_daily_log(f"Task stream iniciada (skill={skill or 'n/a'}): {prompt[:220]}", category="task-start")

    tool_steps = 0
    current_prompt = enriched_prompt

    while tool_steps <= MAX_TOOL_STEPS:
        t0 = time.time()
        out_stream, meta = _run_model_stream_with_meta(current_prompt)
        meta = _normalize_meta(meta, prompt=current_prompt, output="", requested_model=requested_model)
        meta.update(context_meta)
        meta["tool_steps"] = tool_steps

        is_error = meta.get("mode") == "error"
        err_reason = str(meta.get("reason") or meta.get("error_type") or "")

        if is_error:
            duration = time.time() - t0
            record_task(
                prompt=prompt,
                result="fail",
                duration_s=duration,
                model=meta.get("model", ""),
                tokens=0,
                skill=skill,
                retry_count=0,
                error_type=err_reason,
                error_message=str(meta.get("error") or ""),
            )
            append_daily_log(f"Task stream fail (duracao={duration:.2f}s, motivo={err_reason or 'n/a'})", category="task-result")
            _fire_hook(
                plugin_manager,
                HookPhase.ON_ERROR,
                session_id=session_id,
                prompt=prompt,
                response="",
                metadata={"meta": meta, "skill": skill},
            )
            yield from out_stream
            return

        full_output: list[str] = []
        try:
            if meta.get("mode") == "offline-fallback":
                yield f"[offline:{meta.get('reason')} -> {meta.get('model')}]\n"

            for chunk in out_stream:
                full_output.append(chunk)
                yield chunk

            output_text = "".join(full_output)
            tool_call = _maybe_tool_call(output_text)

            if tool_call is not None and tool_steps < MAX_TOOL_STEPS:
                tool_name = str(tool_call.get("name", "")).strip()
                tool_args = tool_call.get("arguments", {}) if isinstance(tool_call.get("arguments"), dict) else {}
                tool_res = _execute_local_tool(
                    tool_name,
                    tool_args,
                    identity=identity,
                    plugin_manager=plugin_manager,
                    session_id=session_id,
                )
                tool_steps += 1
                yield f"\n\n[Executando ferramenta '{tool_name}'...]\n"
                current_prompt = (
                    f"{current_prompt}\n\n[Sua resposta anterior]\n{output_text}\n\n"
                    f"[Resultado da Ferramenta]\n{tool_res}"
                )
                continue

            compact_daily_memory()
            BootstrapManager(workspace_path).complete()
            _safe_vector_store(
                text=f"user: {prompt}\nassistant: {output_text}",
                session_id=session_id,
                skill=skill,
                model=str(meta.get("model", requested_model)),
            )
            _fire_hook(
                plugin_manager,
                HookPhase.AFTER_RESPONSE,
                session_id=session_id,
                prompt=prompt,
                response=output_text,
                metadata={"meta": meta, "skill": skill},
            )

            duration = time.time() - t0
            record_task(
                prompt=prompt,
                result="success",
                duration_s=duration,
                model=meta.get("model", ""),
                tokens=estimate_tokens(output_text),
                skill=skill,
                retry_count=0,
                error_type="",
                error_message="",
            )
            append_daily_log(f"Task stream success (duracao={duration:.2f}s): {prompt[:140]}", category="task-result")
            return
        except Exception as exc:
            duration = time.time() - t0
            record_task(
                prompt=prompt,
                result="fail",
                duration_s=duration,
                model=meta.get("model", ""),
                tokens=0,
                skill=skill,
                retry_count=0,
                error_type="stream-exception",
                error_message=str(exc),
            )
            _fire_hook(
                plugin_manager,
                HookPhase.ON_ERROR,
                session_id=session_id,
                prompt=prompt,
                response=str(exc),
                metadata={"meta": meta, "skill": skill},
            )
            yield f"\n[Erro durante stream: {exc}]"
            return


def run_task_with_meta(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> tuple[str, dict[str, Any]]:
    from clawlite.agent.loop import get_agent_loop

    return get_agent_loop().run_with_meta(
        prompt=prompt,
        skill=skill,
        session_id=session_id,
        workspace_path=workspace_path,
    )


async def run_task_with_meta_async(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> tuple[str, dict[str, Any]]:
    from clawlite.agent.loop import get_agent_loop

    return await get_agent_loop().run_with_meta_async(
        prompt=prompt,
        skill=skill,
        session_id=session_id,
        workspace_path=workspace_path,
    )


def run_task_stream_with_meta(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> tuple[Iterator[str], dict[str, Any]]:
    from clawlite.agent.loop import get_agent_loop

    return get_agent_loop().stream_with_meta(
        prompt=prompt,
        skill=skill,
        session_id=session_id,
        workspace_path=workspace_path,
    )


def run_task_with_learning(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> str:
    from clawlite.agent.loop import get_agent_loop

    return get_agent_loop().run_with_learning(
        prompt=prompt,
        skill=skill,
        session_id=session_id,
        workspace_path=workspace_path,
    )


async def run_task_with_learning_async(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> str:
    from clawlite.agent.loop import get_agent_loop

    return await get_agent_loop().run_with_learning_async(
        prompt=prompt,
        skill=skill,
        session_id=session_id,
        workspace_path=workspace_path,
    )


def run_task_stream_with_learning(
    prompt: str,
    skill: str = "",
    session_id: str = "",
    workspace_path: str | None = None,
) -> Iterator[str]:
    from clawlite.agent.loop import get_agent_loop

    return get_agent_loop().stream_with_learning(
        prompt=prompt,
        skill=skill,
        session_id=session_id,
        workspace_path=workspace_path,
    )
