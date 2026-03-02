from __future__ import annotations

import json
from pathlib import Path

from clawlite.core.codex_auth import (
    is_codex_api_key,
    read_codex_account_id,
    read_codex_cli_access_token,
    resolve_codex_account_id,
)


def _write_auth_json(tmp_path: Path, payload: dict) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "auth.json").write_text(json.dumps(payload), encoding="utf-8")


def test_read_codex_cli_access_token(monkeypatch, tmp_path: Path) -> None:
    _write_auth_json(
        tmp_path,
        {"tokens": {"access_token": "oauth-access-123", "refresh_token": "refresh-123"}},
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    assert read_codex_cli_access_token() == "oauth-access-123"


def test_read_codex_account_id_from_root(monkeypatch, tmp_path: Path) -> None:
    _write_auth_json(
        tmp_path,
        {"account_id": "acc_root_123", "tokens": {"access_token": "oauth-access-123"}},
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    assert read_codex_account_id() == "acc_root_123"


def test_read_codex_account_id_from_accounts_dict(monkeypatch, tmp_path: Path) -> None:
    _write_auth_json(
        tmp_path,
        {
            "tokens": {"access_token": "oauth-access-123"},
            "accounts": {"default": {"id": "acc_from_accounts"}},
        },
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    assert read_codex_account_id() == "acc_from_accounts"


def test_resolve_codex_account_id_prefers_env(monkeypatch, tmp_path: Path) -> None:
    _write_auth_json(
        tmp_path,
        {"account_id": "acc_from_file", "tokens": {"access_token": "oauth-access-123"}},
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    monkeypatch.setenv("OPENAI_CODEX_ACCOUNT_ID", "acc_from_env")
    assert resolve_codex_account_id() == "acc_from_env"


def test_is_codex_api_key_detection() -> None:
    assert is_codex_api_key("sk-proj-123")
    assert not is_codex_api_key("oauth-access-token")
