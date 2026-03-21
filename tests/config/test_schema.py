"""Pydantic v2 schema tests for ClawLite config."""
from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from clawlite.config.schema import (
    AppConfig,
    GatewayAutonomyConfig,
    ProvidersConfig,
    ProviderOverrideConfig,
)
from clawlite.config.loader import load_config, save_config


# ---------------------------------------------------------------------------
# 1. Empty config loads with correct defaults
# ---------------------------------------------------------------------------

def test_empty_config_defaults():
    cfg = AppConfig()
    assert cfg.gateway.port == 8787
    assert cfg.gateway.host == "127.0.0.1"
    assert cfg.gateway.websocket.coalesce_enabled is True
    assert cfg.gateway.websocket.coalesce_min_chars == 24
    assert cfg.gateway.websocket.coalesce_max_chars == 120
    assert cfg.gateway.websocket.coalesce_profile == "compact"
    assert cfg.agents.defaults.model == "gemini/gemini-2.5-flash"
    assert cfg.agents.defaults.max_tokens == 8192
    assert cfg.agents.defaults.temperature == 0.1
    assert cfg.agents.defaults.max_tool_iterations == 40
    assert cfg.channels.telegram.enabled is False
    assert cfg.tools.exec.timeout == 60
    assert cfg.tools.web.timeout == 15.0
    assert cfg.tools.web.max_chars == 12000
    assert cfg.tools.web.block_private_addresses is True
    assert cfg.gateway.auth.mode == "off"
    assert cfg.gateway.auth.allow_loopback_without_auth is True
    assert cfg.gateway.heartbeat.interval_s == 1800
    assert cfg.gateway.supervisor.enabled is True
    assert cfg.gateway.autonomy.enabled is False
    assert cfg.gateway.autonomy.action_policy == "balanced"
    assert cfg.gateway.autonomy.environment_profile == "dev"


# ---------------------------------------------------------------------------
# 2. snake_case input works
# ---------------------------------------------------------------------------

def test_snake_case_input():
    cfg = AppConfig.model_validate({
        "workspace_path": "/tmp/ws",
        "agents": {"defaults": {"model": "openai/gpt-4o", "max_tokens": 4096}},
        "gateway": {"port": 9000, "auth": {"mode": "required", "token": "abc"}},
        "tools": {"web": {"max_chars": 5000, "search_timeout": 8.0}},
    })
    assert cfg.workspace_path == "/tmp/ws"
    assert cfg.agents.defaults.model == "openai/gpt-4o"
    assert cfg.agents.defaults.max_tokens == 4096
    assert cfg.gateway.port == 9000
    assert cfg.gateway.auth.mode == "required"
    assert cfg.gateway.auth.token == "abc"
    assert cfg.tools.web.max_chars == 5000
    assert cfg.tools.web.search_timeout == 8.0


def test_gateway_port_preserves_explicit_zero():
    cfg = AppConfig.model_validate({
        "gateway": {"port": 0},
    })

    assert cfg.gateway.port == 0


# ---------------------------------------------------------------------------
# 3. camelCase input works
# ---------------------------------------------------------------------------

def test_camel_case_input():
    cfg = AppConfig.model_validate({
        "agents": {"defaults": {"maxTokens": 2048, "maxToolIterations": 20}},
        "gateway": {
            "heartbeat": {"intervalS": 600},
            "auth": {"allowLoopbackWithoutAuth": False},
            "websocket": {
                "coalesceEnabled": False,
                "coalesceMinChars": 40,
                "coalesceMaxChars": 16,
                "coalesceProfile": "paragraph",
            },
        },
        "tools": {
            "web": {"searchTimeout": 5.0, "maxChars": 3000, "blockPrivateAddresses": False},
            "exec": {"denyPatterns": ["rm -rf"]},
        },
    })
    assert cfg.agents.defaults.max_tokens == 2048
    assert cfg.agents.defaults.max_tool_iterations == 20
    assert cfg.gateway.heartbeat.interval_s == 600
    assert cfg.gateway.auth.allow_loopback_without_auth is False
    assert cfg.gateway.websocket.coalesce_enabled is False
    assert cfg.gateway.websocket.coalesce_min_chars == 40
    assert cfg.gateway.websocket.coalesce_max_chars == 40
    assert cfg.gateway.websocket.coalesce_profile == "paragraph"
    assert cfg.tools.web.search_timeout == 5.0
    assert cfg.tools.web.max_chars == 3000
    assert cfg.tools.web.block_private_addresses is False
    assert cfg.tools.exec.deny_patterns == ["rm -rf"]


