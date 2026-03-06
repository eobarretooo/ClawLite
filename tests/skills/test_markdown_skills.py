from __future__ import annotations

from clawlite.core.skills import SkillsLoader


def test_builtin_markdown_skills_are_discoverable() -> None:
    loader = SkillsLoader()
    names = {skill.name for skill in loader.discover()}
    expected = {
        "coding-agent",
        "cron",
        "memory",
        "gh-issues",
        "github",
        "summarize",
        "skill-creator",
        "web-search",
        "weather",
        "tmux",
        "hub",
        "clawhub",
        "healthcheck",
        "model-usage",
        "session-logs",
    }
    assert expected.issubset(names)
