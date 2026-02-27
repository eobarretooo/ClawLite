from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawlite.runtime.multiagent import enqueue_task
from clawlite.runtime.voice import clean_audio_flags, inbound_to_prompt, wants_audio_reply


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
    reply_in_audio = wants_audio_reply(text, tcfg)
    payload = {
        "channel": "telegram",
        "chat_id": chat_id,
        "thread_id": thread_id,
        "label": selected_label,
        "text": clean_audio_flags(text),
        "reply_in_audio": reply_in_audio,
        "channel_cfg": tcfg,
    }
    return enqueue_task("telegram", chat_id, thread_id, selected_label, payload)


def dispatch_telegram_update(config_path: str, update: dict[str, Any], label: str | None = None) -> int:
    """Converte update Telegram (texto/voice) em task para pipeline multiagente."""
    cfg = load_config(config_path)
    tcfg = cfg["telegram"]
    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        raise ValueError("update sem chat_id")

    thread_id = str(msg.get("message_thread_id") or "")
    selected_label = label or tcfg.get("defaultLabel", "general")

    prompt, meta = inbound_to_prompt("telegram", update, tcfg)
    reply_in_audio = wants_audio_reply(prompt, tcfg)
    payload = {
        "channel": "telegram",
        "chat_id": chat_id,
        "thread_id": thread_id,
        "label": selected_label,
        "text": clean_audio_flags(prompt),
        "voice_meta": meta,
        "reply_in_audio": reply_in_audio,
        "channel_cfg": tcfg,
    }
    return enqueue_task("telegram", chat_id, thread_id, selected_label, payload)
