from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".clawlite"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "model": "openai/gpt-4o-mini",
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


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
