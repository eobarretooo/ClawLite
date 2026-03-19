# READ tests/cli/test_commands.py

## Identity

- Path: `tests/cli/test_commands.py`
- Area: `tests`
- Extension: `.py`
- Lines: 5021
- Size bytes: 165804
- SHA1: `beebe8ec12f9f655af9d0ca249a77d71ce28069a`

## Summary

`tests.cli.test_commands` is a Python module in the `tests` area. It defines 6 class(es), led by `_Client`, `_Engine`, `_FakeClient`, `_FakeResponse`. It exposes 136 function(s), including `__enter__`, `__exit__`, `__init__`, `run`. It depends on 14 import statement target(s).

## Structural Data

- Classes: 6
- Functions: 135
- Async functions: 1
- Constants: 0
- Internal imports: 6
- Imported by: 0
- Matching tests: 0

## Classes

- `_Client`
- `_Engine`
- `_FakeClient`
- `_FakeResponse`
- `_Response`
- `_StubWhatsAppChannel`

## Functions

- `__enter__`
- `__exit__`
- `__init__`
- `_boom`
- `_fake_fetch`
- `_fake_flow`
- `_fake_open`
- `_fake_review`
- `_fake_revoke`
- `_fake_run`
- `_fake_run_gateway`
- `_fake_trigger`
- `_fake_which`
- `_fake_wizard`
- `get`
- `json`
- `post`
- `test_cli_autonomy_wake_uses_gateway_control`
- `test_cli_configure_flow_compatibility_routes_to_onboarding_wizard`
- `test_cli_configure_routes_flow_override_to_wizard`
- `test_cli_dashboard_no_open_returns_tokenized_handoff_and_bootstrap_state`
- `test_cli_dashboard_opens_browser_when_allowed`
- `test_cli_discord_refresh_uses_gateway_control`
- `test_cli_discord_status_uses_gateway_dashboard_state`
- `test_cli_gateway_alias_parses`
- `test_cli_hatch_completes_pending_bootstrap`
- `test_cli_hatch_skips_when_bootstrap_not_pending`
- `test_cli_heartbeat_trigger_failure_returns_rc2`
- `test_cli_heartbeat_trigger_success_uses_default_url_and_token`
- `test_cli_help_version_status_do_not_import_gateway`
- `test_cli_main_adds_yaml_install_hint`
- `test_cli_main_reports_runtime_errors_on_stderr`
- `test_cli_memory_branch_create_returns_branch_metadata`
- `test_cli_memory_branches_empty_returns_main_branch`
- `test_cli_memory_branching_commands_do_not_import_gateway_runtime`
- `test_cli_memory_branching_commands_return_expected_shapes`
- `test_cli_memory_checkout_switches_current_branch`
- `test_cli_memory_doctor_does_not_import_gateway_runtime`
- `test_cli_memory_doctor_outputs_expected_keys`
- `test_cli_memory_doctor_repair_handles_corrupt_history_line`
- `test_cli_memory_eval_does_not_import_gateway_runtime`
- `test_cli_memory_eval_outputs_json_summary`
- `test_cli_memory_export_and_import_roundtrip`
- `test_cli_memory_merge_returns_import_metadata`
- `test_cli_memory_privacy_returns_config_keys`
- `test_cli_memory_profile_returns_schema_fields`
- `test_cli_memory_quality_generates_and_persists_report`
- `test_cli_memory_share_optin_enable_returns_enabled_true`
- `test_cli_memory_snapshot_and_rollback_restores_previous_state`
- `test_cli_memory_suggest_returns_list_without_crashing_on_empty`
- `test_cli_memory_version_lists_snapshot_ids_desc`
- `test_cli_memory_without_subcommand_returns_overview`
- `test_cli_new_memory_commands_do_not_import_gateway_runtime`
- `test_cli_non_runtime_validate_and_diagnostics_do_not_import_gateway`
- `test_cli_onboard_creates_missing_default_config_and_prints_notice`
- `test_cli_onboard_generates_workspace_files`
- `test_cli_onboard_wizard_mode_routes_to_runner`
- `test_cli_pairing_list_and_approve`
- `test_cli_provider_commands_do_not_import_gateway_runtime`
- `test_cli_provider_login_openai_codex_keep_model_preserves_active_model`
- `test_cli_provider_login_openai_codex_rejects_conflicting_model_flags`
- `test_cli_provider_login_status_logout_gemini_oauth`
- `test_cli_provider_login_status_logout_openai_codex`
- `test_cli_provider_login_unsupported_returns_rc2`
- `test_cli_provider_logout_unsupported_returns_rc2`
- `test_cli_provider_recover_uses_gateway_control`
- `test_cli_provider_set_auth_and_clear_auth_persist_config`
- `test_cli_provider_set_auth_and_heartbeat_do_not_import_gateway_runtime`
- `test_cli_provider_set_auth_invalid_header_returns_rc2`
- `test_cli_provider_set_auth_supports_dynamic_provider_blocks`
- `test_cli_provider_set_auth_unsupported_provider_returns_rc2`
- `test_cli_provider_status_minimax_reports_anthropic_family`
- `test_cli_provider_status_openai_api_key_provider_success`
- `test_cli_provider_status_openai_codex_prefers_current_file_when_config_snapshot_is_stale`
- `test_cli_provider_status_openai_codex_uses_auth_file_when_config_and_env_missing`
- `test_cli_provider_status_qwen_oauth_uses_auth_file_when_config_missing`
- `test_cli_provider_status_unsupported_provider_returns_rc2`
- `test_cli_provider_use_clear_fallback_clears_config`
- `test_cli_provider_use_fallback_model_mismatch_returns_rc2`
- `test_cli_provider_use_provider_model_mismatch_returns_rc2`
- `test_cli_provider_use_success_updates_config_and_returns_rc0`
- `test_cli_provider_use_unsupported_provider_returns_rc2`
- `test_cli_self_evolution_trigger_posts_dry_run`
- `test_cli_skills_check_returns_diagnostics_report`
- `test_cli_skills_config_updates_config_entry_and_preserves_other_skills_keys`
- `test_cli_skills_config_writes_to_profile_overlay`
- `test_cli_skills_doctor_reports_actionable_hints`
- `test_cli_skills_doctor_supports_query_filter`
- `test_cli_skills_doctor_supports_status_and_source_filters`
- `test_cli_skills_enable_disable_and_pin_unpin`
- `test_cli_skills_install_update_and_sync_use_marketplace_root`
- `test_cli_skills_list_and_show`
- `test_cli_skills_managed_filters_by_status_and_includes_hint`
- `test_cli_skills_managed_lists_marketplace_entries`
- `test_cli_skills_managed_supports_query_filter`
- `test_cli_skills_remove_resolves_marketplace_skill_by_name`
- `test_cli_skills_search_uses_clawhub`
- `test_cli_start_creates_missing_default_config_and_prints_notice`
- `test_cli_start_uses_custom_config_values_for_runtime_and_port`
- `test_cli_status_and_version`
- `test_cli_status_respects_profile_overlay`
- `test_cli_supervisor_recover_uses_gateway_control`
- `test_cli_telegram_offset_reset_requires_confirmation`
- `test_cli_telegram_offset_reset_uses_gateway_control`
- `test_cli_telegram_offset_sync_uses_gateway_control`
- `test_cli_telegram_refresh_and_offset_commit_use_gateway_controls`
- `test_cli_telegram_status_uses_gateway_dashboard_state`
- `test_cli_tools_approvals_uses_gateway_endpoint`
- `test_cli_tools_approve_posts_review`
- `test_cli_tools_catalog_uses_gateway_endpoint`
- `test_cli_tools_revoke_grant_posts_revoke`
- `test_cli_tools_safety_preview_rejects_invalid_json`
- `test_cli_tools_safety_preview_reports_approval_mode`
- `test_cli_tools_safety_preview_reports_effective_policy`
- `test_cli_tools_show_returns_not_found`
- `test_cli_tools_show_returns_one_tool_entry`
- `test_cli_validate_channels_slack_bot_only_is_ok_with_warning`
- `test_cli_validate_config_does_not_import_gateway_runtime`
- `test_cli_validate_config_invalid_key_returns_rc2`
- `test_cli_validate_config_ok_strict`
- `test_cli_validate_onboarding_fix_and_diagnostics`
- `test_cli_validate_preflight_does_not_import_gateway_runtime`
- `test_cli_validate_preflight_gateway_failure_returns_rc2`
- `test_cli_validate_preflight_local_success`
- `test_cli_validate_preflight_optional_probes_success`
- `test_cli_validate_provider_accepts_local_runtime_without_api_key`
- `test_cli_validate_provider_and_channels`
- `test_cli_validate_provider_codex_requires_token_and_passes_when_configured`
- `test_cli_validate_provider_reports_local_runtime_failure`
- `test_cli_validate_provider_surfaces_guidance_fields`
- `test_provider_live_probe_ollama_success_detects_missing_model`
- `test_provider_live_probe_openai_codex_uses_responses_backend`
- `test_provider_live_probe_openai_model_not_listed_returns_soft_warning`
- `test_provider_live_probe_prefers_configured_vendor_transport_over_generic_model`
- `test_provider_live_probe_vllm_network_error_returns_runtime_hint`
- `run` (async)

## Notable String Markers

- `test_cli_autonomy_wake_uses_gateway_control`
- `test_cli_configure_flow_compatibility_routes_to_onboarding_wizard`
- `test_cli_configure_routes_flow_override_to_wizard`
- `test_cli_dashboard_no_open_returns_tokenized_handoff_and_bootstrap_state`
- `test_cli_dashboard_opens_browser_when_allowed`
- `test_cli_discord_refresh_uses_gateway_control`
- `test_cli_discord_status_uses_gateway_dashboard_state`
- `test_cli_gateway_alias_parses`
- `test_cli_hatch_completes_pending_bootstrap`
- `test_cli_hatch_skips_when_bootstrap_not_pending`
- `test_cli_heartbeat_trigger_failure_returns_rc2`
- `test_cli_heartbeat_trigger_success_uses_default_url_and_token`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/cli/test_commands.py`.
- Cross-reference `CONNECTIONS_test_commands.md` to see how this file fits into the wider system.
