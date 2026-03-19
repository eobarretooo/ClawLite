# READ tests/channels/test_manager.py

## Identity

- Path: `tests/channels/test_manager.py`
- Area: `tests`
- Extension: `.py`
- Lines: 1639
- Size bytes: 55902
- SHA1: `0c98c05eaf98c3620f722d2492736734afbd81f6`

## Summary

`tests.channels.test_manager` is a Python module in the `tests` area. It defines 17 class(es), led by `ApprovalEngine`, `ApprovalRegistry`, `BlockingEngine`, `ConcurrentEngine`. It exposes 58 function(s), including `__init__`, `_start_typing_keepalive`, `cancel_session`, `_crash`, `_interceptor`, `_notice`. It depends on 11 import statement target(s).

## Structural Data

- Classes: 17
- Functions: 48
- Async functions: 10
- Constants: 0
- Internal imports: 4
- Imported by: 0
- Matching tests: 0

## Classes

- `ApprovalEngine`
- `ApprovalRegistry`
- `BlockingEngine`
- `ConcurrentEngine`
- `ExceptionEngine`
- `FakeChannel`
- `FakeChannelWithSignals`
- `FakeEngine`
- `FakeTelegramTypingChannel`
- `FlakyNextInboundBus`
- `MessageToolEngine`
- `ProgressEngine`
- `RecoveringChannel`
- `StopAwareEngine`
- `SubagentStub`
- `TypingLifecycleEngine`
- `_Result`

## Functions

- `__init__`
- `_start_typing_keepalive`
- `cancel_session`
- `consume_pending_approval_requests`
- `request_stop`
- `signals`
- `test_channel_manager_appends_tool_approval_notice_metadata`
- `test_channel_manager_default_drops_progress_events`
- `test_channel_manager_delivery_counters_track_success_failure_and_dead_letter`
- `test_channel_manager_delivery_diagnostics_recent_tracks_outcomes_newest_first_and_bounded`
- `test_channel_manager_dispatch_carries_discord_interaction_reply_context`
- `test_channel_manager_dispatch_concurrency_bound`
- `test_channel_manager_dispatch_honors_discord_reply_to_mode_first`
- `test_channel_manager_dispatch_honors_discord_reply_to_mode_off`
- `test_channel_manager_dispatch_loop_recovers_after_next_inbound_exception`
- `test_channel_manager_dispatch_preserves_telegram_thread_target`
- `test_channel_manager_dispatch_uses_discord_channel_id_and_reply_metadata`
- `test_channel_manager_dispatcher_diagnostics_and_restart_loop`
- `test_channel_manager_dispatches_inbound_to_engine_and_send`
- `test_channel_manager_inbound_interceptor_can_short_circuit_bus_publish`
- `test_channel_manager_keeps_discord_typing_active_for_full_dispatch`
- `test_channel_manager_keeps_telegram_typing_active_for_full_dispatch`
- `test_channel_manager_operator_recover_channels_recovers_failed_worker`
- `test_channel_manager_operator_replay_inbound_tracks_manual_status`
- `test_channel_manager_operator_replay_tracks_manual_replay_status`
- `test_channel_manager_progress_delivery_policy`
- `test_channel_manager_recovers_failed_channel_worker_and_notifies`
- `test_channel_manager_recovery_diagnostics_and_restart_loop`
- `test_channel_manager_replay_dead_letters_updates_replay_counters`
- `test_channel_manager_retries_and_dead_letters_failed_send`
- `test_channel_manager_send_outbound_parses_telegram_private_thread_session`
- `test_channel_manager_send_outbound_uses_session_routing`
- `test_channel_manager_sends_fallback_when_engine_raises`
- `test_channel_manager_session_slots_are_bounded_and_cleanup_idle_entries`
- `test_channel_manager_startup_replays_persisted_dead_letters_after_restart`
- `test_channel_manager_startup_replays_persisted_inbound_after_restart`
- `test_channel_manager_startup_suppresses_duplicate_dead_letter_replay_with_persisted_idempotency`
- `test_channel_manager_status_includes_channel_specific_signals`
- `test_channel_manager_stop_is_responsive_when_slots_saturated`
- `test_channel_manager_stop_preserves_telegram_thread_target`
- `test_channel_manager_stop_reports_subagent_cancellations`
- `test_channel_manager_suppresses_duplicate_outbound_with_explicit_idempotency_key`
- `test_channel_manager_suppresses_final_reply_after_tool_message_same_target`
- `test_channel_manager_target_from_session_id_parses_discord_dm_format`
- `test_channel_manager_target_from_session_id_parses_discord_guild_format`
- `test_channel_manager_target_from_session_id_parses_discord_guild_slash_format`
- `test_channel_manager_target_from_session_id_parses_telegram_private_thread_format`
- `test_channel_manager_target_from_session_id_parses_telegram_topic_format`
- `_crash` (async)
- `_interceptor` (async)
- `_notice` (async)
- `_scenario` (async)
- `_stop_typing_keepalive` (async)
- `next_inbound` (async)
- `run` (async)
- `send` (async)
- `start` (async)
- `stop` (async)

## Notable String Markers

- `test_channel_manager_appends_tool_approval_notice_metadata`
- `test_channel_manager_default_drops_progress_events`
- `test_channel_manager_delivery_counters_track_success_failure_and_dead_letter`
- `test_channel_manager_delivery_diagnostics_recent_tracks_outcomes_newest_first_and_bounded`
- `test_channel_manager_dispatch_carries_discord_interaction_reply_context`
- `test_channel_manager_dispatch_concurrency_bound`
- `test_channel_manager_dispatch_honors_discord_reply_to_mode_first`
- `test_channel_manager_dispatch_honors_discord_reply_to_mode_off`
- `test_channel_manager_dispatch_loop_recovers_after_next_inbound_exception`
- `test_channel_manager_dispatch_preserves_telegram_thread_target`
- `test_channel_manager_dispatch_uses_discord_channel_id_and_reply_metadata`
- `test_channel_manager_dispatcher_diagnostics_and_restart_loop`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/channels/test_manager.py`.
- Cross-reference `CONNECTIONS_test_manager.md` to see how this file fits into the wider system.
