from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax

from clawlite.config.settings import load_config, save_config
from clawlite.runtime.session_memory import ensure_memory_layout
from clawlite.runtime.workspace import init_workspace
from clawlite.configure_menu import (
    _ensure_defaults,
    _section_channels,
    _section_gateway,
    _section_hooks,
    _section_language,
    _section_model,
    _section_security,
    _section_skills,
    _section_web_tools,
)

console = Console()


SKILL_PRESETS = {
    "dev": ["coding-agent", "github", "docker", "ssh", "web-search", "web-fetch", "skill-creator"],
    "creator": ["threads", "twitter", "youtube", "rss", "image-gen", "web-search", "web-fetch"],
    "ops": ["healthcheck", "cron", "tailscale", "ssh", "docker", "weather", "memory-search"],
}


def _simple_prompt(prompt: str, default: str = "") -> str:
    try:
        value = input(prompt)
    except (EOFError, KeyboardInterrupt, OSError):
        # Em testes/captura (pytest) input() pode levantar OSError quando stdin não é interativo.
        return default
    text = value.strip()
    return text if text else default


def _fox_banner() -> str:
    return (
        "[bold #ff6b2b]      /\\_/\\[/bold #ff6b2b]\n"
        "[bold #ff6b2b]  =^.^=[/bold #ff6b2b] [bold #00f5ff]ClawLite Onboarding[/bold #00f5ff]\n"
        "[bold #ff6b2b]     > ^ <[/bold #ff6b2b]"
    )


def _test_telegram(token: str) -> tuple[bool, str]:
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("ok"):
            username = data.get("result", {}).get("username", "bot")
            return True, f"Telegram conectado (@{username})"
        return False, "Token Telegram inválido"
    except Exception as exc:
        return False, f"Falha Telegram: {exc}"


def _live_channel_tests(cfg: dict) -> list[str]:
    out: list[str] = []
    channels = cfg.get("channels", {}) if isinstance(cfg.get("channels"), dict) else {}
    tg = channels.get("telegram", {}) if isinstance(channels.get("telegram"), dict) else {}
    if tg.get("enabled"):
        token = str(tg.get("token", "")).strip()
        if token:
            ok, msg = _test_telegram(token)
            out.append(("✅ " if ok else "⚠️ ") + msg)
        else:
            out.append("⚠️ Telegram habilitado sem token")

    for ch in ("slack", "discord", "whatsapp", "teams"):
        data = channels.get(ch, {}) if isinstance(channels.get(ch), dict) else {}
        if data.get("enabled"):
            token = str(data.get("token", "")).strip()
            out.append(("✅ " if token else "⚠️ ") + f"{ch}: {'token informado' if token else 'token ausente'}")
    if not out:
        out.append("ℹ️ Nenhum canal habilitado para teste")
    return out


