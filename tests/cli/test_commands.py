from __future__ import annotations

import json
import sys
from pathlib import Path

from clawlite.cli.commands import main
from clawlite.cli.ops import provider_live_probe
from clawlite.channels.telegram_pairing import TelegramPairingStore
from clawlite.workspace.loader import TEMPLATE_FILES


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
    cron = next(item for item in payload["skills"] if item.get("name") == "cron")
    assert "enabled" in cron
    assert "pinned" in cron
    assert "version" in cron

    rc_show = main(["skills", "show", "cron"])
    assert rc_show == 0
    out_show = capsys.readouterr().out
    one = json.loads(out_show)
    assert one.get("name") == "cron"
    assert "Schedule" in one.get("description", "")
    assert "enabled" in one
    assert "pinned" in one
    assert "version" in one


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
        "contract_issues",
        "skills",
    }
    assert payload["watcher"]["enabled"] is True
    summary = payload["summary"]
    assert summary["total"] == summary["available"] + summary["unavailable"]
    assert summary["enabled"] == summary["total"] - summary["disabled"]


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
    request, created = store.issue_request(chat_id="55", user_id="321", username="guest", first_name="Guest")
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

    rc_approve = main(["--config", str(config_path), "pairing", "approve", "telegram", code])
    assert rc_approve == 0
    payload_approve = json.loads(capsys.readouterr().out)
    assert payload_approve["ok"] is True
    assert payload_approve["channel"] == "telegram"
    assert payload_approve["code"] == code
    assert payload_approve["request"]["user_id"] == "321"
    assert "321" in payload_approve["approved_entries"]
    assert "guest" in payload_approve["approved_entries"]
    assert "@guest" in payload_approve["approved_entries"]


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


def test_cli_validate_preflight_local_success(tmp_path: Path, capsys, monkeypatch) -> None:
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


def test_cli_validate_preflight_optional_probes_success(tmp_path: Path, capsys, monkeypatch) -> None:
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
            "onboarding_hint": "OpenAI responde via endpoint OpenAI-compatible padrão; valide billing e projeto ativo.",
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
    assert payload["provider_live_probe"]["recommended_models"] == ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]
    assert "billing" in payload["provider_live_probe"]["onboarding_hint"].lower()
    assert payload["provider_live_probe"]["hints"] == ["Credenciais validas."]
    assert payload["telegram_live_probe"]["enabled"] is True
    assert payload["telegram_live_probe"]["ok"] is True


def test_cli_validate_preflight_gateway_failure_returns_rc2(tmp_path: Path, capsys, monkeypatch) -> None:
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


def test_cli_validate_preflight_does_not_import_gateway_runtime(tmp_path: Path, capsys, monkeypatch) -> None:
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


def test_cli_memory_quality_generates_and_persists_report(tmp_path: Path, capsys) -> None:
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
    assert set(report["retrieval"].keys()) == {"attempts", "hits", "rewrites", "hit_rate"}
    assert set(report["turn_stability"].keys()) == {"successes", "errors", "success_rate", "error_rate"}
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
    assert set(reasoning_layers["distribution"].keys()) == {"fact", "hypothesis", "decision", "outcome"}
    for layer_payload in reasoning_layers["distribution"].values():
        assert isinstance(layer_payload, dict)
        assert set(layer_payload.keys()) == {"count", "ratio"}
    assert isinstance(reasoning_layers["confidence"], dict)
    assert set(reasoning_layers["confidence"].keys()) == {"average", "minimum", "maximum"}
    assert "drift" in report
    assert isinstance(report["recommendations"], list)
    assert payload["state"]["current"]["score"] == report["score"]
    assert Path(payload["quality_state_path"]).exists()
    assert "analysis" in payload
    assert isinstance(payload["analysis"]["reasoning_layers"], dict)
    assert isinstance(payload["analysis"]["confidence"], dict)
    assert "quality_highlights" in payload["analysis"]
    assert payload["analysis"]["quality_highlights"]["total_records"] == reasoning_layers["total_records"]


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

    sys.modules.pop("clawlite.gateway.server", None)
    rc_quality = main(["--config", str(config_path), "memory", "quality"])
    assert rc_quality == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    export_path = tmp_path / "portable.json"
    sys.modules.pop("clawlite.gateway.server", None)
    rc_export = main(["--config", str(config_path), "memory", "export", "--out", str(export_path)])
    assert rc_export == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_provider_login_status_logout_openai_codex(tmp_path: Path, capsys, monkeypatch) -> None:
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
    assert any("live probe" in row.lower() for row in payload["hints"])


def test_cli_provider_status_minimax_reports_anthropic_family(tmp_path: Path, capsys, monkeypatch) -> None:
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
                "providers": {"minimax": {"api_base": "https://api.minimax.io/anthropic"}},
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


def test_provider_live_probe_vllm_network_error_returns_runtime_hint(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "vllm/meta-llama/Llama-3.2-3B-Instruct"},
                "agents": {"defaults": {"model": "vllm/meta-llama/Llama-3.2-3B-Instruct"}},
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
    assert any("Inicie o servidor vLLM" in row for row in payload["hints"])


