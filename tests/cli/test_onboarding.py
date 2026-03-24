from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from clawlite.cli import onboarding as onboarding_module
from clawlite.cli.onboarding import apply_provider_selection
from clawlite.cli.onboarding import build_dashboard_handoff
from clawlite.cli.onboarding import ensure_gateway_token
from clawlite.cli.onboarding import probe_provider
from clawlite.cli.onboarding import probe_telegram
from clawlite.cli.onboarding import resolve_codex_auth
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


def test_apply_provider_selection_xai_updates_dynamic_provider_block() -> None:
    cfg = AppConfig.from_dict({})
    persisted = apply_provider_selection(
        cfg,
        provider="xai",
        api_key="xai_demo_token",
        base_url="https://api.x.ai/v1",
    )

    assert persisted["provider"] == "xai"
    assert persisted["model"] == "xai/grok-4"
    assert cfg.providers.get("xai") is not None
    assert cfg.providers.get("xai").api_key == "xai_demo_token"
    assert cfg.providers.get("xai").api_base == "https://api.x.ai/v1"


def test_apply_provider_selection_openai_codex_updates_auth_and_model() -> None:
    cfg = AppConfig.from_dict({})
    persisted = apply_provider_selection(
        cfg,
        provider="openai-codex",
        api_key="",
        base_url="",
        oauth_access_token="codex-token-123456",
        oauth_account_id="org-1234",
        oauth_source="oauth_cli_kit:get_token",
    )

    assert persisted["provider"] == "openai_codex"
    assert persisted["model"] == "openai-codex/gpt-5.3-codex"
    assert persisted["api_key_masked"].endswith("3456")
    assert persisted["account_id_masked"].endswith("1234")
    assert cfg.auth.providers.openai_codex.access_token == "codex-token-123456"
    assert cfg.auth.providers.openai_codex.account_id == "org-1234"
    assert cfg.auth.providers.openai_codex.source == "oauth_cli_kit:get_token"
    assert cfg.provider.model == "openai-codex/gpt-5.3-codex"
    assert cfg.agents.defaults.model == "openai-codex/gpt-5.3-codex"


def test_resolve_codex_auth_prefers_current_auth_file_over_stale_file_snapshot(tmp_path: Path, monkeypatch) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        '{'
        '"auth_mode":"chatgpt",'
        '"tokens":{"access_token":"fresh-file-token","account_id":"org-fresh"}'
        '}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_CODEX_AUTH_PATH", str(auth_path))
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLAWLITE_CODEX_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("OPENAI_ORG_ID", raising=False)

    cfg = AppConfig.from_dict(
        {
            "auth": {
                "providers": {
                    "openai_codex": {
                        "access_token": "stale-config-token",
                        "account_id": "org-stale",
                        "source": f"file:{auth_path}",
                    }
                }
            }
        }
    )

    resolved = resolve_codex_auth(cfg)

    assert resolved["configured"] is True
    assert resolved["access_token"] == "fresh-file-token"
    assert resolved["account_id"] == "org-fresh"
    assert resolved["source"] == f"file:{auth_path}"


def test_ensure_gateway_token_generates_when_missing() -> None:
    cfg = AppConfig.from_dict({"gateway": {"auth": {"mode": "required", "token": ""}}})
    generated = ensure_gateway_token(cfg)
    assert generated
    assert cfg.gateway.auth.token == generated


def test_build_dashboard_handoff_reports_default_web_search_guidance() -> None:
    cfg = AppConfig.from_dict({"gateway": {"auth": {"mode": "required", "token": "tok-123456"}}})

    payload = build_dashboard_handoff(cfg)

    web_row = next(item for item in payload["guidance"] if item["id"] == "web_search")
    assert "DuckDuckGo" in web_row["body"]
    assert "brave_api_key" in web_row["body"]


def test_build_dashboard_handoff_reports_configured_web_search_backends() -> None:
    cfg = AppConfig.from_dict(
        {
            "gateway": {"auth": {"mode": "required", "token": "tok-123456"}},
            "tools": {"web": {"brave_api_key": "brv-123", "searxng_base_url": "https://searx.example"}},
        }
    )

    payload = build_dashboard_handoff(cfg)

    web_row = next(item for item in payload["guidance"] if item["id"] == "web_search")
    assert "Brave" in web_row["body"]
    assert "SearXNG" in web_row["body"]


def test_build_dashboard_handoff_can_redact_sensitive_dashboard_fields() -> None:
    token = "tok-" + "12345678"
    cfg = AppConfig.from_dict({"gateway": {"auth": {"mode": "required", "token": token}}})

    payload = build_dashboard_handoff(cfg, include_sensitive=False)

    assert payload["gateway_url"] == "http://127.0.0.1:8787"
    assert payload["gateway_token_masked"] == "****12345678"
    assert "gateway_token" not in payload
    assert "dashboard_url_with_token" not in payload
    dashboard_row = next(item for item in payload["guidance"] if item["id"] == "dashboard")
    assert "#token=" not in dashboard_row["body"]
    token_row = next(item for item in payload["guidance"] if item["id"] == "token")
    assert "scoped dashboard session" in token_row["body"]


