from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from clawlite.providers.base import LLMProvider
from clawlite.providers.codex import CODEX_DEFAULT_BASE_URL, CodexProvider
from clawlite.providers.codex_auth import load_codex_auth_file
from clawlite.providers.custom import CustomProvider
from clawlite.providers.discovery import detect_local_runtime, normalize_local_runtime_base_url
from clawlite.providers.failover import FailoverCandidate, FailoverProvider
from clawlite.providers.gemini_auth import load_gemini_auth_file
from clawlite.providers.litellm import LiteLLMProvider
from clawlite.providers.qwen_auth import load_qwen_auth_file

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
    native_transport: str = ""
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
    native_transport: str
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
        name="kilocode",
        aliases=("kilo",),
        keywords=("kilocode",),
        model_prefixes=("kilocode/", "kilo/"),
        key_envs=("KILOCODE_API_KEY",),
        default_base_url="https://api.kilo.ai/api/gateway/",
        base_url_keywords=("api.kilo.ai", "kilo.ai"),
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
        name="together",
        aliases=(),
        keywords=("together",),
        model_prefixes=("together/",),
        key_envs=("TOGETHER_API_KEY",),
        default_base_url="https://api.together.xyz/v1",
        base_url_keywords=("api.together.xyz", "together.ai", "together.xyz"),
    ),
    ProviderSpec(
        name="huggingface",
        aliases=("hf",),
        keywords=("huggingface",),
        model_prefixes=("huggingface/", "hf/"),
        key_envs=("HUGGINGFACE_HUB_TOKEN", "HF_TOKEN"),
        default_base_url="https://router.huggingface.co/v1",
        base_url_keywords=("huggingface.co", "router.huggingface.co"),
    ),
    ProviderSpec(
        name="xai",
        aliases=(),
        keywords=("xai", "grok"),
        model_prefixes=("xai/",),
        key_envs=("XAI_API_KEY",),
        default_base_url="https://api.x.ai/v1",
        base_url_keywords=("api.x.ai",),
    ),
    ProviderSpec(
        name="mistral",
        aliases=(),
        keywords=("mistral",),
        model_prefixes=("mistral/",),
        key_envs=("MISTRAL_API_KEY",),
        default_base_url="https://api.mistral.ai/v1",
        base_url_keywords=("api.mistral.ai", "mistral.ai"),
    ),
    ProviderSpec(
        name="moonshot",
        aliases=("kimi",),
        keywords=("moonshot",),
        model_prefixes=("moonshot/", "kimi/"),
        key_envs=("MOONSHOT_API_KEY",),
        default_base_url="https://api.moonshot.ai/v1",
        base_url_keywords=("api.moonshot.ai", "api.moonshot.cn", "moonshot.ai"),
    ),
    ProviderSpec(
        name="qianfan",
        aliases=(),
        keywords=("qianfan",),
        model_prefixes=("qianfan/",),
        key_envs=("QIANFAN_API_KEY",),
        default_base_url="https://qianfan.baidubce.com/v2",
        base_url_keywords=("qianfan.baidubce.com", "qianfan"),
    ),
    ProviderSpec(
        name="zai",
        aliases=("zhipu",),
        keywords=("zai", "zhipu", "glm"),
        model_prefixes=("zai/", "zhipu/"),
        key_envs=("ZAI_API_KEY", "Z_AI_API_KEY", "ZHIPUAI_API_KEY"),
        default_base_url="https://api.z.ai/api/paas/v4",
        base_url_keywords=("api.z.ai", "open.bigmodel.cn", "bigmodel", "z.ai"),
    ),
    ProviderSpec(
        name="nvidia",
        aliases=(),
        keywords=("nvidia",),
        model_prefixes=("nvidia/",),
        key_envs=("NVIDIA_API_KEY", "NGC_API_KEY"),
        default_base_url="https://integrate.api.nvidia.com/v1",
        base_url_keywords=("integrate.api.nvidia.com", "nvidia.com"),
    ),
    ProviderSpec(
        name="byteplus",
        aliases=(),
        keywords=("byteplus",),
        model_prefixes=("byteplus/",),
        key_envs=("BYTEPLUS_API_KEY",),
        default_base_url="https://ark.ap-southeast.bytepluses.com/api/v3",
        base_url_keywords=("bytepluses.com", "byteplus"),
    ),
    ProviderSpec(
        name="doubao",
        aliases=(),
        keywords=("doubao",),
        model_prefixes=("doubao/",),
        key_envs=("VOLCANO_ENGINE_API_KEY", "VOLCENGINE_API_KEY"),
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        base_url_keywords=("volces.com", "doubao"),
    ),
    ProviderSpec(
        name="volcengine",
        aliases=(),
        keywords=("volcengine",),
        model_prefixes=("volcengine/",),
        key_envs=("VOLCANO_ENGINE_API_KEY", "VOLCENGINE_API_KEY"),
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        base_url_keywords=("volces.com", "volcengine"),
    ),
    ProviderSpec(
        name="minimax",
        aliases=(),
        keywords=("minimax",),
        model_prefixes=("minimax/",),
        key_envs=("MINIMAX_API_KEY",),
        default_base_url="https://api.minimax.io/anthropic",
        base_url_keywords=("api.minimax.io/anthropic", "api.minimaxi.com/anthropic", "minimax.io/anthropic"),
        openai_compatible=False,
        native_transport="anthropic",
    ),
    ProviderSpec(
        name="xiaomi",
        aliases=(),
        keywords=("xiaomi", "mimo"),
        model_prefixes=("xiaomi/",),
        key_envs=("XIAOMI_API_KEY",),
        default_base_url="https://api.xiaomimimo.com/anthropic",
        base_url_keywords=("api.xiaomimimo.com/anthropic", "xiaomimimo.com/anthropic"),
        openai_compatible=False,
        native_transport="anthropic",
    ),
    ProviderSpec(
        name="kimi_coding",
        aliases=("kimi-coding",),
        keywords=("kimi-coding",),
        model_prefixes=("kimi_coding/", "kimi-coding/"),
        key_envs=("KIMI_API_KEY", "KIMICODE_API_KEY"),
        default_base_url="https://api.kimi.com/coding/",
        base_url_keywords=("api.kimi.com/coding", "kimi.com/coding"),
        openai_compatible=False,
        native_transport="anthropic",
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
        native_transport="anthropic",
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
        default_base_url=CODEX_DEFAULT_BASE_URL,
        openai_compatible=True,
        is_oauth=True,
    ),
    ProviderSpec(
        name="gemini_oauth",
        aliases=("gemini-oauth",),
        keywords=("gemini-oauth",),
        model_prefixes=("gemini-oauth/", "gemini_oauth/"),
        key_envs=(),
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        openai_compatible=True,
        is_oauth=True,
    ),
    ProviderSpec(
        name="qwen_oauth",
        aliases=("qwen-oauth",),
        keywords=("qwen-oauth",),
        model_prefixes=("qwen-oauth/", "qwen_oauth/"),
        key_envs=(),
        default_base_url="https://api.qwen.ai/v1",
        openai_compatible=True,
        is_oauth=True,
    ),
    ProviderSpec(
        name="ollama",
        aliases=(),
        keywords=("ollama",),
        model_prefixes=("ollama/",),
        key_envs=(),
        default_base_url="http://127.0.0.1:11434/v1",
        base_url_keywords=("ollama",),
    ),
    ProviderSpec(
        name="vllm",
        aliases=(),
        keywords=("vllm",),
        model_prefixes=("vllm/",),
        key_envs=(),
        default_base_url="http://127.0.0.1:8000/v1",
        base_url_keywords=("vllm",),
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
        return spec.default_base_url.rstrip("/")
    if candidate == OPENAI_DEFAULT_BASE_URL and spec.name != "openai" and spec.default_base_url:
        return spec.default_base_url.rstrip("/")
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

    local_runtime = detect_local_runtime(base_url)
    if local_runtime:
        local_spec = _find_spec(local_runtime)
        if local_spec is not None:
            return local_spec.name

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


def _configured_provider_hint(providers_cfg: dict[str, Any], *, model: str) -> str:
    explicit_prefix = (model or "").strip().lower().split("/", 1)[0] if "/" in (model or "") else ""
    if explicit_prefix:
        explicit_spec = _find_spec(explicit_prefix)
        if explicit_spec is not None:
            return ""

    candidates: list[str] = []
    for spec in SPECS:
        cfg = _provider_cfg(providers_cfg, spec.name)
        api_key = _cfg_value(cfg, "api_key", "apiKey")
        api_base = _cfg_value(cfg, "api_base", "apiBase") or _cfg_value(cfg, "base_url", "baseUrl")
        if str(api_key or "").strip() or str(api_base or "").strip():
            candidates.append(spec.name)
    if len(candidates) == 1:
        return candidates[0]
    return ""


def resolve_litellm_provider(
    model: str,
    *,
    api_key: str,
    base_url: str,
    provider_name: str = "",
) -> ProviderResolution:
    name = detect_provider_name(model, api_key=api_key, base_url=base_url, provider_name=provider_name)
    spec = _find_spec(name) or _find_spec("openai")
    if spec is None:
        raise RuntimeError("provider_registry_error:missing_default_spec:openai")

    resolved_api_key = _resolve_api_key(spec, api_key)
    resolved_base_url = _resolve_base_url(spec, base_url)
    resolved_model = _normalize_model_for_provider(model, spec)

    return ProviderResolution(
        name=spec.name,
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        openai_compatible=spec.openai_compatible,
        native_transport=spec.native_transport,
        is_gateway=spec.is_gateway,
        is_oauth=spec.is_oauth,
    )


def _resolve_codex_oauth(config: dict[str, Any]) -> tuple[str, str]:
    auth = dict(config.get("auth") or {})
    auth_providers = auth.get("providers")
    auth_provider_map = dict(auth_providers) if isinstance(auth_providers, dict) else {}
    auth_file = load_codex_auth_file()

    codex_payload: dict[str, Any] = {}
    for key in ("openai-codex", "openai_codex", "codex", "openaiCodex"):
        candidate = auth_provider_map.get(key)
        if isinstance(candidate, dict):
            codex_payload = dict(candidate)
            break

    token = (
        _cfg_value(codex_payload, "access_token", "accessToken")
        or _cfg_value(codex_payload, "token", "token")
        or os.getenv("CLAWLITE_CODEX_ACCESS_TOKEN", "").strip()
        or os.getenv("OPENAI_CODEX_ACCESS_TOKEN", "").strip()
        or os.getenv("OPENAI_ACCESS_TOKEN", "").strip()
        or str(auth_file.get("access_token", "") or "").strip()
    )
    account_id = (
        _cfg_value(codex_payload, "account_id", "accountId")
        or _cfg_value(codex_payload, "org_id", "orgId")
        or _cfg_value(codex_payload, "organization", "organization")
        or os.getenv("CLAWLITE_CODEX_ACCOUNT_ID", "").strip()
        or os.getenv("OPENAI_ORG_ID", "").strip()
        or str(auth_file.get("account_id", "") or "").strip()
    )
    return token, account_id


def _resolve_generic_oauth(
    config: dict[str, Any],
    *,
    provider_names: tuple[str, ...],
    token_envs: tuple[str, ...],
    account_envs: tuple[str, ...],
    file_loader,
) -> tuple[str, str]:
    auth = dict(config.get("auth") or {})
    auth_providers = auth.get("providers")
    auth_provider_map = dict(auth_providers) if isinstance(auth_providers, dict) else {}
    auth_file = file_loader()

    payload: dict[str, Any] = {}
    for key in provider_names:
        candidate = auth_provider_map.get(key)
        if isinstance(candidate, dict):
            payload = dict(candidate)
            break

    token = (
        _cfg_value(payload, "access_token", "accessToken")
        or _cfg_value(payload, "token", "token")
        or next((os.getenv(env_name, "").strip() for env_name in token_envs if os.getenv(env_name, "").strip()), "")
        or str(auth_file.get("access_token", "") or "").strip()
    )
    account_id = (
        _cfg_value(payload, "account_id", "accountId")
        or _cfg_value(payload, "org_id", "orgId")
        or _cfg_value(payload, "organization", "organization")
        or next((os.getenv(env_name, "").strip() for env_name in account_envs if os.getenv(env_name, "").strip()), "")
        or str(auth_file.get("account_id", "") or "").strip()
    )
    return token, account_id


def _resolve_gemini_oauth(config: dict[str, Any]) -> tuple[str, str]:
    return _resolve_generic_oauth(
        config,
        provider_names=("gemini_oauth", "gemini-oauth", "geminiOAuth", "gemini"),
        token_envs=("CLAWLITE_GEMINI_ACCESS_TOKEN", "GEMINI_ACCESS_TOKEN"),
        account_envs=("CLAWLITE_GEMINI_ACCOUNT_ID", "GEMINI_ACCOUNT_ID"),
        file_loader=load_gemini_auth_file,
    )


def _resolve_qwen_oauth(config: dict[str, Any]) -> tuple[str, str]:
    return _resolve_generic_oauth(
        config,
        provider_names=("qwen_oauth", "qwen-oauth", "qwenOAuth", "qwen"),
        token_envs=("CLAWLITE_QWEN_ACCESS_TOKEN", "QWEN_ACCESS_TOKEN"),
        account_envs=("CLAWLITE_QWEN_ACCOUNT_ID", "QWEN_ACCOUNT_ID"),
        file_loader=load_qwen_auth_file,
    )


def _reliability_settings(config: dict[str, Any]) -> dict[str, Any]:
    retry_max_attempts = max(1, int(config.get("retry_max_attempts", config.get("retryMaxAttempts", 3)) or 3))
    retry_initial_backoff_s = max(
        0.0,
        float(config.get("retry_initial_backoff_s", config.get("retryInitialBackoffS", 0.5)) or 0.5),
    )
    retry_max_backoff_s = max(
        retry_initial_backoff_s,
        float(config.get("retry_max_backoff_s", config.get("retryMaxBackoffS", 8.0)) or 8.0),
    )
    retry_jitter_s = max(0.0, float(config.get("retry_jitter_s", config.get("retryJitterS", 0.2)) or 0.2))
    circuit_failure_threshold = max(
        1,
        int(config.get("circuit_failure_threshold", config.get("circuitFailureThreshold", 3)) or 3),
    )
    circuit_cooldown_s = max(0.0, float(config.get("circuit_cooldown_s", config.get("circuitCooldownS", 30.0)) or 30.0))
    return {
        "retry_max_attempts": retry_max_attempts,
        "retry_initial_backoff_s": retry_initial_backoff_s,
        "retry_max_backoff_s": retry_max_backoff_s,
        "retry_jitter_s": retry_jitter_s,
        "circuit_failure_threshold": circuit_failure_threshold,
        "circuit_cooldown_s": circuit_cooldown_s,
    }


def _fallback_models(config: dict[str, Any]) -> list[str]:
    primary_model = str(config.get("model", "") or "").strip()
    rows: list[str] = []
    seen: set[str] = set()

    def _add(value: Any) -> None:
        model_name = str(value or "").strip()
        if not model_name or model_name == primary_model or model_name in seen:
            return
        seen.add(model_name)
        rows.append(model_name)

    _add(config.get("fallback_model", config.get("fallbackModel", "")))

    raw_list = config.get("fallback_models", config.get("fallbackModels", config.get("fallbacks", [])))
    if isinstance(raw_list, str):
        for item in raw_list.split(","):
            _add(item)
    elif isinstance(raw_list, list):
        for item in raw_list:
            _add(item)

    return rows


def _build_provider_single(config: dict[str, Any]) -> LLMProvider:
    model = str(config.get("model", "gemini/gemini-2.5-flash") or "gemini/gemini-2.5-flash").strip()
    model_lower = model.lower()
    providers_cfg = dict(config.get("providers") or {})
    litellm_cfg = _provider_cfg(providers_cfg, "litellm")
    litellm_api_key = _cfg_value(litellm_cfg, "api_key", "apiKey")
    litellm_base_url = _cfg_value(litellm_cfg, "base_url", "baseUrl")
    reliability = _reliability_settings(config)

    if model_lower.startswith(("openai-codex/", "openai_codex/")):
        model_name = model.split("/", 1)[1] if "/" in model else model
        token, account_id = _resolve_codex_oauth(config)
        codex_cfg = _provider_cfg(providers_cfg, "openai_codex")
        codex_base_url = (
            _cfg_value(codex_cfg, "api_base", "apiBase")
            or _cfg_value(codex_cfg, "base_url", "baseUrl")
            or os.getenv("CLAWLITE_CODEX_BASE_URL", "").strip()
            or CODEX_DEFAULT_BASE_URL
        )
        return CodexProvider(
            model=model_name,
            access_token=token,
            account_id=account_id,
            base_url=codex_base_url,
            **reliability,
        )

    if model_lower.startswith(("gemini-oauth/", "gemini_oauth/")):
        model_name = model.split("/", 1)[1] if "/" in model else model
        token, _account_id = _resolve_gemini_oauth(config)
        gemini_cfg = _provider_cfg(providers_cfg, "gemini_oauth")
        gemini_base_url = (
            _cfg_value(gemini_cfg, "api_base", "apiBase")
            or _cfg_value(gemini_cfg, "base_url", "baseUrl")
            or "https://generativelanguage.googleapis.com/v1beta/openai"
        )
        return LiteLLMProvider(
            base_url=gemini_base_url,
            api_key=token,
            model=model_name,
            provider_name="gemini_oauth",
            allow_empty_api_key=False,
            **reliability,
        )

    if model_lower.startswith(("qwen-oauth/", "qwen_oauth/")):
        model_name = model.split("/", 1)[1] if "/" in model else model
        token, _account_id = _resolve_qwen_oauth(config)
        qwen_cfg = _provider_cfg(providers_cfg, "qwen_oauth")
        qwen_base_url = (
            _cfg_value(qwen_cfg, "api_base", "apiBase")
            or _cfg_value(qwen_cfg, "base_url", "baseUrl")
            or "https://api.qwen.ai/v1"
        )
        return LiteLLMProvider(
            base_url=qwen_base_url,
            api_key=token,
            model=model_name,
            provider_name="qwen_oauth",
            allow_empty_api_key=False,
            **reliability,
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
            **reliability,
        )

    provider_hint = _configured_provider_hint(providers_cfg, model=model)
    predicted_name = detect_provider_name(model, api_key=litellm_api_key, base_url=litellm_base_url, provider_name=provider_hint)
    selected_name = provider_hint or predicted_name
    selected_cfg = _provider_cfg(providers_cfg, selected_name)
    selected_api_key = _cfg_value(selected_cfg, "api_key", "apiKey")
    selected_api_base = _cfg_value(selected_cfg, "api_base", "apiBase")
    resolved = resolve_litellm_provider(
        model=model,
        api_key=selected_api_key or _cfg_value(litellm_cfg, "api_key", "apiKey"),
        base_url=selected_api_base or _cfg_value(litellm_cfg, "base_url", "baseUrl"),
        provider_name=selected_name,
    )

    extra_headers_raw = selected_cfg.get("extra_headers", selected_cfg.get("extraHeaders", {}))
    extra_headers = dict(extra_headers_raw) if isinstance(extra_headers_raw, dict) else {}
    runtime_base_url = resolved.base_url
    if resolved.name in {"ollama", "vllm"}:
        runtime_base_url = normalize_local_runtime_base_url(resolved.name, resolved.base_url)

    return LiteLLMProvider(
        base_url=runtime_base_url,
        api_key=resolved.api_key,
        model=resolved.model,
        provider_name=resolved.name,
        openai_compatible=resolved.openai_compatible,
        native_transport=resolved.native_transport,
        allow_empty_api_key=resolved.name in {"ollama", "vllm"},
        extra_headers=extra_headers,
        **reliability,
    )


def build_provider(config: dict[str, Any]) -> LLMProvider:
    primary = _build_provider_single(config)
    fallback_models = _fallback_models(config)
    if not fallback_models:
        return primary

    candidates = [FailoverCandidate(provider=primary, model=primary.get_default_model())]
    for fallback_model in fallback_models:
        fallback_config = dict(config)
        fallback_config["model"] = fallback_model
        fallback_config["fallback_model"] = ""
        fallback_config["fallback_models"] = []
        fallback_config["fallbackModels"] = []
        fallback_config["fallbacks"] = []
        fallback = _build_provider_single(fallback_config)
        candidates.append(FailoverCandidate(provider=fallback, model=fallback_model))
    return FailoverProvider(candidates=candidates, fallback_model=fallback_models[0])
