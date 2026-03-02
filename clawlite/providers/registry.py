from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clawlite.providers.base import LLMProvider
from clawlite.providers.codex import CodexProvider
from clawlite.providers.custom import CustomProvider
from clawlite.providers.litellm import LiteLLMProvider


@dataclass(slots=True)
class ProviderSpec:
    name: str
    model_prefixes: tuple[str, ...]


SPECS = (
    ProviderSpec(name="codex", model_prefixes=("openai-codex/", "openai_codex/")),
    ProviderSpec(name="litellm", model_prefixes=("openai/", "anthropic/", "gemini/", "openrouter/", "groq/")),
    ProviderSpec(name="custom", model_prefixes=("custom/",)),
)


def detect_provider_name(model: str) -> str:
    raw = (model or "").strip().lower()
    for spec in SPECS:
        if any(raw.startswith(prefix) for prefix in spec.model_prefixes):
            return spec.name
    return "litellm"


def build_provider(config: dict[str, Any]) -> LLMProvider:
    model = str(config.get("model", "openai/gpt-4o-mini")).strip()
    provider_name = detect_provider_name(model)

    if provider_name == "codex":
        auth = config.get("auth", {}).get("providers", {}).get("openai-codex", {})
        token = str(auth.get("token", "")).strip()
        account_id = str(auth.get("account_id", "")).strip()
        model_name = model.split("/", 1)[1] if "/" in model else model
        return CodexProvider(model=model_name, access_token=token, account_id=account_id)

    if provider_name == "custom":
        custom_cfg = config.get("providers", {}).get("custom", {})
        return CustomProvider(
            base_url=str(custom_cfg.get("base_url", "http://127.0.0.1:4000/v1")),
            api_key=str(custom_cfg.get("api_key", "")),
            model=str(custom_cfg.get("model", model.split("/", 1)[-1])),
        )

    litellm_cfg = config.get("providers", {}).get("litellm", {})
    return LiteLLMProvider(
        base_url=str(litellm_cfg.get("base_url", "https://api.openai.com/v1")),
        api_key=str(litellm_cfg.get("api_key", "")),
        model=model.split("/", 1)[1] if "/" in model else model,
    )
