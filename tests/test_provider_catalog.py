from __future__ import annotations

from clawlite.auth import PROVIDERS
from clawlite.core.providers import get_provider_spec, normalize_provider


def test_provider_aliases():
    assert normalize_provider("google") == "gemini"
    assert normalize_provider("codex") == "openai-codex"
    assert normalize_provider("z.ai") == "zai"
    assert normalize_provider("z-ai") == "zai"


def test_provider_specs_basic_presence():
    for key in ("openai", "openai-codex", "anthropic", "gemini", "openrouter", "groq", "moonshot", "mistral"):
        spec = get_provider_spec(key)
        assert spec is not None
        assert spec.request_url


def test_auth_catalog_includes_openclaw_like_providers():
    for key in ("openai", "openai-codex", "anthropic", "gemini", "openrouter", "groq", "moonshot", "mistral", "zai"):
        assert key in PROVIDERS