def test_provider_live_probe_ollama_success_detects_missing_model(tmp_path: Path, monkeypatch) -> None:
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
        def __init__(self, status_code: int, payload: dict[str, object], *, is_success: bool = True, text: str = "") -> None:
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


def test_provider_live_probe_openai_model_not_listed_returns_soft_warning(tmp_path: Path, monkeypatch) -> None:
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
    assert any("nao apareceu na lista remota" in row.lower() for row in payload["hints"])


def test_provider_live_probe_prefers_configured_vendor_transport_over_generic_model(tmp_path: Path, monkeypatch) -> None:
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
                "providers": {"minimax": {"api_base": "https://api.minimax.io/anthropic", "api_key": "mini-key"}},
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
    assert payload["transport"] == "openai_compatible"
    assert payload["family"] == "openai_compatible"
    assert payload["recommended_model"] == "openai/gpt-4o-mini"
    assert "openai/gpt-4o-mini" in payload["recommended_models"]
    assert "billing" in payload["onboarding_hint"].lower()

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
    assert payload["expected"] == "gemini/*"
    assert payload["transport"] == "openai_compatible"
    assert payload["recommended_model"] == "gemini/gemini-2.5-flash"
    assert "gemini/gemini-2.5-flash" in payload["recommended_models"]
    assert "google generative language" in payload["onboarding_hint"].lower()


def test_cli_provider_use_fallback_model_mismatch_returns_rc2(tmp_path: Path, capsys) -> None:
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


def test_cli_validate_provider_surfaces_guidance_fields(tmp_path: Path, capsys, monkeypatch) -> None:
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
                "providers": {"minimax": {"api_base": "https://api.minimax.io/anthropic"}},
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


def test_cli_provider_status_openai_codex_uses_auth_file_when_config_and_env_missing(tmp_path: Path, capsys, monkeypatch) -> None:
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

    rc_status = main(["--config", str(config_path), "provider", "status", "openai-codex"])
    assert rc_status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["configured"] is True
    assert payload["source"] == f"file:{auth_path}"
    assert payload["token_masked"]
    assert payload["account_id_masked"]


def test_cli_validate_provider_reports_local_runtime_failure(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/llama3.2", "litellm_base_url": "http://127.0.0.1:11434"},
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
    assert any(check.get("name") == "local_runtime" and check.get("status") == "error" for check in payload["checks"])


def test_cli_validate_provider_accepts_local_runtime_without_api_key(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/llama3.2", "litellm_base_url": "http://127.0.0.1:11434/v1"},
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
    assert any(check.get("name") == "api_key" and check.get("status") == "ok" for check in payload["checks"])
    assert any(check.get("name") == "local_runtime" and check.get("status") == "ok" for check in payload["checks"])


def test_cli_provider_set_auth_and_clear_auth_persist_config(tmp_path: Path, capsys) -> None:
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
    assert persisted["providers"]["openai"]["extra_headers"] == {"X-Trace": "abc", "X-Env": "prod"}

    rc_clear = main(["--config", str(config_path), "provider", "clear-auth", "openai", "--clear-api-base"])
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


def test_cli_provider_set_auth_supports_dynamic_provider_blocks(tmp_path: Path, capsys) -> None:
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


def test_cli_provider_set_auth_invalid_header_returns_rc2(tmp_path: Path, capsys) -> None:
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


def test_cli_provider_set_auth_unsupported_provider_returns_rc2(tmp_path: Path, capsys) -> None:
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


def test_cli_heartbeat_trigger_success_uses_default_url_and_token(tmp_path: Path, capsys, monkeypatch) -> None:
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


def test_cli_heartbeat_trigger_failure_returns_rc2(tmp_path: Path, capsys, monkeypatch) -> None:
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

    rc = main(["--config", str(config_path), "heartbeat", "trigger", "--gateway-url", "http://127.0.0.1:8787"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["status_code"] == 409
    assert payload["error"] == "heartbeat_disabled"


def test_cli_provider_set_auth_and_heartbeat_do_not_import_gateway_runtime(tmp_path: Path, capsys, monkeypatch) -> None:
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
            return {"ok": True, "decision": {"action": "send", "reason": "ok", "text": ""}}

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
    rc_set = main(["--config", str(config_path), "provider", "set-auth", "openai", "--api-key", "sk-test-1234"])
    assert rc_set == 0
    assert "clawlite.gateway.server" not in sys.modules
    capsys.readouterr()

    sys.modules.pop("clawlite.gateway.server", None)
    rc_hb = main(["--config", str(config_path), "heartbeat", "trigger"])
    assert rc_hb == 0
    assert "clawlite.gateway.server" not in sys.modules


def test_cli_validate_provider_codex_requires_token_and_passes_when_configured(tmp_path: Path, capsys, monkeypatch) -> None:
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