def test_build_dashboard_handoff_profile_persists_token_to_overlay(tmp_path: Path, monkeypatch) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    base_config_path = tmp_path / "config.json"
    base_config_path.write_text("{}", encoding="utf-8")
    overlay_path = tmp_path / "config.prod.json"
    overlay_path.write_text("{}", encoding="utf-8")
    cfg = AppConfig.from_dict(
        {
            "workspace_path": str(workspace_path),
            "gateway": {"auth": {"mode": "required", "token": ""}},
        }
    )

    def _fake_ensure_gateway_token(config) -> str:
        config.gateway.auth.token = "tok-profile-123456"
        return "tok-profile-123456"

    monkeypatch.setattr("clawlite.cli.onboarding.ensure_gateway_token", _fake_ensure_gateway_token)

    payload = build_dashboard_handoff(
        cfg,
        config_path=base_config_path,
        config_profile="prod",
        ensure_token=True,
    )

    saved_overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    saved_base = json.loads(base_config_path.read_text(encoding="utf-8"))
    backup_row = next(item for item in payload["guidance"] if item["id"] == "workspace_backup")

    assert saved_base == {}
    assert saved_overlay["gateway"]["auth"]["token"] == "tok-profile-123456"
    assert not (tmp_path / "config.prod.prod.json").exists()
    assert "config.prod.json" in backup_row["body"]


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
    assert payload["transport"] == "openai_compatible"
    assert payload["family"] == "openai_compatible"
    assert payload["recommended_model"] == "openai/gpt-4o-mini"
    assert "openai/gpt-4o-mini" in payload["recommended_models"]
    assert "billing" in payload["onboarding_hint"].lower()
    assert payload["default_base_url"] == "https://api.openai.com/v1"
    assert payload["key_envs"] == ["OPENAI_API_KEY"]
    assert payload["model_check"]["checked"] is True
    assert payload["model_check"]["ok"] is True
    assert any("OpenAI-compatible" in row for row in payload["hints"])


def test_probe_provider_openai_codex_success(monkeypatch) -> None:
    class _Response:
        status_code = 200
        is_success = True
        text = "data: {\"type\":\"response.completed\"}\n\n"

        @staticmethod
        def json() -> dict[str, str]:
            raise AssertionError("responses probe should be handled as SSE text")

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            assert url.endswith("/codex/responses")
            assert str(headers.get("Authorization", "")).startswith("Bearer codex-")
            assert headers.get("Accept") == "text/event-stream"
            assert json["instructions"] == "You are a concise assistant. Reply briefly."
            assert json["stream"] is True
            assert json["model"] == "gpt-5.3-codex"
            return _Response()

    monkeypatch.setattr("clawlite.cli.onboarding.httpx.Client", _Client)
    payload = probe_provider(
        "openai-codex",
        api_key="",
        base_url="https://chatgpt.com/backend-api",
        model="openai-codex/gpt-5.3-codex",
        oauth_access_token="codex-123456",
    )
    assert payload["ok"] is True
    assert payload["status_code"] == 200
    assert payload["provider"] == "openai_codex"
    assert payload["transport"] == "oauth_codex_responses"
    assert payload["probe_method"] == "POST"
    assert payload["api_key_masked"].endswith("3456")


