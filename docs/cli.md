# CLI

ClawLite ships with a single CLI entry point: `clawlite`.

Most commands print JSON to stdout. By default, ClawLite reads `~/.clawlite/config.json`. Use `--config <path>` before the subcommand to point to a different JSON or YAML config file.

## Global Flags

| Flag | What it does | Example |
| --- | --- | --- |
| `--config <path>` | Uses a non-default config file | `clawlite --config ./config.dev.json status` |
| `--version` | Prints the installed version | `clawlite --version` |

The module entry point is also available as `python -m clawlite.cli`.

## Runtime Commands

| Command | What it does | Example |
| --- | --- | --- |
| `start` | Starts the FastAPI gateway | `clawlite start --host 127.0.0.1 --port 8787` |
| `gateway` | Alias of `start` | `clawlite gateway --port 8787` |
| `run <prompt>` | Runs one prompt directly through the engine | `clawlite run "summarize this repo" --session-id cli:test --timeout 30` |
| `status` | Prints a local config/runtime summary | `clawlite status` |
| `dashboard` | Opens or prints the local dashboard handoff | `clawlite dashboard --no-open` |

Notes:

- `run` does not require the gateway to be running.
- `status` includes enabled channels, provider model, heartbeat interval, and bootstrap state.
- `dashboard` prints the current dashboard URL, tokenized handoff URL, bootstrap state, post-onboarding guidance, and can open the browser unless `--no-open` is passed.

## Setup and Onboarding

| Command | What it does | Example |
| --- | --- | --- |
| `configure --flow quickstart` | Guided setup wizard for provider, gateway, Telegram, and workspace | `clawlite configure --flow quickstart` |
| `configure --flow advanced` | Section-by-section guided setup | `clawlite configure --flow advanced` |
| `onboard` | Generates workspace template files without running the wizard | `clawlite onboard --assistant-name ClawLite --user-name Renan` |
| `onboard --wizard` | Runs the onboarding wizard from `onboard` | `clawlite onboard --wizard --flow advanced --overwrite` |

Identity and user flags accepted by `onboard`:

- `--assistant-name`
- `--assistant-emoji`
- `--assistant-creature`
- `--assistant-vibe`
- `--assistant-backstory`
- `--user-name`
- `--user-timezone`
- `--user-context`
- `--user-preferences`
- `--overwrite`

`configure` is the friendly alias of `onboard --wizard`.

## Validation Commands

| Command | What it does | Example |
| --- | --- | --- |
| `validate provider` | Validates the active provider/model config | `clawlite validate provider` |
| `validate channels` | Validates enabled channel config | `clawlite validate channels` |
| `validate onboarding` | Checks workspace bootstrap files | `clawlite validate onboarding` |
| `validate onboarding --fix` | Creates missing workspace files | `clawlite validate onboarding --fix` |
| `validate config` | Runs strict config-key validation | `clawlite validate config` |
| `validate preflight` | Runs local checks plus optional live probes | `clawlite validate preflight --gateway-url http://127.0.0.1:8787` |

Useful `validate preflight` flags:

- `--gateway-url <url>`
- `--token <bearer-token>`
- `--timeout <seconds>`
- `--provider-live`
- `--telegram-live`

Current built-in `validate channels` checks:

- Telegram: requires `token`, warns if `allow_from` is empty.
- Discord: requires `token`.
- Slack: requires `bot_token`, warns if `app_token` is empty.
- WhatsApp: requires `bridge_url`.
- Extra placeholder channels have no deep static validation rules.

## Provider Commands

| Command | What it does | Example |
| --- | --- | --- |
| `provider login openai-codex` | Persists OpenAI Codex OAuth credentials | `clawlite provider login openai-codex` |
| `provider status [provider]` | Shows auth/status for one provider | `clawlite provider status openai` |
| `provider logout [provider]` | Clears Codex OAuth credentials from config | `clawlite provider logout` |
| `provider use <provider> --model <model>` | Persists the active provider/model | `clawlite provider use openai --model openai/gpt-4o-mini` |
| `provider set-auth <provider> --api-key <key>` | Persists API-key auth for non-OAuth providers | `clawlite provider set-auth openrouter --api-key sk-or-...` |
| `provider clear-auth <provider>` | Clears API-key auth and optional base URL | `clawlite provider clear-auth openrouter --clear-api-base` |

Useful flags:

- `provider login openai-codex`: `--access-token`, `--account-id`, `--keep-model`, `--set-model`, `--no-interactive`
- `provider use`: `--fallback-model`, `--clear-fallback`
- `provider set-auth`: `--api-base`, `--header key=value`, `--clear-headers`, `--clear-api-base`
- `provider clear-auth`: `--clear-api-base`

Notes:

- `provider login` and `provider logout` only support `openai-codex` today.
- `--set-model` is a deprecated compatibility flag; Codex login already switches to the default Codex model unless you pass `--keep-model`.
- `provider status` defaults to `openai-codex` when no provider is supplied.
- Provider aliases such as `codex`, `google`, `claude`, `hf`, and `kimi` are accepted where supported by the registry.

## Control and Diagnostics

| Command | What it does | Example |
| --- | --- | --- |
| `heartbeat trigger` | Calls `/v1/control/heartbeat/trigger` on the gateway | `clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787` |
| `pairing list <channel>` | Lists pending pairing requests | `clawlite pairing list telegram` |
| `pairing approve <channel> <code>` | Approves a pending pairing code | `clawlite pairing approve telegram ABC123` |
| `diagnostics` | Prints local diagnostics and optional gateway probes | `clawlite diagnostics --gateway-url http://127.0.0.1:8787` |

