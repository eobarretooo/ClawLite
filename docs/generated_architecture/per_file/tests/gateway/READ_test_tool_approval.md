# READ tests/gateway/test_tool_approval.py

## Identity

- Path: `tests/gateway/test_tool_approval.py`
- Area: `tests`
- Extension: `.py`
- Lines: 139
- Size bytes: 4599
- SHA1: `f5ce59aa9560d6d6c621481bf28b10603196ebf7`

## Summary

`tests.gateway.test_tool_approval` is a Python module in the `tests` area. It defines 3 class(es), led by `_Channels`, `_DiscordChannel`, `_Tools`. It exposes 8 function(s), including `get_channel`, `review_approval_request`, `test_handle_tool_approval_inbound_action_ignores_non_control_messages`, `_scenario`, `reply_interaction`, `send`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 5
- Async functions: 3
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `_Channels`
- `_DiscordChannel`
- `_Tools`

## Functions

- `get_channel`
- `review_approval_request`
- `test_handle_tool_approval_inbound_action_ignores_non_control_messages`
- `test_handle_tool_approval_inbound_action_replies_on_telegram`
- `test_handle_tool_approval_inbound_action_replies_via_discord_interaction`
- `_scenario` (async)
- `reply_interaction` (async)
- `send` (async)

## Notable String Markers

- `test_handle_tool_approval_inbound_action_ignores_non_control_messages`
- `test_handle_tool_approval_inbound_action_replies_on_telegram`
- `test_handle_tool_approval_inbound_action_replies_via_discord_interaction`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/gateway/test_tool_approval.py`.
- Cross-reference `CONNECTIONS_test_tool_approval.md` to see how this file fits into the wider system.