def test_probe_provider_openai_codex_expired_token_suggests_relogin(monkeypatch) -> None:
    class _Response:
        status_code = 401
        is_success = False
        text = ""

        @staticmethod
        def json() -> dict[str, dict[str, str]]:
            return {"error": {"message": "Provided authentication token is expired. Please try signing in again."}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            assert url.endswith("/codex/responses")
            return _Response()

    monkeypatch.setattr("clawlite.cli.onboarding.httpx.Client", _Client)
    payload = probe_provider(
        "openai-codex",
        api_key="",
        base_url="https://chatgpt.com/backend-api",
        model="openai-codex/gpt-5.3-codex",
        oauth_access_token="codex-123456",
    )
    assert payload["ok"] is False
    assert payload["error"] == "http_status:401"
    assert any("provider login openai-codex" in row for row in payload["hints"])


def test_probe_provider_cerebras_success(monkeypatch) -> None:
    class _Response:
        status_code = 200
        is_success = True
        text = "ok"

        @staticmethod
        def json() -> dict[str, list[dict[str, str]]]:
            return {"data": [{"id": "zai-glm-4.7"}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            assert url == "https://api.cerebras.ai/v1/models"
            assert str(headers.get("Authorization", "")).startswith("Bearer cerebras_demo_")
            return _Response()

    monkeypatch.setattr("clawlite.cli.onboarding.httpx.Client", _Client)
    payload = probe_provider("cerebras", api_key="cerebras_demo_token", base_url="")
    assert payload["ok"] is True
    assert payload["provider"] == "cerebras"
    assert payload["recommended_model"] == "cerebras/zai-glm-4.7"
    assert payload["default_base_url"] == "https://api.cerebras.ai/v1"


def test_apply_provider_selection_aihubmix_uses_default_gateway_base() -> None:
    cfg = AppConfig.from_dict({})
    persisted = apply_provider_selection(
        cfg,
        provider="aihubmix",
        api_key="ahm_demo_token",
        base_url="",
    )

    assert persisted["provider"] == "aihubmix"
    assert persisted["model"] == "aihubmix/openai/gpt-4.1-mini"
    assert persisted["base_url"] == "https://aihubmix.com/v1"
    assert cfg.providers.get("aihubmix") is not None
    assert cfg.providers.get("aihubmix").api_base == "https://aihubmix.com/v1"


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
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_local_provider_runtime",
        lambda **kwargs: {
            "checked": True,
            "ok": True,
            "runtime": "ollama",
            "base_url": kwargs["base_url"],
            "model": "llama3.2",
            "error": "",
            "detail": "",
            "available_models": ["llama3.2:latest"],
        },
    )
    payload = probe_provider("ollama", api_key="", base_url="http://127.0.0.1:11434/v1")
    assert payload["ok"] is True
    assert payload["status_code"] == 200
    assert payload["transport"] == "local_runtime"
    assert any("Ollama runtime responded normally" in row for row in payload["hints"])


def test_probe_provider_openai_model_not_listed_returns_soft_warning(monkeypatch) -> None:
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
    payload = probe_provider(
        "openai",
        api_key="sk-openai-123456",
        base_url="https://api.openai.com/v1",
        model="openai/gpt-4.1-mini",
    )
    assert payload["ok"] is True
    assert payload["model_check"]["checked"] is True
    assert payload["model_check"]["ok"] is False
    assert any("did not appear in the provider's remote list" in row.lower() for row in payload["hints"])


def test_probe_provider_openai_missing_api_key_returns_actionable_hint() -> None:
    payload = probe_provider("openai", api_key="", base_url="https://api.openai.com/v1")
    assert payload["ok"] is False
    assert payload["error"] == "api_key_missing"
    assert payload["transport"] == "openai_compatible"
    assert any("Configure the API key for provider 'openai'" in row for row in payload["hints"])


def test_probe_provider_minimax_uses_anthropic_messages_transport(monkeypatch) -> None:
    class _Response:
        status_code = 200
        is_success = True
        text = "ok"

        @staticmethod
        def json() -> dict[str, str]:
            return {"id": "msg_1"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "https://api.minimax.io/anthropic/messages"
            assert headers["x-api-key"] == "mini-key"
            assert json["model"] == "MiniMax-M2.5"
            assert json["messages"][0]["content"] == "ping"
            return _Response()

    monkeypatch.setattr("clawlite.cli.onboarding.httpx.Client", _Client)
    payload = probe_provider(
        "minimax",
        api_key="mini-key",
        base_url="https://api.minimax.io/anthropic",
        model="minimax/MiniMax-M2.5",
    )
    assert payload["ok"] is True
    assert payload["status_code"] == 200
    assert payload["family"] == "anthropic_compatible"
    assert payload["recommended_model"] == "minimax/MiniMax-M2.5"
    assert "minimax/MiniMax-M2.5" in payload["recommended_models"]
    assert "/anthropic" in payload["onboarding_hint"]


def test_run_onboarding_wizard_advanced_persists_custom_model_and_gateway(monkeypatch, tmp_path) -> None:
    """Section-menu wizard: visit model + gateway sections then done."""
    cfg = AppConfig.from_dict(
        {
            "workspace_path": str(tmp_path / "workspace"),
            "gateway": {"host": "127.0.0.1", "port": 8787, "auth": {"mode": "off", "token": ""}},
            "provider": {"model": "openai/gpt-4o-mini", "litellm_base_url": "https://api.openai.com/v1"},
        }
    )

    # New section-menu flow:
    # Flow -> "2" (advanced)
    # Menu → "1" (model), then provider/key/model prompts
    # Menu → "2" (gateway), then host/port/auth prompts
    # Menu → "5" (done)
    prompt_answers = iter([
        "2",                      # flow menu: advanced
        "1",                      # section menu: model
        "openai",                 # provider
        "sk-openai-123456",       # api key
        "openai/gpt-4.1-mini",   # model
        "2",                      # section menu: gateway
        "0.0.0.0",               # host
        "19090",                  # port
        "required",              # auth mode
        "5",                      # section menu: done
    ])
    confirm_answers = iter([])

    def _fake_prompt_ask(*args, **kwargs):
        return next(prompt_answers)

    def _fake_confirm_ask(*args, **kwargs):
        return next(confirm_answers)

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", _fake_confirm_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": provider,
            "family": "openai_compatible",
            "recommended_model": "openai/gpt-4o-mini",
            "recommended_models": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
            "onboarding_hint": "OpenAI responds via the standard OpenAI-compatible endpoint; validate billing and the active project.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "hints": [],
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
    assert payload["flow"] == "advanced"
    assert "model" in payload["visited_sections"]
    assert "gateway" in payload["visited_sections"]
    assert payload["persisted"]["provider"]["model"] == "openai/gpt-4.1-mini"
    assert payload["persisted"]["gateway"]["host"] == "0.0.0.0"
    assert payload["persisted"]["gateway"]["port"] == 19090
    assert payload["persisted"]["gateway"]["auth_mode"] == "required"
    assert payload["final"]["gateway_url"] == "http://0.0.0.0:19090"
    assert payload["final"]["dashboard_url_with_handoff"].startswith("http://0.0.0.0:19090#handoff=")
    assert payload["final"]["dashboard_url_with_token"].startswith("http://0.0.0.0:19090#handoff=")
    assert payload["final"]["bootstrap_pending"] is False
    assert payload["final"]["recommended_first_message"] == ""
    assert payload["final"]["hatch_session_id"] == "hatch:operator"
    assert any(item["id"] == "dashboard" for item in payload["final"]["guidance"])
    assert any(item["id"] == "security" for item in payload["final"]["guidance"])
    assert payload["final"]["gateway_token"]


def test_run_onboarding_wizard_saves_to_profile_overlay(monkeypatch, tmp_path) -> None:
    cfg = AppConfig.from_dict({"workspace_path": str(tmp_path / "workspace")})
    saved: dict[str, str] = {}

    monkeypatch.setattr("clawlite.cli.onboarding._print_banner", lambda console: None)
    monkeypatch.setattr(
        "clawlite.cli.onboarding._run_quickstart_flow",
        lambda console, config, overwrite, variables: {
            "provider_key": "openai",
            "provider_probe": {"ok": True},
            "telegram_probe": {"ok": True},
            "generated_files": [Path(config.workspace_path) / "IDENTITY.md"],
            "provider_persisted": {"provider": "openai", "model": "openai/gpt-4o-mini"},
            "visited_sections": ["model", "workspace"],
        },
    )
    monkeypatch.setattr("clawlite.cli.onboarding.ensure_gateway_token", lambda config: "tok-profile-123456")
    monkeypatch.setattr(
        "clawlite.cli.onboarding.save_raw_config_payload",
        lambda payload, path, profile="": saved.setdefault("path", str(path)) or path,
    )
    monkeypatch.setattr(
        "clawlite.cli.onboarding.build_dashboard_handoff",
        lambda config, *, config_path, variables, ensure_token, bootstrap_pending_override: {
            "gateway_url": "http://127.0.0.1:8787",
            "dashboard_url_with_handoff": "http://127.0.0.1:8787#handoff=test",
            "dashboard_url_with_token": "http://127.0.0.1:8787#handoff=test",
            "gateway_token": "tok-profile-123456",
            "bootstrap_pending": False,
            "recommended_first_message": "",
            "hatch_session_id": "hatch:operator",
            "guidance": [],
            "onboarding": {"completed": True},
            "onboarding_label": "completed",
        },
    )

    payload = run_onboarding_wizard(
        cfg,
        config_path=tmp_path / "config.json",
        config_profile="prod",
        overwrite=True,
        variables={},
        flow="quickstart",
    )

    assert payload["ok"] is True
    assert payload["saved_path"] == str(tmp_path / "config.prod.json")
    assert saved["path"] == str(tmp_path / "config.prod.json")


def test_run_onboarding_wizard_disables_existing_telegram_when_user_declines(monkeypatch, tmp_path) -> None:
    """Section-menu wizard: visit channels section and decline Telegram."""
    cfg = AppConfig.from_dict(
        {
            "workspace_path": str(tmp_path / "workspace"),
            "channels": {
                "telegram": {
                    "enabled": True,
                    "token": "123:ABC",
                }
            },
            "provider": {"model": "openai/gpt-4o-mini", "litellm_base_url": "https://api.openai.com/v1"},
        }
    )

    # New section-menu flow:
    # Flow -> "2" (advanced)
    # Menu → "3" (channels), Confirm "Enable Telegram?" → False
    # Menu → "5" (done)
    prompt_answers = iter([
        "2",   # flow menu: advanced
        "3",   # section menu: channels
        "5",   # section menu: done
    ])
    confirm_answers = iter([False])  # "Enable Telegram bot?" → False

    def _fake_prompt_ask(*args, **kwargs):
        return next(prompt_answers)

    def _fake_confirm_ask(*args, **kwargs):
        return next(confirm_answers)

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", _fake_confirm_ask)

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
    assert payload["flow"] == "advanced"
    assert "channels" in payload["visited_sections"]
    assert payload["persisted"]["telegram"]["enabled"] is False
    assert cfg.channels.telegram.enabled is False
    # token preserved — user only disabled, didn't clear it
    assert cfg.channels.telegram.token == "123:ABC"


def test_run_onboarding_wizard_quickstart_uses_guided_defaults(monkeypatch, tmp_path) -> None:
    cfg = AppConfig.from_dict(
        {
            "workspace_path": str(tmp_path / "workspace"),
            "provider": {"model": "openai/gpt-4o-mini", "litellm_base_url": "https://api.openai.com/v1"},
        }
    )

    prompt_answers = iter([
        "1",                    # flow menu: quickstart
        "openai",               # provider
        "sk-openai-123456",     # api key
        "openai/gpt-4.1-mini",  # model
    ])
    confirm_answers = iter([False])

    def _fake_prompt_ask(*args, **kwargs):
        return next(prompt_answers)

    def _fake_confirm_ask(*args, **kwargs):
        return next(confirm_answers)

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", _fake_confirm_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": provider,
            "family": "openai_compatible",
            "recommended_model": "openai/gpt-4o-mini",
            "recommended_models": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
            "onboarding_hint": "OpenAI responds via the standard OpenAI-compatible endpoint; validate billing and the active project.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "hints": [],
        },
    )

    class _FakeWorkspaceLoader:
        def __init__(self, workspace_path):
            self.workspace_path = workspace_path

        def bootstrap(self, *, overwrite, variables):
            return [Path(self.workspace_path) / "IDENTITY.md", Path(self.workspace_path) / "BOOTSTRAP.md"]

    monkeypatch.setattr("clawlite.cli.onboarding.WorkspaceLoader", _FakeWorkspaceLoader)

    payload = run_onboarding_wizard(
        cfg,
        config_path=tmp_path / "config.json",
        overwrite=True,
        variables={"assistant_name": "Fox"},
    )

    assert payload["ok"] is True
    assert payload["flow"] == "quickstart"
    assert payload["visited_sections"] == ["channels", "gateway", "model", "workspace"]
    assert payload["persisted"]["provider"]["model"] == "openai/gpt-4.1-mini"
    assert payload["persisted"]["gateway"]["host"] == "127.0.0.1"
    assert payload["persisted"]["gateway"]["port"] == 8787
    assert payload["persisted"]["gateway"]["auth_mode"] == "required"
    assert payload["persisted"]["telegram"]["enabled"] is False
    assert len(payload["workspace"]["created_files"]) == 2
    assert payload["final"]["dashboard_url_with_handoff"].startswith("http://127.0.0.1:8787#handoff=")
    assert payload["final"]["dashboard_url_with_token"].startswith("http://127.0.0.1:8787#handoff=")
    assert payload["final"]["bootstrap_pending"] is True
    assert payload["final"]["recommended_first_message"] == "Wake up, my friend!"
    assert payload["final"]["hatch_session_id"] == "hatch:operator"
    assert any(item["id"] == "hatch" for item in payload["final"]["guidance"])
    assert payload["final"]["gateway_token"]


def test_run_onboarding_wizard_quickstart_supports_openai_codex(monkeypatch, tmp_path) -> None:
    cfg = AppConfig.from_dict(
        {
            "workspace_path": str(tmp_path / "workspace"),
            "provider": {"model": "openai/gpt-4o-mini"},
        }
    )

    prompt_answers = iter([
        "1",
        "openai-codex",
        "openai-codex/gpt-5.3-codex",
    ])
    confirm_answers = iter([False])

    def _fake_prompt_ask(*args, **kwargs):
        return next(prompt_answers)

    def _fake_confirm_ask(*args, **kwargs):
        return next(confirm_answers)

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", _fake_confirm_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding._resolve_codex_auth_interactive",
        lambda config: {
            "configured": True,
            "access_token": "codex-token-123456",
            "account_id": "org-1234",
            "source": "file:/tmp/.codex/auth.json",
            "token_masked": "********3456",
            "account_id_masked": "****1234",
        },
    )
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "openai_codex",
            "family": "oauth",
            "recommended_model": "openai-codex/gpt-5.3-codex",
            "recommended_models": ["openai-codex/gpt-5.3-codex"],
            "onboarding_hint": "OpenAI Codex usa OAuth local.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "transport": "oauth_codex_responses",
            "probe_method": "POST",
            "hints": [],
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
        variables={},
    )

    assert payload["ok"] is True
    assert payload["flow"] == "quickstart"
    assert payload["persisted"]["provider"]["provider"] == "openai_codex"
    assert payload["persisted"]["provider"]["model"] == "openai-codex/gpt-5.3-codex"
    assert payload["persisted"]["provider"]["source"] == "file:/tmp/.codex/auth.json"
    assert payload["final"]["bootstrap_pending"] is False
    assert payload["final"]["hatch_session_id"] == "hatch:operator"
    assert any(item["id"] == "workspace_backup" for item in payload["final"]["guidance"])
    assert cfg.auth.providers.openai_codex.access_token == "codex-token-123456"
    assert payload["persisted"]["telegram"]["enabled"] is False


