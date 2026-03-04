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
