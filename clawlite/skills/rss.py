from __future__ import annotations

from clawlite.skills._safe_exec import parse_command, safe_run, require_bin

SKILL_NAME = "rss"
SKILL_DESCRIPTION = 'Agentic RSS digest using the feed CLI. Fetch, triage, and summarize RSS feeds to surface high-signal posts. Use when: (1) reading RSS feeds or catching up on news, (2) user asks for a digest, roundup, or summary of recent posts, (3) user asks what'


def run(command: str = "") -> str:
    """Executa a skill de forma segura (sem shell=True)."""
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    try:
        args = parse_command(command)
    except ValueError as exc:
        return str(exc)
    return safe_run(args)

