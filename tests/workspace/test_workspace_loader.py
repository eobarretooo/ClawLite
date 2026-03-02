from __future__ import annotations

from pathlib import Path

from clawlite.workspace.loader import WorkspaceLoader


def test_workspace_bootstrap_renders_placeholders(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    created = loader.bootstrap(variables={"assistant_name": "Atlas", "user_name": "Eder"})
    assert created
    identity = (tmp_path / "ws" / "IDENTITY.md").read_text(encoding="utf-8")
    assert "Atlas" in identity
    profile = (tmp_path / "ws" / "USER.md").read_text(encoding="utf-8")
    assert "Eder" in profile


def test_workspace_system_context_includes_core_docs(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()
    content = loader.system_context()
    assert "## IDENTITY.md" in content
    assert "## SOUL.md" in content


def test_workspace_bootstrap_lifecycle(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()

    assert loader.should_run_bootstrap() is True
    prompt = loader.bootstrap_prompt()
    assert "First-run setup checklist" in prompt

    completed = loader.complete_bootstrap()
    assert completed is True
    assert loader.should_run_bootstrap() is False


def test_workspace_sync_templates_is_deterministic(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    first = loader.sync_templates()
    assert first["created"]

    second = loader.sync_templates()
    assert second["created"] == []
    assert second["updated"] == []

    tools_path = tmp_path / "ws" / "TOOLS.md"
    tools_path.write_text("custom", encoding="utf-8")
    third = loader.sync_templates(update_existing=False)
    assert tools_path in third["skipped"]

    fourth = loader.sync_templates(update_existing=True)
    assert tools_path in fourth["updated"]
