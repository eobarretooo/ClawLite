from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from clawlite.core.agent import run_task_with_meta_async

EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}


def _prompt_sync() -> str:
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.patch_stdout import patch_stdout
    except Exception:
        return input("You: ")

    history_file = Path.home() / ".clawlite" / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(history=FileHistory(str(history_file)), multiline=False)
    with patch_stdout():
        return session.prompt(HTML("<b fg='ansiblue'>You:</b> "))


async def run_agent_once(message: str, *, session_id: str = "cli:direct") -> str:
    text = str(message or "").strip()
    if not text:
        return ""
    output, _meta = await run_task_with_meta_async(text, "", session_id)
    return output


async def run_agent_interactive(
    *,
    session_id: str = "cli:interactive",
    render_markdown: bool = True,
) -> int:
    console = Console()
    console.print("🦊 ClawLite Agent Chat")
    console.print("Digite [bold]exit[/bold] para sair.\n")

    while True:
        try:
            user_input = await asyncio.to_thread(_prompt_sync)
        except (EOFError, KeyboardInterrupt):
            console.print("\nSaindo...")
            return 0

        text = str(user_input or "").strip()
        if not text:
            continue
        if text.lower() in EXIT_COMMANDS:
            console.print("Sessão encerrada.")
            return 0

        output = await run_agent_once(text, session_id=session_id)
        body = Markdown(output) if render_markdown else Text(output)
        console.print()
        console.print("[cyan]ClawLite[/cyan]")
        console.print(body)
        console.print()

