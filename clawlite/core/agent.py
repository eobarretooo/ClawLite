from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Iterator

from clawlite.config import settings as app_settings
from clawlite.config.settings import load_config
from clawlite.core.bootstrap import BootstrapManager
from clawlite.core.context_manager import build_context_with_budget
from clawlite.core.model_catalog import estimate_cost_usd, estimate_tokens, get_model_or_default
from clawlite.core.plugin_sdk import HookPhase
from clawlite.core.plugins import PluginManager
from clawlite.core.rbac import Identity, ROLE_SCOPES, Role, check_tool_approval
from clawlite.core.tools import exec_cmd, read_file, write_file
from clawlite.core.vector_memory import search_memory as vector_search_memory
from clawlite.core.vector_memory import store_memory as vector_store_memory
from clawlite.runtime.learning import get_retry_strategy, record_task
from clawlite.runtime.notifications import create_notification
from clawlite.runtime.offline import (
    OllamaExecutionError,
    ProviderExecutionError,
    run_with_offline_fallback,
    run_with_offline_fallback_stream,
)
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
    builtins = """
[Ferramentas Disponiveis]
Voce possui acesso as seguintes ferramentas locais. Se precisar usa-las, responda APENAS com um bloco JSON neste formato (e nada mais):
{"tool_call": {"name": "NOME_DA_FERRAMENTA", "arguments": {"arg1": "valor"}}}

Ferramentas:
1. {"name": "exec_cmd", "description": "Executa um comando no terminal", "arguments": {"command": "string"}}
2. {"name": "read_file", "description": "Le um arquivo do disco", "arguments": {"path": "string"}}
3. {"name": "write_file", "description": "Escreve conteudo em um arquivo", "arguments": {"path": "string", "content": "string"}}

Para interagir com web, utilize as ferramentas de `browser_`:
4. {"name": "browser_goto", "description": "Abre uma URL no navegador e retorna um snapshot (texto + IDs)", "arguments": {"url": "string"}}
5. {"name": "browser_click", "description": "Clica em um elemento pelo seu claw-id", "arguments": {"cid": "string"}}
6. {"name": "browser_fill", "description": "Preenche um elemento com texto pelo seu claw-id", "arguments": {"cid": "string", "text": "string"}}
7. {"name": "browser_read", "description": "Tira um novo snapshot da DOM atual mostrando IDs atualizados", "arguments": {}}
8. {"name": "browser_press", "description": "Pressiona uma tecla especial (ex: Enter, Escape, Tab)", "arguments": {"key": "string"}}
9. {"name": "spawn_subagent", "description": "Delegar tarefa longa para um subagente em background", "arguments": {"task": "string", "label": "string(opcional)"}}
10. {"name": "subagents_list", "description": "Lista subagentes da sessão atual", "arguments": {"active_only": "boolean(opcional)"}}
11. {"name": "subagents_kill", "description": "Cancela subagente por run_id ou todos da sessão", "arguments": {"run_id": "string(opcional)"}}
	"""
    if not plugin_tools:
        return builtins
    lines = [builtins.strip(), "", "Ferramentas de plugins carregados:"]
    idx = 9
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
    actor = identity or _default_identity()
    allowed, policy = check_tool_approval(name, args, identity=actor)
    if not allowed:
        return f"Ferramenta bloqueada: {policy}"

    result = ""
    try:
        if name == "exec_cmd":
            code, out, err = exec_cmd(str(args.get("command", "")))
            result = f"Exit code {code}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
        elif name == "read_file":
            result = read_file(str(args.get("path", "")))
        elif name == "write_file":
            write_file(str(args.get("path", "")), str(args.get("content", "")))
            result = "Arquivo escrito com sucesso."
        elif name.startswith("browser_"):
            from clawlite.runtime.browser_manager import get_browser_manager

            bm = get_browser_manager()
            if name == "browser_goto":
                res = bm.goto(str(args.get("url", "")))
                result = f"{res}\n{bm.get_snapshot()}"
            elif name == "browser_click":
                res = bm.click(str(args.get("cid", "")))
                result = f"{res}\n{bm.get_snapshot()}"
            elif name == "browser_fill":
                res = bm.fill(str(args.get("cid", "")), str(args.get("text", "")))
                result = f"{res}\n{bm.get_snapshot()}"
            elif name == "browser_press":
                res = bm.press(str(args.get("key", "")))
                result = f"{res}\n{bm.get_snapshot()}"
            elif name == "browser_read":
                result = bm.get_snapshot()
            else:
                result = f"Erro: ferramenta browser '{name}' nao mapeada."
        elif name == "spawn_subagent":
            from clawlite.runtime.subagents import get_subagent_runtime

            task = str(args.get("task", "")).strip()
            label = str(args.get("label", "")).strip()
            if not task:
                result = "Erro: argumento 'task' é obrigatório para spawn_subagent."
            else:
                run = get_subagent_runtime().spawn(
                    session_id=(session_id or "default"),
                    task=task,
                    label=label,
                )
                result = json.dumps({"ok": True, "subagent": run}, ensure_ascii=False)
        elif name == "subagents_list":
            from clawlite.runtime.subagents import get_subagent_runtime

            active_only = bool(args.get("active_only", False))
            runs = get_subagent_runtime().list_runs(
                session_id=(session_id or None),
                only_active=active_only,
            )
            result = json.dumps({"ok": True, "runs": runs}, ensure_ascii=False)
        elif name == "subagents_kill":
            from clawlite.runtime.subagents import get_subagent_runtime

            runtime = get_subagent_runtime()
            run_id = str(args.get("run_id", "")).strip()
            if run_id:
                cancelled = runtime.cancel_run(run_id)
                result = json.dumps({"ok": cancelled, "run_id": run_id}, ensure_ascii=False)
            else:
                cancelled_count = runtime.cancel_session(session_id or "")
                result = json.dumps(
                    {"ok": True, "cancelled": cancelled_count, "scope": "session"},
                    ensure_ascii=False,
                )
        else:
            if plugin_manager:
                plugin_output = plugin_manager.try_execute_tool(name, args)
                if plugin_output is not None:
                    result = plugin_output
                else:
                    result = f"Erro: ferramenta '{name}' nao existe."
            else:
                result = f"Erro: ferramenta '{name}' nao existe."
    except Exception as exc:
        result = f"Erro ao executar a ferramenta: {exc}"

    if plugin_manager:
        _fire_hook(
            plugin_manager,
            HookPhase.AFTER_TOOL_CALL,
            session_id=session_id,
            prompt=json.dumps({"tool": name, "arguments": args}, ensure_ascii=False),
            response=result,
            metadata={"policy": policy, "tool_name": name},
        )
    return result


