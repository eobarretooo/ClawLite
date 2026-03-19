# READ clawlite/channels/manager.py

## Identity

- Path: `clawlite/channels/manager.py`
- Area: `channels`
- Extension: `.py`
- Lines: 2429
- Size bytes: 104694
- SHA1: `3d23ae0b845479d65895821d54f0aa0007704a1c`

## Summary

`clawlite.channels.manager` is a Python module in the `channels` area. It defines 3 class(es), led by `ChannelManager`, `EngineProtocol`, `_SessionDispatchSlot`. It exposes 93 function(s), including `__init__`, `_background_task_state`, `_base_target_from_event`, `_acquire_dispatch_slot`, `_clear_persisted_dead_letter`, `_clear_persisted_inbound`. It depends on 30 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 58
- Async functions: 35
- Constants: 1
- Internal imports: 19
- Imported by: 3
- Matching tests: 1

## Classes

- `ChannelManager`
- `EngineProtocol`
- `_SessionDispatchSlot`

## Functions

- `__init__`
- `_background_task_state`
- `_base_target_from_event`
- `_channel_worker_state`
- `_consume_pending_tool_approval_requests`
- `_delivery_allowed`
- `_delivery_metadata_value`
- `_delivery_record_key`
- `_derive_delivery_idempotency_key`
- `_dispatch_typing_context`
- `_ensure_delivery_channel`
- `_ensure_delivery_idempotency_key`
- `_ensure_recovery_channel`
- `_inbound_record_key`
- `_inc_delivery`
- `_is_delivery_idempotency_suppressed`
- `_is_progress_event`
- `_is_stop_command`
- `_is_tool_hint_event`
- `_load_delivery_idempotency_persistence_locked`
- `_load_delivery_persistence_locked`
- `_load_inbound_persistence_locked`
- `_normalize_reply_to_mode`
- `_on_done`
- `_prepare_outbound_metadata`
- `_prune_delivery_idempotency_cache`
- `_prune_session_slots`
- `_record_delivery_recent`
- `_release_dispatch_slot`
- `_remember_delivery_idempotency`
- `_reply_metadata_from_event`
- `_reset_dispatch_controls`
- `_response_metadata_from_event`
- `_safe_remove_task`
- `_serialize_delivery_event`
- `_serialize_inbound_event`
- `_session_slot`
- `_set_delivery_recent_limit`
- `_start_dispatch_typing`
- `_strip_interaction_metadata`
- `_strip_reply_metadata`
- `_target_from_event`
- `_target_from_session_id`
- `_write_delivery_idempotency_persistence_locked`
- `_write_delivery_persistence_locked`
- `_write_inbound_persistence_locked`
- `delivery_diagnostics`
- `dispatcher_diagnostics`
- `get_channel`
- `inbound_diagnostics`
- `recovery_diagnostics`
- `register`
- `request_stop`
- `set_inbound_interceptor`
- `set_recovery_notifier`
- `startup_inbound_replay_status`
- `startup_replay_status`
- `status`
- `_acquire_dispatch_slot` (async)
- `_clear_persisted_dead_letter` (async)
- `_clear_persisted_inbound` (async)
- `_dispatch_event` (async)
- `_dispatch_loop` (async)
- `_dispatch_worker` (async)
- `_handle_stop` (async)
- `_notify_recovery` (async)
- `_on_channel_message` (async)
- `_persist_dead_letter` (async)
- `_persist_pending_inbound` (async)
- `_progress_hook` (async)
- `_publish_and_send` (async)
- `_recover_channel` (async)
- `_recover_channel_detailed` (async)
- `_recovery_loop` (async)
- `_restore_delivery_idempotency_persistence` (async)
- `_restore_persisted_dead_letters` (async)
- `_restore_persisted_inbound` (async)
- `_retry_send` (async)
- `_run_startup_delivery_replay` (async)
- `_run_startup_inbound_replay` (async)
- `_stop_dispatch_typing` (async)
- `_sync_delivery_idempotency_persistence` (async)
- `operator_recover_channels` (async)
- `operator_replay_dead_letters` (async)
- `operator_replay_inbound` (async)
- `replay_dead_letters` (async)
- `run` (async)
- `send` (async)
- `send_outbound` (async)
- `start` (async)
- `start_dispatcher_loop` (async)
- `start_recovery_supervisor` (async)
- `stop` (async)

## Constants

- `_ENGINE_ERROR_FALLBACK_TEXT`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/manager.py`.
- Cross-reference `CONNECTIONS_manager.md` to see how this file fits into the wider system.
