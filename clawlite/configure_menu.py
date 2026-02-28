"""
ClawLite Configure Menu — estilo OpenClaw.

Menu principal com badges de status por seção, submenus por canal,
validação inline, preview JSON, Apply & Restart e todas as seções
que o OpenClaw Control UI cobre (Model, Channels, Skills, Gateway,
MCP, Memory, Runtime, Cron, Agents, Hooks, Web Tools, Security,
Identity, Notifications, Language).
"""
from __future__ import annotations

import json
import os
import secrets
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import questionary
from questionary import Choice
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich import box

from clawlite.auth import PROVIDERS, auth_login
from clawlite.config.settings import CONFIG_DIR, load_config, save_config
from clawlite.core.providers import normalize_provider
from clawlite.runtime.locale import detect_language
from clawlite.skills.registry import SKILLS, describe_skill

console = Console()

# ──────────────────────────────────────────────
# Paleta de cores ClawLite (alinhada ao brand)
# ──────────────────────────────────────────────
C_ORANGE  = "#ff6b2b"
C_CYAN    = "#00f5ff"
C_GREEN   = "#10b981"
C_YELLOW  = "#fbbf24"
C_RED     = "#f87171"
C_GRAY    = "#6b7280"
C_WHITE   = "#f9fafb"

# ──────────────────────────────────────────────
# Opções de modelo por provedor
# ──────────────────────────────────────────────
MODEL_OPTIONS: dict[str, list[str]] = {
    "openai": [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/gpt-4.1",
        "openai/gpt-4.1-mini",
    ],
    "anthropic": [
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-opus-4-6",
        "anthropic/claude-haiku-4-5",
    ],
    "gemini": [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-pro",
        "gemini/gemini-2.0-flash",
    ],
    "openrouter": [
        "openrouter/auto",
        "openrouter/anthropic/claude-sonnet-4-6",
        "openrouter/openai/gpt-4o",
        "openrouter/meta-llama/llama-3.3-70b-instruct",
    ],
    "groq": [
        "groq/llama-3.3-70b-versatile",
        "groq/llama-3.1-8b-instant",
        "groq/mixtral-8x7b-32768",
    ],
    "moonshot": [
        "moonshot/kimi-k2.5",
        "moonshot/kimi-k2-thinking",
        "moonshot/kimi-k2-turbo-preview",
    ],
    "mistral": [
        "mistral/mistral-large-latest",
        "mistral/mistral-medium-latest",
    ],
    "xai": [
        "xai/grok-4",
        "xai/grok-4-fast",
    ],
    "together": [
        "together/moonshotai/Kimi-K2.5",
        "together/meta-llama/Llama-3.3-70B-Instruct-Turbo",
    ],
    "huggingface": [
        "huggingface/deepseek-ai/DeepSeek-R1",
        "huggingface/meta-llama/Llama-3.3-70B-Instruct",
    ],
    "nvidia": [
        "nvidia/llama-3.1-nemotron-70b-instruct",
    ],
    "qianfan": [
        "qianfan/deepseek-v3.2",
    ],
    "venice": [
        "venice/llama-3.3-70b",
        "venice/claude-opus-45",
    ],
    "minimax": [
        "minimax/MiniMax-M2.1",
    ],
    "xiaomi": [
        "xiaomi/mimo-v2-flash",
    ],
    "zai": [
        "zai/glm-5",
        "zai/glm-4.7",
    ],
    "litellm": [
        "litellm/claude-opus-4-6",
        "litellm/gpt-4o",
    ],
    "vercel-ai-gateway": [
        "vercel-ai-gateway/anthropic/claude-opus-4.6",
        "vercel-ai-gateway/openai/gpt-4o",
    ],
    "kilocode": [
        "kilocode/anthropic/claude-opus-4.6",
        "kilocode/google/gemini-2.5-pro",
    ],
    "vllm": [
        "vllm/Qwen/Qwen2.5-7B-Instruct",
        "vllm/meta-llama/Llama-3.1-8B-Instruct",
    ],
    "ollama": [
        "ollama/llama3.1:8b",
        "ollama/qwen2.5:7b",
        "ollama/mistral:7b",
        "ollama/codellama:7b",
    ],
}

CHANNEL_NAMES = ["telegram", "whatsapp", "discord", "slack", "teams"]

# ──────────────────────────────────────────────
# Helpers visuais
# ──────────────────────────────────────────────

def _ok(text: str = "") -> str:
    return f"[{C_GREEN}]✅[/{C_GREEN}]" + (f" [dim]{text}[/dim]" if text else "")

def _warn(text: str = "") -> str:
    return f"[{C_YELLOW}]⚠️[/{C_YELLOW}]" + (f" [dim]{text}[/dim]" if text else "")

def _err(text: str = "") -> str:
    return f"[{C_RED}]🔴[/{C_RED}]" + (f" [dim]{text}[/dim]" if text else "")

def _dim(text: str) -> str:
    return f"[dim]{text}[/dim]"

def _header(title: str, subtitle: str = "") -> None:
    inner = f"[bold {C_ORANGE}]{title}[/bold {C_ORANGE}]"
    if subtitle:
        inner += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel.fit(inner, border_style=C_ORANGE, padding=(0, 2)))

def _section_header(title: str, icon: str = "⚙️") -> None:
    console.print(f"\n[bold {C_CYAN}]{icon}  {title}[/bold {C_CYAN}]")
    console.print(f"[{C_GRAY}]{'─' * 48}[/{C_GRAY}]")

def _autosave(cfg: dict[str, Any]) -> None:
    save_config(cfg)
    console.print(f"  [{C_GREEN}]✅ Salvo automaticamente.[/{C_GREEN}]")

def _divider() -> None:
    console.print(f"[{C_GRAY}]{'─' * 48}[/{C_GRAY}]")

def _show_table(title: str, rows: list[tuple[str, str]]) -> None:
    """Exibe uma tabela Rich com chave/valor, estilo OpenClaw."""
    t = Table(
        title=title,
        box=box.SIMPLE_HEAD,
        border_style=C_GRAY,
        header_style=f"bold {C_CYAN}",
        title_style=f"bold {C_WHITE}",
        show_lines=False,
        padding=(0, 1),
    )
    t.add_column("Configuração", style=C_WHITE, min_width=22)
    t.add_column("Valor atual", style=C_CYAN)
    for k, v in rows:
        t.add_row(k, v)
    console.print(t)


# ──────────────────────────────────────────────
# Status badges para o menu principal
# ──────────────────────────────────────────────

def _status_model(cfg: dict) -> str:
    m = cfg.get("model", "")
    if m:
        return f"[{C_GREEN}]{m}[/{C_GREEN}]"
    return f"[{C_RED}]não configurado[/{C_RED}]"

def _status_channels(cfg: dict) -> str:
    ch = cfg.get("channels", {})
    active = [n for n in CHANNEL_NAMES if ch.get(n, {}).get("enabled")]
    missing_token = [
        n for n in active
        if not str(ch.get(n, {}).get("token", "")).strip()
    ]
    if not active:
        return f"[{C_GRAY}]nenhum ativo[/{C_GRAY}]"
    label = " · ".join(active)
    if missing_token:
        return f"[{C_YELLOW}]{label} ⚠️ sem token[/{C_YELLOW}]"
    return f"[{C_GREEN}]{label}[/{C_GREEN}]"

def _status_skills(cfg: dict) -> str:
    total = len(SKILLS)
    enabled = len(cfg.get("skills", []))
    color = C_GREEN if enabled > 0 else C_GRAY
    return f"[{color}]{enabled}/{total} ativos[/{color}]"

