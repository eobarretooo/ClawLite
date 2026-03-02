from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from clawlite.providers.base import LLMProvider
from clawlite.providers.codex import CodexProvider
from clawlite.providers.custom import CustomProvider
from clawlite.providers.litellm import LiteLLMProvider

OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass(slots=True, frozen=True)
class ProviderSpec:
    name: str
    aliases: tuple[str, ...]
    keywords: tuple[str, ...]
    model_prefixes: tuple[str, ...]
    key_envs: tuple[str, ...]
    default_base_url: str
    key_prefixes: tuple[str, ...] = ()
    base_url_keywords: tuple[str, ...] = ()
    openai_compatible: bool = True
    is_gateway: bool = False
    is_oauth: bool = False
    strip_model_prefix: bool = False


@dataclass(slots=True, frozen=True)
class ProviderResolution:
    name: str
    model: str
    api_key: str
    base_url: str
    openai_compatible: bool
    is_gateway: bool
    is_oauth: bool


SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="custom",
        aliases=(),
        keywords=(),
        model_prefixes=("custom/",),
        key_envs=(),
        default_base_url="",
        openai_compatible=True,
    ),
    ProviderSpec(
        name="openrouter",
        aliases=(),
        keywords=("openrouter",),
        model_prefixes=("openrouter/",),
        key_envs=("OPENROUTER_API_KEY",),
        default_base_url="https://openrouter.ai/api/v1",
        key_prefixes=("sk-or-",),
        base_url_keywords=("openrouter",),
        is_gateway=True,
    ),
    ProviderSpec(
        name="gemini",
        aliases=("google",),
        keywords=("gemini",),
        model_prefixes=("gemini/", "google/"),
        key_envs=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        key_prefixes=("AIza",),
        base_url_keywords=("generativelanguage.googleapis.com",),
    ),
    ProviderSpec(
        name="groq",
        aliases=(),
        keywords=("groq",),
        model_prefixes=("groq/",),
        key_envs=("GROQ_API_KEY",),
        default_base_url="https://api.groq.com/openai/v1",
        key_prefixes=("gsk_",),
        base_url_keywords=("api.groq.com",),
    ),
    ProviderSpec(
        name="deepseek",
        aliases=(),
        keywords=("deepseek",),
        model_prefixes=("deepseek/",),
        key_envs=("DEEPSEEK_API_KEY",),
        default_base_url="https://api.deepseek.com/v1",
        base_url_keywords=("deepseek",),
    ),
    ProviderSpec(
        name="anthropic",
        aliases=("claude",),
        keywords=("anthropic", "claude"),
        model_prefixes=("anthropic/", "claude/"),
        key_envs=("ANTHROPIC_API_KEY",),
        default_base_url="https://api.anthropic.com/v1",
        base_url_keywords=("anthropic",),
        openai_compatible=False,
    ),
    ProviderSpec(
        name="openai",
        aliases=(),
        keywords=("openai", "gpt", "o1", "o3", "o4", "codex"),
        model_prefixes=("openai/",),
        key_envs=("OPENAI_API_KEY",),
        default_base_url=OPENAI_DEFAULT_BASE_URL,
        key_prefixes=("sk-",),
        base_url_keywords=("api.openai.com",),
    ),
    ProviderSpec(
        name="openai_codex",
        aliases=("openai-codex", "codex"),
        keywords=("openai-codex",),
        model_prefixes=("openai-codex/", "openai_codex/"),
        key_envs=(),
        default_base_url=OPENAI_DEFAULT_BASE_URL,
        openai_compatible=True,
        is_oauth=True,
    ),
)


def _normalize(name: str) -> str:
    return (name or "").strip().lower().replace("-", "_")


def _spec_names(spec: ProviderSpec) -> set[str]:
    return {_normalize(spec.name), *(_normalize(alias) for alias in spec.aliases)}


def _find_spec(name: str) -> ProviderSpec | None:
    wanted = _normalize(name)
    for spec in SPECS:
        if wanted in _spec_names(spec):
            return spec
    return None


def _cfg_value(payload: dict[str, Any], snake: str, camel: str) -> str:
    return str(payload.get(snake, payload.get(camel, "")) or "").strip()


def _provider_cfg(raw: dict[str, Any], name: str) -> dict[str, Any]:
    names = [name, _normalize(name), name.replace("_", "-")]
    if spec := _find_spec(name):
        names.extend(list(spec.aliases))
    for key in names:
        payload = raw.get(key)
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def _spec_from_model(model: str) -> ProviderSpec | None:
    model_lower = (model or "").strip().lower()
    if not model_lower:
        return None

    model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
    model_prefix_norm = _normalize(model_prefix)

    standard_specs = [spec for spec in SPECS if not spec.is_gateway]
    for spec in standard_specs:
        if model_prefix_norm and model_prefix_norm in _spec_names(spec):
            return spec
        if any(model_lower.startswith(prefix) for prefix in spec.model_prefixes):
            return spec

    model_norm = _normalize(model_lower)
    for spec in standard_specs:
        if any(keyword in model_lower or _normalize(keyword) in model_norm for keyword in spec.keywords):
            return spec
    return None


