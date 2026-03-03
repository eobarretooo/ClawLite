<div align="center">
  <img src="assets/logo.svg" alt="ClawLite" width="110" />
  <h1>ClawLite</h1>
  <p><strong>Autonomous personal AI agent for Linux, built in Python.</strong></p>
  <p><strong>FastAPI gateway, Telegram-first operations, persistent memory, and real tool execution.</strong></p>
  <p>
    <a href="https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml"><img src="https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
    <a href="https://github.com/eobarretooo/ClawLite/actions/workflows/coverage.yml"><img src="https://github.com/eobarretooo/ClawLite/actions/workflows/coverage.yml/badge.svg" alt="Coverage Workflow"></a>
    <a href="https://github.com/eobarretooo/ClawLite/releases"><img src="https://img.shields.io/github/v/release/eobarretooo/ClawLite" alt="Latest Release"></a>
    <a href="https://github.com/eobarretooo/ClawLite/graphs/contributors"><img src="https://img.shields.io/github/contributors/eobarretooo/ClawLite" alt="Contributors"></a>
    <a href="https://github.com/eobarretooo/ClawLite/issues"><img src="https://img.shields.io/github/issues/eobarretooo/ClawLite" alt="Open Issues"></a>
    <a href="https://github.com/eobarretooo/ClawLite/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22good%20first%20issue%22"><img src="https://img.shields.io/github/issues/eobarretooo/ClawLite/good%20first%20issue" alt="Good First Issues"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-linux-0ea5e9" alt="Linux">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT License"></a>
  </p>
</div>

## ⚡ What Is ClawLite
ClawLite is a practical autonomous assistant focused on execution: it receives messages, runs tools, stores memory, schedules jobs, and sends proactive updates through channels.
Unlike heavier alternatives, ClawLite is intentionally compact: around **4.2k lines of focused Python core code** designed for personal operation and fast iteration.

## ✨ Main Features
- 🧠 **Unified agent engine** for CLI, HTTP API, WebSocket, scheduler, and channels.
- 💬 **Telegram-first channel support** with allowlist validation and long-message chunking.
- 🛡️ **Telegram reliability mechanisms**: retry/backoff with jitter, auth circuit breaker for 401/403, typing keepalive during processing with a separate typing auth circuit breaker, formatting fallback, and safe offset commit only after successful processing.
- 🧩 **Skills via `SKILL.md`** with autoload and executable `command/script` actions.
- 🗓️ **Autonomous scheduling** with Cron jobs and heartbeat loops.
- 🧭 **Runtime supervisor** for health checks and bounded self-recovery with cooldown protections.
- 🤖 **Autonomy bootstrap worker (opt-in)** for periodic supervised self-review turns with backlog/cooldown guards, timeout containment, and manual trigger control.
- 🧱 **Autonomy action execution layer** with strict allowlist, denylisted action blocking, per-action cooldown/rate limits, dry-run-only dead-letter replay clamp, and additive audit diagnostics.
- 🗂️ **Persistent memory + sessions** stored under `~/.clawlite/state`.
- 🔌 **Multi-provider LLM support** (Gemini, OpenAI, OpenRouter, Groq, DeepSeek, Anthropic routing, Codex, custom OpenAI-compatible endpoints).
- 🧯 **Provider reliability controls**: bounded retry/backoff (+ jitter), provider circuit breaker, additive provider diagnostics, and optional fallback model failover for retryable failures.
- 🛠️ **Tool execution** for shell, files, web, cron, message routing, skills, and subagents.

