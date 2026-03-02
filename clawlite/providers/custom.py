from __future__ import annotations

from clawlite.providers.litellm import LiteLLMProvider


class CustomProvider(LiteLLMProvider):
    """Any OpenAI-compatible endpoint configured by user."""
