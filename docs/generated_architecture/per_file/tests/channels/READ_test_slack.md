# READ tests/channels/test_slack.py

## Identity

- Path: `tests/channels/test_slack.py`
- Area: `tests`
- Extension: `.py`
- Lines: 334
- Size bytes: 10439
- SHA1: `8bf3a9ffab19522d6281755f223a0b03644ca49c`

## Summary

`tests.channels.test_slack` is a Python module in the `tests` area. It defines 2 class(es), led by `_FakeClient`, `_FakeWebSocket`. It exposes 18 function(s), including `__aiter__`, `__init__`, `_factory`, `__aenter__`, `__aexit__`, `__anext__`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 10
- Async functions: 8
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakeClient`
- `_FakeWebSocket`

## Functions

- `__aiter__`
- `__init__`
- `_factory`
- `_response`
- `test_slack_channel_reuses_persistent_client_across_sends`
- `test_slack_send_retries_api_ratelimited_error`
- `test_slack_send_retries_http_429_with_retry_after`
- `test_slack_socket_mode_acknowledges_and_emits_user_message`
- `test_slack_socket_mode_ignores_bot_and_acl_blocked_messages`
- `test_slack_typing_keepalive_adds_and_removes_working_indicator`
- `__aenter__` (async)
- `__aexit__` (async)
- `__anext__` (async)
- `_on_message` (async)
- `_scenario` (async)
- `aclose` (async)
- `post` (async)
- `send` (async)

## Notable String Markers

- `test_inbound_ts`
- `test_slack_channel_reuses_persistent_client_across_sends`
- `test_slack_send_retries_api_ratelimited_error`
- `test_slack_send_retries_http_429_with_retry_after`
- `test_slack_socket_mode_acknowledges_and_emits_user_message`
- `test_slack_socket_mode_ignores_bot_and_acl_blocked_messages`
- `test_slack_typing_keepalive_adds_and_removes_working_indicator`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/channels/test_slack.py`.
- Cross-reference `CONNECTIONS_test_slack.md` to see how this file fits into the wider system.
