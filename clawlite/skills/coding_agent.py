from __future__ import annotations

from clawlite.skills._safe_exec import parse_command, safe_run, require_bin

SKILL_NAME = "coding-agent"
SKILL_DESCRIPTION = 'Run Codex CLI, Claude Code, OpenCode, or Pi Coding Agent via background process for programmatic control.'


def run(command: str = "") -> str:
    """Executa a skill de forma segura (sem shell=True)."""
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    try:
        args = parse_command(command)
    except ValueError as exc:
        return str(exc)
    return safe_run(args)


def info() -> str:
    return '---\nname: coding-agent\ndescription: Run Codex CLI, Claude Code, OpenCode, or Pi Coding Agent via background process for programmatic control.\nmetadata: {"clawdbot":{"emoji":"🧩","requires":{"anyBins":["claude","codex","opencode","pi"]}}}\n---\n# Coding Agent (background-first)\nUse **bash background mode** for non-interactive coding work. For interactive coding sessions, use the **tmux** skill (always, except very simple one-shot prompts).\n## The Pattern: workdir + background\n```bash\n# Create temp space for chats/scratch work\nSCRATCH=$(mktemp -d)\n# Start agent in target directory ("little box" - only sees relevant files)\nbash workdir:$SCRATCH background:true command:"<agent command>"\n# Or for project work:\nbash workdir:~/project/folder background:true command:"<agent command>"\n# Returns sessionId for tracking\n# Monitor progress\nprocess action:log sessionId:XXX\n# Check if done  \nprocess action:poll sessionId:XXX\n# Send input (if agent asks a question)\nprocess action:write sessionId:XXX data:"y"\n# Kill if needed\nprocess action:kill sessionId:XXX\n```\n**Why workdir matters:** Agent wakes up in a focused directory, doesn\'t wander off reading unrelated files (like your soul.md 😅).\n---\n## Codex CLI\n**Model:** `gpt-5.2-codex` is the default (set in ~/.codex/config.toml)\n### Building/Creating (use --full-auto or --yolo)\n```bash\n# --full-auto: sandboxed but auto-approves in workspace\nbash workdir:~/project background:true command:"codex exec --full-auto \\"Build a snake game with dark theme'
