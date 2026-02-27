from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawlite.runtime.multiagent import enqueue_task


TELEGRAM_MULTIAGENT_TEMPLATE = {
    "telegram": {
        "enabled": True,
        "token": "<TELEGRAM_BOT_TOKEN>",
        "defaultLabel": "general",
        "routing": {
            "general": {
                "commandTemplate": "clawlite run \"{text}\""
            },
            "code": {
                "commandTemplate": "clawlite run \"[code] {text}\""
            }
        }
    }
}


def template_json() -> str:
    return json.dumps(TELEGRAM_MULTIAGENT_TEMPLATE, ensure_ascii=False, indent=2)


def load_config(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "telegram" not in data:
        raise ValueError("config inválida: falta bloco telegram")
    return data


def dispatch_local(config_path: str, chat_id: str, text: str, thread_id: str = "", label: str | None = None) -> int:
    cfg = load_config(config_path)
    tcfg = cfg["telegram"]
    selected_label = label or tcfg.get("defaultLabel", "general")
    payload = {
        "channel": "telegram",
        "chat_id": chat_id,
        "thread_id": thread_id,
        "label": selected_label,
        "text": text,
    }
    return enqueue_task("telegram", chat_id, thread_id, selected_label, payload)
