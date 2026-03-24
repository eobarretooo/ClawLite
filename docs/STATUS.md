# ClawLite Status

Last updated: 2026-03-23

## Summary

ClawLite is a **local-first autonomous agent runtime** in active hardening. Robustness phases 1–7 and the main maintainability plan are complete in the current working tree; remaining work is release polish, packaging/tagging, heavier operational smoke coverage, and the new parity track for Docker, Discord, tools, and skills.

Phase 7 is complete on `main`: `self_evolution` validates fixes fail-closed, proposes patches through the provider directly instead of the full agent loop, rejects unsafe proposals before apply, routes operator notices through the real gateway notice path, commits only inside isolated git worktree branches, and now supports configurable branch prefixes, autonomy-session canary gating, plus Telegram/Discord approval callbacks that persist review state. It remains disabled by default.

The current OpenClaw parity track is active on `main`. The latest slices harden Discord runtime health again, so Discord auto-presence now sends through the websocket captured for that cycle, clears stale channel error state after a successful refresh, the heartbeat loop closes half-open gateway sockets after a missed ACK, the gateway times out stalled `READY` / `RESUMED` handshakes, `operator_status()` exposes that pending lifecycle state directly, both the dashboard and `/discord-status` now surface that wait state without requiring raw JSON inspection, automatic/manual presence pushes now wait for the current gateway handshake to complete instead of racing a fresh reconnect, reconnect backoff/attempt state is now visible while the gateway is actively recovering, and the operator surfaces now also expose the last connect/ready/disconnect timestamps plus the latest lifecycle outcome so Discord recovery can be diagnosed without raw logs. The current gateway/API slice now adds baseline request correlation across both HTTP and WebSocket surfaces: every HTTP response carries `X-Request-ID`, HTTP error envelopes echo `request_id`, unhandled `500` responses now keep that correlation path intact, gateway WebSocket sessions expose an additive `connection_id` plus last-connection/request/error hints in diagnostics, the packaged dashboard reuses a compact `ws` summary in `dashboard/state` to surface recent gateway WebSocket connects/errors directly in the operator event feed, the dashboard's HTTP/control-plane actions now also append the returned request id in their local event-feed entries, and HTTP diagnostics/logging now keep the latest request and the latest failing request correlated by `request_id`, method, path, status, and error code.
The newest follow-up slice now also surfaces those correlated HTTP diagnostics inside the packaged dashboard itself: the local operator event feed watches `diagnostics.http.last_error_*` and records a dedicated `Gateway HTTP error observed` entry with method, path, status, and the same `request_id`, so control-plane failures no longer require raw diagnostics JSON or log inspection to find the right request handle.
The newest dashboard follow-up now adds a compact `HTTP Correlation` card in the runtime tab itself, showing the latest correlated HTTP request plus the latest correlated HTTP failure with method, path, status, timestamp, and `request_id`, so operators do not have to reconstruct that summary from the scrolling feed alone.
The newest overview follow-up now reuses those same correlated HTTP and websocket diagnostics in a stable `Control-Plane Correlation` card on the main dashboard tab, surfacing the latest request, failure, connection, and socket error summary without forcing operators to switch over to Runtime or inspect raw JSON payloads.
The newest skills follow-up now turns `Skills Inventory` into an operator summary instead of only a raw JSON dump: the Knowledge tab now renders compact cards for availability/runnable coverage, always-on blockers, source mix, missing requirements, contract issues, and watcher health directly from `skills.diagnostics_report()`.
The newest skills follow-up now also makes that card actionable: the Knowledge tab surfaces the first blocked skills with remediation hints and adds a dedicated `Refresh skills inventory` control backed by an explicit live `POST /v1/control/skills/refresh` path instead of forcing operators back through the generic supervisor recovery surface. The same first-class refresh path is now also available from CLI via `clawlite skills refresh`.
The newest skills follow-up now also adds a first-class `skills doctor` control path in the runtime itself: `POST /v1/control/skills/doctor` and `POST /api/skills/doctor` now expose the same actionable blocker report as the CLI, and the Knowledge tab can trigger that live diagnosis directly through a `Doctor blocked skills` action instead of relying only on static summary cards. That doctor/refresh path now also respects the explicitly selected config path/profile consistently across CLI startup/runtime flows instead of silently falling back to the default config file.
The newest skills follow-up now also adds a first-class `skills validate` path across runtime, CLI, and dashboard: `POST /v1/control/skills/validate`, `POST /api/skills/validate`, `clawlite skills validate`, and the new `Validate skills inventory` dashboard action now combine live discovery refresh with the same actionable blocked-skills report in one operator step instead of forcing refresh and diagnosis to stay separate.
The newest Docker follow-up now tightens the setup helper itself: `scripts/docker_setup.sh` now waits for the compose gateway healthcheck to become healthy before finishing, exposes `CLAWLITE_DOCKER_WAIT_TIMEOUT`, and prints recent gateway logs on timeout so Docker startup failures are easier to diagnose without manual `docker inspect` / `docker compose logs` loops.
The newest Docker follow-up now also deepens that preflight path into a real Compose/runtime diagnostic: `clawlite validate preflight --docker` now summarizes the detected runtime stack, fails closed when the stack is present without a healthy `clawlite-gateway`, and also catches unhealthy runtime dependencies such as `redis`; `scripts/release_preflight.sh --docker` keeps forwarding that same optional deployment check.
The newest Docker follow-up now also adds image-level `HEALTHCHECK` logic to the official container itself: it only probes `/health` when PID 1 is actually running `clawlite gateway`, while the compose `clawlite-cli` sidecar still disables that inherited healthcheck explicitly so one-off CLI containers stay out of the health contract entirely.
The newest Docker follow-up now also adds first-class env-file ergonomics for Compose: `CLAWLITE_DOCKER_ENV_FILE` is now honored by both `scripts/docker_setup.sh` and `clawlite validate preflight --docker`, missing env files fail closed, and the repo now ships a `docker-compose.env.example` template for Docker-specific overrides without relying on ad-hoc shell exports.
The newest Docker follow-up now also makes provider/runtime secret pass-through explicit in the Compose layer itself: the shared service environment now forwards the current model/base-url/api-key overrides, gateway auth overrides, common provider API keys, and the existing Codex/Gemini auth envs, while `docker-compose.env.example` documents that same curated surface instead of leaving Docker operators to guess which env names actually reach the container.
The newest Docker follow-up now also makes `clawlite validate preflight --docker` more guided about secrets in that Docker launch context: it reports which provider auth envs are currently satisfied by the shell or `CLAWLITE_DOCKER_ENV_FILE`, emits concrete hints when the active model still lacks a Docker-side key/token, and now fails closed earlier when Docker runtime auth is explicitly `required` but no `CLAWLITE_GATEWAY_AUTH_TOKEN` is available.
The earlier approval state remains exposed through the gateway/CLI (`tools approvals|approve|reject|revoke-grant`) with exact `tool` / `rule` filters, `exec` approvals understand shell/env/cwd-derived specifiers such as `exec:shell` and `exec:env-key:git-ssh-command`, and skills gained richer local operator visibility through `skills doctor`, `skills managed`, `skills search local_matches`, and the new `skills config` write path for `skills.entries.<skillKey>`. Docker also moved into the next parity slice: the official image now runs rootless as `clawlite`, a `scripts/docker_setup.sh` helper bootstraps build/configure/up, and CI now validates `docker compose config` plus an image build smoke.
The current hardening slice also closes the remaining `plano.md` runtime gaps: `ContextWindowManager` now budgets assistant `tool_calls`, session listing is mtime-sorted, empty frontmatter skill names are flagged in diagnostics, prompt history now has a larger cap with optional semantic trimming and oversized tool-result compaction, OAuth-backed Gemini/Qwen providers can refresh file-backed credentials once on `401`, tool execution supports per-tool timeout overrides, and cron now exposes richer status/list/get/enable/disable control-plane routes plus a cross-process `portalocker` fallback when `fcntl` is unavailable.
The newest follow-up slice tightens the default approval baseline on Telegram/Discord, binds approval review to the original requester when available, keeps actor-bound reviews on the native channel path, requires the configured gateway token across the broader control-plane surface when one exists (status, dashboard state, chat, cron/control mutations, approvals/grants, and gateway WebSocket chat) even on loopback, stamps generic HTTP reviews as `control-plane`, keeps `stream_run()` under the same session-lock discipline during provider-stream cleanup, reuses the same completed-turn persistence path for successful streams while skipping empty assistant rows on provider-error done-chunks, honors mid-stream stop requests without draining the provider to completion, gives the main-turn memory planner a smaller first-pass retrieval probe before widening the same query, batches completed-turn working-memory writes when the backend supports it, moves those deferred sync working-memory writes off the event loop so unrelated sessions stay responsive during background flushes, now also moves the final file-backed transcript append off the event loop while still waiting for the write to finish before the turn returns, moves the remaining blocking tool-loop transcript appends plus file-backed session-history reads off the event loop on compatible session stores, reroutes pre-text tool-call provider streams back through the full engine loop before user-visible output even when the provider emitted only blank whitespace or punctuation-only prelude first, treats Unicode alphanumeric output as real visible text for streamed reroute decisions instead of only ASCII/Latin-1, now also reroutes explicit named skill/tool requests such as `notion` or `web_fetch` through the full `run()` loop instead of staying on the text-only stream path, now also gives streamed turns the same tool-routing guidance prompt that `run()` already uses even when the engine keeps the provider stream open, now also blocks dangerous shell/bootstrap env overrides such as `BASH_ENV`, `ENV`, `PYTHONPATH`, `PERL5OPT`, `JAVA_TOOL_OPTIONS`, and `OPENSSL_CONF`, extends the shared network safety baseline to explicit carrier-grade NAT, legacy loopback literals, deprecated 6to4 relay space, and metadata-style ranges like `100.64.0.0/10`, `192.88.99.0/24`, and `100.100.100.200` across `exec`, `web_fetch`, `browser`, and `mcp`, now also forwards compact saved-file references for downloaded Telegram media so inbound photo/document/voice turns expose the real local path instead of only a generic placeholder, now also attempts compact OCR/PDF/text extraction for downloaded Telegram photo/document items when local dependencies allow it, and now also lets the `pgvector` memory backend keep its real `vector` column path while attempting a best-effort ANN cosine index (`hnsw` first, `ivfflat` fallback) with additive diagnostics instead of failing initialization outright when index creation is unavailable, avoids redundant session-file line recounts between cached transcript writes, redacts raw gateway secrets from authenticated dashboard state handoff payloads, bootstraps the packaged dashboard with a short-lived `#handoff=` credential instead of placing the raw gateway token in the browser URL, consumes that handoff on first successful use inside the running gateway process to block replay, binds each derived dashboard session to a tab-local dashboard client id, keeps that derived dashboard session only in the current tab instead of long-lived `localStorage`, seeds dashboard chat with a per-tab `dashboard:operator:<id>` session by default, fixes the packaged dashboard's manual token-save exchange path so re-auth no longer clears browser auth state on failure, and makes the `message` tool explicit about per-channel capabilities instead of silently overpromising advanced actions.

