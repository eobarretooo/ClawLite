<div align="center">
  <img src="assets/logo.svg" alt="ClawLite" width="110" />
  <h1>ClawLite</h1>
  <p><strong>Autonomous personal AI agent for Linux, built in Python.</strong></p>
  <p><strong>FastAPI gateway, CLI-first operations, channel adapters, scheduler, and persistent memory.</strong></p>
  <p>
    <a href="https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml"><img src="https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
    <a href="https://github.com/eobarretooo/ClawLite/releases"><img src="https://img.shields.io/github/v/release/eobarretooo/ClawLite" alt="Latest Release"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-linux-0ea5e9" alt="Linux">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT License"></a>
  </p>
</div>

## What Is ClawLite

ClawLite is an execution-focused assistant runtime that combines a local CLI, FastAPI gateway, channel delivery, scheduler, and memory pipeline in one operational model.

It is designed for practical day-to-day automation with explicit control surfaces:
- Interactive and scripted command execution via CLI.
- HTTP and WebSocket access for external integration.
- Scheduled jobs and heartbeat checks.
- Persistent memory with diagnostics and repair paths.
- Provider routing (including deterministic `openai-codex/*` handling).

## How It Compares

| Project | Language | Primary Runtime | Current ClawLite Relationship |
|---|---|---|---|
| ClawLite | Python | CLI + FastAPI + channels | Active implementation |
| OpenClaw | TypeScript | Gateway + dashboard + channels | Architectural reference for parity work |
| nanobot | Python | Agentic automation workflows | Design influence for operational UX |

This repository tracks parity goals in `ROADMAP.md` and documents currently implemented behavior only.

## Quickstart

1) Install locally:

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

2) Generate workspace templates:

```bash
clawlite onboard
```

3) Validate config and provider wiring:

```bash
clawlite validate config
clawlite validate provider
```

4) Start gateway:

```bash
clawlite start --host 127.0.0.1 --port 8787
```

5) Run one prompt:

```bash
clawlite run "say hello" --session-id cli:default
```

6) Check runtime status and diagnostics:

```bash
clawlite status
clawlite diagnostics --gateway-url http://127.0.0.1:8787
```

## Provider Setup

### Generic provider selection

Use `provider use` to persist the active provider/model:

```bash
clawlite provider use gemini --model gemini/gemini-2.5-flash
clawlite provider use openai --model openai/gpt-4.1-mini
clawlite provider use groq --model groq/llama-3.3-70b-versatile
```

Set a fallback model (or clear it):

```bash
clawlite provider use openai --model openai/gpt-4.1-mini --fallback-model openai/gpt-4o-mini
clawlite provider use openai --model openai/gpt-4.1-mini --clear-fallback
```

Inspect provider status:

```bash
clawlite provider status
clawlite provider status openai
```

### OpenAI Codex login and configuration

ClawLite supports explicit Codex auth lifecycle commands:

```bash
clawlite provider login openai-codex
clawlite provider login openai-codex --access-token "<token>"
clawlite provider login openai-codex --access-token "<token>" --account-id "<org_or_account>" --set-model
clawlite provider login openai-codex --no-interactive
```

Supported flags for `clawlite provider login openai-codex`:
- `--access-token`
- `--account-id`
- `--set-model`
- `--no-interactive`

Status and logout:

```bash
clawlite provider status
clawlite provider status openai-codex
clawlite provider logout
clawlite provider logout openai-codex
```

Codex auth environment variables (checked in this order group):
- `CLAWLITE_CODEX_ACCESS_TOKEN`
- `OPENAI_CODEX_ACCESS_TOKEN`
- `OPENAI_ACCESS_TOKEN`
- `CLAWLITE_CODEX_ACCOUNT_ID`
- `OPENAI_ORG_ID`

Config example (`~/.clawlite/config.json`):

```json
{
  "auth": {
    "providers": {
      "openai_codex": {
        "access_token": "<token>",
        "account_id": "<optional_org_or_account>",
        "source": "config"
      }
    }
  },
  "provider": {
    "model": "openai-codex/gpt-5.3-codex"
  },
  "agents": {
    "defaults": {
      "model": "openai-codex/gpt-5.3-codex"
    }
  }
}
```

Routing note: models with prefix `openai-codex/*` are resolved through deterministic Codex provider routing.

## Channel Setup

### Telegram (implemented, parity in progress)