def _status_gateway(cfg: dict) -> str:
    gw = cfg.get("gateway", {})
    host = gw.get("host", "0.0.0.0")
    port = gw.get("port", 8787)
    token = str(gw.get("token", "")).strip()
    if not token:
        return f"[{C_YELLOW}]{host}:{port} ⚠️ sem token[/{C_YELLOW}]"
    return f"[{C_GREEN}]{host}:{port}[/{C_GREEN}]"

def _status_mcp() -> str:
    try:
        from clawlite.mcp import list_servers
        servers = list_servers()
        if servers:
            return f"[{C_GREEN}]{len(servers)} servidor(es)[/{C_GREEN}]"
    except Exception:
        pass
    return f"[{C_GRAY}]nenhum servidor[/{C_GRAY}]"

def _status_memory() -> str:
    ws = Path.home() / ".clawlite" / "workspace"
    if ws.exists():
        files = list(ws.rglob("*.md"))
        return f"[{C_GREEN}]{len(files)} arquivos[/{C_GREEN}]"
    return f"[{C_YELLOW}]workspace não inicializado[/{C_YELLOW}]"

def _status_runtime(cfg: dict) -> str:
    offline = cfg.get("offline_mode", {})
    ollama  = cfg.get("ollama", {})
    auto    = offline.get("auto_fallback_to_ollama", False)
    model   = ollama.get("model", "")
    if auto and model:
        return f"[{C_GREEN}]fallback: {model}[/{C_GREEN}]"
    if auto:
        return f"[{C_YELLOW}]fallback ativo, sem modelo[/{C_YELLOW}]"
    return f"[{C_GRAY}]fallback desativado[/{C_GRAY}]"

def _status_cron() -> str:
    try:
        from clawlite.runtime.conversation_cron import list_cron_jobs
        jobs = list_cron_jobs()
        enabled = sum(1 for j in jobs if j.enabled)
        if jobs:
            return f"[{C_GREEN}]{enabled}/{len(jobs)} jobs[/{C_GREEN}]"
    except Exception:
        pass
    return f"[{C_GRAY}]nenhum job[/{C_GRAY}]"

def _status_agents() -> str:
    try:
        from clawlite.runtime.multiagent import list_agents
        agents = list_agents()
        if agents:
            return f"[{C_GREEN}]{len(agents)} agente(s)[/{C_GREEN}]"
    except Exception:
        pass
    return f"[{C_GRAY}]nenhum agente[/{C_GRAY}]"

def _status_security(cfg: dict) -> str:
    sec = cfg.get("security", {})
    token = str(cfg.get("gateway", {}).get("token", "")).strip()
    pairing_cfg = sec.get("pairing", {}) if isinstance(sec.get("pairing"), dict) else {}
    pairing_enabled = bool(pairing_cfg.get("enabled", False))
    issues = []
    if not token:
        issues.append("sem token")
    if not sec.get("redact_tokens_in_logs", True):
        issues.append("logs expostos")
    if issues:
        return f"[{C_YELLOW}]⚠️  {', '.join(issues)}[/{C_YELLOW}]"
    if pairing_enabled:
        return f"[{C_GREEN}]ok + pairing[/{C_GREEN}]"
    return f"[{C_GREEN}]ok[/{C_GREEN}]"

def _status_identity(cfg: dict) -> str:
    name = cfg.get("assistant_name", "")
    if name:
        return f"[{C_GREEN}]{name}[/{C_GREEN}]"
    return f"[{C_GRAY}]ClawLite Assistant[/{C_GRAY}]"

def _status_language(cfg: dict) -> str:
    lang = cfg.get("language", "pt-br").upper()
    return f"[{C_CYAN}]{lang}[/{C_CYAN}]"

def _status_hooks(cfg: dict) -> str:
    h = cfg.get("hooks", {})
    active = [k for k, v in h.items() if v]
    if active:
        return f"[{C_GREEN}]{', '.join(active)}[/{C_GREEN}]"
    return f"[{C_GRAY}]nenhum[/{C_GRAY}]"

def _status_notifications(cfg: dict) -> str:
    n = cfg.get("notifications", {})
    if n.get("enabled", True):
        dedupe = n.get("dedupe_window_seconds", 300)
        return f"[{C_GREEN}]ativo · dedupe {dedupe}s[/{C_GREEN}]"
    return f"[{C_GRAY}]desativado[/{C_GRAY}]"


# ──────────────────────────────────────────────
# Validadores
# ──────────────────────────────────────────────

def _validate_required(label: str):
    def _inner(value: str) -> bool | str:
        if not str(value or "").strip():
            return f"⚠️  {label} é obrigatório."
        return True
    return _inner

def _validate_port(value: str) -> bool | str:
    v = (value or "").strip()
    if not v.isdigit():
        return "⚠️  Porta inválida (1–65535)."
    n = int(v)
    if n < 1 or n > 65535:
        return "⚠️  Porta inválida (1–65535)."
    return True

def _validate_interval(value: str) -> bool | str:
    v = (value or "").strip()
    if not v.isdigit() or int(v) <= 0:
        return "⚠️  Intervalo deve ser número inteiro positivo (segundos)."
    return True

def _validate_phone(value: str) -> bool | str:
    v = (value or "").strip()
    if v and not v.startswith("+"):
        return "⚠️  Número no formato internacional: +5511..."
    return True


# ──────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────

def _ensure_defaults(cfg: dict[str, Any]) -> None:
    cfg.setdefault("language", detect_language("pt-br"))
    cfg.setdefault("model", "openai/gpt-4o-mini")
    cfg.setdefault("model_fallback", ["openrouter/auto", "ollama/llama3.1:8b"])
    cfg.setdefault("offline_mode", {
        "enabled": True,
        "auto_fallback_to_ollama": True,
        "connectivity_timeout_sec": 1.5,
    })
    cfg.setdefault("ollama", {"model": "llama3.1:8b"})
    cfg.setdefault("battery_mode", {"enabled": False, "throttle_seconds": 6.0})
    cfg.setdefault("notifications", {"enabled": True, "dedupe_window_seconds": 300})
    cfg.setdefault("channels", {})
    for ch_name, defaults in {
        "telegram":  {"enabled": False, "token": "", "chat_id": "", "accounts": [], "allowFrom": [],
                      "stt_enabled": False, "stt_model": "base", "stt_language": "pt",
                      "tts_enabled": False, "tts_provider": "local",
                      "tts_model": "gpt-4o-mini-tts", "tts_voice": "alloy",
                      "tts_default_reply": False},
        "whatsapp":  {"enabled": False, "token": "", "phone": "", "accounts": [], "allowFrom": [],
                      "stt_enabled": False, "stt_model": "base", "stt_language": "pt",
                      "tts_enabled": False, "tts_provider": "local",
                      "tts_model": "gpt-4o-mini-tts", "tts_voice": "alloy",
                      "tts_default_reply": False},
        "discord":   {"enabled": False, "token": "", "guild_id": "", "accounts": [], "allowFrom": [], "allowChannels": []},
        "slack":     {"enabled": False, "token": "", "workspace": "", "app_token": "", "accounts": [], "allowFrom": [], "allowChannels": []},
        "teams":     {"enabled": False, "token": "", "tenant": "", "accounts": []},
    }.items():
        cfg["channels"].setdefault(ch_name, defaults)
    cfg.setdefault("hooks", {"boot": True, "session_memory": True, "command_logger": False})
    cfg.setdefault("gateway", {
        "host": "0.0.0.0", "port": 8787,
        "token": "", "dashboard_enabled": True,
    })
    cfg.setdefault("web_tools", {
        "web_search": {"enabled": True, "provider": "brave"},
        "reddit":     {"enabled": False, "subreddits": ["selfhosted", "Python"]},
        "threads":    {"enabled": False, "username": ""},
    })
    cfg.setdefault("security", {
        "allow_shell_exec": True,
        "redact_tokens_in_logs": True,
        "require_gateway_token": True,
        "pairing": {"enabled": False, "code_ttl_seconds": 86400},
    })
    cfg.setdefault("skills", [])


