from __future__ import annotations

import json
import secrets
from typing import Any

import questionary
from questionary import Choice

from clawlite.auth import PROVIDERS, auth_login
from clawlite.config.settings import load_config, save_config
from clawlite.skills.registry import SKILLS


def _preview(cfg: dict[str, Any]) -> str:
    return json.dumps(cfg, ensure_ascii=False, indent=2)


def run_configure_menu() -> None:
    cfg = load_config()
    cfg.setdefault("channels", {"telegram": {"enabled": False}, "discord": {"enabled": False}})
    cfg.setdefault("gateway", {"host": "0.0.0.0", "port": 8787, "token": ""})
    cfg.setdefault("security", {"allow_shell_exec": True, "redact_tokens_in_logs": True})
    cfg.setdefault("web_tools", {"enabled": True})

    sections = ["🤖 Model", "📡 Channels", "🧩 Skills", "🌐 Gateway", "🔒 Security", "🕸️ Web Tools", "👀 Preview & Save", "❌ Exit"]

    while True:
        section = questionary.select("ClawLite Configure", choices=sections, use_shortcuts=True).ask()
        if section == "🤖 Model":
            cfg["model"] = questionary.text("Default model", default=cfg.get("model", "openai/gpt-4o-mini")).ask()
            first = questionary.select("Authenticate provider now?", choices=["skip"] + list(PROVIDERS.keys())).ask()
            if first and first != "skip":
                auth_login(first)

        elif section == "📡 Channels":
            ch = questionary.checkbox(
                "Enabled channels",
                choices=[
                    Choice("Telegram", checked=cfg.get("channels", {}).get("telegram", {}).get("enabled", False)),
                    Choice("Discord", checked=cfg.get("channels", {}).get("discord", {}).get("enabled", False)),
                ],
            ).ask() or []
            cfg["channels"]["telegram"]["enabled"] = "Telegram" in ch
            cfg["channels"]["discord"]["enabled"] = "Discord" in ch

        elif section == "🧩 Skills":
            enabled = set(cfg.get("skills", []))
            choices = [Choice(s, checked=(s in enabled)) for s in sorted(SKILLS.keys())]
            picked = questionary.checkbox("Select active skills", choices=choices).ask() or []
            cfg["skills"] = picked

        elif section == "🌐 Gateway":
            cfg["gateway"]["host"] = questionary.text("Gateway host", default=str(cfg["gateway"].get("host", "0.0.0.0"))).ask()
            cfg["gateway"]["port"] = int(questionary.text("Gateway port", default=str(cfg["gateway"].get("port", 8787))).ask())
            tok = questionary.text("Gateway token (blank = generate)", default=str(cfg["gateway"].get("token", ""))).ask().strip()
            cfg["gateway"]["token"] = tok or secrets.token_urlsafe(24)

        elif section == "🔒 Security":
            security = questionary.checkbox(
                "Security toggles",
                choices=[
                    Choice("Allow shell exec", checked=cfg["security"].get("allow_shell_exec", True)),
                    Choice("Redact tokens in logs", checked=cfg["security"].get("redact_tokens_in_logs", True)),
                ],
            ).ask() or []
            cfg["security"]["allow_shell_exec"] = "Allow shell exec" in security
            cfg["security"]["redact_tokens_in_logs"] = "Redact tokens in logs" in security

        elif section == "🕸️ Web Tools":
            enabled = questionary.confirm("Enable web tools?", default=cfg.get("web_tools", {}).get("enabled", True)).ask()
            cfg["web_tools"]["enabled"] = bool(enabled)

        elif section == "👀 Preview & Save":
            print("\n=== Preview ===")
            print(_preview(cfg))
            if questionary.confirm("Save configuration?", default=True).ask():
                save_config(cfg)
                print("✅ Configuration saved.")
                return

        elif section in ("❌ Exit", None):
            print("Exit without saving.")
            return
