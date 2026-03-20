# ClawLite Status

Last updated: 2026-03-20

## Summary

ClawLite is a **local-first autonomous agent runtime** in active hardening. Robustness phases 1–7 and the main maintainability plan are complete in the current working tree; remaining work is release polish, packaging/tagging, heavier operational smoke coverage, and the new parity track for Docker, Discord, tools, and skills.

Phase 7 is complete on `main`: `self_evolution` validates fixes fail-closed, proposes patches through the provider directly instead of the full agent loop, rejects unsafe proposals before apply, routes operator notices through the real gateway notice path, commits only inside isolated git worktree branches, and now supports configurable branch prefixes plus Telegram/Discord approval callbacks that persist review state. It remains disabled by default.

The current OpenClaw parity track is active on `main`. The latest slice adds structured approval context for approval-gated tool calls, so gateway/CLI/operator reviews now show exec binary/env keys/cwd plus browser or web host targets instead of only raw argument previews.
That same approval state remains exposed through the gateway/CLI (`tools approvals|approve|reject|revoke-grant`) with exact `tool` / `rule` filters, `exec` approvals understand shell/env/cwd-derived specifiers such as `exec:shell` and `exec:env-key:git-ssh-command`, and skills gained richer local operator visibility through `skills doctor`, `skills managed`, `skills search local_matches`, and the new `skills config` write path for `skills.entries.<skillKey>`. Docker also moved into the next parity slice: the official image now runs rootless as `clawlite`, a `scripts/docker_setup.sh` helper bootstraps build/configure/up, and CI now validates `docker compose config` plus an image build smoke.
The current hardening slice also closes the remaining `plano.md` runtime gaps: `ContextWindowManager` now budgets assistant `tool_calls`, session listing is mtime-sorted, empty frontmatter skill names are flagged in diagnostics, prompt history now has a larger cap with optional semantic trimming and oversized tool-result compaction, OAuth-backed Gemini/Qwen providers can refresh file-backed credentials once on `401`, tool execution supports per-tool timeout overrides, and cron now exposes richer status/list/get/enable/disable control-plane routes plus a cross-process `portalocker` fallback when `fcntl` is unavailable.
The newest follow-up slice tightens the default approval baseline on Telegram/Discord, binds approval review to the original requester when available, keeps actor-bound reviews on the native channel path, requires the configured gateway token across the broader control-plane surface when one exists (status, dashboard state, chat, cron/control mutations, approvals/grants, and gateway WebSocket chat) even on loopback, stamps generic HTTP reviews as `control-plane`, keeps `stream_run()` under the same session-lock discipline during provider-stream cleanup, reuses the same completed-turn persistence path for successful streams while skipping empty assistant rows on provider-error done-chunks, honors mid-stream stop requests without draining the provider to completion, gives the main-turn memory planner a smaller first-pass retrieval probe before widening the same query, batches completed-turn working-memory writes when the backend supports it, moves those deferred sync working-memory writes off the event loop so unrelated sessions stay responsive during background flushes, now also moves the final file-backed transcript append off the event loop while still waiting for the write to finish before the turn returns, moves the remaining blocking tool-loop transcript appends plus file-backed session-history reads off the event loop on compatible session stores, reroutes pre-text tool-call provider streams back through the full engine loop before user-visible output even when the provider emitted only blank whitespace or punctuation-only prelude first, treats Unicode alphanumeric output as real visible text for streamed reroute decisions instead of only ASCII/Latin-1, now also reroutes explicit named skill/tool requests such as `notion` or `web_fetch` through the full `run()` loop instead of staying on the text-only stream path, now also gives streamed turns the same tool-routing guidance prompt that `run()` already uses even when the engine keeps the provider stream open, now also blocks dangerous shell/bootstrap env overrides such as `BASH_ENV`, `ENV`, `PYTHONPATH`, `PERL5OPT`, `JAVA_TOOL_OPTIONS`, and `OPENSSL_CONF`, and extends the shared network safety baseline to explicit carrier-grade NAT, legacy loopback literals, deprecated 6to4 relay space, and metadata-style ranges like `100.64.0.0/10`, `192.88.99.0/24`, and `100.100.100.200` across `exec`, `web_fetch`, `browser`, and `mcp`, now also forwards compact saved-file references for downloaded Telegram media so inbound photo/document/voice turns expose the real local path instead of only a generic placeholder, avoids redundant session-file line recounts between cached transcript writes, redacts raw gateway secrets from authenticated dashboard state handoff payloads, bootstraps the packaged dashboard with a short-lived `#handoff=` credential instead of placing the raw gateway token in the browser URL, consumes that handoff on first successful use inside the running gateway process to block replay, binds each derived dashboard session to a tab-local dashboard client id, keeps that derived dashboard session only in the current tab instead of long-lived `localStorage`, seeds dashboard chat with a per-tab `dashboard:operator:<id>` session by default, fixes the packaged dashboard's manual token-save exchange path so re-auth no longer clears browser auth state on failure, and makes the `message` tool explicit about per-channel capabilities instead of silently overpromising advanced actions.

