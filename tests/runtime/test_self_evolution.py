from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import clawlite.runtime.self_evolution as self_evolution_module
from clawlite.runtime.self_evolution import PatchApplicator, SelfEvolutionEngine, Validator


def test_validator_prefers_project_venv_python_for_ruff_and_pytest(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    venv_python = project_root / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("", encoding="utf-8")

    calls: list[tuple[list[str], dict[str, object]]] = []

    def _fake_run(args: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((list(args), dict(kwargs)))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch("clawlite.runtime.self_evolution.subprocess.run", side_effect=_fake_run):
        validator = Validator(project_root)
        ruff_ok, _ = validator.run_ruff()
        pytest_ok, _ = validator.run_pytest()

    assert ruff_ok is True
    assert pytest_ok is True
    assert calls[0][0][:4] == [str(venv_python), "-m", "ruff", "check"]
    assert "--fix" not in calls[0][0]
    assert calls[0][1]["cwd"] == str(project_root)
    assert calls[1][0][:3] == [str(venv_python), "-m", "pytest"]
    assert calls[1][1]["cwd"] == str(project_root)


def test_validator_fails_closed_when_python_executable_is_missing(tmp_path: Path) -> None:
    validator = Validator(tmp_path, python_executable=tmp_path / "missing-python")

    with patch("clawlite.runtime.self_evolution.subprocess.run", side_effect=FileNotFoundError):
        ruff_ok, ruff_output = validator.run_ruff()
        pytest_ok, pytest_output = validator.run_pytest()

    assert ruff_ok is False
    assert "python executable not found" in ruff_output
    assert pytest_ok is False
    assert "python executable not found" in pytest_output


def _build_sample_self_evolution_project(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_root = project_root / "clawlite"
    source_root.mkdir(parents=True, exist_ok=True)
    target_file = source_root / "sample.py"
    original = (
        "def target():\n"
        "    pass\n\n"
        "def sibling():\n"
        "    return 'ok'\n"
    )
    target_file.write_text(original, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(project_root), check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "ClawLite Tests"], cwd=str(project_root), check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tests@clawlite.local"], cwd=str(project_root), check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=str(project_root), check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(project_root), check=True, capture_output=True, text=True)
    return project_root, source_root, target_file, original


def _git_output(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(project_root),
        check=True,
        capture_output=True,
        text=True,
    )
    return (result.stdout or result.stderr).strip()


def _build_validator_wrapper(tmp_path: Path) -> Path:
    wrapper = tmp_path / "validator-python"
    wrapper.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import os",
                "import subprocess",
                "import sys",
                "",
                "args = sys.argv[1:]",
                "if len(args) >= 2 and args[0] == '-m' and args[1] == 'ruff':",
                "    sys.exit(0)",
                "if len(args) >= 2 and args[0] == '-m' and args[1] == 'pytest':",
                "    cmd = [sys.executable, '-m', 'pytest', *args[2:]]",
                "    completed = subprocess.run(cmd, cwd=os.getcwd())",
                "    sys.exit(completed.returncode)",
                "completed = subprocess.run([sys.executable, *args], cwd=os.getcwd())",
                "sys.exit(completed.returncode)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def test_self_evolution_run_once_commits_and_notifies(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, target_file, original = _build_sample_self_evolution_project(tmp_path)
    prompts: list[str] = []
    notices: list[tuple[str, dict[str, object]]] = []

    async def _fake_llm(prompt: str) -> str:
        prompts.append(prompt)
        return (
            "DESCRIPTION: implement target\n"
            "```python\n"
            "def target():\n"
            "    return 42\n"
            "```\n"
        )

    async def _fake_notify(source: str, payload: dict[str, object]) -> None:
        notices.append((source, dict(payload)))

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=_fake_llm,
        notify=_fake_notify,
        enabled=True,
        log_path=tmp_path / "evolution-log.json",
    )
    monkeypatch.setattr(self_evolution_module.Validator, "run_ruff", lambda self: (True, "ok"))
    monkeypatch.setattr(self_evolution_module.Validator, "run_pytest", lambda self: (True, "ok"))

    status = asyncio.run(engine.run_once())

    assert status["last_outcome"] == "committed"
    assert status["committed_count"] == 1
    assert str(status["last_branch"]).startswith("self-evolution/evo-")
    assert prompts and "pydantic v2" in prompts[0]
    assert target_file.read_text(encoding="utf-8") == original
    branch_contents = _git_output(project_root, "show", f"{status['last_branch']}:clawlite/sample.py")
    assert "return 42" in branch_contents
    assert "def sibling()" in branch_contents
    assert notices and notices[0][0] == "self_evolution"
    payload = notices[0][1]
    assert payload["text"] == (
        "[self-evolution] Prepared isolated fix `sample.py:2` (stub_pass)\n"
        "Description: implement target\n"
        f"Branch: {status['last_branch']}\n"
        f"Commit: {payload['metadata']['commit_sha']}  •  ruff ✓  pytest ✓"
    )
    assert payload["status"] == "committed"
    assert payload["summary"] == "self-evolution committed fix for sample.py:2"
    assert payload["metadata"]["gap_file"] == "sample.py"
    assert payload["metadata"]["gap_line"] == 2
    assert payload["metadata"]["gap_kind"] == "stub_pass"
    assert payload["metadata"]["branch_name"] == status["last_branch"]
    assert payload["metadata"]["commit_sha"]
    assert payload["metadata"]["run_id"]
    recent = engine.log.recent(1)[0]
    assert recent["outcome"] == "committed"
    assert recent["commit_sha"] == payload["metadata"]["commit_sha"]
    assert recent["ruff_ok"] is True
    assert recent["pytest_ok"] is True
    assert recent["branch_name"] == status["last_branch"]


def test_self_evolution_supports_branch_prefix_and_approval_notice(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, target_file, original = _build_sample_self_evolution_project(tmp_path)
    notices: list[tuple[str, dict[str, object]]] = []

    async def _fake_llm(prompt: str) -> str:
        del prompt
        return (
            "DESCRIPTION: implement target\n"
            "```python\n"
            "def target():\n"
            "    return 42\n"
            "```\n"
        )

    async def _fake_notify(source: str, payload: dict[str, object]) -> None:
        notices.append((source, dict(payload)))

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=_fake_llm,
        notify=_fake_notify,
        enabled=True,
        branch_prefix="review queue",
        require_approval=True,
        log_path=tmp_path / "evolution-log.json",
    )
    monkeypatch.setattr(self_evolution_module.Validator, "run_ruff", lambda self: (True, "ok"))
    monkeypatch.setattr(self_evolution_module.Validator, "run_pytest", lambda self: (True, "ok"))

    status = asyncio.run(engine.run_once())

    assert status["last_outcome"] == "committed"
    assert status["branch_prefix"] == "review-queue"
    assert status["require_approval"] is True
    assert str(status["last_branch"]).startswith("review-queue/evo-")
    assert target_file.read_text(encoding="utf-8") == original
    payload = notices[0][1]
    assert payload["status"] == "awaiting_approval"
    assert "Awaiting operator approval before merge." in str(payload["text"])
    metadata = dict(payload["metadata"])
    assert metadata["approval_required"] is True
    assert metadata["_telegram_inline_keyboard"][0][0]["callback_data"].startswith("self_evolution:approve:")
    assert metadata["discord_components"][0]["components"][0]["custom_id"].startswith("self_evolution:approve:")


def test_self_evolution_review_run_records_approval_state(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, target_file, original = _build_sample_self_evolution_project(tmp_path)
    notices: list[tuple[str, dict[str, object]]] = []

    async def _fake_llm(prompt: str) -> str:
        del prompt
        return (
            "DESCRIPTION: implement target\n"
            "```python\n"
            "def target():\n"
            "    return 42\n"
            "```\n"
        )

    async def _fake_notify(source: str, payload: dict[str, object]) -> None:
        notices.append((source, dict(payload)))

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=_fake_llm,
        notify=_fake_notify,
        enabled=True,
        branch_prefix="review-queue",
        require_approval=True,
        log_path=tmp_path / "evolution-log.json",
    )
    monkeypatch.setattr(self_evolution_module.Validator, "run_ruff", lambda self: (True, "ok"))
    monkeypatch.setattr(self_evolution_module.Validator, "run_pytest", lambda self: (True, "ok"))

    status = asyncio.run(engine.run_once())
    run_id = str(notices[0][1]["metadata"]["run_id"])

    approved = engine.review_run(run_id, decision="approved", actor="telegram:42", note="owner")
    repeat = engine.review_run(run_id, decision="approved", actor="telegram:42", note="owner")
    rejected = engine.review_run(run_id, decision="rejected", actor="telegram:42", note="owner")

    assert status["require_approval"] is True
    assert approved["ok"] is True
    assert approved["changed"] is True
    assert approved["status"] == "approved"
    assert repeat["ok"] is True
    assert repeat["changed"] is False
    assert rejected["ok"] is False
    assert rejected["error"] == "review_run_already_decided:approved"
    latest = engine.log.get(run_id)
    assert latest is not None
    assert latest["review_status"] == "approved"
    assert latest["reviewed_by"] == "telegram:42"
    assert latest["review_note"] == "owner"
    assert target_file.read_text(encoding="utf-8") == original


def test_patch_applicator_preserves_decorated_neighbor_block(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir(parents=True, exist_ok=True)
    target_file = root / "sample.py"
    target_file.write_text(
        "@first\n"
        "def target():\n"
        "    pass\n\n"
        "@decorator\n"
        "def sibling():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )

    proposal = self_evolution_module.FixProposal(
        gap=self_evolution_module.Gap(file="sample.py", line=3, kind="stub_pass", text="stub"),
        description="implement target",
        patch_unified="def target():\n    return 42\n",
        files_touched=["sample.py"],
    )

    ok, error = PatchApplicator(root).apply(proposal)

    assert ok is True
    assert error == ""
    updated = target_file.read_text(encoding="utf-8")
    assert "def target():\n    return 42\n" in updated
    assert "@decorator\ndef sibling():" in updated


def test_patch_applicator_rejects_header_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir(parents=True, exist_ok=True)
    target_file = root / "sample.py"
    target_file.write_text(
        "def target():\n"
        "    pass\n\n"
        "def sibling():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )

    proposal = self_evolution_module.FixProposal(
        gap=self_evolution_module.Gap(file="sample.py", line=2, kind="stub_pass", text="stub"),
        description="rename target",
        patch_unified="def other():\n    return 42\n",
        files_touched=["sample.py"],
    )

    preview, error = PatchApplicator(root).preview(proposal)

    assert preview is None
    assert error == "proposal_header_mismatch:def:target->def:other"
    assert target_file.read_text(encoding="utf-8").startswith("def target():")


def test_patch_applicator_rejects_invalid_target_path(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir(parents=True, exist_ok=True)
    target_file = root / "sample.py"
    target_file.write_text("def target():\n    pass\n", encoding="utf-8")

    proposal = self_evolution_module.FixProposal(
        gap=self_evolution_module.Gap(file="sample.py", line=2, kind="stub_pass", text="stub"),
        description="escape target",
        patch_unified="def target():\n    return 42\n",
        files_touched=["../escape.py"],
    )

    preview, error = PatchApplicator(root).preview(proposal)

    assert preview is None
    assert error.startswith("proposal_path_invalid:")
    assert target_file.read_text(encoding="utf-8") == "def target():\n    pass\n"


def test_self_evolution_rolls_back_when_pytest_fails(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, target_file, original = _build_sample_self_evolution_project(tmp_path)
    notices: list[tuple[str, dict[str, object]]] = []

    async def _fake_llm(prompt: str) -> str:
        del prompt
        return (
            "DESCRIPTION: implement target\n"
            "```python\n"
            "def target():\n"
            "    return 42\n"
            "```\n"
        )

    async def _fake_notify(source: str, payload: dict[str, object]) -> None:
        notices.append((source, dict(payload)))

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=_fake_llm,
        notify=_fake_notify,
        enabled=True,
        log_path=tmp_path / "evolution-log.json",
    )
    monkeypatch.setattr(self_evolution_module.Validator, "run_ruff", lambda self: (True, "ok"))
    monkeypatch.setattr(self_evolution_module.Validator, "run_pytest", lambda self: (False, "tests failed"))

    def _unexpected_commit(root: Path, files: list[str], message: str) -> tuple[bool, str]:
        del root, files, message
        raise AssertionError("commit_should_not_run")

    monkeypatch.setattr(self_evolution_module, "_commit", _unexpected_commit)

    status = asyncio.run(engine.run_once())

    assert status["last_outcome"] == "validation_failed"
    assert status["committed_count"] == 0
    assert status["last_branch"] == ""
    assert target_file.read_text(encoding="utf-8") == original
    assert notices and notices[0][0] == "self_evolution"
    assert notices[0][1]["status"] == "validation_failed"
    assert "tests FAILED, rolled back" in str(notices[0][1]["text"])
    assert _git_output(project_root, "branch", "--list", "self-evolution/*") == ""
    recent = engine.log.recent(1)[0]
    assert recent["outcome"] == "validation_failed"
    assert recent["commit_sha"] == ""


def test_self_evolution_rolls_back_when_commit_fails(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, target_file, original = _build_sample_self_evolution_project(tmp_path)

    async def _fake_llm(prompt: str) -> str:
        del prompt
        return (
            "DESCRIPTION: implement target\n"
            "```python\n"
            "def target():\n"
            "    return 42\n"
            "```\n"
        )

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=_fake_llm,
        enabled=True,
        log_path=tmp_path / "evolution-log.json",
    )
    monkeypatch.setattr(self_evolution_module.Validator, "run_ruff", lambda self: (True, "ok"))
    monkeypatch.setattr(self_evolution_module.Validator, "run_pytest", lambda self: (True, "ok"))
    monkeypatch.setattr(self_evolution_module, "_commit", lambda root, files, message: (False, "git_user_missing"))

    status = asyncio.run(engine.run_once())

    assert status["last_outcome"] == "error"
    assert "commit_failed: git_user_missing" in str(status["last_error"])
    assert status["last_branch"] == ""
    assert target_file.read_text(encoding="utf-8") == original
    assert _git_output(project_root, "branch", "--list", "self-evolution/*") == ""
    recent = engine.log.recent(1)[0]
    assert recent["outcome"] == "error"
    assert "commit_failed: git_user_missing" in str(recent["error"])


def test_self_evolution_rejects_unsafe_proposal_before_apply(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, target_file, original = _build_sample_self_evolution_project(tmp_path)
    notices: list[tuple[str, dict[str, object]]] = []

    async def _fake_llm(prompt: str) -> str:
        del prompt
        return (
            "DESCRIPTION: replace target with other\n"
            "```python\n"
            "def other():\n"
            "    return 42\n"
            "```\n"
        )

    async def _fake_notify(source: str, payload: dict[str, object]) -> None:
        notices.append((source, dict(payload)))

    def _validator_should_not_run(self) -> tuple[bool, str]:
        raise AssertionError("validator_should_not_run")

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=_fake_llm,
        notify=_fake_notify,
        enabled=True,
        log_path=tmp_path / "evolution-log.json",
    )
    monkeypatch.setattr(self_evolution_module.Validator, "run_ruff", _validator_should_not_run)
    monkeypatch.setattr(self_evolution_module.Validator, "run_pytest", _validator_should_not_run)

    status = asyncio.run(engine.run_once())

    assert status["last_outcome"] == "error"
    assert "proposal_policy_failed:proposal_header_mismatch:def:target->def:other" in str(status["last_error"])
    assert status["last_branch"] == ""
    assert target_file.read_text(encoding="utf-8") == original
    assert notices == []
    assert _git_output(project_root, "branch", "--list", "self-evolution/*") == ""
    recent = engine.log.recent(1)[0]
    assert "proposal_policy_failed" in str(recent["error"])


def test_self_evolution_no_gaps_respects_cooldown_and_force(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, _target_file, _original = _build_sample_self_evolution_project(tmp_path)
    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=None,
        enabled=True,
        cooldown_s=60.0,
        log_path=tmp_path / "evolution-log.json",
    )
    monkeypatch.setattr(self_evolution_module.SourceScanner, "scan", lambda self, max_gaps=20: [])
    monkeypatch.setattr(self_evolution_module.SourceScanner, "scan_roadmap", lambda self, roadmap_path, max_items=5: [])
    monkeypatch.setattr(self_evolution_module.SourceScanner, "scan_reference_gaps", lambda self, catalog_path, max_items=5: [])

    first = asyncio.run(engine.run_once())
    second = asyncio.run(engine.run_once())
    third = asyncio.run(engine.run_once(force=True))

    assert first["last_outcome"] == "no_gaps"
    assert first["run_count"] == 1
    assert second["run_count"] == 1
    assert third["run_count"] == 2
    assert third["last_outcome"] == "no_gaps"
    assert third["last_error"] == ""
    assert third["last_branch"] == ""


def test_self_evolution_first_run_ignores_cooldown_when_monotonic_is_low(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, _target_file, _original = _build_sample_self_evolution_project(tmp_path)
    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=None,
        enabled=True,
        cooldown_s=3600.0,
        log_path=tmp_path / "evolution-log.json",
    )
    monkeypatch.setattr(self_evolution_module.SourceScanner, "scan", lambda self, max_gaps=20: [])
    monkeypatch.setattr(self_evolution_module.SourceScanner, "scan_roadmap", lambda self, roadmap_path, max_items=5: [])
    monkeypatch.setattr(self_evolution_module.SourceScanner, "scan_reference_gaps", lambda self, catalog_path, max_items=5: [])
    monotonic_values = iter([30.0, 30.0, 31.0])
    monkeypatch.setattr(engine, "_now_monotonic", lambda: next(monotonic_values))

    status = asyncio.run(engine.run_once())

    assert status["run_count"] == 1
    assert status["last_outcome"] == "no_gaps"
    assert status["cooldown_remaining_s"] == 3599.0


def test_self_evolution_fails_closed_when_primary_checkout_is_dirty(tmp_path: Path) -> None:
    project_root, source_root, target_file, _original = _build_sample_self_evolution_project(tmp_path)
    target_file.write_text("def target():\n    return 'dirty'\n", encoding="utf-8")

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=lambda prompt: (_ for _ in ()).throw(AssertionError("llm_should_not_run")),
        enabled=True,
        log_path=tmp_path / "evolution-log.json",
    )

    status = asyncio.run(engine.run_once())

    assert status["last_outcome"] == "error"
    assert status["last_error"] == "git_worktree_dirty"
    assert status["last_branch"] == ""
    assert _git_output(project_root, "branch", "--list", "self-evolution/*") == ""


def test_self_evolution_dry_run_reports_preview_without_commit(tmp_path: Path, monkeypatch) -> None:
    project_root, source_root, target_file, original = _build_sample_self_evolution_project(tmp_path)
    notices: list[tuple[str, dict[str, object]]] = []

    async def _fake_llm(prompt: str) -> str:
        assert "sample.py" in prompt
        return (
            "DESCRIPTION: implement target\n"
            "```python\n"
            "def target():\n"
            "    return 42\n"
            "```\n"
        )

    async def _fake_notify(source: str, payload: dict[str, object]) -> None:
        notices.append((source, dict(payload)))

    def _validator_should_not_run(self):
        raise AssertionError("validator_should_not_run")

    monkeypatch.setattr(self_evolution_module.Validator, "run_ruff", _validator_should_not_run)
    monkeypatch.setattr(self_evolution_module.Validator, "run_pytest", _validator_should_not_run)

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=_fake_llm,
        notify=_fake_notify,
        enabled=True,
        log_path=tmp_path / "evolution-log.json",
    )

    status = asyncio.run(engine.run_once(dry_run=True))

    assert status["last_outcome"] == "dry_run"
    assert status["dry_run_count"] == 1
    assert status["committed_count"] == 0
    assert status["last_branch"] == ""
    assert target_file.read_text(encoding="utf-8") == original
    assert _git_output(project_root, "branch", "--list", "self-evolution/*") == ""
    assert notices and notices[0][0] == "self_evolution"
    payload = notices[0][1]
    assert payload["status"] == "dry_run"
    assert payload["summary"] == "self-evolution dry-run for sample.py:2"
    assert payload["metadata"]["dry_run"] is True
    assert "Preview:" in str(payload["text"])
    recent = engine.log.recent(1)[0]
    assert recent["outcome"] == "dry_run"
    assert recent["patch_preview"]


def test_self_evolution_end_to_end_smoke_uses_isolated_branch(tmp_path: Path) -> None:
    project_root, source_root, target_file, original = _build_sample_self_evolution_project(tmp_path)
    tests_dir = project_root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_sample.py").write_text(
        "\n".join(
            [
                "from clawlite.sample import target",
                "",
                "",
                "def test_target_returns_42():",
                "    assert target() == 42",
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(project_root), check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "add smoke test"], cwd=str(project_root), check=True, capture_output=True, text=True)

    async def _fake_llm(prompt: str) -> str:
        assert "sample.py" in prompt
        return (
            "DESCRIPTION: implement target\n"
            "```python\n"
            "def target():\n"
            "    return 42\n"
            "```\n"
        )

    notices: list[tuple[str, dict[str, object]]] = []

    async def _fake_notify(source: str, payload: dict[str, object]) -> None:
        notices.append((source, dict(payload)))

    engine = SelfEvolutionEngine(
        project_root=project_root,
        source_root=source_root,
        run_llm=_fake_llm,
        notify=_fake_notify,
        enabled=True,
        log_path=tmp_path / "evolution-log.json",
    )
    engine._validator.python_executable = str(_build_validator_wrapper(tmp_path))

    status = asyncio.run(engine.run_once())

    assert status["last_outcome"] == "committed"
    assert status["committed_count"] == 1
    assert str(status["last_branch"]).startswith("self-evolution/evo-")
    assert target_file.read_text(encoding="utf-8") == original
    assert "return 42" in _git_output(project_root, "show", f"{status['last_branch']}:clawlite/sample.py")
    assert notices and notices[0][1]["metadata"]["branch_name"] == status["last_branch"]
    recent = engine.log.recent(1)[0]
    assert recent["ruff_ok"] is True
    assert recent["pytest_ok"] is True
