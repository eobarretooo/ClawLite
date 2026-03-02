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
