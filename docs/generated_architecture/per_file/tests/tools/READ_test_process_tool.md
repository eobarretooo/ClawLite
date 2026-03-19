# READ tests/tools/test_process_tool.py

## Identity

- Path: `tests/tools/test_process_tool.py`
- Area: `tests`
- Extension: `.py`
- Lines: 259
- Size bytes: 9900
- SHA1: `3d449179fd951305d360bbe12883d3f942439559`

## Summary

`tests.tools.test_process_tool` is a Python module in the `tests` area. It defines 1 class(es), led by `DelayedCaptureProcessTool`. It exposes 13 function(s), including `_loads`, `test_process_clear_output`, `test_process_kill_running_process`, `_capture_stream`, `_scenario`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 11
- Async functions: 2
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `DelayedCaptureProcessTool`

## Functions

- `_loads`
- `test_process_clear_output`
- `test_process_kill_running_process`
- `test_process_log_slicing`
- `test_process_output_truncation_cap`
- `test_process_poll_waits_for_capture_completion`
- `test_process_remove_finished_session`
- `test_process_retention_prunes_finished_keeps_running`
- `test_process_start_blocks_explicit_shell_path_outside_workspace`
- `test_process_start_list_poll_completed_command`
- `test_process_unknown_action_and_missing_session_handling`
- `_capture_stream` (async)
- `_scenario` (async)

## Notable String Markers

- `test_process_clear_output`
- `test_process_kill_running_process`
- `test_process_log_slicing`
- `test_process_output_truncation_cap`
- `test_process_poll_waits_for_capture_completion`
- `test_process_remove_finished_session`
- `test_process_retention_prunes_finished_keeps_running`
- `test_process_start_blocks_explicit_shell_path_outside_workspace`
- `test_process_start_list_poll_completed_command`
- `test_process_unknown_action_and_missing_session_handling`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_process_tool.py`.
- Cross-reference `CONNECTIONS_test_process_tool.md` to see how this file fits into the wider system.
