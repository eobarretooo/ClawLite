# READ tests/tools/test_exec_files.py

## Identity

- Path: `tests/tools/test_exec_files.py`
- Area: `tests`
- Extension: `.py`
- Lines: 276
- Size bytes: 10143
- SHA1: `fa247e91f417697f805c80abc755e21abbb9baef`

## Summary

`tests.tools.test_exec_files` is a Python module in the `tests` area. It exposes 20 function(s), including `test_exec_tool_allow_patterns_enforced`, `test_exec_tool_blocks_dangerous_env_overrides`, `test_exec_tool_default_policy_blocks_dangerous_command`, `_scenario`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 19
- Async functions: 1
- Constants: 0
- Internal imports: 3
- Imported by: 0
- Matching tests: 0

## Functions

- `test_exec_tool_allow_patterns_enforced`
- `test_exec_tool_blocks_dangerous_env_overrides`
- `test_exec_tool_default_policy_blocks_dangerous_command`
- `test_exec_tool_env_overrides`
- `test_exec_tool_invalid_command_syntax_returns_deterministic_marker`
- `test_exec_tool_output_truncation_telemetry_for_stdout_and_stderr`
- `test_exec_tool_path_append`
- `test_exec_tool_restrict_to_workspace_allows_explicit_shell_pwd_inside_workspace`
- `test_exec_tool_restrict_to_workspace_blocks_absolute_path_in_flag`
- `test_exec_tool_restrict_to_workspace_blocks_cwd_outside_workspace`
- `test_exec_tool_restrict_to_workspace_blocks_explicit_shell_home_expansion`
- `test_exec_tool_restrict_to_workspace_blocks_outside_path`
- `test_exec_tool_runs_command`
- `test_exec_tool_supports_cwd_override`
- `test_exec_tool_supports_pipe_and_redirect_via_shell_wrapper`
- `test_exec_tool_timeout_reports_telemetry`
- `test_file_alias_tools_reuse_existing_behavior`
- `test_file_tools_restrict_to_workspace_blocks_outside_path`
- `test_file_tools_roundtrip`
- `_scenario` (async)

## Notable String Markers

- `test_exec_tool_allow_patterns_enforced`
- `test_exec_tool_blocks_dangerous_env_overrides`
- `test_exec_tool_default_policy_blocks_dangerous_command`
- `test_exec_tool_env_overrides`
- `test_exec_tool_invalid_command_syntax_returns_deterministic_marker`
- `test_exec_tool_output_truncation_telemetry_for_stdout_and_stderr`
- `test_exec_tool_path_append`
- `test_exec_tool_restrict_to_workspace_allows_explicit_shell_pwd_inside_workspace`
- `test_exec_tool_restrict_to_workspace_blocks_absolute_path_in_flag`
- `test_exec_tool_restrict_to_workspace_blocks_cwd_outside_workspace`
- `test_exec_tool_restrict_to_workspace_blocks_explicit_shell_home_expansion`
- `test_exec_tool_restrict_to_workspace_blocks_outside_path`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_exec_files.py`.
- Cross-reference `CONNECTIONS_test_exec_files.md` to see how this file fits into the wider system.
