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
from clawlite.runtime.locale import detect_language
from clawlite.skills.registry import SKILLS, describe_skill

console = Console()


I18N = {
    "pt-br": {
        "title": "⚙️ ClawLite Configure",
        "menu": "Use ↑↓ para navegar e Enter para abrir uma seção:",
        "saved": "✅ Configuração salva automaticamente.",
        "preview": "👀 Prévia final",
        "confirm": "Salvar esta configuração?",
        "bye": "👋 Saindo do configurador.",
    },
    "en": {
        "title": "⚙️ ClawLite Configure",
        "menu": "Use ↑↓ and Enter to open a section:",
        "saved": "✅ Configuration auto-saved.",
        "preview": "👀 Final preview",
        "confirm": "Save this configuration?",
        "bye": "👋 Leaving configurator.",
    },
}

MODEL_OPTIONS = {
    "openai": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
    "anthropic": ["anthropic/claude-3-5-sonnet", "anthropic/claude-3-5-haiku"],
    "gemini": ["gemini/gemini-2.0-flash", "gemini/gemini-1.5-pro"],
    "openrouter": ["openrouter/auto", "openrouter/anthropic/claude-3.5-sonnet"],
    "groq": ["groq/llama-3.3-70b", "groq/mixtral-8x7b"],
    "ollama": ["ollama/llama3.1:8b", "ollama/qwen2.5:7b"],
}


def _validate_required(label: str):
    def _inner(value: str) -> bool | str:
        if not str(value or "").strip():
            return f"⚠️ {label} é obrigatório."
        return True

    return _inner


def _validate_port(value: str) -> bool | str:
    v = (value or "").strip()
    if not v.isdigit():
        return "⚠️ Porta inválida (1-65535)."
    n = int(v)
    if n < 1 or n > 65535:
        return "⚠️ Porta inválida (1-65535)."
    return True


def _preview(cfg: dict[str, Any]) -> str:
    return json.dumps(cfg, ensure_ascii=False, indent=2)


def _autosave(cfg: dict[str, Any]) -> None:
    save_config(cfg)
    console.print("[green]✅ Configuração salva automaticamente.[/green]")


def _ensure_defaults(cfg: dict[str, Any]) -> None:
    cfg.setdefault("language", detect_language("pt-br"))
    cfg.setdefault("channels", {})
    cfg["channels"].setdefault("telegram", {"enabled": False, "token": "", "chat_id": ""})
    cfg["channels"].setdefault("whatsapp", {"enabled": False, "token": "", "phone": ""})
    cfg["channels"].setdefault("discord", {"enabled": False, "token": "", "guild_id": ""})
    cfg.setdefault("hooks", {"boot": True, "session_memory": True, "command_logger": False})
    cfg.setdefault("gateway", {"host": "0.0.0.0", "port": 8787, "token": "", "dashboard_enabled": True})
    cfg.setdefault(
        "web_tools",
        {
            "web_search": {"enabled": True, "provider": "brave"},
            "reddit": {"enabled": False, "subreddits": ["selfhosted", "Python"]},
            "threads": {"enabled": False, "username": ""},
        },
    )
    cfg.setdefault("security", {"allow_shell_exec": True, "redact_tokens_in_logs": True, "require_gateway_token": True})
    cfg.setdefault("skills", cfg.get("skills", []))


def _section_model(cfg: dict[str, Any]) -> None:
    provider = questionary.select("Provedor de modelo:", choices=list(MODEL_OPTIONS.keys())).ask()
    model = questionary.select("Modelo:", choices=MODEL_OPTIONS[provider]).ask()
    cfg["model"] = model
    if provider in PROVIDERS and questionary.confirm(f"Fazer login OAuth/chave de {provider} agora?", default=False).ask():
        auth_login(provider)


