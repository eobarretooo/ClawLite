from __future__ import annotations

import json
from pathlib import Path

from clawlite.config.loader import load_config


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.provider.model
    assert cfg.gateway.port == 8787
    assert cfg.channels.send_progress is False


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
                        "denyPatterns": ["rm\\s+-rf"],
                        "allowPathPatterns": ["^\\./"],
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
    assert cfg.tools.exec.deny_patterns == ["rm\\s+-rf"]
    assert cfg.tools.exec.allow_path_patterns == ["^\\./"]
    assert cfg.tools.exec.allow_patterns == []
    assert cfg.tools.exec.deny_path_patterns == []


def test_load_config_web_tool_policy(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "tools": {
                    "web": {
                        "proxy": "http://127.0.0.1:7890",
                        "timeout": 22,
                        "searchTimeout": 9,
                        "maxRedirects": 3,
                        "maxChars": 4000,
                        "blockPrivateAddresses": True,
                        "allowlist": ["example.com", "*.docs.example.com"],
                        "denylist": ["127.0.0.0/8"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.tools.web.proxy == "http://127.0.0.1:7890"
    assert cfg.tools.web.timeout == 22
    assert cfg.tools.web.search_timeout == 9
    assert cfg.tools.web.max_redirects == 3
    assert cfg.tools.web.max_chars == 4000
    assert cfg.tools.web.block_private_addresses is True
    assert cfg.tools.web.allowlist == ["example.com", "*.docs.example.com"]
    assert cfg.tools.web.denylist == ["127.0.0.0/8"]


def test_load_config_mcp_registry_and_policy(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "tools": {
                    "mcp": {
                        "defaultTimeoutS": 12,
                        "policy": {
                            "allowedSchemes": ["https"],
                            "allowedHosts": ["mcp.example.com", "*.internal.example.com"],
                            "deniedHosts": ["blocked.example.com"],
                        },
                        "servers": {
                            "search": {
                                "url": "https://mcp.example.com/rpc",
                                "timeoutS": 3,
                                "headers": {"Authorization": "Bearer token"},
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.tools.mcp.default_timeout_s == 12
    assert cfg.tools.mcp.policy.allowed_schemes == ["https"]
    assert cfg.tools.mcp.policy.allowed_hosts == ["mcp.example.com", "*.internal.example.com"]
    assert cfg.tools.mcp.policy.denied_hosts == ["blocked.example.com"]
    assert "search" in cfg.tools.mcp.servers
    assert cfg.tools.mcp.servers["search"].url == "https://mcp.example.com/rpc"
    assert cfg.tools.mcp.servers["search"].timeout_s == 3


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


def test_load_config_provider_reliability_fields_parse_snake_and_camel(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "provider": {
                    "model": "openai/gpt-4.1-mini",
                    "retryMaxAttempts": 4,
                    "retry_initial_backoff_s": 0.75,
                    "retryMaxBackoffS": 9.5,
                    "retry_jitter_s": 0.3,
                    "circuitFailureThreshold": 5,
                    "circuit_cooldown_s": 45.0,
                    "fallbackModel": "openai/gpt-4o-mini",
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.provider.retry_max_attempts == 4
    assert cfg.provider.retry_initial_backoff_s == 0.75
    assert cfg.provider.retry_max_backoff_s == 9.5
    assert cfg.provider.retry_jitter_s == 0.3
    assert cfg.provider.circuit_failure_threshold == 5
    assert cfg.provider.circuit_cooldown_s == 45.0
    assert cfg.provider.fallback_model == "openai/gpt-4o-mini"


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


def test_load_config_strict_mode_rejects_invalid_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gateway": {"port": 8787, "unknown": True}}), encoding="utf-8")

    try:
        load_config(path, strict=True)
        raise AssertionError("expected strict invalid-key failure")
    except RuntimeError as exc:
        assert "invalid config keys" in str(exc)


def test_load_config_migrates_legacy_gateway_token(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gateway": {"host": "127.0.0.1", "port": 8787, "token": "legacy"}}), encoding="utf-8")
    cfg = load_config(path, strict=True)
    assert cfg.gateway.host == "127.0.0.1"
    assert cfg.gateway.port == 8787
    assert cfg.gateway.auth.mode == "required"
    assert cfg.gateway.auth.token == "legacy"


def test_load_config_gateway_auth_and_diagnostics_env_overrides(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gateway": {"auth": {"mode": "off"}}}), encoding="utf-8")
    monkeypatch.setenv("CLAWLITE_GATEWAY_AUTH_MODE", "required")
    monkeypatch.setenv("CLAWLITE_GATEWAY_AUTH_TOKEN", "secret-token")
    monkeypatch.setenv("CLAWLITE_GATEWAY_DIAGNOSTICS_ENABLED", "false")
    monkeypatch.setenv("CLAWLITE_GATEWAY_DIAGNOSTICS_REQUIRE_AUTH", "false")
    cfg = load_config(path)
    assert cfg.gateway.auth.mode == "required"
    assert cfg.gateway.auth.token == "secret-token"
    assert cfg.gateway.diagnostics.enabled is False
    assert cfg.gateway.diagnostics.require_auth is False


def test_load_config_gateway_supervisor_parses_snake_and_camel(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "gateway": {
                    "supervisor": {
                        "enabled": True,
                        "intervalS": 15,
                        "cooldown_s": 45,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.gateway.supervisor.enabled is True
    assert cfg.gateway.supervisor.interval_s == 15
    assert cfg.gateway.supervisor.cooldown_s == 45


def test_load_config_tool_loop_detection_settings(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "tools": {
                    "loopDetection": {
                        "enabled": True,
                        "historySize": 12,
                        "repeatThreshold": 2,
                        "criticalThreshold": 4,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.tools.loop_detection.enabled is True
    assert cfg.tools.loop_detection.history_size == 12
    assert cfg.tools.loop_detection.repeat_threshold == 2
    assert cfg.tools.loop_detection.critical_threshold == 4


def test_load_config_preserves_telegram_roundtrip_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "channels": {
                    "telegram": {
                        "enabled": True,
                        "token": "tok",
                        "mode": "webhook",
                        "webhook_enabled": True,
                        "webhook_secret": "secret",
                        "webhook_path": "/api/webhooks/telegram-custom",
                        "poll_interval_s": 2.5,
                        "poll_timeout_s": 45,
                        "reconnect_initial_s": 3.0,
                        "reconnect_max_s": 35.0,
                        "send_timeout_s": 20.0,
                        "send_retry_attempts": 4,
                        "send_backoff_base_s": 0.4,
                        "send_backoff_max_s": 9.0,
                        "send_backoff_jitter": 0.15,
                        "send_circuit_failure_threshold": 2,
                        "send_circuit_cooldown_s": 70.0,
                        "typing_enabled": True,
                        "typing_interval_s": 1.75,
                        "typing_max_ttl_s": 150.0,
                        "typing_timeout_s": 3.5,
                        "typing_circuit_failure_threshold": 3,
                        "typing_circuit_cooldown_s": 65.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    telegram = cfg.to_dict()["channels"]["telegram"]
    assert telegram["token"] == "tok"
    assert telegram["mode"] == "webhook"
    assert telegram["webhook_enabled"] is True
    assert telegram["webhook_secret"] == "secret"
    assert telegram["webhook_path"] == "/api/webhooks/telegram-custom"
    assert telegram["poll_interval_s"] == 2.5
    assert telegram["poll_timeout_s"] == 45
    assert telegram["reconnect_initial_s"] == 3.0
    assert telegram["reconnect_max_s"] == 35.0
    assert telegram["send_timeout_s"] == 20.0
    assert telegram["send_retry_attempts"] == 4
    assert telegram["send_backoff_base_s"] == 0.4
    assert telegram["send_backoff_max_s"] == 9.0
    assert telegram["send_backoff_jitter"] == 0.15
    assert telegram["send_circuit_failure_threshold"] == 2
    assert telegram["send_circuit_cooldown_s"] == 70.0
    assert telegram["typing_enabled"] is True
    assert telegram["typing_interval_s"] == 1.75
    assert telegram["typing_max_ttl_s"] == 150.0
    assert telegram["typing_timeout_s"] == 3.5
    assert telegram["typing_circuit_failure_threshold"] == 3
    assert telegram["typing_circuit_cooldown_s"] == 65.0
