# READ clawlite/cli/commands.py

## Identity

- Path: `clawlite/cli/commands.py`
- Area: `cli`
- Extension: `.py`
- Lines: 2689
- Size bytes: 113757
- SHA1: `a84d3014e482dbd6c13bccbcdf90eada7475a88b`

## Summary

`clawlite.cli.commands` is a Python module in the `cli` area. It exposes 111 function(s), including `_ensure_config_materialized`, `_format_cli_error`, `_gateway_preflight_from_diagnostics`, `_scenario`. It depends on 24 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 110
- Async functions: 1
- Constants: 0
- Internal imports: 11
- Imported by: 3
- Matching tests: 1

## Functions

- `_ensure_config_materialized`
- `_format_cli_error`
- `_gateway_preflight_from_diagnostics`
- `_managed_skill_hint`
- `_managed_skill_payload`
- `_managed_skill_rows`
- `_managed_skill_slug`
- `_managed_skill_status`
- `_managed_skill_status_counts`
- `_parse_bool_flag`
- `_parse_cli_headers`
- `_parse_skill_env_assignments`
- `_print_json`
- `_print_stderr`
- `_resolve_managed_skill`
- `_run_clawhub_command`
- `_skills_doctor_hint`
- `_skills_doctor_status`
- `_skills_lifecycle_payload`
- `_skills_loader_for_args`
- `_skills_managed_root`
- `_temporary_cli_profile`
- `build_parser`
- `cmd_autonomy_wake`
- `cmd_configure`
- `cmd_cron_add`
- `cmd_cron_disable`
- `cmd_cron_enable`
- `cmd_cron_list`
- `cmd_cron_remove`
- `cmd_cron_run`
- `cmd_dashboard`
- `cmd_diagnostics`
- `cmd_discord_refresh`
- `cmd_discord_status`
- `cmd_hatch`
- `cmd_heartbeat_trigger`
- `cmd_jobs_cancel`
- `cmd_jobs_list`
- `cmd_jobs_status`
- `cmd_memory_branch`
- `cmd_memory_branches`
- `cmd_memory_checkout`
- `cmd_memory_doctor`
- `cmd_memory_eval`
- `cmd_memory_export`
- `cmd_memory_import`
- `cmd_memory_merge`
- `cmd_memory_overview`
- `cmd_memory_privacy`
- `cmd_memory_profile`
- `cmd_memory_quality`
- `cmd_memory_rollback`
- `cmd_memory_share_optin`
- `cmd_memory_snapshot`
- `cmd_memory_suggest`
- `cmd_memory_version`
- `cmd_onboard`
- `cmd_pairing_approve`
- `cmd_pairing_list`
- `cmd_pairing_reject`
- `cmd_pairing_revoke`
- `cmd_provider_clear_auth`
- `cmd_provider_login`
- `cmd_provider_logout`
- `cmd_provider_recover`
- `cmd_provider_set_auth`
- `cmd_provider_status`
- `cmd_provider_use`
- `cmd_run`
- `cmd_self_evolution_status`
- `cmd_self_evolution_trigger`
- `cmd_skills_check`
- `cmd_skills_clear_version`
- `cmd_skills_config`
- `cmd_skills_disable`
- `cmd_skills_doctor`
- `cmd_skills_enable`
- `cmd_skills_install`
- `cmd_skills_list`
- `cmd_skills_managed`
- `cmd_skills_pin`
- `cmd_skills_pin_version`
- `cmd_skills_remove`
- `cmd_skills_search`
- `cmd_skills_show`
- `cmd_skills_sync`
- `cmd_skills_unpin`
- `cmd_skills_update`
- `cmd_start`
- `cmd_status`
- `cmd_supervisor_recover`
- `cmd_telegram_offset_commit`
- `cmd_telegram_offset_reset`
- `cmd_telegram_offset_sync`
- `cmd_telegram_refresh`
- `cmd_telegram_status`
- `cmd_tools_approvals`
- `cmd_tools_approve`
- `cmd_tools_catalog`
- `cmd_tools_reject`
- `cmd_tools_revoke_grant`
- `cmd_tools_safety`
- `cmd_tools_show`
- `cmd_validate_channels`
- `cmd_validate_config`
- `cmd_validate_onboarding`
- `cmd_validate_preflight`
- `cmd_validate_provider`
- `main`
- `_scenario` (async)

## Notable String Markers

- `clawlite import`
- `clawlite skills`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/cli/commands.py`.
- Cross-reference `CONNECTIONS_commands.md` to see how this file fits into the wider system.
