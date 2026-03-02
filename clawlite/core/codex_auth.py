from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def resolve_codex_auth_path() -> Path:
    codex_home = os.getenv("CODEX_HOME", "").strip()
    if codex_home:
        return Path(codex_home).expanduser() / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def read_codex_auth_json() -> dict[str, Any]:
    auth_path = resolve_codex_auth_path()
    if not auth_path.exists():
        return {}
    try:
        raw = json.loads(auth_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def read_codex_cli_access_token() -> str:
    raw = read_codex_auth_json()
    tokens = raw.get("tokens", {})
    if isinstance(tokens, dict):
        value = str(tokens.get("access_token", "")).strip()
        if value:
            return value
    return str(raw.get("access_token", "")).strip()


def _from_candidate(candidate: Any) -> str:
    if isinstance(candidate, dict):
        for key in ("account_id", "accountId", "id"):
            value = str(candidate.get(key, "")).strip()
            if value:
                return value
    return ""


def read_codex_account_id() -> str:
    raw = read_codex_auth_json()

    # Common layouts.
    direct = _from_candidate(raw)
    if direct:
        return direct
    token_level = _from_candidate(raw.get("tokens"))
    if token_level:
        return token_level
    account_obj = _from_candidate(raw.get("account"))
    if account_obj:
        return account_obj

    accounts = raw.get("accounts")
    if isinstance(accounts, dict):
        for value in accounts.values():
            found = _from_candidate(value)
            if found:
                return found
    if isinstance(accounts, list):
        for value in accounts:
            found = _from_candidate(value)
            if found:
                return found
    return ""


def is_codex_api_key(token: str) -> bool:
    value = str(token or "").strip()
    # OpenAI API keys (inclui projeto) começam com "sk-".
    return value.startswith("sk-")


def resolve_codex_account_id(preferred: str = "") -> str:
    preferred_value = str(preferred or "").strip()
    if preferred_value:
        return preferred_value
    for env_name in ("OPENAI_CODEX_ACCOUNT_ID", "CHATGPT_ACCOUNT_ID"):
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            return env_value
    return read_codex_account_id()
