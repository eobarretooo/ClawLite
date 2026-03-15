# ClawLite Status

Last updated: 2026-03-15

## Summary

ClawLite is a **local-first autonomous agent runtime** in active hardening. The Robustness Milestone is in progress (phases 1–4 of 7 complete). Core runtime, memory, channels, and providers are production-grade. Phases 5–7 are hardening skills, identity, and docs.

> **🤖 AI-built · Solo dev** — Every commit is written by Claude (AI), with the author supervising direction. No team.

## Current Baseline

- Latest tag: `v0.5.0-beta.2`
- `main` is ahead of that tag — Robustness phases 1–4 landed since the tag
- Suite: `python -m pytest tests/core tests/tools tests/jobs` → **510 passed, 0 failed**
- Full suite (all tests): ~1200+ passed (run `python -m pytest tests/ -q --tb=short`)
- CI: pytest on Python 3.10 and 3.12, Ruff lint, smoke imports, autonomy contracts

## Robustness Milestone Progress

| Phase | Commit | What landed |
|-------|--------|-------------|
| 1 — Config + Bus | `8dd97a9` | `ConfigWatcher` hot-reload, `BusJournal` SQLite, typed envelopes (`InboundEvent`/`OutboundEvent`) |
| 2 — Memory | `bf671ab` | Memory hierarchy, `ProactiveContextLoader`, LLM consolidation, TTL, file ingest |
| 3 — Providers + Tools | `8455a59` | `TelemetryRegistry`, streaming recovery, tool timeout middleware, `ToolResultCache`, health checks |
| 4 — Core + Jobs | `d91a585` | `ContextWindowManager`, `JobQueue` + `JobJournal`, `JobsTool`, `JobsConfig`, loop-detection bus events, subagent `parent_session_id` |
| 5–7 | pending | Skills validation/versioning, identity write-back, full docs refresh |

## What Is Complete

### Core Runtime
- FastAPI gateway (HTTP + WebSocket) on `:8787`
- Operator dashboard (packaged HTML/CSS/JS) with live chat, event feed, autorefresh
- Agent engine with `stream_run()` / `ProviderChunk` streaming support
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

### Channels
| Channel | Status |
|---------|--------|
| **Telegram** | ✅ Complete — polling + webhook, reactions, topics, reply keyboards, streaming, offset safety, pairing, dedupe, circuit breaker |
| **Discord** | ✅ Complete — gateway WS, slash commands, buttons, voice messages, webhooks, polls, streaming, embeds, threads, attachments |
| **Email** | 🟡 Usable — IMAP inbound + SMTP outbound |
| **WhatsApp** | 🟡 Usable — webhook inbound + outbound bridge |
| **Slack** | 📤 Send-only |

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

### Workspace Templates
`AGENTS.md` · `IDENTITY.md` · `SOUL.md` · `HEARTBEAT.md` · `USER.md`

## Validation

```bash
python -m pytest tests/ -q --tb=short    # 1178 passed
python -m ruff check --select=E,F,W .   # clean
clawlite validate config
```

## Reference Repositories

- Behavioral parity reference: `/root/projetos/ref/openclaw`
- Autonomy/reliability reference: `/root/projetos/ref/nanobot`
- Memory inspiration reference: `/root/projetos/memU`

## Delivery Policy

- Commit and push every green slice
- Update docs in the same cycle as behavior changes
- Reserve tags and GitHub releases for the end of a validated milestone
- Keep `CHANGELOG.md` current as work lands on `main`
