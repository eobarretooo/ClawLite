from __future__ import annotations

import json
import secrets

import questionary
from questionary import Choice
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from clawlite.auth import PROVIDERS, auth_login
from clawlite.config.settings import load_config, save_config

console = Console()

MASCOT = r'''
┌───────────────────────────────────────┐
│      /\_/\       ClawLite            │
│    (=^･ω･^=)   pronto pra te ajudar  │
│    /  づ づ      rápido • portátil     │
└───────────────────────────────────────┘
'''


def _validate_required(label: str):
    def _inner(value: str) -> bool | str:
        if value is None or not str(value).strip():
            return f"⚠️ {label} é obrigatório."
        return True

    return _inner


def _validate_port(value: str) -> bool | str:
    v = (value or "").strip()
    if not v:
        return "⚠️ Porta é obrigatória."
    if not v.isdigit():
        return "⚠️ Porta precisa ser numérica (ex.: 8787)."
    port = int(v)
    if not (1 <= port <= 65535):
        return "⚠️ Porta fora do intervalo válido (1-65535)."
    return True


def _progress(step: int, total: int = 5) -> None:
    pct = int((step / total) * 100)
    bar_width = 20
    fill = int((step / total) * bar_width)
    bar = "🟩" * fill + "⬜" * (bar_width - fill)
    console.print(f"[bold cyan]Etapa {step}/{total}[/bold cyan] {bar} {pct}%")


def run_onboarding() -> None:
    cfg = load_config()
    cfg.setdefault("channels", {"telegram": {"enabled": False}, "discord": {"enabled": False}})
    cfg.setdefault("gateway", {"host": "0.0.0.0", "port": 8787, "token": ""})

    console.print("\n" + MASCOT)
    console.print(Panel.fit("[bold magenta]🚀 Onboarding ClawLite (PT-BR)[/bold magenta]", border_style="magenta"))

    _progress(1)
    model = questionary.text(
        "🤖 Modelo padrão:",
        default=cfg.get("model", "openai/gpt-4o-mini"),
        validate=_validate_required("Modelo"),
    ).ask()
    cfg["model"] = model

    _progress(2)
    first = questionary.select(
        "🔐 Escolha o primeiro provedor para autenticar:",
        choices=list(PROVIDERS.keys()) + ["pular por enquanto"],
    ).ask()
    if first and first != "pular por enquanto":
        auth_login(first)

    _progress(3)
    channels = questionary.checkbox(
        "📡 Canais ativos (espaço para marcar):",
        choices=[
            Choice("Telegram", checked=cfg.get("channels", {}).get("telegram", {}).get("enabled", False)),
            Choice("Discord", checked=cfg.get("channels", {}).get("discord", {}).get("enabled", False)),
        ],
    ).ask() or []
    cfg["channels"]["telegram"] = {"enabled": "Telegram" in channels}
    cfg["channels"]["discord"] = {"enabled": "Discord" in channels}

    _progress(4)
    host = questionary.text(
        "🌐 Host do gateway:",
        default=str(cfg.get("gateway", {}).get("host", "0.0.0.0")),
        validate=_validate_required("Host do gateway"),
    ).ask()
    port = questionary.text(
        "🔌 Porta do gateway:",
        default=str(cfg.get("gateway", {}).get("port", 8787)),
        validate=_validate_port,
    ).ask()
    token = questionary.text(
        "🪪 Token do gateway (enter para gerar automático):",
        default=cfg.get("gateway", {}).get("token", ""),
    ).ask().strip()

    cfg["gateway"]["host"] = host
    cfg["gateway"]["port"] = int(port)
    cfg["gateway"]["token"] = token or secrets.token_urlsafe(24)

    _progress(5)
    console.print(Panel("Confira antes de salvar:", title="👀 Prévia", border_style="cyan"))
    console.print(Syntax(json.dumps(cfg, ensure_ascii=False, indent=2), "json", theme="monokai", line_numbers=False))

    if not questionary.confirm("💾 Confirmar e salvar configuração?", default=True).ask():
        console.print("🟡 Onboarding cancelado. Nada foi salvo.")
        return

    save_config(cfg)
    resumo = (
        f"🤖 Modelo: [bold]{cfg.get('model')}[/bold]\n"
        f"📡 Telegram: {'✅' if cfg['channels']['telegram']['enabled'] else '❌'}\n"
        f"💬 Discord: {'✅' if cfg['channels']['discord']['enabled'] else '❌'}\n"
        f"🌐 Gateway: [bold]{cfg['gateway']['host']}:{cfg['gateway']['port']}[/bold]\n"
        "📁 Arquivo salvo em [bold]~/.clawlite/config.json[/bold]"
    )
    console.print(Panel(resumo, title="✅ Onboarding concluído com sucesso", border_style="green"))