> **🤖 AI-built · Solo dev** — Every commit is written by Claude (AI), with the author supervising direction. No team.

## Current Baseline

- Latest tag: `v0.7.0-beta.0`
- `main` is ahead of that tag — provider onboarding was expanded with better wizard suggestions and additional OpenAI-compatible providers, and Docker now includes the next parity slice with runtime extras, an optional Redis bus profile, a rootless image, and an official setup helper
- Full suite: `python -m pytest tests/ -q --tb=short` → **1990 passed, 1 skipped**
- Focused runtime slice: `python -m pytest -q tests/runtime/test_autonomy_actions.py tests/gateway/test_server.py tests/runtime/test_self_evolution.py` → **194 passed**
- CI: pytest on Python 3.10 and 3.12, Ruff lint, autonomy contracts, and smoke coverage for YAML CLI config, local-provider probes, quickstart wizard, cron, browser bootstrap hints, and isolated self-evolution branch validation
- Docker: official `Dockerfile`, `docker-compose.yml`, `docs/DOCKER.md`, and `scripts/docker_setup.sh` now ship in-tree; the current parity slice also adds the `runtime` extra, env overrides for the bus backend, an optional Redis compose profile, a rootless `clawlite` image user, CI smoke for `docker compose config` plus image build, and a browser-enabled image gate that verifies Playwright + Chromium are baked into the container
- Discord parity now includes approval callbacks for gated tools plus static/auto presence with native `/discord-presence` operator controls
- Discord parity slice 1 is now in the working tree: DM/guild policy controls, guild/channel/role allowlists, bot gating, explicit session routing, configurable `reply_to_mode`, isolated slash sessions, deferred interaction replies, persisted `/focus` bindings, and automatic idle/max-age expiry for stale Discord bindings
- Discord parity now also routes `MODAL_SUBMIT` interactions as inbound turns with compact field text plus allowlisted `modal_field_ids` / `modal_field_labels` runtime hints
- Discord parity now also supports outbound `discord_modal` trigger buttons that open native Discord text-input forms and keep the trigger click out of the agent loop
- Discord embeds now normalize stats-style field `inline` flags and embed `timestamp` values before POST/PATCH calls, so operator/status embeds render with the expected layout and UTC-aware time payloads.
- Discord webhook execution now also accepts `thread_id`, plus `thread_name` and `applied_tags` for forum/media thread creation, reuses embed normalization, clamps outbound component rows to Discord's five-row limit, and opts into `with_components=true` when outbound components are present.
- Discord `send()` now also accepts `metadata["discord_voice"]`, so channel and DM sends can route native voice-note payloads through the same outbound path instead of requiring a separate direct call to `send_voice_message()`.
- Discord `discord_voice` metadata now also accepts local `audio_path` / `path`, so saved OGG files can be sent directly without pre-encoding them to bytes/base64 first while missing files fail closed.
- Discord voice-message uploads now also reuse the adapter's normal `429` / `Retry-After` retry handling for attachment reservation and CDN upload, hardening the native voice-note send path under rate limits.
- Discord inbound audio/voice attachments can now reuse the same Groq-compatible transcription path as Telegram, appending compact transcription lines to inbound turns and exposing transcription counters in operator status.
- Discord interaction replies now route ephemeral responses through the follow-up webhook path, so operator/status replies and explicit `discord_ephemeral` sends use a valid `flags=64` delivery path instead of relying on a late `@original` edit.
- Discord now also caches `application_id` from interaction payloads and propagates it through dispatch metadata, so interaction replies can still use the webhook response path even when the runtime has not learned the app id from a prior `READY` event.
- Discord now also ACKs built-in operator slash commands and approval/self-evolution button interactions as ephemeral deferred responses, avoiding a public deferred placeholder before the eventual private follow-up.
- Discord interaction sends can now opt into an explicit follow-up message via `metadata["discord_followup"]`, so runtime callers can post an additional interaction response without always editing the original deferred message.
- Discord voice sends now also reuse the source interaction `message_id` as a reply reference when available and fail closed for unsupported `discord_ephemeral` / `discord_followup` voice-response combinations.
- Discord voice sends now also fail closed for mixed text/embed/component/webhook/modal/poll payloads, instead of silently dropping unsupported extra outbound context when `discord_voice` is present.
- Discord voice sends now also require OGG/Opus audio plus a positive duration before the adapter will attempt a native voice-note upload, instead of blindly relabeling arbitrary audio bytes as `voice-message.ogg`.
- Discord interaction follow-up sends now also append `with_components=true` automatically whenever component rows are present, keeping component-bearing follow-ups aligned with the main Discord webhook send path.
- Discord `discord_voice.silent` now also parses string-style booleans like `"true"` / `"false"` correctly, so operator/skill metadata no longer flips silent voice-note delivery on by accident.
- Discord voice sends now also validate explicit `waveform` values as base64 that decodes to exactly 256 samples, so malformed waveform strings fail fast instead of reaching Discord's voice-note API.
- Discord automatic voice-waveform generation now also falls back cleanly to the placeholder waveform when temporary-file setup fails early, instead of leaking a cleanup-time local-variable error.
- Discord's direct `send_voice_message(...)` helper now also normalizes string-style `silent` values like `"true"` / `"false"` before setting the suppress-notifications bit, keeping direct helper calls aligned with the metadata-driven voice path.
- Discord's direct `send_voice_message(...)` helper now also treats unrecognized string-style `silent` values fail-closed as non-silent, so garbage values no longer flip on suppress-notifications by accident.
- Discord's direct `send_voice_message(...)` helper now also strips surrounding whitespace from `channel_id` / `reply_to_message_id` and rejects blank direct `channel_id` values, keeping helper-only voice sends aligned with the safer metadata path.
- Discord's direct `send_voice_message(...)` helper now also requires a non-empty `upload_filename` from Discord's attachment reservation response, so voice uploads fail fast before the final POST if the reservation payload is incomplete.
- Discord's direct `send_voice_message(...)` helper now also fails closed when Discord omits the attachment row entirely and clears any stale `_last_error` latch after a successful voice-note send, so recovered uploads stop reporting the channel as degraded.
- Discord auto-presence now also sends through the websocket captured for that refresh cycle, clears stale channel error state after successful presence recovery, and closes half-open gateway sockets when a heartbeat ACK is missed so the normal reconnect path can restore transport health automatically.
- Discord gateway startup/resume now also starts a bounded `READY` / `RESUMED` watchdog after `HELLO`, forcing stalled handshakes back through the reconnect path instead of leaving the transport superficially connected forever.
- Discord `operator_status()` now also reports additive lifecycle fields for the pending session watchdog (`gateway_session_task_state`, `gateway_session_waiting_for`), making stalled `READY` / `RESUMED` handshakes visible to operator and dashboard surfaces before a manual refresh is needed.
- Discord dashboard cards and `/discord-status` now also surface that pending `READY` / `RESUMED` handshake explicitly, so operators can see startup/reconnect stalls without reading raw dashboard JSON.
- Discord auto-presence and manual `/discord-presence-refresh` now also wait for the current gateway handshake to complete before sending `op 3`, preventing reconnect/startup races from pushing presence updates onto sockets that have not finished `READY` / `RESUMED` yet.
- Discord `operator_status()`, `/discord-status`, the dashboard, and the documented Discord refresh response now also expose active reconnect/backoff state (`gateway_reconnect_attempt`, `gateway_reconnect_retry_in_s`, `gateway_reconnect_state`), so operators can tell “backing off” from “retrying now” without inferring it from stale errors alone.
- Discord `operator_status()`, `/discord-status`, the dashboard, and the documented Discord refresh response now also expose lifecycle history fields (`gateway_last_connect_at`, `gateway_last_ready_at`, `gateway_last_disconnect_at`, `gateway_last_disconnect_reason`, `gateway_last_lifecycle_outcome`, `gateway_last_lifecycle_at`), so operators can see the last healthy Discord session and the most recent disconnect cause without leaving the control-plane surfaces.
- Gateway HTTP responses now also carry `X-Request-ID`, while HTTP error envelopes echo `request_id` and even unhandled `500` responses preserve that same correlation id, giving operators a baseline request-correlation path before full tracing/OTEL lands.
- Gateway WebSocket `connect.challenge` events now also expose an additive `connection_id`, while diagnostics `ws` telemetry now tracks the latest connection open/close ids, timestamps, path, last observed request id, and the last WS error's request/connection context so operators can correlate live sockets without changing the rest of the WS frame contract.
- The packaged dashboard now also receives a compact `ws` snapshot through `GET /api/dashboard/state` and uses it to surface recent gateway WebSocket connects/errors in the local event feed with the same connection/request correlation hints instead of relying only on raw diagnostics JSON.
- The packaged dashboard now also carries HTTP `X-Request-ID` correlation into manual chat/control-plane event entries, so operator-triggered heartbeat/recovery/pairing/memory actions expose the same request handle without leaving the local event feed.
- HTTP diagnostics now also expose `last_request_*` plus `last_error_*` correlation fields, and gateway HTTP error logs now include `request_id`, method, path, and status so operators can tie a failing control-plane request back to the same request handle without full tracing.
- The packaged dashboard now also watches `diagnostics.http.last_error_*` and mirrors new gateway HTTP failures into the local event feed with method/path/status plus `request_id`, so recent control-plane errors are visible without expanding raw diagnostics JSON.
- The packaged dashboard runtime tab now also renders a compact `HTTP Correlation` card from `diagnostics.http.last_request_*` and `last_error_*`, so operators can see the last correlated request and failure summary without reading raw JSON or relying only on the event feed.
- The packaged dashboard overview tab now also renders a compact `Control-Plane Correlation` card from `diagnostics.http.*` and `diagnostics.ws.*`, so operators can see the latest correlated HTTP and websocket request/failure summary without leaving the main control-plane view.
- The packaged dashboard Knowledge tab now also renders a compact `Skills Inventory` summary from `skills.diagnostics_report()`, surfacing availability/runnable coverage, blockers, requirement gaps, contract issues, and watcher health without relying only on the raw JSON preview.
- The packaged dashboard Knowledge tab now also surfaces the first blocked skills with remediation hints and adds a dedicated `Refresh skills inventory` control backed by `POST /v1/control/skills/refresh`, and that same first-class path is now exposed in CLI as `clawlite skills refresh`.
- Skills remediation now also has a first-class live `doctor` path through `POST /v1/control/skills/doctor` / `POST /api/skills/doctor`, and the packaged dashboard Knowledge tab can trigger the same blocked-skills diagnosis directly through `Doctor blocked skills`.
- Skills remediation now also has a first-class live `validate` path through `POST /v1/control/skills/validate` / `POST /api/skills/validate`, `clawlite skills validate`, and the packaged dashboard `Validate skills inventory` action, combining refresh plus actionable diagnosis in one operator step.
- Skills remediation now also has a first-class live `doctor` path through `POST /v1/control/skills/doctor` plus `POST /api/skills/doctor`, and the packaged dashboard Knowledge tab can trigger that same blocker diagnosis directly through `Doctor blocked skills`; those doctor/refresh paths now also honor the explicitly selected config path/profile instead of silently falling back to the default config file.
- Discord `send()` now also accepts `metadata["discord_webhook"]`, routing normal outbound messages through Discord webhooks with the same embed normalization, component row clamp, optional thread targeting, and forum/media thread creation metadata already used by the lower-level webhook helper.
- Discord deferred interaction replies now also stream through the native `@original` response path when the manager uses `stream_run()`, so streamed slash/component turns no longer need a second non-streamed channel send.
- Discord deferred `@original` edits and interaction follow-up webhook sends now also reuse the adapter's normal `429` / `Retry-After` retry handling, hardening the live interaction reply path under Discord rate limits.
- Gateway chat surfaces now have in-memory fixed-window rate limiting on HTTP and WebSocket paths with `429 + Retry-After` and shared `/v1/chat` / `/api/message` bucketing.
- `self_evolution` can now stay disabled globally or run in a session-canary mode through `gateway.autonomy.self_evolution_enabled_for_sessions`, while manual forced triggers still work for operator validation.
- memory quality snapshots now include a compact `trend` block derived from bounded history, so CLI/dashboard/diagnostics can show direction and streaks without recomputing client-side.
- the current validation-hardening slice also removes an unnecessary executor hop from Telegram inbound media directory creation, keeps Telegram media OCR/PDF regressions hermetic in the test harness, and gives `clawlite memory suggest` a synchronous scan path for local CLI snapshots so sandboxed validation no longer stalls on `asyncio.to_thread(...)` for empty/local stores.

