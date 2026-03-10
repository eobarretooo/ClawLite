from __future__ import annotations

import json
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
    assert "This file is one-shot only." in prompt

    completed = loader.complete_bootstrap()
    assert completed is True
    assert loader.should_run_bootstrap() is False


def test_workspace_explicit_bootstrap_cycle_api(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()

    assert loader.should_run() is True
    prompt = loader.get_prompt()
    assert "This file is one-shot only." in prompt

    assert loader.complete() is True
    assert not (tmp_path / "ws" / "BOOTSTRAP.md").exists()
    assert loader.should_run() is False


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


def test_workspace_bootstrap_status_and_state_persistence(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()

    initial = loader.bootstrap_status()
    assert initial["pending"] is True
    assert initial["bootstrap_exists"] is True
    assert initial["last_status"] == ""
    assert initial["run_count"] == 0

    assert loader.record_bootstrap_result(status="completed", session_id="cli:bootstrap") is True
    assert loader.complete_bootstrap() is True

    final = loader.bootstrap_status()
    assert final["pending"] is False
    assert final["bootstrap_exists"] is False
    assert final["last_status"] == "completed"
    assert final["run_count"] == 1
    assert final["last_session_id"] == "cli:bootstrap"
    assert final["completed_at"]

    state_payload = json.loads((tmp_path / "ws" / "memory" / "bootstrap-state.json").read_text(encoding="utf-8"))
    assert state_payload["last_status"] == "completed"
    assert state_payload["run_count"] == 1

    onboarding_payload = json.loads((tmp_path / "ws" / "memory" / "onboarding-state.json").read_text(encoding="utf-8"))
    assert onboarding_payload["bootstrap_seeded_at"]
    assert onboarding_payload["onboarding_completed_at"]


def test_workspace_bootstrap_not_recreated_after_completed_state(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()
    assert (tmp_path / "ws" / "BOOTSTRAP.md").exists()

    assert loader.record_bootstrap_result(status="completed", session_id="cli:1") is True
    assert loader.complete_bootstrap() is True

    loader.sync_templates(update_existing=False)
    assert not (tmp_path / "ws" / "BOOTSTRAP.md").exists()


def test_workspace_onboarding_status_marks_legacy_workspace_complete(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()

    identity_path = tmp_path / "ws" / "IDENTITY.md"
    bootstrap_path = tmp_path / "ws" / "BOOTSTRAP.md"
    identity_path.write_text("custom identity", encoding="utf-8")
    bootstrap_path.unlink()

    status = loader.onboarding_status(persist=True)

    assert status["completed"] is True
    assert status["onboarding_completed_at"]

    loader.sync_templates(update_existing=False)
    assert not bootstrap_path.exists()


def test_workspace_runtime_health_repairs_empty_and_corrupt_core_docs(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()

    soul_path = tmp_path / "ws" / "SOUL.md"
    user_path = tmp_path / "ws" / "USER.md"
    soul_path.write_bytes(b"\x00\x01broken")
    user_path.write_text("", encoding="utf-8")

    report = loader.ensure_runtime_files()

    assert report["issues_detected"] == 2
    assert report["repaired_count"] == 2
    assert report["critical_files"]["SOUL.md"]["repaired"] is True
    assert report["critical_files"]["SOUL.md"]["issue"] == "corrupt"
    assert report["critical_files"]["SOUL.md"]["backup_path"]
    assert Path(report["critical_files"]["SOUL.md"]["backup_path"]).exists()
    assert report["critical_files"]["USER.md"]["repaired"] is True
    assert report["critical_files"]["USER.md"]["issue"] == "empty"
    assert "## Core Values" in soul_path.read_text(encoding="utf-8")
    assert "Preferences:" in user_path.read_text(encoding="utf-8")


def test_workspace_system_context_auto_repairs_missing_runtime_docs(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_path=tmp_path / "ws")
    loader.bootstrap()

    soul_path = tmp_path / "ws" / "SOUL.md"
    user_path = tmp_path / "ws" / "USER.md"
    soul_path.unlink()
    user_path.write_text("", encoding="utf-8")

    content = loader.system_context()
    health = loader.runtime_health()

    assert "## SOUL.md" in content
    assert "## USER.md" in content
    assert health["repaired_count"] == 2
    assert health["critical_files"]["SOUL.md"]["repaired"] is True
    assert health["critical_files"]["USER.md"]["repaired"] is True
