# Telegram Reliability Semantics

This note describes current/expected Telegram delivery behavior for operators.

## 1) Offset commit safety
- Telegram `offset` is advanced only after successful processing (or durable enqueue).
- If failure happens before that point, offset is not committed and redelivery can happen.
- Result: Telegram may redeliver the same update after restart/transient failure.
- Operator expectation: redelivery is normal and not automatically an incident.

## 2) Dedupe behavior
- Duplicate updates (same Telegram update identity) are treated idempotently.
- Dedupe signature is recorded only after successful processing/send for that update.
- Failed processing attempts do not mark dedupe state, so redelivery can reprocess and recover.
- After success, the worker should process at most once and drop subsequent duplicates.
- Dedupe protects against retries, restarts, and long-poll overlap windows.
- Operator expectation: occasional "duplicate ignored" logs are healthy behavior.

## 3) Retry/backoff with jitter
- Transient send/getUpdates failures are retried automatically.
- Backoff increases per attempt and adds jitter to avoid synchronized retry storms.
- On recovery, normal polling/sending resumes without manual action.
- Operator expectation: short bursts of retry logs are acceptable; sustained growth is actionable.

## 4) Auth circuit-breaker behavior
- Repeated auth failures (401/403) open an auth circuit breaker.
- While open, Telegram calls are suppressed for cooldown to reduce provider pressure.
- During cooldown, health can degrade but process remains up.
- Circuit closes after cooldown/probe success or credential correction + reload/reconnect.
- Operator expectation: fix token/config first; avoid tight restart loops.

## 5) Typing keepalive semantics
- Typing keepalive starts after inbound acceptance and runs while processing is in progress.
- Typing keepalive is stopped before outbound send begins.
- `typing_max_ttl_s` caps total keepalive time per inbound to avoid infinite typing loops.
- Typing API auth failures use a dedicated typing auth circuit (`typing_circuit_*`), separate from outbound send auth protection.
- Typing failures are best-effort signals only and must not block outbound message send.

## 6) Formatting/chunk fallback
- If rich formatting is rejected, sender falls back to safer/plain formatting.
- If message size exceeds Telegram limits, payload is chunked into multiple ordered sends.
- If a chunk fails transiently, chunk-level retries follow the same backoff policy.
- Operator expectation: content may lose styling or arrive in parts, but should remain readable.

## 7) Thread/topic semantics (`message_thread_id`)
- Inbound metadata includes `message_thread_id` when Telegram provides it.
- Outbound send supports thread targeting using either metadata (`message_thread_id`) or target format `chat_id:thread_id`.
- Typing keepalive is keyed by `chat_id + thread_id` and sends `send_chat_action` in the same thread context.
- For older Telegram client libraries that do not accept `message_thread_id`, channel send/typing retries gracefully without the thread argument.

## 8) Operational signals
- Channel status may expose Telegram `signals` for runtime reliability diagnostics.
- Current signals include retry counts (`send_retry_count`), retry-after usage (`send_retry_after_count`), auth breaker transitions/state (`*_auth_breaker_*`), typing TTL stop count (`typing_ttl_stop_count`), and reconnect count (`reconnect_count`).
- Breaker transition counters are expected to advance on open->close cycles from both successful probes and natural cooldown expiry; soak tests should show reconnect/retry growth while breaker-open flags return to healthy steady state.
- Operator expectation: treat spikes as transient unless counters/states remain elevated over multiple poll intervals.

## Quick operator checks
- Confirm channel health via `/health` and inspect channel signals via `/v1/diagnostics` (or `clawlite diagnostics`).
- Look for sustained retry escalation, open auth circuit, or repeated final send failures.
- Treat isolated duplicates/chunking/fallback logs as expected reliability mechanisms.
