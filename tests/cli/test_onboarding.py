from __future__ import annotations

from pathlib import Path

from clawlite.cli.onboarding import apply_provider_selection
from clawlite.cli.onboarding import ensure_gateway_token
from clawlite.cli.onboarding import probe_provider
from clawlite.cli.onboarding import probe_telegram
from clawlite.cli.onboarding import run_onboarding_wizard
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


def test_apply_provider_selection_ollama_normalizes_runtime_base_url() -> None:
    cfg = AppConfig.from_dict({})
    persisted = apply_provider_selection(
        cfg,
        provider="ollama",
        api_key="",
        base_url="http://127.0.0.1:11434",
    )

    assert persisted["provider"] == "ollama"
    assert persisted["base_url"] == "http://127.0.0.1:11434/v1"
    assert cfg.provider.litellm_base_url == "http://127.0.0.1:11434/v1"
    assert cfg.providers.ollama.api_base == "http://127.0.0.1:11434/v1"


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


def test_probe_provider_ollama_accepts_runtime_base_url_with_v1(monkeypatch) -> None:
    class _Response:
        status_code = 200
        is_success = True
        text = "ok"

        @staticmethod
        def json() -> dict[str, list[dict[str, str]]]:
            return {"models": [{"name": "llama3.2:latest"}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            del headers
            assert url == "http://127.0.0.1:11434/api/tags"
            return _Response()

    monkeypatch.setattr("clawlite.cli.onboarding.httpx.Client", _Client)
    payload = probe_provider("ollama", api_key="", base_url="http://127.0.0.1:11434/v1")
    assert payload["ok"] is True
    assert payload["status_code"] == 200


def test_run_onboarding_wizard_advanced_persists_custom_model_and_gateway(monkeypatch, tmp_path) -> None:
    cfg = AppConfig.from_dict(
        {
            "workspace_path": str(tmp_path / "workspace"),
            "gateway": {"host": "127.0.0.1", "port": 8787, "auth": {"mode": "off", "token": ""}},
            "provider": {"model": "openai/gpt-4o-mini", "litellm_base_url": "https://api.openai.com/v1"},
        }
    )

    prompt_answers = iter(
        [
            "advanced",
            "0.0.0.0",
            "19090",
            "required",
            "openai",
            "https://api.openai.com/v1",
            "openai/gpt-4.1-mini",
            "sk-openai-123456",
        ]
    )
    confirm_answers = iter([False])

    def _fake_prompt_ask(*args, **kwargs):
        return next(prompt_answers)

    def _fake_confirm_ask(*args, **kwargs):
        return next(confirm_answers)

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", _fake_confirm_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, timeout_s=8.0: {
            "ok": True,
            "status_code": 200,
            "provider": provider,
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
        },
    )
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_telegram",
        lambda token, *, timeout_s=8.0: {
            "ok": True,
            "status_code": 200,
            "token_masked": "",
            "error": "",
        },
    )

    class _FakeWorkspaceLoader:
        def __init__(self, workspace_path):
            self.workspace_path = workspace_path

        def bootstrap(self, *, overwrite, variables):
            return [Path(self.workspace_path) / "IDENTITY.md"]

    monkeypatch.setattr("clawlite.cli.onboarding.WorkspaceLoader", _FakeWorkspaceLoader)

    payload = run_onboarding_wizard(
        cfg,
        config_path=tmp_path / "config.json",
        overwrite=True,
        variables={"assistant_name": "Fox"},
    )

    assert payload["ok"] is True
    assert payload["steps"][1]["step"] == 2
    assert payload["steps"][1]["provider"] == "openai"
    assert payload["steps"][1]["model"] == "openai/gpt-4.1-mini"
    assert payload["persisted"]["provider"]["model"] == "openai/gpt-4.1-mini"
    assert payload["persisted"]["gateway"]["host"] == "0.0.0.0"
    assert payload["persisted"]["gateway"]["port"] == 19090
    assert payload["persisted"]["gateway"]["auth_mode"] == "required"
    assert payload["final"]["gateway_url"] == "http://0.0.0.0:19090"
    assert payload["final"]["gateway_token"]
