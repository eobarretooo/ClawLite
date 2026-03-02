from __future__ import annotations

from pathlib import Path

from clawlite.core.skills import SkillsLoader


def test_skills_loader_discovers_skill_md(tmp_path: Path) -> None:
    skill_dir = tmp_path / "hello"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello\ndescription: test skill\nalways: true\nrequires: curl,git\n---\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    found = loader.discover()
    assert len(found) == 1
    assert found[0].name == "hello"
    assert found[0].always is True
    assert "curl" in found[0].requires