# ---------------------------------------------------------------------------
# 4. Unknown keys are silently ignored
# ---------------------------------------------------------------------------

def test_unknown_keys_ignored():
    cfg = AppConfig.model_validate({
        "totally_unknown_key": "value",
        "gateway": {"unknown_gateway_field": 123, "port": 7777},
    })
    assert cfg.gateway.port == 7777


# ---------------------------------------------------------------------------
# 5. Legacy scheduler.heartbeat_interval_seconds migrates to gateway.heartbeat.interval_s
# ---------------------------------------------------------------------------

def test_legacy_scheduler_migration():
    from clawlite.config.loader import _migrate_config
    raw = {"scheduler": {"heartbeat_interval_seconds": 600}}
    migrated = _migrate_config(raw)
    assert migrated["gateway"]["heartbeat"]["interval_s"] == 600


# ---------------------------------------------------------------------------
# 6. Legacy gateway.token migrates to gateway.auth.token
# ---------------------------------------------------------------------------

def test_legacy_gateway_token_migration():
    from clawlite.config.loader import _migrate_config
    raw = {"gateway": {"token": "mysecret"}}
    migrated = _migrate_config(raw)
    assert migrated["gateway"]["auth"]["token"] == "mysecret"
    assert migrated["gateway"]["auth"]["mode"] == "required"
    assert "token" not in migrated["gateway"]


# ---------------------------------------------------------------------------
# 7. provider.model syncs to agents.defaults.model
# ---------------------------------------------------------------------------

def test_provider_model_syncs_to_agents():
    cfg = AppConfig.model_validate({
        "provider": {"model": "anthropic/claude-3-opus"},
    })
    assert cfg.agents.defaults.model == "anthropic/claude-3-opus"
    assert cfg.provider.model == "anthropic/claude-3-opus"


def test_agents_model_syncs_to_provider():
    cfg = AppConfig.model_validate({
        "agents": {"defaults": {"model": "openai/gpt-4o"}},
    })
    assert cfg.provider.model == "openai/gpt-4o"
    assert cfg.agents.defaults.model == "openai/gpt-4o"


# ---------------------------------------------------------------------------
# 8. Autonomy prod profile sets conservative defaults
# ---------------------------------------------------------------------------

def test_autonomy_prod_profile_conservative_defaults():
    cfg = AppConfig.model_validate({
        "gateway": {"autonomy": {"environment_profile": "prod"}},
    })
    aut = cfg.gateway.autonomy
    assert aut.environment_profile == "prod"
    assert aut.action_policy == "conservative"
    assert aut.action_cooldown_s == 300.0
    assert aut.action_rate_limit_per_hour == 8
    assert aut.min_action_confidence == 0.75
    assert aut.degraded_backlog_threshold == 150
    assert aut.degraded_supervisor_error_threshold == 1


def test_autonomy_dev_profile_balanced_defaults():
    cfg = AppConfig.model_validate({
        "gateway": {"autonomy": {"environment_profile": "dev"}},
    })
    aut = cfg.gateway.autonomy
    assert aut.action_policy == "balanced"
    assert aut.action_cooldown_s == 120.0
    assert aut.action_rate_limit_per_hour == 20
    assert aut.min_action_confidence == 0.55


def test_bus_config_accepts_redis_backend_and_normalizes_aliases():
    cfg = AppConfig.model_validate(
        {
            "bus": {
                "backend": "memory",
                "redis_url": " redis://localhost:6379/1 ",
                "redis_prefix": " clawlite:test ",
            }
        }
    )
    assert cfg.bus.backend == "inprocess"
    assert cfg.bus.redis_url == "redis://localhost:6379/1"
    assert cfg.bus.redis_prefix == "clawlite:test"

    redis_cfg = AppConfig.model_validate({"bus": {"backend": "redis"}})
    assert redis_cfg.bus.backend == "redis"