# ──────────────────────────────────────────────
# SECTION: Model
# ──────────────────────────────────────────────

def _section_model(cfg: dict[str, Any]) -> None:
    _section_header("Model & Provider", "🤖")
    current_model = cfg.get("model", "openai/gpt-4o-mini")
    default_provider = normalize_provider(current_model.split("/")[0] if "/" in current_model else "openai")
    if default_provider not in MODEL_OPTIONS:
        default_provider = "openai"
    _show_table("Estado atual", [
        ("Modelo ativo", current_model),
        ("Fallback 1", cfg.get("model_fallback", ["—"])[0] if cfg.get("model_fallback") else "—"),
    ])
    console.print()

    provider = questionary.select(
        "Provedor principal:",
        choices=list(MODEL_OPTIONS.keys()),
        default=default_provider,
    ).ask()
    if provider is None:
        return

    model = questionary.select(
        "Modelo:",
        choices=MODEL_OPTIONS[provider],
        default=current_model if current_model in MODEL_OPTIONS.get(provider, []) else MODEL_OPTIONS[provider][0],
    ).ask()
    if model is None:
        return
    cfg["model"] = model

    # Fallbacks
    if questionary.confirm("Configurar modelos de fallback?", default=False).ask():
        fb_raw = questionary.text(
            "Fallback (vírgula, ex: openrouter/auto, ollama/llama3.1:8b):",
            default=", ".join(cfg.get("model_fallback", [])),
        ).ask() or ""
        cfg["model_fallback"] = [m.strip() for m in fb_raw.split(",") if m.strip()]

    # Login de API
    if provider in PROVIDERS:
        meta = PROVIDERS.get(provider, {})
        auth_url = str(meta.get("auth_url", "")).strip()
        if auth_url:
            console.print(f"[dim]Link para login/chave: {auth_url}[/dim]")
        if questionary.confirm(f"Configurar chave de API para {provider}?", default=False).ask():
            auth_login(provider)


# ──────────────────────────────────────────────
# SECTION: Channels — submenu por canal
# ──────────────────────────────────────────────

def _channel_status_row(name: str, ch_cfg: dict) -> tuple[str, str]:
    if not ch_cfg.get("enabled"):
        return (name, f"[{C_GRAY}]desativado[/{C_GRAY}]")
    token = str(ch_cfg.get("token", "")).strip()
    if not token:
        return (name, f"[{C_YELLOW}]ativo · ⚠️  sem token[/{C_YELLOW}]")
    return (name, f"[{C_GREEN}]ativo · token configurado[/{C_GREEN}]")


def _edit_telegram(ch: dict) -> None:
    _section_header("Telegram", "✈️")
    _show_table("Config atual", [
        ("Ativado", str(ch.get("enabled", False))),
        ("Token", "***" + str(ch.get("token", ""))[-6:] if ch.get("token") else "—"),
        ("Chat ID", str(ch.get("chat_id", "")) or "—"),
        ("STT", str(ch.get("stt_enabled", False))),
        ("TTS", str(ch.get("tts_enabled", False))),
    ])
    console.print()

    ch["enabled"] = questionary.confirm("Ativar Telegram?", default=ch.get("enabled", False)).ask()
    if not ch["enabled"]:
        return

    ch["token"] = questionary.text(
        "Bot Token:", default=ch.get("token", ""),
        validate=_validate_required("Token"),
    ).ask()

    ch["chat_id"] = questionary.text(
        "Chat ID padrão (seu user/group ID):", default=ch.get("chat_id", ""),
    ).ask()

    accounts_default = ", ".join(
        f"{a.get('account','')}:{a.get('token','')}"
        for a in ch.get("accounts", []) if a.get("account")
    )
    raw = questionary.text(
        "Contas adicionais (account:token, vírgula — opcional):",
        default=accounts_default,
    ).ask() or ""
    if raw.strip():
        ch["accounts"] = [
            {"account": p.split(":", 1)[0].strip(), "token": p.split(":", 1)[1].strip() if ":" in p else ""}
            for p in raw.split(",") if p.strip()
        ]

    # STT / TTS
    console.print(f"\n  [{C_CYAN}]Voz (STT/TTS)[/{C_CYAN}]")
    ch["stt_enabled"] = questionary.confirm(
        "  Ativar STT (áudio → texto)?",
        default=ch.get("stt_enabled", False),
    ).ask()
    if ch["stt_enabled"]:
        ch["stt_model"] = questionary.select(
            "  Modelo STT:", choices=["base", "small", "medium", "large"],
            default=ch.get("stt_model", "base"),
        ).ask()
        ch["stt_language"] = questionary.select(
            "  Idioma STT:", choices=["pt", "en", "es", "auto"],
            default=ch.get("stt_language", "pt"),
        ).ask()

    ch["tts_enabled"] = questionary.confirm(
        "  Ativar TTS (texto → áudio)?",
        default=ch.get("tts_enabled", False),
    ).ask()
    if ch["tts_enabled"]:
        ch["tts_provider"] = questionary.select(
            "  Provider TTS:", choices=["local", "openai"],
            default=ch.get("tts_provider", "local"),
        ).ask()
        if ch["tts_provider"] == "openai":
            ch["tts_voice"] = questionary.select(
                "  Voz OpenAI:", choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                default=ch.get("tts_voice", "alloy"),
            ).ask()
        ch["tts_default_reply"] = questionary.confirm(
            "  Responder sempre em áudio por padrão?",
            default=ch.get("tts_default_reply", False),
        ).ask()


def _edit_whatsapp(ch: dict) -> None:
    _section_header("WhatsApp", "📱")
    _show_table("Config atual", [
        ("Ativado", str(ch.get("enabled", False))),
        ("Token", "***" + str(ch.get("token", ""))[-6:] if ch.get("token") else "—"),
        ("Número", str(ch.get("phone", "")) or "—"),
        ("STT", str(ch.get("stt_enabled", False))),
    ])
    console.print()

    ch["enabled"] = questionary.confirm("Ativar WhatsApp?", default=ch.get("enabled", False)).ask()
    if not ch["enabled"]:
        return

    ch["token"] = questionary.text(
        "API Token / Bearer:", default=ch.get("token", ""),
        validate=_validate_required("Token"),
    ).ask()
    ch["phone"] = questionary.text(
        "Número padrão (+55...):", default=ch.get("phone", ""),
        validate=_validate_phone,
    ).ask()

    raw = questionary.text(
        "Instâncias adicionais (account:token, vírgula — opcional):",
        default=", ".join(
            f"{a.get('account','')}:{a.get('token','')}"
            for a in ch.get("accounts", []) if a.get("account")
        ),
    ).ask() or ""
    if raw.strip():
        ch["accounts"] = [
            {"account": p.split(":", 1)[0].strip(), "token": p.split(":", 1)[1].strip() if ":" in p else ""}
            for p in raw.split(",") if p.strip()
        ]

    ch["stt_enabled"] = questionary.confirm(
        "Ativar STT (áudio → texto)?", default=ch.get("stt_enabled", False),
    ).ask()
    ch["tts_enabled"] = questionary.confirm(
        "Ativar TTS (texto → áudio)?", default=ch.get("tts_enabled", False),
    ).ask()