## Robustness Milestone Progress

| Phase | Commit | What landed |
|-------|--------|-------------|
| 1 — Config + Bus | `8dd97a9` | `ConfigWatcher` hot-reload, `BusJournal` SQLite, typed envelopes (`InboundEvent`/`OutboundEvent`) |
| 2 — Memory | `bf671ab` | Memory hierarchy, `ProactiveContextLoader`, LLM consolidation, TTL, file ingest |
| 3 — Providers + Tools | `8455a59` | `TelemetryRegistry`, streaming recovery, tool timeout middleware, `ToolResultCache`, health checks |
| 4 — Core + Jobs | `d91a585` | `ContextWindowManager`, `JobQueue` + `JobJournal`, `JobsTool`, `JobsConfig`, loop-detection bus events, subagent `parent_session_id` |
| 5 — Runtime Recovery | `e8ddaf1` | `JobQueue.worker_status()`, job workers startup + supervisor, `job_workers` lifecycle component, `autonomy_stuck` detection (consecutive errors / no-progress streak) |
| 6 — Skills + Subagents | `2e0009c` | Skill `fallback_hint` + `version_pin` lifecycle controls; `SubagentManager` orchestration depth guard (`max_orchestration_depth`); `SpawnTool` parent session propagation; CLI `skills pin-version` / `clear-version` |
| 7 — Advanced memory + self-improvement | completed | Restricted provider-direct proposal path, pre-apply proposal policy, isolated git worktree branches, configurable branch prefixes, Telegram/Discord approval callbacks, disabled by default |