Useful flags:

- `heartbeat trigger`: `--gateway-url`, `--token`, `--timeout`
- `diagnostics`: `--gateway-url`, `--token`, `--timeout`, `--no-validation`

Notes:

- Pairing is only meaningful for Telegram today.
- `diagnostics` can probe `/health`, `/v1/status`, and `/v1/diagnostics` when a gateway URL is provided.

## Memory Commands

The bare `memory` command prints an overview. Everything else hangs off `clawlite memory ...`.

| Command | What it does | Example |
| --- | --- | --- |
| `memory` | Prints the overview snapshot | `clawlite memory` |
| `memory doctor` | Emits a diagnostics snapshot | `clawlite memory doctor` |
| `memory doctor --repair` | Runs a safe repair pass before reporting | `clawlite memory doctor --repair` |
| `memory eval` | Runs deterministic retrieval evaluation | `clawlite memory eval --limit 10` |
| `memory quality` | Computes and persists memory quality state | `clawlite memory quality --gateway-url http://127.0.0.1:8787` |
| `memory profile` | Prints the profile snapshot | `clawlite memory profile` |
| `memory suggest` | Prints proactive memory suggestions | `clawlite memory suggest` |
| `memory suggest --no-refresh` | Reads pending suggestions without scanning again | `clawlite memory suggest --no-refresh` |
| `memory snapshot` | Creates a versioned snapshot | `clawlite memory snapshot --tag before-upgrade` |
| `memory version` | Lists available snapshot IDs | `clawlite memory version` |
| `memory rollback <id>` | Rolls memory back to a snapshot | `clawlite memory rollback 20260308-main-before-upgrade` |
| `memory privacy` | Prints the privacy rules snapshot | `clawlite memory privacy` |
| `memory export` | Exports memory state | `clawlite memory export --out ./memory-export.json` |
| `memory import <file>` | Imports memory from a file | `clawlite memory import ./memory-export.json` |
| `memory branches` | Prints branch metadata | `clawlite memory branches` |
| `memory branch <name>` | Creates a branch | `clawlite memory branch experiment --checkout` |
| `memory checkout <name>` | Switches the active branch | `clawlite memory checkout main` |
| `memory merge --source <name> --target <name>` | Merges one branch into another | `clawlite memory merge --source experiment --target main --tag merge` |
| `memory share-optin --user <user> --enabled true|false` | Toggles shared-memory opt-in for one user | `clawlite memory share-optin --user alice --enabled true` |

Useful flags:

- `memory doctor`: `--json`, `--repair`
- `memory quality`: `--json`, `--limit`, `--gateway-url`, `--token`, `--timeout`
- `memory snapshot`: `--tag`
- `memory export`: `--out`
- `memory branch`: `--from-version`, `--checkout`
- `memory merge`: `--source`, `--target`, `--tag`

Notes:

- `memory doctor` and `memory quality` already emit JSON even without `--json`.
- `share-optin --enabled` accepts `true|false`, `yes|no`, or `1|0`.

## Cron Commands

| Command | What it does | Example |
| --- | --- | --- |
| `cron add` | Adds a scheduled job | `clawlite cron add --session-id ops --expression "every 120" --prompt "check alerts"` |
| `cron list` | Lists jobs for a session | `clawlite cron list --session-id ops` |
| `cron remove` | Removes a job by ID | `clawlite cron remove --job-id job_123` |
| `cron enable <job_id>` | Enables a job | `clawlite cron enable job_123` |
| `cron disable <job_id>` | Disables a job | `clawlite cron disable job_123` |
| `cron run <job_id>` | Runs a job immediately | `clawlite cron run job_123` |

`cron add --expression` accepts three forms:

- `every 120`
- `at 2026-03-02T20:00:00`
- standard cron syntax such as `0 9 * * *` (requires `croniter`)

## Skills Commands

| Command | What it does | Example |
| --- | --- | --- |
| `skills list` | Lists discovered skills | `clawlite skills list` |
| `skills list --all` | Includes unavailable skills | `clawlite skills list --all` |
| `skills show <name>` | Prints one skill body and metadata | `clawlite skills show summarize` |
| `skills check` | Emits the aggregated diagnostics report | `clawlite skills check` |
| `skills enable <name>` | Enables a skill in local state | `clawlite skills enable github` |
| `skills disable <name>` | Disables a skill in local state | `clawlite skills disable github` |
| `skills pin <name>` | Pins a skill in local state | `clawlite skills pin summarize` |
| `skills unpin <name>` | Unpins a skill in local state | `clawlite skills unpin summarize` |

Skill discovery includes:

- built-in skills under `clawlite/skills`
- workspace skills under `~/.clawlite/workspace/skills`
- marketplace skills under `~/.clawlite/marketplace/skills`

The local skill state is stored in `~/.clawlite/state/skills-state.json`.

## Common Operator Workflow

Typical first-run flow:

```bash
clawlite configure --flow quickstart
clawlite gateway
clawlite run "hello"
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

Typical provider switch:

```bash
clawlite provider set-auth openai --api-key sk-...
clawlite provider use openai --model openai/gpt-4o-mini
clawlite validate provider
```

Typical memory maintenance:

```bash
clawlite memory doctor
clawlite memory quality --gateway-url http://127.0.0.1:8787
clawlite memory snapshot --tag before-change
```
