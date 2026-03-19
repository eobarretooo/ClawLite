# READ tests/tools/test_skill_tool.py

## Identity

- Path: `tests/tools/test_skill_tool.py`
- Area: `tests`
- Extension: `.py`
- Lines: 1096
- Size bytes: 38156
- SHA1: `7dac849cfd23e1682b9131be0c0a87db4e53011b`

## Summary

`tests.tools.test_skill_tool` is a Python module in the `tests` area. It defines 11 class(es), led by `ExplodingMemory`, `FakeExecCaptureTool`, `FakeExecStatusTool`, `FakeExecTool`. It exposes 41 function(s), including `__init__`, `_write_skill`, `args_schema`, `_scenario`, `complete`, `run`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 11
- Functions: 38
- Async functions: 3
- Constants: 0
- Internal imports: 6
- Imported by: 0
- Matching tests: 0

## Classes

- `ExplodingMemory`
- `FakeExecCaptureTool`
- `FakeExecStatusTool`
- `FakeExecTool`
- `FakeMemory`
- `FakeProvider`
- `FakeReadTool`
- `FakeSessionsSpawnTool`
- `FakeWebFetchPayloadTool`
- `FakeWebFetchSequenceTool`
- `FakeWebSearchTool`

## Functions

- `__init__`
- `_write_skill`
- `args_schema`
- `integration_policy`
- `test_run_skill_allows_execution_when_memory_policy_allows`
- `test_run_skill_blocks_command_when_exec_tool_not_registered`
- `test_run_skill_blocks_disabled_skill`
- `test_run_skill_blocks_execution_when_memory_policy_denies`
- `test_run_skill_blocks_execution_when_memory_policy_errors`
- `test_run_skill_blocks_oversized_argument_list`
- `test_run_skill_coding_agent_wraps_sessions_spawn`
- `test_run_skill_command_injects_skill_entry_env_overrides`
- `test_run_skill_command_prefix_dispatches_multiword_binding`
- `test_run_skill_command_uses_exec_tool_in_cli_context`
- `test_run_skill_dispatches_script_to_tool_registry`
- `test_run_skill_does_not_fallback_to_external_script_exec`
- `test_run_skill_executes_command_binding`
- `test_run_skill_gh_issues_guide_mode_returns_structured_help`
- `test_run_skill_gh_issues_structured_list_dispatches_gh_issue`
- `test_run_skill_gh_issues_uses_skill_entry_api_key_for_auth`
- `test_run_skill_github_precheck_blocks_when_auth_is_missing`
- `test_run_skill_healthcheck_returns_local_diagnostics_snapshot`
- `test_run_skill_model_usage_executes_local_script_binding`
- `test_run_skill_respects_unavailable_requirements`
- `test_run_skill_returns_not_executable_when_no_binding`
- `test_run_skill_returns_skill_blocked_when_registry_blocks_exec`
- `test_run_skill_returns_skill_blocked_when_registry_blocks_exec_unknown_channel`
- `test_run_skill_returns_skill_requires_approval_when_registry_requires_exec_approval`
- `test_run_skill_script_respects_channel_safety_policy`
- `test_run_skill_session_logs_reads_jsonl_without_jq_or_rg`
- `test_run_skill_summarize_blocks_when_reader_tools_are_unavailable`
- `test_run_skill_summarize_blocks_when_web_fetch_is_unavailable`
- `test_run_skill_summarize_falls_back_to_provider_for_local_files`
- `test_run_skill_summarize_falls_back_to_provider_for_urls`
- `test_run_skill_weather_blocks_when_web_fetch_is_unavailable`
- `test_run_skill_weather_falls_back_to_open_meteo`
- `test_run_skill_weather_reports_web_fetch_approval_requirement`
- `test_run_skill_weather_respects_web_fetch_channel_safety_policy`
- `_scenario` (async)
- `complete` (async)
- `run` (async)

## Notable String Markers

- `test_run_skill_allows_execution_when_memory_policy_allows`
- `test_run_skill_blocks_command_when_exec_tool_not_registered`
- `test_run_skill_blocks_disabled_skill`
- `test_run_skill_blocks_execution_when_memory_policy_denies`
- `test_run_skill_blocks_execution_when_memory_policy_errors`
- `test_run_skill_blocks_oversized_argument_list`
- `test_run_skill_coding_agent_wraps_sessions_spawn`
- `test_run_skill_command_injects_skill_entry_env_overrides`
- `test_run_skill_command_prefix_dispatches_multiword_binding`
- `test_run_skill_command_uses_exec_tool_in_cli_context`
- `test_run_skill_dispatches_script_to_tool_registry`
- `test_run_skill_does_not_fallback_to_external_script_exec`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_skill_tool.py`.
- Cross-reference `CONNECTIONS_test_skill_tool.md` to see how this file fits into the wider system.
