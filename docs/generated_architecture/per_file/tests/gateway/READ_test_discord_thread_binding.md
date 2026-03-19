# READ tests/gateway/test_discord_thread_binding.py

## Identity

- Path: `tests/gateway/test_discord_thread_binding.py`
- Area: `tests`
- Extension: `.py`
- Lines: 307
- Size bytes: 10733
- SHA1: `7bf7ebd2a7572663ffbc5b502e176e436d49fcb1`

## Summary

`tests.gateway.test_discord_thread_binding` is a Python module in the `tests` area. It defines 2 class(es), led by `_Channels`, `_DiscordChannel`. It exposes 16 function(s), including `get_channel`, `operator_status`, `test_handle_discord_thread_binding_focus_replies_via_interaction`, `_scenario`, `bind_thread`, `operator_refresh_presence`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 9
- Async functions: 7
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `_Channels`
- `_DiscordChannel`

## Functions

- `get_channel`
- `operator_status`
- `test_handle_discord_thread_binding_focus_replies_via_interaction`
- `test_handle_discord_thread_binding_ignores_non_control_messages`
- `test_handle_discord_thread_binding_refreshes_presence`
- `test_handle_discord_thread_binding_refreshes_transport`
- `test_handle_discord_thread_binding_reports_operator_status`
- `test_handle_discord_thread_binding_reports_presence_status`
- `test_handle_discord_thread_binding_unfocus_falls_back_to_channel_send`
- `_scenario` (async)
- `bind_thread` (async)
- `operator_refresh_presence` (async)
- `operator_refresh_transport` (async)
- `reply_interaction` (async)
- `send` (async)
- `unbind_thread` (async)

## Notable String Markers

- `test_handle_discord_thread_binding_focus_replies_via_interaction`
- `test_handle_discord_thread_binding_ignores_non_control_messages`
- `test_handle_discord_thread_binding_refreshes_presence`
- `test_handle_discord_thread_binding_refreshes_transport`
- `test_handle_discord_thread_binding_reports_operator_status`
- `test_handle_discord_thread_binding_reports_presence_status`
- `test_handle_discord_thread_binding_unfocus_falls_back_to_channel_send`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/gateway/test_discord_thread_binding.py`.
- Cross-reference `CONNECTIONS_test_discord_thread_binding.md` to see how this file fits into the wider system.
