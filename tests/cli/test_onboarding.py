from __future__ import annotations

from clawlite.cli.onboarding import apply_provider_selection
from clawlite.cli.onboarding import ensure_gateway_token
from clawlite.cli.onboarding import probe_provider
from clawlite.cli.onboarding import probe_telegram
from clawlite.config.schema import AppConfig


def test_apply_provider_selection_openai_updates_config() -> None:
    cfg = AppConfig.from_dict({})
    persisted = apply_provider_selection(
        cfg,
        provider="openai",
        api_key="sk-openai-123456",
        base_url="https://api.openai.com/v1",
    )

    assert persisted["provider"] == "openai"
    assert persisted["model"].startswith("openai/")
    assert persisted["api_key_masked"].endswith("3456")
    assert cfg.providers.openai.api_key == "sk-openai-123456"
    assert cfg.providers.openai.api_base == "https://api.openai.com/v1"
    assert cfg.provider.model == cfg.agents.defaults.model


def test_ensure_gateway_token_generates_when_missing() -> None:
    cfg = AppConfig.from_dict({"gateway": {"auth": {"mode": "required", "token": ""}}})
    generated = ensure_gateway_token(cfg)
    assert generated
    assert cfg.gateway.auth.token == generated


def test_probe_provider_openai_success(monkeypatch) -> None:
    class _Response:
        status_code = 200
        is_success = True
        text = "ok"

        @staticmethod
        def json() -> dict[str, list[dict[str, str]]]:
            return {"data": [{"id": "gpt-4o-mini"}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            assert url.endswith("/models")
            assert str(headers.get("Authorization", "")).startswith("Bearer sk-")
            return _Response()

    monkeypatch.setattr("clawlite.cli.onboarding.httpx.Client", _Client)
    payload = probe_provider("openai", api_key="sk-openai-123456", base_url="https://api.openai.com/v1")
    assert payload["ok"] is True
    assert payload["status_code"] == 200
    assert payload["api_key_masked"].endswith("3456")


def test_probe_telegram_handles_network_error(monkeypatch) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            raise RuntimeError("network_down")

    monkeypatch.setattr("clawlite.cli.onboarding.httpx.Client", _Client)
    payload = probe_telegram("12345:ABCDE")
    assert payload["ok"] is False
    assert payload["error"] == "network_down"
    assert payload["token_masked"].endswith("BCDE")