def _run_task_with_timeout(prompt: str, timeout_s: float) -> tuple[str, dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(run_task_with_meta, prompt)
        try:
            return fut.result(timeout=timeout_s)
        except FutureTimeout:
            return (
                f"Timeout: execucao excedeu {timeout_s:.0f}s",
                {
                    "mode": "error",
                    "reason": "attempt-timeout",
                    "model": "n/a",
                    "error": f"timeout>{timeout_s}s",
                    "error_type": "timeout",
                },
            )


def run_task_with_meta(prompt: str, skill: str = "", session_id: str = "") -> tuple[str, dict[str, Any]]:
    del skill, session_id
    requested_model = str(load_config().get("model", "openai/gpt-4o-mini"))

    if prompt.lower().startswith("resuma o diretorio"):
        code, out, err = exec_cmd("ls -la")
        if code == 0:
            output = f"Diretorio atual:\n{out[:3000]}"
            meta = {"mode": "local-tool", "reason": "directory-summary", "model": "local/exec_cmd"}
            return output, _normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)
        output = f"Falha ao listar diretorio: {err}"
        meta = {"mode": "error", "reason": "local-tool-failed", "model": "local/exec_cmd"}
        return output, _normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)

    cfg = load_config()
    requested_model = str(cfg.get("model", "openai/gpt-4o-mini"))
    try:
        output, meta = run_with_offline_fallback(prompt, cfg)
    except ProviderExecutionError as exc:
        create_notification(
            event="provider_failed",
            message=f"Falha no provedor remoto: {exc}",
            priority="high",
            dedupe_key=f"provider_failed:{exc}",
            dedupe_window_seconds=300,
        )
        output = f"Falha no provedor remoto: {exc}"
        meta = {
            "mode": "error",
            "reason": "provider-failed",
            "model": requested_model,
            "error": str(exc),
        }
        return output, _normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)
    except OllamaExecutionError as exc:
        create_notification(
            event="ollama_failed",
            message=f"Falha no fallback Ollama: {exc}",
            priority="high",
            dedupe_key=f"ollama_failed:{exc}",
            dedupe_window_seconds=300,
        )
        output = f"Falha no fallback Ollama: {exc}"
        meta = {
            "mode": "error",
            "reason": "ollama-failed",
            "model": requested_model,
            "error": str(exc),
        }
        return output, _normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)

    if meta.get("mode") == "offline-fallback":
        create_notification(
            event="offline_fallback",
            message=f"Fallback automatico para {meta.get('model')}",
            priority="normal",
            dedupe_key=f"offline_fallback:{meta.get('reason')}:{meta.get('model')}",
            dedupe_window_seconds=300,
            metadata=meta,
        )
    meta = _normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)
    return output, meta


