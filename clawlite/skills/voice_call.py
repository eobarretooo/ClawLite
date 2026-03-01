from __future__ import annotations

from clawlite.skills._safe_exec import parse_command, safe_run, require_bin

SKILL_NAME = "voice-call"
SKILL_DESCRIPTION = 'Realizar chamadas de voz com IA'


def run(command: str = "") -> str:
    """Executa a skill de forma segura (sem shell=True)."""
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    try:
        args = parse_command(command)
    except ValueError as exc:
        return str(exc)
    return safe_run(args)

