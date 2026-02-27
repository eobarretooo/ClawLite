from __future__ import annotations

import json
import secrets
from typing import Any

import questionary
from questionary import Choice
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from clawlite.auth import PROVIDERS, auth_login
from clawlite.config.settings import load_config, save_config
from clawlite.skills.registry import SKILLS

console = Console()


def _preview(cfg: dict[str, Any]) -> str:
    return json.dumps(cfg, ensure_ascii=False, indent=2)


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


def _steps_done(cfg: dict[str, Any]) -> int:
    done = 0
    if cfg.get("model"):
        done += 1
    channels = cfg.get("channels", {})
    if isinstance(channels, dict):
        done += 1
    if isinstance(cfg.get("skills", []), list):
        done += 1
    gateway = cfg.get("gateway", {})
    if gateway.get("host") and gateway.get("port"):
        done += 1
    if isinstance(cfg.get("security", {}), dict):
        done += 1
    if "enabled" in cfg.get("web_tools", {}):
        done += 1
    return done


def _header(cfg: dict[str, Any]) -> None:
    done = min(_steps_done(cfg), 6)
    total = 6
    pct = int((done / total) * 100)
    bar_width = 24
    fill = int((done / total) * bar_width)
    bar = "🟪" * fill + "⬜" * (bar_width - fill)

    console.print(
        Panel.fit(
            f"[bold cyan]⚙️ ClawLite Configure (PT-BR)[/bold cyan]\n"
            f"[magenta]{bar}[/magenta] [bold]{done}/{total}[/bold] etapas • {pct}%",
            border_style="bright_magenta",
        )
    )


def _resumo_final(cfg: dict[str, Any]) -> None:
    channels = cfg.get("channels", {})
    skills = cfg.get("skills", [])
    gateway = cfg.get("gateway", {})

    linhas = [
        f"🤖 Modelo: [bold]{cfg.get('model', 'não definido')}[/bold]",
        f"📡 Telegram: {'✅ ativo' if channels.get('telegram', {}).get('enabled') else '❌ desativado'}",
        f"💬 Discord: {'✅ ativo' if channels.get('discord', {}).get('enabled') else '❌ desativado'}",
        f"🧩 Skills ativas: [bold]{len(skills)}[/bold]",
        f"🌐 Gateway: [bold]{gateway.get('host', '0.0.0.0')}:{gateway.get('port', 8787)}[/bold]",
        f"🕸️ Web tools: {'✅ ativado' if cfg.get('web_tools', {}).get('enabled', True) else '❌ desativado'}",
    ]

    console.print(Panel("\n".join(linhas), title="✅ Configuração concluída", border_style="green"))