def run_task_stream_with_meta(prompt: str, skill: str = "", session_id: str = "") -> tuple[Iterator[str], dict[str, Any]]:
    """
    Versao em formato streaming (generator) do core agent.
    """
    del skill, session_id
    requested_model = str(load_config().get("model", "openai/gpt-4o-mini"))

    if prompt.lower().startswith("resuma o diretorio"):
        code, out, err = exec_cmd("ls -la")

        def _mock_stream() -> Iterator[str]:
            if code == 0:
                yield f"Diretorio atual:\n{out[:3000]}"
            else:
                yield f"Falha ao listar diretorio: {err}"

        if code == 0:
            meta = {"mode": "local-tool", "reason": "directory-summary", "model": "local/exec_cmd"}
            return _mock_stream(), _normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)
        meta = {"mode": "error", "reason": "local-tool-failed", "model": "local/exec_cmd"}
        return _mock_stream(), _normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)

    cfg = load_config()
    requested_model = str(cfg.get("model", "openai/gpt-4o-mini"))
    try:
        out_stream, meta = run_with_offline_fallback_stream(prompt, cfg)
    except ProviderExecutionError as exc:
        exc_msg = str(exc)
        create_notification(
            event="provider_failed",
            message=f"Falha no provedor remoto (stream): {exc_msg}",
            priority="high",
            dedupe_key=f"provider_failed:{exc_msg}",
            dedupe_window_seconds=300,
        )

        def _err_stream() -> Iterator[str]:
            yield f"Falha no provedor remoto: {exc_msg}"

        meta = {
            "mode": "error",
            "reason": "provider-failed",
            "model": requested_model,
            "error": exc_msg,
        }
        return _err_stream(), _normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)
    except OllamaExecutionError as exc:
        exc_msg = str(exc)
        create_notification(
            event="ollama_failed",
            message=f"Falha no fallback Ollama (stream): {exc_msg}",
            priority="high",
            dedupe_key=f"ollama_failed:{exc_msg}",
            dedupe_window_seconds=300,
        )

        def _err_stream() -> Iterator[str]:
            yield f"Falha no fallback Ollama: {exc_msg}"

        meta = {
            "mode": "error",
            "reason": "ollama-failed",
            "model": requested_model,
            "error": exc_msg,
        }
        return _err_stream(), _normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)

    if meta.get("mode") == "offline-fallback":
        create_notification(
            event="offline_fallback",
            message=f"Fallback automatico para {meta.get('model')}",
            priority="normal",
            dedupe_key=f"offline_fallback:{meta.get('reason')}:{meta.get('model')}",
            dedupe_window_seconds=300,
            metadata=meta,
        )

    return out_stream, _normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)


def _prepare_context(
    *,
    prompt: str,
    session_id: str,
    model_key: str,
    plugin_manager: PluginManager,
) -> tuple[str, str, dict[str, Any]]:
    base_system = build_system_prompt()
    prefix = build_preference_prefix()
    startup_ctx = startup_context_text()
    bootstrap_mgr = BootstrapManager()
    bootstrap_txt = bootstrap_mgr.get_prompt() if bootstrap_mgr.should_run() else ""

    keyword_hits = semantic_search_memory(prompt, max_results=3)
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


def run_task_with_learning(prompt: str, skill: str = "", session_id: str = "") -> str:
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
            BootstrapManager().complete()
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


def run_task_stream_with_learning(prompt: str, skill: str = "", session_id: str = "") -> Iterator[str]:
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
    )

    append_daily_log(f"Task stream iniciada (skill={skill or 'n/a'}): {prompt[:220]}", category="task-start")

    tool_steps = 0
    current_prompt = enriched_prompt

    while tool_steps <= MAX_TOOL_STEPS:
        t0 = time.time()
        out_stream, meta = run_task_stream_with_meta(current_prompt)
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
            BootstrapManager().complete()
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