def _section_channels(cfg: dict[str, Any]) -> None:
    selected = questionary.checkbox(
        "Canais ativos (espaço para marcar):",
        choices=[
            Choice("telegram", checked=cfg["channels"]["telegram"].get("enabled", False)),
            Choice("whatsapp", checked=cfg["channels"]["whatsapp"].get("enabled", False)),
            Choice("discord", checked=cfg["channels"]["discord"].get("enabled", False)),
        ],
    ).ask() or []

    for name in ["telegram", "whatsapp", "discord"]:
        cfg["channels"][name]["enabled"] = name in selected

    if cfg["channels"]["telegram"]["enabled"]:
        cfg["channels"]["telegram"]["token"] = questionary.text(
            "Token do Telegram:", default=cfg["channels"]["telegram"].get("token", "")
        ).ask()
        cfg["channels"]["telegram"]["chat_id"] = questionary.text(
            "Chat ID padrão:", default=cfg["channels"]["telegram"].get("chat_id", "")
        ).ask()

    if cfg["channels"]["whatsapp"]["enabled"]:
        cfg["channels"]["whatsapp"]["token"] = questionary.text(
            "Token/API key do WhatsApp:", default=cfg["channels"]["whatsapp"].get("token", "")
        ).ask()
        cfg["channels"]["whatsapp"]["phone"] = questionary.text(
            "Número padrão (+55...):", default=cfg["channels"]["whatsapp"].get("phone", "")
        ).ask()

    if cfg["channels"]["discord"]["enabled"]:
        cfg["channels"]["discord"]["token"] = questionary.text(
            "Token do bot Discord:", default=cfg["channels"]["discord"].get("token", "")
        ).ask()
        cfg["channels"]["discord"]["guild_id"] = questionary.text(
            "Guild ID padrão:", default=cfg["channels"]["discord"].get("guild_id", "")
        ).ask()


def _section_skills(cfg: dict[str, Any]) -> None:
    skills = sorted(SKILLS.keys())
    viewed = questionary.select("Ver descrição de qual skill?", choices=skills + ["pular"]).ask()
    if viewed and viewed != "pular":
        console.print(Panel(describe_skill(viewed), title=f"🧩 {viewed}", border_style="cyan"))

    enabled = set(cfg.get("skills", []))
    choices = [Choice(f"{name} — {describe_skill(name)}", value=name, checked=(name in enabled)) for name in skills]
    cfg["skills"] = questionary.checkbox("Ative/desative skills (espaço):", choices=choices).ask() or []


def _section_hooks(cfg: dict[str, Any]) -> None:
    selected = questionary.checkbox(
        "Hooks ativos:",
        choices=[
            Choice("boot", checked=cfg["hooks"].get("boot", True)),
            Choice("session-memory", checked=cfg["hooks"].get("session_memory", True)),
            Choice("command-logger", checked=cfg["hooks"].get("command_logger", False)),
        ],
    ).ask() or []
    cfg["hooks"] = {
        "boot": "boot" in selected,
        "session_memory": "session-memory" in selected,
        "command_logger": "command-logger" in selected,
    }


def _section_gateway(cfg: dict[str, Any]) -> None:
    cfg["gateway"]["host"] = questionary.text(
        "Host do gateway:", default=str(cfg["gateway"].get("host", "0.0.0.0")), validate=_validate_required("Host")
    ).ask()
    cfg["gateway"]["port"] = int(
        questionary.text("Porta do gateway:", default=str(cfg["gateway"].get("port", 8787)), validate=_validate_port).ask()
    )
    token = questionary.text("Token do gateway (vazio gera automático):", default=str(cfg["gateway"].get("token", ""))).ask().strip()
    cfg["gateway"]["token"] = token or secrets.token_urlsafe(24)
    cfg["gateway"]["dashboard_enabled"] = bool(
        questionary.confirm("Dashboard web habilitado?", default=cfg["gateway"].get("dashboard_enabled", True)).ask()
    )