## 🚀 Quick Start (4 Steps)
1. **Clone and install**
```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

2. **Initialize workspace identity files**
```bash
clawlite onboard
```

3. **Create minimal config** (`~/.clawlite/config.json`)
```json
{
  "provider": {
    "model": "gemini/gemini-2.5-flash"
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "123456789:AA...",
      "allow_from": ["1850513297"]
    }
  }
}
```

4. **Export API key and start gateway**
```bash
export GEMINI_API_KEY="AIza..."
clawlite start --host 127.0.0.1 --port 8787
```

Health check:
```bash
curl -s http://127.0.0.1:8787/health
```

## 🔧 Minimal Config (Gemini + Telegram)
ClawLite loads config from `~/.clawlite/config.json` by default.

```json
{
  "workspace_path": "/home/your-user/.clawlite/workspace",
  "state_path": "/home/your-user/.clawlite/state",
  "provider": {
    "model": "gemini/gemini-2.5-flash"
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 8787
  },
  "scheduler": {
    "heartbeat_interval_seconds": 1800,
    "timezone": "UTC"
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "123456789:AA...",
      "allow_from": ["1850513297"],
      "poll_timeout_s": 20,
      "poll_interval_s": 1.0
    }
  }
}
```

Environment overrides supported:
- `CLAWLITE_MODEL`
- `CLAWLITE_LITELLM_API_KEY`
- `GEMINI_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`
- `CLAWLITE_GATEWAY_HOST`, `CLAWLITE_GATEWAY_PORT`

## 📡 Supported Channels
| Channel | Status | Notes |
|---|---|---|
| Telegram | ✅ Implemented | Polling, reconnection/backoff, allowlist, chunked outbound |
| Discord | ⚠️ Skeleton | Passive adapter placeholder |
| Slack | ⚠️ Skeleton | Passive adapter placeholder |
| WhatsApp | ⚠️ Skeleton | Passive adapter placeholder |
| Signal | ⚠️ Skeleton | Passive adapter placeholder |
| Google Chat | ⚠️ Skeleton | Passive adapter placeholder |
| Email | ⚠️ Skeleton | Passive adapter placeholder |
| Matrix | ⚠️ Skeleton | Passive adapter placeholder |
| IRC | ⚠️ Skeleton | Passive adapter placeholder |
| iMessage | ⚠️ Skeleton | Passive adapter placeholder |
| DingTalk | ⚠️ Skeleton | Passive adapter placeholder |
| Feishu | ⚠️ Skeleton | Passive adapter placeholder |
| Mochat | ⚠️ Skeleton | Passive adapter placeholder |
| QQ | ⚠️ Skeleton | Passive adapter placeholder |

## 🧰 CLI Commands
| Command | Purpose |
|---|---|
| `clawlite start [--host --port --config]` | Start FastAPI + WebSocket gateway |
| `clawlite gateway [--host --port --config]` | Alias for `clawlite start` |
| `clawlite status` | Show runtime/config status summary |
| `clawlite run "<prompt>" [--session-id]` | Run one prompt through the engine |
| `clawlite onboard [--overwrite ...]` | Generate workspace identity templates |
| `clawlite validate provider|channels|onboarding [--fix]` | Validate operator readiness for provider/channel/workspace |
| `clawlite diagnostics [--gateway-url --token --timeout]` | Emit local diagnostics and optional gateway probes |
| `clawlite skills list [--all]` | List discovered skills |
| `clawlite skills show <name>` | Show metadata/body of one skill |
| `clawlite cron add --session-id --expression --prompt [--name]` | Create scheduled job |
| `clawlite cron list --session-id` | List jobs for session |
| `clawlite cron remove --job-id` | Remove scheduled job |

## 🫀 Heartbeat + Cron (Real Examples)
Create a recurring cron job every 2 minutes:
```bash
clawlite cron add \
  --session-id telegram:1850513297 \
  --expression "every 120" \
  --prompt "Send me a concise project status update" \
  --name "status-ping"
```

Create a one-time reminder:
```bash
clawlite cron add \
  --session-id telegram:1850513297 \
  --expression "at 2026-03-02T20:00:00+00:00" \
  --prompt "Remind me to review release notes" \
  --name "release-reminder"
```

List active jobs:
```bash
clawlite cron list --session-id telegram:1850513297
```

Heartbeat interval is controlled by:
```json
{
  "scheduler": {
    "heartbeat_interval_seconds": 1800
  }
}
```

## 🐳 Docker
No official image is published yet. You can run ClawLite in a Python container:

```bash
docker run --rm -it \
  -p 8787:8787 \
  -v "$HOME/.clawlite:/root/.clawlite" \
  -v "$PWD:/app" \
  -w /app \
  python:3.12-bullseye \
  bash -lc "pip install -U pip && pip install -e . && clawlite start --host 0.0.0.0 --port 8787"
