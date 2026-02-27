from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".clawlite"
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
    },
    "channels": {
        "telegram": {"enabled": False},
        "discord": {"enabled": False},
    },
    "skills": ["core-tools", "memory", "gateway"],
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
