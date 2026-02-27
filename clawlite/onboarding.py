from __future__ import annotations

import secrets

from clawlite.config.settings import load_config, save_config


def run_onboarding() -> None:
    cfg = load_config()
    print("\n=== ClawLite Onboarding ===")

    model = input(f"Modelo padrão [{cfg.get('model','openai/gpt-4o-mini')}]: ").strip()
    if model:
        cfg["model"] = model

    tg = input("Ativar canal Telegram? (y/N): ").strip().lower() == "y"
    ds = input("Ativar canal Discord? (y/N): ").strip().lower() == "y"
    cfg.setdefault("channels", {})["telegram"] = {"enabled": tg}
    cfg.setdefault("channels", {})["discord"] = {"enabled": ds}

    token = input("Token do gateway (enter para gerar automático): ").strip()
    if not token:
        token = secrets.token_urlsafe(24)
    cfg.setdefault("gateway", {})["token"] = token

    save_config(cfg)
    print("\n✅ Onboarding concluído.")
    print("Config salva em ~/.clawlite/config.json")
