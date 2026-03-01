from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

ApiStyle = Literal["openai", "anthropic", "local"]


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    display: str
    auth_url: str
    note: str
    env_vars: tuple[str, ...] = ()
    api_style: ApiStyle = "openai"
    request_url: str = ""
    default_model: str = ""
    token_optional: bool = False


_ALIASES: dict[str, str] = {
    "google": "gemini",
    "google-gemini": "gemini",
    "codex": "openai-codex",
    "openai-codex-cli": "openai-codex",
    "z.ai": "zai",
    "z-ai": "zai",
}


def normalize_provider(provider: str) -> str:
    key = str(provider or "").strip().lower()
    return _ALIASES.get(key, key)


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        key="openai",
        display="OpenAI",
        auth_url="https://platform.openai.com/api-keys",
        note="OpenAI API usa API key.",
        env_vars=("OPENAI_API_KEY",),
        api_style="openai",
        request_url="https://api.openai.com/v1/chat/completions",
        default_model="gpt-4o-mini",
    ),
    "openai-codex": ProviderSpec(
        key="openai-codex",
        display="OpenAI Codex",
        auth_url="https://chatgpt.com/codex",
        note=(
            "Codex pode usar chave de API (OPENAI_CODEX_API_KEY/OPENAI_API_KEY) "
            "ou token OAuth do Codex CLI (~/.codex/auth.json)."
        ),
        env_vars=("OPENAI_CODEX_API_KEY", "CODEX_API_KEY", "OPENAI_API_KEY", "OPENAI_CODEX_ACCESS_TOKEN"),
        api_style="openai",
        request_url="https://api.openai.com/v1/chat/completions",
        default_model="gpt-5.3-codex",
    ),
    "anthropic": ProviderSpec(
        key="anthropic",
        display="Anthropic",
        auth_url="https://console.anthropic.com/settings/keys",
        note="Anthropic API usa API key.",
        env_vars=("ANTHROPIC_API_KEY",),
        api_style="anthropic",
        request_url="https://api.anthropic.com/v1/messages",
        default_model="claude-haiku-4-5-20251001",
    ),
    "gemini": ProviderSpec(
        key="gemini",
        display="Google Gemini",
        auth_url="https://aistudio.google.com/app/apikey",
        note="Gemini API key (Google AI Studio).",
        env_vars=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        api_style="openai",
        request_url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        default_model="gemini-2.5-flash",
    ),
    "openrouter": ProviderSpec(
        key="openrouter",
        display="OpenRouter",
        auth_url="https://openrouter.ai/keys",
        note="OpenRouter usa API key.",
        env_vars=("OPENROUTER_API_KEY",),
        api_style="openai",
        request_url="https://openrouter.ai/api/v1/chat/completions",
        default_model="openai/gpt-4o-mini",
    ),
    "groq": ProviderSpec(
        key="groq",
        display="Groq",
        auth_url="https://console.groq.com/keys",
        note="Groq usa API key.",
        env_vars=("GROQ_API_KEY",),
        api_style="openai",
        request_url="https://api.groq.com/openai/v1/chat/completions",
        default_model="llama-3.1-8b-instant",
    ),
    "moonshot": ProviderSpec(
        key="moonshot",
        display="Moonshot (Kimi)",
        auth_url="https://platform.moonshot.ai",
        note="Moonshot/Kimi usa API key.",
        env_vars=("MOONSHOT_API_KEY",),
        api_style="openai",
        request_url="https://api.moonshot.ai/v1/chat/completions",
        default_model="kimi-k2.5",
    ),
    "mistral": ProviderSpec(
        key="mistral",
        display="Mistral",
        auth_url="https://console.mistral.ai/api-keys/",
        note="Mistral usa API key.",
        env_vars=("MISTRAL_API_KEY",),
        api_style="openai",
        request_url="https://api.mistral.ai/v1/chat/completions",
        default_model="mistral-large-latest",
    ),
    "xai": ProviderSpec(
        key="xai",
        display="xAI",
        auth_url="https://console.x.ai",
        note="xAI (Grok) usa API key.",
        env_vars=("XAI_API_KEY",),
        api_style="openai",
        request_url="https://api.x.ai/v1/chat/completions",
        default_model="grok-4",
    ),
    "together": ProviderSpec(
        key="together",
        display="Together AI",
        auth_url="https://api.together.xyz/settings/api-keys",
        note="Together AI usa API key.",
        env_vars=("TOGETHER_API_KEY",),
        api_style="openai",
        request_url="https://api.together.xyz/v1/chat/completions",
        default_model="moonshotai/Kimi-K2.5",
    ),
    "huggingface": ProviderSpec(
        key="huggingface",
        display="Hugging Face Inference",
        auth_url="https://huggingface.co/settings/tokens",
        note="Hugging Face usa token de Inference Providers.",
        env_vars=("HUGGINGFACE_HUB_TOKEN", "HF_TOKEN"),
        api_style="openai",
        request_url="https://router.huggingface.co/v1/chat/completions",
        default_model="deepseek-ai/DeepSeek-R1",
    ),
    "nvidia": ProviderSpec(
        key="nvidia",
        display="NVIDIA",
        auth_url="https://catalog.ngc.nvidia.com/",
        note="NVIDIA NIM/NGC usa API key.",
        env_vars=("NVIDIA_API_KEY",),
        api_style="openai",
        request_url="https://integrate.api.nvidia.com/v1/chat/completions",
        default_model="nvidia/llama-3.1-nemotron-70b-instruct",
    ),
    "qianfan": ProviderSpec(
        key="qianfan",
        display="Qianfan",
        auth_url="https://console.bce.baidu.com/qianfan/ais/console/apiKey",
        note="Qianfan usa API key.",
        env_vars=("QIANFAN_API_KEY",),
        api_style="openai",
        request_url="https://qianfan.baidubce.com/v2/chat/completions",
        default_model="deepseek-v3.2",
    ),
    "venice": ProviderSpec(
        key="venice",
        display="Venice",
        auth_url="https://venice.ai",
        note="Venice usa API key.",
        env_vars=("VENICE_API_KEY",),
        api_style="openai",
        request_url="https://api.venice.ai/api/v1/chat/completions",
        default_model="llama-3.3-70b",
    ),
    "litellm": ProviderSpec(
        key="litellm",
        display="LiteLLM",
        auth_url="https://docs.litellm.ai",
        note="LiteLLM pode rodar sem token local, ou com token próprio.",
        env_vars=("LITELLM_API_KEY",),
        api_style="openai",
        request_url="http://127.0.0.1:4000/v1/chat/completions",
        default_model="claude-opus-4-6",
        token_optional=True,
    ),
    "vercel-ai-gateway": ProviderSpec(
        key="vercel-ai-gateway",
        display="Vercel AI Gateway",
        auth_url="https://vercel.com/ai-gateway",
        note="Vercel AI Gateway usa API key.",
        env_vars=("AI_GATEWAY_API_KEY",),
        api_style="openai",
        request_url="https://ai-gateway.vercel.sh/v1/chat/completions",
        default_model="anthropic/claude-opus-4.6",
    ),
    "kilocode": ProviderSpec(
        key="kilocode",
        display="Kilo Gateway",
        auth_url="https://app.kilo.ai",
        note="Kilo Gateway usa API key.",
        env_vars=("KILOCODE_API_KEY",),
        api_style="openai",
        request_url="https://api.kilo.ai/api/gateway/chat/completions",
        default_model="anthropic/claude-opus-4.6",
    ),
    "zai": ProviderSpec(
        key="zai",
        display="Z.AI (GLM)",
        auth_url="https://platform.z.ai",
        note="Z.AI usa API key.",
        env_vars=("ZAI_API_KEY", "Z_AI_API_KEY"),
        api_style="openai",
        request_url="https://api.z.ai/api/paas/v4/chat/completions",
        default_model="glm-5",
    ),
    "xiaomi": ProviderSpec(
        key="xiaomi",
        display="Xiaomi MiMo",
        auth_url="https://platform.xiaomimimo.com/#/console/api-keys",
        note="Xiaomi MiMo usa API key (Anthropic-compatible endpoint).",
        env_vars=("XIAOMI_API_KEY",),
        api_style="anthropic",
        request_url="https://api.xiaomimimo.com/anthropic/messages",
        default_model="mimo-v2-flash",
    ),
    "minimax": ProviderSpec(
        key="minimax",
        display="MiniMax",
        auth_url="https://platform.minimax.io",
        note="MiniMax usa API key.",
        env_vars=("MINIMAX_API_KEY",),
        api_style="anthropic",
        request_url="https://api.minimax.io/anthropic/messages",
        default_model="MiniMax-M2.1",
    ),
    "vllm": ProviderSpec(
        key="vllm",
        display="vLLM (local)",
        auth_url="https://docs.vllm.ai",
        note="vLLM usa endpoint OpenAI-compatible local.",
        env_vars=("VLLM_API_KEY",),
        api_style="openai",
        request_url="http://127.0.0.1:8000/v1/chat/completions",
        default_model="Qwen/Qwen2.5-7B-Instruct",
        token_optional=True,
    ),
    "ollama": ProviderSpec(
        key="ollama",
        display="Ollama",
        auth_url="https://ollama.com",
        note="Ollama local nao exige API key.",
        env_vars=(),
        api_style="local",
        request_url="http://127.0.0.1:11434/api/tags",
        default_model="llama3.1:8b",
        token_optional=True,
    ),
}


def get_provider_spec(provider: str) -> ProviderSpec | None:
    return PROVIDER_SPECS.get(normalize_provider(provider))


def provider_env_vars(provider: str) -> tuple[str, ...]:
    spec = get_provider_spec(provider)
    return spec.env_vars if spec else ()


def resolve_provider_token(provider: str, fallback_token: str = "") -> str:
    for env_name in provider_env_vars(provider):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return str(fallback_token or "").strip()
