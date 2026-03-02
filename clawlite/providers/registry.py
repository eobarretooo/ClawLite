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
    model_prefixes: tuple[str, ...]
    key_envs: tuple[str, ...]
    default_base_url: str
    key_prefixes: tuple[str, ...] = ()
    base_url_keywords: tuple[str, ...] = ()
    openai_compatible: bool = True


@dataclass(slots=True, frozen=True)
class ProviderResolution:
    name: str
    model: str
    api_key: str
    base_url: str
    openai_compatible: bool


SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="openrouter",
        model_prefixes=("openrouter/",),
        key_envs=("OPENROUTER_API_KEY",),
        default_base_url="https://openrouter.ai/api/v1",
        key_prefixes=("sk-or-",),
        base_url_keywords=("openrouter.ai",),
    ),
    ProviderSpec(
        name="gemini",
        model_prefixes=("gemini/",),
        key_envs=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        key_prefixes=("AIza",),
        base_url_keywords=("generativelanguage.googleapis.com",),
    ),
    ProviderSpec(
        name="groq",
        model_prefixes=("groq/",),
        key_envs=("GROQ_API_KEY",),
        default_base_url="https://api.groq.com/openai/v1",
        key_prefixes=("gsk_",),
        base_url_keywords=("api.groq.com",),
    ),
    ProviderSpec(
        name="deepseek",
        model_prefixes=("deepseek/",),
        key_envs=("DEEPSEEK_API_KEY",),
        default_base_url="https://api.deepseek.com/v1",
        base_url_keywords=("api.deepseek.com",),
    ),
    ProviderSpec(
        name="anthropic",
        model_prefixes=("anthropic/",),
        key_envs=("ANTHROPIC_API_KEY",),
        default_base_url="",
        base_url_keywords=("api.anthropic.com",),
        openai_compatible=False,
    ),
    ProviderSpec(
        name="openai",
        model_prefixes=("openai/",),
        key_envs=("OPENAI_API_KEY",),
        default_base_url=OPENAI_DEFAULT_BASE_URL,
        key_prefixes=("sk-",),
        base_url_keywords=("api.openai.com",),
    ),
)


def _normalize(name: str) -> str:
    return (name or "").strip().lower().replace("-", "_")


def _find_spec(name: str) -> ProviderSpec | None:
    wanted = _normalize(name)
    for spec in SPECS:
        if spec.name == wanted:
            return spec
    return None


def _spec_from_model(model: str) -> ProviderSpec | None:
    model_lower = (model or "").strip().lower()
    for spec in SPECS:
        if any(model_lower.startswith(prefix) for prefix in spec.model_prefixes):
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


def _resolve_api_key(spec: ProviderSpec, configured_api_key: str) -> str:
    direct = (configured_api_key or "").strip()
    if direct:
        return direct

    for env_name in ("CLAWLITE_LITELLM_API_KEY", "CLAWLITE_API_KEY", *spec.key_envs):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return ""


def _resolve_base_url(spec: ProviderSpec, configured_base_url: str) -> str:
    candidate = (configured_base_url or "").strip().rstrip("/")
    if not candidate:
        return spec.default_base_url

    # Treat OpenAI base as implicit default; switch to provider-specific endpoint when possible.
    if candidate == OPENAI_DEFAULT_BASE_URL and spec.name != "openai" and spec.default_base_url:
        return spec.default_base_url
    return candidate


def _normalize_model_for_provider(model: str, provider: ProviderSpec) -> str:
    raw = (model or "").strip()
    if "/" not in raw:
        return raw

    prefix, remainder = raw.split("/", 1)
    if _normalize(prefix) == provider.name:
        return remainder

    # If provider was selected by key/base_url (for example OpenRouter), keep model untouched.
    return raw


def detect_provider_name(model: str, *, api_key: str = "", base_url: str = "") -> str:
    model_spec = _spec_from_model(model)
    key_spec = _spec_from_api_key(api_key)
    base_spec = _spec_from_base_url(base_url)

    # If model points to a non OpenAI-compatible provider and key/base selects a gateway,
    # prefer the gateway to avoid hard failures.
    if model_spec and not model_spec.openai_compatible:
        if key_spec and key_spec.openai_compatible:
            return key_spec.name
        if base_spec and base_spec.openai_compatible:
            return base_spec.name

    if model_spec:
        return model_spec.name
    if key_spec:
        return key_spec.name
    if base_spec:
        return base_spec.name
    return "openai"


def resolve_litellm_provider(model: str, *, api_key: str, base_url: str) -> ProviderResolution:
    name = detect_provider_name(model, api_key=api_key, base_url=base_url)
    spec = _find_spec(name) or _find_spec("openai")
    assert spec is not None  # for type-checkers

    resolved_api_key = _resolve_api_key(spec, api_key)
    resolved_base_url = _resolve_base_url(spec, base_url)
    resolved_model = _normalize_model_for_provider(model, spec)

    return ProviderResolution(
        name=spec.name,
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        openai_compatible=spec.openai_compatible,
    )


def build_provider(config: dict[str, Any]) -> LLMProvider:
    model = str(config.get("model", "gemini/gemini-2.5-flash")).strip()
    model_lower = model.lower()

    if model_lower.startswith(("openai-codex/", "openai_codex/")):
        auth = config.get("auth", {}).get("providers", {}).get("openai-codex", {})
        token = str(auth.get("token", "")).strip() or os.getenv("CLAWLITE_CODEX_ACCESS_TOKEN", "").strip()
        account_id = str(auth.get("account_id", "")).strip() or os.getenv("CLAWLITE_CODEX_ACCOUNT_ID", "").strip()
        model_name = model.split("/", 1)[1] if "/" in model else model
        return CodexProvider(model=model_name, access_token=token, account_id=account_id)

    if model_lower.startswith("custom/"):
        custom_cfg = config.get("providers", {}).get("custom", {})
        return CustomProvider(
            base_url=str(custom_cfg.get("base_url", "http://127.0.0.1:4000/v1")),
            api_key=str(custom_cfg.get("api_key", "")),
            model=str(custom_cfg.get("model", model.split("/", 1)[-1])),
        )

    litellm_cfg = config.get("providers", {}).get("litellm", {})
    resolved = resolve_litellm_provider(
        model=model,
        api_key=str(litellm_cfg.get("api_key", "")),
        base_url=str(litellm_cfg.get("base_url", "")),
    )
    return LiteLLMProvider(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        model=resolved.model,
        provider_name=resolved.name,
        openai_compatible=resolved.openai_compatible,
    )
