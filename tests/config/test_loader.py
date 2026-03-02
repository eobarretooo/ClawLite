from __future__ import annotations

import json
from pathlib import Path

from clawlite.config.loader import load_config


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.provider.model
    assert cfg.gateway.port == 8787


def test_load_config_file_and_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "provider": {"model": "openai/gpt-4.1-mini"},
                "gateway": {"port": 9999},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_GATEWAY_PORT", "7777")
    cfg = load_config(path)
    assert cfg.provider.model == "openai/gpt-4.1-mini"
    assert cfg.agents.defaults.model == "openai/gpt-4.1-mini"
    assert cfg.gateway.port == 7777


def test_load_config_tools_flags(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "tools": {
                    "restrictToWorkspace": True,
                    "exec": {
                        "pathAppend": "/usr/sbin",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.tools.restrict_to_workspace is True
    assert cfg.tools.exec.path_append == "/usr/sbin"
    assert cfg.tools.exec.timeout == 60


def test_load_config_provider_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "provider": {
                    "model": "openrouter/openai/gpt-4o-mini",
                    "litellm_api_key": "legacy-key",
                },
                "providers": {
                    "openrouter": {"api_key": "sk-or-123", "api_base": "https://openrouter.ai/api/v1"},
                    "custom": {
                        "api_key": "custom-key",
                        "api_base": "http://127.0.0.1:5000/v1",
                        "extra_headers": {"X-Test": "1"},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.provider.litellm_api_key == "legacy-key"
    assert cfg.providers.openrouter.api_key == "sk-or-123"
    assert cfg.providers.openrouter.api_base == "https://openrouter.ai/api/v1"
    assert cfg.providers.custom.api_key == "custom-key"
    assert cfg.providers.custom.extra_headers == {"X-Test": "1"}


def test_load_config_channels_and_gateway_heartbeat_backward_compat(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "scheduler": {"heartbeat_interval_seconds": 2222},
                "channels": {
                    "send_progress": False,
                    "send_tool_hints": True,
                    "telegram": {
                        "enabled": True,
                        "token": "x:token",
                        "allowFrom": ["123"],
                        "poll_timeout_s": 15,
                    },
                    "qq": {"enabled": True, "app_id": "app"},
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.gateway.heartbeat.enabled is True
    assert cfg.gateway.heartbeat.interval_s == 2222
    assert cfg.channels.send_progress is False
    assert cfg.channels.send_tool_hints is True
    assert cfg.channels.telegram.enabled is True
    assert cfg.channels.telegram.allow_from == ["123"]
    assert cfg.channels.telegram.poll_timeout_s == 15
    assert "qq" in cfg.channels.extra
