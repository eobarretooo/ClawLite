# READ clawlite/channels/whatsapp.py

## Identity

- Path: `clawlite/channels/whatsapp.py`
- Area: `channels`
- Extension: `.py`
- Lines: 401
- Size bytes: 14633
- SHA1: `70bd0d5d491d646dde2ca46759e90a17121a72fc`

## Summary

`clawlite.channels.whatsapp` is a Python module in the `channels` area. It defines 1 class(es), led by `WhatsAppChannel`. It exposes 22 function(s), including `__init__`, `_bridge_endpoint`, `_extract_retry_after`, `_client_post`, `_get_client`, `_send_typing_once`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 13
- Async functions: 9
- Constants: 0
- Internal imports: 1
- Imported by: 3
- Matching tests: 1

## Classes

- `WhatsAppChannel`

## Functions

- `__init__`
- `_bridge_endpoint`
- `_extract_retry_after`
- `_field`
- `_headers`
- `_is_allowed_sender`
- `_normalize_allow_from`
- `_normalize_bridge_url`
- `_parse_retry_after`
- `_placeholder_for_media`
- `_remember_message_id`
- `_sender_id`
- `_start_typing_keepalive`
- `_client_post` (async)
- `_get_client` (async)
- `_send_typing_once` (async)
- `_stop_typing_keepalive` (async)
- `_typing_loop` (async)
- `receive_hook` (async)
- `send` (async)
- `start` (async)
- `stop` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/whatsapp.py`.
- Cross-reference `CONNECTIONS_whatsapp.md` to see how this file fits into the wider system.
