from __future__ import annotations

import json
import sys
from pathlib import Path

from clawlite.cli.commands import main


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
    assert "Atlas" in content


def test_cli_onboard_wizard_mode_routes_to_runner(tmp_path: Path, capsys, monkeypatch) -> None:
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

    def _fake_wizard(config, *, config_path, overwrite, variables):
        called["ok"] = True
        assert overwrite is True
        assert str(config.agents.defaults.model).startswith("openai/")
        assert variables["assistant_name"] == "Fox"
        return {
            "ok": True,
            "mode": "wizard",
            "final": {"gateway_url": "http://127.0.0.1:8787", "gateway_token": "tok-test-123"},
        }

    monkeypatch.setattr("clawlite.cli.commands.run_onboarding_wizard", _fake_wizard)
    rc = main(
        [
            "--config",
            str(config_path),
            "onboard",
            "--wizard",
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


def test_cli_skills_list_and_show(capsys) -> None:
    rc_list = main(["skills", "list"])
    assert rc_list == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload.get("skills"), list)
    assert any(item.get("name") == "cron" for item in payload["skills"])

    rc_show = main(["skills", "show", "cron"])
    assert rc_show == 0
    out_show = capsys.readouterr().out
    one = json.loads(out_show)
    assert one.get("name") == "cron"
    assert "Schedule" in one.get("description", "")


def test_cli_skills_check_returns_diagnostics_report(capsys) -> None:
    rc = main(["skills", "check"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {
        "summary",
        "execution_kinds",
        "sources",
        "missing_requirements",
        "contract_issues",
        "skills",
    }
    summary = payload["summary"]
    assert summary["total"] == summary["available"] + summary["unavailable"]


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
                "agents": {"defaults": {"memory_window": 17, "session_retention_messages": 77}},
                "channels": {"telegram": {"enabled": True}, "discord": {"enabled": False}},
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

    def _fake_run_gateway(*, host, port):
        called["ok"] = True
        assert host == "127.0.0.1"
        assert port == 8787

    monkeypatch.setattr("clawlite.gateway.server.run_gateway", _fake_run_gateway)
    rc = main(["--config", str(config_path), "gateway"])
    assert rc == 0
    assert called["ok"] is True


def test_cli_onboard_creates_missing_default_config_and_prints_notice(tmp_path: Path, monkeypatch, capsys) -> None:
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


def test_cli_start_creates_missing_default_config_and_prints_notice(tmp_path: Path, monkeypatch, capsys) -> None:
    default_config = tmp_path / ".clawlite" / "config.json"
    monkeypatch.setattr("clawlite.cli.commands.DEFAULT_CONFIG_PATH", default_config)
    monkeypatch.setattr("clawlite.config.loader.DEFAULT_CONFIG_PATH", default_config)
    monkeypatch.setenv("CLAWLITE_WORKSPACE", str(tmp_path / "workspace"))

    called = {"ok": False}

    def _fake_run_gateway(*, host, port):
        called["ok"] = True
        assert host == "127.0.0.1"
        assert port == 8787

    monkeypatch.setattr("clawlite.gateway.server.run_gateway", _fake_run_gateway)

    rc = main(["start"])
    assert rc == 0
    assert default_config.exists()
    assert called["ok"] is True

    out = capsys.readouterr().out
    assert "Config criado em ~/.clawlite/config.json." in out


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


def test_cli_validate_provider_and_channels(tmp_path: Path, capsys, monkeypatch) -> None:
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
                "agents": {"defaults": {"memory_window": 29, "session_retention_messages": 111}},
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


def test_cli_non_runtime_validate_and_diagnostics_do_not_import_gateway(tmp_path: Path, capsys) -> None:
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


def test_cli_validate_config_does_not_import_gateway_runtime(tmp_path: Path, capsys) -> None:
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


def test_cli_validate_channels_slack_bot_only_is_ok_with_warning(tmp_path: Path, capsys) -> None:
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

    rc = main(["--config", str(config_path), "memory", "doctor"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["repair_applied"] is False
    assert set(payload["paths"].keys()) == {"history", "curated", "checkpoints"}
    assert set(payload["files"].keys()) == {"history", "curated", "checkpoints"}
    assert set(payload["counts"].keys()) == {"history", "curated", "total"}
    assert set(payload["analysis"].keys()) == {"recent", "temporal_marked_count", "top_sources"}
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


def test_cli_memory_doctor_repair_handles_corrupt_history_line(tmp_path: Path, capsys) -> None:
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
                json.dumps({"id": "a1", "text": "remember alpha", "source": "seed", "created_at": "2026-01-01T00:00:00+00:00"}),
                "{broken-json",
                json.dumps({"id": "b2", "text": "remember beta", "source": "seed", "created_at": "2026-01-02T00:00:00+00:00"}),
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

    repaired_lines = [line for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(repaired_lines) == 2
    assert all("broken-json" not in line for line in repaired_lines)


def test_cli_memory_doctor_does_not_import_gateway_runtime(tmp_path: Path, capsys) -> None:
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


def test_cli_memory_eval_does_not_import_gateway_runtime(tmp_path: Path, capsys) -> None:
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


def test_cli_memory_suggest_returns_list_without_crashing_on_empty(tmp_path: Path, capsys) -> None:
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


def test_cli_memory_snapshot_and_rollback_restores_previous_state(tmp_path: Path, capsys) -> None:
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

    rc_snapshot = main(["--config", str(config_path), "memory", "snapshot", "--tag", "baseline"])
    assert rc_snapshot == 0
    snapshot_payload = json.loads(capsys.readouterr().out)
    version_id = snapshot_payload["version_id"]
    assert version_id

    history_path.write_text("\n".join([json.dumps(row_a), json.dumps(row_b)]) + "\n", encoding="utf-8")

    rc_rollback = main(["--config", str(config_path), "memory", "rollback", version_id])
    assert rc_rollback == 0
    rollback_payload = json.loads(capsys.readouterr().out)
    assert rollback_payload["ok"] is True
    restored = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
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
    rc_export = main(["--config", str(config_path), "memory", "export", "--out", str(export_path)])
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

    rc_import = main(["--config", str(config_path), "memory", "import", str(export_path)])
    assert rc_import == 0
    import_payload = json.loads(capsys.readouterr().out)
    assert import_payload["ok"] is True
    rows_after_import = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = {row["id"] for row in rows_after_import}
    assert ids == {"exp-a"}


def test_cli_memory_branching_commands_return_expected_shapes(tmp_path: Path, capsys) -> None:
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

    assert main(["--config", str(config_path), "memory", "snapshot", "--tag", "seed"]) == 0
    capsys.readouterr()

    rc_branches = main(["--config", str(config_path), "memory", "branches"])
    assert rc_branches == 0
    branches_payload = json.loads(capsys.readouterr().out)
    assert branches_payload["ok"] is True
    assert branches_payload["current"] == "main"
    assert isinstance(branches_payload["branches"], dict)

    rc_branch = main(["--config", str(config_path), "memory", "branch", "feature-x", "--checkout"])
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

    rc_share = main(["--config", str(config_path), "memory", "share-optin", "--user", "42", "--enabled", "true"])
    assert rc_share == 0
    share_payload = json.loads(capsys.readouterr().out)
    assert share_payload == {"ok": True, "user_id": "42", "enabled": True}


def test_cli_memory_branching_commands_do_not_import_gateway_runtime(tmp_path: Path, capsys) -> None:
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
    rc_share = main(["--config", str(config_path), "memory", "share-optin", "--user", "99", "--enabled", "false"])
    assert rc_share == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_new_memory_commands_do_not_import_gateway_runtime(tmp_path: Path, capsys) -> None:
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
    rc_suggest = main(["--config", str(config_path), "memory", "suggest", "--no-refresh"])
    assert rc_suggest == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    export_path = tmp_path / "portable.json"
    sys.modules.pop("clawlite.gateway.server", None)
    rc_export = main(["--config", str(config_path), "memory", "export", "--out", str(export_path)])
    assert rc_export == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_provider_login_status_logout_openai_codex(tmp_path: Path, capsys) -> None:
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
            "--set-model",
            "--no-interactive",
        ]
    )
    assert rc_login == 0
    login_payload = json.loads(capsys.readouterr().out)
    assert login_payload["ok"] is True
    assert login_payload["configured"] is True

    rc_status = main(["--config", str(config_path), "provider", "status", "openai-codex"])
    assert rc_status == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["configured"] is True
    assert status_payload["provider"] == "openai_codex"
    assert status_payload["model"] == "openai-codex/gpt-5.3-codex"

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["auth"]["providers"]["openai_codex"]["access_token"] == "codex-token-1234"
    assert persisted["auth"]["providers"]["openai_codex"]["account_id"] == "org-123"

    rc_logout = main(["--config", str(config_path), "provider", "logout", "openai-codex"])
    assert rc_logout == 0
    logout_payload = json.loads(capsys.readouterr().out)
    assert logout_payload["configured"] is False

    persisted_after = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted_after["auth"]["providers"]["openai_codex"]["access_token"] == ""
    assert persisted_after["auth"]["providers"]["openai_codex"]["account_id"] == ""


def test_cli_provider_status_openai_api_key_provider_success(tmp_path: Path, capsys, monkeypatch) -> None:
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
    assert payload["api_key_source"] == "env:OPENAI_API_KEY"
    assert payload["env_key_present"] is True
    assert payload["base_url"] == "https://api.openai.com/v1"


def test_cli_provider_status_unsupported_provider_returns_rc2(tmp_path: Path, capsys) -> None:
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

    rc_status = main(["--config", str(config_path), "provider", "status", "unknown-provider"])
    assert rc_status == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": False, "error": "unsupported_provider:unknown-provider"}


def test_cli_provider_use_success_updates_config_and_returns_rc0(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "gemini/gemini-2.5-flash", "fallback_model": "openai/gpt-4.1-mini"},
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

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["provider"]["model"] == "openai/gpt-4.1-mini"
    assert persisted["agents"]["defaults"]["model"] == "openai/gpt-4.1-mini"
    assert persisted["provider"]["fallback_model"] == "openai/gpt-4o-mini"


def test_cli_provider_use_unsupported_provider_returns_rc2(tmp_path: Path, capsys) -> None:
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


def test_cli_provider_use_provider_model_mismatch_returns_rc2(tmp_path: Path, capsys) -> None:
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


def test_cli_provider_use_clear_fallback_clears_config(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4.1-mini", "fallback_model": "openai/gpt-4o-mini"},
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


def test_cli_provider_commands_do_not_import_gateway_runtime(tmp_path: Path, capsys) -> None:
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
    rc_status = main(["--config", str(config_path), "provider", "status", "openai-codex"])
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


def test_cli_validate_provider_codex_requires_token_and_passes_when_configured(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ACCESS_TOKEN", raising=False)

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
    assert any("oauth_access_token" == check.get("name") and check.get("status") == "error" for check in missing_payload["checks"])

    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai-codex/gpt-5.3-codex"},
                "auth": {"providers": {"openai_codex": {"access_token": "tok-codex-999"}}},
            }
        ),
        encoding="utf-8",
    )

    rc_ok = main(["--config", str(config_path), "validate", "provider"])
    assert rc_ok == 0
    ok_payload = json.loads(capsys.readouterr().out)
    assert ok_payload["ok"] is True
    assert ok_payload["oauth_token_masked"]