def _section_web_tools(cfg: dict[str, Any]) -> None:
    selected = questionary.checkbox(
        "Ferramentas web ativas:",
        choices=[
            Choice("web-search", checked=cfg["web_tools"].get("web_search", {}).get("enabled", True)),
            Choice("reddit", checked=cfg["web_tools"].get("reddit", {}).get("enabled", False)),
            Choice("threads", checked=cfg["web_tools"].get("threads", {}).get("enabled", False)),
        ],
    ).ask() or []

    cfg["web_tools"].setdefault("web_search", {})
    cfg["web_tools"].setdefault("reddit", {})
    cfg["web_tools"].setdefault("threads", {})

    cfg["web_tools"]["web_search"]["enabled"] = "web-search" in selected
    cfg["web_tools"]["reddit"]["enabled"] = "reddit" in selected
    cfg["web_tools"]["threads"]["enabled"] = "threads" in selected

    if cfg["web_tools"]["web_search"]["enabled"]:
        cfg["web_tools"]["web_search"]["provider"] = questionary.select(
            "Provider do web search:", choices=["brave", "duckduckgo", "serpapi"]
        ).ask()

    if cfg["web_tools"]["reddit"]["enabled"]:
        subs = questionary.text(
            "Subreddits (vírgula):",
            default=", ".join(cfg["web_tools"]["reddit"].get("subreddits", ["selfhosted", "Python"])),
        ).ask()
        cfg["web_tools"]["reddit"]["subreddits"] = [s.strip() for s in subs.split(",") if s.strip()]

    if cfg["web_tools"]["threads"]["enabled"]:
        cfg["web_tools"]["threads"]["username"] = questionary.text(
            "Usuário Threads:", default=cfg["web_tools"]["threads"].get("username", "")
        ).ask()


def _section_language(cfg: dict[str, Any]) -> None:
    default_lang = cfg.get("language") or detect_language("pt-br")
    cfg["language"] = questionary.select("Idioma da interface:", choices=["pt-br", "en"], default=default_lang).ask()


def _section_security(cfg: dict[str, Any]) -> None:
    selected = questionary.checkbox(
        "Opções de segurança:",
        choices=[
            Choice("allow-shell-exec", checked=cfg["security"].get("allow_shell_exec", True)),
            Choice("redact-tokens-in-logs", checked=cfg["security"].get("redact_tokens_in_logs", True)),
            Choice("require-gateway-token", checked=cfg["security"].get("require_gateway_token", True)),
        ],
    ).ask() or []
    cfg["security"] = {
        "allow_shell_exec": "allow-shell-exec" in selected,
        "redact_tokens_in_logs": "redact-tokens-in-logs" in selected,
        "require_gateway_token": "require-gateway-token" in selected,
    }
    if cfg["security"]["require_gateway_token"] and not str(cfg["gateway"].get("token", "")).strip():
        cfg["gateway"]["token"] = secrets.token_urlsafe(24)


def run_configure_menu() -> None:
    cfg = load_config()
    _ensure_defaults(cfg)
    if not cfg.get("language"):
        cfg["language"] = detect_language("pt-br")

    sections = [
        Choice("Model", "model"),
        Choice("Channels", "channels"),
        Choice("Skills", "skills"),
        Choice("Hooks", "hooks"),
        Choice("Gateway", "gateway"),
        Choice("Web Tools", "web_tools"),
        Choice("Language", "language"),
        Choice("Security", "security"),
        Choice("Preview & Save", "save"),
        Choice("Exit", "exit"),
    ]

    while True:
        lang = cfg.get("language", "pt-br")
        console.print(Panel.fit(f"[bold cyan]{I18N.get(lang, I18N['pt-br'])['title']}[/bold cyan]", border_style="magenta"))
        section = questionary.select(I18N.get(lang, I18N["pt-br"])["menu"], choices=sections).ask()

        if section == "model":
            _section_model(cfg)
            _autosave(cfg)
        elif section == "channels":
            _section_channels(cfg)
            _autosave(cfg)
        elif section == "skills":
            _section_skills(cfg)
            _autosave(cfg)
        elif section == "hooks":
            _section_hooks(cfg)
            _autosave(cfg)
        elif section == "gateway":
            _section_gateway(cfg)
            _autosave(cfg)
        elif section == "web_tools":
            _section_web_tools(cfg)
            _autosave(cfg)
        elif section == "language":
            _section_language(cfg)
            _autosave(cfg)
        elif section == "security":
            _section_security(cfg)
            _autosave(cfg)
        elif section == "save":
            console.print(Panel(I18N.get(lang, I18N["pt-br"])["preview"], border_style="cyan"))
            console.print(Syntax(_preview(cfg), "json", theme="monokai", line_numbers=False))
            if questionary.confirm(I18N.get(lang, I18N["pt-br"])["confirm"], default=True).ask():
                save_config(cfg)
                console.print("[green]✅ Configuração final salva.[/green]")
                return
        else:
            console.print(I18N.get(lang, I18N["pt-br"])["bye"])
            return