def _edit_discord(ch: dict) -> None:
    _section_header("Discord", "🎮")
    _show_table("Config atual", [
        ("Ativado", str(ch.get("enabled", False))),
        ("Token bot", "***" + str(ch.get("token", ""))[-6:] if ch.get("token") else "—"),
        ("Guild ID", str(ch.get("guild_id", "")) or "—"),
    ])
    console.print()

    ch["enabled"] = questionary.confirm("Ativar Discord?", default=ch.get("enabled", False)).ask()
    if not ch["enabled"]:
        return

    ch["token"] = questionary.text(
        "Bot Token:", default=ch.get("token", ""),
        validate=_validate_required("Token"),
    ).ask()
    ch["guild_id"] = questionary.text(
        "Guild ID padrão:", default=ch.get("guild_id", ""),
    ).ask()

    raw = questionary.text(
        "Bots adicionais (guild:token, vírgula — opcional):",
        default=", ".join(
            f"{a.get('account','')}:{a.get('token','')}"
            for a in ch.get("accounts", []) if a.get("account")
        ),
    ).ask() or ""
    if raw.strip():
        ch["accounts"] = [
            {"account": p.split(":", 1)[0].strip(), "token": p.split(":", 1)[1].strip() if ":" in p else ""}
            for p in raw.split(",") if p.strip()
        ]


def _edit_slack(ch: dict) -> None:
    _section_header("Slack", "💬")
    _show_table("Config atual", [
        ("Ativado", str(ch.get("enabled", False))),
        ("Token bot", "***" + str(ch.get("token", ""))[-6:] if ch.get("token") else "—"),
        ("Workspace", str(ch.get("workspace", "")) or "—"),
    ])
    console.print()

    ch["enabled"] = questionary.confirm("Ativar Slack?", default=ch.get("enabled", False)).ask()
    if not ch["enabled"]:
        return

    ch["token"] = questionary.text(
        "Bot Token (xoxb-...):", default=ch.get("token", ""),
        validate=_validate_required("Token"),
    ).ask()
    ch["workspace"] = questionary.text(
        "Workspace padrão:", default=ch.get("workspace", ""),
    ).ask()

    raw = questionary.text(
        "Workspaces adicionais (workspace:token, vírgula — opcional):",
        default=", ".join(
            f"{a.get('account','')}:{a.get('token','')}"
            for a in ch.get("accounts", []) if a.get("account")
        ),
    ).ask() or ""
    if raw.strip():
        ch["accounts"] = [
            {"account": p.split(":", 1)[0].strip(), "token": p.split(":", 1)[1].strip() if ":" in p else ""}
            for p in raw.split(",") if p.strip()
        ]


def _edit_teams(ch: dict) -> None:
    _section_header("Microsoft Teams", "🏢")
    _show_table("Config atual", [
        ("Ativado", str(ch.get("enabled", False))),
        ("Token bot", "***" + str(ch.get("token", ""))[-6:] if ch.get("token") else "—"),
        ("Tenant", str(ch.get("tenant", "")) or "—"),
    ])
    console.print()

    ch["enabled"] = questionary.confirm("Ativar Teams?", default=ch.get("enabled", False)).ask()
    if not ch["enabled"]:
        return

    ch["token"] = questionary.text(
        "Bot Token:", default=ch.get("token", ""),
        validate=_validate_required("Token"),
    ).ask()
    ch["tenant"] = questionary.text(
        "Tenant ID/padrão:", default=ch.get("tenant", ""),
    ).ask()

    raw = questionary.text(
        "Tenants adicionais (tenant:token, vírgula — opcional):",
        default=", ".join(
            f"{a.get('account','')}:{a.get('token','')}"
            for a in ch.get("accounts", []) if a.get("account")
        ),
    ).ask() or ""
    if raw.strip():
        ch["accounts"] = [
            {"account": p.split(":", 1)[0].strip(), "token": p.split(":", 1)[1].strip() if ":" in p else ""}
            for p in raw.split(",") if p.strip()
        ]


_CHANNEL_EDITORS = {
    "telegram": _edit_telegram,
    "whatsapp": _edit_whatsapp,
    "discord":  _edit_discord,
    "slack":    _edit_slack,
    "teams":    _edit_teams,
}


def _section_channels(cfg: dict[str, Any]) -> None:
    """Submenu de canais no estilo OpenClaw — um canal por vez."""
    while True:
        _section_header("Canais", "📡")
        channels_cfg = cfg["channels"]

        rows = [_channel_status_row(n, channels_cfg[n]) for n in CHANNEL_NAMES]
        _show_table("Status dos canais", rows)
        console.print()

        choices = [
            Choice(f"{'✅' if channels_cfg[n].get('enabled') else '○'} {n.capitalize()}", value=n)
            for n in CHANNEL_NAMES
        ] + [Choice("← Voltar", value="__back__")]

        pick = questionary.select("Canal para configurar:", choices=choices).ask()
        if pick is None or pick == "__back__":
            break

        editor = _CHANNEL_EDITORS.get(pick)
        if editor:
            editor(channels_cfg[pick])
        console.print()


# ──────────────────────────────────────────────
# SECTION: Skills
# ──────────────────────────────────────────────

def _section_skills(cfg: dict[str, Any]) -> None:
    _section_header("Skills", "🧩")
    total = len(SKILLS)
    enabled_set = set(cfg.get("skills", []))
    console.print(f"  [{C_CYAN}]{len(enabled_set)}/{total} skills ativas[/{C_CYAN}]\n")

    while True:
        action = questionary.select(
            "Ação:",
            choices=[
                Choice("Ativar / desativar skills", value="toggle"),
                Choice("Ver descrição de uma skill", value="describe"),
                Choice("← Voltar", value="__back__"),
            ],
        ).ask()

        if action is None or action == "__back__":
            break

        if action == "describe":
            pick = questionary.select(
                "Qual skill?",
                choices=sorted(SKILLS.keys()) + ["← Voltar"],
            ).ask()
            if pick and pick != "← Voltar":
                console.print(Panel(describe_skill(pick), title=f"🧩 [bold]{pick}[/bold]", border_style=C_CYAN))

        elif action == "toggle":
            choices = [
                Choice(f"{name}  —  {describe_skill(name)}", value=name, checked=(name in enabled_set))
                for name in sorted(SKILLS.keys())
            ]
            result = questionary.checkbox("Ative/desative (espaço):", choices=choices).ask()
            if result is not None:
                cfg["skills"] = sorted(result)
                enabled_set = set(cfg["skills"])
                console.print(f"  [{C_GREEN}]{len(enabled_set)}/{total} skills ativas.[/{C_GREEN}]")


# ──────────────────────────────────────────────
# SECTION: Gateway
# ──────────────────────────────────────────────

def _section_gateway(cfg: dict[str, Any]) -> None:
    _section_header("Gateway", "🌐")
    gw = cfg["gateway"]
    token_preview = ("***" + str(gw.get("token", ""))[-6:]) if gw.get("token") else "—"
    _show_table("Config atual", [
        ("Host",           str(gw.get("host", "0.0.0.0"))),
        ("Porta",          str(gw.get("port", 8787))),
        ("Token",          token_preview),
        ("Dashboard",      str(gw.get("dashboard_enabled", True))),
    ])
    console.print()

    gw["host"] = questionary.text(
        "Host (0.0.0.0 = público, 127.0.0.1 = local):",
        default=str(gw.get("host", "0.0.0.0")),
        validate=_validate_required("Host"),
    ).ask() or gw["host"]

    gw["port"] = int(questionary.text(
        "Porta:",
        default=str(gw.get("port", 8787)),
        validate=_validate_port,
    ).ask() or gw["port"])

    token_input = questionary.text(
        "Token (Enter = gerar automaticamente):",
        default=str(gw.get("token", "")),
    ).ask()
    gw["token"] = token_input.strip() if token_input and token_input.strip() else secrets.token_urlsafe(32)

    gw["dashboard_enabled"] = questionary.confirm(
        "Dashboard web ativo?", default=gw.get("dashboard_enabled", True),
    ).ask()

    if gw["dashboard_enabled"]:
        console.print(
            f"\n  [{C_GREEN}]Dashboard: http://{gw['host']}:{gw['port']}[/{C_GREEN}]"
        )