def test_configure_model_uses_provider_specific_default_and_prints_suggestions(monkeypatch) -> None:
    cfg = AppConfig.from_dict(
        {
            "provider": {
                "model": "gemini/gemini-2.5-flash",
                "litellm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            }
        }
    )
    prompt_calls: list[tuple[str, str]] = []

    def _fake_prompt_ask(label: str, *args, **kwargs):
        prompt_calls.append((label, str(kwargs.get("default", ""))))
        if label.strip() == "Provider":
            return "openai-codex"
        if label.strip() == "Model":
            assert kwargs.get("default") == "openai-codex/gpt-5.3-codex"
            return "openai-codex/gpt-5.3-codex"
        raise AssertionError(f"unexpected prompt: {label}")

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding._resolve_codex_auth_interactive",
        lambda config: {
            "configured": True,
            "access_token": "codex-token-123456",
            "account_id": "org-1234",
            "source": "file:/tmp/.codex/auth.json",
            "token_masked": "********3456",
            "account_id_masked": "****1234",
        },
    )
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "openai_codex",
            "family": "oauth",
            "recommended_model": "openai-codex/gpt-5.3-codex",
            "recommended_models": ["openai-codex/gpt-5.3-codex"],
            "onboarding_hint": "OpenAI Codex uses local OAuth; sign in before validating the provider.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "transport": "oauth_codex_responses",
            "probe_method": "POST",
            "hints": [],
        },
    )

    console = Console(record=True, width=120)
    onboarding_module._configure_model(console, cfg, allow_continue_on_probe_failure=True)

    rendered = console.export_text()
    assert "openai-codex suggestions" in rendered.lower()
    assert "Suggested models:" in rendered
    assert "clawlite provider login openai-codex" in rendered