def test_observability_config_accepts_endpoint_and_defaults() -> None:
    cfg = AppConfig.model_validate(
        {
            "observability": {
                "enabled": True,
                "otlp_endpoint": " http://otel:4317 ",
                "service_name": " clawlite-dev ",
                "service_namespace": " local ",
            }
        }
    )
    assert cfg.observability.enabled is True
    assert cfg.observability.otlp_endpoint == "http://otel:4317"
    assert cfg.observability.service_name == "clawlite-dev"
    assert cfg.observability.service_namespace == "local"


def test_channels_config_supports_slack_whatsapp_and_irc_runtime_fields() -> None:
    cfg = AppConfig.model_validate(
        {
            "channels": {
                "slack": {
                    "enabled": True,
                    "botToken": "xoxb-1",
                    "appToken": "xapp-1",
                    "allowFrom": ["U123"],
                    "sendRetryAttempts": 4,
                    "socketModeEnabled": True,
                    "workingIndicatorEmoji": "hourglass",
                },
                "whatsapp": {
                    "enabled": True,
                    "bridgeUrl": "http://localhost:3001",
                    "sendRetryAttempts": 4,
                    "typingIntervalS": 3.5,
                },
                "irc": {
                    "enabled": True,
                    "channelsToJoin": ["#clawlite"],
                    "useSsl": False,
                },
            }
        }
    )

    assert cfg.channels.slack.allow_from == ["U123"]
    assert cfg.channels.slack.send_retry_attempts == 4
    assert cfg.channels.slack.working_indicator_emoji == "hourglass"
    assert cfg.channels.whatsapp.send_retry_attempts == 4
    assert cfg.channels.whatsapp.typing_interval_s == 3.5
    assert cfg.channels.irc.channels_to_join == ["#clawlite"]
    assert cfg.channels.irc.use_ssl is False
    assert "irc" in cfg.channels.enabled_names()


def test_channels_config_supports_discord_policy_and_guild_allowlists() -> None:
    cfg = AppConfig.model_validate(
        {
            "channels": {
                "discord": {
                    "enabled": True,
                    "token": "discord-token",
                    "allowFrom": ["123", "@owner"],
                    "dmPolicy": "allowlist",
                    "groupPolicy": "allowlist",
                    "allowBots": "mentions",
                    "requireMention": True,
                    "ignoreOtherMentions": True,
                    "replyToMode": "first",
                    "slashIsolatedSessions": False,
                    "status": "idle",
                    "activity": "Focus time",
                    "activityType": 4,
                    "autoPresence": {
                        "enabled": True,
                        "intervalS": 45,
                        "minUpdateIntervalS": 20,
                        "healthyText": "online",
                        "degradedText": "warming up",
                        "exhaustedText": "offline",
                    },
                    "threadBindingsEnabled": True,
                    "threadBindingStatePath": " /tmp/discord-bindings.json ",
                    "threadBindingIdleTimeoutS": 900,
                    "threadBindingMaxAgeS": 7200,
                    "transcribeVoice": False,
                    "transcribeAudio": True,
                    "transcriptionApiKey": "discord-groq",
                    "transcriptionBaseUrl": "https://api.groq.com/openai/v1",
                    "transcriptionModel": "whisper-large-v3-turbo",
                    "transcriptionLanguage": "en",
                    "transcriptionTimeoutS": 45,
                    "guilds": {
                        "guild-1": {
                            "requireMention": False,
                            "users": ["123"],
                            "channels": {
                                "chan-1": {
                                    "allow": True,
                                    "roles": ["role-1"],
                                }
                            },
                        }
                    },
                }
            }
        }
    )

    assert cfg.channels.discord.gateway_intents == 46593
    assert cfg.channels.discord.allow_from == ["123", "@owner"]
    assert cfg.channels.discord.dm_policy == "allowlist"
    assert cfg.channels.discord.group_policy == "allowlist"
    assert cfg.channels.discord.allow_bots == "mentions"
    assert cfg.channels.discord.require_mention is True
    assert cfg.channels.discord.ignore_other_mentions is True
    assert cfg.channels.discord.reply_to_mode == "first"
    assert cfg.channels.discord.slash_isolated_sessions is False
    assert cfg.channels.discord.status == "idle"
    assert cfg.channels.discord.activity == "Focus time"
    assert cfg.channels.discord.activity_type == 4
    assert cfg.channels.discord.auto_presence["enabled"] is True
    assert cfg.channels.discord.auto_presence["intervalS"] == 45
    assert cfg.channels.discord.thread_bindings_enabled is True
    assert cfg.channels.discord.thread_binding_state_path == "/tmp/discord-bindings.json"
    assert cfg.channels.discord.thread_binding_idle_timeout_s == 900.0
    assert cfg.channels.discord.thread_binding_max_age_s == 7200.0
    assert cfg.channels.discord.transcribe_voice is False
    assert cfg.channels.discord.transcribe_audio is True
    assert cfg.channels.discord.transcription_api_key == "discord-groq"
    assert cfg.channels.discord.transcription_base_url == "https://api.groq.com/openai/v1"
    assert cfg.channels.discord.transcription_model == "whisper-large-v3-turbo"
    assert cfg.channels.discord.transcription_language == "en"
    assert cfg.channels.discord.transcription_timeout_s == 45.0
    assert cfg.channels.discord.guilds["guild-1"]["channels"]["chan-1"]["roles"] == ["role-1"]


