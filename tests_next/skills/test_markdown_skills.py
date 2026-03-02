from __future__ import annotations

from clawlite.core.skills import SkillsLoader


def test_builtin_markdown_skills_are_discoverable() -> None:
    loader = SkillsLoader()
    names = {skill.name for skill in loader.discover()}
    expected = {"cron", "memory", "github", "summarize", "skill-creator", "web-search", "weather", "tmux", "hub"}
    assert expected.issubset(names)
