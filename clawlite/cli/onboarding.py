from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.prompt import Prompt

from clawlite.config.loader import save_config
from clawlite.config.schema import AppConfig
from clawlite.workspace.loader import WorkspaceLoader

SUPPORTED_PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "groq", "ollama")

DEFAULT_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "anthropic": "https://api.anthropic.com",
    "ollama": "http://127.0.0.1:11434",
}

DEFAULT_PROVIDER_MODELS: dict[str, str] = {
    "openai": "openai/gpt-4o-mini",
    "groq": "groq/llama-3.1-8b-instant",
    "anthropic": "anthropic/claude-3-5-haiku-latest",
    "ollama": "openai/llama3.2",
}


def _mask_secret(value: str, *, keep: int = 4) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if len(token) <= keep:
        return "*" * len(token)
    return f"{'*' * max(3, len(token) - keep)}{token[-keep:]}"


def _join_base(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    suffix = str(path or "").strip()
    if not suffix.startswith("/"):
        suffix = f"/{suffix}"
    return f"{base}{suffix}"


def ensure_gateway_token(config: AppConfig) -> str:
    current = str(config.gateway.auth.token or "").strip()
    if current:
        return current
    generated = uuid.uuid4().hex
    config.gateway.auth.token = generated
    return generated


def apply_provider_selection(
    config: AppConfig,
    *,
    provider: str,
    api_key: str,
    base_url: str,
    model: str = "",
) -> dict[str, Any]:
    provider_key = str(provider or "").strip().lower()
    if provider_key not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported_provider:{provider_key}")

    selected_model = str(model or "").strip() or DEFAULT_PROVIDER_MODELS[provider_key]
    selected_base_url = str(base_url or "").strip() or DEFAULT_PROVIDER_BASE_URLS[provider_key]
    selected_api_key = str(api_key or "").strip()

    config.provider.model = selected_model
    config.agents.defaults.model = selected_model
    config.provider.litellm_base_url = selected_base_url
    config.provider.litellm_api_key = selected_api_key

    if provider_key == "openai":
        config.providers.openai.api_key = selected_api_key
        config.providers.openai.api_base = selected_base_url
    elif provider_key == "groq":
        config.providers.groq.api_key = selected_api_key
        config.providers.groq.api_base = selected_base_url
    elif provider_key == "anthropic":
        config.providers.anthropic.api_key = selected_api_key
        config.providers.anthropic.api_base = selected_base_url

    return {
        "provider": provider_key,
        "model": selected_model,
        "base_url": selected_base_url,
        "api_key_masked": _mask_secret(selected_api_key),
    }


def probe_provider(provider: str, *, api_key: str, base_url: str, timeout_s: float = 8.0) -> dict[str, Any]:
    provider_key = str(provider or "").strip().lower()
    key = str(api_key or "").strip()
    resolved_base = str(base_url or "").strip() or DEFAULT_PROVIDER_BASE_URLS.get(provider_key, "")

    if provider_key in {"openai", "groq"}:
        url = _join_base(resolved_base, "/models")
        headers = {"Authorization": f"Bearer {key}"}
    elif provider_key == "anthropic":
        url = _join_base(resolved_base, "/v1/models")
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    elif provider_key == "ollama":
        url = _join_base(resolved_base, "/api/tags")
        headers = {}
    else:
        return {
            "ok": False,
            "provider": provider_key,
            "error": f"unsupported_provider:{provider_key}",
            "api_key_masked": _mask_secret(key),
            "base_url": resolved_base,
        }

    try:
        with httpx.Client(timeout=max(0.5, float(timeout_s))) as client:
            response = client.get(url, headers=headers)
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text
        return {
            "ok": bool(response.is_success),
            "provider": provider_key,
            "status_code": int(response.status_code),
            "url": url,
            "base_url": resolved_base,
            "api_key_masked": _mask_secret(key),
            "error": "" if response.is_success else f"http_status:{response.status_code}",
            "body": body if response.is_success else "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider_key,
            "status_code": 0,
            "url": url,
            "base_url": resolved_base,
            "api_key_masked": _mask_secret(key),
            "error": str(exc),
            "body": "",
        }


def probe_telegram(token: str, *, timeout_s: float = 8.0) -> dict[str, Any]:
    clean = str(token or "").strip()
    url = f"https://api.telegram.org/bot{clean}/getMe" if clean else ""
    if not clean:
        return {
            "ok": False,
            "status_code": 0,
            "url": "",
            "token_masked": "",
            "error": "telegram_token_missing",
            "body": "",
        }
    try:
        with httpx.Client(timeout=max(0.5, float(timeout_s))) as client:
            response = client.get(url)
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text
        ok = bool(response.is_success) and bool(isinstance(body, dict) and body.get("ok", False))
        return {
            "ok": ok,
            "status_code": int(response.status_code),
            "url": url,
            "token_masked": _mask_secret(clean),
            "error": "" if ok else "telegram_probe_failed",
            "body": body if ok else "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "url": url,
            "token_masked": _mask_secret(clean),
            "error": str(exc),
            "body": "",
        }


def run_onboarding_wizard(
    config: AppConfig,
    *,
    config_path: str | Path | None,
    overwrite: bool = False,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    console = Console(stderr=True, soft_wrap=True)
    payload: dict[str, Any] = {
        "ok": False,
        "mode": "wizard",
        "steps": [],
    }

    try:
        console.print(Panel("ClawLite Onboarding Wizard", title="clawlite onboard --wizard"))

        step_1_mode = Prompt.ask("Step 1/5 - mode", choices=["quickstart", "advanced"], default="quickstart")
        payload["steps"].append({"step": 1, "name": "mode", "choice": step_1_mode})

        if step_1_mode == "advanced":
            host = Prompt.ask("Gateway host", default=str(config.gateway.host or "127.0.0.1").strip())
            port_raw = Prompt.ask("Gateway port", default=str(int(config.gateway.port or 8787)))
            auth_mode = Prompt.ask(
                "Gateway auth mode",
                choices=["off", "optional", "required"],
                default=str(config.gateway.auth.mode or "off").strip().lower() or "off",
            )
            try:
                port = int(port_raw)
            except Exception:
                port = 8787
            config.gateway.host = host.strip() or "127.0.0.1"
            config.gateway.port = max(1, port)
            config.gateway.auth.mode = auth_mode
        else:
            config.gateway.host = str(config.gateway.host or "127.0.0.1").strip() or "127.0.0.1"
            config.gateway.port = max(1, int(config.gateway.port or 8787))
            if str(config.gateway.auth.mode or "").strip().lower() not in {"off", "optional", "required"}:
                config.gateway.auth.mode = "off"

        provider = Prompt.ask("Step 2/5 - provider", choices=list(SUPPORTED_PROVIDERS), default="openai")
        provider_default_base = DEFAULT_PROVIDER_BASE_URLS[provider]
        current_base = str(config.provider.litellm_base_url or "").strip()
        base_default = current_base or provider_default_base
        base_url = base_default
        if step_1_mode == "advanced":
            base_url = Prompt.ask(f"{provider} base URL", default=base_default)
        api_key = ""
        if provider != "ollama":
            api_key = Prompt.ask(f"{provider} API key", password=True)
        provider_probe = probe_provider(provider, api_key=api_key, base_url=base_url)
        payload["steps"].append(
            {
                "step": 2,
                "name": "provider",
                "provider": provider,
                "probe_ok": bool(provider_probe.get("ok", False)),
                "base_url": str(provider_probe.get("base_url", "") or ""),
                "api_key_masked": str(provider_probe.get("api_key_masked", "") or ""),
                "probe_error": str(provider_probe.get("error", "") or ""),
            }
        )
        if (not bool(provider_probe.get("ok", False))) and (not Confirm.ask("Provider probe failed. Continue?", default=False)):
            return {
                "ok": False,
                "mode": "wizard",
                "error": "provider_probe_failed",
                "steps": payload["steps"],
            }

        provider_persisted = apply_provider_selection(
            config,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
        )

        telegram_enabled = Confirm.ask("Step 3/5 - enable Telegram channel?", default=False)
        telegram_probe: dict[str, Any] = {
            "ok": True,
            "status_code": 0,
            "token_masked": "",
            "error": "",
        }
        if telegram_enabled:
            telegram_token = Prompt.ask("Telegram bot token", password=True)
            telegram_probe = probe_telegram(telegram_token)
            if (not bool(telegram_probe.get("ok", False))) and (not Confirm.ask("Telegram probe failed. Continue?", default=False)):
                return {
                    "ok": False,
                    "mode": "wizard",
                    "error": "telegram_probe_failed",
                    "steps": payload["steps"],
                }
            config.channels.telegram.enabled = True
            config.channels.telegram.token = str(telegram_token or "").strip()
        payload["steps"].append(
            {
                "step": 3,
                "name": "telegram",
                "enabled": telegram_enabled,
                "probe_ok": bool(telegram_probe.get("ok", False)),
                "token_masked": str(telegram_probe.get("token_masked", "") or ""),
                "probe_error": str(telegram_probe.get("error", "") or ""),
            }
        )

        generated_token = ensure_gateway_token(config)

        loader = WorkspaceLoader(workspace_path=config.workspace_path)
        generated_files = loader.bootstrap(overwrite=bool(overwrite), variables=variables or {})
        payload["steps"].append(
            {
                "step": 4,
                "name": "workspace",
                "workspace": str(config.workspace_path),
                "created_files": [str(path) for path in generated_files],
            }
        )

        saved_path = save_config(config, path=config_path)
        gateway_url = f"http://{config.gateway.host}:{config.gateway.port}"
        payload["steps"].append({"step": 5, "name": "final", "gateway_url": gateway_url})

        console.print(
            Panel(
                f"Gateway URL: {gateway_url}\nGateway token: {generated_token}",
                title="Onboarding complete",
            )
        )

        return {
            "ok": True,
            "mode": "wizard",
            "saved_path": str(saved_path),
            "persisted": {
                "provider": provider_persisted,
                "gateway": {
                    "host": str(config.gateway.host),
                    "port": int(config.gateway.port),
                    "auth_mode": str(config.gateway.auth.mode),
                    "token_masked": _mask_secret(generated_token),
                },
                "telegram": {
                    "enabled": bool(config.channels.telegram.enabled),
                    "token_masked": _mask_secret(config.channels.telegram.token),
                },
            },
            "workspace": {
                "path": str(config.workspace_path),
                "created_files": [str(path) for path in generated_files],
            },
            "probes": {
                "provider": {
                    "ok": bool(provider_probe.get("ok", False)),
                    "status_code": int(provider_probe.get("status_code", 0) or 0),
                    "error": str(provider_probe.get("error", "") or ""),
                    "api_key_masked": str(provider_probe.get("api_key_masked", "") or ""),
                },
                "telegram": {
                    "ok": bool(telegram_probe.get("ok", False)),
                    "status_code": int(telegram_probe.get("status_code", 0) or 0),
                    "error": str(telegram_probe.get("error", "") or ""),
                    "token_masked": str(telegram_probe.get("token_masked", "") or ""),
                },
            },
            "final": {
                "gateway_url": gateway_url,
                "gateway_token": generated_token,
            },
            "steps": payload["steps"],
        }
    except KeyboardInterrupt:
        return {
            "ok": False,
            "mode": "wizard",
            "error": "cancelled",
            "steps": payload["steps"],
        }