# ---------------------------------------------------------------------------
# 9. ProvidersConfig.get() returns custom provider
# ---------------------------------------------------------------------------

def test_providers_get_custom():
    cfg = AppConfig.model_validate({
        "providers": {
            "gemini": {"api_key": "gkey"},
            "mycompany": {"api_key": "custom_key", "api_base": "https://custom.example.com"},
        }
    })
    assert cfg.providers.gemini.api_key == "gkey"
    custom = cfg.providers.get("mycompany")
    assert custom is not None
    assert custom.api_key == "custom_key"
    assert custom.api_base == "https://custom.example.com"


def test_providers_get_builtin():
    cfg = AppConfig.model_validate({
        "providers": {"openai": {"api_key": "sk-abc"}}
    })
    p = cfg.providers.get("openai")
    assert p is not None
    assert p.api_key == "sk-abc"


def test_providers_to_dict_contains_all_builtins():
    cfg = AppConfig()
    d = cfg.providers.to_dict()
    for key in ProvidersConfig.BUILTIN_KEYS:
        assert key in d
    assert "api_key" in d["openai"]


# ---------------------------------------------------------------------------
# 10. save_config + load_config round-trip
# ---------------------------------------------------------------------------

def test_save_load_round_trip(tmp_path):
    cfg = AppConfig.model_validate({
        "workspace_path": "/tmp/roundtrip",
        "agents": {"defaults": {"model": "openai/gpt-4o", "max_tokens": 1024}},
        "gateway": {"port": 9999, "auth": {"mode": "required", "token": "tok"}},
        "channels": {"telegram": {"enabled": True, "token": "tgtoken"}},
        "providers": {"gemini": {"api_key": "gk"}},
    })
    p = tmp_path / "config.json"
    save_config(cfg, p)
    cfg2 = load_config(p)
    assert cfg2.workspace_path == "/tmp/roundtrip"
    assert cfg2.agents.defaults.model == "openai/gpt-4o"
    assert cfg2.agents.defaults.max_tokens == 1024
    assert cfg2.gateway.port == 9999
    assert cfg2.gateway.auth.mode == "required"
    assert cfg2.gateway.auth.token == "tok"
    assert cfg2.channels.telegram.enabled is True
    assert cfg2.channels.telegram.token == "tgtoken"
    assert cfg2.providers.gemini.api_key == "gk"


# ---------------------------------------------------------------------------
# 11. Required field attribute access (gateway server uses these)
# ---------------------------------------------------------------------------

