from __future__ import annotations

from typing import Any

from clawlite.config.settings import load_config
from clawlite.core.tools import exec_cmd
from clawlite.runtime.notifications import create_notification
from clawlite.runtime.offline import (
    OllamaExecutionError,
    ProviderExecutionError,
    run_with_offline_fallback,
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
    output, meta = run_task_with_meta(prompt)
    if meta.get("mode") == "offline-fallback":
        return f"[offline:{meta.get('reason')} -> {meta.get('model')}]\n{output}"
    return output