```

## 🤖 Supported Providers
| Provider | Model prefix example | Auth |
|---|---|---|
| Gemini | `gemini/gemini-2.5-flash` | `GEMINI_API_KEY` |
| OpenAI | `openai/gpt-4.1-mini` | `OPENAI_API_KEY` |
| OpenRouter | `openrouter/openai/gpt-4o-mini` | `OPENROUTER_API_KEY` |
| Groq | `groq/llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| DeepSeek | `deepseek/deepseek-chat` | `DEEPSEEK_API_KEY` |
| Anthropic (routing) | `anthropic/claude-3-7-sonnet` | `ANTHROPIC_API_KEY` |
| OpenAI Codex | `openai-codex/codex-mini-latest` | Provider auth token |
| Custom OpenAI-compatible | `custom/<model>` | Configured key/base URL |

## 🏗️ Architecture
```text
clawlite/
├── core/         # engine, prompt builder, memory, skills, subagent loop
├── tools/        # tool abstractions and executable tools
├── bus/          # inbound/outbound events and async queue
├── channels/     # Telegram implementation + channel adapters
├── gateway/      # FastAPI app and WebSocket endpoint
├── scheduler/    # cron service and heartbeat service
├── providers/    # model provider resolution and HTTP adapters
├── session/      # session history store
├── workspace/    # bootstrap + prompt template files
├── skills/       # built-in SKILL.md files
├── config/       # schema + config loader
├── cli/          # command-line interface
└── utils/        # helpers and logging setup
```

## 📊 Status Snapshot (2026-03-03)
- **Working now**
  - Gateway/API v1 endpoints are implemented and documented (`/health`, `/v1/chat`, `/v1/cron/*`, `/v1/ws`).
  - Telegram channel is the only production channel today, with polling, retry/backoff (+ jitter), 401/403 auth circuit breaker, typing keepalive with dedicated typing auth circuit protection, allowlist checks, chunked outbound, formatting fallback, and safe offset commit after successful processing.
  - Telegram reliability test coverage now includes deterministic soak/recovery-style validation for repeated reconnect and outbound transient retry cycles, plus mixed-failure chaos/recovery matrix scenarios (chunking, formatting fallback, 429 retry-after, timeout, and multi-cycle polling recovery).
  - Core loop persistence is now fail-soft: response delivery is preserved when session append or memory consolidation fails, with degraded-mode logging for recovery visibility.
  - Gateway diagnostics now expose additive engine persistence telemetry and session-store durability/recovery counters when diagnostics config exposure is enabled.
  - Long-term memory/session recovery hardening landed: malformed memory JSONL read-repair, per-session context recovery fallback when session history is missing, and additive memory/session recovery diagnostics in engine telemetry.
  - Tool I/O reliability hardening landed: additive tool execution telemetry in engine diagnostics, deterministic `exec` invalid-syntax/truncation safeguards, and safer MCP timeout/network/HTTP/invalid-response handling with bounded retry.
  - Provider reliability hardening landed: fail-soft retry taxonomy (429 non-quota + 5xx + network/timeout), Retry-After support, provider circuit breaker telemetry, and optional one-hop fallback model failover.
  - Scheduler is active with both Cron jobs and Heartbeat loop, plus CLI/API controls.
  - Gateway runtime supervisor is active with additive health telemetry and bounded auto-recovery checks for heartbeat/cron/channel runtime health, plus cooldown-based restart-storm protection.
  - Autonomy loop bootstrap is active as an opt-in gateway subsystem: periodic supervised review turns with bounded timeout, queue-backlog/cooldown guards, additive diagnostics, and manual `/v1/control/autonomy/trigger` control.
  - Autonomy action execution layer is active with allowlisted operations (`validate_provider`, `validate_channels`, `diagnostics_snapshot`, `dead_letter_replay_dry_run`), denylisted unknown-action blocking, per-action cooldown/rate guardrails, quality-confidence and degraded-runtime gates, and additive `autonomy_actions` diagnostics plus persisted audit export (`/v1/control/autonomy/audit`).
  - P1 proactive delivery observability is active: additive outbound/dead-letter telemetry in queue/channel diagnostics plus bounded dead-letter replay control via API.
  - Scheduler reliability telemetry hardening landed: heartbeat/cron now expose additive durability counters, trigger/reason/job health signals, and isolate transient persistence/schedule/job failures without crashing runtime loops.
  - Provider routing is active for Gemini, OpenAI, OpenRouter, Groq, DeepSeek, Anthropic routing, Codex, and custom OpenAI-compatible endpoints.
  - Core tools and workspace templates are live: shell/files/web/cron/message/skills/subagent tools and `IDENTITY`, `SOUL`, `AGENTS`, `TOOLS`, `USER`, `HEARTBEAT`, `BOOTSTRAP`, `memory/MEMORY`.