# ──────────────────────────────────────────────
# SECTION: MCP (novo — estilo OpenClaw)
# ──────────────────────────────────────────────

def _section_mcp(cfg: dict[str, Any]) -> None:  # noqa: ARG001
    _section_header("MCP — Model Context Protocol", "🔌")

    try:
        from clawlite.mcp import (
            add_server, install_template, list_servers,
            remove_server, search_marketplace, KNOWN_SERVER_TEMPLATES,
        )
    except ImportError:
        console.print(f"  [{C_RED}]Módulo MCP não disponível.[/{C_RED}]")
        return

    while True:
        servers = list_servers()

        if servers:
            rows = [(s["name"], s["url"]) for s in servers]
            _show_table("Servidores configurados", rows)
        else:
            console.print(f"  [{C_GRAY}]Nenhum servidor MCP configurado.[/{C_GRAY}]")
        console.print()

        action = questionary.select(
            "Ação:",
            choices=[
                Choice("Instalar template (filesystem, github…)", value="install"),
                Choice("Adicionar servidor manual", value="add"),
                Choice("Remover servidor", value="remove"),
                Choice("Buscar no marketplace MCP", value="search"),
                Choice("← Voltar", value="__back__"),
            ],
        ).ask()

        if action is None or action == "__back__":
            break

        if action == "install":
            templates = list(KNOWN_SERVER_TEMPLATES.keys())
            pick = questionary.select("Template:", choices=templates + ["← Voltar"]).ask()
            if pick and pick != "← Voltar":
                try:
                    result = install_template(pick)
                    console.print(f"  [{C_GREEN}]✅ Instalado: {result['name']} → {result['url']}[/{C_GREEN}]")
                except ValueError as exc:
                    console.print(f"  [{C_RED}]Erro: {exc}[/{C_RED}]")

        elif action == "add":
            name = questionary.text(
                "Nome do servidor (ex: meu-server):",
                validate=_validate_required("Nome"),
            ).ask()
            if not name:
                continue
            url = questionary.text(
                "URL ou comando (https://... / npx / uvx / python):",
                validate=_validate_required("URL"),
            ).ask()
            if not url:
                continue
            try:
                result = add_server(name.strip(), url.strip())
                console.print(f"  [{C_GREEN}]✅ Adicionado: {result['name']}[/{C_GREEN}]")
            except ValueError as exc:
                console.print(f"  [{C_RED}]Erro: {exc}[/{C_RED}]")

        elif action == "remove":
            if not servers:
                console.print(f"  [{C_GRAY}]Nenhum servidor para remover.[/{C_GRAY}]")
                continue
            names = [s["name"] for s in servers]
            pick = questionary.select("Remover qual?", choices=names + ["← Cancelar"]).ask()
            if pick and pick != "← Cancelar":
                if questionary.confirm(f"Remover '{pick}'?", default=False).ask():
                    remove_server(pick)
                    console.print(f"  [{C_GREEN}]Removido: {pick}[/{C_GREEN}]")

        elif action == "search":
            query = questionary.text("Buscar (Enter = todos):").ask() or ""
            with console.status("Buscando…"):
                results = search_marketplace(query)
            if not results:
                console.print(f"  [{C_GRAY}]Nenhum resultado.[/{C_GRAY}]")
            else:
                t = Table(box=box.SIMPLE, border_style=C_GRAY, show_header=True,
                          header_style=f"bold {C_CYAN}")
                t.add_column("Nome")
                t.add_column("Descrição")
                t.add_column("Fonte")
                for r in results[:20]:
                    t.add_row(r.get("name",""), r.get("description","")[:60], r.get("source",""))
                console.print(t)


# ──────────────────────────────────────────────
# SECTION: Memory / Workspace (novo)
# ──────────────────────────────────────────────

def _section_memory(_cfg: dict[str, Any]) -> None:
    _section_header("Memory & Workspace", "🧠")

    try:
        from clawlite.runtime.session_memory import ensure_memory_layout, semantic_search_memory
        from clawlite.runtime.workspace import init_workspace
    except ImportError:
        console.print(f"  [{C_RED}]Módulo de memória não disponível.[/{C_RED}]")
        return

    ws = Path(init_workspace())
    md_files = sorted(ws.rglob("*.md"))
    daily_files = sorted((ws / "memory").glob("*.md")) if (ws / "memory").exists() else []

    _show_table("Workspace", [
        ("Diretório",   str(ws)),
        ("Arquivos MD", str(len(md_files))),
        ("Diário",      f"{len(daily_files)} arquivo(s)"),
    ])
    console.print()

    action = questionary.select(
        "Ação:",
        choices=[
            Choice("Ver arquivos de identidade (SOUL, USER, AGENTS…)", value="view"),
            Choice("Testar busca semântica", value="search"),
            Choice("Reinicializar workspace (cria arquivos padrão)", value="init"),
            Choice("← Voltar", value="__back__"),
        ],
    ).ask()

    if action == "view":
        for fname in ["AGENTS.md", "SOUL.md", "USER.md", "IDENTITY.md", "MEMORY.md"]:
            fpath = ws / fname
            if fpath.exists():
                console.print(Panel(
                    fpath.read_text(encoding="utf-8")[:800],
                    title=f"[bold]{fname}[/bold]",
                    border_style=C_CYAN,
                ))

    elif action == "search":
        query = questionary.text("Consulta de busca:").ask()
        if query:
            hits = semantic_search_memory(query, max_results=5)
            if hits:
                for h in hits:
                    console.print(Panel(
                        f"[{C_CYAN}]Score: {h.score}[/{C_CYAN}]\n{h.snippet}",
                        title=Path(h.path).name,
                        border_style=C_GRAY,
                    ))
            else:
                console.print(f"  [{C_GRAY}]Nenhum resultado.[/{C_GRAY}]")

    elif action == "init":
        if questionary.confirm("Recriar arquivos padrão (não apaga conteúdo existente)?", default=True).ask():
            ensure_memory_layout()
            console.print(f"  [{C_GREEN}]✅ Workspace inicializado em {ws}[/{C_GREEN}]")


# ──────────────────────────────────────────────
# SECTION: Runtime / Offline (novo)
# ──────────────────────────────────────────────

def _section_runtime(cfg: dict[str, Any]) -> None:
    _section_header("Runtime & Offline", "⚡")
    offline = cfg.setdefault("offline_mode", {})
    ollama  = cfg.setdefault("ollama", {})
    battery = cfg.setdefault("battery_mode", {})

    _show_table("Config atual", [
        ("Fallback Ollama",  str(offline.get("auto_fallback_to_ollama", True))),
        ("Timeout connect.", f"{offline.get('connectivity_timeout_sec', 1.5)}s"),
        ("Modelo Ollama",    ollama.get("model", "llama3.1:8b")),
        ("Modo bateria",     str(battery.get("enabled", False))),
        ("Throttle",         f"{battery.get('throttle_seconds', 6.0)}s"),
    ])
    console.print()

    offline["auto_fallback_to_ollama"] = questionary.confirm(
        "Ativar fallback automático para Ollama quando offline?",
        default=offline.get("auto_fallback_to_ollama", True),
    ).ask()

    if offline["auto_fallback_to_ollama"]:
        timeout_raw = questionary.text(
            "Timeout de conectividade (segundos):",
            default=str(offline.get("connectivity_timeout_sec", 1.5)),
        ).ask() or "1.5"
        try:
            offline["connectivity_timeout_sec"] = float(timeout_raw)
        except ValueError:
            pass

        ollama["model"] = questionary.select(
            "Modelo Ollama padrão:",
            choices=["llama3.1:8b", "qwen2.5:7b", "mistral:7b", "codellama:7b", "outro"],
            default=ollama.get("model", "llama3.1:8b"),
        ).ask() or ollama.get("model", "llama3.1:8b")

        if ollama["model"] == "outro":
            ollama["model"] = questionary.text(
                "Nome do modelo (ex: phi3:mini):",
                validate=_validate_required("Modelo"),
            ).ask() or "llama3.1:8b"

    battery["enabled"] = questionary.confirm(
        "Ativar modo bateria (reduz polling em dispositivos móveis)?",
        default=battery.get("enabled", False),
    ).ask()
    if battery["enabled"]:
        throttle_raw = questionary.text(
            "Throttle (segundos entre polls):",
            default=str(battery.get("throttle_seconds", 6.0)),
        ).ask() or "6.0"
        try:
            battery["throttle_seconds"] = float(throttle_raw)
        except ValueError:
            pass