def test_configure_model_prompts_for_azure_openai_base_url(monkeypatch) -> None:
    cfg = AppConfig.from_dict({"provider": {"model": "openai/gpt-4o-mini"}})
    asked: list[tuple[str, str]] = []

    def _fake_prompt_ask(label: str, *args, **kwargs):
        asked.append((label, str(kwargs.get("default", ""))))
        if label.strip() == "Provider":
            return "azure-openai"
        if label.strip() == "azure-openai API key":
            return "azure-key-123456"
        if label.strip() == "azure-openai base URL":
            return "https://example-resource.openai.azure.com/openai/v1"
        if label.strip() == "Model":
            assert kwargs.get("default") == "azure-openai/gpt-4.1-mini"
            return "azure-openai/gpt-4.1-mini"
        raise AssertionError(f"unexpected prompt: {label}")

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "azure_openai",
            "family": "openai_compatible",
            "recommended_model": "azure-openai/gpt-4.1-mini",
            "recommended_models": ["azure-openai/gpt-4.1-mini"],
            "onboarding_hint": "Azure OpenAI uses a resource-scoped /openai/v1 endpoint.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "hints": [],
        },
    )

    console = Console(record=True, width=120)
    provider, api_key, base_url, selected_model, probe, oauth_payload = onboarding_module._configure_model(
        console,
        cfg,
        allow_continue_on_probe_failure=True,
    )

    assert provider == "azure-openai"
    assert api_key == "azure-key-123456"
    assert base_url == "https://example-resource.openai.azure.com/openai/v1"
    assert selected_model == "azure-openai/gpt-4.1-mini"
    assert probe["provider"] == "azure_openai"
    assert oauth_payload == {"access_token": "", "account_id": "", "source": ""}
    assert any(label.strip() == "azure-openai base URL" for label, _ in asked)