- **Known gaps**
  - Telegram reliability is improved with long-run soak/recovery validation coverage, but not yet a guaranteed zero-error operation under all network/provider conditions.
  - Typing keepalive cadence/TTL tuning and richer Telegram formatting consistency still need more production validation.
  - Most non-Telegram channels are still skeleton adapters.
  - 24/7 supervision/recovery bootstrap is active and autonomy periodic review bootstrap is available, but full autonomous self-improvement loops with internet research and deeper policy adaptation remain in progress.

## 🛣️ Roadmap
- **P0 Reliability and Core Completion (highest priority)**
  - [ ] Telegram at near-100% reliability: typing signal, formatting stability, resilient retries, and zero-crash channel loop (inspired by [OpenClaw](https://github.com/openclaw/openclaw) + [nanobot](https://github.com/HKUDS/nanobot) reliability targets).
  - [ ] ClawLite core loop fully reliable across Memory, Agents, Heartbeat, Soul context, Tools, and User context.
  - [ ] Gateway v1 stability hardening with expanded integration tests for `/v1/chat`, `/v1/cron/*`, and scheduler dispatch.
  - [x] Provider/runtime robustness: safer auth/config validation, clearer provider error taxonomy, stronger fallback/retry behavior, and additive provider telemetry.
- **P1 Capability Expansion**
  - [ ] Skills system at production quality: discovery, execution diagnostics, guardrails, and repeatable outcomes (OpenClaw/nanobot inspired operator UX).
  - [ ] Subagents at production quality: queue/retry/resume reliability, better observability, and practical delegation flows.
  - [ ] Move from supervised automation to truly autonomous operation with controlled guardrails.
  - [ ] Main objective: autonomous and intelligent self-improvement 24/7 with internet research loops and measurable quality gates.
- **P2 Ecosystem and Collaboration**
  - [ ] Future collaboration network: OpenClaw + nanobot + ClawLite working together in Telegram/Discord group workflows.
  - [ ] Codex 5.3 xhigh + agents/subagents applied to GitHub operations (posts, PRs, commits, releases, READMEs, docs, architecture notes, and continuous learning tasks).
  - [ ] Dashboard for transparent progress tracking, total time spent, and an agent reward system for delivered outcomes.
  - [ ] Vision (concise): `final objective = real autonomy, continuous improvement, and collaboration among agents`.

See full plan in [`ROADMAP.md`](ROADMAP.md).

## 🤝 Contributing
PRs are welcome and encouraged.

- Read [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Check open issues: <https://github.com/eobarretooo/ClawLite/issues>
- Run tests before PR: `pytest -q tests`
- Keep docs aligned with runtime behavior

## 🌍 Community
- Discussions: <https://github.com/eobarretooo/ClawLite/discussions>
- Issues: <https://github.com/eobarretooo/ClawLite/issues>

## 🙏 Acknowledgements
ClawLite is its own implementation.

Thanks to the official repositories [**nanobot**](https://github.com/HKUDS/nanobot) and [**OpenClaw**](https://github.com/openclaw/openclaw) for architectural inspiration and practical reference points.

## 📄 License
This project is licensed under the MIT License. See [`LICENSE`](LICENSE).
