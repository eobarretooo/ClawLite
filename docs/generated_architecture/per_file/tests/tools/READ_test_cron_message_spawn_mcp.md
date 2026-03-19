# READ tests/tools/test_cron_message_spawn_mcp.py

## Identity

- Path: `tests/tools/test_cron_message_spawn_mcp.py`
- Area: `tests`
- Extension: `.py`
- Lines: 428
- Size bytes: 15363
- SHA1: `4e40d47bebf25033d53fb374510b78886810bddc`

## Summary

`tests.tools.test_cron_message_spawn_mcp` is a Python module in the `tests` area. It defines 5 class(es), led by `FakeCronAPI`, `FakeMemory`, `FakeMemoryPolicyRaises`, `FakeMsgAPI`. It exposes 27 function(s), including `__init__`, `enable_job`, `integration_policy`, `_runner`, `_scenario`, `_slow_runner`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 5
- Functions: 20
- Async functions: 7
- Constants: 0
- Internal imports: 5
- Imported by: 0
- Matching tests: 0

## Classes

- `FakeCronAPI`
- `FakeMemory`
- `FakeMemoryPolicyRaises`
- `FakeMsgAPI`
- `ThreadAwareCronAPI`

## Functions

- `__init__`
- `enable_job`
- `integration_policy`
- `list_jobs`
- `remove_job`
- `test_cron_tool_add_and_list`
- `test_cron_tool_rejects_foreign_session_override`
- `test_cron_tool_sync_remove_and_enable_run_off_event_loop_thread`
- `test_message_tool`
- `test_message_tool_invalid_buttons_raises_value_error`
- `test_message_tool_maps_buttons_to_telegram_metadata`
- `test_message_tool_maps_media_to_telegram_metadata`
- `test_message_tool_maps_telegram_edit_action_to_metadata_bridge`
- `test_message_tool_rejects_media_for_non_telegram_channel`
- `test_message_tool_telegram_action_constraints_raise_value_error`
- `test_spawn_tool`
- `test_spawn_tool_allows_when_memory_policy_allows`
- `test_spawn_tool_blocks_when_memory_policy_check_raises`
- `test_spawn_tool_blocks_when_memory_policy_denies`
- `test_spawn_tool_surfaces_queue_limits`
- `_runner` (async)
- `_scenario` (async)
- `_slow_runner` (async)
- `add_job` (async)
- `list_jobs` (async)
- `run_job` (async)
- `send` (async)

## Notable String Markers

- `test_cron_tool_add_and_list`
- `test_cron_tool_rejects_foreign_session_override`
- `test_cron_tool_sync_remove_and_enable_run_off_event_loop_thread`
- `test_message_tool`
- `test_message_tool_invalid_buttons_raises_value_error`
- `test_message_tool_maps_buttons_to_telegram_metadata`
- `test_message_tool_maps_media_to_telegram_metadata`
- `test_message_tool_maps_telegram_edit_action_to_metadata_bridge`
- `test_message_tool_rejects_media_for_non_telegram_channel`
- `test_message_tool_telegram_action_constraints_raise_value_error`
- `test_spawn_tool`
- `test_spawn_tool_allows_when_memory_policy_allows`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_cron_message_spawn_mcp.py`.
- Cross-reference `CONNECTIONS_test_cron_message_spawn_mcp.md` to see how this file fits into the wider system.
