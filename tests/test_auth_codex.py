from __future__ import annotations

import json
import tempfile
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
