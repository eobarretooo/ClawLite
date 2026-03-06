# ClawLite

Portable runtime-first autonomous assistant for Linux.

## What ClawLite is

ClawLite is a Python agent runtime centered on CLI + gateway operation:

- FastAPI gateway (`/v1/*` + compatibility aliases under `/api/*`)
- WebSocket + HTTP chat entrypoints
- Scheduler services (cron + heartbeat + supervision)
- Multi-provider inference routing and provider auth lifecycle commands
- Memory subsystem with diagnostics, versioning, branching, and quality tuning

The runtime does not depend on a dashboard UI. The gateway root (`GET /`) serves a minimal static HTML entrypoint for endpoint visibility.

## Current status snapshot (through Stage 18)

Major shipped capabilities visible in current code/tests:

- Production-grade gateway contract with auth modes (`off|optional|required`), diagnostics, token masking, HTTP/WS telemetry, and compatibility aliases.
- Runtime scheduler and control-plane paths for heartbeat and cron (`/v1/control/heartbeat/trigger`, `/v1/cron/*`).
- Provider operations in CLI (`provider login/status/logout/use/set-auth/clear-auth`) and release preflight checks.
- ClawMemory lifecycle controls (`doctor`, `quality`, snapshot/version/rollback, branches/merge, export/import, privacy/share-optin).
- Stage 15/16/17/18 memory-quality/autonomy progression:
  - Stage 15: reasoning-layer quality signals (`fact/hypothesis/decision/outcome`) included in quality state/reporting.
  - Stage 16: autonomous memory-quality tuning loop with cooldown/rate limits and persisted tuning state.
  - Stage 17: layer-aware tuning playbooks with action metadata (`playbook_id`, `weakest_layer`, `severity`) and legacy layer alias normalization.
  - Stage 18: layer-specific execution metadata and telemetry (`template_id`, `backfill_limit`, `snapshot_tag`, `action_variant`; `actions_by_layer`, `actions_by_playbook`, `actions_by_action`, `action_status_by_layer`, `last_action_metadata`).

## Quickstart

Prerequisite: Python 3.10+.

1) Install locally

```bash
pip install -e .
```

2) Generate workspace templates / onboarding baseline

```bash
clawlite onboard
# interactive wizard variant:
clawlite onboard --wizard
```

3) Configure provider (example)

```bash
export CLAWLITE_MODEL="gemini/gemini-2.5-flash"
export CLAWLITE_LITELLM_API_KEY="<your-key>"
```

4) Start gateway

```bash
clawlite start --host 127.0.0.1 --port 8787
# alias:
clawlite gateway --host 127.0.0.1 --port 8787
```

5) Send a chat request

```bash
curl -sS http://127.0.0.1:8787/v1/chat \
  -H 'content-type: application/json' \
  -d '{"session_id":"cli:quickstart","text":"hello"}'
```

If auth mode is required, include bearer token (header or query param, per config).

## Key CLI commands

Provider + validation:

```bash
clawlite provider status
clawlite provider use openai --model openai/gpt-4.1-mini
clawlite provider set-auth openai --api-key "<key>"
clawlite validate provider
clawlite validate config
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

Diagnostics + memory + scheduler + skills:

```bash
clawlite diagnostics --gateway-url http://127.0.0.1:8787
clawlite memory
clawlite memory doctor
clawlite memory quality --gateway-url http://127.0.0.1:8787
clawlite cron add --session-id cli:ops --expression "every 300" --prompt "status"
clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787
clawlite skills list
clawlite skills check
```

## Gateway endpoints (v1 + compatibility aliases)

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/` | Minimal static gateway entrypoint (no dashboard dependency) |
| GET | `/health` | Health/readiness snapshot |
| GET | `/v1/status` | Control-plane status |
| GET | `/api/status` | Alias of `/v1/status` |
| GET | `/v1/diagnostics` | Runtime diagnostics snapshot |
| GET | `/api/diagnostics` | Alias of `/v1/diagnostics` |
| POST | `/v1/chat` | Main HTTP chat endpoint |
| POST | `/api/message` | Alias of `/v1/chat` |
| GET | `/api/token` | Masked token diagnostics |
| POST | `/v1/control/heartbeat/trigger` | Trigger heartbeat cycle |
| POST | `/v1/cron/add` | Create cron job |
| GET | `/v1/cron/list` | List cron jobs by session |
| DELETE | `/v1/cron/{job_id}` | Remove cron job |
| WS | `/v1/ws` | Main WebSocket chat |
| WS | `/ws` | Alias of `/v1/ws` |

## Memory and autonomy highlights

- Hybrid memory retrieval and quality tracking are integrated into runtime diagnostics and CLI operations.
- Memory quality state persists scoring, drift assessment, recommendations, and tuning history.
- Tuning loop runs as an autonomous runtime component when enabled, with fail-soft behavior, cooldown, and rate limiting.
- Layer-aware playbooks pick actions based on drift severity and weakest reasoning layer.
- Layer-specific execution details are persisted for auditability (`template_id`, `backfill_limit`, `snapshot_tag`, `action_variant`) together with playbook fields.
- Diagnostics expose tuning telemetry maps and latest action context (`actions_by_layer`, `actions_by_playbook`, `actions_by_action`, `action_status_by_layer`, `last_action_metadata`).

## Testing and CI commands

Local checks:

```bash
pytest -q tests
ruff check clawlite/ --select E9,F --ignore F401,F811
bash scripts/smoke_test.sh
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

CI workflows in `.github/workflows/`:

- `ci.yml` (pytest matrix, lint, smoke, autonomy contract)
- `coverage.yml` (pytest + coverage XML)
- `secret-scan.yml` (gitleaks)

## Docs index

- `docs/QUICKSTART.md`
- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/CONFIGURATION.md`
- `docs/OPERATIONS.md`
- `docs/SKILLS.md`
- `docs/TELEGRAM_RELIABILITY_SEMANTICS.md`
