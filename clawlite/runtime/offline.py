from __future__ import annotations

import os
import socket
import subprocess
from typing import Any, Callable, Iterator

import httpx

DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_CONNECTIVITY_TIMEOUT = 1.5
DEFAULT_REMOTE_TIMEOUT = 30.0
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
    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_name = env_map.get(provider, "")
    if env_name:
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            return env_value

    providers = cfg.get("auth", {}).get("providers", {})
    token = providers.get(provider, {}).get("token", "")
    return str(token).strip()


def _model_name_without_provider(model: str) -> str:
    value = (model or "").strip()
    if "/" not in value:
        return value
    return value.split("/", 1)[1].strip()


def _extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderExecutionError("resposta inválida do provedor remoto (choices ausente)")

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        if parts:
            return "\n".join(parts)

    raise ProviderExecutionError("resposta sem conteúdo textual do provedor remoto")


def _extract_anthropic_content(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list) or not content:
        raise ProviderExecutionError("resposta inválida do provedor remoto (content ausente)")

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())

    if not parts:
        raise ProviderExecutionError("resposta sem conteúdo textual do provedor remoto")
    return "\n".join(parts)


def _remote_timeout_seconds() -> float:
    raw = os.getenv("CLAWLITE_REMOTE_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_REMOTE_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_REMOTE_TIMEOUT
    return value if value > 0 else DEFAULT_REMOTE_TIMEOUT


def run_remote_provider(prompt: str, model: str, token: str) -> str:
    if os.getenv("CLAWLITE_SIMULATE_PROVIDER_FAILURE", "").strip() == "1":
        raise ProviderExecutionError("falha simulada de provedor")

    provider = provider_from_model(model)
    model_name = _model_name_without_provider(model)
    if not provider or not model_name:
        raise ProviderExecutionError("modelo remoto inválido; use provider/model")

    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_name = env_map.get(provider)
    resolved_token = (os.getenv(env_name, "").strip() if env_name else "") or str(token or "").strip()
    if not resolved_token:
        raise ProviderExecutionError(f"token ausente para provedor remoto '{provider}'")

    timeout = _remote_timeout_seconds()

    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }
    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": resolved_token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
    elif provider == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }
    else:
        raise ProviderExecutionError(f"provedor remoto não suportado: '{provider}'")

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        raise ProviderExecutionError(f"timeout ao chamar provedor remoto '{provider}'") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else "desconhecido"
        detail = ""
        if exc.response is not None:
            detail = (exc.response.text or "").strip()
            if len(detail) > 240:
                detail = detail[:240] + "..."
        msg = f"erro HTTP do provedor remoto '{provider}' (status {status_code})"
        if detail:
            msg = f"{msg}: {detail}"
        raise ProviderExecutionError(msg) from exc
    except httpx.RequestError as exc:
        raise ProviderExecutionError(f"erro de rede ao chamar provedor remoto '{provider}': {exc}") from exc
    except ValueError as exc:
        raise ProviderExecutionError(f"resposta JSON inválida do provedor remoto '{provider}'") from exc

    if provider == "anthropic":
        return _extract_anthropic_content(data)
    return _extract_chat_content(data)


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


def resolve_online_fallbacks(cfg: dict[str, Any], excluded_model: str) -> list[str]:
    fallback_models = cfg.get("model_fallback", [])
    result = []
    if isinstance(fallback_models, list):
        for item in fallback_models:
            value = str(item).strip()
            if value and not is_ollama_model(value) and value != excluded_model:
                result.append(value)
    return result


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


def _run_ollama_fallback_stream(
    prompt: str,
    cfg: dict[str, Any],
    reason: str,
    ollama_executor: Callable[[str, str], Iterator[str]],
) -> tuple[Iterator[str], dict[str, str]]:
    fallback = resolve_ollama_fallback(cfg)
    fallback_name = extract_ollama_model(fallback)
    meta = {
        "mode": "offline-fallback",
        "reason": reason,
        "model": f"ollama/{fallback_name}",
    }
    return ollama_executor(prompt, fallback_name), meta


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
        # Try online fallbacks first
        online_fallbacks = resolve_online_fallbacks(cfg, model)
        for fb_model in online_fallbacks:
            fb_provider = provider_from_model(fb_model)
            fb_token = _provider_token(cfg, fb_provider)
            if fb_token:
                try:
                    return online(prompt, fb_model, fb_token), {"mode": "online", "model": fb_model, "reason": "online-fallback"}
                except Exception:
                    continue

        if _offline_auto_fallback(cfg):
            out, meta = _run_ollama_fallback(prompt, cfg, "provider_failure", ollama)
            meta["error"] = str(exc)
            return out, meta
        raise

def run_with_offline_fallback_stream(
    prompt: str,
    cfg: dict[str, Any],
) -> tuple[Iterator[str], dict[str, str]]:
    from clawlite.runtime.streaming import run_remote_provider_stream, run_ollama_stream
    
    online = run_remote_provider_stream
    ollama = run_ollama_stream
    
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
            return _run_ollama_fallback_stream(prompt, cfg, "connectivity", ollama)
        raise ProviderExecutionError("sem conectividade e fallback offline desativado")
        
    try:
        return online(prompt, model, token), {"mode": "online", "model": model, "reason": "provider-ok"}
    except Exception as exc:
        online_fallbacks = resolve_online_fallbacks(cfg, model)
        for fb_model in online_fallbacks:
            fb_provider = provider_from_model(fb_model)
            fb_token = _provider_token(cfg, fb_provider)
            if fb_token:
                try:
                    return online(prompt, fb_model, fb_token), {"mode": "online", "model": fb_model, "reason": "online-fallback"}
                except Exception:
                    continue

        if _offline_auto_fallback(cfg):
            out_stream, meta = _run_ollama_fallback_stream(prompt, cfg, "provider_failure", ollama)
            meta["error"] = str(exc)
            return out_stream, meta
        raise
