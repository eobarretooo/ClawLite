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


def test_skills_loader_marks_unavailable_when_requirements_missing(tmp_path: Path) -> None:
    skill_dir = tmp_path / "gh"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: github\n"
        "description: github skill\n"
        "always: false\n"
        'metadata: {"nanobot":{"requires":{"bins":["definitely-not-a-real-bin-xyz"]}}}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    all_rows = loader.discover(include_unavailable=True)
    assert len(all_rows) == 1
    assert all_rows[0].available is False
    assert any(item.startswith("bin:") for item in all_rows[0].missing)

    available = loader.discover(include_unavailable=False)
    assert available == []


def test_skills_loader_always_on_filters_unavailable(tmp_path: Path, monkeypatch) -> None:
    required_env = "TEST_CLAWLITE_SKILL_ENV"
    skill_dir = tmp_path / "always"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: always\n"
        "description: always skill\n"
        "always: true\n"
        f'metadata: {{"nanobot":{{"requires":{{"env":["{required_env}"]}}}}}}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    monkeypatch.delenv(required_env, raising=False)
    assert loader.always_on() == []

    monkeypatch.setenv(required_env, "1")
    rows = loader.always_on()
    assert len(rows) == 1
    assert rows[0].name == "always"


def test_skills_loader_can_load_body_and_render_prompt(tmp_path: Path) -> None:
    skill_dir = tmp_path / "a"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: skill alpha\nalways: true\n---\n\n# Alpha\n\nUse alpha.\n",
        encoding="utf-8",
    )
    loader = SkillsLoader(builtin_root=tmp_path)
    content = loader.load_skill_content("alpha")
    assert content is not None
    assert "Use alpha." in content

    prompt_rows = loader.render_for_prompt()
    assert any("alpha:" in row for row in prompt_rows)
