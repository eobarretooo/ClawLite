from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ProviderProfile:
    family: str
    recommended_models: tuple[str, ...]
    onboarding_hint: str


ONBOARDING_PROVIDER_ORDER: tuple[str, ...] = (
    "openai",
    "azure-openai",
    "anthropic",
    "gemini",
    "groq",
    "deepseek",
    "openrouter",
    "aihubmix",
    "siliconflow",
    "cerebras",
    "xai",
    "mistral",
    "moonshot",
    "zai",
    "qianfan",
    "huggingface",
    "together",
    "kilocode",
    "minimax",
    "xiaomi",
    "kimi-coding",
    "ollama",
    "vllm",
)


PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "custom": ProviderProfile(
        family="custom",
        recommended_models=(),
        onboarding_hint="Custom provider; review the model, auth, and base URL manually before use.",
    ),
    "openrouter": ProviderProfile(
        family="gateway",
        recommended_models=("openrouter/auto", "openrouter/openai/gpt-4o-mini"),
        onboarding_hint="Multi-model Gateway; 'auto' mode does not require an exact match in the remote list.",
    ),
    "kilocode": ProviderProfile(
        family="gateway",
        recommended_models=("kilocode/anthropic/claude-opus-4.6",),
        onboarding_hint="Multi-model Gateway; confirm the upstream provider embedded in the model name.",
    ),
    "gemini": ProviderProfile(
        family="openai_compatible",
        recommended_models=("gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"),
        onboarding_hint="Gemini uses an OpenAI-compatible endpoint via Google Generative Language.",
    ),
    "groq": ProviderProfile(
        family="openai_compatible",
        recommended_models=("groq/llama-3.1-8b-instant", "groq/llama-3.3-70b-versatile"),
        onboarding_hint="Groq responds via OpenAI-compatible endpoints; prefer low-latency models when possible.",
    ),
    "deepseek": ProviderProfile(
        family="openai_compatible",
        recommended_models=("deepseek/deepseek-chat", "deepseek/deepseek-reasoner"),
        onboarding_hint="DeepSeek responds via OpenAI-compatible endpoints; validate quota and billing before rollout.",
    ),
    "together": ProviderProfile(
        family="gateway",
        recommended_models=("together/moonshotai/Kimi-K2.5", "together/meta-llama/Llama-3.3-70B-Instruct-Turbo"),
        onboarding_hint="Together behaves like an OpenAI-compatible gateway; confirm the full upstream model name.",
    ),
    "huggingface": ProviderProfile(
        family="gateway",
        recommended_models=("huggingface/deepseek-ai/DeepSeek-R1", "huggingface/meta-llama/Llama-3.3-70B-Instruct"),
        onboarding_hint="The Hugging Face router exposes full upstream models; confirm the repo/model id.",
    ),
    "xai": ProviderProfile(
        family="openai_compatible",
        recommended_models=("xai/grok-4", "xai/grok-4-fast-reasoning"),
        onboarding_hint="xAI responds via OpenAI-compatible endpoints; confirm access to the chosen Grok model.",
    ),
    "mistral": ProviderProfile(
        family="openai_compatible",
        recommended_models=("mistral/mistral-large-latest", "mistral/codestral-latest"),
        onboarding_hint="Mistral responds via OpenAI-compatible endpoints; prefer 'latest' aliases to avoid fixed-version drift.",
    ),
    "moonshot": ProviderProfile(
        family="openai_compatible",
        recommended_models=("moonshot/kimi-k2.5",),
        onboarding_hint="Moonshot/Kimi responds via OpenAI-compatible endpoints; confirm regional endpoint availability.",
    ),
    "qianfan": ProviderProfile(
        family="openai_compatible",
        recommended_models=("qianfan/deepseek-v3.2", "qianfan/ernie-4.0-turbo"),
        onboarding_hint="Qianfan uses its own OpenAI-compatible endpoint; verify credentials and the Baidu Cloud region.",
    ),
    "zai": ProviderProfile(
        family="openai_compatible",
        recommended_models=("zai/glm-5", "zai/glm-4.6"),
        onboarding_hint="Z.AI/GLM responds via a compatible endpoint; confirm that your account is enabled for the GLM model.",
    ),
    "nvidia": ProviderProfile(
        family="openai_compatible",
        recommended_models=("nvidia/meta/llama-3.1-70b-instruct",),
        onboarding_hint="NVIDIA NIM responds via OpenAI-compatible endpoints; the catalog may vary by tenant or project.",
    ),
    "byteplus": ProviderProfile(
        family="openai_compatible",
        recommended_models=("byteplus/deepseek-v3.1",),
        onboarding_hint="BytePlus Ark responds via OpenAI-compatible endpoints; confirm the project and regional endpoint.",
    ),
    "doubao": ProviderProfile(
        family="openai_compatible",
        recommended_models=("doubao/doubao-seed-1-6",),
        onboarding_hint="Doubao Ark responds via OpenAI-compatible endpoints; confirm that the tenant has access to the chosen model.",
    ),
    "volcengine": ProviderProfile(
        family="openai_compatible",
        recommended_models=("volcengine/doubao-seed-1-6",),
        onboarding_hint="Volcengine Ark responds via OpenAI-compatible endpoints; validate region and project before use.",
    ),
    "minimax": ProviderProfile(
        family="anthropic_compatible",
        recommended_models=("minimax/MiniMax-M2.5",),
        onboarding_hint="MiniMax uses Anthropic-compatible transport; the base URL usually ends with /anthropic.",
    ),
    "xiaomi": ProviderProfile(
        family="anthropic_compatible",
        recommended_models=("xiaomi/mimo-v2-flash",),
        onboarding_hint="Xiaomi Mimo uses Anthropic-compatible transport; confirm a base URL ending with /anthropic.",
    ),
    "kimi_coding": ProviderProfile(
        family="anthropic_compatible",
        recommended_models=("kimi-coding/k2p5",),
        onboarding_hint="Kimi Coding uses Anthropic-compatible transport and a dedicated /coding/ base URL.",
    ),
    "anthropic": ProviderProfile(
        family="anthropic_compatible",
        recommended_models=("anthropic/claude-3-5-haiku-latest", "anthropic/claude-3-7-sonnet-latest"),
        onboarding_hint="Anthropic uses the native /v1/messages transport; confirm the ANTHROPIC_API_KEY value.",
    ),
    "openai": ProviderProfile(
        family="openai_compatible",
        recommended_models=("openai/gpt-4o-mini", "openai/gpt-4.1-mini"),
        onboarding_hint="OpenAI responds via the standard OpenAI-compatible endpoint; validate billing and the active project.",
    ),
    "azure_openai": ProviderProfile(
        family="openai_compatible",
        recommended_models=("azure-openai/gpt-4.1-mini", "azure-openai/gpt-4o-mini"),
        onboarding_hint=(
            "Azure OpenAI now accepts resource-scoped OpenAI v1 base URLs; use your own "
            "`https://<resource>.openai.azure.com/openai/v1` or "
            "`https://<resource>.services.ai.azure.com/openai/v1` endpoint."
        ),
    ),
    "aihubmix": ProviderProfile(
        family="gateway",
        recommended_models=("aihubmix/openai/gpt-4.1-mini", "aihubmix/anthropic/claude-3-5-sonnet"),
        onboarding_hint="AiHubMix exposes an OpenAI-compatible multi-model gateway; confirm the upstream model name you want to route.",
    ),
    "siliconflow": ProviderProfile(
        family="gateway",
        recommended_models=("siliconflow/deepseek-ai/DeepSeek-V3", "siliconflow/zai-org/GLM-4.6"),
        onboarding_hint="SiliconFlow uses an OpenAI-compatible base URL; copy the full upstream model id from the SiliconFlow model catalog.",
    ),
    "cerebras": ProviderProfile(
        family="openai_compatible",
        recommended_models=("cerebras/zai-glm-4.7", "cerebras/qwen-3-coder-480b"),
        onboarding_hint="Cerebras exposes an OpenAI-compatible API; confirm that your account has access to the selected model family.",
    ),
    "openai_codex": ProviderProfile(
        family="oauth",
        recommended_models=("openai-codex/gpt-5.3-codex",),
        onboarding_hint="OpenAI Codex uses local OAuth; sign in before validating the provider.",
    ),
    "gemini_oauth": ProviderProfile(
        family="oauth",
        recommended_models=("gemini_oauth/gemini-2.0-flash",),
        onboarding_hint="Gemini OAuth uses a local OAuth token against the Google OpenAI-compatible endpoint.",
    ),
    "qwen_oauth": ProviderProfile(
        family="oauth",
        recommended_models=("qwen_oauth/qwen-plus",),
        onboarding_hint="Qwen OAuth uses a local OAuth token against the Qwen-compatible endpoint.",
    ),
    "ollama": ProviderProfile(
        family="local_runtime",
        recommended_models=("openai/llama3.2", "openai/qwen2.5-coder:7b"),
        onboarding_hint="Ollama requires a running local runtime and a model downloaded ahead of time with 'ollama pull'.",
    ),
    "vllm": ProviderProfile(
        family="local_runtime",
        recommended_models=("vllm/meta-llama/Llama-3.2-3B-Instruct",),
        onboarding_hint="vLLM requires a running server and a model loaded when the process starts.",
    ),
}


def provider_profile(name: str) -> ProviderProfile:
    provider_name = str(name or "").strip().lower().replace("-", "_")
    return PROVIDER_PROFILES.get(
        provider_name,
        ProviderProfile(
            family="custom",
            recommended_models=(),
            onboarding_hint="Provider profile is unknown; review the model, auth, and endpoint manually.",
        ),
    )


def default_provider_model(name: str) -> str:
    profile = provider_profile(name)
    return str(profile.recommended_models[0] if profile.recommended_models else "")