def test_configure_model_reuses_detected_local_runtime_base_url_and_prints_hint(monkeypatch) -> None:
    cfg = AppConfig.from_dict(
        {
            "provider": {
                "model": "openai/gpt-4o-mini",
                "litellm_base_url": "http://localhost:11434",
            }
        }
    )
    asked: list[tuple[str, str]] = []

    def _fake_prompt_ask(label: str, *args, **kwargs):
        default = str(kwargs.get("default", ""))
        asked.append((label, default))
        if label.strip() == "Provider":
            assert default == "ollama"
            return "ollama"
        if label.strip() == "ollama base URL":
            assert default == "http://localhost:11434/v1"
            return default
        if label.strip() == "Model":
            assert default == "openai/llama3.2"
            return default
        raise AssertionError(f"unexpected prompt: {label}")

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "ollama",
            "family": "local_runtime",
            "recommended_model": "openai/llama3.2",
            "recommended_models": ["openai/llama3.2"],
            "onboarding_hint": "Ollama requires a running local runtime and a model downloaded ahead of time with 'ollama pull'.",
            "base_url": base_url,
            "api_key_masked": "",
            "error": "",
            "hints": [],
        },
    )

    console = Console(record=True, width=140)
    provider, api_key, base_url, selected_model, probe, oauth_payload = onboarding_module._configure_model(
        console,
        cfg,
        allow_continue_on_probe_failure=True,
    )

    rendered = console.export_text()
    assert provider == "ollama"
    assert api_key == ""
    assert base_url == "http://localhost:11434/v1"
    assert selected_model == "openai/llama3.2"
    assert probe["provider"] == "ollama"
    assert oauth_payload == {"access_token": "", "account_id": "", "source": ""}
    assert "Suggested provider:" in rendered
    assert "detected from the current local runtime base URL" in rendered
    assert "Local runtime:" in rendered
    assert "http://localhost:11434/v1" in rendered
    assert "checks that the model is loaded" in rendered


