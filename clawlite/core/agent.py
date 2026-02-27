from __future__ import annotations

import time
from typing import Any

from clawlite.config.settings import load_config
from clawlite.core.tools import exec_cmd
from clawlite.runtime.notifications import create_notification
from clawlite.runtime.offline import (
    OllamaExecutionError,
    ProviderExecutionError,
    run_with_offline_fallback,
)
from clawlite.runtime.learning import record_task, get_retry_strategy
from clawlite.runtime.preferences import build_preference_prefix
from clawlite.runtime.session_memory import (
    append_daily_log,
    compact_daily_memory,
    semantic_search_memory,
    startup_context_text,
)


def run_task_with_meta(prompt: str) -> tuple[str, dict[str, Any]]:
    if prompt.lower().startswith("resuma o diretório"):
        code, out, err = exec_cmd("ls -la")
        if code == 0:
            return (
                f"Diretório atual:\n{out[:3000]}",
                {"mode": "local-tool", "reason": "directory-summary", "model": "local/exec_cmd"},
            )
        return (
            f"Falha ao listar diretório: {err}",
            {"mode": "error", "reason": "local-tool-failed", "model": "local/exec_cmd"},
        )

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
        return (
            f"Falha no provedor remoto: {exc}",
            {
                "mode": "error",
                "reason": "provider-failed",
                "model": requested_model,
                "error": str(exc),
            },
        )
    except OllamaExecutionError as exc:
        create_notification(
            event="ollama_failed",
            message=f"Falha no fallback Ollama: {exc}",
            priority="high",
            dedupe_key=f"ollama_failed:{exc}",
            dedupe_window_seconds=300,
        )
        return (
            f"Falha no fallback Ollama: {exc}",
            {
                "mode": "error",
                "reason": "ollama-failed",
                "model": requested_model,
                "error": str(exc),
            },
        )

    if meta.get("mode") == "offline-fallback":
        create_notification(
            event="offline_fallback",
            message=f"Fallback automático para {meta.get('model')}",
            priority="normal",
            dedupe_key=f"offline_fallback:{meta.get('reason')}:{meta.get('model')}",
            dedupe_window_seconds=300,
            metadata=meta,
        )
    return output, meta


def run_task(prompt: str) -> str:
    return run_task_with_learning(prompt)


def run_task_with_learning(prompt: str, skill: str = "") -> str:
    """Executa task com aprendizado contínuo: preferências, histórico e auto-retry."""
    # Injetar preferências + contexto de memória de sessão
    prefix = build_preference_prefix()
    startup_ctx = startup_context_text()
    mem_hits = semantic_search_memory(prompt, max_results=3)
    mem_snippets = "\n".join([f"- {h.snippet}" for h in mem_hits])

    context_prefix_parts = []
    if startup_ctx.strip():
        context_prefix_parts.append("[Contexto de Sessão]\n" + startup_ctx[:2200])
    if mem_snippets.strip():
        context_prefix_parts.append("[Memória Relevante]\n" + mem_snippets[:1200])
    if prefix.strip():
        context_prefix_parts.append(prefix)

    context_prefix = "\n\n".join(context_prefix_parts).strip()
    enriched_prompt = f"{context_prefix}\n\n[Pedido]\n{prompt}" if context_prefix else prompt

    append_daily_log(f"Task iniciada (skill={skill or 'n/a'}): {prompt[:220]}", category="task-start")

    attempt = 0
    current_prompt = enriched_prompt
    last_output = ""
    last_meta: dict[str, Any] = {}

    while attempt <= 3:
        t0 = time.time()
        output, meta = run_task_with_meta(current_prompt)
        duration = time.time() - t0

        is_error = meta.get("mode") == "error"
        result = "fail" if is_error else "success"

        record_task(
            prompt=prompt,
            result=result,
            duration_s=duration,
            model=meta.get("model", ""),
            tokens=meta.get("tokens", 0),
            skill=skill,
        )

        append_daily_log(
            f"Task {result} (tentativa={attempt + 1}, skill={skill or 'n/a'}, duração={duration:.2f}s): {prompt[:140]}",
            category="task-result",
        )

        if not is_error:
            compact_daily_memory()
            if meta.get("mode") == "offline-fallback":
                return f"[offline:{meta.get('reason')} -> {meta.get('model')}]\n{output}"
            return output

        last_output = output
        last_meta = meta
        attempt += 1

        retry_prompt = get_retry_strategy(prompt, attempt)
        if retry_prompt is None:
            break
        current_prompt = f"{context_prefix}\n\n{retry_prompt}" if context_prefix else retry_prompt

    compact_daily_memory()
    if last_meta.get("mode") == "offline-fallback":
        return f"[offline:{last_meta.get('reason')} -> {last_meta.get('model')}]\n{last_output}"
    return last_output