> **🤖 AI-built · Solo dev** — Every commit is written by Claude (AI), with the author supervising direction. No team.

## Current Baseline

- Latest tag: `v0.7.0-beta.0`
- `main` is ahead of that tag — provider onboarding was expanded with better wizard suggestions and additional OpenAI-compatible providers, and Docker now includes the next parity slice with runtime extras, an optional Redis bus profile, a rootless image, and an official setup helper
- Full suite: `python -m pytest tests/ -q --tb=short` → **1840 passed, 1 skipped**
- Focused runtime slice: `python -m pytest -q tests/runtime/test_autonomy_actions.py tests/gateway/test_server.py tests/runtime/test_self_evolution.py` → **194 passed**
- CI: pytest on Python 3.10 and 3.12, Ruff lint, autonomy contracts, and smoke coverage for YAML CLI config, local-provider probes, quickstart wizard, cron, browser bootstrap hints, and isolated self-evolution branch validation
- Docker: official `Dockerfile`, `docker-compose.yml`, `docs/DOCKER.md`, and `scripts/docker_setup.sh` now ship in-tree; the current parity slice also adds the `runtime` extra, env overrides for the bus backend, an optional Redis compose profile, a rootless `clawlite` image user, and CI smoke for `docker compose config` plus image build
- Discord parity now includes approval callbacks for gated tools plus static/auto presence with native `/discord-presence` operator controls
- Discord parity slice 1 is now in the working tree: DM/guild policy controls, guild/channel/role allowlists, bot gating, explicit session routing, configurable `reply_to_mode`, isolated slash sessions, deferred interaction replies, persisted `/focus` bindings, and automatic idle/max-age expiry for stale Discord bindings

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
- Provider failover, auth/quota suppression, manual recovery from CLI + dashboard
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
| **Discord** | 🟡 Usable — gateway WS, slash commands, buttons, voice messages, webhooks, polls, streaming, embeds, threads, attachments, focus bindings |
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
python -m pytest tests/ -q --tb=short  # 1840 passed, 1 skipped
python -m pytest -q tests/runtime/test_autonomy_actions.py tests/gateway/test_server.py tests/runtime/test_self_evolution.py  # 194 passed
bash scripts/smoke_test.sh  # 7 ok / 0 failure(s)
python -m ruff check --select=E,F,W .  # when ruff is installed
clawlite validate config
```

## Reference Repositories

- Behavioral parity reference: `ref/openclaw`
- Autonomy/reliability reference: `ref/nanobot`

## Next Major Track

- Current slice: Discord policy/routing parity, reply-mode control, isolated slash sessions, persisted `/focus` bindings, and automatic idle/max-age expiry
- Next slice: continue Docker/browser operational parity or return to deeper tools and skills governance

## Delivery Policy

- Commit and push every green slice
- Update docs in the same cycle as behavior changes
- Reserve tags and GitHub releases for the end of a validated milestone
- Keep `CHANGELOG.md` current as work lands on `main`
