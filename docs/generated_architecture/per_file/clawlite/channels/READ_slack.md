# READ clawlite/channels/slack.py

## Identity

- Path: `clawlite/channels/slack.py`
- Area: `channels`
- Extension: `.py`
- Lines: 388
- Size bytes: 15624
- SHA1: `d8405128be2e6eeb1e00e41182234d40369e1c3d`

## Summary

`clawlite.channels.slack` is a Python module in the `channels` area. It defines 1 class(es), led by `SlackChannel`. It exposes 17 function(s), including `__init__`, `_extract_retry_after`, `_is_allowed_user`, `_ack_socket_envelope`, `_handle_slack_event`, `_handle_socket_envelope`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 6
- Async functions: 11
- Constants: 0
- Internal imports: 1
- Imported by: 3
- Matching tests: 1

## Classes

- `SlackChannel`

## Functions

- `__init__`
- `_extract_retry_after`
- `_is_allowed_user`
- `_normalize_allow_from`
- `_parse_retry_after`
- `_start_typing_keepalive`
- `_ack_socket_envelope` (async)
- `_handle_slack_event` (async)
- `_handle_socket_envelope` (async)
- `_set_working_indicator` (async)
- `_socket_mode_runner` (async)
- `_socket_open_url` (async)
- `_stop_typing_keepalive` (async)
- `_typing_loop` (async)
- `send` (async)
- `start` (async)
- `stop` (async)

## Notable String Markers

- `test_inbound_ts`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/slack.py`.
- Cross-reference `CONNECTIONS_slack.md` to see how this file fits into the wider system.
