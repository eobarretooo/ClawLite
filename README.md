# ClawLite

![ClawLite logo](assets/logo.svg)

ClawLite is a Linux/Termux-first, execution-focused AI runtime that combines a gateway, scheduler, and persistent memory with Telegram-first delivery reliability.

[![CI](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg)](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform Linux|Termux](https://img.shields.io/badge/platform-linux%20%7C%20termux-0ea5e9)
[![Release](https://img.shields.io/github/v/release/eobarretooo/ClawLite)](https://github.com/eobarretooo/ClawLite/releases)

## What is ClawLite?

ClawLite is a Python runtime for running an agent operationally, not just interactively.

- **Single command surface:** operational commands live in `clawlite/cli/commands.py` (`start`, `gateway`, `run`, `status`, `onboard`, `validate`, `provider`, `diagnostics`, `memory`, `cron`, `skills`).
- **Gateway as control plane:** HTTP + WebSocket routes are implemented in `clawlite/gateway/server.py`.
- **Scheduler-driven automation:** heartbeat and cron execution logic lives in `clawlite/scheduler/heartbeat.py` and `clawlite/scheduler/cron.py`.
- **Persistent memory stack:** memory runtime, backend, and monitoring are in `clawlite/core/memory.py`, `clawlite/core/memory_backend.py`, and `clawlite/core/memory_monitor.py`.

## Key capabilities (implemented)

- **Gateway endpoints:** `GET /health`, `GET /v1/status`, `GET /api/status`, `GET /v1/diagnostics`, `GET /api/diagnostics`, `GET /api/token`, `GET /`, `POST /v1/chat`, `POST /api/message`, `POST /v1/control/heartbeat/trigger`, `POST /v1/cron/add`, `GET /v1/cron/list`, `DELETE /v1/cron/{job_id}`, `WS /v1/ws`, `WS /ws` in `clawlite/gateway/server.py`.
- **Auth modes + token masking:** gateway auth config (`off|optional|required`) is defined in `clawlite/config/schema.py`; token masking for diagnostics endpoints is implemented in `clawlite/gateway/server.py` (`/api/token`).
- **Telegram reliability semantics:** retry/backoff, dedupe, webhook/polling handling, and delivery guardrails are implemented in `clawlite/channels/telegram.py`; behavior contract is documented in `docs/TELEGRAM_RELIABILITY_SEMANTICS.md`.
- **Cron lease/idempotency controls:** lease/claim/finalize behavior is in `clawlite/scheduler/cron.py`.
- **Heartbeat loop + state persistence:** periodic heartbeat processing and state file writes are in `clawlite/scheduler/heartbeat.py`.
- **Bootstrap lifecycle support:** bootstrap loading/finalization behavior is in `clawlite/workspace/loader.py` and finalized through gateway/runtime calls in `clawlite/gateway/server.py`.
- **Provider reliability/failover:** provider registry/failover/reliability layers are in `clawlite/providers/registry.py`, `clawlite/providers/failover.py`, and `clawlite/providers/reliability.py`.
- **Tools + skills plumbing:** tool registration and skill integration are in `clawlite/tools/registry.py`, `clawlite/tools/skill.py`, and `clawlite/core/skills.py`.

## Install

### From source (editable)

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Console entrypoint is declared in `pyproject.toml` (`clawlite = "clawlite.cli:main"`). Module entrypoint is also available: `python -m clawlite.cli`.

### Installer script

```bash
bash scripts/install.sh
```

Installer behavior (venv/bootstrap/symlink flow) is implemented in `scripts/install.sh`.

## Quickstart (2-5 min)

```bash
clawlite onboard --wizard
clawlite validate config
clawlite validate provider
clawlite start --host 127.0.0.1 --port 8787
```

In another terminal:

```bash
clawlite run "health check: respond with gateway status"
clawlite status
```

Equivalent module form:

```bash
python -m clawlite.cli start --host 127.0.0.1 --port 8787
```

Command routing and handlers are implemented in `clawlite/cli/commands.py`.

## Configuration

- **Primary config path:** `~/.clawlite/config.json` via `DEFAULT_CONFIG_PATH` in `clawlite/config/loader.py`.
- **Schema and auth settings:** gateway auth, provider, channels, diagnostics, and policy structures are defined in `clawlite/config/schema.py`.
- **Provider selection:** provider selection commands are implemented in `clawlite/cli/commands.py` (`provider use`, `provider status`, login flows).
- **Telegram settings:** polling/webhook behavior and dynamic webhook route (default `/api/webhooks/telegram`) are wired by `clawlite/config/schema.py`, `clawlite/channels/telegram.py`, and `clawlite/gateway/server.py`.
- **Environment secret overrides:** env overlay handling is in `clawlite/config/loader.py` (for example gateway/provider secrets).

Configuration references:

- `docs/CONFIGURATION.md`
- `docs/config.example.json`
- `docs/TELEGRAM_RELIABILITY_SEMANTICS.md`

## Runbook

- **Run gateway:** `clawlite start --host 127.0.0.1 --port 8787` or `clawlite gateway --host 127.0.0.1 --port 8787` (`clawlite/cli/commands.py`).
- **Check service health/status:** use `GET /health`, `GET /v1/status`, `GET /api/status` (`clawlite/gateway/server.py`).
- **Send runtime messages:** `POST /api/message` or `POST /v1/chat` (`clawlite/gateway/server.py`).
- **Use WebSocket channel:** connect to `WS /ws` or `WS /v1/ws` (`clawlite/gateway/server.py`).
- **Telegram polling mode:** configure `channels.telegram.mode = "polling"` and token in config (`clawlite/config/schema.py`, `clawlite/channels/telegram.py`).
- **Telegram webhook mode:** configure webhook settings; route defaults to `/api/webhooks/telegram` (`clawlite/config/schema.py`, `clawlite/gateway/server.py`).
- **Scheduler operations:** add/list/remove jobs via CLI `clawlite cron ...` and API `POST /v1/cron/add`, `GET /v1/cron/list`, `DELETE /v1/cron/{job_id}` (`clawlite/cli/commands.py`, `clawlite/gateway/server.py`).
- **Heartbeat operations:** periodic loop and state tracking in `clawlite/scheduler/heartbeat.py`; immediate trigger at `POST /v1/control/heartbeat/trigger`.

API reference: `docs/API.md`.

## Tests

CI canonical command:

```bash
python -m pytest tests/ -q --tb=short
```

Smoke test script:

```bash
bash scripts/smoke_test.sh
```

Focused local subsets:

```bash
python -m pytest tests/gateway/test_server.py -q
python -m pytest tests/channels/test_telegram.py -q
python -m pytest tests/scheduler/test_cron.py tests/scheduler/test_heartbeat.py -q
```

Coverage evidence examples: `tests/gateway/test_server.py`, `tests/channels/test_telegram.py`, `tests/scheduler/test_cron.py`, `tests/scheduler/test_heartbeat.py`, `tests/cli/test_commands.py`.

## Security

- Security policy and disclosure process: `SECURITY.md`.
- Gateway auth behavior is defined by schema + server guard logic in `clawlite/config/schema.py` and `clawlite/gateway/server.py`.
- Tool safety gating is configured in schema and enforced at registry level (`clawlite/config/schema.py`, `clawlite/tools/registry.py`).

## Contributing

- Contribution process: `CONTRIBUTING.md`.
- Issue tracker: <https://github.com/eobarretooo/ClawLite/issues>.
- Project roadmap and tracked work: `ROADMAP.md`.
- Public API surface and route contracts: `docs/API.md`.
- License terms: `LICENSE`.

## Status

✅ Shipping now

- Core CLI command surface and onboarding flow (`clawlite/cli/commands.py`, `clawlite/cli/onboarding.py`).
- Gateway HTTP/WS control plane with compatibility aliases (`clawlite/gateway/server.py`).
- Telegram reliability implementation and documented semantics (`clawlite/channels/telegram.py`, `docs/TELEGRAM_RELIABILITY_SEMANTICS.md`).
- Scheduler heartbeat + cron lease/idempotency behavior (`clawlite/scheduler/heartbeat.py`, `clawlite/scheduler/cron.py`).
- Persistent memory runtime and monitoring (`clawlite/core/memory.py`, `clawlite/core/memory_backend.py`, `clawlite/core/memory_monitor.py`).

🚧 In progress / not shipped

- Rich dashboard UI is not shipped in this repository scope.
- `GET /` currently serves a minimal endpoint page from the gateway, not a full dashboard (`clawlite/gateway/server.py`).

## Related projects

- OpenClaw: <https://github.com/openclaw/openclaw>
- nanobot: <https://github.com/HKUDS/nanobot>
- memU: <https://github.com/NevaMind-AI/memU>
