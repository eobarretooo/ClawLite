from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _can_write_under(path: Path) -> bool:
    probe_dir = path / ".clawlite"
    probe_file = probe_dir / ".write_probe"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        return True
    except OSError:
        return False


def _resolve_home_dir() -> Path:
    """
    Resolve home directory consistently across OSes and test environments.

    Priority:
    1) CLAWLITE_HOME
    2) HOME
    3) platform default (Path.home())
    """
    for env_name in ("CLAWLITE_HOME", "HOME"):
        value = os.getenv(env_name, "").strip()
        if value:
            return Path(value).expanduser()
    home = Path.home()
    if _can_write_under(home):
        return home
    temp_home = Path(tempfile.gettempdir()) / "clawlite-home"
    if _can_write_under(temp_home):
        return temp_home
    return Path.cwd()


CONFIG_DIR = _resolve_home_dir() / ".clawlite"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "model": "openai/gpt-4o-mini",
    "model_fallback": ["openrouter/auto", "ollama/llama3.1:8b"],
    "offline_mode": {
        "enabled": True,
        "auto_fallback_to_ollama": True,
        "connectivity_timeout_sec": 1.5,
    },
    "ollama": {
        "model": "llama3.1:8b",
    },
    "battery_mode": {
        "enabled": False,
        "throttle_seconds": 6.0,
    },
    "notifications": {
        "enabled": True,
        "dedupe_window_seconds": 300,
    },
    "gateway": {
        "host": "0.0.0.0",
        "port": 8787,
        "token": "",
        "dashboard_enabled": True,
    },
    "update": {
        "channel": "stable",
        "check_on_start": True,
    },
    "channels": {
        "telegram": {
            "enabled": False,
            "token": "",
            "chat_id": "",
            "accounts": [],
            "allowFrom": [],
            "stt_enabled": False,
            "stt_model": "base",
            "stt_language": "pt",
            "tts_enabled": False,
            "tts_provider": "local",
            "tts_model": "gpt-4o-mini-tts",
            "tts_voice": "alloy",
            "tts_default_reply": False,
        },
        "whatsapp": {
            "enabled": False,
            "token": "",
            "phone": "",
            "accounts": [],
            "allowFrom": [],
            "stt_enabled": False,
            "stt_model": "base",
            "stt_language": "pt",
            "tts_enabled": False,
            "tts_provider": "local",
            "tts_model": "gpt-4o-mini-tts",
            "tts_voice": "alloy",
            "tts_default_reply": False,
        },
        "discord": {"enabled": False, "token": "", "guild_id": "", "accounts": [], "allowFrom": [], "allowChannels": []},
        "slack": {
            "enabled": False,
            "token": "",
            "workspace": "",
            "app_token": "",
            "accounts": [],
            "allowFrom": [],
            "allowChannels": [],
        },
        "googlechat": {
            "enabled": False,
            "token": "",
            "botUser": "",
            "requireMention": True,
            "allowFrom": [],
            "allowChannels": [],
            "serviceAccountFile": "",
            "webhookPath": "/api/webhooks/googlechat",
            "dm": {"policy": "pairing", "allowFrom": []},
        },
        "irc": {
            "enabled": False,
            "token": "",
            "host": "",
            "port": 6697,
            "tls": True,
            "nick": "clawlite-bot",
            "channels": [],
            "allowFrom": [],
            "allowChannels": [],
            "requireMention": True,
            "relay_url": "",
        },
        "signal": {
            "enabled": False,
            "token": "",
            "account": "",
            "cliPath": "signal-cli",
            "httpUrl": "",
            "allowFrom": [],
        },
        "imessage": {
            "enabled": False,
            "token": "",
            "cliPath": "imsg",
            "service": "auto",
            "allowFrom": [],
        },
        "teams": {"enabled": False, "token": "", "tenant": "", "accounts": []},
    },
    "hooks": {
        "boot": True,
        "session_memory": True,
        "command_logger": False,
    },
    "web_tools": {
        "web_search": {"enabled": True, "provider": "brave"},
        "reddit": {"enabled": False, "subreddits": ["selfhosted", "Python"]},
        "threads": {"enabled": False, "username": ""},
    },
    "language": "pt-br",
    "security": {
        "allow_shell_exec": True,
        "redact_tokens_in_logs": True,
        "require_gateway_token": True,
        "pairing": {
            "enabled": False,
            "code_ttl_seconds": 86400,
        },
        "rbac": {
            "viewer_tokens": [],
        },
        "tool_policies": {},
    },
    "skills": ["core-tools", "memory", "gateway"],
    "reddit": {
        "enabled": False,
        "client_id": "",
        "client_secret": "",
        "redirect_uri": "http://127.0.0.1:8788/reddit/callback",
        "refresh_token": "",
        "subreddits": ["selfhosted", "Python", "AIAssistants", "termux"],
        "notify_chat_id": ""
    },
}


def _clone_defaults() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_CONFIG))


def _merge_defaults(defaults: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    merged = _clone_defaults()

    def _merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                _merge(dst[key], value)
            else:
                dst[key] = value

    _merge(merged, loaded)
    return merged


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return _clone_defaults()
    loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return _clone_defaults()
    return _merge_defaults(DEFAULT_CONFIG, loaded)


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