def _spec_from_api_key(api_key: str) -> ProviderSpec | None:
    value = (api_key or "").strip()
    if not value:
        return None
    for spec in SPECS:
        if any(value.startswith(prefix) for prefix in spec.key_prefixes):
            return spec
    return None


def _spec_from_base_url(base_url: str) -> ProviderSpec | None:
    value = (base_url or "").strip().lower()
    if not value:
        return None
    for spec in SPECS:
        if any(keyword in value for keyword in spec.base_url_keywords):
            return spec
    return None


def _find_gateway(
    provider_name: str = "",
    api_key: str = "",
    base_url: str = "",
) -> ProviderSpec | None:
    if provider_name:
        spec = _find_spec(provider_name)
        if spec is not None and spec.is_gateway:
            return spec

    key_spec = _spec_from_api_key(api_key)
    if key_spec is not None and key_spec.is_gateway:
        return key_spec

    base_spec = _spec_from_base_url(base_url)
    if base_spec is not None and base_spec.is_gateway:
        return base_spec

    return None


def _is_compatible_key_for_spec(value: str, spec: ProviderSpec) -> bool:
    token = (value or "").strip()
    if not token:
        return False
    if spec.is_oauth:
        return True
    if not spec.key_prefixes:
        return True
    if any(token.startswith(prefix) for prefix in spec.key_prefixes):
        return True
    guessed = _spec_from_api_key(token)
    if guessed is not None and guessed.name != spec.name:
        return False
    return True


def _resolve_api_key(spec: ProviderSpec, configured_api_key: str) -> str:
    direct = (configured_api_key or "").strip()
    if direct and _is_compatible_key_for_spec(direct, spec):
        return direct

    for env_name in spec.key_envs:
        value = os.getenv(env_name, "").strip()
        if value and _is_compatible_key_for_spec(value, spec):
            return value

    for env_name in ("CLAWLITE_LITELLM_API_KEY", "CLAWLITE_API_KEY"):
        value = os.getenv(env_name, "").strip()
        if value and _is_compatible_key_for_spec(value, spec):
            return value
    return ""


def _resolve_base_url(spec: ProviderSpec, configured_base_url: str) -> str:
    candidate = (configured_base_url or "").strip().rstrip("/")
    if not candidate:
        return spec.default_base_url
    if candidate == OPENAI_DEFAULT_BASE_URL and spec.name != "openai" and spec.default_base_url:
        return spec.default_base_url
    return candidate


def _normalize_model_for_provider(model: str, provider: ProviderSpec) -> str:
    normalized = (model or "").strip()
    if not normalized:
        return normalized

    if provider.strip_model_prefix and "/" in normalized:
        normalized = normalized.split("/", 1)[1]

    if "/" not in normalized:
        return normalized

    prefix, remainder = normalized.split("/", 1)
    if _normalize(prefix) in _spec_names(provider):
        return remainder
    return normalized


def detect_provider_name(
    model: str,
    *,
    api_key: str = "",
    base_url: str = "",
    provider_name: str = "",
) -> str:
    model_prefix = (model or "").strip().lower().split("/", 1)[0] if "/" in (model or "") else ""
    if model_prefix:
        model_prefix_spec = _find_spec(model_prefix)
        if model_prefix_spec is not None and model_prefix_spec.is_gateway:
            return model_prefix_spec.name

    gateway_spec = _find_gateway(provider_name=provider_name, api_key=api_key, base_url=base_url)
    if gateway_spec is not None:
        return gateway_spec.name

    if provider_name:
        explicit = _find_spec(provider_name)
        if explicit is not None:
            return explicit.name

    model_spec = _spec_from_model(model)
    if model_spec is not None:
        return model_spec.name

    key_spec = _spec_from_api_key(api_key)
    if key_spec is not None:
        return key_spec.name

    base_spec = _spec_from_base_url(base_url)
    if base_spec is not None:
        return base_spec.name

    return "openai"


def resolve_litellm_provider(
    model: str,
    *,
    api_key: str,
    base_url: str,
    provider_name: str = "",
) -> ProviderResolution:
    name = detect_provider_name(model, api_key=api_key, base_url=base_url, provider_name=provider_name)
    spec = _find_spec(name) or _find_spec("openai")
    assert spec is not None

    resolved_api_key = _resolve_api_key(spec, api_key)
    resolved_base_url = _resolve_base_url(spec, base_url)
    resolved_model = _normalize_model_for_provider(model, spec)

    return ProviderResolution(
        name=spec.name,
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        openai_compatible=spec.openai_compatible,
        is_gateway=spec.is_gateway,
        is_oauth=spec.is_oauth,
    )