Telegram currently supports inbound polling plus outbound delivery. Configure in `~/.clawlite/config.json`:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "123456789:AA...",
      "allow_from": ["1850513297"]
    }
  }
}
```

Validate channel readiness:

```bash
clawlite validate channels
```

Current delivery surface:
- Telegram: inbound + outbound.
- Discord/Slack/WhatsApp: outbound adapters.
- Additional channels: placeholders/skeletons.

## Commands Reference

Core runtime:
- `clawlite start [--host ...] [--port ...]`
- `clawlite gateway [--host ...] [--port ...]` (alias)
- `clawlite run "<prompt>" --session-id <id> [--timeout <seconds>]`
- `clawlite status`
- `clawlite diagnostics [--gateway-url <url>] [--token <bearer>] [--timeout <seconds>] [--no-validation]`

Validation and onboarding:
- `clawlite onboard [--overwrite ...]`
- `clawlite validate provider`
- `clawlite validate channels`
- `clawlite validate onboarding [--fix]`
- `clawlite validate config`

Provider lifecycle:
- `clawlite provider use <provider> --model <provider/model> [--fallback-model <provider/model>] [--clear-fallback]`
- `clawlite provider login openai-codex [--access-token ...] [--account-id ...] [--set-model] [--no-interactive]`
- `clawlite provider status [provider]`
- `clawlite provider logout [openai-codex]`

Memory and scheduler:
- `clawlite memory doctor [--repair]`
- `clawlite memory eval [--limit N]`
- `clawlite cron add --session-id <id> --expression "<expr>" --prompt "<text>" [--name <name>]`
- `clawlite cron list --session-id <id>`
- `clawlite cron remove --job-id <id>`
- `clawlite cron enable <job_id>`
- `clawlite cron disable <job_id>`
- `clawlite cron run <job_id>`

Cron `--expression` accepts:
- `every 120`
- `at 2026-03-02T20:00:00`
- `0 9 * * *` (requires `croniter`)

## API Reference

Default base URL: `http://127.0.0.1:8787`

Primary endpoints:
- `GET /health`
- `POST /v1/chat`
- `WS /v1/ws`
- `GET /v1/status`
- `GET /v1/diagnostics`
- `POST /v1/cron/add`
- `GET /v1/cron/list`
- `DELETE /v1/cron/{job_id}`

Compatibility aliases:
- `POST /api/message` -> `POST /v1/chat`
- `GET /api/status` -> `GET /v1/status`
- `GET /api/diagnostics` -> `GET /v1/diagnostics`
- `WS /ws` -> `WS /v1/ws`
- `GET /api/token` (masked token diagnostics)
- `GET /` (lightweight deterministic gateway entrypoint)

More details: `docs/API.md`

## Architecture

```text
clawlite/
|- cli/         command parser and operator commands
|- config/      schema + loader + env overlay
|- core/        engine, prompts, memory, autonomy wiring
|- gateway/     FastAPI server, auth guard, HTTP/WS contracts
|- scheduler/   cron + heartbeat runtime
|- channels/    Telegram and outbound channel adapters
|- providers/   provider registry, routing, HTTP adapters
|- tools/       tool implementations and safety policy hooks
|- session/     session persistence and history windows
|- workspace/   onboarding templates and workspace bootstrap files
|- skills/      built-in SKILL.md catalog
`- utils/       logging and shared helpers
```

## Security Notes

- Gateway auth posture can auto-harden to `required` on non-loopback hosts when a token is configured.
- `/api/token` returns masked diagnostics only; secrets are not returned in plaintext.
- Risky tools (`exec`, `web_fetch`, `web_search`, `mcp`) are governed by channel-aware safety policy.
- Keep secrets in environment variables or local config outside version control.
- Review `SECURITY.md` before exposing gateway endpoints publicly.

## Roadmap

Current priorities are maintained in `ROADMAP.md`:
- P0: core stability and contract hardening.
- P1: operational autonomy and reliability.
- P2: ecosystem maturity and operator experience.

## Testing

Documentation changes do not require runtime tests, but the project test commands are:

```bash
pytest -q tests
bash scripts/smoke_test.sh
```

## Acknowledgements

ClawLite is informed by:
- [OpenClaw](https://github.com/openclaw/openclaw)
- [nanobot](https://github.com/HKUDS/nanobot)
- [memU](https://github.com/NevaMind-AI/memU)

## Contributing and License

- Contribution guide: `CONTRIBUTING.md`
- Issues: <https://github.com/eobarretooo/ClawLite/issues>
- License: MIT (`LICENSE`)
