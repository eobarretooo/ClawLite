from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import httpx

# Keep CLI command tests importable while channel modules are being replaced in
# parallel worktrees. These tests do not exercise WhatsApp channel behavior.
if importlib.util.find_spec("clawlite.channels.whatsapp") is None:
    whatsapp_stub = types.ModuleType("clawlite.channels.whatsapp")

    class _StubWhatsAppChannel:
        pass

    whatsapp_stub.WhatsAppChannel = _StubWhatsAppChannel
    sys.modules["clawlite.channels.whatsapp"] = whatsapp_stub

from clawlite.cli.commands import cmd_provider_login
from clawlite.cli.commands import cmd_provider_logout
from clawlite.cli.commands import docker_preflight_probe
from clawlite.cli.commands import main
from clawlite.cli.ops import fetch_gateway_tool_approval_audit_export
from clawlite.cli.ops import provider_live_probe
from clawlite.channels.telegram_pairing import TelegramPairingStore
from clawlite.config.loader import load_config
from clawlite.core.skills import SkillsLoader
from clawlite.providers.probe_cache import save_provider_probe_snapshot
from clawlite.workspace.loader import TEMPLATE_FILES
from clawlite.workspace.loader import WorkspaceLoader


def test_cli_onboard_generates_workspace_files(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "onboard",
            "--assistant-name",
            "Atlas",
            "--user-name",
            "Eder",
        ]
    )
    assert rc == 0
    assert (tmp_path / "workspace" / "IDENTITY.md").exists()
    content = (tmp_path / "workspace" / "IDENTITY.md").read_text(encoding="utf-8")
    assert "## Name" in content
    assert "self-hosted autonomous AI agent" in content