# ──────────────────────────────────────────────
# SECTION: Cron Jobs (novo)
# ──────────────────────────────────────────────

def _section_cron(_cfg: dict[str, Any]) -> None:
    _section_header("Cron Jobs", "⏰")

    try:
        from clawlite.runtime.conversation_cron import (
            add_cron_job, list_cron_jobs, remove_cron_job,
        )
    except ImportError:
        console.print(f"  [{C_RED}]Módulo de cron não disponível.[/{C_RED}]")
        return

    while True:
        jobs = list_cron_jobs()

        if jobs:
            t = Table(box=box.SIMPLE, border_style=C_GRAY, header_style=f"bold {C_CYAN}")
            t.add_column("ID", style="dim", width=4)
            t.add_column("Nome", style=C_WHITE)
            t.add_column("Canal")
            t.add_column("Intervalo")
            t.add_column("Status")
            for j in jobs:
                status_str = f"[{C_GREEN}]ativo[/{C_GREEN}]" if j.enabled else f"[{C_GRAY}]pausado[/{C_GRAY}]"
                interval_str = _fmt_interval(j.interval_seconds)
                t.add_row(str(j.id), j.name, j.channel, interval_str, status_str)
            console.print(t)
        else:
            console.print(f"  [{C_GRAY}]Nenhum cron job configurado.[/{C_GRAY}]")
        console.print()

        action = questionary.select(
            "Ação:",
            choices=[
                Choice("Criar novo job", value="add"),
                Choice("Remover job", value="remove") if jobs else Choice("Remover job", value="remove", disabled="sem jobs"),
                Choice("← Voltar", value="__back__"),
            ],
        ).ask()

        if action is None or action == "__back__":
            break

        if action == "add":
            name = questionary.text(
                "Nome do job:", validate=_validate_required("Nome"),
            ).ask()
            if not name:
                continue

            channel = questionary.select(
                "Canal:", choices=CHANNEL_NAMES + ["system"],
            ).ask() or "system"

            chat_id = questionary.text(
                "Chat ID (pode ser 'local' para jobs internos):",
                default="local",
            ).ask() or "local"

            text = questionary.text(
                "Comando/texto a executar:", validate=_validate_required("Texto"),
            ).ask()
            if not text:
                continue

            interval_raw = questionary.text(
                "Intervalo em segundos (3600 = 1h, 86400 = 1d):",
                default="3600",
                validate=_validate_interval,
            ).ask() or "3600"

            job_id = add_cron_job(
                channel=channel,
                chat_id=chat_id,
                thread_id="",
                label="cron",
                name=name.strip(),
                text=text.strip(),
                interval_seconds=int(interval_raw),
                enabled=True,
            )
            console.print(f"  [{C_GREEN}]✅ Job #{job_id} criado: {name}[/{C_GREEN}]")

        elif action == "remove":
            if not jobs:
                continue
            job_names = [f"#{j.id} {j.name} ({j.channel})" for j in jobs]
            pick_str = questionary.select("Remover qual?", choices=job_names + ["← Cancelar"]).ask()
            if not pick_str or pick_str == "← Cancelar":
                continue
            job_id_pick = int(pick_str.split()[0].lstrip("#"))
            if questionary.confirm(f"Remover job #{job_id_pick}?", default=False).ask():
                remove_cron_job(job_id_pick)
                console.print(f"  [{C_GREEN}]Removido job #{job_id_pick}.[/{C_GREEN}]")


def _fmt_interval(seconds: int) -> str:
    if seconds >= 86400:
        return f"{seconds // 86400}d"
    if seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


# ──────────────────────────────────────────────
# SECTION: Agents (novo)
# ──────────────────────────────────────────────

def _section_agents(_cfg: dict[str, Any]) -> None:
    _section_header("Agentes", "🤖")

    try:
        from clawlite.runtime.multiagent import (
            bind_agent, create_agent, list_agent_bindings, list_agents,
        )
    except ImportError:
        console.print(f"  [{C_RED}]Módulo multiagente não disponível.[/{C_RED}]")
        return

    while True:
        agents = list_agents()

        if agents:
            t = Table(box=box.SIMPLE, border_style=C_GRAY, header_style=f"bold {C_CYAN}")
            t.add_column("ID", style="dim", width=4)
            t.add_column("Nome", style=C_WHITE)
            t.add_column("Canal")
            t.add_column("Role")
            t.add_column("Orch?")
            t.add_column("Status")
            for a in agents:
                orch = f"[{C_ORANGE}]sim[/{C_ORANGE}]" if a.orchestrator else "—"
                status = f"[{C_GREEN}]ativo[/{C_GREEN}]" if a.enabled else f"[{C_GRAY}]inativo[/{C_GRAY}]"
                t.add_row(str(a.id), a.name, a.channel, a.role or "—", orch, status)
            console.print(t)
        else:
            console.print(f"  [{C_GRAY}]Nenhum agente configurado.[/{C_GRAY}]")
        console.print()

        action = questionary.select(
            "Ação:",
            choices=[
                Choice("Criar agente", value="create"),
                Choice("Vincular agente a canal (bind)", value="bind") if agents else Choice("Bind", value="bind", disabled="sem agentes"),
                Choice("Ver vínculos (bindings)", value="bindings"),
                Choice("← Voltar", value="__back__"),
            ],
        ).ask()

        if action is None or action == "__back__":
            break

        if action == "create":
            name = questionary.text(
                "Nome do agente:", validate=_validate_required("Nome"),
            ).ask()
            if not name:
                continue

            channel = questionary.select(
                "Canal principal:", choices=CHANNEL_NAMES,
            ).ask() or "telegram"

            role = questionary.text("Role/especialidade (ex: engenheiro, redator):").ask() or ""
            personality = questionary.text("Personalidade (ex: direto, técnico):").ask() or ""
            account = questionary.text("Conta/token (opcional):").ask() or ""
            orchestrator = questionary.confirm("É orquestrador?", default=False).ask()

            tags_raw = questionary.text(
                "Tags para routing automático (vírgula, ex: bug,code,deploy):",
            ).ask() or ""
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

            agent_id = create_agent(
                name.strip(), channel=channel, role=role,
                personality=personality, account=account,
                orchestrator=orchestrator, tags=tags,
            )
            console.print(f"  [{C_GREEN}]✅ Agente #{agent_id} criado: {name}[/{C_GREEN}]")

        elif action == "bind":
            agent_names = [a.name for a in agents]
            pick = questionary.select("Qual agente?", choices=agent_names + ["← Cancelar"]).ask()
            if not pick or pick == "← Cancelar":
                continue
            extra_channel = questionary.select("Canal adicional:", choices=CHANNEL_NAMES).ask() or "slack"
            extra_account = questionary.text("Conta nesse canal:").ask() or ""
            bind_agent(pick, channel=extra_channel, account=extra_account)
            console.print(f"  [{C_GREEN}]✅ {pick} vinculado a {extra_channel}/{extra_account}[/{C_GREEN}]")

        elif action == "bindings":
            bindings = list_agent_bindings()
            if bindings:
                t = Table(box=box.SIMPLE, border_style=C_GRAY, header_style=f"bold {C_CYAN}")
                t.add_column("ID", style="dim", width=4)
                t.add_column("Agente")
                t.add_column("Canal")
                t.add_column("Conta")
                for b in bindings:
                    t.add_row(str(b["id"]), b["name"], b["channel"], b["account"])
                console.print(t)
            else:
                console.print(f"  [{C_GRAY}]Nenhum vínculo.[/{C_GRAY}]")
            questionary.press_any_key_to_continue("Enter para voltar…").ask()


