from __future__ import annotations

from pathlib import Path

from clawlite.skills.discovery import always_loaded_skills, build_skills_summary, discover_skill_docs


def _write_skill(root: Path, name: str, frontmatter: str, body: str = "# Skill\n") -> None:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(frontmatter + "\n" + body, encoding="utf-8")


def test_discovery_reads_always_and_requires(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_skill(
        tmp_path,
        "always-skill",
        """---
name: always-skill
description: Skill sempre carregada
always: true
requires:
  bins:
    - sh
---""",
    )
    _write_skill(
        tmp_path,
        "env-skill",
        """---
name: env-skill
description: Skill que exige ENV
always: false
requires:
  env:
    - CLAWLITE_TEST_MISSING_ENV
---""",
    )

    rows = discover_skill_docs(tmp_path)
    by_name = {row.name: row for row in rows}

    assert "always-skill" in by_name
    assert by_name["always-skill"].always is True
    assert by_name["always-skill"].available is True

    assert "env-skill" in by_name
    assert by_name["env-skill"].available is False
    assert by_name["env-skill"].requires_env == ["CLAWLITE_TEST_MISSING_ENV"]

    always = always_loaded_skills(tmp_path)
    assert [row.name for row in always] == ["always-skill"]

    summary = build_skills_summary(tmp_path)
    assert "Always-loaded skills:" in summary
    assert "always-skill" in summary
    assert "env-skill: missing-requirements" in summary