def test_cli_onboard_wizard_mode_routes_to_runner(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    called: dict[str, bool] = {"ok": False}

    def _fake_wizard(config, *, config_path, config_profile=None, overwrite, variables, flow=None):
        called["ok"] = True
        assert overwrite is True
        assert flow == "quickstart"
        assert config_profile is None
        assert str(config.agents.defaults.model).startswith("openai/")
        assert variables["assistant_name"] == "Fox"
        return {
            "ok": True,
            "mode": "wizard",
            "flow": flow,
            "final": {
                "gateway_url": "http://127.0.0.1:8787",
                "gateway_token": "tok-test-123",
            },
        }

    monkeypatch.setattr("clawlite.cli.commands.run_onboarding_wizard", _fake_wizard)
    rc = main(
        [
            "--config",
            str(config_path),
            "onboard",
            "--wizard",
            "--flow",
            "quickstart",
            "--overwrite",
            "--assistant-name",
            "Fox",
        ]
    )
    assert rc == 0
    assert called["ok"] is True
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "wizard"
    assert payload["flow"] == "quickstart"


def test_cli_configure_routes_flow_override_to_wizard(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    called: dict[str, object] = {"section": None}

    def _fake_flow(console, config, *, config_path, config_profile=None, section=None):
        called["section"] = section
        called["config_profile"] = config_profile
        return {
            "ok": True,
            "visited_sections": [section] if section else [],
            "saved_path": str(config_path),
        }

    monkeypatch.setattr("clawlite.cli.commands.run_configure_flow", _fake_flow)
    rc = main(
        [
            "--config",
            str(config_path),
            "configure",
            "--section",
            "memory",
        ]
    )

    assert rc == 0
    assert called["section"] == "memory"
    assert called["config_profile"] is None
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_cli_configure_flow_compatibility_routes_to_onboarding_wizard(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    called: dict[str, object] = {}

    def _fake_wizard(config, *, config_path, config_profile=None, overwrite=False, flow="quickstart", variables=None):
        called["config_path"] = str(config_path)
        called["config_profile"] = config_profile
        called["overwrite"] = overwrite
        called["flow"] = flow
        called["variables"] = dict(variables or {})
        return {"ok": True, "mode": "wizard", "flow": flow}

    monkeypatch.setattr("clawlite.cli.commands.run_onboarding_wizard", _fake_wizard)

    rc = main([
        "--config",
        str(config_path),
        "configure",
        "--flow",
        "quickstart",
    ])

    assert rc == 0
    assert called["config_path"] == str(config_path)
    assert called["config_profile"] is None
    assert called["overwrite"] is False
    assert called["flow"] == "quickstart"
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "wizard"
    assert payload["flow"] == "quickstart"


def test_cli_configure_flow_compatibility_passes_profile_to_onboarding_wizard(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    called: dict[str, object] = {}

    def _fake_wizard(config, *, config_path, config_profile=None, overwrite=False, flow="quickstart", variables=None):
        del config, overwrite, variables
        called["config_path"] = str(config_path)
        called["config_profile"] = config_profile
        called["flow"] = flow
        return {"ok": True, "mode": "wizard", "flow": flow}

    monkeypatch.setattr("clawlite.cli.commands.run_onboarding_wizard", _fake_wizard)

    rc = main([
        "--config",
        str(config_path),
        "--profile",
        "prod",
        "configure",
        "--flow",
        "quickstart",
    ])

    assert rc == 0
    assert called["config_path"] == str(config_path)
    assert called["config_profile"] == "prod"
    assert called["flow"] == "quickstart"
    capsys.readouterr()


def test_cli_onboard_wizard_mode_passes_profile_to_runner(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    called: dict[str, object] = {}

    def _fake_wizard(config, *, config_path, config_profile=None, overwrite, variables, flow=None):
        del config, overwrite, variables, flow
        called["config_path"] = str(config_path)
        called["config_profile"] = config_profile
        return {
            "ok": True,
            "mode": "wizard",
            "flow": "quickstart",
            "final": {
                "gateway_url": "http://127.0.0.1:8787",
                "gateway_token": "tok-test-123",
            },
        }

    monkeypatch.setattr("clawlite.cli.commands.run_onboarding_wizard", _fake_wizard)
    rc = main(
        [
            "--config",
            str(config_path),
            "--profile",
            "prod",
            "onboard",
            "--wizard",
        ]
    )
    assert rc == 0
    assert called["config_path"] == str(config_path)
    assert called["config_profile"] == "prod"
    capsys.readouterr()


def test_cli_main_reports_runtime_errors_on_stderr(capsys, monkeypatch) -> None:
    def _boom(_args) -> int:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr("clawlite.cli.commands.cmd_status", _boom)

    rc = main(["status"])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "error: synthetic failure" in captured.err


def test_cli_main_adds_yaml_install_hint(capsys, monkeypatch) -> None:
    def _boom(_args) -> int:
        raise RuntimeError("pyyaml is required for YAML config files")

    monkeypatch.setattr("clawlite.cli.commands.cmd_status", _boom)

    rc = main(["status"])

    captured = capsys.readouterr()
    assert rc == 2
    assert "hint:" in captured.err
    assert "python -m pip install pyyaml" in captured.err


def test_cli_skills_list_and_show(capsys) -> None:
    rc_list = main(["skills", "list"])
    assert rc_list == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload.get("skills"), list)
    assert any(item.get("name") == "cron" for item in payload["skills"])
    cron = next(item for item in payload["skills"] if item.get("name") == "cron")
    assert "enabled" in cron
    assert "pinned" in cron
    assert "version" in cron
    assert "skill_key" in cron
    assert "primary_env" in cron

    rc_show = main(["skills", "show", "cron"])
    assert rc_show == 0
    out_show = capsys.readouterr().out
    one = json.loads(out_show)
    assert one.get("name") == "cron"
    assert "Schedule" in one.get("description", "")
    assert "enabled" in one
    assert "pinned" in one
    assert "version" in one
    assert "skill_key" in one
    assert "primary_env" in one


def test_cli_skills_check_returns_diagnostics_report(capsys) -> None:
    rc = main(["skills", "check"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {
        "summary",
        "execution_kinds",
        "sources",
        "watcher",
        "missing_requirements",
        "managed",
        "contract_issues",
        "skills",
    }
    assert payload["watcher"]["enabled"] is True
    assert "count" in payload["managed"]
    assert "status_counts" in payload["managed"]
    summary = payload["summary"]
    assert summary["total"] == summary["available"] + summary["unavailable"]
    assert summary["enabled"] == summary["total"] - summary["disabled"]


def test_cli_skills_config_updates_config_entry_and_preserves_other_skills_keys(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                f"workspace_path: {tmp_path / 'workspace'}",
                f"state_path: {tmp_path / 'state'}",
                "skills:",
                "  allowBundled:",
                "    - cron",
                "",
            ]
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "skills",
            "config",
            "cron",
            "--api-key",
            "secret-token",
            "--env",
            "CRON_TOKEN=from-config",
            "--disable",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "skills_config"
    assert payload["skill_key"] == "cron"
    assert payload["entry"] == {
        "apiKey": "secret-token",
        "env": {"CRON_TOKEN": "from-config"},
        "enabled": False,
    }

    raw = config_path.read_text(encoding="utf-8")
    assert "allowBundled:" in raw
    assert "apiKey: secret-token" in raw
    assert "CRON_TOKEN: from-config" in raw

    rc_show = main(["--config", str(config_path), "skills", "config", "cron"])
    assert rc_show == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["action"] == "skills_config_show"
    assert shown["entry"]["enabled"] is False


def test_cli_skills_config_writes_to_profile_overlay(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "skills": {"allowBundled": ["cron"]},
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "--profile",
            "prod",
            "skills",
            "config",
            "cron",
            "--enable",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["config_path"].endswith("config.prod.json")
    assert payload["entry"] == {"enabled": True}

    base_payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert "entries" not in base_payload["skills"]

    profile_payload = json.loads((tmp_path / "config.prod.json").read_text(encoding="utf-8"))
    assert profile_payload["skills"]["entries"]["cron"]["enabled"] is True


def test_cli_skills_enable_disable_and_pin_unpin(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_disable = main(["--config", str(config_path), "skills", "disable", "cron"])
    assert rc_disable == 0
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["ok"] is True
    assert disabled["action"] == "disable"
    assert disabled["name"] == "cron"
    assert disabled["enabled"] is False

    rc_pin = main(["--config", str(config_path), "skills", "pin", "cron"])
    assert rc_pin == 0
    pinned = json.loads(capsys.readouterr().out)
    assert pinned["ok"] is True
    assert pinned["action"] == "pin"
    assert pinned["pinned"] is True
    assert pinned["enabled"] is False

    rc_show = main(["--config", str(config_path), "skills", "show", "cron"])
    assert rc_show == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["enabled"] is False
    assert shown["pinned"] is True

    rc_enable = main(["--config", str(config_path), "skills", "enable", "cron"])
    assert rc_enable == 0
    enabled = json.loads(capsys.readouterr().out)
    assert enabled["ok"] is True
    assert enabled["action"] == "enable"
    assert enabled["enabled"] is True

    rc_unpin = main(["--config", str(config_path), "skills", "unpin", "cron"])
    assert rc_unpin == 0
    unpinned = json.loads(capsys.readouterr().out)
    assert unpinned["ok"] is True
    assert unpinned["action"] == "unpin"
    assert unpinned["pinned"] is False


def test_cli_skills_install_update_and_sync_use_marketplace_root(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    calls: list[list[str]] = []
    managed_skill = tmp_path / ".clawlite" / "marketplace" / "skills" / "jira-helper"
    managed_skill.mkdir(parents=True, exist_ok=True)
    (managed_skill / "SKILL.md").write_text(
        "---\nname: Jira Helper\ndescription: marketplace skill\n---\nbody\n",
        encoding="utf-8",
    )

    def _fake_which(name: str) -> str | None:
        return "/usr/bin/npx" if name == "npx" else None

    def _fake_run(command: list[str], capture_output: bool, text: bool):
        assert capture_output is True
        assert text is True
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("clawlite.cli.commands.shutil.which", _fake_which)
    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    rc_install = main(["skills", "install", "jira-helper"])
    assert rc_install == 0
    install_payload = json.loads(capsys.readouterr().out)
    assert install_payload["ok"] is True
    assert install_payload["action"] == "install"
    assert install_payload["slug"] == "jira-helper"
    assert install_payload["managed_root"].endswith(".clawlite/marketplace")
    assert install_payload["skills_root"].endswith(".clawlite/marketplace/skills")
    assert install_payload["resolved"]["status"] == "ready"
    assert install_payload["resolved"]["slug"] == "jira-helper"
    assert install_payload["managed_count"] == 1
    assert install_payload["status_counts"] == {"ready": 1}

    rc_update = main(["skills", "update", "Jira Helper"])
    assert rc_update == 0
    update_payload = json.loads(capsys.readouterr().out)
    assert update_payload["ok"] is True
    assert update_payload["action"] == "update"
    assert update_payload["slug"] == "jira-helper"
    assert update_payload["name"] == "Jira Helper"
    assert update_payload["resolved"]["status"] == "ready"
    assert update_payload["managed_count"] == 1
    assert update_payload["status_counts"] == {"ready": 1}

    rc_sync = main(["skills", "sync"])
    assert rc_sync == 0
    sync_payload = json.loads(capsys.readouterr().out)
    assert sync_payload["ok"] is True
    assert sync_payload["action"] == "sync"
    assert sync_payload["managed_count"] == 1
    assert sync_payload["status_counts"] == {"ready": 1}
    assert sync_payload["skills"][0]["slug"] == "jira-helper"

    assert calls[0][-2:] == ["--workdir", str(tmp_path / ".clawlite" / "marketplace")]
    assert calls[1][3:5] == ["update", "jira-helper"]
    assert calls[2][3:5] == ["update", "--all"]


def test_cli_skills_search_uses_clawhub(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    calls: list[list[str]] = []
    managed_skill = tmp_path / ".clawlite" / "marketplace" / "skills" / "discord-helper"
    managed_skill.mkdir(parents=True, exist_ok=True)
    (managed_skill / "SKILL.md").write_text(
        "---\nname: Discord Helper\ndescription: managed discord skill\ncommand: echo hi\n---\nbody\n",
        encoding="utf-8",
    )

    def _fake_which(name: str) -> str | None:
        return "/usr/bin/npx" if name == "npx" else None

    def _fake_run(command: list[str], capture_output: bool, text: bool):
        assert capture_output is True
        assert text is True
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="search ok\n", stderr="")

    monkeypatch.setattr("clawlite.cli.commands.shutil.which", _fake_which)
    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    rc = main(["skills", "search", "discord", "--limit", "3"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "search"
    assert payload["query"] == "discord"
    assert payload["limit"] == 3
    assert payload["managed_count"] == 1
    assert payload["status_counts"] == {"ready": 1}
    assert payload["local_matches"][0]["slug"] == "discord-helper"
    assert calls[0][3:7] == ["search", "discord", "--limit", "3"]


def test_cli_skills_managed_lists_marketplace_entries(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    market_skill = tmp_path / ".clawlite" / "marketplace" / "skills" / "market-echo"
    market_skill.mkdir(parents=True, exist_ok=True)
    (market_skill / "SKILL.md").write_text(
        "---\nname: market-echo\ndescription: marketplace skill\ncommand: echo hi\n---\nbody\n",
        encoding="utf-8",
    )

    rc = main(["skills", "managed"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "managed"
    assert payload["count"] == 1
    assert payload["total_count"] == 1
    assert payload["ready_count"] == 1
    assert payload["blocked_count"] == 0
    assert payload["status_counts"] == {"ready": 1}
    assert payload["skills"][0]["slug"] == "market-echo"
    assert payload["skills"][0]["name"] == "market-echo"
    assert payload["skills"][0]["description"] == "marketplace skill"
    assert payload["skills"][0]["status"] == "ready"
    assert payload["skills"][0]["hint"] == "No action required."
    assert payload["skills_root"].endswith(".clawlite/marketplace/skills")


def test_cli_skills_managed_filters_by_status_and_includes_hint(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ready_skill = tmp_path / ".clawlite" / "marketplace" / "skills" / "market-ready"
    ready_skill.mkdir(parents=True, exist_ok=True)
    (ready_skill / "SKILL.md").write_text(
        "---\nname: market-ready\ndescription: ready\ncommand: echo hi\n---\nbody\n",
        encoding="utf-8",
    )

    broken_skill = tmp_path / ".clawlite" / "marketplace" / "skills" / "market-broken"
    broken_skill.mkdir(parents=True, exist_ok=True)
    (broken_skill / "SKILL.md").write_text(
        "---\n"
        "name: market-broken\n"
        "description: broken\n"
        "metadata:\n"
        "  clawlite:\n"
        "    primaryEnv: BROKEN_TOKEN\n"
        "    requires:\n"
        "      env: [BROKEN_TOKEN]\n"
        "---\nbody\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("BROKEN_TOKEN", raising=False)

    rc = main(["skills", "managed", "--status", "missing_requirements"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["total_count"] == 2
    assert payload["ready_count"] == 1
    assert payload["blocked_count"] == 1
    assert payload["status_filter"] == "missing_requirements"
    assert payload["status_counts"] == {"missing_requirements": 1, "ready": 1}
    assert payload["skills"][0]["name"] == "market-broken"
    assert "BROKEN_TOKEN" in payload["skills"][0]["hint"]


def test_cli_skills_managed_supports_query_filter(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    discord_skill = tmp_path / ".clawlite" / "marketplace" / "skills" / "discord-helper"
    discord_skill.mkdir(parents=True, exist_ok=True)
    (discord_skill / "SKILL.md").write_text(
        "---\nname: Discord Helper\ndescription: moderation helpers\ncommand: echo hi\n---\nbody\n",
        encoding="utf-8",
    )
    jira_skill = tmp_path / ".clawlite" / "marketplace" / "skills" / "jira-helper"
    jira_skill.mkdir(parents=True, exist_ok=True)
    (jira_skill / "SKILL.md").write_text(
        "---\nname: Jira Helper\ndescription: issue tracking\ncommand: echo hi\n---\nbody\n",
        encoding="utf-8",
    )

    rc = main(["skills", "managed", "--query", "discord"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "discord"
    assert payload["count"] == 1
    assert payload["total_count"] == 2
    assert payload["skills"][0]["slug"] == "discord-helper"


def test_cli_skills_sync_updates_managed_marketplace(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    calls: list[list[str]] = []

    def _fake_which(binary: str) -> str | None:
        return "/usr/bin/npx" if binary == "npx" else None

    def _fake_run(command: list[str], capture_output: bool = True, text: bool = True):
        assert capture_output is True
        assert text is True
        calls.append(list(command))
        managed_root = Path(command[-1])
        skill_dir = managed_root / "skills" / "jira-helper"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Jira Helper\ndescription: managed sync skill\ncommand: echo hi\n---\nbody\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "updated all", "")

    monkeypatch.setattr("clawlite.core.skills.shutil.which", _fake_which)
    monkeypatch.setattr("clawlite.core.skills.subprocess.run", _fake_run)

    rc = main(["skills", "sync"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "sync"
    assert payload["returncode"] == 0
    assert payload["refresh"]["refreshed"] is True
    assert payload["managed_count"] == 1
    assert payload["status_counts"] == {"ready": 1}
    assert payload["managed"]["action"] == "managed"
    assert payload["managed"]["skills"][0]["slug"] == "jira-helper"
    assert payload["skills"][0]["slug"] == "jira-helper"
    assert calls[0][3:5] == ["update", "--all"]


def test_cli_skills_remove_resolves_marketplace_skill_by_name(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    skill_dir = tmp_path / ".clawlite" / "marketplace" / "skills" / "managed-folder"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: Managed Skill\n---\n", encoding="utf-8")

    rc = main(["skills", "remove", "Managed Skill"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "remove"
    assert payload["slug"] == "managed-folder"
    assert payload["name"] == "Managed Skill"
    assert payload["removed"]["slug"] == "managed-folder"
    assert payload["managed_count"] == 0
    assert payload["status_counts"] == {}
    assert not skill_dir.exists()


def test_cli_tools_safety_preview_reports_effective_policy(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "safety": {
                        "enabled": True,
                        "risky_tools": [],
                        "risky_specifiers": ["browser:evaluate"],
                        "blocked_channels": ["telegram"],
                        "allowed_channels": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "safety",
            "browser",
            "--session-id",
            "telegram:1",
            "--channel",
            "telegram",
            "--args-json",
            '{"action":"evaluate"}',
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "tools_safety_preview"
    assert payload["blocked"] is True
    assert payload["matched_specifiers"] == ["browser:evaluate"]
    assert payload["derived_specifiers"] == ["browser", "browser:evaluate"]


def test_cli_tools_safety_preview_reports_approval_mode(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "safety": {
                        "enabled": True,
                        "risky_tools": [],
                        "approval_specifiers": ["browser:evaluate"],
                        "approval_channels": ["telegram"],
                        "blocked_channels": [],
                        "allowed_channels": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "safety",
            "browser",
            "--session-id",
            "telegram:1",
            "--channel",
            "telegram",
            "--args-json",
            '{"action":"evaluate"}',
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["decision"] == "approval"
    assert payload["approval_required"] is True
    assert payload["matched_approval_specifiers"] == ["browser:evaluate"]
    assert len(str(payload["approval_request_id"])) == 16
    assert payload["approval_context"] == {"tool": "browser", "action": "evaluate"}


def test_cli_tools_safety_preview_rejects_invalid_json(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "safety",
            "browser",
            "--args-json",
            '{"action"',
        ]
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"].startswith("invalid_arguments_json:")


def test_cli_tools_catalog_uses_gateway_endpoint(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    def _fake_fetch(*, gateway_url: str, include_schema: bool = False, timeout: float = 3.0, token: str = ""):
        assert gateway_url == "http://127.0.0.1:8787"
        assert include_schema is True
        assert timeout == 5.0
        assert token == "tok"
        return {
            "ok": True,
            "groups": [
                {"id": "runtime", "label": "Runtime", "tools": [{"id": "exec", "description": "run shell"}]},
                {"id": "web", "label": "Web", "tools": [{"id": "web_fetch", "description": "fetch web"}]},
            ],
            "tool_count": 2,
        }

    monkeypatch.setattr("clawlite.cli.commands.fetch_gateway_tools_catalog", _fake_fetch)

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "catalog",
            "--include-schema",
            "--timeout",
            "5",
            "--token",
            "tok",
            "--group",
            "runtime",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "tools_catalog"
    assert payload["group_filter"] == "runtime"
    assert payload["tool_count"] == 1
    assert payload["groups"][0]["id"] == "runtime"


def test_cli_tools_show_returns_one_tool_entry(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    def _fake_fetch(*, gateway_url: str, include_schema: bool = False, timeout: float = 3.0, token: str = ""):
        assert include_schema is True
        return {
            "ok": True,
            "base_url": "http://127.0.0.1:8787",
            "endpoint": "/v1/tools/catalog",
            "aliases": {"bash": "exec"},
            "groups": [
                {"id": "runtime", "label": "Runtime", "tools": [{"id": "exec", "description": "run shell"}]},
            ],
            "schema": [
                {"name": "exec", "description": "run shell", "parameters": {"type": "object"}},
            ],
        }

    monkeypatch.setattr("clawlite.cli.commands.fetch_gateway_tools_catalog", _fake_fetch)

    rc = main(["--config", str(config_path), "tools", "show", "bash"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "tools_show"
    assert payload["requested_name"] == "bash"
    assert payload["resolved_name"] == "exec"
    assert payload["alias_of"] == "exec"
    assert payload["group"]["id"] == "runtime"
    assert payload["schema"]["name"] == "exec"


def test_cli_tools_show_returns_not_found(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "clawlite.cli.commands.fetch_gateway_tools_catalog",
        lambda **_: {"ok": True, "aliases": {}, "groups": [], "schema": [], "base_url": "http://127.0.0.1:8787", "endpoint": "/v1/tools/catalog"},
    )

    rc = main(["--config", str(config_path), "tools", "show", "ghost"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "tool_not_found:ghost"


def test_cli_tools_approvals_uses_gateway_endpoint(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    def _fake_fetch(
        config,
        *,
        gateway_url="",
        token="",
        timeout=10.0,
        status="pending",
        session_id="",
        channel="",
        tool="",
        rule="",
        include_grants=False,
        limit=50,
    ):
        assert gateway_url == ""
        assert token == ""
        assert timeout == 10.0
        assert status == "pending"
        assert session_id == "telegram:1"
        assert channel == "telegram"
        assert tool == "browser"
        assert rule == "browser:evaluate"
        assert include_grants is True
        assert limit == 10
        return {
            "ok": True,
            "count": 1,
            "requests": [{"request_id": "req-1", "tool": "browser"}],
            "grant_count": 1,
            "grants": [{"rule": "browser:evaluate"}],
        }

    monkeypatch.setattr("clawlite.cli.commands.fetch_gateway_tool_approvals", _fake_fetch)

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "approvals",
            "--session-id",
            "telegram:1",
            "--channel",
            "telegram",
            "--tool",
            "browser",
            "--rule",
            "browser:evaluate",
            "--include-grants",
            "--limit",
            "10",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "tools_approvals"
    assert payload["count"] == 1
    assert payload["grant_count"] == 1


def test_cli_tools_approve_posts_review(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    def _fake_review(config, *, request_id="", decision="", actor="", note="", gateway_url="", token="", timeout=10.0):
        assert request_id == "req-1"
        assert decision == "approved"
        assert actor == "cli"
        assert note == "looks good"
        return {"ok": True, "summary": {"status": "approved", "request_id": request_id}}

    monkeypatch.setattr("clawlite.cli.commands.review_gateway_tool_approval", _fake_review)

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "approve",
            "req-1",
            "--actor",
            "cli",
            "--note",
            "looks good",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "tools_approve"
    assert payload["summary"]["status"] == "approved"


def test_cli_tools_approval_audit_uses_gateway_endpoint(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    def _fake_fetch(
        config,
        *,
        gateway_url="",
        token="",
        timeout=10.0,
        action="",
        session_id="",
        channel="",
        request_id="",
        tool="",
        rule="",
        limit=50,
    ):
        assert gateway_url == ""
        assert token == ""
        assert timeout == 10.0
        assert action == "review"
        assert session_id == "telegram:1"
        assert channel == "telegram"
        assert request_id == "req-1"
        assert tool == "browser"
        assert rule == "browser:evaluate"
        assert limit == 10
        return {
            "ok": True,
            "action": "review",
            "count": 1,
            "changed_count": 1,
            "entries": [{"action": "review", "status": "approved", "request_id": "req-1"}],
        }

    monkeypatch.setattr("clawlite.cli.commands.fetch_gateway_tool_approval_audit", _fake_fetch)

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "approval-audit",
            "--action",
            "review",
            "--session-id",
            "telegram:1",
            "--channel",
            "telegram",
            "--request-id",
            "req-1",
            "--tool",
            "browser",
            "--rule",
            "browser:evaluate",
            "--limit",
            "10",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "tools_approval_audit"
    assert payload["audit_action_filter"] == "review"
    assert payload["count"] == 1
    assert payload["changed_count"] == 1


def test_cli_tools_approval_audit_ndjson_uses_export_endpoint(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    def _fake_export(
        config,
        *,
        gateway_url="",
        token="",
        timeout=10.0,
        action="",
        session_id="",
        channel="",
        request_id="",
        tool="",
        rule="",
        limit=50,
    ):
        assert action == "review"
        assert request_id == "req-1"
        assert tool == "browser"
        assert rule == "browser:evaluate"
        return {
            "ok": True,
            "content": '{"action":"review","request_id":"req-1"}\n',
            "line_count": 1,
        }

    monkeypatch.setattr("clawlite.cli.commands.fetch_gateway_tool_approval_audit_export", _fake_export)

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "approval-audit",
            "--format",
            "ndjson",
            "--action",
            "review",
            "--request-id",
            "req-1",
            "--tool",
            "browser",
            "--rule",
            "browser:evaluate",
        ]
    )

    assert rc == 0
    assert capsys.readouterr().out == '{"action":"review","request_id":"req-1"}\n'


def test_fetch_gateway_tool_approval_audit_export_preserves_single_line_ndjson(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    config = load_config(config_path)

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params=None):
            del params
            request = httpx.Request("GET", url)
            return httpx.Response(
                200,
                request=request,
                content=b'{"action":"review","request_id":"req-1"}\n',
                headers={
                    "X-ClawLite-Audit-Retention-Limit": "200",
                    "X-ClawLite-Audit-Retained-Count": "4",
                    "X-ClawLite-Audit-Matched-Count": "1",
                    "X-ClawLite-Audit-Returned-Count": "1",
                    "X-ClawLite-Audit-Truncated": "false",
                },
            )

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _Client)

    payload = fetch_gateway_tool_approval_audit_export(
        config,
        action="review",
        request_id="req-1",
    )

    assert payload["ok"] is True
    assert payload["content"] == '{"action":"review","request_id":"req-1"}\n'
    assert payload["line_count"] == 1
    assert payload["retention"] == {
        "limit": 200,
        "retained_count": 4,
        "matched_count": 1,
        "returned_count": 1,
        "truncated": False,
    }


def test_cli_tools_revoke_grant_posts_revoke(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    def _fake_revoke(config, *, session_id="", channel="", rule="", gateway_url="", token="", timeout=10.0):
        assert session_id == "telegram:1"
        assert channel == "telegram"
        assert rule == "browser:evaluate"
        return {"ok": True, "summary": {"removed_count": 1}}

    monkeypatch.setattr("clawlite.cli.commands.revoke_gateway_tool_grants", _fake_revoke)

    rc = main(
        [
            "--config",
            str(config_path),
            "tools",
            "revoke-grant",
            "--session-id",
            "telegram:1",
            "--channel",
            "telegram",
            "--rule",
            "browser:evaluate",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["action"] == "tools_revoke_grant"
    assert payload["summary"]["removed_count"] == 1


def test_cli_skills_doctor_reports_actionable_hints(tmp_path: Path, capsys, monkeypatch) -> None:
    builtin_root = tmp_path / "builtin"
    missing_dir = builtin_root / "github"
    missing_dir.mkdir(parents=True, exist_ok=True)
    (missing_dir / "SKILL.md").write_text(
        "---\n"
        "name: github\n"
        "description: GitHub skill\n"
        "script: github\n"
        "metadata:\n"
        "  clawlite:\n"
        "    primaryEnv: GH_TOKEN\n"
        "    requires:\n"
        "      env: [GH_TOKEN]\n"
        "---\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "clawlite.cli.commands.SkillsLoader",
        lambda state_path=None, config_path=None, config_profile=None: SkillsLoader(
            builtin_root=builtin_root,
            state_path=state_path,
            config_path=config_path,
            config_profile=config_profile,
        ),
    )
    monkeypatch.delenv("GH_TOKEN", raising=False)

    rc = main(["--config", str(config_path), "skills", "doctor"])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "skills_doctor"
    assert payload["ok"] is False
    assert payload["status_counts"]["missing_requirements"] == 1
    assert payload["skills"][0]["status"] == "missing_requirements"
    assert "GH_TOKEN" in payload["skills"][0]["hint"]


def test_cli_skills_doctor_uses_explicit_config_path_for_skill_entries(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    builtin_root = tmp_path / "builtin"
    missing_dir = builtin_root / "github"
    missing_dir.mkdir(parents=True, exist_ok=True)
    (missing_dir / "SKILL.md").write_text(
        "---\n"
        "name: github\n"
        "description: GitHub skill\n"
        "script: github\n"
        "metadata:\n"
        "  clawlite:\n"
        "    primaryEnv: GH_TOKEN\n"
        "    requires:\n"
        "      env: [GH_TOKEN]\n"
        "---\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "skills": {
                    "entries": {
                        "github": {
                            "apiKey": "token-from-custom-config",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("CLAWLITE_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(
        "clawlite.cli.commands.SkillsLoader",
        lambda state_path=None, config_path=None, config_profile=None: SkillsLoader(
            builtin_root=builtin_root,
            state_path=state_path,
            config_path=config_path,
            config_profile=config_profile,
        ),
    )

    rc = main(["--config", str(config_path), "skills", "doctor"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "skills_doctor"
    assert payload["ok"] is True
    assert payload["count"] == 0
    assert payload["recommendations"] == []
    assert payload["status_counts"]["ready"] == 1


def test_cli_skills_doctor_supports_status_and_source_filters(tmp_path: Path, capsys, monkeypatch) -> None:
    builtin_root = tmp_path / "builtin"
    github_dir = builtin_root / "github"
    github_dir.mkdir(parents=True, exist_ok=True)
    (github_dir / "SKILL.md").write_text(
        "---\n"
        "name: github\n"
        "description: GitHub skill\n"
        "script: github\n"
        "metadata:\n"
        "  clawlite:\n"
        "    primaryEnv: GH_TOKEN\n"
        "    requires:\n"
        "      env: [GH_TOKEN]\n"
        "---\n",
        encoding="utf-8",
    )
    marketplace_root = tmp_path / ".clawlite" / "marketplace" / "skills" / "jira-helper"
    marketplace_root.mkdir(parents=True, exist_ok=True)
    (marketplace_root / "SKILL.md").write_text(
        "---\n"
        "name: jira-helper\n"
        "description: Jira helper\n"
        "script: jira\n"
        "---\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "clawlite.cli.commands.SkillsLoader",
        lambda state_path=None, config_path=None, config_profile=None: SkillsLoader(
            builtin_root=builtin_root,
            state_path=state_path,
            config_path=config_path,
            config_profile=config_profile,
        ),
    )
    monkeypatch.delenv("GH_TOKEN", raising=False)

    rc = main(["--config", str(config_path), "skills", "doctor", "--status", "missing_requirements", "--source", "builtin"])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "skills_doctor"
    assert payload["status_filter"] == "missing_requirements"
    assert payload["source_filter"] == "builtin"
    assert payload["count"] == 1
    assert [row["name"] for row in payload["skills"]] == ["github"]


def test_cli_skills_doctor_supports_query_filter(tmp_path: Path, capsys, monkeypatch) -> None:
    builtin_root = tmp_path / "builtin"
    github_dir = builtin_root / "github"
    github_dir.mkdir(parents=True, exist_ok=True)
    (github_dir / "SKILL.md").write_text(
        "---\n"
        "name: github\n"
        "description: GitHub skill\n"
        "script: github\n"
        "metadata:\n"
        "  clawlite:\n"
        "    primaryEnv: GH_TOKEN\n"
        "    requires:\n"
        "      env: [GH_TOKEN]\n"
        "---\n",
        encoding="utf-8",
    )
    builtin_root.joinpath("jira").mkdir(parents=True, exist_ok=True)
    (builtin_root / "jira" / "SKILL.md").write_text(
        "---\nname: jira\ndescription: Jira skill\nscript: jira\n---\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "clawlite.cli.commands.SkillsLoader",
        lambda state_path=None, config_path=None, config_profile=None: SkillsLoader(
            builtin_root=builtin_root,
            state_path=state_path,
            config_path=config_path,
            config_profile=config_profile,
        ),
    )
    monkeypatch.delenv("GH_TOKEN", raising=False)

    rc = main(["--config", str(config_path), "skills", "doctor", "--query", "github"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "github"
    assert payload["count"] == 1
    assert payload["skills"][0]["name"] == "github"


def test_cli_status_and_version(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    state_path = tmp_path / "state"
    workspace_path = tmp_path / "workspace"
    state_path.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
                "agents": {
                    "defaults": {"memory_window": 17, "session_retention_messages": 77}
                },
                "channels": {
                    "telegram": {"enabled": True},
                    "discord": {"enabled": False},
                },
                "scheduler": {"heartbeat_interval_seconds": 1234},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "status"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_model"] == "openai/gpt-4o-mini"
    assert payload["heartbeat_interval_seconds"] == 1234
    assert payload["memory_window"] == 17
    assert payload["session_retention_messages"] == 77
    assert payload["channels_enabled"] == ["telegram"]
    assert payload["gateway_auth_mode"] == "off"
    assert payload["gateway_auth_token_configured"] is False
    assert payload["gateway_diagnostics_enabled"] is True
    assert "bootstrap_pending" in payload
    assert "bootstrap_last_status" in payload

    rc_ver = main(["--version"])
    assert rc_ver == 0
    ver_out = capsys.readouterr().out.strip()
    assert ver_out


def test_cli_status_respects_profile_overlay(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "scheduler": {"heartbeat_interval_seconds": 1234},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config.prod.json").write_text(
        json.dumps(
            {
                "scheduler": {"heartbeat_interval_seconds": 4321},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "--profile", "prod", "status"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["heartbeat_interval_seconds"] == 4321


def test_cli_self_evolution_trigger_posts_dry_run(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    def _fake_trigger(config, *, gateway_url="", token="", timeout=10.0, dry_run=False):
        assert dry_run is True
        assert gateway_url == ""
        assert token == ""
        assert timeout == 10.0
        return {"ok": True, "status": {"last_outcome": "dry_run"}, "runner": {"running": False}}

    monkeypatch.setattr("clawlite.cli.commands.self_evolution_trigger", _fake_trigger)

    rc = main(["--config", str(config_path), "self-evolution", "trigger", "--dry-run"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"]["last_outcome"] == "dry_run"


def test_cli_dashboard_no_open_returns_tokenized_handoff_and_bootstrap_state(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    workspace_path = tmp_path / "workspace"
    WorkspaceLoader(workspace_path=workspace_path).bootstrap()
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {"auth": {"mode": "required", "token": ""}},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "dashboard", "--no-open"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["open_attempted"] is False
    assert payload["opened"] is False
    assert payload["gateway_url"] == "http://127.0.0.1:8787"
    assert payload["dashboard_url_with_handoff"].startswith(
        "http://127.0.0.1:8787#handoff="
    )
    assert payload["dashboard_url_with_token"].startswith(
        "http://127.0.0.1:8787#handoff="
    )
    assert payload["bootstrap_pending"] is True
    assert payload["recommended_first_message"] == "Wake up, my friend!"
    assert payload["hatch_session_id"] == "hatch:operator"
    assert any(item["id"] == "hatch" for item in payload["guidance"])
    assert any(item["id"] == "web_search" for item in payload["guidance"])
    assert any(item["id"] == "security" for item in payload["guidance"])

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["gateway"]["auth"]["token"]


def test_cli_dashboard_profile_saves_token_to_overlay(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    overlay_path = tmp_path / "config.prod.json"
    workspace_path = tmp_path / "workspace"
    WorkspaceLoader(workspace_path=workspace_path).bootstrap()
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {"auth": {"mode": "required", "token": ""}},
            }
        ),
        encoding="utf-8",
    )
    overlay_path.write_text(
        json.dumps(
            {
                "gateway": {"port": 19090},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "--profile", "prod", "dashboard", "--no-open"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    backup_row = next(item for item in payload["guidance"] if item["id"] == "workspace_backup")
    saved_base = json.loads(config_path.read_text(encoding="utf-8"))
    saved_overlay = json.loads(overlay_path.read_text(encoding="utf-8"))

    assert payload["gateway_url"] == "http://127.0.0.1:19090"
    assert "config.prod.json" in backup_row["body"]
    assert saved_base["gateway"]["auth"]["token"] == ""
    assert saved_overlay["gateway"]["auth"]["token"]
    assert not (tmp_path / "config.prod.prod.json").exists()


def test_cli_dashboard_opens_browser_when_allowed(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {"auth": {"mode": "required", "token": "tok-open-123456"}},
            }
        ),
        encoding="utf-8",
    )

    opened: dict[str, str] = {"url": ""}

    def _fake_open(url: str) -> bool:
        opened["url"] = url
        return True

    monkeypatch.setattr("clawlite.cli.commands.webbrowser.open", _fake_open)

    rc = main(["--config", str(config_path), "dashboard"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["open_attempted"] is True
    assert payload["opened"] is True
    assert payload["hatch_session_id"] == "hatch:operator"
    assert any(item["id"] == "dashboard" for item in payload["guidance"])
    assert opened["url"] == payload["open_target"]
    assert opened["url"].startswith("http://127.0.0.1:8787#handoff=")


def test_cli_hatch_skips_when_bootstrap_not_pending(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    def _boom(_config, **kwargs):
        del kwargs
        raise AssertionError(
            "build_runtime should not be called when bootstrap is not pending"
        )

    monkeypatch.setattr("clawlite.gateway.server.build_runtime", _boom)
    rc = main(["--config", str(config_path), "hatch"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "skipped"
    assert payload["reason"] == "not_pending"


def test_cli_hatch_passes_profile_to_dashboard_handoff(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    called: dict[str, Any] = {}

    def _fake_handoff(
        config,
        *,
        config_path=None,
        config_profile=None,
        variables=None,
        ensure_token=False,
        bootstrap_pending_override=None,
        include_sensitive=True,
    ):
        del config, variables, ensure_token, bootstrap_pending_override, include_sensitive
        called["config_path"] = str(config_path)
        called["config_profile"] = config_profile
        return {
            "bootstrap_pending": False,
            "hatch_session_id": "hatch:operator",
        }

    monkeypatch.setattr("clawlite.cli.commands.build_dashboard_handoff", _fake_handoff)
    rc = main(["--config", str(config_path), "--profile", "prod", "hatch"])

    assert rc == 0
    assert called["config_path"] == str(config_path)
    assert called["config_profile"] == "prod"
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "skipped"


def test_cli_hatch_completes_pending_bootstrap(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    workspace_path = tmp_path / "workspace"
    loader = WorkspaceLoader(workspace_path=workspace_path)
    loader.bootstrap()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    class _Engine:
        async def run(self, *, session_id: str, user_text: str):
            captured["session_id"] = session_id
            captured["user_text"] = user_text
            return types.SimpleNamespace(text="ready", model="openai/gpt-4o-mini")

    runtime = types.SimpleNamespace(engine=_Engine(), workspace=loader)
    monkeypatch.setattr(
        "clawlite.gateway.server.build_runtime", lambda _config, **kwargs: runtime
    )

    rc = main(["--config", str(config_path), "hatch"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert payload["session_id"] == "hatch:operator"
    assert captured["session_id"] == "hatch:operator"
    assert captured["user_text"] == "Wake up, my friend!"
    assert not (workspace_path / "BOOTSTRAP.md").exists()


def test_cli_pairing_list_and_approve(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    pairing_state_path = tmp_path / "telegram-pairing.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "channels": {
                    "telegram": {
                        "enabled": True,
                        "token": "123:abc",
                        "pairing_state_path": str(pairing_state_path),
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    store = TelegramPairingStore(token="123:abc", state_path=str(pairing_state_path))
    request, created = store.issue_request(
        chat_id="55", user_id="321", username="guest", first_name="Guest"
    )
    assert created is True
    code = str(request["code"])

    rc_list = main(["--config", str(config_path), "pairing", "list", "telegram"])
    assert rc_list == 0
    payload_list = json.loads(capsys.readouterr().out)
    assert payload_list["ok"] is True
    assert payload_list["channel"] == "telegram"
    assert payload_list["count"] == 1
    assert payload_list["pending"][0]["code"] == code
    assert payload_list["pending"][0]["user_id"] == "321"

    rc_approve = main(
        ["--config", str(config_path), "pairing", "approve", "telegram", code]
    )
    assert rc_approve == 0
    payload_approve = json.loads(capsys.readouterr().out)
    assert payload_approve["ok"] is True
    assert payload_approve["channel"] == "telegram"
    assert payload_approve["code"] == code
    assert payload_approve["request"]["user_id"] == "321"
    assert "321" in payload_approve["approved_entries"]
    assert "guest" in payload_approve["approved_entries"]
    assert "@guest" in payload_approve["approved_entries"]

    request2, created2 = store.issue_request(
        chat_id="56", user_id="654", username="guest2", first_name="Guest2"
    )
    assert created2 is True
    code2 = str(request2["code"])

    rc_reject = main(
        ["--config", str(config_path), "pairing", "reject", "telegram", code2]
    )
    assert rc_reject == 0
    payload_reject = json.loads(capsys.readouterr().out)
    assert payload_reject["ok"] is True
    assert payload_reject["channel"] == "telegram"
    assert payload_reject["code"] == code2
    assert payload_reject["request"]["user_id"] == "654"

    rc_revoke = main(
        ["--config", str(config_path), "pairing", "revoke", "telegram", "@guest"]
    )
    assert rc_revoke == 0
    payload_revoke = json.loads(capsys.readouterr().out)
    assert payload_revoke["ok"] is True
    assert payload_revoke["entry"] == "@guest"
    assert payload_revoke["removed_entry"] == "@guest"
    assert "@guest" not in payload_revoke["approved_entries"]


def test_cli_gateway_alias_parses(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    called = {"ok": False}

    def _fake_run_gateway(*, host, port, config=None, config_path=None, config_profile=None):
        called["ok"] = True
        assert host == "127.0.0.1"
        assert port == 8787
        assert config is not None
        assert config_path == str(config_path_obj)
        assert config_profile is None

    config_path_obj = config_path
    monkeypatch.setattr("clawlite.gateway.server.run_gateway", _fake_run_gateway)
    rc = main(["--config", str(config_path), "gateway"])
    assert rc == 0
    assert called["ok"] is True


def test_cli_onboard_creates_missing_default_config_and_prints_notice(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    default_config = tmp_path / ".clawlite" / "config.json"
    monkeypatch.setattr("clawlite.cli.commands.DEFAULT_CONFIG_PATH", default_config)
    monkeypatch.setattr("clawlite.config.loader.DEFAULT_CONFIG_PATH", default_config)
    monkeypatch.setenv("CLAWLITE_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.chdir(tmp_path)

    rc = main(["onboard"])
    assert rc == 0
    assert default_config.exists()

    out = capsys.readouterr().out
    assert "Config criado em ~/.clawlite/config.json." in out
    assert (tmp_path / "workspace" / "IDENTITY.md").exists()


def test_cli_start_creates_missing_default_config_and_prints_notice(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    default_config = tmp_path / ".clawlite" / "config.json"
    monkeypatch.setattr("clawlite.cli.commands.DEFAULT_CONFIG_PATH", default_config)
    monkeypatch.setattr("clawlite.config.loader.DEFAULT_CONFIG_PATH", default_config)
    monkeypatch.setenv("CLAWLITE_WORKSPACE", str(tmp_path / "workspace"))

    called = {"ok": False}

    def _fake_run_gateway(*, host, port, config=None, config_path=None, config_profile=None):
        called["ok"] = True
        assert host == "127.0.0.1"
        assert port == 8787
        assert config is not None
        assert config_path is None
        assert config_profile is None

    monkeypatch.setattr("clawlite.gateway.server.run_gateway", _fake_run_gateway)

    rc = main(["start"])
    assert rc == 0
    assert default_config.exists()
    assert called["ok"] is True

    out = capsys.readouterr().out
    assert "Config criado em ~/.clawlite/config.json." in out


def test_cli_start_uses_custom_config_values_for_runtime_and_port(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "custom.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 19999,
                    "auth": {"mode": "required", "token": "tok-123456"},
                },
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def _fake_run_gateway(*, host, port, config=None, config_path=None, config_profile=None):
        captured["host"] = host
        captured["port"] = port
        captured["config"] = config
        captured["config_path"] = config_path
        captured["config_profile"] = config_profile

    monkeypatch.setattr("clawlite.gateway.server.run_gateway", _fake_run_gateway)

    rc = main(["--config", str(config_path), "start"])
    assert rc == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 19999
    assert captured["config_path"] == str(config_path)
    assert captured["config_profile"] is None
    assert captured["config"].gateway.port == 19999


def test_cli_start_uses_profiled_config_for_gateway_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "custom.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 1111,
                    "auth": {"mode": "required", "token": "tok-123456"},
                },
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "custom.prod.json").write_text(
        json.dumps(
            {
                "gateway": {
                    "port": 2222,
                }
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def _fake_run_gateway(*, host, port, config=None, config_path=None, config_profile=None):
        captured["host"] = host
        captured["port"] = port
        captured["config"] = config
        captured["config_path"] = config_path
        captured["config_profile"] = config_profile

    monkeypatch.setattr("clawlite.gateway.server.run_gateway", _fake_run_gateway)

    rc = main(["--config", str(config_path), "--profile", "prod", "start"])
    assert rc == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 2222
    assert captured["config_path"] == str(config_path)
    assert captured["config_profile"] == "prod"
    assert captured["config"].gateway.port == 2222


def test_cli_help_version_status_do_not_import_gateway(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    state_path = tmp_path / "state"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc_ver = main(["--version"])
    assert rc_ver == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_help = main([])
    assert rc_help == 1
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_status = main(["--config", str(config_path), "status"])
    assert rc_status == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_validate_provider_and_channels(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_API_KEY", raising=False)

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "channels": {
                    "telegram": {"enabled": True, "token": ""},
                },
            }
        ),
        encoding="utf-8",
    )

    rc_provider = main(["--config", str(config_path), "validate", "provider"])
    assert rc_provider == 2
    provider_payload = json.loads(capsys.readouterr().out)
    assert provider_payload["ok"] is False
    assert provider_payload["provider"] == "openai"

    rc_channels = main(["--config", str(config_path), "validate", "channels"])
    assert rc_channels == 2
    channels_payload = json.loads(capsys.readouterr().out)
    assert channels_payload["ok"] is False
    assert channels_payload["enabled"] == ["telegram"]


def test_cli_validate_onboarding_fix_and_diagnostics(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    workspace_path = tmp_path / "workspace"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "gemini/gemini-2.5-flash"},
                "agents": {
                    "defaults": {"memory_window": 29, "session_retention_messages": 111}
                },
            }
        ),
        encoding="utf-8",
    )

    rc_validate = main(["--config", str(config_path), "validate", "onboarding"])
    assert rc_validate == 2
    payload_before = json.loads(capsys.readouterr().out)
    assert payload_before["ok"] is False
    assert "IDENTITY.md" in payload_before["missing"]

    rc_fix = main(["--config", str(config_path), "validate", "onboarding", "--fix"])
    assert rc_fix == 0
    payload_after = json.loads(capsys.readouterr().out)
    assert payload_after["ok"] is True
    assert (workspace_path / "IDENTITY.md").exists()

    rc_diag = main(["--config", str(config_path), "diagnostics", "--no-validation"])
    assert rc_diag == 0
    diagnostics = json.loads(capsys.readouterr().out)
    assert diagnostics["local"]["gateway"]["diagnostics_enabled"] is True
    assert diagnostics["local"]["memory_window"] == 29
    assert diagnostics["local"]["session_retention_messages"] == 111
    assert diagnostics["local"]["agent_defaults"]["memory_window"] == 29
    assert diagnostics["local"]["agent_defaults"]["session_retention_messages"] == 111
    assert "bootstrap" in diagnostics["local"]
    assert "pending" in diagnostics["local"]["bootstrap"]
    assert "validation" not in diagnostics["local"]


def test_cli_non_runtime_validate_and_diagnostics_do_not_import_gateway(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "gemini/gemini-2.5-flash"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc_validate = main(["--config", str(config_path), "validate", "onboarding"])
    assert rc_validate == 2
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_diag = main(["--config", str(config_path), "diagnostics", "--no-validation"])
    assert rc_diag == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_validate_config_ok_strict(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "validate", "config"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["strict"] is True
    assert payload["provider_model"] == "openai/gpt-4o-mini"


def test_cli_validate_config_invalid_key_returns_rc2(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "invalid_top_level": True,
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "validate", "config"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["strict"] is True
    assert "invalid config keys" in payload["error"]


def test_cli_validate_config_does_not_import_gateway_runtime(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc = main(["--config", str(config_path), "validate", "config"])
    assert rc == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()


def test_cli_validate_preflight_local_success(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-preflight-1234")
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_API_KEY", raising=False)

    workspace_path = tmp_path / "workspace"
    for rel in TEMPLATE_FILES:
        target = workspace_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n", encoding="utf-8")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "validate", "preflight"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["strict_config"]["ok"] is True
    assert payload["local_checks"]["provider"]["ok"] is True
    assert payload["local_checks"]["channels"]["ok"] is True
    assert payload["local_checks"]["onboarding"]["ok"] is True
    assert payload["gateway_probe"] == {"enabled": False, "ok": True}
    assert payload["provider_live_probe"] == {"enabled": False, "ok": True}
    assert payload["telegram_live_probe"] == {"enabled": False, "ok": True}
    assert payload["docker_preflight"] == {"enabled": False, "ok": True}


def test_cli_validate_preflight_optional_probes_success(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-preflight-1234")

    workspace_path = tmp_path / "workspace"
    for rel in TEMPLATE_FILES:
        target = workspace_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n", encoding="utf-8")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "channels": {"telegram": {"token": "12345:ABCDE"}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "clawlite.cli.commands.fetch_gateway_diagnostics",
        lambda **kwargs: {
            "base_url": kwargs["gateway_url"],
            "endpoints": {
                "/health": {"ok": True, "status_code": 200},
                "/v1/status": {"ok": True, "status_code": 200},
                "/v1/diagnostics": {"ok": True, "status_code": 200},
            },
        },
    )
    monkeypatch.setattr(
        "clawlite.cli.commands.provider_live_probe",
        lambda config, timeout: {
            "ok": True,
            "provider": "openai",
            "provider_detected": "openai",
            "family": "openai_compatible",
            "model": str(config.provider.model),
            "recommended_model": "openai/gpt-4o-mini",
            "recommended_models": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
            "status_code": 200,
            "error": "",
            "error_detail": "",
            "error_class": "",
            "base_url": "https://api.openai.com/v1",
            "base_url_source": "spec:openai.default_base_url",
            "default_base_url": "https://api.openai.com/v1",
            "endpoint": "/models",
            "transport": "openai_compatible",
            "probe_method": "GET",
            "api_key_masked": "********1234",
            "api_key_source": "env:OPENAI_API_KEY",
            "key_envs": ["OPENAI_API_KEY"],
            "model_check": {"checked": False, "ok": True},
            "capability_summary": {
                "provider": "openai",
                "model": str(config.provider.model),
                "transport": "openai_compatible",
                "checked": False,
                "current_model_listed": False,
                "detail": "model_list_unavailable",
                "listed_model_count": 0,
                "listed_model_sample": [],
            },
            "onboarding_hint": "OpenAI responds via the standard OpenAI-compatible endpoint; validate billing and the active project.",
            "hints": ["Credenciais validas."],
        },
    )
    monkeypatch.setattr(
        "clawlite.cli.commands.telegram_live_probe",
        lambda config, timeout: {
            "ok": True,
            "status_code": 200,
            "error": "",
            "endpoint": "https://api.telegram.org/bot***/getMe",
            "token_masked": "******BCDE",
        },
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "validate",
            "preflight",
            "--gateway-url",
            "http://127.0.0.1:8787",
            "--provider-live",
            "--telegram-live",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["gateway_probe"]["enabled"] is True
    assert payload["gateway_probe"]["ok"] is True
    assert payload["provider_live_probe"]["enabled"] is True
    assert payload["provider_live_probe"]["ok"] is True
    assert payload["provider_live_probe"]["family"] == "openai_compatible"
    assert payload["provider_live_probe"]["transport"] == "openai_compatible"
    assert payload["provider_live_probe"]["probe_method"] == "GET"
    assert payload["provider_live_probe"]["recommended_model"] == "openai/gpt-4o-mini"
    assert payload["provider_live_probe"]["recommended_models"] == [
        "openai/gpt-4o-mini",
        "openai/gpt-4.1-mini",
    ]
    assert payload["provider_live_probe"]["last_capability_probe"]["provider"] == "openai"
    assert payload["provider_live_probe"]["last_capability_probe"]["detail"] == "model_list_unavailable"
    assert "billing" in payload["provider_live_probe"]["onboarding_hint"].lower()
    assert payload["provider_live_probe"]["hints"] == ["Credenciais validas."]
    assert payload["telegram_live_probe"]["enabled"] is True
    assert payload["telegram_live_probe"]["ok"] is True
    assert payload["docker_preflight"] == {"enabled": False, "ok": True}


def test_cli_validate_preflight_gateway_failure_returns_rc2(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-preflight-1234")

    workspace_path = tmp_path / "workspace"
    for rel in TEMPLATE_FILES:
        target = workspace_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n", encoding="utf-8")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "clawlite.cli.commands.fetch_gateway_diagnostics",
        lambda **kwargs: {
            "base_url": kwargs["gateway_url"],
            "endpoints": {
                "/health": {"ok": True, "status_code": 200},
                "/v1/status": {"ok": False, "status_code": 500, "error": "boom"},
                "/v1/diagnostics": {"ok": True, "status_code": 200},
            },
        },
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "validate",
            "preflight",
            "--gateway-url",
            "http://127.0.0.1:8787",
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["gateway_probe"]["enabled"] is True
    assert payload["gateway_probe"]["ok"] is False
    assert payload["gateway_probe"]["endpoints"]["/v1/status"]["status_code"] == 500
    assert payload["docker_preflight"] == {"enabled": False, "ok": True}


def test_cli_validate_preflight_does_not_import_gateway_runtime(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-preflight-1234")

    workspace_path = tmp_path / "workspace"
    for rel in TEMPLATE_FILES:
        target = workspace_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n", encoding="utf-8")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc = main(["--config", str(config_path), "validate", "preflight"])
    assert rc == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()


def test_docker_preflight_probe_reports_not_running_stack_as_ok(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        if command[:3] == ["/usr/bin/docker", "compose", "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command[:3] == ["/usr/bin/docker", "compose", "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == ["/usr/bin/docker", "compose", "ps", "--format", "json"]:
            return subprocess.CompletedProcess(command, 0, stdout="[]\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(timeout=1.5)

    assert payload["ok"] is True
    assert payload["repo_root_source"] == "cwd"
    assert payload["compose_config"]["ok"] is True
    assert payload["env_file"]["configured"] is False
    assert payload["stack"]["detected"] is False
    assert payload["gateway"]["detected"] is False
    assert payload["gateway"]["status"] == "not_running"


def test_docker_preflight_probe_uses_configured_env_file(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env.docker"
    env_file.write_text("CLAWLITE_BUS_BACKEND=redis\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAWLITE_DOCKER_ENV_FILE", env_file.name)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        compose_prefix = ["/usr/bin/docker", "compose", "--env-file", str(env_file.resolve())]
        if command == [*compose_prefix, "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command == [*compose_prefix, "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == [*compose_prefix, "ps", "--format", "json"]:
            return subprocess.CompletedProcess(command, 0, stdout="[]\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(timeout=1.5)

    assert payload["ok"] is True
    assert payload["env_file"]["configured"] is True
    assert payload["env_file"]["ok"] is True
    assert payload["env_file"]["path"] == str(env_file.resolve())


def test_docker_preflight_probe_fails_when_env_file_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAWLITE_DOCKER_ENV_FILE", "missing.env")

    payload = docker_preflight_probe(timeout=1.5)

    assert payload["ok"] is False
    assert payload["error"] == "docker_env_file_missing"
    assert payload["env_file"]["configured"] is True
    assert payload["env_file"]["ok"] is False
    assert payload["env_file"]["path"] == "missing.env"


def test_docker_preflight_probe_adds_provider_env_hint_when_docker_context_is_missing_key(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_API_KEY", raising=False)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        if command[:3] == ["/usr/bin/docker", "compose", "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command[:3] == ["/usr/bin/docker", "compose", "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == ["/usr/bin/docker", "compose", "ps", "--format", "json"]:
            return subprocess.CompletedProcess(command, 0, stdout="[]\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(timeout=1.5, config=load_config(str(config_path)))

    assert payload["ok"] is True
    assert payload["secrets"]["warnings"] == ["docker_provider_env_missing:openai"]
    assert "OPENAI_API_KEY" in payload["secrets"]["hints"][0]
    assert payload["secrets"]["provider"]["detected"] == "openai"
    assert payload["secrets"]["provider"]["available_envs"] == []
    assert "OPENAI_API_KEY" in payload["secrets"]["provider"]["missing_envs"]


def test_docker_preflight_probe_uses_env_file_to_satisfy_provider_env_hint(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env.docker"
    env_file.write_text("OPENAI_API_KEY=sk-test-openai-1234\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CLAWLITE_DOCKER_ENV_FILE", env_file.name)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        compose_prefix = ["/usr/bin/docker", "compose", "--env-file", str(env_file.resolve())]
        if command == [*compose_prefix, "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command == [*compose_prefix, "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == [*compose_prefix, "ps", "--format", "json"]:
            return subprocess.CompletedProcess(command, 0, stdout="[]\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(timeout=1.5, config=load_config(str(config_path)))

    assert payload["ok"] is True
    assert payload["secrets"]["warnings"] == []
    assert payload["secrets"]["provider"]["available_envs"] == [{"name": "OPENAI_API_KEY", "source": "env_file"}]


def test_docker_preflight_probe_ignores_host_only_custom_config_for_provider_secret_hints(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    custom_dir = tmp_path / "outside"
    custom_dir.mkdir(parents=True, exist_ok=True)
    config_path = custom_dir / "custom.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "providers": {"openai": {"api_key": "sk-config-only-1234"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_API_KEY", raising=False)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        if command[:3] == ["/usr/bin/docker", "compose", "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command[:3] == ["/usr/bin/docker", "compose", "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == ["/usr/bin/docker", "compose", "ps", "--format", "json"]:
            return subprocess.CompletedProcess(command, 0, stdout="[]\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(
        timeout=1.5,
        config=load_config(str(config_path)),
        config_path=str(config_path),
    )

    assert payload["ok"] is True
    assert payload["secrets"]["warnings"] == ["docker_provider_env_missing:openai"]
    assert payload["secrets"]["provider"]["configured"] is False
    assert payload["secrets"]["provider"]["configured_source"] == ""


def test_docker_preflight_probe_surfaces_unhealthy_gateway(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        if command[:3] == ["/usr/bin/docker", "compose", "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command[:3] == ["/usr/bin/docker", "compose", "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == ["/usr/bin/docker", "compose", "ps", "--format", "json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    [
                        {
                            "Service": "clawlite-gateway",
                            "State": "running",
                            "Health": "unhealthy",
                            "Status": "Up 30 seconds (unhealthy)",
                        }
                    ]
                ),
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(timeout=1.5)

    assert payload["ok"] is False
    assert payload["error"] == "docker_gateway_not_healthy"
    assert payload["gateway"]["detected"] is True
    assert payload["gateway"]["running"] is True
    assert payload["gateway"]["health"] == "unhealthy"


def test_docker_preflight_probe_treats_starting_gateway_as_not_ready(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        if command[:3] == ["/usr/bin/docker", "compose", "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command[:3] == ["/usr/bin/docker", "compose", "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == ["/usr/bin/docker", "compose", "ps", "--format", "json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    [
                        {
                            "Service": "clawlite-gateway",
                            "State": "running",
                            "Health": "starting",
                            "Status": "Up 10 seconds (health: starting)",
                        }
                    ]
                ),
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(timeout=1.5)

    assert payload["ok"] is False
    assert payload["error"] == "docker_gateway_not_healthy"
    assert payload["gateway"]["health"] == "starting"


def test_docker_preflight_probe_requires_gateway_when_runtime_stack_is_present(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        if command[:3] == ["/usr/bin/docker", "compose", "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command[:3] == ["/usr/bin/docker", "compose", "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == ["/usr/bin/docker", "compose", "ps", "--format", "json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    [
                        {
                            "Service": "redis",
                            "State": "running",
                            "Health": "healthy",
                            "Status": "Up 5 minutes (healthy)",
                        }
                    ]
                ),
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(timeout=1.5)

    assert payload["ok"] is False
    assert payload["error"] == "docker_gateway_not_running"
    assert payload["stack"]["detected"] is True
    assert payload["stack"]["error"] == "docker_gateway_not_running"
    assert payload["stack"]["runtime_service_count"] == 1
    assert payload["stack"]["services"][0]["service"] == "redis"
    assert payload["gateway"]["detected"] is False
    assert payload["gateway"]["error"] == "docker_gateway_not_running"


def test_docker_preflight_probe_surfaces_unhealthy_runtime_dependency(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        if command[:3] == ["/usr/bin/docker", "compose", "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command[:3] == ["/usr/bin/docker", "compose", "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == ["/usr/bin/docker", "compose", "ps", "--format", "json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    [
                        {
                            "Service": "clawlite-gateway",
                            "State": "running",
                            "Health": "healthy",
                            "Status": "Up 2 minutes (healthy)",
                        },
                        {
                            "Service": "redis",
                            "State": "running",
                            "Health": "unhealthy",
                            "Status": "Up 2 minutes (unhealthy)",
                        },
                    ]
                ),
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(timeout=1.5)

    assert payload["ok"] is False
    assert payload["error"] == "docker_stack_not_healthy"
    assert payload["gateway"]["detected"] is True
    assert payload["gateway"]["ok"] is True
    assert payload["gateway"]["error"] == ""
    assert payload["stack"]["detected"] is True
    assert payload["stack"]["ok"] is False
    assert payload["stack"]["error"] == "docker_stack_not_healthy"
    assert payload["stack"]["unhealthy_services"] == ["redis"]


def test_docker_preflight_probe_requires_gateway_auth_token_when_required(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAWLITE_GATEWAY_AUTH_MODE", "required")
    monkeypatch.delenv("CLAWLITE_GATEWAY_AUTH_TOKEN", raising=False)

    payload = docker_preflight_probe(timeout=1.5, config=load_config(str(config_path)))

    assert payload["ok"] is False
    assert payload["error"] == "docker_gateway_auth_token_missing"
    assert payload["secrets"]["ok"] is False
    assert payload["secrets"]["gateway_auth"]["mode"] == "required"
    assert payload["secrets"]["gateway_auth"]["token_configured"] is False
    assert payload["secrets"]["gateway_auth"]["error"] == "docker_gateway_auth_token_missing"


def test_docker_preflight_probe_ignores_legacy_gateway_token_env_for_required_auth(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAWLITE_GATEWAY_AUTH_MODE", "required")
    monkeypatch.setenv("CLAWLITE_GATEWAY_TOKEN", "legacy-only-token")
    monkeypatch.delenv("CLAWLITE_GATEWAY_AUTH_TOKEN", raising=False)

    payload = docker_preflight_probe(
        timeout=1.5,
        config=load_config(str(config_path)),
        config_path=str(config_path),
    )

    assert payload["ok"] is False
    assert payload["error"] == "docker_gateway_auth_token_missing"
    assert payload["secrets"]["gateway_auth"]["token_configured"] is False


def test_docker_preflight_probe_qwen_oauth_hint_lists_real_env_names(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  clawlite-gateway:\n    image: clawlite\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "qwen-oauth/qwen-max"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAWLITE_QWEN_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("QWEN_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr("clawlite.cli.commands.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def _fake_run(command, cwd=None, capture_output=False, text=False, timeout=None):
        del cwd, capture_output, text, timeout
        if command[:3] == ["/usr/bin/docker", "compose", "version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Docker Compose version v2.32.0\n", stderr="")
        if command[:3] == ["/usr/bin/docker", "compose", "config"]:
            return subprocess.CompletedProcess(command, 0, stdout="services: {}\n", stderr="")
        if command == ["/usr/bin/docker", "compose", "ps", "--format", "json"]:
            return subprocess.CompletedProcess(command, 0, stdout="[]\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("clawlite.cli.commands.subprocess.run", _fake_run)

    payload = docker_preflight_probe(
        timeout=1.5,
        config=load_config(str(config_path)),
        config_path=str(config_path),
    )

    assert payload["ok"] is True
    assert payload["secrets"]["warnings"] == ["docker_provider_oauth_missing:qwen_oauth"]
    assert "CLAWLITE_QWEN_ACCESS_TOKEN" in payload["secrets"]["hints"][0]
    assert "QWEN_ACCESS_TOKEN" in payload["secrets"]["hints"][0]
    assert "Set one of  " not in payload["secrets"]["hints"][0]


def test_cli_validate_preflight_docker_probe_success(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-preflight-1234")

    workspace_path = tmp_path / "workspace"
    for rel in TEMPLATE_FILES:
        target = workspace_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n", encoding="utf-8")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "clawlite.cli.commands.docker_preflight_probe",
        lambda timeout, config=None, config_path=None, config_profile=None, provider_check=None: {
            "enabled": True,
            "ok": True,
            "repo_root": str(tmp_path),
            "compose_file": str(tmp_path / "docker-compose.yml"),
            "docker_available": True,
            "compose_config": {"ok": True, "exit_code": 0, "detail": ""},
            "gateway": {"detected": False, "running": False, "ok": True, "status": "not_running", "state": "", "health": "", "error": ""},
        },
    )

    rc = main(["--config", str(config_path), "validate", "preflight", "--docker"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["docker_preflight"]["enabled"] is True
    assert payload["docker_preflight"]["ok"] is True
    assert payload["docker_preflight"]["gateway"]["status"] == "not_running"


def test_cli_validate_preflight_docker_probe_failure_returns_rc2(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-preflight-1234")

    workspace_path = tmp_path / "workspace"
    for rel in TEMPLATE_FILES:
        target = workspace_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n", encoding="utf-8")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "clawlite.cli.commands.docker_preflight_probe",
        lambda timeout, config=None, config_path=None, config_profile=None, provider_check=None: {
            "enabled": True,
            "ok": False,
            "error": "docker_missing",
            "repo_root": str(tmp_path),
            "compose_file": str(tmp_path / "docker-compose.yml"),
            "docker_available": False,
            "compose_config": {"ok": False, "exit_code": 0, "detail": ""},
            "gateway": {"detected": False, "running": False, "ok": True, "status": "not_running", "state": "", "health": "", "error": ""},
        },
    )

    rc = main(["--config", str(config_path), "validate", "preflight", "--docker"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["docker_preflight"]["enabled"] is True
    assert payload["docker_preflight"]["error"] == "docker_missing"


def test_cli_validate_channels_slack_bot_only_is_ok_with_warning(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "channels": {
                    "slack": {
                        "enabled": True,
                        "bot_token": "xoxb-test",
                        "app_token": "",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    rc_channels = main(["--config", str(config_path), "validate", "channels"])
    assert rc_channels == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    slack_row = next(row for row in payload["channels"] if row["channel"] == "slack")
    assert slack_row["status"] == "warning"
    assert slack_row["warnings"] == ["app_token"]


def test_cli_memory_doctor_outputs_expected_keys(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "doctor", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["repair_applied"] is False
    assert set(payload["paths"].keys()) == {"history", "curated", "checkpoints"}
    assert set(payload["files"].keys()) == {"history", "curated", "checkpoints"}
    assert set(payload["counts"].keys()) == {"history", "curated", "total"}
    assert set(payload["analysis"].keys()) == {
        "recent",
        "temporal_marked_count",
        "top_sources",
        "reasoning_layers",
        "confidence",
    }
    assert isinstance(payload["analysis"]["reasoning_layers"], dict)
    assert isinstance(payload["analysis"]["confidence"], dict)
    assert "diagnostics" in payload
    assert set(payload["schema"].keys()) == {"curated", "checkpoints"}


def test_cli_memory_without_subcommand_returns_overview(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "agents": {"defaults": {"memory": {"proactive": True}}},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert set(payload["counts"].keys()) == {"history", "curated", "total"}
    assert "semantic_coverage" in payload
    assert payload["proactive_enabled"] is True
    assert "paths" in payload


def test_cli_memory_version_lists_snapshot_ids_desc(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "state"
    state_path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    history_path = state_path / "memory.jsonl"
    history_path.write_text(
        json.dumps(
            {
                "id": "mem-1",
                "text": "baseline",
                "source": "seed",
                "created_at": "2026-03-04T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert main(["--config", str(config_path), "memory", "snapshot", "--tag", "a"]) == 0
    capsys.readouterr()
    assert main(["--config", str(config_path), "memory", "snapshot", "--tag", "b"]) == 0
    capsys.readouterr()

    rc = main(["--config", str(config_path), "memory", "version"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["count"] == len(payload["versions"])
    assert payload["versions"] == sorted(payload["versions"], reverse=True)


def test_cli_memory_doctor_repair_handles_corrupt_history_line(
    tmp_path: Path, capsys
) -> None:
    state_path = tmp_path / "state"
    state_path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    history_path = state_path / "memory.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "a1",
                        "text": "remember alpha",
                        "source": "seed",
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                ),
                "{broken-json",
                json.dumps(
                    {
                        "id": "b2",
                        "text": "remember beta",
                        "source": "seed",
                        "created_at": "2026-01-02T00:00:00+00:00",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "doctor", "--repair"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["repair_applied"] is True
    assert payload["diagnostics"]["history_read_corrupt_lines"] >= 1
    assert payload["diagnostics"]["history_repaired_files"] >= 1

    repaired_lines = [
        line
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(repaired_lines) == 2
    assert all("broken-json" not in line for line in repaired_lines)


def test_cli_memory_doctor_does_not_import_gateway_runtime(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc = main(["--config", str(config_path), "memory", "doctor"])
    assert rc == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()


def test_cli_memory_eval_outputs_json_summary(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "eval", "--limit", "3"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["cases"] == 5
    assert payload["passed"] == 5
    assert payload["failed"] == 0
    assert len(payload["details"]) == payload["cases"]


def test_cli_memory_eval_does_not_import_gateway_runtime(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc = main(["--config", str(config_path), "memory", "eval"])
    assert rc == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()


def test_cli_memory_quality_generates_and_persists_report(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "quality", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    report = payload["report"]
    assert 0 <= int(report["score"]) <= 100
    assert set(report["retrieval"].keys()) == {
        "attempts",
        "hits",
        "rewrites",
        "hit_rate",
    }
    assert set(report["turn_stability"].keys()) == {
        "successes",
        "errors",
        "success_rate",
        "error_rate",
    }
    assert "reasoning_layers" in report
    reasoning_layers = report["reasoning_layers"]
    assert set(reasoning_layers.keys()) == {
        "total_records",
        "distribution",
        "balance_score",
        "weakest_layer",
        "weakest_ratio",
        "confidence",
    }
    assert isinstance(reasoning_layers["distribution"], dict)
    assert set(reasoning_layers["distribution"].keys()) == {
        "fact",
        "hypothesis",
        "decision",
        "outcome",
    }
    for layer_payload in reasoning_layers["distribution"].values():
        assert isinstance(layer_payload, dict)
        assert set(layer_payload.keys()) == {"count", "ratio"}
    assert isinstance(reasoning_layers["confidence"], dict)
    assert set(reasoning_layers["confidence"].keys()) == {
        "average",
        "minimum",
        "maximum",
    }
    assert "drift" in report
    assert isinstance(report["recommendations"], list)
    assert payload["state"]["current"]["score"] == report["score"]
    assert isinstance(payload["state"]["trend"], dict)
    assert payload["state"]["trend"]["available"] is True
    assert int(payload["state"]["trend"]["window_points"]) >= 1
    assert Path(payload["quality_state_path"]).exists()
    assert "analysis" in payload
    assert isinstance(payload["analysis"]["reasoning_layers"], dict)
    assert isinstance(payload["analysis"]["confidence"], dict)
    assert "quality_highlights" in payload["analysis"]
    assert (
        payload["analysis"]["quality_highlights"]["total_records"]
        == reasoning_layers["total_records"]
    )


def test_cli_memory_profile_returns_schema_fields(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "profile"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "profile" in payload
    assert payload["profile"]["timezone"]
    assert payload["profile"]["language"]
    assert payload["profile"]["response_length_preference"]


def test_cli_memory_suggest_returns_list_without_crashing_on_empty(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "suggest"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert isinstance(payload["suggestions"], list)
    assert payload["count"] == len(payload["suggestions"])


def test_cli_memory_snapshot_and_rollback_restores_previous_state(
    tmp_path: Path, capsys
) -> None:
    state_path = tmp_path / "state"
    state_path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    history_path = state_path / "memory.jsonl"
    row_a = {
        "id": "row-a",
        "text": "baseline memory",
        "source": "session:a",
        "created_at": "2026-03-04T00:00:00+00:00",
    }
    row_b = {
        "id": "row-b",
        "text": "new memory",
        "source": "session:b",
        "created_at": "2026-03-04T00:01:00+00:00",
    }
    history_path.write_text(json.dumps(row_a) + "\n", encoding="utf-8")

    rc_snapshot = main(
        ["--config", str(config_path), "memory", "snapshot", "--tag", "baseline"]
    )
    assert rc_snapshot == 0
    snapshot_payload = json.loads(capsys.readouterr().out)
    version_id = snapshot_payload["version_id"]
    assert version_id

    history_path.write_text(
        "\n".join([json.dumps(row_a), json.dumps(row_b)]) + "\n", encoding="utf-8"
    )

    rc_rollback = main(["--config", str(config_path), "memory", "rollback", version_id])
    assert rc_rollback == 0
    rollback_payload = json.loads(capsys.readouterr().out)
    assert rollback_payload["ok"] is True
    restored = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    restored_ids = {item["id"] for item in restored}
    assert "row-a" in restored_ids
    assert "row-b" not in restored_ids


def test_cli_memory_privacy_returns_config_keys(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "privacy"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "privacy" in payload
    assert "never_memorize_patterns" in payload["privacy"]
    assert "ephemeral_ttl_days" in payload["privacy"]


def test_cli_memory_export_and_import_roundtrip(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "state"
    state_path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )
    history_path = state_path / "memory.jsonl"
    history_path.write_text(
        json.dumps(
            {
                "id": "exp-a",
                "text": "export baseline",
                "source": "session:export",
                "created_at": "2026-03-04T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    export_path = tmp_path / "memory-export.json"
    rc_export = main(
        ["--config", str(config_path), "memory", "export", "--out", str(export_path)]
    )
    assert rc_export == 0
    export_payload = json.loads(capsys.readouterr().out)
    assert export_payload["ok"] is True
    assert export_payload["written"] is True
    assert export_path.exists()

    history_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "exp-a",
                        "text": "export baseline",
                        "source": "session:export",
                        "created_at": "2026-03-04T00:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "id": "exp-b",
                        "text": "to be rolled back by import",
                        "source": "session:export",
                        "created_at": "2026-03-04T00:01:00+00:00",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rc_import = main(
        ["--config", str(config_path), "memory", "import", str(export_path)]
    )
    assert rc_import == 0
    import_payload = json.loads(capsys.readouterr().out)
    assert import_payload["ok"] is True
    rows_after_import = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = {row["id"] for row in rows_after_import}
    assert ids == {"exp-a"}


def test_cli_memory_branching_commands_return_expected_shapes(
    tmp_path: Path, capsys
) -> None:
    state_path = tmp_path / "state"
    state_path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    history_path = state_path / "memory.jsonl"
    history_path.write_text(
        json.dumps(
            {
                "id": "branch-a",
                "text": "baseline branch row",
                "source": "session:branch",
                "created_at": "2026-03-04T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(["--config", str(config_path), "memory", "snapshot", "--tag", "seed"]) == 0
    )
    capsys.readouterr()

    rc_branches = main(["--config", str(config_path), "memory", "branches"])
    assert rc_branches == 0
    branches_payload = json.loads(capsys.readouterr().out)
    assert branches_payload["ok"] is True
    assert branches_payload["current"] == "main"
    assert isinstance(branches_payload["branches"], dict)

    rc_branch = main(
        ["--config", str(config_path), "memory", "branch", "feature-x", "--checkout"]
    )
    assert rc_branch == 0
    branch_payload = json.loads(capsys.readouterr().out)
    assert branch_payload["ok"] is True
    assert branch_payload["name"] == "feature-x"
    assert branch_payload["checkout"] is True
    assert branch_payload["current"] == "feature-x"

    rc_checkout = main(["--config", str(config_path), "memory", "checkout", "main"])
    assert rc_checkout == 0
    checkout_payload = json.loads(capsys.readouterr().out)
    assert checkout_payload["ok"] is True
    assert checkout_payload["current"] == "main"
    assert "head" in checkout_payload

    rc_merge = main(
        [
            "--config",
            str(config_path),
            "memory",
            "merge",
            "--source",
            "feature-x",
            "--target",
            "main",
            "--tag",
            "sync",
        ]
    )
    assert rc_merge == 0
    merge_payload = json.loads(capsys.readouterr().out)
    assert merge_payload["ok"] is True
    assert merge_payload["source"] == "feature-x"
    assert merge_payload["target"] == "main"
    assert merge_payload["version"]
    assert "target_head_before" in merge_payload
    assert "target_head_after" in merge_payload

    rc_share = main(
        [
            "--config",
            str(config_path),
            "memory",
            "share-optin",
            "--user",
            "42",
            "--enabled",
            "true",
        ]
    )
    assert rc_share == 0
    share_payload = json.loads(capsys.readouterr().out)
    assert share_payload == {"ok": True, "user_id": "42", "enabled": True}


def test_cli_memory_branching_commands_do_not_import_gateway_runtime(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc_branches = main(["--config", str(config_path), "memory", "branches"])
    assert rc_branches == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_share = main(
        [
            "--config",
            str(config_path),
            "memory",
            "share-optin",
            "--user",
            "99",
            "--enabled",
            "false",
        ]
    )
    assert rc_share == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_memory_branches_empty_returns_main_branch(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "branches"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["current"] == "main"
    assert list(payload["branches"].keys()) == ["main"]
    assert payload["branches"]["main"]["head"] == ""


def test_cli_memory_branch_create_returns_branch_metadata(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "memory", "branch", "feature-empty"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["name"] == "feature-empty"
    assert payload["current"] == "main"
    assert payload["checkout"] is False
    assert payload["head"] == ""


def test_cli_memory_checkout_switches_current_branch(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(["--config", str(config_path), "memory", "branch", "feature-checkout"])
        == 0
    )
    capsys.readouterr()

    rc = main(["--config", str(config_path), "memory", "checkout", "feature-checkout"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["current"] == "feature-checkout"
    assert payload["head"] == ""

    rc_branches = main(["--config", str(config_path), "memory", "branches"])
    assert rc_branches == 0
    branches_payload = json.loads(capsys.readouterr().out)
    assert branches_payload["current"] == "feature-checkout"


def test_cli_memory_merge_returns_import_metadata(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "clawlite.cli.commands.memory_merge_branches",
        lambda cfg, source, target, tag: {
            "ok": True,
            "source": source,
            "target": target,
            "source_head": "src-1",
            "target_head_before": "dst-1",
            "target_head_after": "dst-2",
            "version": "20260308T130000Z-sync",
            "imported": True,
        },
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "memory",
            "merge",
            "--source",
            "feature-merge",
            "--target",
            "main",
            "--tag",
            "sync",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["source"] == "feature-merge"
    assert payload["target"] == "main"
    assert payload["imported"] is True
    assert payload["version"]
    assert payload["target_head_before"]
    assert payload["target_head_after"]


def test_cli_memory_share_optin_enable_returns_enabled_true(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "memory",
            "share-optin",
            "--user",
            "42",
            "--enabled",
            "true",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "user_id": "42", "enabled": True}


def test_cli_new_memory_commands_do_not_import_gateway_runtime(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc_profile = main(["--config", str(config_path), "memory", "profile"])
    assert rc_profile == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_suggest = main(
        ["--config", str(config_path), "memory", "suggest", "--no-refresh"]
    )
    assert rc_suggest == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_quality = main(["--config", str(config_path), "memory", "quality"])
    assert rc_quality == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    export_path = tmp_path / "portable.json"
    sys.modules.pop("clawlite.gateway.server", None)
    rc_export = main(
        ["--config", str(config_path), "memory", "export", "--out", str(export_path)]
    )
    assert rc_export == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_provider_login_status_logout_openai_codex(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("CLAWLITE_CODEX_AUTH_PATH", str(tmp_path / "missing-auth.json"))
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_login = main(
        [
            "--config",
            str(config_path),
            "provider",
            "login",
            "openai-codex",
            "--access-token",
            "codex-token-1234",
            "--account-id",
            "org-123",
            "--no-interactive",
        ]
    )
    assert rc_login == 0
    login_payload = json.loads(capsys.readouterr().out)
    assert login_payload["ok"] is True
    assert login_payload["configured"] is True

    rc_status = main(
        ["--config", str(config_path), "provider", "status", "openai-codex"]
    )
    assert rc_status == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["configured"] is True
    assert status_payload["provider"] == "openai_codex"
    assert status_payload["model"] == "openai-codex/gpt-5.3-codex"
    assert status_payload["transport"] == "oauth_codex_responses"
    assert status_payload["default_base_url"] == "https://chatgpt.com/backend-api"
    assert status_payload["base_url"] == "https://chatgpt.com/backend-api"

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert (
        persisted["auth"]["providers"]["openai_codex"]["access_token"]
        == "codex-token-1234"
    )
    assert persisted["auth"]["providers"]["openai_codex"]["account_id"] == "org-123"
    assert persisted["provider"]["model"] == "openai-codex/gpt-5.3-codex"

    rc_logout = main(
        ["--config", str(config_path), "provider", "logout", "openai-codex"]
    )
    assert rc_logout == 0
    logout_payload = json.loads(capsys.readouterr().out)
    assert logout_payload["configured"] is False

    persisted_after = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted_after["auth"]["providers"]["openai_codex"]["access_token"] == ""
    assert persisted_after["auth"]["providers"]["openai_codex"]["account_id"] == ""


def test_cli_provider_login_status_logout_gemini_oauth(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    auth_path = tmp_path / "gemini-oauth.json"
    auth_path.write_text(
        json.dumps({"tokens": {"access_token": "gemini-token-1234"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_GEMINI_AUTH_PATH", str(auth_path))
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_login = main(
        [
            "--config",
            str(config_path),
            "provider",
            "login",
            "gemini-oauth",
            "--no-interactive",
        ]
    )
    assert rc_login == 0
    login_payload = json.loads(capsys.readouterr().out)
    assert login_payload["ok"] is True
    assert login_payload["provider"] == "gemini_oauth"
    assert login_payload["configured"] is True

    rc_status = main(
        ["--config", str(config_path), "provider", "status", "gemini-oauth"]
    )
    assert rc_status == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["configured"] is True
    assert status_payload["provider"] == "gemini_oauth"
    assert status_payload["model"] == "gemini_oauth/gemini-2.0-flash"
    assert status_payload["transport"] == "oauth_openai_compatible"
    assert status_payload["default_base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert status_payload["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["auth"]["providers"]["gemini_oauth"]["access_token"] == "gemini-token-1234"
    assert persisted["provider"]["model"] == "gemini_oauth/gemini-2.0-flash"

    rc_logout = main(
        ["--config", str(config_path), "provider", "logout", "gemini-oauth"]
    )
    assert rc_logout == 0
    logout_payload = json.loads(capsys.readouterr().out)
    assert logout_payload["configured"] is False


def test_cli_provider_status_qwen_oauth_uses_auth_file_when_config_missing(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    auth_path = tmp_path / "qwen-oauth.json"
    auth_path.write_text(
        json.dumps({"tokens": {"access_token": "qwen-token-1234"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_QWEN_AUTH_PATH", str(auth_path))
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "qwen_oauth/qwen-plus"},
            }
        ),
        encoding="utf-8",
    )

    rc_status = main(["--config", str(config_path), "provider", "status", "qwen-oauth"])
    assert rc_status == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["configured"] is True
    assert status_payload["provider"] == "qwen_oauth"
    assert status_payload["transport"] == "oauth_openai_compatible"
    assert status_payload["default_base_url"] == "https://api.qwen.ai/v1"
    assert status_payload["base_url"] == "https://api.qwen.ai/v1"


def test_cli_provider_status_openai_api_key_provider_success(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-1234")
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_API_KEY", raising=False)

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4.1-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_status = main(["--config", str(config_path), "provider", "status", "openai"])
    assert rc_status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["provider"] == "openai"
    assert payload["configured"] is True
    assert payload["auth_mode"] == "api_key"
    assert payload["transport"] == "openai_compatible"
    assert payload["api_key_source"] == "env:OPENAI_API_KEY"
    assert payload["env_key_present"] is True
    assert payload["base_url"] == "https://api.openai.com/v1"
    assert payload["default_base_url"] == "https://api.openai.com/v1"
    assert payload["key_envs"] == ["OPENAI_API_KEY"]
    assert payload["family"] == "openai_compatible"
    assert payload["recommended_model"] == "openai/gpt-4o-mini"
    assert "openai/gpt-4o-mini" in payload["recommended_models"]
    assert "billing" in payload["onboarding_hint"].lower()
    assert any("live provider probe" in row.lower() for row in payload["hints"])


def test_cli_provider_login_openai_codex_keep_model_preserves_active_model(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_login = main(
        [
            "--config",
            str(config_path),
            "provider",
            "login",
            "openai-codex",
            "--access-token",
            "codex-token-keep-1234",
            "--keep-model",
            "--no-interactive",
        ]
    )
    assert rc_login == 0
    login_payload = json.loads(capsys.readouterr().out)
    assert login_payload["ok"] is True
    assert login_payload["model"] == "openai/gpt-4o-mini"

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["provider"]["model"] == "openai/gpt-4o-mini"


def test_cli_provider_login_openai_codex_rejects_conflicting_model_flags(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_login = main(
        [
            "--config",
            str(config_path),
            "provider",
            "login",
            "openai-codex",
            "--access-token",
            "codex-token-conflict-1234",
            "--set-model",
            "--keep-model",
            "--no-interactive",
        ]
    )
    assert rc_login == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "invalid_model_selection_options"


def test_cli_provider_status_minimax_reports_anthropic_family(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "mini-key-1234")
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_API_KEY", raising=False)

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "minimax/MiniMax-M2.5"},
                "providers": {
                    "minimax": {"api_base": "https://api.minimax.io/anthropic"}
                },
            }
        ),
        encoding="utf-8",
    )

    rc_status = main(["--config", str(config_path), "provider", "status", "minimax"])
    assert rc_status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["provider"] == "minimax"
    assert payload["transport"] == "anthropic"
    assert payload["family"] == "anthropic_compatible"
    assert payload["recommended_model"] == "minimax/MiniMax-M2.5"
    assert "minimax/MiniMax-M2.5" in payload["recommended_models"]
    assert "/anthropic" in payload["onboarding_hint"]


def test_provider_live_probe_vllm_network_error_returns_runtime_hint(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "vllm/meta-llama/Llama-3.2-3B-Instruct"},
                "agents": {
                    "defaults": {"model": "vllm/meta-llama/Llama-3.2-3B-Instruct"}
                },
                "providers": {"vllm": {"api_base": "http://127.0.0.1:8000/v1"}},
            }
        ),
        encoding="utf-8",
    )

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            del url, headers
            raise RuntimeError("connection refused")

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _Client)

    from clawlite.config.loader import load_config

    payload = provider_live_probe(load_config(config_path), timeout=0.1)
    assert payload["ok"] is False
    assert payload["provider"] == "vllm"
    assert payload["transport"] == "local_runtime"
    assert payload["probe_method"] == "GET"
    assert payload["error_class"] == "network"
    assert any("Start the vLLM server" in row for row in payload["hints"])


def test_provider_live_probe_openai_codex_uses_responses_backend(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai-codex/gpt-5.3-codex"},
                "agents": {"defaults": {"model": "openai-codex/gpt-5.3-codex"}},
                "auth": {
                    "providers": {"openai_codex": {"access_token": "tok-codex-1234"}}
                },
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        is_success = True

        def json(self):
            return {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ]
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = dict(headers or {})
            captured["json"] = dict(json or {})
            return _Response()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _Client)

    from clawlite.config.loader import load_config

    payload = provider_live_probe(load_config(config_path), timeout=0.1)
    assert payload["ok"] is True
    assert payload["provider"] == "openai_codex"
    assert payload["transport"] == "oauth_codex_responses"
    assert payload["probe_method"] == "POST"
    assert payload["endpoint"] == "/codex/responses"
    assert payload["base_url"] == "https://chatgpt.com/backend-api"
    assert captured["url"] == "https://chatgpt.com/backend-api/codex/responses"
    assert captured["headers"]["Authorization"] == "Bearer tok-codex-1234"
    assert captured["headers"]["Accept"] == "text/event-stream"
    assert captured["json"]["store"] is False
    assert captured["json"]["stream"] is True
    assert (
        captured["json"]["instructions"]
        == "You are a concise assistant. Reply briefly."
    )
    assert captured["json"]["tools"] == []
    assert captured["json"]["tool_choice"] == "auto"
    assert captured["json"]["parallel_tool_calls"] is False
    assert "max_output_tokens" not in captured["json"]
    assert captured["json"]["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "ping"}],
        }
    ]


def test_provider_live_probe_ollama_success_detects_missing_model(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "ollama/llama3.2"},
                "agents": {"defaults": {"model": "ollama/llama3.2"}},
                "providers": {"ollama": {"api_base": "http://127.0.0.1:11434/v1"}},
            }
        ),
        encoding="utf-8",
    )

    class _Response:
        def __init__(
            self,
            status_code: int,
            payload: dict[str, object],
            *,
            is_success: bool = True,
            text: str = "",
        ) -> None:
            self.status_code = status_code
            self._payload = payload
            self.is_success = is_success
            self.text = text

        def json(self) -> dict[str, object]:
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            del headers
            if url.endswith("/api/tags"):
                return _Response(200, {"models": [{"name": "mistral:latest"}]})
            raise AssertionError(url)

        def post(self, url, json=None):
            assert url.endswith("/api/show")
            assert json == {"name": "llama3.2"}
            return _Response(404, {}, is_success=False)

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _Client)
    monkeypatch.setattr("clawlite.providers.discovery.httpx.Client", _Client)

    from clawlite.config.loader import load_config

    payload = provider_live_probe(load_config(config_path), timeout=0.1)
    assert payload["ok"] is False
    assert payload["error"] == "provider_config_error:ollama_model_missing:llama3.2"
    assert payload["error_class"] == "config"
    assert payload["model_check"]["checked"] is True
    assert payload["model_check"]["available_models"] == ["mistral:latest"]
    assert any("ollama pull llama3.2" in row for row in payload["hints"])


def test_provider_live_probe_openai_model_not_listed_returns_soft_warning(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-1234")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4.1-mini"},
                "agents": {"defaults": {"model": "openai/gpt-4.1-mini"}},
            }
        ),
        encoding="utf-8",
    )

    class _Response:
        status_code = 200
        is_success = True
        text = "ok"

        @staticmethod
        def json() -> dict[str, list[dict[str, str]]]:
            return {"data": [{"id": "gpt-4o-mini"}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            assert url.endswith("/models")
            assert str(headers.get("Authorization", "")).startswith("Bearer sk-")
            return _Response()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _Client)

    from clawlite.config.loader import load_config

    payload = provider_live_probe(load_config(config_path), timeout=0.1)
    assert payload["ok"] is True
    assert payload["provider"] == "openai"
    assert payload["model_check"]["checked"] is True
    assert payload["model_check"]["ok"] is False
    assert payload["model_check"]["detail"] == "model_not_listed"
    assert any(
        "did not appear in the provider's remote list" in row.lower()
        for row in payload["hints"]
    )


def test_provider_live_probe_persists_snapshot_and_provider_status_reuses_it(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-1234")

    config_path = tmp_path / "config.json"
    state_path = tmp_path / "state"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
                "agents": {"defaults": {"model": "openai/gpt-4o-mini"}},
            }
        ),
        encoding="utf-8",
    )

    class _Response:
        status_code = 200
        is_success = True
        text = "ok"

        @staticmethod
        def json() -> dict[str, list[dict[str, str]]]:
            return {"data": [{"id": "gpt-4o-mini"}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            assert url.endswith("/models")
            assert str(headers.get("Authorization", "")).startswith("Bearer sk-")
            return _Response()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _Client)

    payload = provider_live_probe(load_config(config_path), timeout=0.1)
    assert payload["ok"] is True
    assert payload["capability_summary"]["checked"] is True
    assert payload["capability_summary"]["current_model_listed"] is True
    assert payload["capability_summary"]["listed_model_count"] == 1
    assert payload["last_capability_probe"]["source"] == "provider_live_probe"
    assert payload["last_capability_probe"]["checked_at"]

    cache_path = state_path / "provider-probes.json"
    assert cache_path.exists()
    cached_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached_payload["providers"]["openai"]["provider"] == "openai"
    assert cached_payload["providers"]["openai"]["source"] == "provider_live_probe"
    assert cached_payload["providers"]["openai"]["status_code"] == 200
    assert cached_payload["providers"]["openai"]["capability_summary"]["listed_model_sample"] == ["gpt-4o-mini"]

    rc_status = main(["--config", str(config_path), "provider", "status", "openai"])
    assert rc_status == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["last_live_probe"]["provider"] == "openai"
    assert status_payload["last_live_probe"]["ok"] is True
    assert status_payload["last_live_probe"]["source"] == "provider_live_probe"
    assert status_payload["last_live_probe"]["matches_current_model"] is True
    assert status_payload["last_live_probe"]["matches_current_base_url"] is True
    assert status_payload["last_capability_probe"]["provider"] == "openai"
    assert status_payload["last_capability_probe"]["current_model_listed"] is True
    assert status_payload["last_capability_probe"]["listed_model_count"] == 1


def test_provider_live_probe_snapshot_drops_raw_remote_error_detail(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-1234")

    config_path = tmp_path / "config.json"
    state_path = tmp_path / "state"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
                "agents": {"defaults": {"model": "openai/gpt-4o-mini"}},
            }
        ),
        encoding="utf-8",
    )

    class _Response:
        status_code = 401
        is_success = False
        text = "proxy reflected Authorization: Bearer sk-test-openai-1234"

        @staticmethod
        def json() -> dict[str, str]:
            raise ValueError("not json")

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            assert url.endswith("/models")
            assert str(headers.get("Authorization", "")).startswith("Bearer sk-")
            return _Response()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _Client)

    payload = provider_live_probe(load_config(config_path), timeout=0.1)
    assert payload["ok"] is False
    assert "sk-test-openai-1234" in payload["error_detail"]

    cache_path = state_path / "provider-probes.json"
    cached_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached_payload["providers"]["openai"]["error_detail"] == ""


def test_provider_live_probe_prefers_configured_vendor_transport_over_generic_model(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {
                    "model": "claude-3.5-sonnet",
                    "litellm_base_url": "https://api.minimax.io/anthropic",
                    "litellm_api_key": "mini-key",
                },
                "agents": {"defaults": {"model": "claude-3.5-sonnet"}},
                "providers": {
                    "minimax": {
                        "api_base": "https://api.minimax.io/anthropic",
                        "api_key": "mini-key",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class _Response:
        status_code = 200
        is_success = True
        text = "ok"

        @staticmethod
        def json() -> dict[str, object]:
            return {"id": "msg_123", "content": [{"type": "text", "text": "pong"}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            raise AssertionError(f"unexpected GET probe: {url} headers={headers}")

        def post(self, url, headers=None, json=None):
            assert url == "https://api.minimax.io/anthropic/messages"
            assert headers["x-api-key"] == "mini-key"
            assert headers["anthropic-version"] == "2023-06-01"
            assert json["model"] == "claude-3.5-sonnet"
            return _Response()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _Client)

    from clawlite.config.loader import load_config

    payload = provider_live_probe(load_config(config_path), timeout=0.1)
    assert payload["ok"] is True
    assert payload["provider"] == "minimax"
    assert payload["transport"] == "anthropic_compatible"
    assert payload["probe_method"] == "POST"


def test_cli_provider_status_unsupported_provider_returns_rc2(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_status = main(
        ["--config", str(config_path), "provider", "status", "unknown-provider"]
    )
    assert rc_status == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": False, "error": "unsupported_provider:unknown-provider"}


def test_cli_provider_login_unsupported_returns_rc2(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = cmd_provider_login(
        types.SimpleNamespace(
            config=str(config_path),
            provider="unknown-provider",
            access_token="",
            account_id="",
            set_model=False,
            no_interactive=True,
        )
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": False, "error": "unsupported_provider:unknown-provider"}


def test_cli_provider_logout_unsupported_returns_rc2(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = cmd_provider_logout(
        types.SimpleNamespace(
            config=str(config_path),
            provider="unknown-provider",
        )
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": False, "error": "unsupported_provider:unknown-provider"}


def test_cli_provider_use_success_updates_config_and_returns_rc0(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {
                    "model": "gemini/gemini-2.5-flash",
                    "fallback_model": "openai/gpt-4.1-mini",
                },
                "agents": {"defaults": {"model": "gemini/gemini-2.5-flash"}},
            }
        ),
        encoding="utf-8",
    )

    rc_use = main(
        [
            "--config",
            str(config_path),
            "provider",
            "use",
            "openai",
            "--model",
            "openai/gpt-4.1-mini",
            "--fallback-model",
            "openai/gpt-4o-mini",
        ]
    )
    assert rc_use == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["provider"] == "openai"
    assert payload["model"] == "openai/gpt-4.1-mini"
    assert payload["fallback_model"] == "openai/gpt-4o-mini"
    assert payload["transport"] == "openai_compatible"
    assert payload["family"] == "openai_compatible"
    assert payload["recommended_model"] == "openai/gpt-4o-mini"
    assert "openai/gpt-4o-mini" in payload["recommended_models"]
    assert "billing" in payload["onboarding_hint"].lower()

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["provider"]["model"] == "openai/gpt-4.1-mini"
    assert persisted["agents"]["defaults"]["model"] == "openai/gpt-4.1-mini"
    assert persisted["provider"]["fallback_model"] == "openai/gpt-4o-mini"


def test_cli_provider_use_unsupported_provider_returns_rc2(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_use = main(
        [
            "--config",
            str(config_path),
            "provider",
            "use",
            "unknown-provider",
            "--model",
            "openai/gpt-4.1-mini",
        ]
    )
    assert rc_use == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "unsupported_provider:unknown-provider"


def test_cli_provider_use_provider_model_mismatch_returns_rc2(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_use = main(
        [
            "--config",
            str(config_path),
            "provider",
            "use",
            "gemini",
            "--model",
            "openai/gpt-4.1-mini",
        ]
    )
    assert rc_use == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "provider_model_mismatch"
    assert payload["provider"] == "gemini"
    assert payload["expected"] == "gemini/*"
    assert payload["transport"] == "openai_compatible"
    assert payload["recommended_model"] == "gemini/gemini-2.5-flash"
    assert "gemini/gemini-2.5-flash" in payload["recommended_models"]
    assert "google generative language" in payload["onboarding_hint"].lower()


def test_cli_provider_use_fallback_model_mismatch_returns_rc2(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc_use = main(
        [
            "--config",
            str(config_path),
            "provider",
            "use",
            "openai",
            "--model",
            "openai/gpt-4.1-mini",
            "--fallback-model",
            "groq/llama-3.1-8b-instant",
        ]
    )
    assert rc_use == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "fallback_provider_model_mismatch"
    assert payload["provider"] == "openai"
    assert payload["fallback_model"] == "groq/llama-3.1-8b-instant"
    assert payload["detected_provider"] == "groq"
    assert payload["expected"] == "openai/*"
    assert payload["recommended_model"] == "openai/gpt-4o-mini"
    assert "billing" in payload["onboarding_hint"].lower()


def test_cli_validate_provider_surfaces_guidance_fields(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "mini-key-1234")
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_API_KEY", raising=False)

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "minimax/MiniMax-M2.5"},
                "providers": {
                    "minimax": {"api_base": "https://api.minimax.io/anthropic"}
                },
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "validate", "provider"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["provider"] == "minimax"
    assert payload["transport"] == "anthropic"
    assert payload["family"] == "anthropic_compatible"
    assert payload["recommended_model"] == "minimax/MiniMax-M2.5"
    assert "minimax/MiniMax-M2.5" in payload["recommended_models"]
    assert "/anthropic" in payload["onboarding_hint"]


def test_cli_validate_provider_surfaces_last_live_probe_snapshot(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "mini-key-1234")
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_API_KEY", raising=False)

    state_path = tmp_path / "state"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "minimax/MiniMax-M2.5"},
                "providers": {
                    "minimax": {"api_base": "https://api.minimax.io/anthropic"}
                },
            }
        ),
        encoding="utf-8",
    )

    save_provider_probe_snapshot(
        state_path,
        provider="minimax",
        payload={
            "ok": True,
            "provider": "minimax",
            "model": "minimax/MiniMax-M2.5",
            "base_url": "https://api.minimax.io/anthropic",
            "base_url_source": "config:providers.minimax.api_base",
            "transport": "anthropic_compatible",
            "probe_method": "POST",
            "endpoint": "/messages",
            "status_code": 200,
            "family": "anthropic_compatible",
            "recommended_model": "minimax/MiniMax-M2.5",
            "recommended_models": ["minimax/MiniMax-M2.5"],
            "onboarding_hint": "MiniMax uses the Anthropic-compatible /messages path.",
            "hints": ["Credenciais validas."],
            "model_check": {"checked": False, "ok": True},
        },
    )

    rc = main(["--config", str(config_path), "validate", "provider"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["last_live_probe"]["provider"] == "minimax"
    assert payload["last_live_probe"]["ok"] is True
    assert payload["last_live_probe"]["transport"] == "anthropic_compatible"
    assert payload["last_live_probe"]["source"] == "provider_live_probe"
    assert payload["last_live_probe"]["matches_current_model"] is True
    assert payload["last_live_probe"]["matches_current_base_url"] is True
    assert payload["last_capability_probe"]["provider"] == "minimax"
    assert payload["last_capability_probe"]["checked"] is False
    assert payload["last_capability_probe"]["detail"] == "model_list_unavailable"


def test_cli_provider_status_derives_capability_summary_from_legacy_probe_snapshot(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-1234")

    state_path = tmp_path / "state"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
                "provider": {"model": "openai/gpt-4o-mini"},
                "agents": {"defaults": {"model": "openai/gpt-4o-mini"}},
            }
        ),
        encoding="utf-8",
    )

    cache_path = state_path / "provider-probes.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "providers": {
                    "openai": {
                        "provider": "openai",
                        "model": "openai/gpt-4o-mini",
                        "base_url": "https://api.openai.com/v1",
                        "transport": "openai_compatible",
                        "status_code": 200,
                        "ok": True,
                        "source": "provider_live_probe",
                        "checked_at": "2026-03-25T00:00:00+00:00",
                        "model_check": {
                            "checked": True,
                            "ok": True,
                            "detail": "model_listed",
                            "matched_model": "gpt-4o-mini",
                            "available_models": ["gpt-4o-mini", "gpt-4.1-mini"],
                        },
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc_status = main(["--config", str(config_path), "provider", "status", "openai"])
    assert rc_status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["last_live_probe"]["provider"] == "openai"
    assert payload["last_capability_probe"]["provider"] == "openai"
    assert payload["last_capability_probe"]["source"] == "provider_live_probe"
    assert payload["last_capability_probe"]["checked_at"] == "2026-03-25T00:00:00+00:00"
    assert payload["last_capability_probe"]["current_model_listed"] is True
    assert payload["last_capability_probe"]["listed_model_count"] == 2
    assert payload["last_capability_probe"]["listed_model_sample"] == ["gpt-4o-mini", "gpt-4.1-mini"]


def test_cli_provider_use_clear_fallback_clears_config(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {
                    "model": "openai/gpt-4.1-mini",
                    "fallback_model": "openai/gpt-4o-mini",
                },
                "agents": {"defaults": {"model": "openai/gpt-4.1-mini"}},
            }
        ),
        encoding="utf-8",
    )

    rc_use = main(
        [
            "--config",
            str(config_path),
            "provider",
            "use",
            "openai",
            "--model",
            "openai/gpt-4.1-mini",
            "--clear-fallback",
        ]
    )
    assert rc_use == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["fallback_model"] == ""

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["provider"]["fallback_model"] == ""


def test_cli_provider_commands_do_not_import_gateway_runtime(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai-codex/gpt-5.3-codex"},
            }
        ),
        encoding="utf-8",
    )

    sys.modules.pop("clawlite.gateway.server", None)
    rc_status = main(
        ["--config", str(config_path), "provider", "status", "openai-codex"]
    )
    assert rc_status in {0, 2}
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_login = main(
        [
            "--config",
            str(config_path),
            "provider",
            "login",
            "openai-codex",
            "--access-token",
            "codex-token-5678",
            "--no-interactive",
        ]
    )
    assert rc_login == 0
    assert "clawlite.gateway.server" not in sys.modules

    capsys.readouterr()
    sys.modules.pop("clawlite.gateway.server", None)
    rc_use = main(
        [
            "--config",
            str(config_path),
            "provider",
            "use",
            "openai-codex",
            "--model",
            "openai-codex/gpt-5.3-codex",
        ]
    )
    assert rc_use == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_provider_status_openai_codex_uses_auth_file_when_config_and_env_missing(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "auth_mode": "login",
                "tokens": {
                    "access_token": "codex-file-token-1234",
                    "account_id": "org-file-1234",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLAWLITE_CODEX_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("OPENAI_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ORG_ID", raising=False)
    monkeypatch.setenv("CLAWLITE_CODEX_AUTH_PATH", str(auth_path))

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai-codex/gpt-5.3-codex"},
            }
        ),
        encoding="utf-8",
    )

    rc_status = main(
        ["--config", str(config_path), "provider", "status", "openai-codex"]
    )
    assert rc_status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["configured"] is True
    assert payload["source"] == f"file:{auth_path}"
    assert payload["token_masked"]
    assert payload["account_id_masked"]


def test_cli_provider_status_openai_codex_prefers_current_file_when_config_snapshot_is_stale(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "auth_mode": "login",
                "tokens": {
                    "access_token": "codex-file-token-fresh",
                    "account_id": "org-file-fresh",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLAWLITE_CODEX_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("OPENAI_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ORG_ID", raising=False)
    monkeypatch.setenv("CLAWLITE_CODEX_AUTH_PATH", str(auth_path))

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai-codex/gpt-5.3-codex"},
                "auth": {
                    "providers": {
                        "openai_codex": {
                            "access_token": "stale-config-token",
                            "account_id": "org-stale",
                            "source": f"file:{auth_path}",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    rc_status = main(["--config", str(config_path), "provider", "status", "openai-codex"])

    assert rc_status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["configured"] is True
    assert payload["source"] == f"file:{auth_path}"
    assert payload["account_id_masked"].endswith("resh")


def test_cli_validate_provider_reports_local_runtime_failure(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {
                    "model": "openai/llama3.2",
                    "litellm_base_url": "http://127.0.0.1:11434",
                },
                "providers": {
                    "openai": {
                        "api_base": "http://127.0.0.1:11434",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "clawlite.cli.ops.probe_local_provider_runtime",
        lambda *, model, base_url, timeout_s=2.0: {
            "checked": True,
            "ok": False,
            "runtime": "ollama",
            "model": "llama3.2",
            "base_url": base_url,
            "error": "provider_config_error:ollama_unreachable:http://127.0.0.1:11434",
            "detail": "connection_refused",
            "available_models": [],
        },
    )

    rc = main(["--config", str(config_path), "validate", "provider"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert any(
        check.get("name") == "local_runtime" and check.get("status") == "error"
        for check in payload["checks"]
    )


def test_cli_validate_provider_accepts_local_runtime_without_api_key(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {
                    "model": "openai/llama3.2",
                    "litellm_base_url": "http://127.0.0.1:11434/v1",
                },
                "providers": {
                    "ollama": {
                        "api_base": "http://127.0.0.1:11434/v1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "clawlite.cli.ops.probe_local_provider_runtime",
        lambda *, model, base_url, timeout_s=2.0: {
            "checked": True,
            "ok": True,
            "runtime": "ollama",
            "model": "llama3.2",
            "base_url": base_url,
            "error": "",
            "detail": "",
            "available_models": ["llama3.2:latest"],
        },
    )

    rc = main(["--config", str(config_path), "validate", "provider"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert any(
        check.get("name") == "api_key" and check.get("status") == "ok"
        for check in payload["checks"]
    )
    assert any(
        check.get("name") == "local_runtime" and check.get("status") == "ok"
        for check in payload["checks"]
    )


def test_cli_provider_set_auth_and_clear_auth_persist_config(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "providers": {
                    "openai": {
                        "api_key": "",
                        "api_base": "https://api.openai.com/v1",
                        "extra_headers": {"X-Old": "1"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    rc_set = main(
        [
            "--config",
            str(config_path),
            "provider",
            "set-auth",
            "openai",
            "--api-key",
            "sk-live-new-1234",
            "--api-base",
            "https://alt.example/v1",
            "--clear-headers",
            "--header",
            "X-Trace=abc",
            "--header",
            "X-Env=prod",
        ]
    )
    assert rc_set == 0
    set_payload = json.loads(capsys.readouterr().out)
    assert set_payload["ok"] is True
    assert set_payload["provider"] == "openai"
    assert set_payload["api_key_masked"].endswith("1234")
    assert set_payload["api_base"] == "https://alt.example/v1"
    assert set_payload["extra_headers"] == {"X-Trace": "abc", "X-Env": "prod"}

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["providers"]["openai"]["api_key"] == "sk-live-new-1234"
    assert persisted["providers"]["openai"]["api_base"] == "https://alt.example/v1"
    assert persisted["providers"]["openai"]["extra_headers"] == {
        "X-Trace": "abc",
        "X-Env": "prod",
    }

    rc_clear = main(
        [
            "--config",
            str(config_path),
            "provider",
            "clear-auth",
            "openai",
            "--clear-api-base",
        ]
    )
    assert rc_clear == 0
    clear_payload = json.loads(capsys.readouterr().out)
    assert clear_payload["ok"] is True
    assert clear_payload["provider"] == "openai"
    assert clear_payload["api_key_masked"] == ""
    assert clear_payload["api_base"] == ""
    assert clear_payload["extra_headers"] == {}

    persisted_after = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted_after["providers"]["openai"]["api_key"] == ""
    assert persisted_after["providers"]["openai"]["api_base"] == ""
    assert persisted_after["providers"]["openai"]["extra_headers"] == {}


def test_cli_provider_set_auth_supports_dynamic_provider_blocks(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "xai/grok-4"},
            }
        ),
        encoding="utf-8",
    )

    rc_set = main(
        [
            "--config",
            str(config_path),
            "provider",
            "set-auth",
            "xai",
            "--api-key",
            "xai-live-1234",
            "--api-base",
            "https://api.x.ai/v1",
        ]
    )
    assert rc_set == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["provider"] == "xai"
    assert payload["api_base"] == "https://api.x.ai/v1"

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["providers"]["xai"]["api_key"] == "xai-live-1234"
    assert persisted["providers"]["xai"]["api_base"] == "https://api.x.ai/v1"

    rc_status = main(["--config", str(config_path), "provider", "status", "xai"])
    assert rc_status == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["ok"] is True
    assert status_payload["provider"] == "xai"
    assert status_payload["configured"] is True


def test_cli_provider_set_auth_invalid_header_returns_rc2(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "provider",
            "set-auth",
            "openai",
            "--api-key",
            "sk-test-1234",
            "--header",
            "INVALID_HEADER",
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "invalid_header_format:INVALID_HEADER"


def test_cli_provider_set_auth_unsupported_provider_returns_rc2(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "provider",
            "set-auth",
            "unknown-provider",
            "--api-key",
            "sk-test-1234",
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "unsupported_provider:unknown-provider"


def test_cli_heartbeat_trigger_success_uses_default_url_and_token(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.9",
                    "port": 8877,
                    "auth": {"token": "gw-token-abc"},
                },
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "decision": {
                    "action": "send",
                    "reason": "heartbeat_signal",
                    "text": "ping",
                },
            }

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            captured["timeout"] = timeout
            captured["headers"] = dict(headers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url):
            captured["url"] = url
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "heartbeat", "trigger"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status_code"] == 200
    assert payload["decision"]["action"] == "send"
    assert payload["base_url"] == "http://127.0.0.9:8877"
    assert captured["url"] == "http://127.0.0.9:8877/v1/control/heartbeat/trigger"
    assert captured["headers"] == {"Authorization": "Bearer gw-token-abc"}


def test_cli_heartbeat_trigger_failure_returns_rc2(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 409
            self.is_success = False

        def json(self) -> dict[str, object]:
            return {"detail": "heartbeat_disabled"}

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url):
            del url
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(
        [
            "--config",
            str(config_path),
            "heartbeat",
            "trigger",
            "--gateway-url",
            "http://127.0.0.1:8787",
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["status_code"] == 409
    assert payload["error"] == "heartbeat_disabled"


def test_cli_telegram_status_uses_gateway_dashboard_state(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.9",
                    "port": 8877,
                    "auth": {"token": "gw-token-abc"},
                },
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {
                "telegram": {
                    "available": True,
                    "offset_next": 42,
                    "hints": [
                        "Webhook mode is requested but not active; try refreshing Telegram transport."
                    ],
                }
            }

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            captured["timeout"] = timeout
            captured["headers"] = dict(headers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            captured["url"] = url
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "telegram", "status"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["telegram"]["offset_next"] == 42
    assert payload["telegram"]["hints"] == [
        "Webhook mode is requested but not active; try refreshing Telegram transport."
    ]
    assert captured["url"] == "http://127.0.0.9:8877/api/dashboard/state"
    assert captured["headers"] == {"Authorization": "Bearer gw-token-abc"}


def test_cli_telegram_refresh_and_offset_commit_use_gateway_controls(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "t-123"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.status_code = 200
            self.is_success = True
            self._payload = payload

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            if url.endswith("/refresh"):
                return _FakeResponse({"ok": True, "summary": {"connected": True}})
            return _FakeResponse({"ok": True, "summary": {"update_id": 144}})

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc_refresh = main(["--config", str(config_path), "telegram", "refresh"])
    assert rc_refresh == 0
    refresh_payload = json.loads(capsys.readouterr().out)
    assert refresh_payload["ok"] is True
    assert refresh_payload["summary"]["connected"] is True

    rc_commit = main(["--config", str(config_path), "telegram", "offset-commit", "144"])
    assert rc_commit == 0
    commit_payload = json.loads(capsys.readouterr().out)
    assert commit_payload["ok"] is True
    assert commit_payload["summary"]["update_id"] == 144

    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/channels/telegram/refresh",
        {},
    )
    assert calls[1] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/channels/telegram/offset/commit",
        {"update_id": 144},
    )


def test_cli_generate_self_writes_runtime_and_requested_outputs(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    runtime_workspace = tmp_path / "runtime-workspace"
    repo_workspace = tmp_path / "workspace" / "SELF.md"
    repo_docs = tmp_path / "docs" / "SELF.md"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(runtime_workspace),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "generate-self",
            "--out",
            str(repo_workspace),
            "--out",
            str(repo_docs),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert (runtime_workspace / "SELF.md").exists()
    assert repo_workspace.exists()
    assert repo_docs.exists()
    assert "# SELF.md" in repo_workspace.read_text(encoding="utf-8")
    assert "## 1. O que é o ClawLite" in repo_docs.read_text(encoding="utf-8")


def test_cli_telegram_offset_sync_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "t-123"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {"ok": True, "summary": {"next_offset": 145}}

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "telegram", "offset-sync", "145"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["next_offset"] == 145
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/channels/telegram/offset/sync",
        {"next_offset": 145, "allow_reset": False},
    )


def test_cli_telegram_offset_reset_requires_confirmation(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--config", str(config_path), "telegram", "offset-reset"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "confirmation_required"


def test_cli_telegram_offset_reset_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "t-123"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {"ok": True, "summary": {"next_offset": 0}}

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "telegram", "offset-reset", "--yes"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/channels/telegram/offset/sync",
        {"next_offset": 0, "allow_reset": True},
    )


def test_cli_provider_recover_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "prov-token"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {"ok": True, "summary": {"cleared": 1, "role": "primary"}}

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(
        ["--config", str(config_path), "provider", "recover", "--role", "primary"]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["cleared"] == 1
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/provider/recover",
        {"role": "primary", "model": ""},
    )


def test_cli_discord_status_uses_gateway_dashboard_state(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.9",
                    "port": 8877,
                    "auth": {"token": "gw-token-xyz"},
                },
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {
                "discord": {
                    "available": True,
                    "gateway_task_state": "running",
                    "session_id": "sess-1",
                    "hints": [
                        "Discord gateway listener is not running; refresh transport to reconnect the gateway loop."
                    ],
                }
            }

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            captured["timeout"] = timeout
            captured["headers"] = dict(headers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            captured["url"] = url
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "discord", "status"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["discord"]["session_id"] == "sess-1"
    assert captured["url"] == "http://127.0.0.9:8877/api/dashboard/state"
    assert captured["headers"] == {"Authorization": "Bearer gw-token-xyz"}


def test_cli_discord_refresh_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "d-123"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {"ok": True, "summary": {"gateway_restarted": True}}

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "discord", "refresh"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["gateway_restarted"] is True
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/channels/discord/refresh",
        {},
    )


def test_cli_restart_gateway_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "gw-token"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {"ok": True, "summary": {"gateway_restarted": True, "scheduled": True}}

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(
        [
            "--config",
            str(config_path),
            "restart-gateway",
            "--reason",
            "operator_request",
            "--delay-s",
            "0.25",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["gateway_restarted"] is True
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/gateway/restart",
        {"reason": "operator_request", "delay_s": 0.25},
    )


def test_cli_supervisor_recover_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "sup-token"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {"ok": True, "summary": {"recovered": 1, "component": "heartbeat"}}

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(
        [
            "--config",
            str(config_path),
            "supervisor",
            "recover",
            "--component",
            "heartbeat",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["recovered"] == 1
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/supervisor/recover",
        {"component": "heartbeat", "force": True, "reason": "operator_recover"},
    )


def test_cli_autonomy_wake_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "aut-token"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {"ok": True, "summary": {"kind": "proactive", "status": "ok"}}

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "autonomy", "wake", "--kind", "proactive"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["kind"] == "proactive"
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/autonomy/wake",
        {"kind": "proactive"},
    )


def test_cli_skills_refresh_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "skills-token"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "summary": {
                    "ok": True,
                    "refresh": {"refreshed": True, "debounced": False},
                    "skills": {"available": 12, "runnable": 9},
                    "watcher": {"task_state": "running", "last_error": ""},
                },
            }

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "skills", "refresh"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["refresh"]["refreshed"] is True
    assert payload["summary"]["skills"]["available"] == 12
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/skills/refresh",
        {"force": True},
    )


def test_cli_skills_refresh_no_force_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "skills-token"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "summary": {
                    "ok": True,
                    "refresh": {"refreshed": False, "debounced": True},
                    "skills": {"available": 12, "runnable": 9},
                    "watcher": {"task_state": "running", "last_error": ""},
                },
            }

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "skills", "refresh", "--no-force"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["refresh"]["debounced"] is True
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/skills/refresh",
        {"force": False},
    )


def test_cli_skills_validate_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "skills-token"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {
                "ok": False,
                "summary": {
                    "ok": False,
                    "action": "skills_validate",
                    "refresh": {"refreshed": True, "debounced": False},
                    "count": 1,
                    "status_filter": "missing_requirements",
                    "source_filter": "builtin",
                    "query": "github",
                    "recommendations": ["Export GH_TOKEN"],
                },
            }

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(
        [
            "--config",
            str(config_path),
            "skills",
            "validate",
            "--all",
            "--status",
            "missing_requirements",
            "--source",
            "builtin",
            "--query",
            "github",
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["summary"]["action"] == "skills_validate"
    assert payload["summary"]["count"] == 1
    assert payload["summary"]["recommendations"] == ["Export GH_TOKEN"]
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/skills/validate",
        {
            "force": True,
            "include_all": True,
            "status": "missing_requirements",
            "source": "builtin",
            "query": "github",
        },
    )


def test_cli_skills_validate_no_force_uses_gateway_control(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {
                    "host": "127.0.0.1",
                    "port": 8787,
                    "auth": {"token": "skills-token"},
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object]] = []

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "summary": {
                    "ok": True,
                    "action": "skills_validate",
                    "refresh": {"refreshed": False, "debounced": True},
                    "count": 0,
                },
            }

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json))
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    rc = main(["--config", str(config_path), "skills", "validate", "--no-force"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["refresh"]["debounced"] is True
    assert calls[0] == (
        "POST",
        "http://127.0.0.1:8787/v1/control/skills/validate",
        {
            "force": False,
            "include_all": False,
            "status": "",
            "source": "",
            "query": "",
        },
    )


def test_cli_provider_set_auth_and_heartbeat_do_not_import_gateway_runtime(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
                "gateway": {"host": "127.0.0.1", "port": 8787, "auth": {"token": "t"}},
            }
        ),
        encoding="utf-8",
    )

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.is_success = True

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "decision": {"action": "send", "reason": "ok", "text": ""},
            }

    class _FakeClient:
        def __init__(self, *, timeout, headers):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url):
            del url
            return _FakeResponse()

    monkeypatch.setattr("clawlite.cli.ops.httpx.Client", _FakeClient)

    sys.modules.pop("clawlite.gateway.server", None)
    rc_set = main(
        [
            "--config",
            str(config_path),
            "provider",
            "set-auth",
            "openai",
            "--api-key",
            "sk-test-1234",
        ]
    )
    assert rc_set == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_hb = main(["--config", str(config_path), "heartbeat", "trigger"])
    assert rc_hb == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_validate_provider_codex_requires_token_and_passes_when_configured(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("CLAWLITE_CODEX_AUTH_PATH", str(tmp_path / "missing-auth.json"))

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai-codex/gpt-5.3-codex"},
                "auth": {"providers": {"openai_codex": {"access_token": ""}}},
            }
        ),
        encoding="utf-8",
    )

    rc_missing = main(["--config", str(config_path), "validate", "provider"])
    assert rc_missing == 2
    missing_payload = json.loads(capsys.readouterr().out)
    assert missing_payload["ok"] is False
    assert any(
        "oauth_access_token" == check.get("name") and check.get("status") == "error"
        for check in missing_payload["checks"]
    )

    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai-codex/gpt-5.3-codex"},
                "auth": {
                    "providers": {"openai_codex": {"access_token": "tok-codex-999"}}
                },
            }
        ),
        encoding="utf-8",
    )

    rc_ok = main(["--config", str(config_path), "validate", "provider"])
    assert rc_ok == 0
    ok_payload = json.loads(capsys.readouterr().out)
    assert ok_payload["ok"] is True
    assert ok_payload["oauth_token_masked"]
