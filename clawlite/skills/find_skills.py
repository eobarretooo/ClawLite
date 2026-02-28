from __future__ import annotations

from clawlite.skills._safe_exec import parse_command, safe_run, require_bin

SKILL_NAME = "find-skills"
SKILL_DESCRIPTION = 'Helps users discover and install agent skills when they ask questions like'


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
    return '---\nname: find-skills\ndescription: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.\n---\n# Find Skills\nThis skill helps you discover and install skills from the open agent skills ecosystem.\n## When to Use This Skill\nUse this skill when the user:\n- Asks "how do I do X" where X might be a common task with an existing skill\n- Says "find a skill for X" or "is there a skill for X"\n- Asks "can you do X" where X is a specialized capability\n- Expresses interest in extending agent capabilities\n- Wants to search for tools, templates, or workflows\n- Mentions they wish they had help with a specific domain (design, testing, deployment, etc.)\n## What is the Skills CLI?\nThe Skills CLI (`npx skills`) is the package manager for the open agent skills ecosystem. Skills are modular packages that extend agent capabilities with specialized knowledge, workflows, and tools.\n**Key commands:**\n- `npx skills find [query]` - Search for skills interactively or by keyword\n- `npx skills add <package>` - Install a skill from GitHub or other sources\n- `npx skills check` - Check for skill updates\n- `npx skills update` - Update all installed skills\n**Browse skills at:** https://skills.sh/\n## How to Help Users Find Skills\n### Step 1: Understand What They Need\nWh'
