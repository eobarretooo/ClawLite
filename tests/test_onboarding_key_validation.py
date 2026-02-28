from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from clawlite.onboarding import (
    _build_readiness_checks,
    _ensure_gateway_token_if_required,
    _get_stored_token,
    _provider_from_model,
    _readiness_score,
    _show_completion_panel,
    _test_api_key,
    _write_onboarding_report,
)


# ---------------------------------------------------------------------------
# _provider_from_model
# ---------------------------------------------------------------------------

def test_provider_from_anthropic():
    assert _provider_from_model("anthropic/claude-haiku-4-5-20251001") == "anthropic"


def test_provider_from_openai():
    assert _provider_from_model("openai/gpt-4o-mini") == "openai"


def test_provider_from_groq():
    assert _provider_from_model("groq/llama3") == "groq"


def test_provider_from_ollama():
    assert _provider_from_model("ollama/llama3.1:8b") == "ollama"


def test_provider_from_google_alias():
    assert _provider_from_model("google/gemini-2.5-flash") == "gemini"


def test_provider_no_slash():
    assert _provider_from_model("openai") == "openai"


# ---------------------------------------------------------------------------
# _get_stored_token
# ---------------------------------------------------------------------------

def test_get_token_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert _get_stored_token({}, "anthropic") == "sk-ant-test"


def test_get_token_from_cfg():
    cfg = {"auth": {"providers": {"openai": {"token": "sk-openai-abc"}}}}
    assert _get_stored_token(cfg, "openai") == "sk-openai-abc"


def test_get_token_empty():
    assert _get_stored_token({}, "anthropic") == ""


def test_get_token_from_google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "g-google-env")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert _get_stored_token({}, "gemini") == "g-google-env"


# ---------------------------------------------------------------------------
# _test_api_key - mocking httpx
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    return r


def test_anthropic_valid_key():
    with patch("httpx.post", return_value=_mock_response(200)):
        ok, msg = _test_api_key("anthropic", "sk-ant-valid")
    assert ok is True
    assert "key" in msg.lower() or "ok" in msg.lower()


def test_anthropic_invalid_key_401():
    with patch("httpx.post", return_value=_mock_response(401, "unauthorized")):
        ok, msg = _test_api_key("anthropic", "sk-ant-bad")
    assert ok is False
    assert "401" in msg


def test_openai_valid_key():
    with patch("httpx.post", return_value=_mock_response(200)):
        ok, msg = _test_api_key("openai", "sk-openai-ok")
    assert ok is True


def test_openai_invalid_key_401():
    with patch("httpx.post", return_value=_mock_response(401)):
        ok, msg = _test_api_key("openai", "sk-bad")
    assert ok is False
    assert "401" in msg


def test_rate_limit_429_treated_as_valid():
    with patch("httpx.post", return_value=_mock_response(429)):
        ok, msg = _test_api_key("anthropic", "sk-ant-quota")
    assert ok is True
    assert "429" in msg or "rate" in msg.lower()


def test_connection_error():
    import httpx as _httpx

    with patch("httpx.post", side_effect=_httpx.ConnectError("connection refused")):
        ok, msg = _test_api_key("openai", "sk-x")
    assert ok is False
    assert "conexao" in msg.lower() or "conexÃ£o" in msg.lower() or "connect" in msg.lower()


def test_ollama_reachable():
    with patch("httpx.get", return_value=_mock_response(200, '{"models":[]}')):
        ok, msg = _test_api_key("ollama", "")
    assert ok is True


def test_ollama_not_reachable():
    with patch("httpx.get", return_value=_mock_response(404)):
        ok, msg = _test_api_key("ollama", "")
    assert ok is False


def test_groq_valid():
    with patch("httpx.post", return_value=_mock_response(200)):
        ok, msg = _test_api_key("groq", "gsk-valid")
    assert ok is True


def test_minimax_valid():
    with patch("httpx.post", return_value=_mock_response(200)):
        ok, _msg = _test_api_key("minimax", "mm-valid")
    assert ok is True


def test_litellm_token_optional():
    with patch("httpx.post", return_value=_mock_response(200)):
        ok, _msg = _test_api_key("litellm", "")
    assert ok is True


