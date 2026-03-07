from __future__ import annotations

import asyncio
import json
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
    assert len(prompt_rows) == 1
    assert "<available_skills>" in prompt_rows[0]
    assert "<name>alpha</name>" in prompt_rows[0]
    assert "<location>" in prompt_rows[0]
    assert "<version>" in prompt_rows[0]


def test_skills_loader_persists_enable_disable_and_pin_state(tmp_path: Path) -> None:
    skill_dir = tmp_path / "alpha"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: skill alpha\nalways: true\n---\n\n# Alpha\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "skills-state.json"

    loader = SkillsLoader(builtin_root=tmp_path, state_path=state_path)
    initial = loader.get("alpha")
    assert initial is not None
    assert initial.enabled is True
    assert initial.pinned is False

    disabled = loader.set_enabled("alpha", False)
    assert disabled is not None
    assert disabled.enabled is False

    pinned = loader.set_pinned("alpha", True)
    assert pinned is not None
    assert pinned.enabled is False
    assert pinned.pinned is True

    reloaded = SkillsLoader(builtin_root=tmp_path, state_path=state_path).get("alpha")
    assert reloaded is not None
    assert reloaded.enabled is False
    assert reloaded.pinned is True
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["entries"]["alpha"]["enabled"] is False
    assert payload["entries"]["alpha"]["pinned"] is True


def test_skills_loader_debounces_skill_file_refreshes(tmp_path: Path) -> None:
    now = {"value": 10.0}

    def _now() -> float:
        return now["value"]

    skill_dir = tmp_path / "alpha"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\nname: alpha\ndescription: first\n---\n\n# Alpha\n",
        encoding="utf-8",
    )
    loader = SkillsLoader(builtin_root=tmp_path, state_path=tmp_path / "skills-state.json", watch_debounce_ms=1000, now_monotonic=_now)

    first = loader.get("alpha")
    assert first is not None
    first_version = first.version

    skill_path.write_text(
        "---\nname: alpha\ndescription: second\n---\n\n# Alpha 2\n",
        encoding="utf-8",
    )

    debounced = loader.get("alpha")
    assert debounced is not None
    assert debounced.version == first_version

    now["value"] += 1.1
    refreshed = loader.get("alpha")
    assert refreshed is not None
    assert refreshed.version != first_version


def test_skills_loader_watcher_refreshes_pending_skill_changes(tmp_path: Path) -> None:
    async def _scenario() -> None:
        skill_dir = tmp_path / "alpha"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(
            "---\nname: alpha\ndescription: first\n---\n\n# Alpha\n",
            encoding="utf-8",
        )

        loader = SkillsLoader(
            builtin_root=tmp_path,
            state_path=tmp_path / "skills-state.json",
            watch_debounce_ms=20,
            watch_interval_s=0.01,
        )
        first = loader.get("alpha")
        assert first is not None
        first_version = first.version

        await loader.start_watcher()
        try:
            skill_path.write_text(
                "---\nname: alpha\ndescription: second\n---\n\n# Alpha 2\n",
                encoding="utf-8",
            )
            for _ in range(30):
                await asyncio.sleep(0.02)
                updated = loader.get("alpha")
                assert updated is not None
                if updated.version != first_version:
                    break
            else:
                raise AssertionError("watcher did not refresh changed skill")

            watcher = loader.watcher_status()
            assert watcher["running"] is True
            assert int(watcher["ticks"]) >= 1
            diagnostics = loader.diagnostics_report()
            assert diagnostics["watcher"]["running"] is True
        finally:
            stopped = await loader.stop_watcher()
            assert stopped["running"] is False

    asyncio.run(_scenario())


def test_skills_loader_watcher_survives_refresh_failure(tmp_path: Path, monkeypatch) -> None:
    async def _scenario() -> None:
        skill_dir = tmp_path / "alpha"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: stable\n---\n\n# Alpha\n",
            encoding="utf-8",
        )

        loader = SkillsLoader(
            builtin_root=tmp_path,
            state_path=tmp_path / "skills-state.json",
            watch_interval_s=0.01,
        )
        loader.get("alpha")

        original_refresh = loader.refresh
        calls = {"count": 0}

        def _flaky_refresh(*, force: bool = False) -> dict[str, object]:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("transient refresh failure")
            return original_refresh(force=force)

        monkeypatch.setattr(loader, "refresh", _flaky_refresh)

        await loader.start_watcher()
        try:
            for _ in range(40):
                await asyncio.sleep(0.02)
                watcher = loader.watcher_status()
                if calls["count"] >= 2 and watcher["last_error"] == "":
                    assert watcher["running"] is True
                    assert watcher["task_state"] == "running"
                    assert watcher["last_result"] in {"idle", "refreshed"}
                    break
            else:
                raise AssertionError("watcher did not recover after refresh failure")
        finally:
            stopped = await loader.stop_watcher()
            assert stopped["running"] is False

    asyncio.run(_scenario())


