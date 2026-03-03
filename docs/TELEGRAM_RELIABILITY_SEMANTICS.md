# Telegram Reliability Semantics

This note describes current/expected Telegram delivery behavior for operators.

## 1) Offset commit safety
- Telegram `offset` is advanced only after successful processing (or durable enqueue).
- If failure happens before that point, offset is not committed and redelivery can happen.
- Result: Telegram may redeliver the same update after restart/transient failure.
- Operator expectation: redelivery is normal and not automatically an incident.

## 2) Dedupe behavior
- Duplicate updates (same Telegram update identity) are treated idempotently.
- The worker should process at most once and drop subsequent duplicates.
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

## Quick operator checks
- Confirm channel health via `/api/channels/status`.
- Look for sustained retry escalation, open auth circuit, or repeated final send failures.
- Treat isolated duplicates/chunking/fallback logs as expected reliability mechanisms.
