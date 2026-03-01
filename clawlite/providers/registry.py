from __future__ import annotations

from dataclasses import dataclass

from clawlite.auth import auth_status
from clawlite.config.settings import load_config, save_config
from clawlite.core.providers import PROVIDER_SPECS, get_provider_spec, normalize_provider, resolve_provider_token
from clawlite.runtime.offline import provider_from_model


@dataclass(frozen=True)
class ProviderStatus:
    key: str
    display: str
    default_model: str
    api_style: str
    auth_url: str
    token_available: bool
    configured_in_auth: bool
    env_vars: tuple[str, ...]


def _build_status(provider_key: str) -> ProviderStatus:
    key = normalize_provider(provider_key)
    spec = get_provider_spec(key)
    if spec is None:
        raise ValueError(f"provider desconhecido: {provider_key}")

    auth_map = {row["provider"]: bool(row["logged_in"]) for row in auth_status()}
    token_available = bool(resolve_provider_token(key))
    return ProviderStatus(
        key=key,
        display=spec.display,
        default_model=spec.default_model,
        api_style=spec.api_style,
        auth_url=spec.auth_url,
        token_available=token_available or bool(auth_map.get(key, False)),
        configured_in_auth=bool(auth_map.get(key, False)),
        env_vars=tuple(spec.env_vars),
    )


def list_provider_statuses() -> list[ProviderStatus]:
    return [_build_status(key) for key in sorted(PROVIDER_SPECS.keys())]


def current_provider_status() -> tuple[str, str]:
    cfg = load_config()
    model = str(cfg.get("model", "openai/gpt-4o-mini")).strip() or "openai/gpt-4o-mini"
    provider = provider_from_model(model)
    return provider, model


def _resolve_model_for_provider(provider: str, model: str | None = None) -> str:
    key = normalize_provider(provider)
    spec = get_provider_spec(key)
    if spec is None:
        raise ValueError(f"provider não suportado: {provider}")

    custom_model = str(model or "").strip()
    if custom_model:
        return custom_model if "/" in custom_model else f"{key}/{custom_model}"

    default_model = str(spec.default_model).strip()
    if not default_model:
        raise ValueError(f"provider '{key}' sem modelo padrão")
    if "/" in default_model:
        return default_model
    return f"{key}/{default_model}"


def set_active_provider(provider: str, model: str | None = None) -> str:
    resolved = _resolve_model_for_provider(provider, model)
    cfg = load_config()
    cfg["model"] = resolved
    save_config(cfg)
    return resolved