def test_skills_loader_marks_invalid_execution_contract(tmp_path: Path) -> None:
    skill_dir = tmp_path / "invalid-contract"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: invalid-contract\n"
        "description: invalid binding\n"
        "command: echo hello\n"
        "script: web_search\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    rows = loader.discover(include_unavailable=True)
    assert len(rows) == 1
    assert rows[0].available is False
    assert rows[0].execution_kind == "invalid"
    assert "contract:command_and_script_are_mutually_exclusive" in rows[0].contract_issues


def test_skills_loader_duplicate_policy_prefers_workspace_over_builtin(tmp_path: Path, monkeypatch) -> None:
    builtin = tmp_path / "builtin"
    workspace = tmp_path / ".clawlite" / "workspace" / "skills"
    marketplace = tmp_path / ".clawlite" / "marketplace" / "skills"

    (builtin / "dup").mkdir(parents=True, exist_ok=True)
    (workspace / "dup").mkdir(parents=True, exist_ok=True)
    (marketplace / "dup").mkdir(parents=True, exist_ok=True)

    (builtin / "dup" / "SKILL.md").write_text(
        "---\nname: dup\ndescription: from builtin\n---\n",
        encoding="utf-8",
    )
    (workspace / "dup" / "SKILL.md").write_text(
        "---\nname: dup\ndescription: from workspace\n---\n",
        encoding="utf-8",
    )
    (marketplace / "dup" / "SKILL.md").write_text(
        "---\nname: dup\ndescription: from marketplace\n---\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(tmp_path))
    loader = SkillsLoader(builtin_root=builtin)
    row = loader.get("dup")
    assert row is not None
    assert row.source == "workspace"
    assert row.description == "from workspace"


def test_skills_loader_parses_multiline_metadata_json(tmp_path: Path) -> None:
    skill_dir = tmp_path / "meta"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: meta\n"
        "description: metadata parser\n"
        "metadata: {\n"
        '  "clawlite": {\n'
        '    "requires": {"env": ["TEST_MULTI_ENV"]}\n'
        "  }\n"
        "}\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("meta")
    assert row is not None
    assert "env:TEST_MULTI_ENV" in row.missing


def test_skills_loader_supports_openclaw_any_bins_requirement(tmp_path: Path, monkeypatch) -> None:
    skill_dir = tmp_path / "coding-agent"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: coding-agent\n"
        "description: coding agent\n"
        'metadata: {"openclaw":{"requires":{"anyBins":["missing-a","missing-b"]}}}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    missing = loader.get("coding-agent")
    assert missing is not None
    assert missing.available is False
    assert missing.missing == ["any_bin:missing-a|missing-b"]

    def _fake_which(name: str) -> str | None:
        return "/usr/bin/codex" if name == "missing-b" else None

    monkeypatch.setattr("clawlite.core.skills.shutil.which", _fake_which)
    available = loader.get("coding-agent")
    assert available is not None
    assert available.available is True
    assert available.missing == []


def test_skills_loader_supports_openclaw_primary_env_and_config_requirements(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "channels": {
                    "discord": {"token": "discord-token"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_CONFIG", str(config_path))

    skill_dir = tmp_path / "discord"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: discord\n"
        "description: discord skill\n"
        'metadata: {"openclaw":{"requires":{"config":["channels.discord.token"]},"primaryEnv":"GH_TOKEN"}}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("discord")
    assert row is not None
    assert row.available is False
    assert "env:GH_TOKEN" in row.missing
    assert "config:channels.discord.token" not in row.missing

    monkeypatch.setenv("GH_TOKEN", "token")
    available = loader.get("discord")
    assert available is not None
    assert available.available is True
    assert available.missing == []


def test_skills_loader_normalizes_requirement_schema_and_reports_invalid_env_names(tmp_path: Path) -> None:
    skill_dir = tmp_path / "schema"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: schema\n"
        "description: requirement schema\n"
        'requirements: {"bins": ["python3"], "env": ["GOOD_ENV", "bad-env"], "os": ["Linux"]}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("schema")
    assert row is not None
    assert row.requirements["os"] == ["linux"]
    assert "python3" in row.requirements["bins"]
    assert "GOOD_ENV" in row.requirements["env"]
    assert any(issue.startswith("requirements:invalid_env_name:bad-env") for issue in row.contract_issues)
    assert row.available is False


def test_skills_loader_diagnostics_report_aggregates_deterministically(tmp_path: Path) -> None:
    command_dir = tmp_path / "command-ok"
    command_dir.mkdir(parents=True, exist_ok=True)
    (command_dir / "SKILL.md").write_text(
        "---\n"
        "name: command-ok\n"
        "description: command skill\n"
        "always: true\n"
        "command: sh -c 'echo ok'\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    missing_dir = tmp_path / "missing-reqs"
    missing_dir.mkdir(parents=True, exist_ok=True)
    (missing_dir / "SKILL.md").write_text(
        "---\n"
        "name: missing-reqs\n"
        "description: missing requirements\n"
        'requirements: {"bins": ["definitely-missing-bin-xyz"], "env": ["SKILL_TEST_MISSING_ENV"]}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    invalid_dir = tmp_path / "invalid-contract"
    invalid_dir.mkdir(parents=True, exist_ok=True)
    (invalid_dir / "SKILL.md").write_text(
        "---\n"
        "name: invalid-contract\n"
        "description: invalid contract\n"
        "command: echo hi\n"
        "script: web_search\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    report = loader.diagnostics_report()

    assert set(report.keys()) == {
        "summary",
        "execution_kinds",
        "sources",
        "watcher",
        "missing_requirements",
        "contract_issues",
        "skills",
    }
    assert report["watcher"]["enabled"] is True

    summary = report["summary"]
    assert summary == {
        "total": 3,
        "available": 1,
        "unavailable": 2,
        "enabled": 3,
        "disabled": 0,
        "pinned": 0,
        "runnable": 1,
        "always_on_available": 1,
        "always_on_unavailable": 0,
    }

    assert report["execution_kinds"] == {
        "command": 1,
        "script": 0,
        "none": 1,
        "invalid": 1,
    }
    assert report["sources"] == {
        "builtin": 3,
        "workspace": 0,
        "marketplace": 0,
    }

    missing_requirements = report["missing_requirements"]
    assert missing_requirements["bin"]["count"] == 1
    assert missing_requirements["bin"]["items"] == ["bin:definitely-missing-bin-xyz"]
    assert missing_requirements["env"]["count"] == 1
    assert missing_requirements["env"]["items"] == ["env:SKILL_TEST_MISSING_ENV"]
    assert missing_requirements["os"] == {"count": 0, "items": []}
    assert missing_requirements["other"] == {"count": 0, "items": []}

    contract_issues = report["contract_issues"]
    assert contract_issues["total"] == 1
    assert contract_issues["by_key"] == {
        "contract:command_and_script_are_mutually_exclusive": 1,
    }

    skills = report["skills"]
    assert [row["name"] for row in skills] == ["command-ok", "invalid-contract", "missing-reqs"]
    assert all("version" in row for row in skills)
    assert all("enabled" in row for row in skills)


def test_skills_loader_diagnostics_report_marks_doc_only_as_not_runnable(tmp_path: Path) -> None:
    doc_dir = tmp_path / "docs-only"
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "SKILL.md").write_text(
        "---\nname: docs-only\ndescription: docs\n---\n",
        encoding="utf-8",
    )

    summarize_dir = tmp_path / "summarize"
    summarize_dir.mkdir(parents=True, exist_ok=True)
    (summarize_dir / "SKILL.md").write_text(
        "---\nname: summarize\ndescription: summarize\nscript: summarize\n---\n",
        encoding="utf-8",
    )

    report = SkillsLoader(builtin_root=tmp_path).diagnostics_report()
    by_name = {str(row["name"]): row for row in report["skills"]}

    assert by_name["docs-only"]["runnable"] is False
    assert by_name["docs-only"]["runtime_requirements"] == []
    assert by_name["summarize"]["runnable"] is True
    assert by_name["summarize"]["runtime_requirements"] == ["provider", "tool:web_fetch|read|read_file"]
