from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
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

MAX_RETRIES = 3
ATTEMPT_TIMEOUT_S = float(os.getenv("CLAWLITE_ATTEMPT_TIMEOUT_S", "90"))
RETRY_BACKOFF_BASE_S = 0.5


def _run_task_with_timeout(prompt: str, timeout_s: float) -> tuple[str, dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(run_task_with_meta, prompt)
        try:
            return fut.result(timeout=timeout_s)
        except FutureTimeout:
            return (
                f"Timeout: execução excedeu {timeout_s:.0f}s",
                {
                    "mode": "error",
                    "reason": "attempt-timeout",
                    "model": "n/a",
                    "error": f"timeout>{timeout_s}s",
                    "error_type": "timeout",
                },
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

    while attempt <= MAX_RETRIES:
        t0 = time.time()
        output, meta = _run_task_with_timeout(current_prompt, ATTEMPT_TIMEOUT_S)
        duration = time.time() - t0

        is_error = meta.get("mode") == "error"
        result = "fail" if is_error else "success"
        err_reason = str(meta.get("reason") or meta.get("error_type") or "")

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
            f"Task {result} (tentativa={attempt + 1}/{MAX_RETRIES + 1}, skill={skill or 'n/a'}, duração={duration:.2f}s, motivo={err_reason or 'n/a'}): {prompt[:140]}",
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

        create_notification(
            event="task_retry",
            message=f"Retry {attempt}/{MAX_RETRIES} para task (skill={skill or 'n/a'})",
            priority="normal",
            dedupe_key=f"task_retry:{skill}:{err_reason}:{attempt}",
            dedupe_window_seconds=30,
            metadata={"attempt": attempt, "reason": err_reason, "skill": skill},
        )

        time.sleep(RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)))
        current_prompt = f"{context_prefix}\n\n{retry_prompt}" if context_prefix else retry_prompt

    compact_daily_memory()
    create_notification(
        event="task_retry_exhausted",
        message=f"Task falhou após {MAX_RETRIES + 1} tentativas (skill={skill or 'n/a'})",
        priority="high",
        dedupe_key=f"task_retry_exhausted:{skill}:{str(last_meta.get('reason', ''))[:40]}",
        dedupe_window_seconds=120,
        metadata={"skill": skill, "last_reason": last_meta.get("reason", "")},
    )
    if last_meta.get("mode") == "offline-fallback":
        return f"[offline:{last_meta.get('reason')} -> {last_meta.get('model')}]\n{last_output}"
    return last_output