# ──────────────────────────────────────────────
# SECTION: Hooks
# ──────────────────────────────────────────────

def _section_hooks(cfg: dict[str, Any]) -> None:
    _section_header("Hooks", "🪝")
    h = cfg.setdefault("hooks", {})
    _show_table("Config atual", [
        ("boot",           str(h.get("boot", True))),
        ("session_memory", str(h.get("session_memory", True))),
        ("command_logger", str(h.get("command_logger", False))),
    ])
    console.print()

    selected = questionary.checkbox(
        "Hooks ativos (espaço para marcar):",
        choices=[
            Choice("boot  — executa setup ao iniciar", value="boot",
                   checked=h.get("boot", True)),
            Choice("session-memory  — persiste contexto entre sessões", value="session_memory",
                   checked=h.get("session_memory", True)),
            Choice("command-logger  — registra todos os comandos executados", value="command_logger",
                   checked=h.get("command_logger", False)),
        ],
    ).ask() or []

    cfg["hooks"] = {
        "boot":           "boot"           in selected,
        "session_memory": "session_memory" in selected,
        "command_logger": "command_logger" in selected,
    }


# ──────────────────────────────────────────────
# SECTION: Web Tools
# ──────────────────────────────────────────────

def _section_web_tools(cfg: dict[str, Any]) -> None:
    _section_header("Web Tools", "🔍")
    wt = cfg.setdefault("web_tools", {})
    wt.setdefault("web_search", {"enabled": True, "provider": "brave"})
    wt.setdefault("reddit", {"enabled": False, "subreddits": []})
    wt.setdefault("threads", {"enabled": False, "username": ""})

    _show_table("Config atual", [
        ("Web Search",  f"{wt['web_search'].get('provider', '—')} · {'ativo' if wt['web_search'].get('enabled') else 'inativo'}"),
        ("Reddit",      "ativo" if wt["reddit"].get("enabled") else "inativo"),
        ("Threads",     wt["threads"].get("username", "") or "inativo"),
    ])
    console.print()

    selected = questionary.checkbox(
        "Ferramentas web ativas:",
        choices=[
            Choice("web-search", value="web_search", checked=wt["web_search"].get("enabled", True)),
            Choice("reddit",     value="reddit",     checked=wt["reddit"].get("enabled", False)),
            Choice("threads",    value="threads",    checked=wt["threads"].get("enabled", False)),
        ],
    ).ask() or []

    wt["web_search"]["enabled"] = "web_search" in selected
    wt["reddit"]["enabled"]     = "reddit"     in selected
    wt["threads"]["enabled"]    = "threads"    in selected

    if wt["web_search"]["enabled"]:
        wt["web_search"]["provider"] = questionary.select(
            "Provider do web search:",
            choices=["brave", "duckduckgo", "serpapi", "google"],
            default=wt["web_search"].get("provider", "brave"),
        ).ask() or "brave"

    if wt["reddit"]["enabled"]:
        subs = questionary.text(
            "Subreddits (vírgula):",
            default=", ".join(wt["reddit"].get("subreddits", ["selfhosted", "Python"])),
        ).ask() or ""
        wt["reddit"]["subreddits"] = [s.strip() for s in subs.split(",") if s.strip()]

    if wt["threads"]["enabled"]:
        wt["threads"]["username"] = questionary.text(
            "Usuário do Threads:", default=wt["threads"].get("username", ""),
        ).ask() or ""


# ──────────────────────────────────────────────
# SECTION: Security
# ──────────────────────────────────────────────

def _section_security(cfg: dict[str, Any]) -> None:
    _section_header("Security", "🔒")
    sec = cfg.setdefault("security", {})
    pairing_cfg = sec.get("pairing", {}) if isinstance(sec.get("pairing"), dict) else {}
    token = str(cfg.get("gateway", {}).get("token", "")).strip()

    _show_table("Config atual", [
        ("Token gateway",      ("✅ configurado" if token else "⚠️  ausente")),
        ("Shell exec",         str(sec.get("allow_shell_exec", True))),
        ("Redact tokens logs", str(sec.get("redact_tokens_in_logs", True))),
        ("Require token",      str(sec.get("require_gateway_token", True))),
        ("Pairing",            str(pairing_cfg.get("enabled", False))),
    ])
    console.print()

    selected = questionary.checkbox(
        "Políticas de segurança:",
        choices=[
            Choice("allow-shell-exec  — permite execução de shell pelo agente",
                   value="allow_shell_exec",
                   checked=sec.get("allow_shell_exec", True)),
            Choice("redact-tokens-in-logs  — oculta tokens em logs",
                   value="redact_tokens_in_logs",
                   checked=sec.get("redact_tokens_in_logs", True)),
            Choice("require-gateway-token  — exige auth Bearer no gateway",
                   value="require_gateway_token",
                   checked=sec.get("require_gateway_token", True)),
            Choice("pairing-enabled  — exige aprovação por código para remetentes novos",
                   value="pairing_enabled",
                   checked=pairing_cfg.get("enabled", False)),
        ],
    ).ask() or []

    ttl_default = pairing_cfg.get("code_ttl_seconds", 86400)
    ttl_raw = questionary.text(
        "TTL do código de pairing (segundos):",
        default=str(ttl_default),
        validate=lambda v: str(v).strip().isdigit() and int(str(v).strip()) > 0 or "Informe inteiro > 0",
    ).ask() or str(ttl_default)

    cfg["security"] = {
        "allow_shell_exec":       "allow_shell_exec"       in selected,
        "redact_tokens_in_logs":  "redact_tokens_in_logs"  in selected,
        "require_gateway_token":  "require_gateway_token"  in selected,
        "pairing": {
            "enabled": "pairing_enabled" in selected,
            "code_ttl_seconds": int(ttl_raw),
        },
        "rbac": sec.get("rbac", {"viewer_tokens": []}),
        "tool_policies": sec.get("tool_policies", {}),
    }

    # Auto-gerar token se necessário
    if cfg["security"]["require_gateway_token"] and not token:
        new_token = secrets.token_urlsafe(32)
        cfg.setdefault("gateway", {})["token"] = new_token
        console.print(f"\n  [{C_GREEN}]Token gerado automaticamente.[/{C_GREEN}]")
        console.print(f"  [{C_CYAN}]Token: {new_token}[/{C_CYAN}]")


# ──────────────────────────────────────────────
# SECTION: Identity (novo — também usado no onboarding)
# ──────────────────────────────────────────────