## What Is Complete

### Core Runtime
- FastAPI gateway (HTTP + WebSocket) on `:8787`
- Operator dashboard (packaged HTML/CSS/JS) with live chat, event feed, autorefresh
- Agent engine with `stream_run()` / `ProviderChunk` streaming support
- Per-subsystem startup timeouts, so stalled channels stop failing the whole gateway startup path
- Provider failover, auth/quota suppression, health-scored fallback ordering, manual recovery from CLI + dashboard
- Heartbeat supervisor with recovery telemetry and timezone-aware scheduling
- Cron engine (persistent, replay-safe) with dashboard visibility
- Autonomy wake coordinator — manual and scheduled wakes
- Dead-letter queue + inbound journal replay (automated and operator-triggered)
- Subagent lifecycle, orchestration, context isolation

### Memory
- Hybrid BM25 + vector similarity search
- SQLite (local) and pgvector (Postgres) backends
- FTS5 full-text indexing, temporal decay, salience scoring
- Consolidation loop (episodic → knowledge)
- Snapshot / rollback with control-plane confirmation
- Memory suggestions refresh from dashboard
- Main responsibilities split across dedicated modules (`memory_search`, `memory_retrieval`, `memory_workflows`, `memory_api`, `memory_policy`, `memory_reporting`, `memory_versions`, `memory_quality`)

