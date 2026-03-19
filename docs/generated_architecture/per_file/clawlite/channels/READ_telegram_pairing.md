# READ clawlite/channels/telegram_pairing.py

## Identity

- Path: `clawlite/channels/telegram_pairing.py`
- Area: `channels`
- Extension: `.py`
- Lines: 331
- Size bytes: 12719
- SHA1: `c3c49992f738b0dedd0be2740691221315a0a252`

## Summary

`clawlite.channels.telegram_pairing` is a Python module in the `channels` area. It defines 2 class(es), led by `TelegramPairingRequest`, `TelegramPairingStore`. It exposes 19 function(s), including `__init__`, `_generate_unique_code`, `_normalize_approved`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 19
- Async functions: 0
- Constants: 4
- Internal imports: 0
- Imported by: 3
- Matching tests: 1

## Classes

- `TelegramPairingRequest`
- `TelegramPairingStore`

## Functions

- `__init__`
- `_generate_unique_code`
- `_normalize_approved`
- `_now_iso`
- `_parse_timestamp`
- `_pending_requests`
- `_prune_pending`
- `_random_code`
- `_read_store`
- `_resolve_path`
- `_write_store`
- `approve`
- `approved_entries`
- `from_payload`
- `issue_request`
- `list_pending`
- `reject`
- `revoke_approved`
- `to_payload`

## Constants

- `PAIRING_CODE_ALPHABET`
- `PAIRING_CODE_LENGTH`
- `PAIRING_MAX_PENDING`
- `PAIRING_PENDING_TTL_S`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/telegram_pairing.py`.
- Cross-reference `CONNECTIONS_telegram_pairing.md` to see how this file fits into the wider system.
