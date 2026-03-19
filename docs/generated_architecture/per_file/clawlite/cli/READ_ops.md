# READ clawlite/cli/ops.py

## Identity

- Path: `clawlite/cli/ops.py`
- Area: `cli`
- Extension: `.py`
- Lines: 3283
- Size bytes: 121941
- SHA1: `cb0820d964085982473705e1b8f5ca18a051353d`

## Summary

`clawlite.cli.ops` is a Python module in the `cli` area. It exposes 76 function(s), including `_build_memory_store`, `_file_stat`, `_gateway_control_request`. It depends on 26 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 76
- Async functions: 0
- Constants: 4
- Internal imports: 16
- Imported by: 4
- Matching tests: 0

## Functions

- `_build_memory_store`
- `_file_stat`
- `_gateway_control_request`
- `_mask_secret`
- `_normalize_provider_name`
- `_parse_oauth_result`
- `_provider_name_variants`
- `_provider_override`
- `_provider_override_for_update`
- `_provider_profile_payload`
- `_provider_spec`
- `_resolve_codex_base_url`
- `_resolve_codex_probe_endpoint`
- `_resolve_generic_oauth_status`
- `_resolve_provider_probe_target`
- `_resolve_supported_provider`
- `_response_error_detail`
- `_schema_hints`
- `_telegram_pairing_store`
- `autonomy_wake`
- `channels_validation`
- `diagnostics_snapshot`
- `discord_refresh`
- `discord_status`
- `fetch_gateway_diagnostics`
- `fetch_gateway_tool_approvals`
- `fetch_gateway_tools_catalog`
- `heartbeat_trigger`
- `memory_branch_checkout`
- `memory_branch_create`
- `memory_branches_snapshot`
- `memory_doctor_snapshot`
- `memory_eval_snapshot`
- `memory_export_snapshot`
- `memory_import_snapshot`
- `memory_merge_branches`
- `memory_overview_snapshot`
- `memory_privacy_snapshot`
- `memory_profile_snapshot`
- `memory_quality_snapshot`
- `memory_shared_opt_in`
- `memory_snapshot_create`
- `memory_snapshot_rollback`
- `memory_suggest_snapshot`
- `memory_version_snapshot`
- `onboarding_validation`
- `pairing_approve`
- `pairing_list`
- `pairing_reject`
- `pairing_revoke`
- `provider_clear_auth`
- `provider_live_probe`
- `provider_login_oauth`
- `provider_login_openai_codex`
- `provider_logout_oauth`
- `provider_logout_openai_codex`
- `provider_recover`
- `provider_set_auth`
- `provider_status`
- `provider_use_model`
- `provider_validation`
- `resolve_codex_auth`
- `resolve_gemini_oauth`
- `resolve_oauth_provider_auth`
- `resolve_qwen_oauth`
- `review_gateway_tool_approval`
- `revoke_gateway_tool_grants`
- `self_evolution_status`
- `self_evolution_trigger`
- `supervisor_recover`
- `telegram_live_probe`
- `telegram_offset_commit`
- `telegram_offset_reset`
- `telegram_offset_sync`
- `telegram_refresh`
- `telegram_status`

## Constants

- `OAUTH_PROVIDER_DEFAULT_MODELS`
- `SUPPORTED_OAUTH_PROVIDER_AUTH`
- `SUPPORTED_PROVIDER_AUTH`
- `SUPPORTED_PROVIDER_USE`

## Notable String Markers

- `clawlite provider`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/cli/ops.py`.
- Cross-reference `CONNECTIONS_ops.md` to see how this file fits into the wider system.