### Channels
| Channel | Status |
|---------|--------|
| **Telegram** | ✅ Complete — polling + webhook, reactions, topics, reply keyboards, streaming, offset safety, pairing, dedupe, circuit breaker |
| **Discord** | 🟡 Usable — gateway WS, slash commands, buttons/selects/modals, voice messages, voice/audio transcription, webhooks, polls, streaming, embeds, threads, attachments, focus bindings |
| **Email** | 🟡 Usable — IMAP inbound + SMTP outbound |
| **WhatsApp** | 🟡 Usable — webhook inbound, outbound retry, bridge typing keepalive |
| **Slack** | 🟡 Usable — Socket Mode inbound, outbound retry, reversible working indicator |
| **IRC** | 🟡 Minimal — asyncio transport with JOIN, PING/PONG, PRIVMSG |

### Tools (18+)
`files` · `exec` · `spawn` · `process` · `web` · `browser` (Playwright)
`pdf` · `tts` · `mcp` · `sessions` · `cron` · `memory` · `skill`
`message` · `agents` · `discord_admin` · `apply_patch` · `jobs`

### Skills (25+)
`web-search` · `cron` · `memory` · `coding-agent` · `summarize`
`github-issues` · `notion` · `obsidian` · `spotify` · `docker`
`jira` · `linear` · `trello` · `1password` · `apple-notes`
`weather` · `tmux` · `model-usage` · `session-logs` · `skill-creator`
`github` · `gh-issues` · `healthcheck` · `clawhub` · `hub`

