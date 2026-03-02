from __future__ import annotations

from pathlib import Path

from clawlite.core.prompt import PromptBuilder


def test_prompt_builder_reads_workspace_files(tmp_path: Path) -> None:
    (tmp_path / "IDENTITY.md").write_text("I am Claw", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("Be direct", encoding="utf-8")

    builder = PromptBuilder(tmp_path)
    out = builder.build(
        user_text="hello",
        memory_snippets=["fact A"],
        history=[{"role": "user", "content": "old"}],
        skills_for_prompt=["cron: schedule tasks"],
    )

    assert "IDENTITY.md" in out.system_prompt
    assert "SOUL.md" in out.system_prompt
    assert "fact A" in out.memory_section
    assert "user: old" in out.history_section
