from __future__ import annotations

import json

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.syntax import Syntax

from clawlite.config.settings import load_config, save_config
from clawlite.runtime.session_memory import ensure_memory_layout
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


def run_onboarding() -> None:
    ensure_memory_layout()
    cfg = load_config()
    _ensure_defaults(cfg)

    steps = [
        ("Idioma", _section_language),
        ("Modelo", _section_model),
        ("Canais", _section_channels),
        ("Perfil de Skills", _skills_quickstart_profile),
        ("Skills", _section_skills),
        ("Hooks", _section_hooks),
        ("Gateway", _section_gateway),
        ("Web Tools", _section_web_tools),
        ("Security", _section_security),
    ]

    console.print(Panel.fit("🚀 Onboarding ClawLite (wizard guiado)", border_style="magenta"))

    with Progress(
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task("Configurando", total=len(steps))
        for name, fn in steps:
            progress.update(task, description=f"Etapa: {name}")
            fn(cfg)
            save_config(cfg)
            progress.advance(task)

    console.print(Panel("Resumo final", border_style="green"))
    console.print(Syntax(json.dumps(cfg, ensure_ascii=False, indent=2), "json", line_numbers=False))

    if questionary.confirm("Concluir onboarding e manter essas configurações?", default=True).ask():
        save_config(cfg)
        console.print("✅ Onboarding concluído. Nada de JSON manual 🙂")
    else:
        console.print("🟡 Onboarding cancelado no final. As alterações já estavam salvas durante o wizard.")
