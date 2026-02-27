from __future__ import annotations

import os
import socket
import subprocess
from typing import Any, Callable

DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_CONNECTIVITY_TIMEOUT = 1.5
_CONNECTIVITY_PROBE = ("1.1.1.1", 53)


class ProviderExecutionError(RuntimeError):
    """Raised when the remote provider cannot execute the request."""


class OllamaExecutionError(RuntimeError):
    """Raised when the local Ollama execution fails."""


def provider_from_model(model: str) -> str:
    value = (model or "").strip()
    if "/" in value:
        return value.split("/", 1)[0].lower()
    return value.lower()


def is_ollama_model(model: str) -> bool:
    return provider_from_model(model) == "ollama"


def extract_ollama_model(model: str, fallback_model: str = DEFAULT_OLLAMA_MODEL) -> str:
    value = (model or "").strip()
    if "/" in value and is_ollama_model(value):
        _, name = value.split("/", 1)
        if name.strip():
            return name.strip()
    return fallback_model


def check_connectivity(timeout_seconds: float = DEFAULT_CONNECTIVITY_TIMEOUT) -> bool:
    try:
        with socket.create_connection(_CONNECTIVITY_PROBE, timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _provider_token(cfg: dict[str, Any], provider: str) -> str:
    providers = cfg.get("auth", {}).get("providers", {})
    token = providers.get(provider, {}).get("token", "")
    return str(token).strip()


def run_remote_provider(prompt: str, model: str, token: str) -> str:
    if os.getenv("CLAWLITE_SIMULATE_PROVIDER_FAILURE", "").strip() == "1":
        raise ProviderExecutionError("falha simulada de provedor")
    if not token:
        raise ProviderExecutionError("token ausente para provedor remoto")
    return f"[{model}] {prompt}"


def run_ollama(prompt: str, model: str, timeout_seconds: int = 90) -> str:
    cmd = ["ollama", "run", model, prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise OllamaExecutionError("binário 'ollama' não encontrado") from exc
    except subprocess.TimeoutExpired as exc:
        raise OllamaExecutionError(f"ollama timeout após {timeout_seconds}s") from exc

    if proc.returncode != 0:
        error = (proc.stderr or proc.stdout or "erro ao executar ollama").strip()
        raise OllamaExecutionError(error)

    out = (proc.stdout or "").strip()
    if not out:
        return "(ollama sem saída)"
    return out


def resolve_ollama_fallback(cfg: dict[str, Any]) -> str:
    fallback_models = cfg.get("model_fallback", [])
    if isinstance(fallback_models, list):
        for item in fallback_models:
            value = str(item).strip()
            if is_ollama_model(value):
                return value

    ollama_cfg = cfg.get("ollama", {})
    model_name = str(ollama_cfg.get("model", DEFAULT_OLLAMA_MODEL)).strip() or DEFAULT_OLLAMA_MODEL
    return f"ollama/{model_name}"


def _offline_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("offline_mode", {}).get("enabled", True))


def _offline_auto_fallback(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("offline_mode", {}).get("auto_fallback_to_ollama", True))


def _connectivity_timeout(cfg: dict[str, Any]) -> float:
    value = cfg.get("offline_mode", {}).get("connectivity_timeout_sec", DEFAULT_CONNECTIVITY_TIMEOUT)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CONNECTIVITY_TIMEOUT
    return parsed if parsed > 0 else DEFAULT_CONNECTIVITY_TIMEOUT


def _run_ollama_fallback(
    prompt: str,
    cfg: dict[str, Any],
    reason: str,
    ollama_executor: Callable[[str, str], str],
) -> tuple[str, dict[str, str]]:
    fallback = resolve_ollama_fallback(cfg)
    fallback_name = extract_ollama_model(fallback)
    output = ollama_executor(prompt, fallback_name)
    meta = {
        "mode": "offline-fallback",
        "reason": reason,
        "model": f"ollama/{fallback_name}",
    }
    return output, meta


def run_with_offline_fallback(
    prompt: str,
    cfg: dict[str, Any],
    online_executor: Callable[[str, str, str], str] | None = None,
    ollama_executor: Callable[[str, str], str] | None = None,
) -> tuple[str, dict[str, str]]:
    online = online_executor or run_remote_provider
    ollama = ollama_executor or run_ollama

    model = str(cfg.get("model", "openai/gpt-4o-mini"))
    provider = provider_from_model(model)

    if is_ollama_model(model):
        chosen = extract_ollama_model(model)
        return ollama(prompt, chosen), {"mode": "ollama", "model": f"ollama/{chosen}", "reason": "explicit"}

    token = _provider_token(cfg, provider)
    if not _offline_enabled(cfg):
        return online(prompt, model, token), {"mode": "online", "model": model, "reason": "offline-disabled"}

    if not check_connectivity(_connectivity_timeout(cfg)):
        if _offline_auto_fallback(cfg):
            return _run_ollama_fallback(prompt, cfg, "connectivity", ollama)
        raise ProviderExecutionError("sem conectividade e fallback offline desativado")

    try:
        return online(prompt, model, token), {"mode": "online", "model": model, "reason": "provider-ok"}
    except Exception as exc:
        if _offline_auto_fallback(cfg):
            out, meta = _run_ollama_fallback(prompt, cfg, "provider_failure", ollama)
            meta["error"] = str(exc)
            return out, meta
        raise