def run_configure_menu() -> None:
    cfg = load_config()
    cfg.setdefault("channels", {"telegram": {"enabled": False}, "discord": {"enabled": False}})
    cfg.setdefault("gateway", {"host": "0.0.0.0", "port": 8787, "token": ""})
    cfg.setdefault("security", {"allow_shell_exec": True, "redact_tokens_in_logs": True})
    cfg.setdefault("web_tools", {"enabled": True})
    cfg.setdefault("skills", cfg.get("skills", []))

    sections = [
        Choice(
            title="🤖 Modelo e autenticação\n   └─ Define IA padrão e login inicial de provedor",
            value="model",
        ),
        Choice(
            title="📡 Canais\n   └─ Liga/desliga Telegram e Discord",
            value="channels",
        ),
        Choice(
            title="🧩 Skills\n   └─ Escolhe recursos extras com espaço",
            value="skills",
        ),
        Choice(
            title="🌐 Gateway\n   └─ Host, porta e token de acesso",
            value="gateway",
        ),
        Choice(
            title="🔒 Segurança\n   └─ Regras de execução e proteção de logs",
            value="security",
        ),
        Choice(
            title="🕸️ Ferramentas Web\n   └─ Habilita busca/fetch na internet",
            value="web_tools",
        ),
        Choice(
            title="👀 Prévia, confirmação e salvar\n   └─ Revise tudo antes de gravar",
            value="save",
        ),
        Choice(title="❌ Sair sem salvar", value="exit"),
    ]

    while True:
        _header(cfg)
        section = questionary.select(
            "Use ↑↓ para navegar e Enter para abrir uma etapa:",
            choices=sections,
            use_shortcuts=True,
        ).ask()

        if section == "model":
            cfg["model"] = questionary.text(
                "🤖 Modelo padrão:",
                default=cfg.get("model", "openai/gpt-4o-mini"),
                validate=_validate_required("Modelo"),
            ).ask()
            first = questionary.select(
                "🔐 Autenticar provedor agora?",
                choices=["pular"] + list(PROVIDERS.keys()),
            ).ask()
            if first and first != "pular":
                auth_login(first)

        elif section == "channels":
            ch = questionary.checkbox(
                "📡 Canais ativos (use espaço para marcar):",
                choices=[
                    Choice("Telegram", checked=cfg.get("channels", {}).get("telegram", {}).get("enabled", False)),
                    Choice("Discord", checked=cfg.get("channels", {}).get("discord", {}).get("enabled", False)),
                ],
            ).ask() or []
            cfg["channels"]["telegram"]["enabled"] = "Telegram" in ch
            cfg["channels"]["discord"]["enabled"] = "Discord" in ch

        elif section == "skills":
            enabled = set(cfg.get("skills", []))
            choices = [Choice(f"{s}", checked=(s in enabled)) for s in sorted(SKILLS.keys())]
            picked = questionary.checkbox("🧩 Skills ativas (espaço para marcar):", choices=choices).ask() or []
            cfg["skills"] = picked

        elif section == "gateway":
            cfg["gateway"]["host"] = questionary.text(
                "🌐 Host do gateway:",
                default=str(cfg["gateway"].get("host", "0.0.0.0")),
                validate=_validate_required("Host do gateway"),
            ).ask()
            port_raw = questionary.text(
                "🔌 Porta do gateway:",
                default=str(cfg["gateway"].get("port", 8787)),
                validate=_validate_port,
            ).ask()
            cfg["gateway"]["port"] = int(port_raw)
            tok = questionary.text(
                "🪪 Token do gateway (vazio = gerar automático):",
                default=str(cfg["gateway"].get("token", "")),
            ).ask().strip()
            cfg["gateway"]["token"] = tok or secrets.token_urlsafe(24)

        elif section == "security":
            security = questionary.checkbox(
                "🔒 Regras de segurança (espaço para marcar):",
                choices=[
                    Choice("Permitir shell exec", checked=cfg["security"].get("allow_shell_exec", True)),
                    Choice("Mascarar tokens nos logs", checked=cfg["security"].get("redact_tokens_in_logs", True)),
                ],
            ).ask() or []
            cfg["security"]["allow_shell_exec"] = "Permitir shell exec" in security
            cfg["security"]["redact_tokens_in_logs"] = "Mascarar tokens nos logs" in security

        elif section == "web_tools":
            enabled = questionary.confirm(
                "🕸️ Ativar ferramentas web?",
                default=cfg.get("web_tools", {}).get("enabled", True),
            ).ask()
            cfg["web_tools"]["enabled"] = bool(enabled)

        elif section == "save":
            console.print(Panel("Revise com calma antes de confirmar.", border_style="cyan", title="👀 Prévia"))
            console.print(Syntax(_preview(cfg), "json", theme="monokai", line_numbers=False))

            if questionary.confirm("💾 Salvar essas configurações agora?", default=True).ask():
                save_config(cfg)
                _resumo_final(cfg)
                return
            console.print("🟡 Nada foi salvo ainda. Você pode continuar editando.")

        elif section in ("exit", None):
            console.print("👋 Saindo sem salvar alterações.")
            return
