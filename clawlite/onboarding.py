from __future__ import annotations

import json

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.syntax import Syntax

from clawlite.config.settings import load_config, save_config
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


def run_onboarding() -> None:
    cfg = load_config()
    _ensure_defaults(cfg)

    steps = [
        ("Idioma", _section_language),
        ("Modelo", _section_model),
        ("Canais", _section_channels),
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
