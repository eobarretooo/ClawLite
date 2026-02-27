from __future__ import annotations

import json

TEMPLATES = {
    "telegram": {
        "channels": {
            "telegram": {
                "enabled": True,
                "token": "<TELEGRAM_BOT_TOKEN>",
                "allowFrom": ["<TELEGRAM_USER_ID>"],
                "stt_enabled": True,
                "tts_enabled": False,
                "stt_model": "base",
                "stt_language": "pt",
                "tts_provider": "local"
            }
        }
    },
    "telegram-multiagent": {
        "telegram": {
            "enabled": True,
            "token": "<TELEGRAM_BOT_TOKEN>",
            "defaultLabel": "general",
            "routing": {
                "general": {"commandTemplate": "clawlite run \"{text}\""},
                "code": {"commandTemplate": "clawlite run \"[code] {text}\""}
            }
        }
    },
    "discord": {
        "channels": {
            "discord": {
                "enabled": True,
                "token": "<DISCORD_BOT_TOKEN>",
                "allowFrom": ["<DISCORD_USER_ID>"]
            }
        }
    },
    "whatsapp": {
        "channels": {
            "whatsapp": {
                "enabled": True,
                "allowFrom": ["+5511999999999"],
                "stt_enabled": True,
                "tts_enabled": False,
                "stt_model": "base",
                "stt_language": "pt",
                "tts_provider": "local"
            }
        }
    },
}


def channel_template(name: str) -> str:
    key = name.lower()
    if key not in TEMPLATES:
        raise ValueError(f"Canal não suportado: {name}")
    return json.dumps(TEMPLATES[key], ensure_ascii=False, indent=2)
