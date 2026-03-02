from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import clawlite.auth as auth
from clawlite.config import settings


def _patch_config_home(tmpdir: str):
    old_dir = settings.CONFIG_DIR
    old_path = settings.CONFIG_PATH
    settings.CONFIG_DIR = Path(tmpdir) / "cfg"
    settings.CONFIG_PATH = settings.CONFIG_DIR / "config.json"
    return old_dir, old_path


def test_read_codex_cli_access_token_from_auth_json(monkeypatch, tmp_path: Path):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_json = codex_home / "auth.json"
    auth_json.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": "codex-access-token-123",
                    "refresh_token": "codex-refresh-token-123",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    assert auth._read_codex_cli_access_token() == "codex-access-token-123"


def test_auth_login_openai_codex_reuses_cli_token(monkeypatch, tmp_path: Path):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "account_id": "acc-xyz",
                "tokens": {
                    "access_token": "codex-access-token-xyz",
                    "refresh_token": "codex-refresh-token-xyz",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(auth.webbrowser, "open", lambda *_args, **_kwargs: True)

    old_dir, old_path = _patch_config_home(str(tmp_path))
    try:
        settings.save_config(settings.DEFAULT_CONFIG)
        ok, msg = auth.auth_login("openai-codex")
        cfg = settings.load_config()
    finally:
        settings.CONFIG_DIR = old_dir
        settings.CONFIG_PATH = old_path

    assert ok is True
    assert "OpenAI Codex" in msg
    assert (
        cfg.get("auth", {})
        .get("providers", {})
        .get("openai-codex", {})
        .get("token", "")
        == "codex-access-token-xyz"
    )
    assert (
        cfg.get("auth", {})
        .get("providers", {})
        .get("openai-codex", {})
        .get("account_id", "")
        == "acc-xyz"
    )


def test_run_codex_cli_oauth_login_uses_codex_binary(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run(cmd):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(auth.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(auth.subprocess, "run", _fake_run)
    monkeypatch.setattr(auth, "_read_codex_cli_access_token", lambda: "oauth-from-codex-cli")

    token = auth._run_codex_cli_oauth_login()
    assert token == "oauth-from-codex-cli"
    assert calls and calls[0] == ["codex", "login"]


def test_auth_login_openai_codex_runs_cli_oauth_when_needed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(auth, "_read_codex_cli_access_token", lambda: "")
    monkeypatch.setattr(auth, "_can_prompt_user", lambda: True)
    monkeypatch.setattr(auth.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(auth, "_run_codex_cli_oauth_login", lambda: "oauth-token-imported")

    old_dir, old_path = _patch_config_home(str(tmp_path))
    try:
        settings.save_config(settings.DEFAULT_CONFIG)
        ok, _msg = auth.auth_login("openai-codex")
        cfg = settings.load_config()
    finally:
        settings.CONFIG_DIR = old_dir
        settings.CONFIG_PATH = old_path

    assert ok is True
    assert (
        cfg.get("auth", {})
        .get("providers", {})
        .get("openai-codex", {})
        .get("token", "")
        == "oauth-token-imported"
    )
