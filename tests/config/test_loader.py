from __future__ import annotations

import json
import os
from pathlib import Path

from clawlite.config.loader import load_config, save_config
from clawlite.config.schema import AppConfig


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.provider.model
    assert cfg.gateway.port == 8787
    assert cfg.channels.send_progress is False


def test_save_config_writes_valid_json_and_is_readable(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cfg = AppConfig()

    saved = save_config(cfg, path)

    assert saved == path
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["gateway"]["port"] == 8787

    loaded = load_config(path)
    assert loaded.gateway.port == 8787


def test_save_config_uses_atomic_replace_in_same_directory(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def _tracking_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        calls.append((src_path, dst_path))
        real_replace(src, dst)

    monkeypatch.setattr("clawlite.config.loader.os.replace", _tracking_replace)

    save_config(AppConfig(), path)

    assert len(calls) == 1
    src, dst = calls[0]
    assert dst == path
    assert src.parent == path.parent
    assert src != path
    assert path.exists()


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


def test_load_config_tools_safety_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.tools.safety.enabled is True
    assert cfg.tools.safety.risky_tools == ["exec", "run_skill", "web_fetch", "web_search", "mcp"]
    assert cfg.tools.safety.blocked_channels == []
    assert cfg.tools.safety.allowed_channels == []


def test_load_config_tools_safety_custom_and_camel_case(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "tools": {
                    "safety": {
                        "enabled": True,
                        "riskyTools": ["exec", "mcp"],
                        "blockedChannels": ["telegram", "slack"],
                        "allowed_channels": ["telegram"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.tools.safety.enabled is True
    assert cfg.tools.safety.risky_tools == ["exec", "mcp"]
    assert cfg.tools.safety.blocked_channels == ["telegram", "slack"]
    assert cfg.tools.safety.allowed_channels == ["telegram"]


def test_load_config_tools_safety_layered_parsing_and_normalization(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "tools": {
                    "safety": {
                        "profile": "  TeamA  ",
                        "profiles": {
                            " TeamA ": {
                                "riskyTools": [" Exec ", "", "MCP"],
                                "blocked_channels": [" Telegram ", ""],
                                "allowedChannels": [" cli ", ""],
                            }
                        },
                        "agents": {
                            " Agent-1 ": {
                                "risky_tools": ["run_skill"],
                                "blockedChannels": ["Slack"],
                            }
                        },
                        "byChannel": {
                            " TELEGRAM ": {
                                "allowed_channels": ["Telegram"],
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.tools.safety.profile == "teama"
    assert cfg.tools.safety.profiles["teama"].risky_tools == ["exec", "mcp"]
    assert cfg.tools.safety.profiles["teama"].blocked_channels == ["telegram"]
    assert cfg.tools.safety.profiles["teama"].allowed_channels == ["cli"]
    assert cfg.tools.safety.by_agent["agent-1"].risky_tools == ["run_skill"]
    assert cfg.tools.safety.by_agent["agent-1"].blocked_channels == ["slack"]
    assert cfg.tools.safety.by_agent["agent-1"].allowed_channels is None
    assert cfg.tools.safety.by_channel["telegram"].allowed_channels == ["telegram"]


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


def test_load_config_gateway_auth_legacy_env_alias_fallback(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gateway": {"auth": {"mode": "off"}}}), encoding="utf-8")
    monkeypatch.setenv("CLAWLITE_GATEWAY_AUTH_TOKEN", "")
    monkeypatch.setenv("CLAWLITE_GATEWAY_TOKEN", "legacy-token")
    cfg = load_config(path)
    assert cfg.gateway.auth.token == "legacy-token"


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


def test_load_config_agent_defaults_session_retention_messages_snake_case(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "session_retention_messages": 321,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.agents.defaults.session_retention_messages == 321


def test_load_config_agent_defaults_session_retention_messages_camel_case(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "sessionRetentionMessages": 654,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.agents.defaults.session_retention_messages == 654


def test_load_config_gateway_diagnostics_include_provider_telemetry_snake_and_camel(tmp_path: Path) -> None:
    path_snake = tmp_path / "snake.json"
    path_snake.write_text(
        json.dumps({"gateway": {"diagnostics": {"include_provider_telemetry": False}}}),
        encoding="utf-8",
    )
    cfg_snake = load_config(path_snake)
    assert cfg_snake.gateway.diagnostics.include_provider_telemetry is False

    path_camel = tmp_path / "camel.json"
    path_camel.write_text(
        json.dumps({"gateway": {"diagnostics": {"includeProviderTelemetry": False}}}),
        encoding="utf-8",
    )
    cfg_camel = load_config(path_camel)
    assert cfg_camel.gateway.diagnostics.include_provider_telemetry is False


def test_load_config_gateway_diagnostics_include_provider_telemetry_env_override(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"gateway": {"diagnostics": {"include_provider_telemetry": True}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_GATEWAY_DIAGNOSTICS_INCLUDE_PROVIDER_TELEMETRY", "false")
    cfg = load_config(path)
    assert cfg.gateway.diagnostics.include_provider_telemetry is False


def test_load_config_auth_providers_alias_parsing(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "auth": {
                    "providers": {
                        "openaiCodex": {
                            "token": "oauth-token",
                            "organization": "org-123",
                            "source": "config:test",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.auth.providers.openai_codex.access_token == "oauth-token"
    assert cfg.auth.providers.openai_codex.account_id == "org-123"
    assert cfg.auth.providers.openai_codex.source == "config:test"


def test_load_config_auth_env_overrides_codex(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"auth": {"providers": {"openai_codex": {}}}}), encoding="utf-8")
    monkeypatch.setenv("CLAWLITE_CODEX_ACCESS_TOKEN", "tok-a")
    monkeypatch.setenv("CLAWLITE_CODEX_ACCOUNT_ID", "org-a")

    cfg = load_config(path)
    assert cfg.auth.providers.openai_codex.access_token == "tok-a"
    assert cfg.auth.providers.openai_codex.account_id == "org-a"


def test_load_config_agent_defaults_semantic_flags_default_false(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.agents.defaults.semantic_memory is False
    assert cfg.agents.defaults.memory_auto_categorize is False
    assert cfg.agents.defaults.memory.backend == "sqlite"


def test_load_config_agent_defaults_semantic_flags_camel_case(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "semanticMemory": True,
                        "memoryAutoCategorize": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.agents.defaults.semantic_memory is True
    assert cfg.agents.defaults.memory_auto_categorize is True


def test_load_config_agent_memory_nested_snake_case_and_legacy_interop(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "semantic_memory": False,
                        "memory_auto_categorize": False,
                        "memory": {
                            "semantic_search": True,
                            "auto_categorize": True,
                            "proactive": True,
                            "proactive_retry_backoff_s": 45,
                            "proactive_max_retry_attempts": 5,
                            "emotional_tracking": True,
                            "backend": "pgvector",
                            "pgvector_url": "postgresql://memory-db",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.agents.defaults.memory.semantic_search is True
    assert cfg.agents.defaults.memory.auto_categorize is True
    assert cfg.agents.defaults.memory.proactive is True
    assert cfg.agents.defaults.memory.proactive_retry_backoff_s == 45.0
    assert cfg.agents.defaults.memory.proactive_max_retry_attempts == 5
    assert cfg.agents.defaults.memory.emotional_tracking is True
    assert cfg.agents.defaults.memory.backend == "pgvector"
    assert cfg.agents.defaults.memory.pgvector_url == "postgresql://memory-db"
    assert cfg.agents.defaults.semantic_memory is True
    assert cfg.agents.defaults.memory_auto_categorize is True


def test_load_config_agent_memory_nested_camel_case_and_legacy_fallback(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "semanticMemory": True,
                        "memoryAutoCategorize": True,
                        "memory": {
                            "proactive": True,
                            "proactiveRetryBackoffS": 15,
                            "proactiveMaxRetryAttempts": 4,
                            "emotionalTracking": True,
                            "backend": "jsonl",
                            "pgvectorUrl": "postgresql://ignored",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.agents.defaults.memory.semantic_search is True
    assert cfg.agents.defaults.memory.auto_categorize is True
    assert cfg.agents.defaults.memory.proactive is True
    assert cfg.agents.defaults.memory.proactive_retry_backoff_s == 15.0
    assert cfg.agents.defaults.memory.proactive_max_retry_attempts == 4
    assert cfg.agents.defaults.memory.emotional_tracking is True
    assert cfg.agents.defaults.memory.backend == "sqlite"
    assert cfg.agents.defaults.memory.pgvector_url == "postgresql://ignored"
    assert cfg.agents.defaults.semantic_memory is True
    assert cfg.agents.defaults.memory_auto_categorize is True
