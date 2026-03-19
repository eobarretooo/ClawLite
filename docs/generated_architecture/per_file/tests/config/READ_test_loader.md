# READ tests/config/test_loader.py

## Identity

- Path: `tests/config/test_loader.py`
- Area: `tests`
- Extension: `.py`
- Lines: 1054
- Size bytes: 38332
- SHA1: `117fc9896cec527a4f685d9bb1d6c49f8fabd6b4`

## Summary

`tests.config.test_loader` is a Python module in the `tests` area. It exposes 46 function(s), including `_tracking_replace`, `test_app_config_gateway_preserves_explicit_zero_values_and_clamps_minimums`, `test_load_config_agent_defaults_semantic_flags_camel_case`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 46
- Async functions: 0
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Functions

- `_tracking_replace`
- `test_app_config_gateway_preserves_explicit_zero_values_and_clamps_minimums`
- `test_load_config_agent_defaults_semantic_flags_camel_case`
- `test_load_config_agent_defaults_semantic_flags_default_false`
- `test_load_config_agent_defaults_session_retention_messages_camel_case`
- `test_load_config_agent_defaults_session_retention_messages_snake_case`
- `test_load_config_agent_defaults_session_retention_ttl_camel_case`
- `test_load_config_agent_defaults_session_retention_ttl_snake_case`
- `test_load_config_agent_memory_accepts_sqlite_vec_backend_variants`
- `test_load_config_agent_memory_nested_camel_case_and_legacy_fallback`
- `test_load_config_agent_memory_nested_snake_case_and_legacy_interop`
- `test_load_config_auth_env_overrides_codex`
- `test_load_config_auth_providers_alias_parsing`
- `test_load_config_bus_backend_and_redis_fields`
- `test_load_config_bus_env_overrides`
- `test_load_config_channel_runtime_fields_for_slack_whatsapp_and_irc`
- `test_load_config_channels_and_gateway_heartbeat_backward_compat`
- `test_load_config_defaults_when_missing`
- `test_load_config_file_and_env_override`
- `test_load_config_gateway_auth_and_diagnostics_env_overrides`
- `test_load_config_gateway_auth_legacy_env_alias_fallback`
- `test_load_config_gateway_diagnostics_include_provider_telemetry_env_override`
- `test_load_config_gateway_diagnostics_include_provider_telemetry_snake_and_camel`
- `test_load_config_gateway_startup_timeouts_and_self_evolution_controls`
- `test_load_config_mcp_registry_and_policy`
- `test_load_config_migrates_legacy_gateway_token`
- `test_load_config_observability_fields`
- `test_load_config_preserves_dynamic_provider_blocks`
- `test_load_config_profile_defaults_to_env_variable`
- `test_load_config_profile_overlay_merges_over_base_file`
- `test_load_config_provider_blocks`
- `test_load_config_rejects_invalid_profile_name`
- `test_load_config_scheduler_cron_concurrency`
- `test_load_config_strict_mode_allows_dynamic_provider_blocks`
- `test_load_config_strict_mode_rejects_invalid_keys`
- `test_load_config_tool_loop_detection_settings`
- `test_load_config_tools_flags`
- `test_load_config_tools_safety_custom_and_camel_case`
- `test_load_config_tools_safety_defaults`
- `test_load_config_tools_safety_layered_parsing_and_normalization`
- `test_load_config_web_tool_policy`
- `test_load_config_yaml_file`
- `test_save_config_uses_atomic_replace_in_same_directory`
- `test_save_config_writes_valid_json_and_is_readable`
- `test_save_raw_config_payload_preserves_skills_section_in_yaml`
- `test_save_raw_config_payload_uses_profile_target_path`

## Notable String Markers

- `test_app_config_gateway_preserves_explicit_zero_values_and_clamps_minimums`
- `test_load_config_agent_defaults_semantic_flags_camel_case`
- `test_load_config_agent_defaults_semantic_flags_default_false`
- `test_load_config_agent_defaults_session_retention_messages_camel_case`
- `test_load_config_agent_defaults_session_retention_messages_snake_case`
- `test_load_config_agent_defaults_session_retention_ttl_camel_case`
- `test_load_config_agent_defaults_session_retention_ttl_snake_case`
- `test_load_config_agent_memory_accepts_sqlite_vec_backend_variants`
- `test_load_config_agent_memory_nested_camel_case_and_legacy_fallback`
- `test_load_config_agent_memory_nested_snake_case_and_legacy_interop`
- `test_load_config_auth_env_overrides_codex`
- `test_load_config_auth_providers_alias_parsing`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/config/test_loader.py`.
- Cross-reference `CONNECTIONS_test_loader.md` to see how this file fits into the wider system.
