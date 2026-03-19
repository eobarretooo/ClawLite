# READ clawlite/tools/skill.py

## Identity

- Path: `clawlite/tools/skill.py`
- Area: `tools`
- Extension: `.py`
- Lines: 1047
- Size bytes: 44520
- SHA1: `3328f6c57218f293cfefcf04b83a9862622f64cc`

## Summary

`clawlite.tools.skill` is a Python module in the `tools` area. It defines 1 class(es), led by `SkillTool`. It exposes 37 function(s), including `__init__`, `_exec_output_exit_code`, `_exec_output_stream`, `_dispatch_script`, `_fetch_web_payload`, `_load_summary_source`. It depends on 19 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 23
- Async functions: 14
- Constants: 4
- Internal imports: 7
- Imported by: 3
- Matching tests: 6

## Classes

- `SkillTool`

## Functions

- `__init__`
- `_exec_output_exit_code`
- `_exec_output_stream`
- `_extra_args`
- `_gh_bool`
- `_gh_label_values`
- `_gh_value`
- `_guard_extra_args`
- `_iter_rows`
- `_join_command`
- `_load_module_from_path`
- `_matches`
- `_policy_reason`
- `_resolve_session_path`
- `_script_tool_arguments`
- `_skill_config_path`
- `_skill_payload`
- `_timeout_value`
- `_weather_code_description`
- `_web_fetch_error_message`
- `_web_fetch_json_payload`
- `_web_fetch_result_text`
- `args_schema`
- `_dispatch_script` (async)
- `_fetch_web_payload` (async)
- `_load_summary_source` (async)
- `_memory_policy_allows` (async)
- `_precheck_github_auth` (async)
- `_run_coding_agent` (async)
- `_run_command_via_exec_tool` (async)
- `_run_gh_issues` (async)
- `_run_healthcheck` (async)
- `_run_model_usage` (async)
- `_run_session_logs` (async)
- `_run_summarize` (async)
- `_run_weather` (async)
- `run` (async)

## Constants

- `MAX_ARG_CHARS`
- `MAX_SKILL_ARGS`
- `MAX_TIMEOUT_SECONDS`
- `SUMMARY_MAX_SOURCE_CHARS`

## Notable String Markers

- `test_cost`
- `test_cost_date`
- `test_day_cost`
- `test_model_date`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/skill.py`.
- Cross-reference `CONNECTIONS_skill.md` to see how this file fits into the wider system.