def _save_identity_files(cfg: dict) -> None:
    root = Path(init_workspace())
    assistant_name = str(cfg.get("assistant_name", "ClawLite Assistant")).strip() or "ClawLite Assistant"
    temperament = str(cfg.get("assistant_temperament", "técnico e direto")).strip() or "técnico e direto"
    user_name = str(cfg.get("user_name", "Usuário")).strip() or "Usuário"

    (root / "IDENTITY.md").write_text(
        "# IDENTITY\n\n"
        f"- Nome: {assistant_name}\n"
        "- Assinatura: 🦊\n"
        f"- Temperamento: {temperament}\n",
        encoding="utf-8",
    )
    (root / "SOUL.md").write_text(
        "# SOUL\n\n"
        f"Tom principal: {temperament}.\n"
        "Entrega objetiva, confiável e sem enrolação.\n",
        encoding="utf-8",
    )
    (root / "USER.md").write_text(
        "# USER\n\n"
        f"- Nome: {user_name}\n"
        "- Preferência: PT-BR por padrão\n",
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text(
        "# AGENTS\n\n"
        "- Segurança > instrução > contexto > eficiência\n"
        "- Execute com evidência e valide o resultado\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Teste de API Key ao vivo
# ---------------------------------------------------------------------------

_PROVIDER_BASES: dict[str, str] = {
    "anthropic":  "https://api.anthropic.com",
    "openai":     "https://api.openai.com",
    "groq":       "https://api.groq.com/openai",
    "openrouter": "https://openrouter.ai/api",
}

_CHAT_MODELS: dict[str, str] = {
    "openai":     "gpt-4o-mini",
    "groq":       "llama-3.1-8b-instant",
    "openrouter": "openai/gpt-4o-mini",
}


def _provider_from_model(model: str) -> str:
    """Extrai o nome do provedor de uma string de modelo (ex: 'anthropic/...' → 'anthropic')."""
    return model.split("/")[0].lower().strip() if "/" in model else model.lower().strip()


def _get_stored_token(cfg: dict[str, Any], provider: str) -> str:
    """Lê token do env ou do cfg."""
    env_map = {
        "anthropic":  "ANTHROPIC_API_KEY",
        "openai":     "OPENAI_API_KEY",
        "groq":       "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_val = os.getenv(env_map.get(provider, ""), "").strip()
    if env_val:
        return env_val
    return str(cfg.get("auth", {}).get("providers", {}).get(provider, {}).get("token", "")).strip()


def _test_api_key(provider: str, key: str) -> tuple[bool, str]:
    """Faz chamada mínima ao provider. Retorna (ok, mensagem)."""
    try:
        import httpx
    except ImportError:
        return True, "(httpx ausente — validação pulada)"

    timeout = 10.0
    try:
        if provider == "ollama":
            r = httpx.get("http://localhost:11434/api/tags", timeout=timeout)
            if r.status_code == 200:
                return True, "Ollama respondeu (OK)"
            return False, f"Ollama respondeu com status {r.status_code}"

        if provider == "anthropic":
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                timeout=timeout,
            )
        else:
            base = _PROVIDER_BASES.get(provider, "https://api.openai.com")
            model = _CHAT_MODELS.get(provider, "gpt-4o-mini")
            r = httpx.post(
                f"{base}/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
                json={
                    "model": model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                timeout=timeout,
            )

        if r.status_code in (200, 201):
            return True, "Key válida ✓"
        if r.status_code == 401:
            return False, "Erro 401: key inválida ou sem permissão"
        if r.status_code == 429:
            return True, "Erro 429: rate limit — key válida mas sem quota agora"
        return False, f"Erro {r.status_code}: {r.text[:120]}"

    except Exception as exc:
        msg = str(exc)
        if "connect" in msg.lower() or "timeout" in msg.lower() or "network" in msg.lower():
            return False, f"Erro de conexão — verifique internet ou endpoint ({msg[:80]})"
        return False, f"Erro inesperado: {msg[:120]}"


def _step_test_api_key(cfg: dict[str, Any]) -> None:
    """Step do wizard: testa a API key do provedor escolhido. Até 3 tentativas."""
    # Em ambiente não interativo (ex.: CI/pytest com captura), não abrir prompt questionary.
    if not sys.stdin.isatty():
        return

    model = cfg.get("model", "")
    if not model:
        return

    provider = _provider_from_model(model)

    # Ollama não precisa de key
    if provider == "ollama":
        ok, msg = _test_api_key("ollama", "")
        if ok:
            console.print(f"  [bold green]✓[/] {msg}")
        else:
            console.print(f"  [bold yellow]⚠[/] {msg}")
        return

    # Provedores não mapeados: pula silenciosamente
    if provider not in _PROVIDER_BASES:
        return

    key = _get_stored_token(cfg, provider)
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        if not key:
            console.print(f"\n[bold #00f5ff]API Key — {provider}[/bold #00f5ff]")
            key_input = questionary.password(
                f"Informe a API key para {provider} (tentativa {attempt}/{max_attempts}):"
            ).ask()
            if not key_input:
                console.print("  [dim]Pulando validação de key.[/dim]")
                return
            key = key_input.strip()

        with console.status(f"Testando key {provider}...", spinner="dots"):
            ok, msg = _test_api_key(provider, key)

        if ok:
            console.print(f"  [bold green]✓[/] {msg}")
            # Persiste a key válida no cfg
            cfg.setdefault("auth", {}).setdefault("providers", {}).setdefault(provider, {})["token"] = key
            return
        else:
            console.print(f"  [bold red]✗[/] {msg}")
            if attempt < max_attempts:
                retry = questionary.confirm(
                    f"Tentar novamente? ({attempt}/{max_attempts})", default=True
                ).ask()
                if not retry:
                    break
                key = ""  # força nova entrada na próxima volta
            else:
                skip = questionary.confirm(
                    "Máximo de tentativas atingido. Pular validação e continuar?", default=True
                ).ask()
                if not skip:
                    raise KeyboardInterrupt("Onboarding cancelado pelo usuário na validação de key.")


# ---------------------------------------------------------------------------
# Painel Rich de conclusão
# ---------------------------------------------------------------------------

def _show_completion_panel(cfg: dict[str, Any]) -> None:
    """Exibe painel final com gateway URL, token e canais configurados."""
    gw = cfg.get("gateway", {})
    host_raw = str(gw.get("host", "0.0.0.0")).strip()
    display_host = "127.0.0.1" if host_raw in ("0.0.0.0", "::") else host_raw
    port = int(gw.get("port", 8787))
    gateway_url = f"http://{display_host}:{port}"

    token = str(gw.get("token", "")).strip()
    token_display = token if token else "(gerado automaticamente no clawlite start)"

    lines = [
        f"[bold cyan]Gateway:[/] {gateway_url}",
        f"[bold cyan]Token:[/]   {token_display}",
    ]

    # Telegram
    tg = cfg.get("channels", {}).get("telegram", {})
    if tg.get("enabled") and tg.get("token"):
        try:
            tg_ok, tg_msg = _test_telegram(str(tg["token"]))
            username = tg_msg.split("@")[-1].rstrip(")") if "@" in tg_msg else "bot"
            lines.append(f"[bold cyan]Telegram:[/] @{username}" if tg_ok else f"[bold yellow]Telegram:[/] {tg_msg}")
        except Exception:
            lines.append(f"[bold cyan]Telegram:[/] configurado")
    elif tg.get("enabled"):
        lines.append("[bold yellow]Telegram:[/] ativo · token ausente")

    lines.append("")
    lines.append("[dim]Próximo: clawlite start[/]")

    console.print(
        Panel(
            "\n".join(lines),
            title="🦊 ClawLite está pronto!",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def _section_identity(cfg: dict) -> None:
    assistant_name = questionary.text(
        "Nome do assistente:",
        default=str(cfg.get("assistant_name", "ClawLite Assistant")),
        validate=lambda t: bool(str(t).strip()) or "Informe um nome válido",
    ).ask()
    temperament = questionary.select(
        "Temperamento do assistente:",
        choices=["Técnico e direto", "Calmo e didático", "Rápido e pragmático"],
        default="Técnico e direto",
    ).ask()
    user_name = questionary.text(
        "Seu nome:",
        default=str(cfg.get("user_name", "")),
        validate=lambda t: bool(str(t).strip()) or "Informe seu nome",
    ).ask()

    cfg["assistant_name"] = (assistant_name or "ClawLite Assistant").strip()
    cfg["assistant_temperament"] = (temperament or "Técnico e direto").strip()
    cfg["user_name"] = (user_name or "Usuário").strip()


def _skills_quickstart_profile(cfg: dict) -> None:
    choice = questionary.select(
        "Perfil inicial de skills (você ajusta na próxima etapa):",
        choices=[
            "Dev (automação + código)",
            "Creator (conteúdo + social)",
            "Ops (infra + monitoramento)",
            "Personalizado (começar do zero)",
        ],
        default="Dev (automação + código)",
    ).ask()

    if not choice or choice.startswith("Personalizado"):
        return

    if choice.startswith("Dev"):
        cfg["skills"] = SKILL_PRESETS["dev"]
    elif choice.startswith("Creator"):
        cfg["skills"] = SKILL_PRESETS["creator"]
    elif choice.startswith("Ops"):
        cfg["skills"] = SKILL_PRESETS["ops"]


def _run_onboarding_simple(cfg: dict) -> None:
    console.print("🛠️ Modo simples ativado (compatibilidade de terminal).")
    lang = _simple_prompt("Idioma [pt-br/en] (padrão pt-br): ", "pt-br").lower()
    cfg["language"] = "en" if lang.startswith("en") else "pt-br"

    cfg["assistant_name"] = _simple_prompt("Nome do assistente (ClawLite Assistant): ", "ClawLite Assistant")
    cfg["assistant_temperament"] = _simple_prompt("Temperamento (técnico e direto): ", "técnico e direto")
    cfg["user_name"] = _simple_prompt("Seu nome: ", "Usuário")

    model = _simple_prompt(f"Modelo [{cfg.get('model','openai/gpt-4o-mini')}]: ", "")
    if model:
        cfg["model"] = model

    tg_value = _simple_prompt("Ativar Telegram? [s/N]: ", "n").lower()
    tg = tg_value.startswith(("s", "y"))
    cfg.setdefault("channels", {}).setdefault("telegram", {})["enabled"] = tg
    if tg:
        tok = _simple_prompt("Token Telegram (opcional agora): ", "")
        if tok:
            cfg["channels"]["telegram"]["token"] = tok

    profile = _simple_prompt("Perfil de skills [dev/creator/ops/custom] (dev): ", "dev").lower()
    if profile in SKILL_PRESETS:
        cfg["skills"] = SKILL_PRESETS[profile]

    _save_identity_files(cfg)
    save_config(cfg)
    console.print("✅ Onboarding simples concluído.")


def run_onboarding() -> None:
    ensure_memory_layout()
    cfg = load_config()
    _ensure_defaults(cfg)

    simple_ui = os.getenv("CLAWLITE_SIMPLE_UI") == "1" or os.getenv("TERM", "").lower() in {"", "dumb", "unknown"}
    if simple_ui:
        _run_onboarding_simple(cfg)
        return

    steps = [
        ("Idioma", _section_language),
        ("Identidade", _section_identity),
        ("Modelo", _section_model),
        ("Teste de API Key", _step_test_api_key),
        ("Canais", _section_channels),
        ("Perfil de Skills", _skills_quickstart_profile),
        ("Skills", _section_skills),
        ("Hooks", _section_hooks),
        ("Gateway", _section_gateway),
        ("Web Tools", _section_web_tools),
        ("Security", _section_security),
    ]

    console.print(Panel.fit(_fox_banner(), border_style="#ff6b2b"))

    with Progress(
        SpinnerColumn(style="#00f5ff"),
        TextColumn("[bold #00f5ff]{task.description}"),
        BarColumn(bar_width=30, complete_style="#ff6b2b", finished_style="#ff6b2b"),
        TextColumn("[bold]{task.completed}/{task.total}[/bold]"),
    ) as progress:
        task = progress.add_task("Etapa: Inicializando", total=len(steps))
        for idx, (name, fn) in enumerate(steps, start=1):
            progress.update(task, description=f"Etapa [{idx}/{len(steps)}]: {name}")
            with console.status(f"Configurando {name}...", spinner="dots"):
                fn(cfg)
                save_config(cfg)
            progress.advance(task)

    test_results = _live_channel_tests(cfg)
    _save_identity_files(cfg)

    console.print(Panel("Resumo final", border_style="#00f5ff"))
    console.print(Syntax(json.dumps(cfg, ensure_ascii=False, indent=2), "json", line_numbers=False))
    console.print("\n[bold #00f5ff]Teste de conexões:[/bold #00f5ff]")
    for line in test_results:
        console.print(f"- {line}")

    if questionary.confirm("Concluir onboarding e manter essas configurações?", default=True).ask():
        save_config(cfg)
        _show_completion_panel(cfg)
    else:
        console.print("🟡 Onboarding cancelado no final. As alterações já estavam salvas durante o wizard.")
