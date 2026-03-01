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
            "accounts": [
                {"account": "dev-bot", "token": "<TOKEN_1>"},
                {"account": "docs-bot", "token": "<TOKEN_2>"}
            ],
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
                "accounts": [{"account": "guild-main", "token": "<TOKEN>"}],
                "allowFrom": ["<DISCORD_USER_ID>"],
                "allowChannels": ["<DISCORD_CHANNEL_ID>"]
            }
        }
    },
    "slack": {
        "channels": {
            "slack": {
                "enabled": True,
                "token": "<SLACK_BOT_TOKEN>",
                "app_token": "<SLACK_APP_TOKEN>",
                "accounts": [
                    {
                        "account": "workspace-main",
                        "token": "<SLACK_BOT_TOKEN>",
                        "app_token": "<SLACK_APP_TOKEN>"
                    }
                ]
            }
        }
    },
    "whatsapp": {
        "channels": {
            "whatsapp": {
                "enabled": True,
                "accounts": [{"account": "wa-main", "token": "<TOKEN>"}],
                "allowFrom": ["+5511999999999"],
                "stt_enabled": True,
                "tts_enabled": False,
                "stt_model": "base",
                "stt_language": "pt",
                "tts_provider": "local"
            }
        }
    },
    "googlechat": {
        "channels": {
            "googlechat": {
                "enabled": True,
                "serviceAccountFile": "/path/to/service-account.json",
                "botUser": "users/1234567890",
                "requireMention": True,
                "allowFrom": ["users/1234567890"],
                "allowChannels": ["spaces/AAAA"],
                "dm": {"policy": "pairing", "allowFrom": ["users/1234567890"]},
            }
        }
    },
    "irc": {
        "channels": {
            "irc": {
                "enabled": True,
                "host": "irc.libera.chat",
                "port": 6697,
                "tls": True,
                "nick": "clawlite-bot",
                "channels": ["#clawlite"],
                "requireMention": True,
                "allowFrom": ["*"],
                "relay_url": "http://127.0.0.1:8899/irc/send"
            }
        }
    },
    "signal": {
        "channels": {
            "signal": {
                "enabled": True,
                "account": "+15551234567",
                "cliPath": "signal-cli",
                "allowFrom": ["+15557654321"]
            }
        }
    },
    "imessage": {
        "channels": {
            "imessage": {
                "enabled": True,
                "cliPath": "imsg",
                "service": "auto",
                "allowFrom": ["chat_id:*"]
            }
        }
    },
    "teams": {
        "channels": {
            "teams": {
                "enabled": True,
                "token": "<TEAMS_BOT_TOKEN>",
                "accounts": [{"account": "tenant-main", "token": "<TOKEN>"}]
            }
        }
    },
}


def channel_template(name: str) -> str:
    key = name.lower()
    if key not in TEMPLATES:
        raise ValueError(f"Canal não suportado: {name}")
    return json.dumps(TEMPLATES[key], ensure_ascii=False, indent=2)
