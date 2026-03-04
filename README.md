<div align="center">
  <img src="assets/logo.svg" alt="ClawLite" width="110" />
  <h1>ClawLite</h1>
  <p><strong>Autonomous personal AI agent for Linux, built in Python.</strong></p>
  <p><strong>FastAPI gateway, Telegram-first operations, persistent memory, and real tool execution.</strong></p>
  <p>
    <a href="https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml"><img src="https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
    <a href="https://github.com/eobarretooo/ClawLite/releases"><img src="https://img.shields.io/github/v/release/eobarretooo/ClawLite" alt="Latest Release"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-linux-0ea5e9" alt="Linux">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT License"></a>
  </p>
</div>

## What ClawLite Is
ClawLite is a practical autonomous assistant focused on execution. It can receive messages, run tools, schedule work, keep persistent memory, and proactively deliver updates through channels.

The same core engine powers CLI, gateway, scheduler, and channel workflows for a single operational model.

## Key Capabilities
- Unified runtime for CLI, HTTP API, WebSocket, scheduler, and channels.
- Telegram inbound support with allowlist and resilient polling.
- Active outbound adapters for Discord, Slack, and WhatsApp.
- Memory tooling for learn/recall/forget/analyze plus `clawlite memory doctor` diagnostics and safe repair path.
- Scheduler with cron jobs and heartbeat loop (`HEARTBEAT_OK` contract + persisted heartbeat state).
- Session controls including `agents.defaults.memory_window` and `agents.defaults.session_retention_messages`.
- Gateway compatibility aliases aligned with OpenClaw-style surface.
- Channel-aware tool safety policy for risky tools (`exec`, `web_fetch`, `web_search`, `mcp`).
- Control-plane endpoints for diagnostics, heartbeat trigger, autonomy trigger/simulate/explain/policy, and dead-letter replay.

## Quickstart
1. Clone and install:

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

2. Bootstrap workspace templates:

```bash
clawlite onboard
```

3. Create `~/.clawlite/config.json` (minimal example below).

4. Export provider key and start the gateway:

```bash
export GEMINI_API_KEY="..."
clawlite start --host 127.0.0.1 --port 8787
```

5. Smoke check:

```bash
curl -sS http://127.0.0.1:8787/health | python -m json.tool
```

## Minimal Config
Default config path: `~/.clawlite/config.json`

```json
{
  "workspace_path": "/home/your-user/.clawlite/workspace",
  "state_path": "/home/your-user/.clawlite/state",
  "provider": {
    "model": "gemini/gemini-2.5-flash"
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 8787,
    "auth": {
      "mode": "off"
    }
  },
  "agents": {
    "defaults": {
      "memory_window": 30,
      "session_retention_messages": 200
    }
  },
  "scheduler": {
    "heartbeat_interval_seconds": 1800,
    "timezone": "UTC"
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "123456789:AA...",
      "allow_from": ["1850513297"]
    }
  },
  "tools": {
    "safety": {
      "enabled": true,
      "risky_tools": ["exec", "web_fetch", "web_search", "mcp"],
      "blocked_channels": ["telegram", "discord", "slack", "whatsapp"],
      "allowed_channels": []
    }
  }
}
```

Common environment overrides:
- `CLAWLITE_MODEL`
- `CLAWLITE_LITELLM_API_KEY`
- `GEMINI_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`
- `CLAWLITE_GATEWAY_HOST`, `CLAWLITE_GATEWAY_PORT`, `CLAWLITE_GATEWAY_TOKEN`

Gateway auth hardening behavior:
- On non-loopback hosts, if a token is configured and auth mode is weaker, runtime posture auto-hardens to `required`.
- Loopback (`127.0.0.1` / localhost) behavior stays unchanged unless explicitly configured otherwise.

## API Highlights
Base URL (default): `http://127.0.0.1:8787`

