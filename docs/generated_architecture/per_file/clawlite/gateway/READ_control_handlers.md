# READ clawlite/gateway/control_handlers.py

## Identity

- Path: `clawlite/gateway/control_handlers.py`
- Area: `gateway`
- Extension: `.py`
- Lines: 227
- Size bytes: 11020
- SHA1: `62de75f0ab6da0f12ee881ffcfa341cbd69569b5`

## Summary

`clawlite.gateway.control_handlers` is a Python module in the `gateway` area. It defines 1 class(es), led by `GatewayControlHandlers`. It exposes 23 function(s), including `_check_control`, `_require_channel`, `_require_channel_operator`, `autonomy_wake`, `channels_inbound_replay`, `channels_recover`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 3
- Async functions: 20
- Constants: 0
- Internal imports: 1
- Imported by: 1
- Matching tests: 0

## Classes

- `GatewayControlHandlers`

## Functions

- `_check_control`
- `_require_channel`
- `_require_channel_operator`
- `autonomy_wake` (async)
- `channels_inbound_replay` (async)
- `channels_recover` (async)
- `channels_replay` (async)
- `discord_refresh` (async)
- `heartbeat_trigger` (async)
- `memory_snapshot_create` (async)
- `memory_snapshot_rollback` (async)
- `memory_suggest_refresh` (async)
- `provider_recover` (async)
- `self_evolution_status` (async)
- `self_evolution_trigger` (async)
- `supervisor_recover` (async)
- `telegram_offset_commit` (async)
- `telegram_offset_reset` (async)
- `telegram_offset_sync` (async)
- `telegram_pairing_approve` (async)
- `telegram_pairing_reject` (async)
- `telegram_pairing_revoke` (async)
- `telegram_refresh` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/gateway/control_handlers.py`.
- Cross-reference `CONNECTIONS_control_handlers.md` to see how this file fits into the wider system.