def test_gateway_server_attributes():
    cfg = AppConfig.model_validate({
        "tools": {
            "exec": {
                "deny_patterns": ["rm"],
                "allow_patterns": [],
                "deny_path_patterns": ["/etc"],
                "allow_path_patterns": [],
            },
            "web": {
                "proxy": "http://proxy:3128",
                "timeout": 20.0,
                "search_timeout": 12.0,
                "max_redirects": 3,
                "max_chars": 8000,
                "allowlist": ["example.com"],
                "denylist": ["evil.com"],
                "block_private_addresses": False,
            }
        }
    })
    assert cfg.tools.exec.deny_patterns == ["rm"]
    assert cfg.tools.exec.deny_path_patterns == ["/etc"]
    assert cfg.tools.web.proxy == "http://proxy:3128"
    assert cfg.tools.web.timeout == 20.0
    assert cfg.tools.web.search_timeout == 12.0
    assert cfg.tools.web.max_redirects == 3
    assert cfg.tools.web.max_chars == 8000
    assert cfg.tools.web.allowlist == ["example.com"]
    assert cfg.tools.web.denylist == ["evil.com"]
    assert cfg.tools.web.block_private_addresses is False
    assert hasattr(cfg.tools.web, "brave_api_key")
    assert hasattr(cfg.tools.web, "brave_base_url")
    assert hasattr(cfg.tools.web, "searxng_base_url")


# ---------------------------------------------------------------------------
# 12. Onboarding-style direct mutation
# ---------------------------------------------------------------------------

def test_direct_mutation():
    cfg = AppConfig()
    cfg.gateway.auth.token = "newtoken"
    cfg.gateway.auth.mode = "required"
    cfg.channels.telegram.enabled = True
    assert cfg.gateway.auth.token == "newtoken"
    assert cfg.channels.telegram.enabled is True


# ---------------------------------------------------------------------------
# 13. ToolLoopDetectionConfig critical > repeat enforced
# ---------------------------------------------------------------------------

def test_loop_detection_critical_gt_repeat():
    from clawlite.config.schema import ToolLoopDetectionConfig
    cfg = ToolLoopDetectionConfig.model_validate({"repeat_threshold": 5, "critical_threshold": 5})
    assert cfg.critical_threshold == 6  # repeat + 1


# ---------------------------------------------------------------------------
# 14. MCP servers parsed correctly
# ---------------------------------------------------------------------------

def test_mcp_servers():
    cfg = AppConfig.model_validate({
        "tools": {
            "mcp": {
                "default_timeout_s": 30.0,
                "servers": {
                    "my_server": {"url": "https://mcp.example.com", "timeout_s": 60.0}
                }
            }
        }
    })
    assert cfg.tools.mcp.default_timeout_s == 30.0
    assert "my_server" in cfg.tools.mcp.servers
    assert cfg.tools.mcp.servers["my_server"].url == "https://mcp.example.com"
    assert cfg.tools.mcp.servers["my_server"].timeout_s == 60.0


def test_tools_config_normalizes_per_tool_timeouts() -> None:
    cfg = AppConfig.model_validate(
        {
            "tools": {
                "default_timeout_s": 20,
                "timeouts": {
                    "exec": 120,
                    "browser": "30",
                    "bad": "nope",
                    "": 5,
                },
            }
        }
    )

    assert cfg.tools.timeouts == {"exec": 120.0, "browser": 30.0}


# ---------------------------------------------------------------------------
# 15. AgentMemoryConfig fields
# ---------------------------------------------------------------------------

def test_agent_memory_config():
    cfg = AppConfig.model_validate({
        "agents": {
            "defaults": {
                "memory": {
                    "semantic_search": True,
                    "auto_categorize": True,
                    "proactive": False,
                    "backend": "sqlite",
                }
            }
        }
    })
    mem = cfg.agents.defaults.memory
    assert mem.semantic_search is True
    assert mem.auto_categorize is True
    assert mem.backend == "sqlite"
    # Legacy flags synced
    assert cfg.agents.defaults.semantic_memory is True
    assert cfg.agents.defaults.memory_auto_categorize is True


def test_agent_memory_config_accepts_sqlite_vec_alias() -> None:
    cfg = AppConfig.model_validate(
        {
            "agents": {
                "defaults": {
                    "memory": {
                        "backend": "sqlite_vec",
                    }
                }
            }
        }
    )

    assert cfg.agents.defaults.memory.backend == "sqlite-vec"
