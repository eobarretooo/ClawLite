# READ tests/channels/test_outbound_adapters.py

## Identity

- Path: `tests/channels/test_outbound_adapters.py`
- Area: `tests`
- Extension: `.py`
- Lines: 180
- Size bytes: 6628
- SHA1: `85d6aa63f1bf455b08d4e0b0ff98f97c156f1d2e`

## Summary

`tests.channels.test_outbound_adapters` is a Python module in the `tests` area. It defines 2 class(es), led by `_Client`, `_ClientFactory`. It exposes 13 function(s), including `__call__`, `__init__`, `_response`, `__aenter__`, `__aexit__`, `_scenario`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 8
- Async functions: 5
- Constants: 0
- Internal imports: 4
- Imported by: 0
- Matching tests: 0

## Classes

- `_Client`
- `_ClientFactory`

## Functions

- `__call__`
- `__init__`
- `_response`
- `test_discord_send_success_and_http_failure`
- `test_outbound_channels_raise_when_not_running`
- `test_passive_channel_send_raises_not_implemented_even_when_running`
- `test_slack_send_success_and_api_failure`
- `test_whatsapp_send_success_and_request_failure`
- `__aenter__` (async)
- `__aexit__` (async)
- `_scenario` (async)
- `aclose` (async)
- `post` (async)

## Notable String Markers

- `test_discord_send_success_and_http_failure`
- `test_outbound_channels_raise_when_not_running`
- `test_passive_channel_send_raises_not_implemented_even_when_running`
- `test_slack_send_success_and_api_failure`
- `test_whatsapp_send_success_and_request_failure`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/channels/test_outbound_adapters.py`.
- Cross-reference `CONNECTIONS_test_outbound_adapters.md` to see how this file fits into the wider system.
