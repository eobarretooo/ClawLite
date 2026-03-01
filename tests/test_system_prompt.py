from __future__ import annotations

from pathlib import Path

from clawlite.runtime.system_prompt import build_system_prompt


def test_build_system_prompt_contains_sections(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("# AGENTS\nrule", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("# SOUL\ntone", encoding="utf-8")
    (tmp_path / "USER.md").write_text("# USER\nprefs", encoding="utf-8")
    (tmp_path / "IDENTITY.md").write_text("# IDENTITY\nname", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("# MEMORY", encoding="utf-8")
    (tmp_path / "memory").mkdir()

    prompt = build_system_prompt(str(tmp_path))
    assert "[SYSTEM ROLE]" in prompt
    assert "[IDENTITY]" in prompt
    assert "[SOUL]" in prompt
    assert "[AGENTS]" in prompt
    assert "[USER]" in prompt


def test_build_system_prompt_includes_discovered_skills(tmp_path: Path):
    (tmp_path / "skills" / "always-skill").mkdir(parents=True)
    (tmp_path / "skills" / "always-skill" / "SKILL.md").write_text(
        """---
name: always-skill
description: Skill de teste
always: true
---
# Always Skill
""",
        encoding="utf-8",
    )

    prompt = build_system_prompt(str(tmp_path))
    assert "[SKILLS]" in prompt
    assert "always-skill" in prompt
