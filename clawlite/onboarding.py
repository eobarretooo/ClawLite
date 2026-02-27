from __future__ import annotations

import secrets

import questionary

from clawlite.auth import PROVIDERS, auth_login
from clawlite.config.settings import load_config, save_config


MASCOT = r'''
┌───────────────────────────────┐
│      /\_/\    ClawLite        │
│     ( =^.^= )  initialized    │
│     /  _  \   swift • smart   │
│    (__/ \__)  terminal-ready  │
└───────────────────────────────┘
'''


def run_onboarding() -> None:
    cfg = load_config()
    print("\n" + MASCOT)
    print("=== ClawLite Onboarding ===")

    model = questionary.text("Modelo padrão", default=cfg.get("model", "openai/gpt-4o-mini")).ask()
    if model:
        cfg["model"] = model

    first = questionary.select("Escolha o primeiro provedor para autenticar", choices=list(PROVIDERS.keys()) + ["pular"]).ask()
    if first and first != "pular":
        auth_login(first)

    tg = questionary.confirm("Ativar canal Telegram?", default=cfg.get("channels",{}).get("telegram",{}).get("enabled", False)).ask()
    ds = questionary.confirm("Ativar canal Discord?", default=cfg.get("channels",{}).get("discord",{}).get("enabled", False)).ask()
    cfg.setdefault("channels", {})["telegram"] = {"enabled": bool(tg)}
    cfg.setdefault("channels", {})["discord"] = {"enabled": bool(ds)}

    token = questionary.text("Token do gateway (enter para gerar)", default=cfg.get("gateway",{}).get("token", "")).ask().strip()
    if not token:
        token = secrets.token_urlsafe(24)
    cfg.setdefault("gateway", {})["token"] = token

    save_config(cfg)
    print("\n✅ Onboarding concluído.")
    print("Config salva em ~/.clawlite/config.json")
