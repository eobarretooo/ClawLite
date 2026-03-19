# READ tests/tools/test_registry.py

## Identity

- Path: `tests/tools/test_registry.py`
- Area: `tests`
- Extension: `.py`
- Lines: 1183
- Size bytes: 41509
- SHA1: `ff050973e66bbfc7e758c1fca59d30d59f4fc9a3`

## Summary

`tests.tools.test_registry` is a Python module in the `tests` area. It defines 8 class(es), led by `BrowserLikeTool`, `EchoTool`, `ExecLikeTool`, `NestedSchemaTool`. It exposes 52 function(s), including `__enter__`, `__exit__`, `__init__`, `_scenario`, `run`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 8
- Functions: 50
- Async functions: 2
- Constants: 0
- Internal imports: 4
- Imported by: 0
- Matching tests: 0

## Classes

- `BrowserLikeTool`
- `EchoTool`
- `ExecLikeTool`
- `NestedSchemaTool`
- `RunSkillLikeTool`
- `StrictSchemaTool`
- `_FakeSpan`
- `_FakeTracer`

## Functions

- `__enter__`
- `__exit__`
- `__init__`
- `args_schema`
- `record_exception`
- `set_attribute`
- `start_as_current_span`
- `test_tool_registry_aggregates_multiple_validation_errors`
- `test_tool_registry_allows_non_risky_tools_for_empty_channel_and_session`
- `test_tool_registry_allows_risky_tools_for_cli_channel`
- `test_tool_registry_allows_valid_arguments_after_schema_validation`
- `test_tool_registry_approval_grant_is_bound_to_same_request_payload`
- `test_tool_registry_approval_request_grant_allows_retry`
- `test_tool_registry_approval_snapshots_include_requests_and_grants`
- `test_tool_registry_block_precedes_approval_when_both_match`
- `test_tool_registry_blocks_browser_when_configured_for_channel`
- `test_tool_registry_blocks_exec_binary_specifier_for_telegram`
- `test_tool_registry_blocks_missing_required_arguments_fail_closed`
- `test_tool_registry_blocks_nested_item_type_and_min_items_fail_closed`
- `test_tool_registry_blocks_nested_missing_required_arguments_fail_closed`
- `test_tool_registry_blocks_nested_unexpected_arguments_fail_closed`
- `test_tool_registry_blocks_non_object_arguments_fail_closed`
- `test_tool_registry_blocks_operation_specific_browser_specifier`
- `test_tool_registry_blocks_risky_tools_for_blocked_channels`
- `test_tool_registry_blocks_risky_tools_for_unknown_channel_when_restricted`
- `test_tool_registry_blocks_risky_tools_with_derived_channel_from_session`
- `test_tool_registry_blocks_run_skill_for_telegram_when_explicitly_configured`
- `test_tool_registry_blocks_run_skill_name_specifier_for_telegram`
- `test_tool_registry_blocks_type_and_range_mismatches_fail_closed`
- `test_tool_registry_blocks_unexpected_arguments_when_schema_forbids_them`
- `test_tool_registry_blocks_wildcard_browser_specifier`
- `test_tool_registry_consume_pending_approval_requests_is_one_shot`
- `test_tool_registry_default_safety_allows_run_skill_for_telegram`
- `test_tool_registry_default_safety_marks_browser_as_risky`
- `test_tool_registry_derives_exec_shell_env_and_cwd_specifiers`
- `test_tool_registry_derives_exec_shell_specifier_for_explicit_shell_wrapper`
- `test_tool_registry_derives_host_specifiers_for_browser_navigate`
- `test_tool_registry_derives_host_specifiers_for_web_fetch`
- `test_tool_registry_exec_can_require_approval_for_specific_env_key`
- `test_tool_registry_execute`
- `test_tool_registry_execute_emits_tool_span`
- `test_tool_registry_execute_requires_approval_when_configured`
- `test_tool_registry_layered_agent_override_supersedes_profile_and_global`
- `test_tool_registry_layered_channel_override_can_clear_risky_specifiers`
- `test_tool_registry_layered_channel_override_supersedes_agent_and_global`
- `test_tool_registry_layered_profile_override_changes_effective_risky_tools`
- `test_tool_registry_legacy_approval_grants_remain_visible_and_usable`
- `test_tool_registry_revoke_approval_grants_filters_by_session_channel_and_rule`
- `test_tool_registry_safety_decision_reports_approval_requirement`
- `test_tool_registry_safety_decision_reports_matched_specifiers`
- `_scenario` (async)
- `run` (async)

## Notable String Markers

- `test_tool_registry_aggregates_multiple_validation_errors`
- `test_tool_registry_allows_non_risky_tools_for_empty_channel_and_session`
- `test_tool_registry_allows_risky_tools_for_cli_channel`
- `test_tool_registry_allows_valid_arguments_after_schema_validation`
- `test_tool_registry_approval_grant_is_bound_to_same_request_payload`
- `test_tool_registry_approval_request_grant_allows_retry`
- `test_tool_registry_approval_snapshots_include_requests_and_grants`
- `test_tool_registry_block_precedes_approval_when_both_match`
- `test_tool_registry_blocks_browser_when_configured_for_channel`
- `test_tool_registry_blocks_exec_binary_specifier_for_telegram`
- `test_tool_registry_blocks_missing_required_arguments_fail_closed`
- `test_tool_registry_blocks_nested_item_type_and_min_items_fail_closed`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_registry.py`.
- Cross-reference `CONNECTIONS_test_registry.md` to see how this file fits into the wider system.