def test_unknown_status_500():
    with patch("httpx.post", return_value=_mock_response(500, "server error")):
        ok, msg = _test_api_key("anthropic", "sk-ant-x")
    assert ok is False
    assert "500" in msg


# ---------------------------------------------------------------------------
# _show_completion_panel - smoke
# ---------------------------------------------------------------------------

def test_show_completion_panel_minimal(capsys):
    cfg = {
        "gateway": {"host": "0.0.0.0", "port": 8787, "token": "tok-abc123"},
        "channels": {},
    }
    _show_completion_panel(cfg)
    out = capsys.readouterr().out
    assert "8787" in out or "ClawLite" in out


def test_show_completion_panel_with_telegram_token(capsys):
    cfg = {
        "gateway": {"host": "127.0.0.1", "port": 8787, "token": "tok-xyz"},
        "channels": {
            "telegram": {"enabled": True, "token": "fake-tg-token"}
        },
    }
    with patch("clawlite.onboarding._test_telegram", return_value=(True, "Telegram conectado (@meubot)")):
        _show_completion_panel(cfg)
    out = capsys.readouterr().out
    assert "meubot" in out or "8787" in out


def test_show_completion_panel_no_token(capsys):
    cfg = {"gateway": {}, "channels": {}}
    _show_completion_panel(cfg)
    out = capsys.readouterr().out
    assert "clawlite start" in out or "gerado" in out


# ---------------------------------------------------------------------------
# Readiness / report
# ---------------------------------------------------------------------------

def test_ensure_gateway_token_generated_when_required():
    cfg = {"security": {"require_gateway_token": True}, "gateway": {"token": ""}}
    changed = _ensure_gateway_token_if_required(cfg)
    assert changed is True
    assert isinstance(cfg["gateway"]["token"], str)
    assert len(cfg["gateway"]["token"]) >= 16


def test_ensure_gateway_token_not_generated_when_not_required():
    cfg = {"security": {"require_gateway_token": False}, "gateway": {"token": ""}}
    changed = _ensure_gateway_token_if_required(cfg)
    assert changed is False
    assert cfg["gateway"]["token"] == ""


def test_readiness_score_calculation():
    checks = [
        {"name": "A", "ok": "true", "detail": "ok"},
        {"name": "B", "ok": "false", "detail": "warn"},
        {"name": "C", "ok": "true", "detail": "ok"},
        {"name": "D", "ok": "true", "detail": "ok"},
    ]
    assert _readiness_score(checks) == 75


def test_write_onboarding_report_creates_file(monkeypatch, tmp_path: Path):
    import clawlite.onboarding as onboarding

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(onboarding, "init_workspace", lambda: str(workspace))

    cfg = {"model": "openai/gpt-4o-mini", "language": "pt-br"}
    checks = [{"name": "Doctor Healthcheck", "ok": "true", "detail": "No doctor warnings"}]
    channel_tests = ["✅ Telegram conectado (@bot)"]

    report = _write_onboarding_report(cfg, checks, channel_tests)
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "ONBOARDING REPORT" in text
    assert "Readiness score" in text
    assert "Doctor Healthcheck" in text


def test_build_readiness_checks_happy_path(monkeypatch, tmp_path: Path):
    import clawlite.onboarding as onboarding

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    for name in ("AGENTS.md", "SOUL.md", "USER.md", "IDENTITY.md", "MEMORY.md"):
        (workspace / name).write_text("# ok\n", encoding="utf-8")

    monkeypatch.setattr(onboarding, "init_workspace", lambda: str(workspace))
    monkeypatch.setattr(onboarding, "run_doctor", lambda: "warnings: none ✅")

    cfg = {
        "model": "openai/gpt-4o-mini",
        "auth": {"providers": {"openai": {"token": "sk-openai-test"}}},
        "gateway": {"host": "127.0.0.1", "port": 8787, "token": "tok-abc"},
        "security": {"require_gateway_token": True, "redact_tokens_in_logs": True},
        "channels": {"telegram": {"enabled": True, "token": "tg-token"}},
        "skills": ["web-search", "web-fetch", "coding-agent"],
    }
    checks = _build_readiness_checks(cfg, ["✅ Telegram conectado (@bot)"])
    names = {c["name"] for c in checks}
    assert "Model Catalog" in names
    assert "Doctor Healthcheck" in names
    assert _readiness_score(checks) >= 80
