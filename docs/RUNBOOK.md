# ClawLite Runbook

Last updated: 2026-03-10

This is the operator-facing runbook for local and milestone validation flows.

## Start The Gateway

```bash
clawlite start --host 127.0.0.1 --port 8787
```

Equivalent alias:

```bash
clawlite gateway --host 127.0.0.1 --port 8787
```

Print or reopen the tokenized dashboard handoff without relaunching onboarding:

```bash
clawlite dashboard --no-open
```

The payload includes the current bootstrap state and the same backup/security notes shown at the end of onboarding.

## Quick Health Checks

```bash
python -m clawlite.cli --help
curl -sS http://127.0.0.1:8787/health | python -m json.tool
curl -sS http://127.0.0.1:8787/api/status | python -m json.tool
curl -sS http://127.0.0.1:8787/api/diagnostics | python -m json.tool
```

## Local Validation

```bash
python -m pytest tests/ -q --tb=short
bash scripts/smoke_test.sh
clawlite validate config
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

For release-grade local validation:

```bash
bash scripts/release_preflight.sh --config ~/.clawlite/config.json --gateway-url http://127.0.0.1:8787
```

## Common Operator Flows

Onboarding and workspace setup:

```bash
clawlite configure --flow quickstart
clawlite configure --flow advanced
clawlite onboard --overwrite
```

Diagnostics and runtime state:

```bash
clawlite diagnostics --gateway-url http://127.0.0.1:8787
clawlite status
clawlite skills check
```

Heartbeat and memory checks:

```bash
clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787
clawlite memory doctor
clawlite memory quality --gateway-url http://127.0.0.1:8787
```

## Incident Triage

1. Confirm the CLI still starts: `python -m clawlite.cli --help`
2. Confirm the gateway is alive: `GET /health`
3. Inspect `GET /api/status` and `GET /api/diagnostics`
4. Run `clawlite validate config`
5. Run `python -m pytest tests/ -q --tb=short` before attempting a hotfix release

## Related Docs

- `docs/OPERATIONS.md` - deeper operational commands and endpoint reference
- `docs/STATUS.md` - current milestone and known gaps
- `docs/AUTONOMY_PLAN.md` - phased engineering plan
- `docs/RELEASING.md` - tag and release process