def _resolve_codex_oauth(config: dict[str, Any]) -> tuple[str, str]:
    auth = dict(config.get("auth") or {})
    auth_providers = auth.get("providers")
    auth_provider_map = dict(auth_providers) if isinstance(auth_providers, dict) else {}

    codex_payload: dict[str, Any] = {}
    for key in ("openai-codex", "openai_codex", "codex", "openaiCodex"):
        candidate = auth_provider_map.get(key)
        if isinstance(candidate, dict):
            codex_payload = dict(candidate)
            break

    token = (
        _cfg_value(codex_payload, "token", "token")
        or _cfg_value(codex_payload, "access_token", "accessToken")
        or os.getenv("CLAWLITE_CODEX_ACCESS_TOKEN", "").strip()
        or os.getenv("OPENAI_CODEX_ACCESS_TOKEN", "").strip()
        or os.getenv("OPENAI_ACCESS_TOKEN", "").strip()
    )
    account_id = (
        _cfg_value(codex_payload, "account_id", "accountId")
        or _cfg_value(codex_payload, "org_id", "orgId")
        or _cfg_value(codex_payload, "organization", "organization")
        or os.getenv("CLAWLITE_CODEX_ACCOUNT_ID", "").strip()
        or os.getenv("OPENAI_ORG_ID", "").strip()
    )
    return token, account_id


def build_provider(config: dict[str, Any]) -> LLMProvider:
    model = str(config.get("model", "gemini/gemini-2.5-flash") or "gemini/gemini-2.5-flash").strip()
    model_lower = model.lower()
    providers_cfg = dict(config.get("providers") or {})
    litellm_cfg = _provider_cfg(providers_cfg, "litellm")

    if model_lower.startswith(("openai-codex/", "openai_codex/")):
        model_name = model.split("/", 1)[1] if "/" in model else model
        token, account_id = _resolve_codex_oauth(config)
        if token:
            return CodexProvider(model=model_name, access_token=token, account_id=account_id)

        openai_cfg = _provider_cfg(providers_cfg, "openai")
        resolved = resolve_litellm_provider(
            model=f"openai/{model_name}",
            api_key=_cfg_value(openai_cfg, "api_key", "apiKey") or _cfg_value(litellm_cfg, "api_key", "apiKey"),
            base_url=_cfg_value(openai_cfg, "api_base", "apiBase") or _cfg_value(litellm_cfg, "base_url", "baseUrl"),
            provider_name="openai",
        )
        return LiteLLMProvider(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            model=resolved.model,
            provider_name=resolved.name,
            openai_compatible=resolved.openai_compatible,
            extra_headers={},
        )

    if model_lower.startswith("custom/"):
        custom_cfg = _provider_cfg(providers_cfg, "custom")
        extra_headers_raw = custom_cfg.get("extra_headers", custom_cfg.get("extraHeaders", {}))
        extra_headers = dict(extra_headers_raw) if isinstance(extra_headers_raw, dict) else {}
        return CustomProvider(
            base_url=_cfg_value(custom_cfg, "api_base", "apiBase")
            or _cfg_value(custom_cfg, "base_url", "baseUrl")
            or "http://127.0.0.1:4000/v1",
            api_key=_cfg_value(custom_cfg, "api_key", "apiKey") or "",
            model=str(custom_cfg.get("model", model.split("/", 1)[-1])),
            extra_headers=extra_headers,
        )

    predicted_name = detect_provider_name(model, api_key="", base_url="")
    selected_cfg = _provider_cfg(providers_cfg, predicted_name)
    selected_api_key = _cfg_value(selected_cfg, "api_key", "apiKey")
    selected_api_base = _cfg_value(selected_cfg, "api_base", "apiBase")
    resolved = resolve_litellm_provider(
        model=model,
        api_key=selected_api_key or _cfg_value(litellm_cfg, "api_key", "apiKey"),
        base_url=selected_api_base or _cfg_value(litellm_cfg, "base_url", "baseUrl"),
        provider_name=predicted_name,
    )

    extra_headers_raw = selected_cfg.get("extra_headers", selected_cfg.get("extraHeaders", {}))
    extra_headers = dict(extra_headers_raw) if isinstance(extra_headers_raw, dict) else {}

    return LiteLLMProvider(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        model=resolved.model,
        provider_name=resolved.name,
        openai_compatible=resolved.openai_compatible,
        extra_headers=extra_headers,
    )
