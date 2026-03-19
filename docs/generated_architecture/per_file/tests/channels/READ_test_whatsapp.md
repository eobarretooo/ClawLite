# READ tests/channels/test_whatsapp.py

## Identity

- Path: `tests/channels/test_whatsapp.py`
- Area: `tests`
- Extension: `.py`
- Lines: 275
- Size bytes: 8737
- SHA1: `6542e7d08354d1e895ed1a236c04fe0741039be5`

## Summary

`tests.channels.test_whatsapp` is a Python module in the `tests` area. It defines 1 class(es), led by `_FakeClient`. It exposes 13 function(s), including `__init__`, `_factory`, `_response`, `_on_message`, `_scenario`, `aclose`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 9
- Async functions: 4
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakeClient`

## Functions

- `__init__`
- `_factory`
- `_response`
- `test_whatsapp_receive_hook_emits_text_message_with_full_chat_id`
- `test_whatsapp_receive_hook_filters_self_and_acl`
- `test_whatsapp_receive_hook_rejects_invalid_payloads`
- `test_whatsapp_receive_hook_supports_media_placeholder_and_dedupes`
- `test_whatsapp_send_retries_rate_limit_and_returns_bridge_message_id`
- `test_whatsapp_typing_keepalive_hits_typing_endpoint_until_stopped`
- `_on_message` (async)
- `_scenario` (async)
- `aclose` (async)
- `post` (async)

## Notable String Markers

- `test_whatsapp_receive_hook_emits_text_message_with_full_chat_id`
- `test_whatsapp_receive_hook_filters_self_and_acl`
- `test_whatsapp_receive_hook_rejects_invalid_payloads`
- `test_whatsapp_receive_hook_supports_media_placeholder_and_dedupes`
- `test_whatsapp_send_retries_rate_limit_and_returns_bridge_message_id`
- `test_whatsapp_typing_keepalive_hits_typing_endpoint_until_stopped`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/channels/test_whatsapp.py`.
- Cross-reference `CONNECTIONS_test_whatsapp.md` to see how this file fits into the wider system.
