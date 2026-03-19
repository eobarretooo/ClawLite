# READ clawlite/config/schema.py

## Identity

- Path: `clawlite/config/schema.py`
- Area: `config`
- Extension: `.py`
- Lines: 1863
- Size bytes: 69941
- SHA1: `a321582079f292ac5385c9d7f44cdc37f1365017`

## Summary

`clawlite.config.schema` is a Python module in the `config` area. It defines 38 class(es), led by `AgentDefaultsConfig`, `AgentMemoryConfig`, `AgentsConfig`, `AppConfig`. It exposes 125 function(s), including `_activity_type_range`, `_apply_profile_defaults`, `_base_url_default`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 38
- Functions: 125
- Async functions: 0
- Constants: 4
- Internal imports: 0
- Imported by: 26
- Matching tests: 1

## Classes

- `AgentDefaultsConfig`
- `AgentMemoryConfig`
- `AgentsConfig`
- `AppConfig`
- `AuthConfig`
- `AuthProviderTokenConfig`
- `AuthProvidersConfig`
- `Base`
- `BusConfig`
- `ChannelsConfig`
- `DiscordChannelConfig`
- `EmailChannelConfig`
- `ExecToolConfig`
- `GatewayAuthConfig`
- `GatewayAutonomyConfig`
- `GatewayConfig`
- `GatewayDiagnosticsConfig`
- `GatewayHeartbeatConfig`
- `GatewaySupervisorConfig`
- `IRCChannelConfig`
- `JobsConfig`
- `MCPServerConfig`
- `MCPToolConfig`
- `MCPTransportPolicyConfig`
- `ObservabilityConfig`
- `ProviderConfig`
- `ProviderOverrideConfig`
- `ProvidersConfig`
- `SchedulerConfig`
- `SlackChannelConfig`
- `TelegramChannelConfig`
- `ToolLoopDetectionConfig`
- `ToolSafetyLayerConfig`
- `ToolSafetyPolicyConfig`
- `ToolsConfig`
- `VikingConfig`
- `WebToolConfig`
- `WhatsAppChannelConfig`

## Functions

- `_activity_type_range`
- `_apply_profile_defaults`
- `_base_url_default`
- `_branch_prefix_default`
- `_brave_url_default`
- `_build_servers_with_default_timeout`
- `_clamp_confidence`
- `_ensure_critical_gt_repeat`
- `_extract_extra_channels`
- `_extract_extras`
- `_handle_aliases`
- `_handle_legacy_memory_fields`
- `_handle_timeout_aliases`
- `_header_name_default`
- `_host_default`
- `_journal_path_default`
- `_mailbox_default`
- `_min_action_cooldown`
- `_min_actions`
- `_min_approval_ttl`
- `_min_audit`
- `_min_backlog`
- `_min_backoff`
- `_min_backoff_base`
- `_min_backoff_max`
- `_min_body_chars`
- `_min_chars`
- `_min_circuit`
- `_min_circuit_cooldown`
- `_min_concurrency`
- `_min_connect_timeout`
- `_min_context_budget`
- `_min_cooldown`
- `_min_critical`
- `_min_dedupe`
- `_min_deg_backlog`
- `_min_deg_super`
- `_min_evo_cooldown`
- `_min_history`
- `_min_imap_port`
- `_min_intents`
- `_min_interval`
- `_min_iterations`
- `_min_jitter`
- `_min_max_tokens`
- `_min_non_negative_float`
- `_min_poll`
- `_min_port`
- `_min_positive_budget`
- `_min_rate_limit`
- `_min_reaction_cache`
- `_min_recovery_cooldown`
- `_min_recovery_interval`
- `_min_redirects`
- `_min_repeat`
- `_min_replay`
- `_min_replay_limit`
- `_min_retry`
- `_min_retry_attempts`
- `_min_retry_backoff`
- `_min_retry_max_backoff`
- `_min_search_timeout`
- `_min_smtp_port`
- `_min_thread_binding_timeout`
- `_min_timeout`
- `_min_tuning_actions`
- `_min_tuning_backoff`
- `_min_tuning_cooldown`
- `_min_tuning_interval`
- `_min_tuning_streak`
- `_min_tuning_timeout`
- `_min_typing_interval`
- `_min_window`
- `_model_default`
- `_normalize_auto_presence`
- `_normalize_backend`
- `_normalize_codex_key`
- `_normalize_fields`
- `_normalize_layer_map_keys`
- `_normalize_strings`
- `_normalize_thread_binding_state_path`
- `_normalize_tool_timeouts`
- `_parse_allow_bots`
- `_parse_allow_from`
- `_parse_channels`
- `_parse_dm_policy`
- `_parse_group_policy`
- `_parse_guilds`
- `_parse_hosts`
- `_parse_list`
- `_parse_names`
- `_parse_optional_list`
- `_parse_patterns`
- `_parse_reasons`
- `_parse_reply_to_mode`
- `_parse_schemes`
- `_parse_status`
- `_persist_path_default`
- `_port_default`
- `_provider_default`
- `_query_param_default`
- `_raw_with_alias`
- `_reasoning_effort`
- `_session_retention`
- `_session_retention_ttl`
- `_startup_timeout_default`
- `_state_default`
- `_string_default`
- `_strip`
- `_strip_fallback`
- `_strip_optional_text`
- `_strip_profile`
- `_strip_token`
- `_strip_url`
- `_sync_memory_flags`
- `_sync_provider_model`
- `_temperature_default`
- `_validate_mode`
- `_workspace_default`
- `enabled_names`
- `ensure`
- `from_dict`
- `get`
- `normalize_name`
- `to_dict`

## Constants

- `BUILTIN_KEYS`
- `_DEFAULT_MODEL`
- `_DEFAULT_STATE`
- `_DEFAULT_WORKSPACE`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/config/schema.py`.
- Cross-reference `CONNECTIONS_schema.md` to see how this file fits into the wider system.