- `GET /health`: readiness and queue snapshot.
- `POST /v1/chat`: chat execution.
- `WS /v1/ws`: WebSocket chat.
- `GET /v1/status`: control-plane status + auth posture.
- `GET /v1/diagnostics`: operational diagnostics snapshot.
- `POST /v1/control/*`: heartbeat/autonomy/dead-letter control endpoints.
- `POST /v1/cron/add`, `GET /v1/cron/list`, `DELETE /v1/cron/{job_id}`: scheduler API.

Compatibility aliases:
- `GET /api/status` -> `GET /v1/status`
- `POST /api/message` -> `POST /v1/chat`
- `GET /api/diagnostics` -> `GET /v1/diagnostics`
- `WS /ws` -> `WS /v1/ws`
- `GET /api/token`: token diagnostics with masked token only
- `GET /`: lightweight deterministic gateway entrypoint

Full reference: [`docs/API.md`](docs/API.md)

## CLI Highlights
Core commands:
- `clawlite start` (alias: `clawlite gateway`)
- `clawlite run "<prompt>" --session-id <id>`
- `clawlite status`
- `clawlite onboard`
- `clawlite validate provider|channels|onboarding [--fix]`
- `clawlite diagnostics [--gateway-url ...]`
- `clawlite memory doctor [--repair]`
- `clawlite cron add|list|remove|enable|disable|run ...`
- `clawlite skills list|show ...`

## Channels and Providers
### Channels
| Channel | Status | Notes |
|---|---|---|
| Telegram | Implemented | Inbound polling + outbound delivery, allowlist, chunking |
| Discord | Outbound active | HTTP outbound adapter |
| Slack | Outbound active | `chat.postMessage` outbound adapter |
| WhatsApp | Outbound active | Bridge `/send` outbound adapter |
| Signal, Google Chat, Email, Matrix, IRC, iMessage, DingTalk, Feishu, Mochat, QQ | Skeleton | Passive placeholders |

### Providers
| Provider | Model prefix example | Auth |
|---|---|---|
| Gemini | `gemini/gemini-2.5-flash` | `GEMINI_API_KEY` |
| OpenAI | `openai/gpt-4.1-mini` | `OPENAI_API_KEY` |
| OpenRouter | `openrouter/openai/gpt-4o-mini` | `OPENROUTER_API_KEY` |
| Groq | `groq/llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| DeepSeek | `deepseek/deepseek-chat` | `DEEPSEEK_API_KEY` |
| Anthropic (routing) | `anthropic/claude-3-7-sonnet` | `ANTHROPIC_API_KEY` |
| OpenAI Codex | `openai-codex/codex-mini-latest` | Provider token |
| Custom OpenAI-compatible | `custom/<model>` | Configured key/base URL |

## Operations and Testing
Run locally:

```bash
clawlite start --host 127.0.0.1 --port 8787
```

Smoke test:

```bash
bash scripts/smoke_test.sh
```

Test suite:

```bash
pytest -q tests
```

Operational runbook: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)

## Architecture
```text
clawlite/
├── core/         # engine, prompts, memory, skills, autonomy wiring
├── tools/        # tool abstractions and executable tools
├── bus/          # inbound/outbound events and queueing
├── channels/     # Telegram + channel adapters
├── gateway/      # FastAPI app, HTTP API, WebSocket, control-plane
├── scheduler/    # cron and heartbeat services
├── providers/    # model provider resolution and HTTP adapters
├── session/      # per-session history store
├── workspace/    # workspace templates and bootstrap files
├── skills/       # built-in `SKILL.md` assets
├── config/       # schema and config loader
├── cli/          # command-line interface
└── utils/        # logging and shared helpers
```

## Roadmap
Current priorities are tracked in [`ROADMAP.md`](ROADMAP.md):
- P0: core stability and contract hardening
- P1: operational autonomy and reliability
- P2: ecosystem and operator experience

## Acknowledgements
ClawLite is informed by ideas and design inspiration from the following projects:
- [OpenClaw](https://github.com/openclaw/openclaw)
- [memU](https://github.com/NevaMind-AI/memU)
- [nanobot](https://github.com/HKUDS/nanobot)

## Contributing and License
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Issues: <https://github.com/eobarretooo/ClawLite/issues>
- License: MIT, see [`LICENSE`](LICENSE)
