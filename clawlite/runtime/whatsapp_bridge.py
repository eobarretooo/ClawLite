from __future__ import annotations

from typing import Any

from clawlite.runtime.multiagent import enqueue_task
from clawlite.runtime.voice import clean_audio_flags, inbound_to_prompt, wants_audio_reply


def dispatch_whatsapp_payload(config: dict[str, Any], payload: dict[str, Any], label: str = "general") -> int:
    """Integra payload WhatsApp atual ao pipeline de tasks.

    Espera `payload` com `from` (telefone), `text` e/ou `media_url`/`audio_url`.
    """
    wcfg = config.get("channels", {}).get("whatsapp", {})
    chat_id = str(payload.get("from") or payload.get("chat_id") or "")
    if not chat_id:
        raise ValueError("payload WhatsApp sem identificador do remetente")

    prompt, meta = inbound_to_prompt("whatsapp", payload, wcfg)
    task_payload = {
        "channel": "whatsapp",
        "chat_id": chat_id,
        "thread_id": "",
        "label": label,
        "text": clean_audio_flags(prompt),
        "voice_meta": meta,
        "reply_in_audio": wants_audio_reply(prompt, wcfg),
        "channel_cfg": wcfg,
    }
    return enqueue_task("whatsapp", chat_id, "", label, task_payload)
