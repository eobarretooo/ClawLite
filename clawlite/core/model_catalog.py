"""
ClawLite Model Catalog — Registro central de modelos com metadata.

Cada modelo tem: context window, custo por 1K tokens, capabilities,
e flags de compatibilidade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelCost:
    """Custo por 1K tokens em USD."""
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0


@dataclass
class ModelCapabilities:
    """Capacidades do modelo."""
    text: bool = True
    image_input: bool = False
    tool_calling: bool = True
    streaming: bool = True
    reasoning: bool = False
    json_mode: bool = False


@dataclass
class ModelEntry:
    """Entrada completa de um modelo no catálogo."""
    id: str
    provider: str
    display_name: str
    context_window: int = 128_000
    max_output_tokens: int = 4_096
    cost: ModelCost = field(default_factory=ModelCost)
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    deprecated: bool = False
    api_format: str = "openai"  # openai | anthropic | ollama


# ──────────────────────────────────────────────
# Catálogo Built-in
# ──────────────────────────────────────────────

CATALOG: dict[str, ModelEntry] = {
    # OpenAI
    "openai/gpt-4o-mini": ModelEntry(
        id="gpt-4o-mini", provider="openai", display_name="GPT-4o Mini",
        context_window=128_000, max_output_tokens=16_384,
        cost=ModelCost(input=0.00015, output=0.0006),
        capabilities=ModelCapabilities(image_input=True, json_mode=True),
    ),
    "openai/gpt-4o": ModelEntry(
        id="gpt-4o", provider="openai", display_name="GPT-4o",
        context_window=128_000, max_output_tokens=16_384,
        cost=ModelCost(input=0.005, output=0.015),
        capabilities=ModelCapabilities(image_input=True, json_mode=True),
    ),
    "openai/gpt-4.1-mini": ModelEntry(
        id="gpt-4.1-mini", provider="openai", display_name="GPT-4.1 Mini",
        context_window=1_000_000, max_output_tokens=32_768,
        cost=ModelCost(input=0.0004, output=0.0016),
        capabilities=ModelCapabilities(image_input=True, json_mode=True),
    ),
    "openai/gpt-4.1": ModelEntry(
        id="gpt-4.1", provider="openai", display_name="GPT-4.1",
        context_window=1_000_000, max_output_tokens=32_768,
        cost=ModelCost(input=0.002, output=0.008),
        capabilities=ModelCapabilities(image_input=True, json_mode=True),
    ),
    "openai/o3-mini": ModelEntry(
        id="o3-mini", provider="openai", display_name="o3-mini",
        context_window=200_000, max_output_tokens=100_000,
        cost=ModelCost(input=0.0011, output=0.0044),
        capabilities=ModelCapabilities(reasoning=True, json_mode=True),
    ),

    # Anthropic
    "anthropic/claude-sonnet-4-6": ModelEntry(
        id="claude-sonnet-4-6", provider="anthropic", display_name="Claude Sonnet 4.6",
        context_window=200_000, max_output_tokens=16_384,
        cost=ModelCost(input=0.003, output=0.015),
        capabilities=ModelCapabilities(image_input=True, reasoning=True),
        api_format="anthropic",
    ),
    "anthropic/claude-haiku-4-5": ModelEntry(
        id="claude-haiku-4-5", provider="anthropic", display_name="Claude Haiku 4.5",
        context_window=200_000, max_output_tokens=8_192,
        cost=ModelCost(input=0.0008, output=0.004),
        capabilities=ModelCapabilities(image_input=True),
        api_format="anthropic",
    ),
    "anthropic/claude-opus-4-6": ModelEntry(
        id="claude-opus-4-6", provider="anthropic", display_name="Claude Opus 4.6",
        context_window=200_000, max_output_tokens=32_000,
        cost=ModelCost(input=0.015, output=0.075),
        capabilities=ModelCapabilities(image_input=True, reasoning=True),
        api_format="anthropic",
    ),

    # Ollama (local, custo zero)
    "ollama/llama3.1:8b": ModelEntry(
        id="llama3.1:8b", provider="ollama", display_name="Llama 3.1 8B",
        context_window=128_000, max_output_tokens=4_096,
        cost=ModelCost(),
        capabilities=ModelCapabilities(streaming=True),
        api_format="ollama",
    ),
    "ollama/llama3.2:3b": ModelEntry(
        id="llama3.2:3b", provider="ollama", display_name="Llama 3.2 3B",
        context_window=128_000, max_output_tokens=4_096,
        cost=ModelCost(),
        capabilities=ModelCapabilities(streaming=True),
        api_format="ollama",
    ),
    "ollama/qwen2.5:7b": ModelEntry(
        id="qwen2.5:7b", provider="ollama", display_name="Qwen 2.5 7B",
        context_window=128_000, max_output_tokens=4_096,
        cost=ModelCost(),
        capabilities=ModelCapabilities(streaming=True),
        api_format="ollama",
    ),
    "ollama/mistral:7b": ModelEntry(
        id="mistral:7b", provider="ollama", display_name="Mistral 7B",
        context_window=32_000, max_output_tokens=4_096,
        cost=ModelCost(),
        capabilities=ModelCapabilities(streaming=True),
        api_format="ollama",
    ),

    # OpenRouter (custo variável, usa formato OpenAI)
    "openrouter/auto": ModelEntry(
        id="auto", provider="openrouter", display_name="OpenRouter Auto",
        context_window=128_000, max_output_tokens=4_096,
        cost=ModelCost(input=0.0005, output=0.0015),
    ),
    "openrouter/google/gemini-2.0-flash": ModelEntry(
        id="google/gemini-2.0-flash", provider="openrouter", display_name="Gemini 2.0 Flash",
        context_window=1_000_000, max_output_tokens=8_192,
        cost=ModelCost(input=0.0001, output=0.0004),
        capabilities=ModelCapabilities(image_input=True),
    ),
}


def get_model(model_key: str) -> ModelEntry | None:
    """Busca modelo pelo identificador completo (provider/model)."""
    return CATALOG.get(model_key)


def get_model_or_default(model_key: str) -> ModelEntry:
    """Busca modelo ou retorna um entry genérico com valores padrão."""
    entry = CATALOG.get(model_key)
    if entry:
        return entry
    # Modelo desconhecido: retorna entry genérico
    provider = model_key.split("/", 1)[0] if "/" in model_key else "unknown"
    model_id = model_key.split("/", 1)[1] if "/" in model_key else model_key
    return ModelEntry(
        id=model_id,
        provider=provider,
        display_name=model_key,
        context_window=128_000,
        max_output_tokens=4_096,
        cost=ModelCost(input=0.001, output=0.003),
    )


def estimate_tokens(text: str) -> int:
    """Estimativa rápida de tokens (1 token ~ 4 chars para inglês, ~3 para PT-BR)."""
    return max(1, len(text) // 3)


def estimate_cost_usd(model_key: str, input_tokens: int, output_tokens: int) -> float:
    """Estima custo em USD para uma chamada ao modelo."""
    entry = get_model_or_default(model_key)
    input_cost = (input_tokens / 1000) * entry.cost.input
    output_cost = (output_tokens / 1000) * entry.cost.output
    return round(input_cost + output_cost, 6)


def context_window(model_key: str) -> int:
    """Retorna o context window do modelo em tokens."""
    return get_model_or_default(model_key).context_window


def list_models(provider: str = "") -> list[ModelEntry]:
    """Lista modelos do catálogo, opcionalmente filtrados por provider."""
    entries = list(CATALOG.values())
    if provider:
        entries = [e for e in entries if e.provider == provider]
    return sorted(entries, key=lambda e: (e.provider, e.display_name))
