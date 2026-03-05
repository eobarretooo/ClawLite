from __future__ import annotations

import os
import json
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx

from clawlite.config.loader import save_config
from clawlite.config.schema import AppConfig
from clawlite.core.memory import MemoryStore
from clawlite.core.memory_monitor import MemoryMonitor
from clawlite.providers.registry import SPECS, detect_provider_name
from clawlite.workspace.loader import TEMPLATE_FILES
from clawlite.workspace.loader import WorkspaceLoader


def _mask_secret(value: str, *, keep: int = 4) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if len(token) <= keep:
        return "*" * len(token)
    return f"{'*' * max(3, len(token) - keep)}{token[-keep:]}"


SUPPORTED_PROVIDER_AUTH: tuple[str, ...] = (
    "openai",
    "gemini",
    "groq",
    "deepseek",
    "anthropic",
    "openrouter",
    "custom",
)


def _normalize_provider_name(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _resolve_supported_provider(provider: str) -> str:
    provider_norm = _normalize_provider_name(provider)
    provider_key = provider_norm.replace("-", "_")
    if provider_key not in SUPPORTED_PROVIDER_AUTH:
        raise ValueError(f"unsupported_provider:{provider_norm or provider}")
    return provider_key


def provider_set_auth(
    config: AppConfig,
    *,
    config_path: str | Path | None,
    provider: str,
    api_key: str,
    api_base: str = "",
    extra_headers: dict[str, str] | None = None,
    clear_headers: bool = False,
    clear_api_base: bool = False,
) -> dict[str, Any]:
    try:
        provider_key = _resolve_supported_provider(provider)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    token = str(api_key or "").strip()
    if not token:
        return {
            "ok": False,
            "error": "api_key_required",
            "provider": provider_key,
        }

    selected = getattr(config.providers, provider_key)
    selected.api_key = token

    if clear_headers:
        selected.extra_headers = {}
    if extra_headers:
        merged = dict(selected.extra_headers)
        merged.update({str(k): str(v) for k, v in extra_headers.items()})
        selected.extra_headers = merged

    if clear_api_base:
        selected.api_base = ""
    else:
        base_value = str(api_base or "").strip()
        if base_value:
            selected.api_base = base_value

    saved_path = save_config(config, path=config_path)
    return {
        "ok": True,
        "provider": provider_key,
        "api_key_masked": _mask_secret(selected.api_key),
        "api_base": str(selected.api_base or ""),
        "extra_headers": dict(selected.extra_headers or {}),
        "saved_path": str(saved_path),
    }


def provider_clear_auth(
    config: AppConfig,
    *,
    config_path: str | Path | None,
    provider: str,
    clear_api_base: bool = False,
) -> dict[str, Any]:
    try:
        provider_key = _resolve_supported_provider(provider)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    selected = getattr(config.providers, provider_key)
    selected.api_key = ""
    selected.extra_headers = {}
    if clear_api_base:
        selected.api_base = ""

    saved_path = save_config(config, path=config_path)
    return {
        "ok": True,
        "provider": provider_key,
        "api_key_masked": _mask_secret(selected.api_key),
        "api_base": str(selected.api_base or ""),
        "extra_headers": dict(selected.extra_headers or {}),
        "saved_path": str(saved_path),
    }


def heartbeat_trigger(
    config: AppConfig,
    *,
    gateway_url: str = "",
    token: str = "",
    timeout: float = 10.0,
) -> dict[str, Any]:
    base_url = str(gateway_url or "").strip().rstrip("/")
    if not base_url:
        base_url = f"http://{config.gateway.host}:{int(config.gateway.port)}"

    resolved_token = str(token or "").strip() or str(config.gateway.auth.token or "").strip()
    endpoint = "/v1/control/heartbeat/trigger"
    headers: dict[str, str] = {}
    if resolved_token:
        headers["Authorization"] = f"Bearer {resolved_token}"

    payload: dict[str, Any] = {
        "ok": False,
        "base_url": base_url,
        "endpoint": endpoint,
        "token_configured": bool(resolved_token),
    }

    try:
        with httpx.Client(timeout=max(0.1, float(timeout)), headers=headers) as client:
            response = client.post(f"{base_url}{endpoint}")
    except Exception as exc:
        payload["error"] = str(exc)
        payload["error_type"] = exc.__class__.__name__
        return payload

    body: Any
    try:
        body = response.json()
    except Exception:
        body = response.text

    payload["status_code"] = int(response.status_code)
    payload["response"] = body

    if response.is_success and isinstance(body, dict) and bool(body.get("ok", False)):
        payload["ok"] = True
        payload["decision"] = body.get("decision", {})
        return payload

    if isinstance(body, dict):
        detail = body.get("detail", body.get("error", "heartbeat_trigger_failed"))
    else:
        detail = str(body or "heartbeat_trigger_failed")
    payload["error"] = str(detail)
    return payload


def resolve_codex_auth(config: AppConfig) -> dict[str, Any]:
    codex = config.auth.providers.openai_codex
    cfg_token = str(codex.access_token or "").strip()
    cfg_account = str(codex.account_id or "").strip()
    cfg_source = str(codex.source or "").strip()

    env_token_candidates: tuple[tuple[str, str], ...] = (
        ("CLAWLITE_CODEX_ACCESS_TOKEN", os.getenv("CLAWLITE_CODEX_ACCESS_TOKEN", "").strip()),
        ("OPENAI_CODEX_ACCESS_TOKEN", os.getenv("OPENAI_CODEX_ACCESS_TOKEN", "").strip()),
        ("OPENAI_ACCESS_TOKEN", os.getenv("OPENAI_ACCESS_TOKEN", "").strip()),
    )
    env_account_candidates: tuple[tuple[str, str], ...] = (
        ("CLAWLITE_CODEX_ACCOUNT_ID", os.getenv("CLAWLITE_CODEX_ACCOUNT_ID", "").strip()),
        ("OPENAI_ORG_ID", os.getenv("OPENAI_ORG_ID", "").strip()),
    )

    env_token_name = ""
    env_token = ""
    for name, value in env_token_candidates:
        if value:
            env_token_name = name
            env_token = value
            break

    env_account_name = ""
    env_account = ""
    for name, value in env_account_candidates:
        if value:
            env_account_name = name
            env_account = value
            break

    token = cfg_token or env_token
    account_id = cfg_account or env_account
    if cfg_token:
        source = cfg_source or "config"
    elif env_token_name:
        source = f"env:{env_token_name}"
    else:
        source = ""

    return {
        "configured": bool(token),
        "access_token": token,
        "account_id": account_id,
        "source": source,
        "token_masked": _mask_secret(token),
        "account_id_masked": _mask_secret(account_id),
        "env_token_name": env_token_name,
        "env_account_name": env_account_name,
    }


def _parse_oauth_result(payload: Any) -> tuple[str, str]:
    if isinstance(payload, str):
        return payload.strip(), ""
    if isinstance(payload, dict):
        token = str(payload.get("access_token", payload.get("accessToken", payload.get("token", ""))) or "").strip()
        account = str(
            payload.get(
                "account_id",
                payload.get("accountId", payload.get("org_id", payload.get("orgId", payload.get("organization", "")))),
            )
            or ""
        ).strip()
        return token, account
    return "", ""


def provider_login_openai_codex(
    config: AppConfig,
    *,
    config_path: str | Path | None,
    access_token: str = "",
    account_id: str = "",
    set_model: bool = False,
    interactive: bool = True,
) -> dict[str, Any]:
    token = str(access_token or "").strip()
    resolved_account_id = str(account_id or "").strip()
    source = ""

    if token:
        source = "cli:access_token"
    else:
        if interactive:
            try:
                import oauth_cli_kit  # type: ignore

                get_token = getattr(oauth_cli_kit, "get_token", None)
                login_oauth_interactive = getattr(oauth_cli_kit, "login_oauth_interactive", None)
                if callable(get_token):
                    oauth_result = get_token()
                    token, oauth_account = _parse_oauth_result(oauth_result)
                    if token:
                        source = "oauth_cli_kit:get_token"
                        if not resolved_account_id and oauth_account:
                            resolved_account_id = oauth_account
                if (not token) and callable(login_oauth_interactive):
                    oauth_result: Any = None
                    try:
                        oauth_result = login_oauth_interactive(provider="openai-codex")
                    except TypeError:
                        oauth_result = login_oauth_interactive("openai-codex")
                    token, oauth_account = _parse_oauth_result(oauth_result)
                    if token:
                        source = "oauth_cli_kit:interactive"
                        if not resolved_account_id and oauth_account:
                            resolved_account_id = oauth_account
            except Exception:
                pass

        if not token:
            status = resolve_codex_auth(config)
            token = str(status.get("access_token", "") or "").strip()
            if not resolved_account_id:
                resolved_account_id = str(status.get("account_id", "") or "").strip()
            if token:
                source = str(status.get("source", "") or "") or "env"

    if not token:
        return {
            "ok": False,
            "provider": "openai_codex",
            "error": "codex_access_token_missing",
            "detail": "Missing Codex access token. Use --access-token or run interactive login.",
        }

    config.auth.providers.openai_codex.access_token = token
    config.auth.providers.openai_codex.account_id = resolved_account_id
    config.auth.providers.openai_codex.source = source or "config"

    if set_model:
        model = "openai-codex/gpt-5.3-codex"
        config.provider.model = model
        config.agents.defaults.model = model

    saved_path = save_config(config, path=config_path)
    status = resolve_codex_auth(config)
    return {
        "ok": True,
        "provider": "openai_codex",
        "configured": bool(status["configured"]),
        "token_masked": status["token_masked"],
        "account_id_masked": status["account_id_masked"],
        "source": status["source"],
        "model": str(config.agents.defaults.model or config.provider.model),
        "saved_path": str(saved_path),
    }


def provider_status(config: AppConfig, provider: str = "openai-codex") -> dict[str, Any]:
    provider_norm = str(provider or "openai-codex").strip().lower().replace("_", "-")
    if provider_norm in {"openai-codex", "codex"}:
        status = resolve_codex_auth(config)
        return {
            "ok": True,
            "provider": "openai_codex",
            "configured": bool(status["configured"]),
            "token_masked": status["token_masked"],
            "account_id_masked": status["account_id_masked"],
            "source": status["source"],
            "model": str(config.agents.defaults.model or config.provider.model),
        }

    supported_api_key_providers = {
        "openai",
        "gemini",
        "groq",
        "deepseek",
        "anthropic",
        "openrouter",
        "custom",
    }

    provider_key = provider_norm.replace("-", "_")
    spec = next((row for row in SPECS if row.name == provider_key), None)
    if spec is None or spec.name not in supported_api_key_providers:
        return {
            "ok": False,
            "error": f"unsupported_provider:{provider}",
        }

    selected = getattr(config.providers, spec.name, None)
    cfg_api_key = str(getattr(selected, "api_key", "") or "").strip()
    cfg_base_url = str(getattr(selected, "api_base", "") or "").strip()
    global_api_key = str(config.provider.litellm_api_key or "").strip()
    global_base_url = str(config.provider.litellm_base_url or "").strip()

    env_names: list[str] = list(spec.key_envs)
    env_names.extend(["CLAWLITE_LITELLM_API_KEY", "CLAWLITE_API_KEY"])
    env_first_name = ""
    env_first_value = ""
    env_key_present = False
    seen: set[str] = set()
    for env_name in env_names:
        if env_name in seen:
            continue
        seen.add(env_name)
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            env_key_present = True
            if not env_first_name:
                env_first_name = env_name
                env_first_value = env_value

    api_key = ""
    api_key_source = ""
    if cfg_api_key:
        api_key = cfg_api_key
        api_key_source = f"config:providers.{spec.name}.api_key"
    elif global_api_key:
        api_key = global_api_key
        api_key_source = "config:provider.litellm_api_key"
    elif env_first_value:
        api_key = env_first_value
        api_key_source = f"env:{env_first_name}"

    base_url = ""
    base_url_source = ""
    if cfg_base_url:
        base_url = cfg_base_url
        base_url_source = f"config:providers.{spec.name}.api_base"
    elif global_base_url:
        base_url = global_base_url
        base_url_source = "config:provider.litellm_base_url"
    elif spec.default_base_url:
        base_url = spec.default_base_url
        base_url_source = f"spec:{spec.name}.default_base_url"

    return {
        "ok": True,
        "provider": spec.name,
        "configured": bool(api_key),
        "auth_mode": "api_key",
        "api_key_masked": _mask_secret(api_key),
        "api_key_source": api_key_source,
        "base_url": base_url,
        "base_url_source": base_url_source,
        "env_key_present": env_key_present,
        "model": str(config.agents.defaults.model or config.provider.model),
    }


def provider_logout_openai_codex(config: AppConfig, *, config_path: str | Path | None) -> dict[str, Any]:
    config.auth.providers.openai_codex.access_token = ""
    config.auth.providers.openai_codex.account_id = ""
    config.auth.providers.openai_codex.source = ""
    saved_path = save_config(config, path=config_path)
    status = resolve_codex_auth(config)
    return {
        "ok": True,
        "provider": "openai_codex",
        "configured": bool(status["configured"]),
        "saved_path": str(saved_path),
    }


SUPPORTED_PROVIDER_USE: tuple[str, ...] = (
    "openai-codex",
    "openai",
    "gemini",
    "groq",
    "deepseek",
    "anthropic",
    "openrouter",
    "custom",
)

OPENAI_COMPATIBLE_PROBE_PROVIDERS: tuple[str, ...] = (
    "openai",
    "gemini",
    "groq",
    "deepseek",
    "openrouter",
    "custom",
    "openai_codex",
)


def _provider_spec(name: str) -> Any:
    provider_name = str(name or "").strip().lower().replace("-", "_")
    return next((row for row in SPECS if row.name == provider_name), None)


def _resolve_provider_probe_target(config: AppConfig, provider_name: str) -> dict[str, Any]:
    provider_key = str(provider_name or "").strip().lower().replace("-", "_")

    if provider_key == "openai_codex":
        codex = resolve_codex_auth(config)
        cfg_openai_base = str(getattr(config.providers.openai, "api_base", "") or "").strip()
        global_base = str(config.provider.litellm_base_url or "").strip()
        base_url = cfg_openai_base or global_base or "https://api.openai.com/v1"
        base_url_source = (
            "config:providers.openai.api_base"
            if cfg_openai_base
            else "config:provider.litellm_base_url"
            if global_base
            else "spec:openai.default_base_url"
        )
        return {
            "ok": True,
            "provider": provider_key,
            "api_key": str(codex.get("access_token", "") or "").strip(),
            "api_key_masked": str(codex.get("token_masked", "") or ""),
            "api_key_source": str(codex.get("source", "") or ""),
            "base_url": base_url,
            "base_url_source": base_url_source,
            "auth_mode": "oauth",
        }

    if provider_key == "ollama":
        cfg_base = str(config.providers.custom.api_base or "").strip()
        global_base = str(config.provider.litellm_base_url or "").strip()
        env_base = str(os.getenv("OLLAMA_BASE_URL", "") or "").strip()
        base_url = cfg_base or global_base or env_base or "http://127.0.0.1:11434"
        base_url_source = (
            "config:providers.custom.api_base"
            if cfg_base
            else "config:provider.litellm_base_url"
            if global_base
            else "env:OLLAMA_BASE_URL"
            if env_base
            else "default:ollama"
        )
        return {
            "ok": True,
            "provider": provider_key,
            "api_key": "",
            "api_key_masked": "",
            "api_key_source": "",
            "base_url": base_url,
            "base_url_source": base_url_source,
            "auth_mode": "none",
        }

    spec = _provider_spec(provider_key)
    if spec is None:
        return {"ok": False, "provider": provider_key, "error": f"unsupported_provider:{provider_key}"}

    selected = getattr(config.providers, spec.name, None)
    cfg_api_key = str(getattr(selected, "api_key", "") or "").strip()
    cfg_base_url = str(getattr(selected, "api_base", "") or "").strip()
    global_api_key = str(config.provider.litellm_api_key or "").strip()
    global_base_url = str(config.provider.litellm_base_url or "").strip()

    env_names: list[str] = list(spec.key_envs)
    env_names.extend(["CLAWLITE_LITELLM_API_KEY", "CLAWLITE_API_KEY"])
    env_first_name = ""
    env_first_value = ""
    seen: set[str] = set()
    for env_name in env_names:
        if env_name in seen:
            continue
        seen.add(env_name)
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            env_first_name = env_name
            env_first_value = env_value
            break

    api_key = ""
    api_key_source = ""
    if cfg_api_key:
        api_key = cfg_api_key
        api_key_source = f"config:providers.{spec.name}.api_key"
    elif global_api_key:
        api_key = global_api_key
        api_key_source = "config:provider.litellm_api_key"
    elif env_first_value:
        api_key = env_first_value
        api_key_source = f"env:{env_first_name}"

    base_url = ""
    base_url_source = ""
    if cfg_base_url:
        base_url = cfg_base_url
        base_url_source = f"config:providers.{spec.name}.api_base"
    elif global_base_url:
        base_url = global_base_url
        base_url_source = "config:provider.litellm_base_url"
    elif spec.default_base_url:
        base_url = spec.default_base_url
        base_url_source = f"spec:{spec.name}.default_base_url"

    if provider_key == "openai":
        base_norm = base_url.lower()
        if ("11434" in base_norm) or ("ollama" in base_norm):
            return _resolve_provider_probe_target(config, "ollama")

    return {
        "ok": True,
        "provider": spec.name,
        "api_key": api_key,
        "api_key_masked": _mask_secret(api_key),
        "api_key_source": api_key_source,
        "base_url": base_url,
        "base_url_source": base_url_source,
        "auth_mode": "api_key",
    }


def provider_live_probe(config: AppConfig, *, timeout: float = 3.0) -> dict[str, Any]:
    model = str(config.agents.defaults.model or config.provider.model).strip() or str(config.provider.model)
    detected = detect_provider_name(model)
    target = _resolve_provider_probe_target(config, detected)
    if not bool(target.get("ok", False)):
        return {
            "ok": False,
            "provider": str(target.get("provider", detected) or detected),
            "provider_detected": detected,
            "model": model,
            "status_code": 0,
            "error": str(target.get("error", "provider_resolution_failed") or "provider_resolution_failed"),
            "api_key_masked": "",
            "api_key_source": "",
            "base_url": "",
            "base_url_source": "",
            "endpoint": "",
        }

    provider = str(target.get("provider", detected) or detected)
    base_url = str(target.get("base_url", "") or "").strip().rstrip("/")
    api_key = str(target.get("api_key", "") or "").strip()
    endpoint = ""
    headers: dict[str, str] = {}

    if provider in OPENAI_COMPATIBLE_PROBE_PROVIDERS:
        endpoint = "/models"
        if not api_key:
            return {
                "ok": False,
                "provider": provider,
                "provider_detected": detected,
                "model": model,
                "status_code": 0,
                "error": "api_key_missing",
                "api_key_masked": str(target.get("api_key_masked", "") or ""),
                "api_key_source": str(target.get("api_key_source", "") or ""),
                "base_url": base_url,
                "base_url_source": str(target.get("base_url_source", "") or ""),
                "endpoint": endpoint,
            }
        headers["Authorization"] = f"Bearer {api_key}"
    elif provider == "anthropic":
        endpoint = "/v1/models"
        if not api_key:
            return {
                "ok": False,
                "provider": provider,
                "provider_detected": detected,
                "model": model,
                "status_code": 0,
                "error": "api_key_missing",
                "api_key_masked": str(target.get("api_key_masked", "") or ""),
                "api_key_source": str(target.get("api_key_source", "") or ""),
                "base_url": base_url,
                "base_url_source": str(target.get("base_url_source", "") or ""),
                "endpoint": endpoint,
            }
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif provider == "ollama":
        endpoint = "/api/tags"
    else:
        return {
            "ok": False,
            "provider": provider,
            "provider_detected": detected,
            "model": model,
            "status_code": 0,
            "error": f"unsupported_provider:{provider}",
            "api_key_masked": str(target.get("api_key_masked", "") or ""),
            "api_key_source": str(target.get("api_key_source", "") or ""),
            "base_url": base_url,
            "base_url_source": str(target.get("base_url_source", "") or ""),
            "endpoint": endpoint,
        }

    if not base_url:
        return {
            "ok": False,
            "provider": provider,
            "provider_detected": detected,
            "model": model,
            "status_code": 0,
            "error": "base_url_missing",
            "api_key_masked": str(target.get("api_key_masked", "") or ""),
            "api_key_source": str(target.get("api_key_source", "") or ""),
            "base_url": "",
            "base_url_source": str(target.get("base_url_source", "") or ""),
            "endpoint": endpoint,
        }

    url = f"{base_url}{endpoint}"
    try:
        with httpx.Client(timeout=max(0.1, float(timeout))) as client:
            response = client.get(url, headers=headers)
        status_code = int(response.status_code)
        ok = bool(response.is_success)
        error = "" if ok else f"http_status:{status_code}"
    except Exception as exc:
        status_code = 0
        ok = False
        error = str(exc)

    return {
        "ok": ok,
        "provider": provider,
        "provider_detected": detected,
        "model": model,
        "status_code": status_code,
        "error": error,
        "api_key_masked": str(target.get("api_key_masked", "") or ""),
        "api_key_source": str(target.get("api_key_source", "") or ""),
        "base_url": base_url,
        "base_url_source": str(target.get("base_url_source", "") or ""),
        "endpoint": endpoint,
    }


def telegram_live_probe(config: AppConfig, *, timeout: float = 3.0) -> dict[str, Any]:
    token = str(config.channels.telegram.token or "").strip()
    if not token:
        return {
            "ok": False,
            "status_code": 0,
            "error": "telegram_token_missing",
            "token_masked": "",
            "endpoint": "",
        }

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with httpx.Client(timeout=max(0.1, float(timeout))) as client:
            response = client.get(url)
        body: Any
        try:
            body = response.json()
        except Exception:
            body = {}
        ok = bool(response.is_success and isinstance(body, dict) and bool(body.get("ok", False)))
        return {
            "ok": ok,
            "status_code": int(response.status_code),
            "error": "" if ok else "telegram_probe_failed",
            "token_masked": _mask_secret(token),
            "endpoint": "https://api.telegram.org/bot***/getMe",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "error": str(exc),
            "token_masked": _mask_secret(token),
            "endpoint": "https://api.telegram.org/bot***/getMe",
        }


def provider_use_model(
    config: AppConfig,
    *,
    config_path: str | Path | None,
    provider: str,
    model: str,
    fallback_model: str = "",
    clear_fallback: bool = False,
) -> dict[str, Any]:
    provider_norm = str(provider or "").strip().lower().replace("_", "-")
    model_norm = str(model or "").strip()
    fallback_norm = str(fallback_model or "").strip()

    if not provider_norm:
        return {
            "ok": False,
            "error": "provider_required",
        }

    if provider_norm not in SUPPORTED_PROVIDER_USE:
        return {
            "ok": False,
            "error": f"unsupported_provider:{provider_norm}",
            "supported": list(SUPPORTED_PROVIDER_USE),
        }

    if not model_norm:
        return {
            "ok": False,
            "error": "model_required",
            "provider": provider_norm,
        }

    if fallback_norm and clear_fallback:
        return {
            "ok": False,
            "error": "invalid_fallback_options",
            "detail": "Cannot combine --fallback-model with --clear-fallback.",
            "provider": provider_norm,
            "model": model_norm,
        }

    if provider_norm == "openai-codex":
        model_lower = model_norm.lower()
        if not (model_lower.startswith("openai-codex/") or model_lower.startswith("openai_codex/")):
            return {
                "ok": False,
                "error": "provider_model_mismatch",
                "provider": provider_norm,
                "model": model_norm,
                "expected": "openai-codex/*",
            }
    else:
        expected_provider = provider_norm.replace("-", "_")
        detected_provider = detect_provider_name(model_norm)
        if detected_provider != expected_provider:
            return {
                "ok": False,
                "error": "provider_model_mismatch",
                "provider": provider_norm,
                "model": model_norm,
                "detected_provider": detected_provider,
            }

    config.provider.model = model_norm
    config.agents.defaults.model = model_norm
    if fallback_norm:
        config.provider.fallback_model = fallback_norm
    elif clear_fallback:
        config.provider.fallback_model = ""

    saved_path = save_config(config, path=config_path)
    return {
        "ok": True,
        "saved_path": str(saved_path),
        "provider": provider_norm,
        "model": str(config.provider.model),
        "fallback_model": str(config.provider.fallback_model or ""),
    }


def provider_validation(config: AppConfig) -> dict[str, Any]:
    model = str(config.agents.defaults.model or config.provider.model).strip() or config.provider.model
    provider_name = detect_provider_name(model)
    spec = next((row for row in SPECS if row.name == provider_name), None)
    selected = getattr(config.providers, provider_name, None)

    provider_api_key = str(getattr(selected, "api_key", "") or "")
    provider_api_base = str(getattr(selected, "api_base", "") or "")
    resolved_api_key = provider_api_key or str(config.provider.litellm_api_key or "")
    resolved_base_url = provider_api_base or str(config.provider.litellm_base_url or "")

    env_hits: dict[str, bool] = {}
    env_names: list[str] = []
    if spec is not None:
        env_names.extend(list(spec.key_envs))
    env_names.extend(["CLAWLITE_LITELLM_API_KEY", "CLAWLITE_API_KEY"])
    seen: set[str] = set()
    for env_name in env_names:
        if env_name in seen:
            continue
        seen.add(env_name)
        env_hits[env_name] = bool(os.getenv(env_name, "").strip())

    checks: list[dict[str, str]] = []
    errors: list[str] = []
    warnings: list[str] = []

    oauth = bool(spec.is_oauth) if spec is not None else False
    checks.append({"name": "provider_detected", "status": "ok", "detail": provider_name})

    if oauth:
        codex_status = resolve_codex_auth(config)
        if provider_name == "openai_codex":
            if codex_status["configured"]:
                checks.append(
                    {
                        "name": "oauth_access_token",
                        "status": "ok",
                        "detail": f"Codex token configured ({codex_status['token_masked']}) from {codex_status['source'] or 'unknown'}.",
                    }
                )
            else:
                errors.append("Missing OAuth access token for provider 'openai_codex'.")
                checks.append(
                    {
                        "name": "oauth_access_token",
                        "status": "error",
                        "detail": "Run 'clawlite provider login openai-codex' or set CLAWLITE_CODEX_ACCESS_TOKEN.",
                    }
                )
            checks.append(
                {
                    "name": "oauth_account_id",
                    "status": "ok" if codex_status["account_id"] else "warning",
                    "detail": (
                        f"account_id={codex_status['account_id_masked']}"
                        if codex_status["account_id"]
                        else "account_id not configured (optional)."
                    ),
                }
            )
        else:
            checks.append(
                {
                    "name": "oauth_mode",
                    "status": "ok",
                    "detail": "OAuth provider selected.",
                }
            )
    else:
        has_key = bool(resolved_api_key) or any(env_hits.values())
        if has_key:
            checks.append(
                {
                    "name": "api_key",
                    "status": "ok",
                    "detail": "API key configured via config or environment.",
                }
            )
        else:
            errors.append(f"Missing API key for provider '{provider_name}'.")
            checks.append(
                {
                    "name": "api_key",
                    "status": "error",
                    "detail": "Set a provider key in config.providers or provider-specific environment variables.",
                }
            )

    if provider_name == "custom":
        if resolved_base_url:
            checks.append({"name": "base_url", "status": "ok", "detail": resolved_base_url})
        else:
            errors.append("Custom provider requires providers.custom.api_base.")
            checks.append(
                {
                    "name": "base_url",
                    "status": "error",
                    "detail": "Set providers.custom.api_base for custom/<model> routes.",
                }
            )
    else:
        if resolved_base_url:
            checks.append({"name": "base_url", "status": "ok", "detail": resolved_base_url})
        else:
            warnings.append("Provider base URL is empty; runtime may fail when provider requires explicit base URL.")
            checks.append(
                {
                    "name": "base_url",
                    "status": "warning",
                    "detail": "Base URL not configured; defaults depend on provider resolution.",
                }
            )

    return {
        "ok": not errors,
        "model": model,
        "provider": provider_name,
        "oauth": oauth,
        "api_key_masked": _mask_secret(resolved_api_key),
        "oauth_token_masked": resolve_codex_auth(config)["token_masked"] if provider_name == "openai_codex" else "",
        "oauth_source": resolve_codex_auth(config)["source"] if provider_name == "openai_codex" else "",
        "base_url": resolved_base_url,
        "env_key_present": env_hits,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }


def channels_validation(config: AppConfig) -> dict[str, Any]:
    channels = config.channels
    enabled_names = channels.enabled_names()

    issues: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []

    builtins: list[tuple[str, dict[str, Any], list[str], list[str]]] = [
        ("telegram", {"token": channels.telegram.token, "allow_from": channels.telegram.allow_from}, ["token"], ["allow_from"]),
        ("discord", {"token": channels.discord.token}, ["token"], []),
        ("slack", {"bot_token": channels.slack.bot_token, "app_token": channels.slack.app_token}, ["bot_token"], ["app_token"]),
        ("whatsapp", {"bridge_url": channels.whatsapp.bridge_url}, ["bridge_url"], []),
    ]

    for name, payload, required_fields, warning_fields in builtins:
        enabled = bool(getattr(channels, name).enabled)
        record = {
            "channel": name,
            "enabled": enabled,
            "status": "disabled",
            "missing": [],
            "warnings": [],
        }
        if enabled:
            missing = [field for field in required_fields if not str(payload.get(field, "") or "").strip()]
            warns = [field for field in warning_fields if not payload.get(field)]
            if missing:
                record["status"] = "error"
                record["missing"] = missing
                issues.append(
                    {
                        "severity": "error",
                        "channel": name,
                        "detail": f"Missing required field(s): {', '.join(missing)}",
                    }
                )
            elif warns:
                record["status"] = "warning"
                record["warnings"] = warns
                issues.append(
                    {
                        "severity": "warning",
                        "channel": name,
                        "detail": f"Recommended field(s) not configured: {', '.join(warns)}",
                    }
                )
            else:
                record["status"] = "ok"
        rows.append(record)

    for name, payload in sorted(channels.extra.items()):
        enabled = bool(payload.get("enabled", False))
        record = {
            "channel": name,
            "enabled": enabled,
            "status": "disabled",
            "missing": [],
            "warnings": [],
        }
        if enabled:
            record["status"] = "warning"
            record["warnings"] = ["custom_channel_validation_not_available"]
            issues.append(
                {
                    "severity": "warning",
                    "channel": name,
                    "detail": "Enabled custom channel has no static validation rules.",
                }
            )
        rows.append(record)

    if not enabled_names:
        issues.append(
            {
                "severity": "warning",
                "channel": "*",
                "detail": "No channels are enabled; outbound operator alerts cannot be delivered.",
            }
        )

    errors = [item for item in issues if item["severity"] == "error"]
    return {
        "ok": not errors,
        "enabled": enabled_names,
        "channels": rows,
        "issues": issues,
    }


def onboarding_validation(config: AppConfig, *, fix: bool = False) -> dict[str, Any]:
    workspace = Path(config.workspace_path).expanduser()
    existing = [name for name in TEMPLATE_FILES if (workspace / name).exists()]
    missing = [name for name in TEMPLATE_FILES if (workspace / name) not in [(workspace / row) for row in existing]]

    created: list[str] = []
    if fix and missing:
        from clawlite.workspace.loader import WorkspaceLoader

        loader = WorkspaceLoader(workspace_path=workspace)
        generated = loader.bootstrap(overwrite=False)
        created = [str(path.relative_to(workspace)) for path in generated if path.exists()]
        existing = [name for name in TEMPLATE_FILES if (workspace / name).exists()]
        missing = [name for name in TEMPLATE_FILES if (workspace / name) not in [(workspace / row) for row in existing]]

    return {
        "ok": not missing,
        "workspace": str(workspace),
        "existing": existing,
        "missing": missing,
        "created": created,
    }


def diagnostics_snapshot(config: AppConfig, *, config_path: str, include_validation: bool = True) -> dict[str, Any]:
    state_path = Path(config.state_path).expanduser()
    cron_store = state_path / "cron_jobs.json"
    heartbeat_state = Path(config.workspace_path).expanduser() / "memory" / "heartbeat-state.json"
    workspace_loader = WorkspaceLoader(workspace_path=config.workspace_path)
    payload: dict[str, Any] = {
        "config_path": config_path,
        "workspace_path": config.workspace_path,
        "state_path": config.state_path,
        "provider_model": config.agents.defaults.model,
        "memory_window": config.agents.defaults.memory_window,
        "session_retention_messages": config.agents.defaults.session_retention_messages,
        "agent_defaults": {
            "provider_model": config.agents.defaults.model,
            "memory_window": config.agents.defaults.memory_window,
            "session_retention_messages": config.agents.defaults.session_retention_messages,
        },
        "gateway": {
            "host": config.gateway.host,
            "port": config.gateway.port,
            "auth_mode": config.gateway.auth.mode,
            "diagnostics_enabled": config.gateway.diagnostics.enabled,
            "diagnostics_require_auth": config.gateway.diagnostics.require_auth,
        },
        "scheduler": {
            "heartbeat_interval_seconds": config.gateway.heartbeat.interval_s,
            "cron_store_exists": cron_store.exists(),
            "heartbeat_state_exists": heartbeat_state.exists(),
        },
        "bootstrap": workspace_loader.bootstrap_status(),
        "channels_enabled": config.channels.enabled_names(),
    }
    if include_validation:
        payload["validation"] = {
            "provider": provider_validation(config),
            "channels": channels_validation(config),
            "onboarding": onboarding_validation(config, fix=False),
        }
    return payload


def fetch_gateway_diagnostics(*, gateway_url: str, timeout: float = 3.0, token: str = "") -> dict[str, Any]:
    base = gateway_url.strip().rstrip("/")
    if not base:
        raise RuntimeError("gateway_url_required")

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    out: dict[str, Any] = {"base_url": base, "endpoints": {}}
    client_timeout = max(0.1, float(timeout))
    with httpx.Client(timeout=client_timeout, headers=headers) as client:
        for endpoint in ("/health", "/v1/status", "/v1/diagnostics"):
            url = f"{base}{endpoint}"
            try:
                response = client.get(url)
                parsed: Any
                try:
                    parsed = response.json()
                except Exception:
                    parsed = response.text
                out["endpoints"][endpoint] = {
                    "status_code": response.status_code,
                    "ok": response.is_success,
                    "body": parsed,
                }
            except Exception as exc:
                out["endpoints"][endpoint] = {
                    "status_code": 0,
                    "ok": False,
                    "error": str(exc),
                }
    return out


def memory_eval_snapshot(config: AppConfig, limit: int = 5) -> dict[str, Any]:
    del config
    top_k = max(1, int(limit or 1))
    corpus: list[dict[str, str]] = [
        {
            "id": "mem_tz_001",
            "text": "User timezone is America/Sao_Paulo and prefers morning updates.",
            "source": "seed:profile",
            "created_at": "2026-03-01T08:00:00+00:00",
        },
        {
            "id": "mem_deploy_001",
            "text": "Deployment schedule is Friday at 17:00 UTC for production.",
            "source": "seed:ops",
            "created_at": "2026-03-01T09:00:00+00:00",
        },
        {
            "id": "mem_stack_001",
            "text": "Project stack uses Python FastAPI pytest and uvicorn.",
            "source": "seed:project",
            "created_at": "2026-03-01T10:00:00+00:00",
        },
        {
            "id": "mem_food_001",
            "text": "Remember grocery list includes banana bread coffee and eggs.",
            "source": "seed:personal",
            "created_at": "2026-03-01T11:00:00+00:00",
        },
        {
            "id": "mem_lang_001",
            "text": "User prefers Portuguese answers for operational updates.",
            "source": "seed:profile",
            "created_at": "2026-03-01T12:00:00+00:00",
        },
    ]
    cases: list[dict[str, Any]] = [
        {
            "name": "timezone_preference",
            "query": "what is my timezone preference",
            "expected_ids": ["mem_tz_001"],
        },
        {
            "name": "deployment_schedule",
            "query": "when do we deploy on friday",
            "expected_ids": ["mem_deploy_001"],
        },
        {
            "name": "project_stack",
            "query": "what stack do we use for project",
            "expected_ids": ["mem_stack_001"],
        },
        {
            "name": "grocery_memory",
            "query": "remember grocery list",
            "expected_ids": ["mem_food_001"],
        },
        {
            "name": "language_preference",
            "query": "what language do i prefer",
            "expected_ids": ["mem_lang_001"],
        },
    ]

    with tempfile.TemporaryDirectory(prefix="clawlite-memory-eval-") as temp_dir:
        base = Path(temp_dir)
        history_path = base / "memory.jsonl"
        curated_path = base / "memory_curated.json"
        checkpoints_path = base / "memory_checkpoints.json"
        store = MemoryStore(
            db_path=history_path,
            curated_path=curated_path,
            checkpoints_path=checkpoints_path,
        )
        history_lines = [
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in corpus
        ]
        history_path.write_text("\n".join(history_lines) + "\n", encoding="utf-8")

        details: list[dict[str, Any]] = []
        passed = 0
        for case in cases:
            rows = store.search(str(case["query"]), limit=top_k)
            top_ids = [str(row.id) for row in rows[:top_k]]
            expected_ids = [str(item) for item in list(case["expected_ids"])]
            hit = bool(set(top_ids).intersection(expected_ids))
            if hit:
                passed += 1
            details.append(
                {
                    "name": str(case["name"]),
                    "query": str(case["query"]),
                    "expected_ids": expected_ids,
                    "top_ids": top_ids,
                    "hit": hit,
                }
            )

    total_cases = len(cases)
    failed = total_cases - passed
    return {
        "ok": failed == 0,
        "cases": total_cases,
        "passed": passed,
        "failed": failed,
        "details": details,
    }


def memory_quality_snapshot(
    config: AppConfig,
    gateway_url: str = "",
    token: str = "",
    timeout: float = 3.0,
    limit: int = 5,
) -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        eval_snapshot = memory_eval_snapshot(config, limit=max(1, int(limit or 1)))
        diagnostics = store.diagnostics()
        analysis = store.analysis_stats()

        eval_attempts = int(eval_snapshot.get("cases", 0) or 0)
        eval_hits = int(eval_snapshot.get("passed", 0) or 0)

        recovery_attempts = int(diagnostics.get("session_recovery_attempts", 0) or 0)
        recovery_hits = int(diagnostics.get("session_recovery_hits", 0) or 0)
        rewrites = int(diagnostics.get("consolidate_dedup_hits", 0) or 0)

        retrieval_metrics = {
            "attempts": max(0, eval_attempts + recovery_attempts),
            "hits": max(0, eval_hits + recovery_hits),
            "rewrites": max(0, rewrites),
        }

        error_keys = (
            "history_read_corrupt_lines",
            "privacy_audit_errors",
            "privacy_encrypt_errors",
            "privacy_decrypt_errors",
            "privacy_key_errors",
        )
        turn_errors = sum(int(diagnostics.get(key, 0) or 0) for key in error_keys)
        if str(diagnostics.get("last_error", "") or "").strip():
            turn_errors += 1
        turn_successes = max(0, int(diagnostics.get("consolidate_writes", 0) or 0) + recovery_hits)

        turn_stability_metrics = {
            "successes": turn_successes,
            "errors": turn_errors,
        }

        semantic = analysis.get("semantic", {}) if isinstance(analysis.get("semantic", {}), dict) else {}
        semantic_metrics = {
            "enabled": bool(semantic.get("enabled", False)),
            "coverage_ratio": float(semantic.get("coverage_ratio", 0.0) or 0.0),
        }

        gateway_block: dict[str, Any] = {"enabled": False}
        gateway_metrics: dict[str, Any] = {}
        if str(gateway_url or "").strip():
            gateway_block = {"enabled": True}
            try:
                gateway_snapshot = fetch_gateway_diagnostics(
                    gateway_url=str(gateway_url or ""),
                    token=str(token or ""),
                    timeout=float(timeout),
                )
                gateway_block["ok"] = True
                gateway_block["base_url"] = str(gateway_snapshot.get("base_url", "") or "")
                endpoints = gateway_snapshot.get("endpoints", {})
                if isinstance(endpoints, dict):
                    ok_count = sum(1 for value in endpoints.values() if isinstance(value, dict) and bool(value.get("ok", False)))
                    gateway_metrics = {
                        "endpoint_ok": ok_count,
                        "endpoint_total": len(endpoints),
                    }
            except Exception as exc:
                gateway_block["ok"] = False
                gateway_block["error"] = str(exc)

        report = store.update_quality_state(
            retrieval_metrics=retrieval_metrics,
            turn_stability_metrics=turn_stability_metrics,
            semantic_metrics=semantic_metrics,
            gateway_metrics=gateway_metrics,
        )
        state = store.quality_state_snapshot()

        return {
            "ok": True,
            "report": report,
            "state": state,
            "quality_state_path": str(store.quality_state_path),
            "eval": {
                "cases": eval_attempts,
                "passed": eval_hits,
                "failed": int(eval_snapshot.get("failed", 0) or 0),
            },
            "gateway_probe": gateway_block,
            "analysis": {
                "reasoning_layers": dict(analysis.get("reasoning_layers", {}))
                if isinstance(analysis.get("reasoning_layers"), dict)
                else {},
                "confidence": dict(analysis.get("confidence", {}))
                if isinstance(analysis.get("confidence"), dict)
                else {},
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def _file_stat(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "size_bytes": 0,
            "mtime": "",
        }
    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return {
        "exists": True,
        "size_bytes": int(stat.st_size),
        "mtime": mtime,
    }


def _schema_hints(path: Path, *, kind: str) -> dict[str, Any]:
    hints: dict[str, Any] = {
        "exists": path.exists(),
        "version": None,
        "keys_present": [],
    }
    if not path.exists():
        return hints
    try:
        payload = json.loads(path.read_text(encoding="utf-8").strip() or "{}")
    except Exception:
        hints["parse_error"] = True
        return hints

    if isinstance(payload, dict):
        keys = sorted(str(key) for key in payload.keys())
        hints["keys_present"] = keys
        raw_version = payload.get("version")
        if isinstance(raw_version, (int, float, str)):
            hints["version"] = raw_version
        if kind == "checkpoints":
            hints["shape"] = "v2" if any(
                key in payload for key in ("source_signatures", "source_activity", "global_signatures")
            ) else "legacy_or_custom"
    else:
        hints["parse_error"] = True
    return hints


def memory_doctor_snapshot(config: AppConfig, repair: bool = False) -> dict[str, Any]:
    state_path = Path(config.state_path).expanduser()
    history_path = state_path / "memory.jsonl"
    curated_path = state_path / "memory_curated.json"
    checkpoints_path = state_path / "memory_checkpoints.json"

    payload: dict[str, Any] = {
        "ok": True,
        "repair_applied": False,
        "paths": {
            "history": str(history_path),
            "curated": str(curated_path),
            "checkpoints": str(checkpoints_path),
        },
        "files": {
            "history": _file_stat(history_path),
            "curated": _file_stat(curated_path),
            "checkpoints": _file_stat(checkpoints_path),
        },
        "counts": {"history": 0, "curated": 0, "total": 0},
        "analysis": {
            "recent": {"last_24h": 0, "last_7d": 0, "last_30d": 0},
            "temporal_marked_count": 0,
            "top_sources": [],
        },
        "diagnostics": {},
        "schema": {
            "curated": _schema_hints(curated_path, kind="curated"),
            "checkpoints": _schema_hints(checkpoints_path, kind="checkpoints"),
        },
    }

    try:
        store = MemoryStore(
            db_path=history_path,
            curated_path=curated_path,
            checkpoints_path=checkpoints_path,
        )
        if repair:
            store.all()
            payload["repair_applied"] = True
        stats = store.analysis_stats()
        payload["counts"] = dict(stats.get("counts", {}))
        payload["analysis"] = {
            "recent": dict(stats.get("recent", {})),
            "temporal_marked_count": int(stats.get("temporal_marked_count", 0) or 0),
            "top_sources": list(stats.get("top_sources", [])),
        }
        reasoning_layers = stats.get("reasoning_layers")
        if isinstance(reasoning_layers, dict):
            payload["analysis"]["reasoning_layers"] = dict(reasoning_layers)
        confidence = stats.get("confidence")
        if isinstance(confidence, dict):
            payload["analysis"]["confidence"] = dict(confidence)
        payload["diagnostics"] = store.diagnostics()
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
    return payload


def memory_overview_snapshot(config: AppConfig) -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        history_count = len(store.all())
        curated_count = len(store.curated())
        total_count = history_count + curated_count
        embedding_rows = 0
        try:
            embedding_rows = len(store._read_embeddings_map())
        except Exception:
            embedding_rows = 0

        semantic_coverage = 0.0
        if total_count > 0:
            semantic_coverage = round(min(1.0, float(embedding_rows) / float(total_count)), 4)

        return {
            "ok": True,
            "counts": {
                "history": history_count,
                "curated": curated_count,
                "total": total_count,
            },
            "semantic_coverage": semantic_coverage,
            "proactive_enabled": bool(getattr(config.agents.defaults.memory, "proactive", False)),
            "paths": {
                "memory_home": str(store.memory_home),
                "history": str(store.history_path),
                "curated": str(store.curated_path) if store.curated_path is not None else "",
                "embeddings": str(store.embeddings_path),
                "versions": str(store.versions_path),
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_version_snapshot(config: AppConfig) -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        version_ids = sorted(
            [path.stem.replace(".json", "") for path in store.versions_path.glob("*.json.gz") if path.is_file()],
            reverse=True,
        )
        return {
            "ok": True,
            "count": len(version_ids),
            "versions": version_ids,
            "path": str(store.versions_path),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_branches_snapshot(config: AppConfig) -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        payload = store.branches()
        return {
            "ok": True,
            "current": str(payload.get("current", "main") or "main"),
            "branches": payload.get("branches", {}),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_branch_create(config: AppConfig, name: str, from_version: str = "", checkout: bool = False) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        return {"ok": False, "error": {"type": "ValueError", "message": "branch_name_required"}}
    try:
        store = _build_memory_store(config)
        payload = store.branch(clean_name, from_version=str(from_version or ""), checkout=bool(checkout))
        return {
            "ok": True,
            "name": str(payload.get("name", "") or clean_name),
            "head": str(payload.get("head", "") or ""),
            "current": str(payload.get("current", "main") or "main"),
            "checkout": bool(payload.get("checkout", False)),
        }
    except Exception as exc:
        return {
            "ok": False,
            "name": clean_name,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_branch_checkout(config: AppConfig, name: str) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        return {"ok": False, "error": {"type": "ValueError", "message": "branch_name_required"}}
    try:
        store = _build_memory_store(config)
        payload = store.checkout_branch(clean_name)
        return {
            "ok": True,
            "current": str(payload.get("current", "") or clean_name),
            "head": str(payload.get("head", "") or ""),
        }
    except Exception as exc:
        return {
            "ok": False,
            "current": clean_name,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_merge_branches(config: AppConfig, source: str, target: str, tag: str = "merge") -> dict[str, Any]:
    source_name = str(source or "").strip()
    target_name = str(target or "").strip()
    if not source_name or not target_name:
        return {"ok": False, "error": {"type": "ValueError", "message": "source_and_target_required"}}
    try:
        store = _build_memory_store(config)
        payload = store.merge(source_name, target_name, tag=str(tag or "merge"))
        return {
            "ok": True,
            "source": str(payload.get("source", source_name)),
            "target": str(payload.get("target", target_name)),
            "source_head": str(payload.get("source_head", "") or ""),
            "target_head_before": str(payload.get("target_head_before", "") or ""),
            "target_head_after": str(payload.get("target_head_after", "") or ""),
            "version": str(payload.get("version", "") or ""),
            "imported": bool(payload.get("imported", False)),
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": source_name,
            "target": target_name,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_shared_opt_in(config: AppConfig, user_id: str, enabled: bool) -> dict[str, Any]:
    clean_user = str(user_id or "").strip()
    if not clean_user:
        return {"ok": False, "error": {"type": "ValueError", "message": "user_id_required"}}
    try:
        store = _build_memory_store(config)
        payload = store.set_shared_opt_in(clean_user, bool(enabled))
        return {
            "ok": True,
            "user_id": str(payload.get("user_id", clean_user) or clean_user),
            "enabled": bool(payload.get("enabled", False)),
        }
    except Exception as exc:
        return {
            "ok": False,
            "user_id": clean_user,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def _build_memory_store(config: AppConfig) -> MemoryStore:
    semantic_enabled = bool(
        getattr(config.agents.defaults.memory, "semantic_search", config.agents.defaults.semantic_memory)
    )
    auto_categorize = bool(
        getattr(config.agents.defaults.memory, "auto_categorize", config.agents.defaults.memory_auto_categorize)
    )
    return MemoryStore(
        db_path=Path(config.state_path).expanduser() / "memory.jsonl",
        semantic_enabled=semantic_enabled,
        memory_auto_categorize=auto_categorize,
        memory_backend_name=str(config.agents.defaults.memory.backend or "sqlite"),
        memory_backend_url=str(config.agents.defaults.memory.pgvector_url or ""),
    )


def memory_profile_snapshot(config: AppConfig) -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        profile = store._load_json_dict(store.profile_path, store._default_profile())
        return {
            "ok": True,
            "profile": profile,
            "path": str(store.profile_path),
            "keys": sorted(profile.keys()),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_suggest_snapshot(config: AppConfig, refresh: bool = True) -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        monitor = MemoryMonitor(store)
        source = "pending"
        if refresh:
            try:
                suggestions = asyncio.run(monitor.scan())
                source = "scan"
            except Exception:
                suggestions = monitor.pending()
                source = "pending_fallback"
        else:
            suggestions = monitor.pending()
        rows = [item.to_payload() for item in suggestions]
        rows.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))))
        return {
            "ok": True,
            "refresh": bool(refresh),
            "source": source,
            "count": len(rows),
            "suggestions": rows,
            "pending_path": str(monitor.suggestions_path),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_snapshot_create(config: AppConfig, tag: str = "") -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        version_id = store.snapshot(tag=tag)
        version_path = store.versions_path / f"{version_id}.json.gz"
        return {
            "ok": True,
            "version_id": version_id,
            "tag": str(tag or ""),
            "version_path": str(version_path),
            "exists": version_path.exists(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_snapshot_rollback(config: AppConfig, version_id: str) -> dict[str, Any]:
    clean_id = str(version_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": {"type": "ValueError", "message": "version_id_required"}}
    try:
        store = _build_memory_store(config)
        before = len(store.all()) + len(store.curated())
        store.rollback(clean_id)
        after = len(store.all()) + len(store.curated())
        return {
            "ok": True,
            "version_id": clean_id,
            "counts": {"before": before, "after": after},
        }
    except Exception as exc:
        return {
            "ok": False,
            "version_id": clean_id,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_privacy_snapshot(config: AppConfig) -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        privacy = store._load_json_dict(store.privacy_path, store._default_privacy())
        return {
            "ok": True,
            "privacy": privacy,
            "path": str(store.privacy_path),
            "keys": sorted(privacy.keys()),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_export_snapshot(config: AppConfig, out_path: str = "") -> dict[str, Any]:
    try:
        store = _build_memory_store(config)
        payload = store.export_payload()
        output_path = str(out_path or "").strip()
        if output_path:
            target = Path(output_path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return {
                "ok": True,
                "out_path": str(target),
                "written": True,
                "version": payload.get("version"),
                "counts": {
                    "history": len(payload.get("history", [])),
                    "curated": len(payload.get("curated", [])),
                },
            }
        return {
            "ok": True,
            "written": False,
            "export": payload,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def memory_import_snapshot(config: AppConfig, file_path: str) -> dict[str, Any]:
    source_path = Path(str(file_path or "").strip()).expanduser()
    if not str(file_path or "").strip():
        return {"ok": False, "error": {"type": "ValueError", "message": "file_path_required"}}
    if not source_path.exists():
        return {
            "ok": False,
            "error": {"type": "FileNotFoundError", "message": str(source_path)},
        }
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        payload = raw if isinstance(raw, dict) else {}
        store = _build_memory_store(config)
        before = len(store.all()) + len(store.curated())
        store.import_payload(payload)
        after = len(store.all()) + len(store.curated())
        return {
            "ok": True,
            "file_path": str(source_path),
            "imported": True,
            "counts": {"before": before, "after": after},
        }
    except Exception as exc:
        return {
            "ok": False,
            "file_path": str(source_path),
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }
