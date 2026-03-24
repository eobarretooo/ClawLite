from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from clawlite.core.skills import SkillsLoader, skills_doctor_report, skills_managed_report, skills_validate_report


class _FakeWatchfiles:
    def __init__(self) -> None:
        self.paths: tuple[str, ...] = ()
        self._queue: asyncio.Queue[set[tuple[int, str]] | None] = asyncio.Queue()

    async def awatch(self, *paths: str, stop_event=None):
        self.paths = tuple(str(path) for path in paths)
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                batch = await asyncio.wait_for(self._queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            if batch is None:
                return
            yield batch

    async def emit(self, *paths: Path) -> None:
        await self._queue.put({(1, str(path)) for path in paths})


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


def test_skills_loader_watcher_refreshes_pending_skill_changes(tmp_path: Path, monkeypatch) -> None:
    async def _scenario() -> None:
        monkeypatch.setitem(sys.modules, "watchfiles", None)
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
            assert watcher["backend"] == "polling"
            assert int(watcher["ticks"]) >= 1
            diagnostics = loader.diagnostics_report()
            assert diagnostics["watcher"]["running"] is True
        finally:
            stopped = await loader.stop_watcher()
            assert stopped["running"] is False

    asyncio.run(_scenario())


def test_skills_loader_watcher_survives_refresh_failure(tmp_path: Path, monkeypatch) -> None:
    async def _scenario() -> None:
        monkeypatch.setitem(sys.modules, "watchfiles", None)
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
                    assert watcher["backend"] == "polling"
                    assert watcher["task_state"] == "running"
                    assert watcher["last_result"] in {"idle", "refreshed"}
                    break
            else:
                raise AssertionError("watcher did not recover after refresh failure")
        finally:
            stopped = await loader.stop_watcher()
            assert stopped["running"] is False

    asyncio.run(_scenario())


def test_skills_loader_watcher_uses_watchfiles_backend_when_available(tmp_path: Path, monkeypatch) -> None:
    async def _scenario() -> None:
        fake_watchfiles = _FakeWatchfiles()
        monkeypatch.setitem(sys.modules, "watchfiles", SimpleNamespace(awatch=fake_watchfiles.awatch))

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
            watch_interval_s=0.5,
        )
        first = loader.get("alpha")
        assert first is not None
        first_version = first.version

        started = await loader.start_watcher()
        assert started["backend"] == "watchfiles"
        try:
            skill_path.write_text(
                "---\nname: alpha\ndescription: second\n---\n\n# Alpha 2\n",
                encoding="utf-8",
            )
            await fake_watchfiles.emit(skill_path)

            for _ in range(40):
                await asyncio.sleep(0.02)
                updated = loader.get("alpha")
                assert updated is not None
                if updated.version != first_version:
                    watcher = loader.watcher_status()
                    assert watcher["running"] is True
                    assert watcher["backend"] == "watchfiles"
                    assert int(watcher["ticks"]) >= 1
                    break
            else:
                raise AssertionError("watchfiles watcher did not refresh changed skill")

            assert fake_watchfiles.paths
            assert str(tmp_path) in fake_watchfiles.paths
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


def test_build_skills_summary_returns_xml(tmp_path: Path) -> None:
    """Summary only includes name + description, not full content."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: Does something useful\n---\n\n# My Skill\n\nFull content here.",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    summary = loader.build_skills_summary()
    assert "<skill" in summary
    assert "my-skill" in summary
    assert "Does something useful" in summary
    # Full body content should NOT be in summary
    assert "Full content here" not in summary


def test_load_skill_full_returns_complete_content(tmp_path: Path) -> None:
    """Full load returns complete SKILL.md content."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: Does something useful\n---\n\n# My Skill\n\nFull content here.",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    full = loader.load_skill_full("my-skill")
    assert "Full content here" in full


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


def test_skills_loader_parses_nested_yaml_metadata(tmp_path: Path) -> None:
    skill_dir = tmp_path / "meta-yaml"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: meta-yaml\n"
        "description: metadata parser yaml\n"
        "metadata:\n"
        "  clawlite:\n"
        "    requires:\n"
        "      env:\n"
        "        - TEST_YAML_ENV\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("meta-yaml")
    assert row is not None
    assert "env:TEST_YAML_ENV" in row.missing


def test_skills_loader_parses_nested_yaml_requirements(tmp_path: Path) -> None:
    skill_dir = tmp_path / "schema-yaml"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: schema-yaml\n"
        "description: requirement schema yaml\n"
        "requirements:\n"
        "  bins:\n"
        "    - python3\n"
        "  env:\n"
        "    - GOOD_ENV\n"
        "    - bad-env\n"
        "  os:\n"
        "    - Linux\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("schema-yaml")
    assert row is not None
    assert row.requirements["os"] == ["linux"]
    assert "python3" in row.requirements["bins"]
    assert "GOOD_ENV" in row.requirements["env"]
    assert any(issue.startswith("requirements:invalid_env_name:bad-env") for issue in row.contract_issues)
    assert row.available is False


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


def test_skills_loader_uses_skill_entries_api_key_for_primary_env(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "skills": {
                    "entries": {
                        "discord": {
                            "apiKey": "injected-gh-token",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_CONFIG", str(config_path))
    monkeypatch.delenv("GH_TOKEN", raising=False)

    skill_dir = tmp_path / "discord"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: discord\n"
        "description: discord skill\n"
        'metadata: {"openclaw":{"primaryEnv":"GH_TOKEN"}}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("discord")
    assert row is not None
    assert row.available is True
    assert row.primary_env == "GH_TOKEN"
    assert loader.resolved_env_overrides(row) == {"GH_TOKEN": "injected-gh-token"}


def test_skills_loader_uses_explicit_config_path_for_skill_entries(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "custom-config.json"
    config_path.write_text(
        json.dumps(
            {
                "skills": {
                    "entries": {
                        "discord": {
                            "apiKey": "from-explicit-config",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("CLAWLITE_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    skill_dir = tmp_path / "discord"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: discord\n"
        "description: discord skill\n"
        'metadata: {"openclaw":{"primaryEnv":"GH_TOKEN"}}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path, config_path=config_path)
    row = loader.get("discord")
    assert row is not None
    assert row.available is True
    assert loader.resolved_env_overrides(row) == {"GH_TOKEN": "from-explicit-config"}


def test_skills_loader_applies_profiled_skill_entries(tmp_path: Path, monkeypatch) -> None:
    base_path = tmp_path / "config.yaml"
    base_path.write_text("skills:\n  entries: {}\n", encoding="utf-8")
    (tmp_path / "config.prod.yaml").write_text(
        "\n".join(
            [
                "skills:",
                "  entries:",
                "    release-helper:",
                "      apiKey: profiled-token",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_CONFIG", str(base_path))
    monkeypatch.setenv("CLAWLITE_PROFILE", "prod")
    monkeypatch.delenv("GH_TOKEN", raising=False)

    skill_dir = tmp_path / "release-helper"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: release-helper\n"
        "description: release helper\n"
        'metadata: {"openclaw":{"primaryEnv":"GH_TOKEN"}}\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("release-helper")
    assert row is not None
    assert row.available is True
    assert loader.resolved_env_overrides(row) == {"GH_TOKEN": "profiled-token"}


def test_skills_loader_respects_config_entry_disable(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "skills": {
                    "entries": {
                        "disabled-skill": {
                            "enabled": False,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_CONFIG", str(config_path))

    skill_dir = tmp_path / "disabled-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: disabled-skill\n"
        "description: disabled by config\n"
        "command: echo ok\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("disabled-skill")
    assert row is not None
    assert row.available is True
    assert row.enabled is False


def test_skills_loader_applies_bundled_allowlist_without_blocking_workspace_override(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "skills": {
                    "allowBundled": ["allowed-skill"],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_CONFIG", str(config_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    builtin = tmp_path / "builtin"
    (builtin / "blocked-skill").mkdir(parents=True, exist_ok=True)
    (builtin / "allowed-skill").mkdir(parents=True, exist_ok=True)
    (builtin / "blocked-skill" / "SKILL.md").write_text(
        "---\nname: blocked-skill\ndescription: blocked bundled skill\ncommand: echo blocked\n---\nbody\n",
        encoding="utf-8",
    )
    (builtin / "allowed-skill" / "SKILL.md").write_text(
        "---\nname: allowed-skill\ndescription: allowed bundled skill\ncommand: echo allowed\n---\nbody\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=builtin)
    blocked = loader.get("blocked-skill")
    allowed = loader.get("allowed-skill")
    assert blocked is not None
    assert blocked.available is False
    assert "policy:bundled_not_allowed" in blocked.missing
    assert allowed is not None
    assert allowed.available is True

    workspace_override = tmp_path / ".clawlite" / "workspace" / "skills" / "blocked-skill"
    workspace_override.mkdir(parents=True, exist_ok=True)
    (workspace_override / "SKILL.md").write_text(
        "---\nname: blocked-skill\ndescription: workspace override\ncommand: echo workspace\n---\nbody\n",
        encoding="utf-8",
    )

    override_loader = SkillsLoader(builtin_root=builtin)
    override_row = override_loader.get("blocked-skill")
    assert override_row is not None
    assert override_row.source == "workspace"
    assert override_row.available is True


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


def test_skills_loader_marks_explicit_empty_name_as_invalid(tmp_path: Path) -> None:
    skill_dir = tmp_path / "fallback-name"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: \"\"\n"
        "description: invalid name\n"
        "command: echo test\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    row = loader.get("fallback-name")
    assert row is not None
    assert row.name == "fallback-name"
    assert "metadata:empty_name" in row.contract_issues
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
        "managed",
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

    managed = report["managed"]
    assert managed == {
        "count": 0,
        "ready_count": 0,
        "blocked_count": 0,
        "disabled_count": 0,
        "status_counts": {},
        "items": [],
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


def test_skills_loader_diagnostics_report_summarizes_managed_marketplace_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    builtin_root = tmp_path / "builtin"
    builtin_root.mkdir(parents=True, exist_ok=True)

    marketplace_root = tmp_path / ".clawlite" / "marketplace" / "skills"
    ready_dir = marketplace_root / "jira-helper"
    ready_dir.mkdir(parents=True, exist_ok=True)
    (ready_dir / "SKILL.md").write_text(
        "---\nname: Jira Helper\ndescription: ready managed skill\n---\nbody\n",
        encoding="utf-8",
    )

    blocked_dir = marketplace_root / "github-helper"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    (blocked_dir / "SKILL.md").write_text(
        "---\n"
        "name: GitHub Helper\n"
        "description: missing env\n"
        'requirements: {"env": ["GH_TOKEN"]}\n'
        "---\nbody\n",
        encoding="utf-8",
    )

    report = SkillsLoader(builtin_root=builtin_root).diagnostics_report()
    managed = report["managed"]

    assert managed["count"] == 2
    assert managed["ready_count"] == 1
    assert managed["blocked_count"] == 1
    assert managed["disabled_count"] == 0
    assert managed["status_counts"] == {"missing_requirements": 1, "ready": 1}
    assert [row["slug"] for row in managed["items"]] == ["github-helper", "jira-helper"]
    assert managed["items"][0]["status"] == "missing_requirements"
    assert "GH_TOKEN" in str(managed["items"][0]["hint"])


def test_skills_managed_report_supports_filters_and_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    builtin_root = tmp_path / "builtin"
    builtin_root.mkdir(parents=True, exist_ok=True)

    ready_dir = tmp_path / ".clawlite" / "marketplace" / "skills" / "jira-helper"
    ready_dir.mkdir(parents=True, exist_ok=True)
    (ready_dir / "SKILL.md").write_text(
        "---\nname: Jira Helper\ndescription: issue tracker helper\ncommand: echo hi\n---\nbody\n",
        encoding="utf-8",
    )

    blocked_dir = tmp_path / ".clawlite" / "marketplace" / "skills" / "github-helper"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    (blocked_dir / "SKILL.md").write_text(
        "---\n"
        "name: GitHub Helper\n"
        "description: github triage\n"
        "metadata:\n"
        "  clawlite:\n"
        "    primaryEnv: GH_TOKEN\n"
        "    requires:\n"
        "      env: [GH_TOKEN]\n"
        "---\nbody\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("GH_TOKEN", raising=False)
    loader = SkillsLoader(builtin_root=builtin_root)
    payload = skills_managed_report(loader, status="missing_requirements", query="github")

    assert payload["ok"] is True
    assert payload["action"] == "managed"
    assert payload["count"] == 1
    assert payload["total_count"] == 2
    assert payload["ready_count"] == 1
    assert payload["blocked_count"] == 1
    assert payload["status_filter"] == "missing_requirements"
    assert payload["query"] == "github"
    assert payload["status_counts"] == {"missing_requirements": 1, "ready": 1}
    assert payload["skills"][0]["slug"] == "github-helper"
    assert "GH_TOKEN" in str(payload["skills"][0]["hint"])


def test_skills_managed_report_keeps_marketplace_rows_when_workspace_shadows_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    builtin_root = tmp_path / "builtin"
    builtin_root.mkdir(parents=True, exist_ok=True)

    workspace_skill = tmp_path / ".clawlite" / "workspace" / "skills" / "jira-helper"
    workspace_skill.mkdir(parents=True, exist_ok=True)
    (workspace_skill / "SKILL.md").write_text(
        "---\nname: Jira Helper\ndescription: workspace override\ncommand: echo workspace\n---\nbody\n",
        encoding="utf-8",
    )

    marketplace_skill = tmp_path / ".clawlite" / "marketplace" / "skills" / "jira-helper-market"
    marketplace_skill.mkdir(parents=True, exist_ok=True)
    (marketplace_skill / "SKILL.md").write_text(
        "---\nname: Jira Helper\ndescription: marketplace copy\ncommand: echo marketplace\n---\nbody\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=builtin_root)
    payload = skills_managed_report(loader)
    report = loader.diagnostics_report()

    assert payload["count"] == 1
    assert payload["total_count"] == 1
    assert payload["skills"][0]["slug"] == "jira-helper-market"
    assert report["managed"]["count"] == 1
    assert report["managed"]["items"][0]["slug"] == "jira-helper-market"


def test_fallback_hint_parsed_from_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "gh-cli"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: gh-cli\n"
        "description: GitHub CLI skill\n"
        "always: false\n"
        "command: __nonexistent_binary_xyz__\n"
        "fallback_hint: Install gh via https://cli.github.com\n"
        "metadata: {\"clawlite\":{\"requires\":{\"bins\":[\"__nonexistent_binary_xyz__\"]}}}\n"
        "---\nUse gh CLI.\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    specs = loader.discover(include_unavailable=True)
    spec = next((s for s in specs if s.name == "gh-cli"), None)
    assert spec is not None
    assert spec.available is False
    assert spec.fallback_hint == "Install gh via https://cli.github.com"

    report = loader.diagnostics_report()
    by_name = {str(row["name"]): row for row in report["skills"]}
    assert by_name["gh-cli"].get("fallback_hint") == "Install gh via https://cli.github.com"


def test_fallback_hint_not_shown_for_available_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "always-available"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: always-available\n"
        "description: Always available skill\n"
        "always: false\n"
        "fallback_hint: Should not appear\n"
        "---\nDocs only.\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(builtin_root=tmp_path)
    specs = loader.discover()
    spec = next((s for s in specs if s.name == "always-available"), None)
    assert spec is not None
    assert spec.available is True
    assert spec.fallback_hint == "Should not appear"  # parsed but...

    report = loader.diagnostics_report()
    by_name = {str(row["name"]): row for row in report["skills"]}
    # fallback_hint should NOT appear in diagnostics for available skills
    assert "fallback_hint" not in by_name["always-available"]


def test_skills_doctor_report_omits_recommendations_for_filtered_out_rows() -> None:
    payload = skills_doctor_report(
        {
            "summary": {},
            "watcher": {},
            "skills": [
                {
                    "name": "github",
                    "skill_key": "github",
                    "primary_env": "GH_TOKEN",
                    "source": "builtin",
                    "enabled": False,
                    "available": False,
                    "missing": ["env:GH_TOKEN"],
                    "contract_issues": [],
                    "runtime_requirements": [],
                }
            ],
        }
    )

    assert payload["ok"] is True
    assert payload["count"] == 0
    assert payload["skills"] == []
    assert payload["recommendations"] == []


def test_skills_validate_report_combines_refresh_and_doctor() -> None:
    class _Loader:
        def refresh(self, *, force: bool = True) -> dict[str, object]:
            return {"ok": True, "refreshed": force, "debounced": not force}

        def diagnostics_report(self) -> dict[str, object]:
            return {
                "summary": {"available": 2, "runnable": 1},
                "watcher": {"task_state": "running", "last_error": ""},
                "contract_issues": {"count": 0},
                "missing_requirements": {"count": 1},
                "skills": [
                    {
                        "name": "github",
                        "skill_key": "github",
                        "source": "builtin",
                        "enabled": True,
                        "available": False,
                        "missing": ["env:GH_TOKEN"],
                        "contract_issues": [],
                        "runtime_requirements": [],
                        "primary_env": "GH_TOKEN",
                    }
                ],
            }

    payload = skills_validate_report(
        _Loader(),
        force=False,
        status="missing_requirements",
        source="builtin",
        query="github",
    )

    assert payload["action"] == "skills_validate"
    assert payload["ok"] is False
    assert payload["refresh"]["refreshed"] is False
    assert payload["refresh"]["debounced"] is True
    assert payload["doctor"]["action"] == "skills_doctor"
    assert payload["status_filter"] == "missing_requirements"
    assert payload["source_filter"] == "builtin"
    assert payload["query"] == "github"
    assert payload["count"] == 1
    assert payload["recommendations"] == [
        "Export GH_TOKEN, set skills.entries.github.apiKey manually, or run clawlite skills config github."
    ]


def test_version_pin_persisted_and_reflected(tmp_path: Path) -> None:
    skill_dir = tmp_path / "mypkg"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: mypkg\ndescription: pkg skill\nalways: false\n---\nBody.\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    loader = SkillsLoader(builtin_root=tmp_path, state_path=state_path)

    spec = loader.get("mypkg")
    assert spec is not None
    assert spec.version_pin == ""

    updated = loader.set_version_pin("mypkg", "1.2.3")
    assert updated is not None
    assert updated.version_pin == "1.2.3"

    # Reload to verify persistence
    loader2 = SkillsLoader(builtin_root=tmp_path, state_path=state_path)
    spec2 = loader2.get("mypkg")
    assert spec2 is not None
    assert spec2.version_pin == "1.2.3"


def test_clear_version_pin(tmp_path: Path) -> None:
    skill_dir = tmp_path / "mypkg"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: mypkg\ndescription: pkg\nalways: false\n---\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    loader = SkillsLoader(builtin_root=tmp_path, state_path=state_path)

    loader.set_version_pin("mypkg", "2.0.0")
    cleared = loader.clear_version_pin("mypkg")
    assert cleared is not None
    assert cleared.version_pin == ""


def test_version_pin_returns_none_for_unknown_skill(tmp_path: Path) -> None:
    loader = SkillsLoader(builtin_root=tmp_path)
    result = loader.set_version_pin("does-not-exist", "1.0")
    assert result is None


def test_version_pin_shown_in_diagnostics_report(tmp_path: Path) -> None:
    skill_dir = tmp_path / "mypkg"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: mypkg\ndescription: pkg\nalways: false\n---\n",
        encoding="utf-8",
    )
    loader = SkillsLoader(builtin_root=tmp_path)
    loader.set_version_pin("mypkg", "3.1.4")

    report = loader.diagnostics_report()
    by_name = {str(row["name"]): row for row in report["skills"]}
    assert by_name["mypkg"]["version_pin"] == "3.1.4"