def _section_identity(cfg: dict[str, Any]) -> None:
    _section_header("Identity — Personalidade do Assistente", "🦊")
    _show_table("Config atual", [
        ("Nome",         cfg.get("assistant_name", "ClawLite Assistant")),
        ("Temperamento", cfg.get("assistant_temperament", "técnico e direto")),
        ("Seu nome",     cfg.get("user_name", "—")),
    ])
    console.print()

    name = questionary.text(
        "Nome do assistente:",
        default=cfg.get("assistant_name", "ClawLite Assistant"),
        validate=lambda v: bool(str(v).strip()) or "Nome obrigatório.",
    ).ask()
    if name:
        cfg["assistant_name"] = name.strip()

    temperament = questionary.select(
        "Temperamento:",
        choices=[
            "Técnico e direto",
            "Calmo e didático",
            "Rápido e pragmático",
            "Criativo e amigável",
            "Formal e profissional",
        ],
        default=cfg.get("assistant_temperament", "Técnico e direto"),
    ).ask()
    if temperament:
        cfg["assistant_temperament"] = temperament

    user_name = questionary.text(
        "Seu nome:",
        default=cfg.get("user_name", ""),
    ).ask()
    if user_name is not None:
        cfg["user_name"] = user_name.strip()


# ──────────────────────────────────────────────
# SECTION: Notifications (novo)
# ──────────────────────────────────────────────

def _section_notifications(cfg: dict[str, Any]) -> None:
    _section_header("Notifications", "🔔")
    n = cfg.setdefault("notifications", {})
    _show_table("Config atual", [
        ("Ativo",           str(n.get("enabled", True))),
        ("Janela de dedupe", f"{n.get('dedupe_window_seconds', 300)}s"),
    ])
    console.print()

    n["enabled"] = questionary.confirm(
        "Ativar notificações?", default=n.get("enabled", True),
    ).ask()

    if n["enabled"]:
        dedupe_raw = questionary.text(
            "Janela de deduplicação (segundos — evita spam de alertas repetidos):",
            default=str(n.get("dedupe_window_seconds", 300)),
            validate=_validate_interval,
        ).ask() or "300"
        n["dedupe_window_seconds"] = int(dedupe_raw)


# ──────────────────────────────────────────────
# SECTION: Language
# ──────────────────────────────────────────────

def _section_language(cfg: dict[str, Any]) -> None:
    _section_header("Language", "🌍")
    default_lang = cfg.get("language") or detect_language("pt-br")
    cfg["language"] = questionary.select(
        "Idioma da interface:",
        choices=[
            Choice("PT-BR — Português (Brasil)", value="pt-br"),
            Choice("EN — English",               value="en"),
            Choice("ES — Español",               value="es"),
        ],
        default=default_lang,
    ).ask() or default_lang


# ──────────────────────────────────────────────
# Apply & Restart
# ──────────────────────────────────────────────

def _apply_and_restart(cfg: dict[str, Any]) -> None:
    save_config(cfg)
    pid_file = CONFIG_DIR / "gateway.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGHUP)
            console.print(f"  [{C_GREEN}]✅ Config aplicada. Gateway (PID {pid}) recarregado.[/{C_GREEN}]")
        except (ValueError, ProcessLookupError, PermissionError):
            console.print(f"  [{C_YELLOW}]⚠️  Gateway não está rodando. Inicie com: clawlite start[/{C_YELLOW}]")
    else:
        console.print(f"  [{C_YELLOW}]⚠️  Gateway não detectado. Config salva — inicie com: clawlite start[/{C_YELLOW}]")


# ──────────────────────────────────────────────
# View Config JSON
# ──────────────────────────────────────────────

def _view_config_json(cfg: dict[str, Any]) -> None:
    _section_header("Config JSON", "📄")

    # Ocultar tokens antes de exibir
    import copy
    safe = copy.deepcopy(cfg)
    if safe.get("gateway", {}).get("token"):
        safe["gateway"]["token"] = "***" + safe["gateway"]["token"][-4:]
    for ch in CHANNEL_NAMES:
        if safe.get("channels", {}).get(ch, {}).get("token"):
            safe["channels"][ch]["token"] = "***" + safe["channels"][ch]["token"][-4:]

    console.print(Syntax(json.dumps(safe, ensure_ascii=False, indent=2), "json",
                         theme="monokai", line_numbers=True))
    console.print(f"\n  [{C_GRAY}]Arquivo: {CONFIG_DIR / 'config.json'}[/{C_GRAY}]")
    questionary.press_any_key_to_continue("Enter para voltar…").ask()


# ──────────────────────────────────────────────
# MENU PRINCIPAL
# ──────────────────────────────────────────────

def _build_menu_choices(cfg: dict) -> list[Choice]:
    """Constrói o menu com badges de status ao lado de cada seção."""

    def _row(label: str, status: str, value: str) -> Choice:
        # Formata: "  Model           claude-sonnet-4-6 ✅"
        display = f"{label:<18} {status}"
        return Choice(display, value=value)

    return [
        _row("Model",          _status_model(cfg),          "model"),
        _row("Channels",       _status_channels(cfg),       "channels"),
        _row("Skills",         _status_skills(cfg),         "skills"),
        _row("Gateway",        _status_gateway(cfg),        "gateway"),
        _row("MCP",            _status_mcp(),               "mcp"),
        _row("Memory",         _status_memory(),            "memory"),
        _row("Runtime",        _status_runtime(cfg),        "runtime"),
        _row("Cron Jobs",      _status_cron(),              "cron"),
        _row("Agents",         _status_agents(),            "agents"),
        _row("Hooks",          _status_hooks(cfg),          "hooks"),
        _row("Web Tools",      "–",                         "web_tools"),
        _row("Security",       _status_security(cfg),       "security"),
        _row("Identity",       _status_identity(cfg),       "identity"),
        _row("Notifications",  _status_notifications(cfg),  "notifications"),
        _row("Language",       _status_language(cfg),       "language"),
        Choice("─" * 38,      value="__sep__", disabled=""),
        Choice("📄  View Config JSON",        value="view_json"),
        Choice("🔄  Apply & Restart Gateway", value="apply"),
        Choice("✅  Salvar e sair",           value="save"),
        Choice("❌  Sair sem salvar",         value="exit"),
    ]


_SECTION_MAP = {
    "model":         _section_model,
    "channels":      _section_channels,
    "skills":        _section_skills,
    "gateway":       _section_gateway,
    "mcp":           _section_mcp,
    "memory":        _section_memory,
    "runtime":       _section_runtime,
    "cron":          _section_cron,
    "agents":        _section_agents,
    "hooks":         _section_hooks,
    "web_tools":     _section_web_tools,
    "security":      _section_security,
    "identity":      _section_identity,
    "notifications": _section_notifications,
    "language":      _section_language,
}


def run_configure_menu() -> None:
    cfg = load_config()
    _ensure_defaults(cfg)

    # Ambiente sem TTY
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print(f"[{C_YELLOW}]ℹ️  Ambiente sem TTY. Configuração padrão salva.[/{C_YELLOW}]")
        save_config(cfg)
        return

    _header(
        "⚙️  ClawLite Configure",
        "Use ↑↓ para navegar · Enter para abrir · auto-save por seção",
    )
    console.print()

    while True:
        choices = _build_menu_choices(cfg)
        section = questionary.select(
            "Seção:",
            choices=choices,
            use_shortcuts=False,
        ).ask()

        if section is None or section == "exit":
            console.print(f"[{C_GRAY}]Saindo sem salvar alterações não confirmadas.[/{C_GRAY}]")
            break

        if section == "save":
            save_config(cfg)
            console.print(f"[{C_GREEN}]✅ Configuração salva em {CONFIG_DIR / 'config.json'}[/{C_GREEN}]")
            break

        if section == "apply":
            _apply_and_restart(cfg)
            continue

        if section == "view_json":
            _view_config_json(cfg)
            continue

        if section == "__sep__":
            continue

        fn = _SECTION_MAP.get(section)
        if fn:
            fn(cfg)
            _autosave(cfg)

        console.print()