def test_configure_model_defaults_provider_from_single_provider_env(monkeypatch) -> None:
    cfg = AppConfig.from_dict({"provider": {"model": "openai/gpt-4o-mini"}})
    asked_labels: list[str] = []

    def _fake_prompt_ask(label: str, *args, **kwargs):
        asked_labels.append(label.strip())
        default = str(kwargs.get("default", ""))
        if label.strip() == "Provider":
            assert default == "anthropic"
            return default
        if label.strip() == "anthropic API key [leave blank to reuse detected value]":
            return ""
        if label.strip() == "anthropic base URL":
            return default
        if label.strip() == "Model":
            assert kwargs.get("default") == "anthropic/claude-3-5-haiku-latest"
            return str(kwargs.get("default", ""))
        raise AssertionError(f"unexpected prompt: {label}")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "anthropic",
            "family": "anthropic",
            "recommended_model": "anthropic/claude-3-5-haiku-latest",
            "recommended_models": ["anthropic/claude-3-5-haiku-latest"],
            "onboarding_hint": "Anthropic uses the native /v1/messages transport; confirm the ANTHROPIC_API_KEY value.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "hints": [],
        },
    )

    console = Console(record=True, width=140)
    provider, api_key, base_url, selected_model, probe, oauth_payload = onboarding_module._configure_model(
        console,
        cfg,
        allow_continue_on_probe_failure=True,
    )

    rendered = console.export_text()
    assert provider == "anthropic"
    assert api_key == "env-anthropic-key"
    assert base_url == "https://api.anthropic.com/v1"
    assert selected_model == "anthropic/claude-3-5-haiku-latest"
    assert probe["provider"] == "anthropic"
    assert oauth_payload == {"access_token": "", "account_id": "", "source": ""}
    assert "Suggested provider:" in rendered
    assert "ANTHROPIC_API_KEY" in rendered
    assert "API key found:" in rendered
    assert "anthropic API key [leave blank to reuse detected value]" in asked_labels


def test_configure_model_reuses_configured_provider_override_api_key(monkeypatch) -> None:
    cfg = AppConfig.from_dict(
        {
            "provider": {"model": "openai/gpt-4o-mini"},
            "providers": {"groq": {"api_key": "gsk_detected_123456"}},
        }
    )

    def _fake_prompt_ask(label: str, *args, **kwargs):
        default = str(kwargs.get("default", ""))
        if label.strip() == "Provider":
            assert default == "groq"
            return default
        if label.strip() == "groq API key [leave blank to reuse detected value]":
            return ""
        if label.strip() == "Model":
            assert kwargs.get("default") == "groq/llama-3.1-8b-instant"
            return str(kwargs.get("default", ""))
        raise AssertionError(f"unexpected prompt: {label}")

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "groq",
            "family": "openai_compatible",
            "recommended_model": "groq/llama-3.1-8b-instant",
            "recommended_models": ["groq/llama-3.1-8b-instant"],
            "onboarding_hint": "Groq responds via OpenAI-compatible endpoints; prefer low-latency models when possible.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "hints": [],
        },
    )

    console = Console(record=True, width=140)
    provider, api_key, base_url, selected_model, probe, oauth_payload = onboarding_module._configure_model(
        console,
        cfg,
        allow_continue_on_probe_failure=True,
    )

    rendered = console.export_text()
    assert provider == "groq"
    assert api_key == "gsk_detected_123456"
    assert base_url == "https://api.groq.com/openai/v1"
    assert selected_model == "groq/llama-3.1-8b-instant"
    assert probe["provider"] == "groq"
    assert oauth_payload == {"access_token": "", "account_id": "", "source": ""}
    assert "config:providers.groq.api_key" in rendered


def test_configure_model_defaults_provider_from_saved_oauth_credentials(monkeypatch) -> None:
    cfg = AppConfig.from_dict(
        {
            "provider": {"model": "openai/gpt-4o-mini"},
            "auth": {"providers": {"openai_codex": {"access_token": "codex-token-123456", "account_id": "org-1"}}},
        }
    )

    def _fake_prompt_ask(label: str, *args, **kwargs):
        default = str(kwargs.get("default", ""))
        if label.strip() == "Provider":
            assert default == "openai_codex"
            return default
        if label.strip() == "Model":
            assert kwargs.get("default") == "openai-codex/gpt-5.3-codex"
            return str(kwargs.get("default", ""))
        raise AssertionError(f"unexpected prompt: {label}")

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding._resolve_codex_auth_interactive",
        lambda config: {
            "configured": True,
            "access_token": "codex-token-123456",
            "account_id": "org-1",
            "source": "config",
            "token_masked": "********3456",
            "account_id_masked": "****org-1",
        },
    )
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "openai_codex",
            "family": "oauth",
            "recommended_model": "openai-codex/gpt-5.3-codex",
            "recommended_models": ["openai-codex/gpt-5.3-codex"],
            "onboarding_hint": "OpenAI Codex uses local OAuth; sign in before validating the provider.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "transport": "oauth_codex_responses",
            "probe_method": "POST",
            "hints": [],
        },
    )

    console = Console(record=True, width=140)
    provider, api_key, base_url, selected_model, probe, oauth_payload = onboarding_module._configure_model(
        console,
        cfg,
        allow_continue_on_probe_failure=True,
    )

    rendered = console.export_text()
    assert provider == "openai_codex"
    assert api_key == ""
    assert base_url == "https://chatgpt.com/backend-api"
    assert selected_model == "openai-codex/gpt-5.3-codex"
    assert probe["provider"] == "openai_codex"
    assert oauth_payload["access_token"] == "codex-token-123456"
    assert "Suggested provider:" in rendered
    assert "saved openai-codex OAuth credentials" in rendered


