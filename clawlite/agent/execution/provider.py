from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Iterator

from clawlite.config.settings import load_config
from clawlite.core.model_catalog import estimate_cost_usd, estimate_tokens, get_model_or_default
from clawlite.core.tools import exec_cmd
from clawlite.runtime.notifications import create_notification
from clawlite.runtime.offline import (
    OllamaExecutionError,
    ProviderExecutionError,
    run_with_offline_fallback,
    run_with_offline_fallback_stream,
)

DEFAULT_ATTEMPT_TIMEOUT_S = float(os.getenv("CLAWLITE_ATTEMPT_TIMEOUT_S", "90"))


class ProviderExecution:
    def __init__(self, *, default_timeout_s: float = DEFAULT_ATTEMPT_TIMEOUT_S) -> None:
        self.default_timeout_s = float(default_timeout_s)

    @staticmethod
    def _normalize_meta(
        meta: dict[str, Any],
        *,
        prompt: str,
        output: str,
        requested_model: str,
    ) -> dict[str, Any]:
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

    def run_model_with_meta(self, prompt: str) -> tuple[str, dict[str, Any]]:
        requested_model = str(load_config().get("model", "openai/gpt-4o-mini"))

        if prompt.lower().startswith("resuma o diretorio"):
            code, out, err = exec_cmd("ls -la")
            if code == 0:
                output = f"Diretorio atual:\n{out[:3000]}"
                meta = {"mode": "local-tool", "reason": "directory-summary", "model": "local/exec_cmd"}
                return output, self._normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)
            output = f"Falha ao listar diretorio: {err}"
            meta = {"mode": "error", "reason": "local-tool-failed", "model": "local/exec_cmd"}
            return output, self._normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)

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
            return output, self._normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)
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
            return output, self._normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)

        if meta.get("mode") == "offline-fallback":
            create_notification(
                event="offline_fallback",
                message=f"Fallback automatico para {meta.get('model')}",
                priority="normal",
                dedupe_key=f"offline_fallback:{meta.get('reason')}:{meta.get('model')}",
                dedupe_window_seconds=300,
                metadata=meta,
            )
        return output, self._normalize_meta(meta, prompt=prompt, output=output, requested_model=requested_model)

    def run_model_stream_with_meta(self, prompt: str) -> tuple[Iterator[str], dict[str, Any]]:
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
                return _mock_stream(), self._normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)
            meta = {"mode": "error", "reason": "local-tool-failed", "model": "local/exec_cmd"}
            return _mock_stream(), self._normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)

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
            return _err_stream(), self._normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)
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
            return _err_stream(), self._normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)

        if meta.get("mode") == "offline-fallback":
            create_notification(
                event="offline_fallback",
                message=f"Fallback automatico para {meta.get('model')}",
                priority="normal",
                dedupe_key=f"offline_fallback:{meta.get('reason')}:{meta.get('model')}",
                dedupe_window_seconds=300,
                metadata=meta,
            )

        return out_stream, self._normalize_meta(meta, prompt=prompt, output="", requested_model=requested_model)

    def run_task_with_timeout(
        self,
        prompt: str,
        timeout_s: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        effective_timeout = float(timeout_s if timeout_s is not None else self.default_timeout_s)
        with ThreadPoolExecutor(max_workers=1) as executor:
            fut = executor.submit(self.run_model_with_meta, prompt)
            try:
                return fut.result(timeout=effective_timeout)
            except FutureTimeout:
                return (
                    f"Timeout: execucao excedeu {effective_timeout:.0f}s",
                    {
                        "mode": "error",
                        "reason": "attempt-timeout",
                        "model": "n/a",
                        "error": f"timeout>{effective_timeout}s",
                        "error_type": "timeout",
                    },
                )


_PROVIDER_EXECUTION: ProviderExecution | None = None


def get_provider_execution() -> ProviderExecution:
    global _PROVIDER_EXECUTION
    if _PROVIDER_EXECUTION is None:
        _PROVIDER_EXECUTION = ProviderExecution()
    return _PROVIDER_EXECUTION