### Config
- Full Pydantic v2 schema (`clawlite/config/schema.py`)
- Interactive wizard: `clawlite configure --flow quickstart`
- Full field reference: [`docs/CONFIGURATION.md`](CONFIGURATION.md)

### Maintainability
- Gateway request/status/websocket/control surfaces are split across dedicated modules instead of one monolith
- `clawlite/gateway/server.py` is down to roughly 3.3k lines, and `clawlite/core/memory.py` to roughly 4.4k lines
- Telegram remains large but already routes transport, delivery, inbound, status, dedupe, and offset logic through dedicated modules

### Workspace Templates
`AGENTS.md` · `IDENTITY.md` · `SOUL.md` · `HEARTBEAT.md` · `USER.md`

## Validation

```bash
python -m pytest tests/ -q --tb=short  # 1990 passed, 1 skipped
python -m pytest -q tests/runtime/test_autonomy_actions.py tests/gateway/test_server.py tests/runtime/test_self_evolution.py  # 194 passed
bash scripts/smoke_test.sh  # 7 ok / 0 failure(s)
python -m ruff check --select=E,F,W .  # when ruff is installed
clawlite validate config
```

## Reference Repositories

- Behavioral parity reference: `ref/openclaw`
- Autonomy/reliability reference: `ref/nanobot`

## Next Major Track

- Current slice: Docker deployment now also gives `clawlite validate preflight --docker` guided provider/gateway secret hints for the effective Compose env context, including fail-closed handling when required gateway auth is missing a token
- Next slice: keep pushing Docker/Deployment maturity with a small follow-up such as richer live Docker validation once a daemon is available, or broader provider/runtime secret diagnostics beyond the current curated Docker env surface

## Delivery Policy

- Commit and push every green slice
- Update docs in the same cycle as behavior changes
- Reserve tags and GitHub releases for the end of a validated milestone
- Keep `CHANGELOG.md` current as work lands on `main`