def test_configure_model_defaults_provider_from_single_oauth_env(monkeypatch) -> None:
    cfg = AppConfig.from_dict({"provider": {"model": "openai/gpt-4o-mini"}})

    def _fake_prompt_ask(label: str, *args, **kwargs):
        default = str(kwargs.get("default", ""))
        if label.strip() == "Provider":
            assert default == "gemini_oauth"
            return default
        if label.strip() == "Model":
            assert kwargs.get("default") == "gemini_oauth/gemini-2.0-flash"
            return str(kwargs.get("default", ""))
        raise AssertionError(f"unexpected prompt: {label}")

    monkeypatch.setenv("CLAWLITE_GEMINI_ACCESS_TOKEN", "gemini-token-123456")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "gemini_oauth",
            "family": "oauth",
            "recommended_model": "gemini_oauth/gemini-2.0-flash",
            "recommended_models": ["gemini_oauth/gemini-2.0-flash"],
            "onboarding_hint": "Gemini uses an OpenAI-compatible endpoint via Google Generative Language.",
            "base_url": base_url,
            "api_key_masked": "********3456",
            "error": "",
            "transport": "oauth_openai_compatible",
            "probe_method": "GET",
            "hints": [],
        },
    )

    console = Console(record=True, width=140)
    provider, api_key, base_url, selected_model, probe, oauth_payload = onboarding_module._configure_model(
        console,
        cfg,
        allow_continue_on_probe_failure=True,
    )

    rendered = console.export_text()
    assert provider == "gemini_oauth"
    assert api_key == ""
    assert base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert selected_model == "gemini_oauth/gemini-2.0-flash"
    assert probe["provider"] == "gemini_oauth"
    assert oauth_payload["access_token"] == "gemini-token-123456"
    assert oauth_payload["source"] == "env:CLAWLITE_GEMINI_ACCESS_TOKEN"
    assert "Suggested provider:" in rendered
    assert "CLAWLITE_GEMINI_ACCESS_TOKEN" in rendered


def test_configure_model_does_not_reuse_other_local_runtime_base_url(monkeypatch) -> None:
    cfg = AppConfig.from_dict(
        {
            "provider": {
                "model": "openai/gpt-4o-mini",
                "litellm_base_url": "http://localhost:11434",
            }
        }
    )

    def _fake_prompt_ask(label: str, *args, **kwargs):
        default = str(kwargs.get("default", ""))
        if label.strip() == "Provider":
            return "vllm"
        if label.strip() == "vllm base URL":
            assert default == "http://127.0.0.1:8000/v1"
            return default
        if label.strip() == "Model":
            assert default == "vllm/meta-llama/Llama-3.2-3B-Instruct"
            return default
        raise AssertionError(f"unexpected prompt: {label}")

    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", _fake_prompt_ask)
    monkeypatch.setattr(
        "clawlite.cli.onboarding.probe_provider",
        lambda provider, *, api_key, base_url, model="", timeout_s=8.0, oauth_access_token="", oauth_account_id="": {
            "ok": True,
            "status_code": 200,
            "provider": "vllm",
            "family": "local_runtime",
            "recommended_model": "vllm/meta-llama/Llama-3.2-3B-Instruct",
            "recommended_models": ["vllm/meta-llama/Llama-3.2-3B-Instruct"],
            "onboarding_hint": "vLLM requires a running server and a model loaded when the process starts.",
            "base_url": base_url,
            "api_key_masked": "",
            "error": "",
            "hints": [],
        },
    )

    console = Console(record=True, width=140)
    provider, api_key, base_url, selected_model, probe, oauth_payload = onboarding_module._configure_model(
        console,
        cfg,
        allow_continue_on_probe_failure=True,
    )

    assert provider == "vllm"
    assert api_key == ""
    assert base_url == "http://127.0.0.1:8000/v1"
    assert selected_model == "vllm/meta-llama/Llama-3.2-3B-Instruct"
    assert probe["provider"] == "vllm"
    assert oauth_payload == {"access_token": "", "account_id": "", "source": ""}
