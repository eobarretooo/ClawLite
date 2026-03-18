# ClawLite Status

Last updated: 2026-03-18

## Summary

ClawLite is a **local-first autonomous agent runtime** in active hardening. Robustness phases 1–7 and the main maintainability plan are complete in the current working tree; remaining work is release polish, packaging/tagging, heavier operational smoke coverage, and the new parity track for Docker, Discord, tools, and skills.

Phase 7 is complete on `main`: `self_evolution` validates fixes fail-closed, proposes patches through the provider directly instead of the full agent loop, rejects unsafe proposals before apply, routes operator notices through the real gateway notice path, commits only inside isolated git worktree branches, and now supports configurable branch prefixes plus Telegram/Discord approval callbacks that persist review state. It remains disabled by default.

The current OpenClaw parity track is active on `main`. The latest slice adds interactive Telegram/Discord approval controls for approval-gated tool calls, backed by temporary request-bound grants instead of silent auto-resume.
That same approval state is now exposed through the gateway/CLI (`tools approvals|approve|reject|revoke-grant`), `exec` approvals now understand shell/env/cwd-derived specifiers such as `exec:shell` and `exec:env-key:git-ssh-command`, and skills gained a `skills doctor` operator view with remediation hints plus `--status` / `--source` triage filters.

> **🤖 AI-built · Solo dev** — Every commit is written by Claude (AI), with the author supervising direction. No team.

## Current Baseline

- Latest tag: `v0.7.0-beta.0`
- `main` is ahead of that tag — provider onboarding was expanded with better wizard suggestions and additional OpenAI-compatible providers, and Docker now includes the next parity slice with runtime extras plus an optional Redis bus profile
- Full suite: `python -m pytest tests/ -q --tb=short` → **1561 passed, 1 skipped**
- Focused runtime slice: `python -m pytest -q tests/runtime/test_autonomy_actions.py tests/gateway/test_server.py tests/runtime/test_self_evolution.py` → **190 passed**
- CI: pytest on Python 3.10 and 3.12, Ruff lint, autonomy contracts, and smoke coverage for YAML CLI config, local-provider probes, quickstart wizard, cron, browser bootstrap hints, and isolated self-evolution branch validation
- Docker: official `Dockerfile`, `docker-compose.yml`, and `docs/DOCKER.md` now ship in-tree; the current parity slice also adds the `runtime` extra, env overrides for the bus backend, and an optional Redis compose profile
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
python -m pytest tests/ -q --tb=short  # 1561 passed, 1 skipped
python -m pytest -q tests/runtime/test_autonomy_actions.py tests/gateway/test_server.py tests/runtime/test_self_evolution.py  # 190 passed
bash scripts/smoke_test.sh  # 7 ok / 0 failure(s)
python -m ruff check --select=E,F,W .  # when ruff is installed
clawlite validate config
```

## Reference Repositories

- Behavioral parity reference: `ref/openclaw`
- Autonomy/reliability reference: `ref/nanobot`

## Next Major Track

- Current slice: Discord policy/routing parity, reply-mode control, isolated slash sessions, persisted `/focus` bindings, and automatic idle/max-age expiry
- Next slice: tools and skills advanced parity after the current Docker runtime slice is committed

## Delivery Policy

- Commit and push every green slice
- Update docs in the same cycle as behavior changes
- Reserve tags and GitHub releases for the end of a validated milestone
- Keep `CHANGELOG.md` current as work lands on `main`
